# -*- coding: utf-8 -*-
"""骰子酒馆 · 本地服务

一个进程同时干三件事：
  1. 把 web/ 里的页面发给浏览器（默认 http://127.0.0.1:8790）
  2. 管牌桌：你和哦鲸鲸的一张桌，或者 QQ 群里那张桌
  3. 给 QQ 那边留一个 HTTP 口子（qq_bridge.py 就是照这个口子说话）

起法：  python server.py            正常起，顺手开浏览器
        python server.py --quiet    不开窗、不打扰（给 QQ 接入自动拉起用）
"""

import argparse
import json
import os
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import ai
import identity
import qqtext
import rules

try:
    import brain            # 让她本人下场拍板（调模型；没密钥会自动退回本地算法）
except Exception:           # pragma: no cover
    brain = None

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
DEFAULT_PORT = 8790
NAPCAT_HTTP = "http://127.0.0.1:3000"     # NapCat 的 HTTP 口，发 QQ 消息用
IDLE_DROP = 3 * 3600                      # 三小时没人动的桌子自动收掉

_TABLES = {}
_LOCK = threading.RLock()
_seq = [0]
_verbose = True


# ---------------------------------------------------------------- 牌桌管理
def _new_id(prefix="t"):
    _seq[0] += 1
    return "%s%d" % (prefix, _seq[0])


def _touch(entry):
    entry["touched"] = time.time()


def _gc():
    now = time.time()
    for key in [k for k, e in _TABLES.items() if now - e["touched"] > IDLE_DROP]:
        _TABLES.pop(key, None)


def _entry_out(entry):
    return {"id": entry["id"], "kind": entry["kind"], "label": entry["label"],
            "chat": entry["chat"], "state": entry["table"].state()}


def _make_table(humans, target, style="normal", bot_name="哦鲸鲸", brain_mode="local"):
    players = [rules.Player(n, uid=u) for n, u in humans] + [rules.Player(bot_name, bot=True)]
    t = rules.Table(players, target=target)
    t.bot_style = style
    t.brain_mode = brain_mode      # "local" = 期望值算法；"model" = 让她本人调模型拍板
    return t


def _bot_decide(t):
    """她这一手怎么办：优先让她本人想，失败/没开就直接退回本地算法。"""
    who = getattr(t, "who", None)
    if getattr(t, "brain_mode", "local") == "model" and brain is not None:
        out = brain.decide(t, who=who)
        if out:
            return out
    act, idx = ai.decide(t)
    return act, idx, ""


def _play_bot(entry):
    """让哦鲸鲸把这一回合走完，返回每一步（客户端拿着慢慢播）"""
    t = entry["table"]
    steps = []
    for _ in range(120):
        if t.phase == "over" or not t.cur.bot:
            break
        if t.phase == "roll":
            ev = t.roll()
            if ev["type"] == "bust":
                steps.append({"kind": "bust", "lost": ev.get("lost", 0),
                              "line": ai.line("bust"), "state": t.state()})
                t.settle()      # 给界面的是"骰子还在桌上"的那一帧，这里才收场
                break
            else:
                best = max((o["score"] for o in ev.get("options") or []), default=0)
                if best >= 500:
                    q = ai.line("roll_hot")
                elif best <= 100:
                    q = ai.line("roll_meh")
                else:
                    q = ""
                steps.append({"kind": "roll", "line": q, "state": t.state()})
        else:
            act, idx, say = _bot_decide(t)
            if act == "bank":
                ev = t.bank()
                steps.append({"kind": "bank",
                              "line": say or (ai.line("win") if ev.get("win") else ai.line("bank")),
                              "state": t.state()})
            else:
                if act == "roll" or not idx:     # 模型嘴上说"掷"，可这一步必须留牌，替她挑够分的那手
                    cands = rules.legal_keeps(t.rolled)
                    if not cands:
                        break
                    idx = max(cands, key=lambda o: o["score"])["indices"]
                ev = t.keep(idx)
                if ev.get("hot"):
                    steps.append({"kind": "hot", "line": say or ai.line("hot"), "state": t.state()})
                else:
                    steps.append({"kind": "keep", "line": say, "state": t.state()})
    _touch(entry)
    return steps


