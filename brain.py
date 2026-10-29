# -*- coding: utf-8 -*-
"""骰子酒馆 · 真·AI 对手（让她本人下场拍板）

和 ai.py 的区别：
  ai.py     —— 本地算法，拿期望值表比阈值，零成本、零延迟
  brain.py  —— 把当前牌面和所有合法留法喂给 DeepSeek，让她自己挑，顺手带一句嘴硬台词

任何一步失败（没密钥 / 网络不通 / 超时 / 返回的 JSON 不合法 / 挑了不存在的留法），
都返回 None，调用方随即退回 ai.py 的本地决策 —— 游戏永远不会卡住或让她犯规。

密钥复用 QQ 那边的 secrets.json，优先环境变量 DEEPSEEK_API_KEY。
"""

import json
import os
import re
import urllib.request

import ai
import persona
import rules

API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
TIMEOUT = int(os.environ.get("DICE_BRAIN_TIMEOUT", "12"))
VERBOSE = os.environ.get("DICE_BRAIN_VERBOSE", "") not in ("", "0")

RULES_TEXT = (
    "计分：单颗1=100，单颗5=50；三同 1=1000/2=200/3=300/4=400/5=500/6=600，"
    "四同起翻倍；顺子 1-2-3-4-5=500、2-3-4-5-6=750、六颗一条龙=1500。"
    "每一手必须至少留一颗计分骰，留不出就算爆骰、本回合分全没。"
    "六颗全留叫洗手，本回合分保住、重新掷六颗。"
)

SYSTEM = (
    persona.PERSONA
    + "现在你在跟人玩掷骰子。" + RULES_TEXT
    + "你只能输出一个 JSON 对象，不许有多余的话。"
)


def _key():
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(persona.SECRETS, encoding="utf-8") as f:
            return str(json.load(f).get("deepseek_api_key", "")).strip()
    except Exception:
        return ""


def _options_line(opts):
    letters = "ABCDEFGH"
    parts = []
    for i, o in enumerate(opts[:8]):
        parts.append("%s) %s +%d" % (letters[i], o["label"], o["score"]))
    return "；".join(parts)


def _tone(who):
    return persona.tone(who)


def _prompt(t, who=None):
    st = t.state()
    board = "、".join(
        "%s %d 分" % (p["name"], p["total"]) for p in st["players"]
    )
    rolled = " ".join(str(d) for d in (st.get("rolled") or []))
    held = " ".join(str(d) for d in (st.get("held") or []))
    opts = rules.legal_keeps(t.rolled)
    head = [
        "对面是谁：%s。%s" % ((who or {}).get("label", "陌生的酒客"), _tone(who)),
        "比分：%s（目标 %d，先到者赢）" % (board, st["target"]),
        "桌面骰子：%s" % (rolled or "无"),
        "本回合已留：%s（共 %d 分）" % (held or "无", st["turn_score"]),
        "可留：%s" % (_options_line(opts) if opts else "一手都留不出（只能继续掷）"),
    ]
    ask = (
        "你要决定：继续掷（roll）、留一手（keep，选一个字母）、还是收分（bank，"
        "把本回合 %d 分落袋）。\n"
        '只输出 JSON：{"op":"keep","pick":"A","say":"不超过20个字的嘴硬台词"}'
        % st["turn_score"]
    )
    return "\n".join(head + [ask])


def _parse(text, opts):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    op = str(d.get("op", "")).lower().strip()
    say = str(d.get("say", "") or "").strip().strip('“”"\'')
    say = say.replace("\n", " ")[:30]
    if op == "roll":
        return ("roll", [], say)
    if op == "bank":
        return ("bank", [], say)
    if op == "keep":
        pick = str(d.get("pick", "") or "").upper().strip()[:1]
        idx = "ABCDEFGH".find(pick)
        if 0 <= idx < len(opts):
            return ("keep", list(opts[idx]["indices"]), say)
    return None


def decide(t, who=None):
    """返回 (act, indices, say)；失败返回 None，让调用方退回本地算法。

    who: identity.classify() 的结果（{"who": "owner"/"stranger", "label": "..."}）
    """
    key = _key()
    if not key:
        return None
    if who is None:
        who = getattr(t, "who", None)
    if t.phase != "decide":
        return ("roll", [], "")
    opts = rules.legal_keeps(t.rolled)
    if not opts:
        return ("roll", [], "")
    if not any(o["score"] > 0 for o in opts):
        return ("roll", [], "")

    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _prompt(t, who)},
        ],
        "thinking": {"type": "disabled"},
        "max_tokens": 120,
        "temperature": 0.6,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        if VERBOSE:
            print("[brain] 请求失败：%s" % e)
        return None

    txt = ((d.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "")
    if VERBOSE:
        u = d.get("usage") or {}
        print("[brain] %s（对面：%s）-> %s | tokens=%s" % (
            t.cur.name, (who or {}).get("label", "?"), txt.strip()[:60], u.get("total_tokens")))
    out = _parse(txt, opts)
    if out is None:
        return None
    act, idx, say = out
    if act == "bank" and t.turn_score <= 0:      # 一分没有还想收？那只能继续掷
        return ("roll", [], say)
    return (act, idx, say)
