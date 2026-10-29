# -*- coding: utf-8 -*-
"""骰子酒馆 · 给 QQ 那边的接入口（bot 侧薄客户端）

bot.py 里只需要一行调用：

    reply = await asyncio.to_thread(dice_bridge.try_handle, text, is_group, gid, uid, nick)
    if reply:  # 是骰子指令，把 reply 发出去，本次不再交给她自由发挥
        ...

约定：
  · 不是骰子指令 → 返回 None，她照常聊天
  · 是骰子指令   → 返回要发到群里的那段字（可能 1~3 行）
  · 牌馆服务没开 → 顺手把它拉起来（pythonw 无窗口，detached）
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import qqtext  # noqa: E402

BASE = (os.environ.get("DICE_TAVERN_URL") or "http://127.0.0.1:8790").rstrip("/")
AUTOSTART = os.environ.get("DICE_TAVERN_AUTOSTART", "1") != "0"
TIMEOUT = float(os.environ.get("DICE_TAVERN_TIMEOUT", "20"))

_health_at = [0.0]
_health_ok = [False]


def health(timeout=0.5):
    try:
        with urllib.request.urlopen(BASE + "/api/ping", timeout=timeout) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception:
        return False


def _find_pythonw():
    exe = sys.executable or ""
    cand = exe.replace("python.exe", "pythonw.exe")
    if cand != exe and os.path.isfile(cand):
        return cand
    return exe


def ensure_server(force=False):
    """牌馆不在就拉起来；force=True 表示上一次确认过它活着，可以省一次探测"""
    now = time.time()
    if not force and _health_ok[0] and now - _health_at[0] < 20:
        return True
    if health():
        _health_at[0], _health_ok[0] = time.time(), True
        return True
    _health_ok[0] = False
    if not AUTOSTART:
        return False
    try:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
        subprocess.Popen(
            [_find_pythonw(), os.path.join(HERE, "server.py"), "--quiet", "--no-browser"],
            cwd=HERE, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kwargs)
    except Exception as e:
        print(f"  骰子酒馆没能自动拉起: {e}")
        return False
    for _ in range(24):
        time.sleep(0.25)
        if health():
            _health_at[0], _health_ok[0] = time.time(), True
            return True
    return False


def _post(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return False, json.loads(e.read().decode("utf-8")).get("error") or str(e)
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def try_handle(text, is_group, gid, uid, nick=""):
    """是骰子指令就替她玩一把，返回要说的话；否则 None"""
    if not text:
        return None
    act = qqtext.parse(text)
    if act is None:
        return None
    if not ensure_server():
        return "骰子酒馆没开门（127.0.0.1:8790 连不上），我这边也没辙了……"
    chat = ("g" + str(gid)) if is_group else ("p" + str(uid))
    ok, data = _post("/api/qq/command", {
        "chat": chat, "uid": str(uid), "nick": nick or "群友", "text": text,
    })
    if not ok:
        return "骰子酒馆那边出岔子了：%s" % data
    return (data.get("reply") or "").strip() or None


if __name__ == "__main__":  # 手动试一句：python qq_bridge.py "骰子开局"
    msg = " ".join(sys.argv[1:]) or "骰子开局"
    print(try_handle(msg, True, "000000", "111", "测试员"))