# ---------------------------------------------------------------- QQ 指令
def qq_command(chat, uid, nick, text):
    """群/私聊里的一句话 -> 该回什么（不是骰子指令就返回 None，交回给她正常聊天）"""
    parsed = qqtext.parse(text)
    if parsed is None:
        return None
    act, args = parsed
    key = "chat:" + str(chat)
    uid = str(uid or "")
    nick = (nick or "无名").strip() or "无名"

    with _LOCK:
        _gc()
        entry = _TABLES.get(key)

        if act == "help":
            return qqtext.HELP

        if act == "new":
            if entry and entry["table"].phase != "over":
                return "这桌还开着呢，接着来：\n" + qqtext.render(entry["table"].state(), uid)
            t = _make_table([(nick, uid)], rules.DEFAULT_TARGET,
                            brain_mode=os.environ.get("DICE_BRAIN", "local"))
            t.who = identity.classify("", uid)   # 群里认不出 IP，只能靠 QQ 号猜是不是爸爸
            label = ("群 " + str(chat)[1:]) if str(chat).startswith("g") else "私聊"
            entry = {"id": _new_id("qq"), "kind": "qq", "label": label, "chat": key,
                     "table": t, "touched": time.time()}
            _TABLES[key] = entry
            return qqtext.render(t.state(), uid)

        if entry is None:
            if act == "join":
                return "还没人开局，先发：骰子开局"
            return "这桌还没支起来，先发：骰子开局"

        t = entry["table"]
        t.who = identity.classify("", uid)      # 谁在敲这句，就按谁的口味来

        if act == "quit":
            _TABLES.pop(key, None)
            return "行，桌子撤了。想再来就发：骰子开局"

        if act == "status":
            return qqtext.render(t.state(), uid)

        if act == "join":
            if any(p.uid == uid for p in t.players):
                return "你已经在桌上了。\n" + qqtext.render(t.state(), uid)
            humans = [p for p in t.players if not p.bot]
            if len(humans) >= 5:
                return "桌子挤不下了，最多 5 个人跟本鱼打。"
            t.players.insert(len(t.players) - 1, rules.Player(nick, uid=uid))
            t._say("%s 坐下了" % nick)
            return "%s 坐下了，接着牌局。\n%s" % (nick, qqtext.render(t.state(), uid))

        # 剩下都是"要动手"的指令
        if t.phase == "over":
            return "这局已经完了。要重开就发：骰子开局"
        if t.phase == "bust":       # 万一上一手停在爆骰这一帧
            t.settle()
        me = t.cur
        if me.bot:
            return "等下，本鱼还在掷。"
        if me.uid != uid:
            return "现在轮到 %s，你先别急。" % me.name

        try:
            if act == "roll":
                ev = t.roll()
                if ev["type"] == "bust":
                    tail = "💥 爆骰！掷出 %s，一颗都不计分%s" % (
                        qqtext._pips(ev["dice"]),
                        "，%d 分飞了" % ev["lost"] if ev.get("lost") else "")
                    t.settle()      # 文字里已经把点数亮过了，这边直接收场
                    steps = []
                else:
                    tail, steps = "", []
            elif act == "bank":
                ev = t.bank()
                tail, steps = "", []
                if ev.get("win"):
                    tail = "🏆 你赢了！"
            elif act in ("keep", "keepall"):
                if act == "keepall":
                    opts = rules.legal_keeps(t.rolled)
                    if not opts:
                        raise rules.RuleError("这手没法全留")
                    idx = max(opts, key=lambda o: (o["score"], len(o["indices"])))["indices"]
                else:
                    idx = qqtext.faces_of(t.state(), args or [])
                    if idx is None:
                        raise rules.RuleError("桌上没有 %s 这颗骰子" % " ".join(map(str, args or [])))
                ev = t.keep(idx)
                tail, steps = "", []
                if ev.get("hot"):
                    tail = "🎉 六颗全留下，洗手重掷！"
        except rules.RuleError as e:
            return str(e) + "\n" + qqtext.render(t.state(), uid)

        if t.cur.bot and t.phase != "over":
            steps = _play_bot(entry)

        parts = []
        if steps:
            parts.append(qqtext.render_steps(steps, t.state(), uid))
        if tail:
            parts.insert(0, tail)
        parts.append(qqtext.render(t.state(), uid))
        return "\n".join(parts)


