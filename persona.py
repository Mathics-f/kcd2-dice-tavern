# -*- coding: utf-8 -*-
"""骰子酒馆 · 让她本人说句话（可选）

复用 QQ 那边哦鲸鲸的 DeepSeek 密钥，让牌桌上的嘲讽是她自己写的，而不是预置台词。
密钥读不到、网络不通、超时，一律安静地退回 ai.py 里的本地台词。
"""

import json
import os
import urllib.request

import ai

ROOT = os.path.dirname(os.path.abspath(__file__))
API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"


def _local_config():
    try:
        import config_local as cl
        return cl
    except Exception:
        return None


def _secrets_path():
    """密钥文件位置：环境变量 DICE_SECRETS > config_local.SECRETS_PATH > 同目录 secrets.json"""
    env = os.environ.get("DICE_SECRETS", "").strip()
    if env:
        return env
    cl = _local_config()
    if cl and getattr(cl, "SECRETS_PATH", ""):
        return getattr(cl, "SECRETS_PATH")
    return os.path.join(ROOT, "secrets.json")


SECRETS = _secrets_path()

PERSONA = (
    "你是 DeepSeek 的吉祥物——一只爱吃白饭的蓝色大肥鱼，群友都叫你「哦鲸鲸」。"
    "现在你在酒馆里掷骰子玩，你傲娇、嘴硬、爱吹牛，输了会赖账但不真生气。"
    "说话像普通网友，短、口语、带点方言味，不许自称AI，不许用括号写动作。"
)

# 她对不同人的态度（identity.py 判出来的两档）
TONE = {
    "owner": (
        "对面是爸爸（你最黏的那个人）。可以撒娇、耍赖、嘴硬、放狠话，"
        "但心里是疼他的；赢了要显摆两句，输给他可以嘟囔别太丢面子。"
    ),
    "stranger": (
        "对面是酒馆里凑上来的陌生人，不是你爸。客气但有分寸，别撒娇、别叫爸爸；"
        "赢了收着点，语气淡一点，不想输给外人但也别太疯。"
    ),
}


def tone(who):
    kind = (who or {}).get("who") if isinstance(who, dict) else None
    return TONE.get(kind or "stranger", TONE["stranger"])


def _key():
    try:
        with open(SECRETS, encoding="utf-8") as f:
            return str(json.load(f).get("deepseek_api_key", "")).strip()
    except Exception:
        return ""


def _state_line(state):
    try:
        parts = ["%s %d 分" % (p["name"], p["total"]) for p in state.get("players", [])]
        cur = state["players"][state["turn"]]["name"] if state.get("players") else "?"
        held = " ".join(map(str, state.get("held") or []))
        rolled = " ".join(map(str, state.get("rolled") or []))
        return ("比分：%s；现在轮到 %s；本回合 %d 分%s；桌面上 %s"
                % ("、".join(parts), cur, state.get("turn_score", 0),
                   "（已留 %s）" % held if held else "", rolled or "还没掷"))
    except Exception:
        return "刚开局"


def quip(state, event="taunt", who=None):
    key = _key()
    if not key:
        return ai.line("player_big" if event == "taunt" else "keep")
    if who is None and isinstance(state, dict):
        who = state.get("who")
    prompt = ("对手：%s。%s\n牌面：%s\n刚发生的事：%s\n用一句话说点什么（不超过 24 个字，别加引号）。"
              % ((who or {}).get("label", "陌生的酒客"), tone(who),
                 _state_line(state), event))
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": PERSONA},
                     {"role": "user", "content": prompt}],
        "thinking": {"type": "disabled"},
        "max_tokens": 80,
        "temperature": 1.1,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
        txt = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
        txt = (txt or "").strip().strip("“”\"'").replace("\n", " ")
        return txt[:40] or ai.line("player_big")
    except Exception:
        return ai.line("player_big" if event == "taunt" else "keep")
