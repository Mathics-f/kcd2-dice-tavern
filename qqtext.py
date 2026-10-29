# -*- coding: utf-8 -*-
"""骰子酒馆 · QQ 文本层

只干两件事：把群友那句话翻译成"要干嘛"，把牌面翻译成人话。
真正的规则跑在 rules.py 里，服务端负责执行。
"""

import re

import rules

TRIGGER = re.compile(r"^\s*(?:\[@我\]|@\S{1,24})?\s*[，,：:]?\s*(?:骰子|色子|dice|掷骰)\s*[，,：:]?\s*", re.I)

# 指令别名 -> 标准动作
ALIAS = {
    "掷": "roll", "摇": "roll", "掷骰": "roll", "掷骰子": "roll", "roll": "roll",
    "扔": "roll",
    "留": "keep", "收下": "keep", "留下": "keep", "要": "keep",
    "全留": "keepall", "都要": "keepall",
    "收": "bank", "收分": "bank", "结束": "bank", "存": "bank", "存分": "bank",
    "过": "bank", "pass": "bank",
    "开局": "new", "开始": "new", "来一把": "new", "新局": "new", "开": "new",
    "再来": "new", "开桌": "new",
    "加入": "join", "坐一桌": "join",
    "状态": "status", "看板": "status", "牌面": "status", "桌面": "status",
    "规则": "help", "说明": "help", "玩法": "help", "怎么玩": "help",
    "退出": "quit", "解散": "quit", "不玩了": "quit", "撤": "quit",
}

PIP = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

HELP = (
    "🎲 骰子酒馆 —— 《天国：拯救2》那副骰子，普通骰子版\n"
    "先到 4000 分的人赢。一回合里：\n"
    "· 掷骰，至少留一颗计分骰，剩下接着掷\n"
    "· 留不出任何计分骰 = 爆骰，本回合分清零\n"
    "· 六颗全留下 = 洗手重掷，本回合分保留\n"
    "计分：单1=100 单5=50；1-2-3-4-5=500；2-3-4-5-6=750；一条龙=1500；\n"
    "三同 1=1000，2=200，3=300，4=400，5=500，6=600；四同起每多一颗翻倍。\n"
    "指令：骰子开局 / 骰子加入 / 骰子掷 / 骰子留 1 5 / 骰子全留 / 骰子收 / 骰子状态 / 骰子退出"
)


def parse(text):
    """'骰子 留 1 5' -> ('keep', [1, 5])；不是骰子指令返回 None"""
    if not text:
        return None
    m = TRIGGER.match(text)
    if not m:
        return None
    rest = text[m.end():].strip()
    rest = re.sub(r"^[，,。、!！~～\s]+", "", rest)
    if not rest:
        return ("status", [])
    word = re.split(r"[\s，,。:：]+", rest)[0]
    action = ALIAS.get(word)
    if action is None:
        for key, act in ALIAS.items():
            if rest.startswith(key):
                action = act
                rest = rest[len(key):]
                break
    if action is None:
        faces = [int(x) for x in re.findall(r"[1-6]", rest)]
        return ("keep", faces) if faces else ("status", [])
    if action == "keep":
        faces = [int(x) for x in re.findall(r"[1-6]", rest[len(word):])]
        if not faces:
            return ("keepall", [])
        return ("keep", faces)
    return (action, [])


def faces_of(state, faces):
    """把"留 1 5"里的数字映射成桌面骰子的下标（同点数按顺序取）"""
    rolled = list(state.get("rolled") or [])
    idx, used = [], set()
    for f in faces:
        for i, v in enumerate(rolled):
            if i not in used and v == f:
                idx.append(i)
                used.add(i)
                break
        else:
            return None      # 桌上没这颗骰子
    return idx


def _pips(dice):
    return "".join(PIP.get(int(d), "?") for d in dice) or "—"


def _names(state):
    parts = []
    for p in state["players"]:
        who = ("🐟 " if p["bot"] else "") + p["name"]
        parts.append("%s %d" % (who, p["total"]))
    return " ｜ ".join(parts)


def render(state, uid=""):
    """把牌面渲染成 2~3 行：bot.py 的 send_text 按行拆消息，行数别太多免得被合并"""
    if state["phase"] == "over":
        w = state["players"][state["winner"]] if state.get("winner") is not None else None
        return "🏆 %s 赢了！ ｜ 先到 %d 分" % (w["name"] if w else "有人", state["target"]) + \
               "\n" + _names(state) + "\n要再来一把就发：骰子开局"

    cur = state["players"][state["turn"]]
    mine = (not cur["bot"]) and (not uid or cur["uid"] == str(uid))
    head = "🎲 骰子酒馆 · 先到 %d ｜ %s" % (state["target"], _names(state))
    mid = "轮到 %s%s ｜ 本回合 %d 分%s" % (
        cur["name"], "（你）" if mine else "", state["turn_score"],
        "（已留 %s）" % _pips(state["held"]) if state["held"] else "")

    if state["phase"] == "bust":
        b = state.get("busted") or {}
        return head + "\n💥 %s 掷出 %s，一颗都不计分%s\n发：骰子 掷" % (
            b.get("who") or cur["name"], _pips(b.get("dice") or []),
            "，%d 分飞了" % b["lost"] if b.get("lost") else "")

    if state["phase"] == "decide":
        opts = state.get("legal") or []
        top = sorted(opts, key=lambda o: (-o["score"], -len(o["indices"])))[:3]
        picks = " / ".join("%s=%d" % (" ".join(map(str, o["dice"])), o["score"]) for o in top) or "没得留"
        can = "留 " + " ".join(map(str, top[0]["dice"])) if top else "收"
        tail = "桌面 %s ｜ 能留 %s ｜ 发：骰子 %s ｜ 骰子 收 ｜ 骰子 掷" % (
            _pips(state["rolled"]), picks, can)
    else:
        tail = "桌面 %s ｜ 发：骰子 掷" % (_pips(state["rolled"]) if state["rolled"] else "空")
    return head + "\n" + mid + "\n" + tail


def render_steps(steps, state, uid=""):
    """机器人一整轮的流水，压成一行"""
    bits, quip = [], ""
    for s in steps:
        kind = s.get("kind")
        st = s.get("state") or {}
        last = st.get("last") or {}
        if kind == "roll":
            bits.append("掷 %s" % _pips(st.get("rolled") or []))
        elif kind == "keep" and last.get("type") == "keep":
            bits.append("留 %s +%d" % (_pips(last.get("dice") or []), last.get("score", 0)))
        elif kind == "hot":
            bits.append("六颗全留·洗手重掷")
        elif kind == "bank":
            bits.append("收 %d 分（总分 %d）" % (last.get("score", 0), last.get("total", 0)))
        elif kind == "bust":
            bits.append("爆骰 · %d 分飞了" % (s.get("lost") or 0))
        if s.get("line"):
            quip = s["line"]
    line = "🐟 这轮：" + " → ".join(bits)
    if quip:
        line += " ｜ 💬 " + quip
    return line
