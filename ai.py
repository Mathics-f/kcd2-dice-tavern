# -*- coding: utf-8 -*-
"""骰子酒馆 · 哦鲸鲸的骰子脑瓜

决策部分是真的算期望值：把所有掷骰结果枚举出来，对每种结果找出"留几颗最划算"，
再迭代出"手里还有 n 颗骰子时接着掷能值多少分"，收不收分就看这个数。
台词部分纯属瞎讲，跟算分没关系。
"""

import json
import math
import os
import random
from collections import Counter
from itertools import combinations, combinations_with_replacement

import rules

EV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ev_cache.json")
EV_VERSION = 2

_EV = None
_CANDS = None

STYLE = {           # 收分的保守程度：0.7 = 有 70% 的期望就落袋（怂），1.18 = 想多掷两把（浪）
    "easy": 0.70,
    "normal": 1.00,
    "bold": 1.18,
}


def _candidates():
    """{骰子颗数: [(点型, 概率, [(留几颗, 分数) 的最佳组合])]}"""
    global _CANDS
    if _CANDS is not None:
        return _CANDS
    out = {}
    for n in range(1, rules.MAX_DICE + 1):
        rows = []
        for ms in combinations_with_replacement(range(1, 7), n):
            c = Counter(ms)
            perm = math.factorial(n)
            for v in c.values():
                perm //= math.factorial(v)
            best = {}
            for r in range(1, n + 1):
                for sub in set(combinations(ms, r)):
                    sc = rules.score_selection(sub)[0]
                    if sc > best.get(r, 0):
                        best[r] = sc
            rows.append((ms, perm / (6 ** n), sorted(best.items())))
        out[n] = rows
    _CANDS = out
    return out


def build_ev(rounds=80):
    """迭代求 期望值[n]：桌面还剩 n 颗骰子时，接着掷平均能再得多少分"""
    cands = _candidates()
    ev = [0.0] * (rules.MAX_DICE + 1)
    for _ in range(rounds):
        new = [0.0] * (rules.MAX_DICE + 1)
        for n in range(1, rules.MAX_DICE + 1):
            acc = 0.0
            for _ms, p, opts in cands[n]:
                best = 0.0
                for r, sc in opts:
                    nxt = rules.MAX_DICE if r == n else n - r
                    v = sc + ev[nxt]
                    if v > best:
                        best = v
                acc += p * best
            new[n] = acc
        diff = max(abs(new[i] - ev[i]) for i in range(len(ev)))
        ev = new
        if diff < 1e-3:
            break
    return ev


def get_ev():
    global _EV
    if _EV is not None:
        return _EV
    try:
        with open(EV_PATH, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version") == EV_VERSION and len(d.get("ev", [])) == rules.MAX_DICE + 1:
            _EV = [float(x) for x in d["ev"]]
            return _EV
    except Exception:
        pass
    _EV = build_ev()
    try:
        with open(EV_PATH, "w", encoding="utf-8") as f:
            json.dump({"version": EV_VERSION, "ev": [round(x, 4) for x in _EV],
                       "note": "期望值表，删了会自动重算"}, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return _EV


def decide(table):
    """返回 ("roll", []) / ("keep", 下标列表) / ("bank", [])"""
    if table.phase == "over":
        return ("none", [])
    if table.phase == "roll":
        return ("roll", [])
    me = table.cur
    if me.total + table.turn_score >= table.target:      # 能一把结束就收
        return ("bank", [])
    opts = rules.legal_keeps(table.rolled)
    if not opts:
        return ("bank", [])
    ev = get_ev()
    n = len(table.rolled)
    best = None
    for o in opts:
        r = len(o["indices"])
        nxt = rules.MAX_DICE if r == n else n - r
        val = o["score"] + ev[nxt]
        if best is None or val > best[0] + 1e-9:
            best = (val, o)
        elif abs(val - best[0]) < 1e-9 and len(o["indices"]) > len(best[1]["indices"]):
            best = (val, o)
    thresh = best[0] * STYLE.get(getattr(table, "bot_style", "normal"), 1.0)
    if table.turn_score > 0 and table.turn_score >= thresh:
        return ("bank", [])
    return ("keep", list(best[1]["indices"]))


# ---------------- 台词 ----------------
_LINES = {
    "start": ["来啊，谁先破产谁请白饭。", "本鱼的骰子可是洗干净的。", "别紧张，输给本鱼很正常。"],
    "roll_hot": ["看见没，这手气的。", "哎呀，运气来了挡不住。", "本鱼可不是靠脸吃饭。"],
    "roll_meh": ["……凑合吧。", "这骰子今天不太听话。", "再来再来。"],
    "keep": ["这几颗留着，看着顺眼。", "收下收下，别浪费。", "嗯，就这么办。"],
    "hot": ["洗手重掷！本鱼今天发财了。", "六颗全留，再来一轮！", "嘿嘿，天助我也。"],
    "bank": ["见好就收，本鱼端着碗走了。", "先落袋为安，谁跟你似的梭哈。", "这点分够了，收工。"],
    "bust": ["……本鱼手滑了。", "这不科学。", "啊，风太大，骰子跑了。"],
    "player_bust": ["哈哈哈哈哈，空的！", "手气不好就别硬撑嘛。", "这运气，本鱼都替你尴尬。"],
    "player_big": ["运气而已，别得意。", "行吧，算你狠。", "哼，一会儿你就笑不出来了。"],
    "player_bank": ["开始攒分了是吧。", "胆小。", "随你，反正本鱼要赢。"],
    "win": ["赢了！今晚白饭加量。", "本鱼说了吧，酒馆里没人比本鱼会掷骰子。", "承让承让，钱留下。"],
    "lose": ["……不算，刚才那是热身。", "本鱼让着你的。", "哼，明天再来，本鱼要赢回来。"],
}


def line(kind, seed=None):
    pool = _LINES.get(kind) or []
    if not pool:
        return ""
    rng = random.Random(seed) if seed is not None else random
    return rng.choice(pool)


def line_for_event(ev, table):
    """给一次事件配一句台词；玩家的事件就阴阳对方，自己的事件就自夸/叹气"""
    if not isinstance(ev, dict):
        return ""
    t = ev.get("type")
    mine = ev.get("who") == table.cur.name and not getattr(table.cur, "bot", False)
    bot_name = next((p.name for p in table.players if p.bot), "")
    i_am = ev.get("who") == bot_name
    if t == "bust":
        return line("bust") if i_am else line("player_bust")
    if t == "bank":
        if ev.get("win"):
            return line("win") if i_am else line("lose")
        return line("bank") if i_am else (line("player_big") if ev.get("score", 0) >= 1000
                                          else line("player_bank"))
    if t == "keep":
        if ev.get("score", 0) >= 1000:
            return line("player_big") if not i_am else line("roll_hot")
        return line("keep") if i_am else ""
    if t == "roll":
        if ev.get("hot"):
            return line("hot") if i_am else ""
        return line("roll_hot") if i_am else ""
    return ""


if __name__ == "__main__":
    ev = get_ev()
    print("期望值表(还剩 n 颗骰子时平均还能得多少分):")
    for i in range(1, rules.MAX_DICE + 1):
        print("  %d 颗 -> %.1f" % (i, ev[i]))