# ---------------------------------------------------------------- NapCat 转发
def napcat_send_group(gid, text):
    body = json.dumps({"group_id": int(gid), "message": text},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(NAPCAT_HTTP + "/send_group_msg", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


# ---------------------------------------------------------------- HTTP
def _body(handler):
    n = int(handler.headers.get("Content-Length") or 0)
    if not n:
        return {}
    raw = handler.rfile.read(n)
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}


def _api_get(path, qs, ip=""):
    if path == "/api/ping":
        return {"ok": True, "tables": len(_TABLES), "port": PORT}
    if path == "/api/whoami":
        who = identity.classify(ip)
        return {"ip": ip, "who": who}
    if path == "/api/table":
        tid = (qs.get("id") or [""])[0]
        with _LOCK:
            entry = next((e for e in _TABLES.values() if e["id"] == tid), None)
            if not entry:
                return {"error": "找不到这张桌子"}
            return _entry_out(entry)
    if path == "/api/qq/tables":
        with _LOCK:
            _gc()
            out = []
            for e in _TABLES.values():
                if e["kind"] != "qq":
                    continue
                st = e["table"].state()
                out.append({"id": e["id"], "label": e["label"],
                            "players": [{"name": p["name"], "total": p["total"], "bot": p["bot"]}
                                        for p in st["players"]],
                            "phase": st["phase"], "turn": st["turn"], "target": st["target"]})
            return {"tables": out}
    return {"error": "没有这个接口"}


def _api_post(path, data, ip=""):
    if path == "/api/new":
        name = (data.get("name") or "你").strip()[:12] or "你"
        target = int(data.get("target") or rules.DEFAULT_TARGET)
        target = max(500, min(20000, target))
        style = data.get("style") if data.get("style") in ai.STYLE else "normal"
        brain_mode = data.get("brain") if data.get("brain") in ("model", "local") else \
            os.environ.get("DICE_BRAIN", "local")
        with _LOCK:
            _gc()
            t = _make_table([(name, "me")], target, style, brain_mode=brain_mode)
            t.who = identity.classify(ip, data.get("uid") or "")
            entry = {"id": _new_id("solo"), "kind": "solo", "label": name, "chat": "",
                     "table": t, "touched": time.time()}
            _TABLES[entry["id"]] = entry
            return _entry_out(entry)

    if path == "/api/action":
        tid = data.get("id")
        with _LOCK:
            entry = _TABLES.get(tid)
            if not entry:
                return {"error": "找不到这张桌子，刷新一下吧"}
            t = entry["table"]
            seat = data.get("seat")
            op = data.get("op")
            try:
                if op == "settle":          # 爆骰那手停够了，收场换人
                    t.settle()
                    _touch(entry)
                    return _entry_out(entry)
                if seat is not None and int(seat) != t.turn:
                    raise rules.RuleError("还没轮到你")
                if t.cur.bot:
                    raise rules.RuleError("这回合是她/他在掷")
                if op == "roll":
                    t.roll()
                elif op == "keep":
                    t.keep(data.get("indices") or [])
                elif op == "bank":
                    t.bank()
                else:
                    raise rules.RuleError("看不懂这个操作")
            except rules.RuleError as e:
                _touch(entry)
                return {"error": str(e), "state": t.state()}
            _touch(entry)
            return _entry_out(entry)

    if path == "/api/bot_turn":
        tid = data.get("id")
        with _LOCK:
            entry = _TABLES.get(tid)
            if not entry:
                return {"error": "找不到这张桌子"}
            if not entry["table"].cur.bot:
                return {"steps": [], "state": entry["table"].state()}
            steps = _play_bot(entry)
            return {"steps": steps, "state": entry["table"].state()}

    if path == "/api/qq/command":
        reply = qq_command(data.get("chat") or "local", data.get("uid") or "0",
                           data.get("nick") or "试玩的人", data.get("text") or "")
        if reply is None:
            return {"reply": None, "not_dice": True}
        return {"reply": reply}

    if path == "/api/qq/push":
        try:
            r = napcat_send_group(data.get("group") or 0, str(data.get("text") or "")[:1500])
            ok = (r.get("retcode") == 0) or (r.get("status") in ("ok", "async"))
            return {"ok": bool(ok), "raw": r}
        except Exception as e:
            return {"ok": False, "error": "NapCat 没应答（QQ 那边可能没开）：%s" % e}

    if path == "/api/say":
        import persona
        txt = persona.quip(data.get("state") or {}, data.get("event") or "taunt")
        return {"text": txt}

    return {"error": "没有这个接口"}


class Handler(BaseHTTPRequestHandler):
    server_version = "DiceTavern/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if _verbose:
            print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args))

    # ---- 小工具 ----
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, code, body, ctype="application/json; charset=utf-8", cache=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if not cache:
            self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    # ---- 路由 ----
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)
        if path.startswith("/api/"):
            try:
                return self._json(_api_get(path, qs, identity.client_ip(self)))
            except Exception as e:
                return self._json({"error": "服务端出错：%s" % e}, 500)
        return self._static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = _body(self)
            return self._json(_api_post(path, data, identity.client_ip(self)))
        except Exception as e:
            return self._json({"error": "服务端出错：%s" % e}, 500)

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            return self._send(404, "<h1>404</h1><p>牌馆里没这东西</p>",
                              "text/html; charset=utf-8")
        ext = os.path.splitext(full)[1].lower()
        ctype = {".html": "text/html; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".json": "application/json; charset=utf-8",
                 ".svg": "image/svg+xml",
                 ".png": "image/png",
                 ".woff2": "font/woff2"}.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)


PORT = DEFAULT_PORT


def main():
    global PORT, _verbose
    ap = argparse.ArgumentParser(description="骰子酒馆")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1", help="监听地址，走 nginx 就留默认，直连可写 0.0.0.0")
    ap.add_argument("--quiet", action="store_true", help="不打印访问日志、不开浏览器")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    PORT = a.port
    _verbose = not a.quiet

    try:
        ai.get_ev()          # 先把期望值表算好，第一把别卡
    except Exception as e:
        print("期望值表没算出来（不影响玩）：%s" % e)

    srv = ThreadingHTTPServer((a.host, PORT), Handler)
    srv.daemon_threads = True
    url = "http://127.0.0.1:%d/" % PORT
    print("骰子酒馆开张了：%s" % url)
    print("QQ 接入：bot.py 已经挂好钩子的话，群里发「骰子开局」就行。")
    if not (a.quiet or a.no_browser):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n打烊。")


if __name__ == "__main__":
    main()
