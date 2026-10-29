# -*- coding: utf-8 -*-
"""骰子酒馆 · 规则引擎

照着《天国：拯救2》酒馆里那副骰子（Farkle 变体）做的，
只用普通骰子，没有特殊骰子、没有徽章、没有"恶魔之首"。

计分表（6 颗骰子，先到 target 分的人赢）：
    单颗 1 .......... 100            单颗 5 .......... 50
    1-2-3-4-5 ....... 500            2-3-4-5-6 ....... 750
    1-2-3-4-5-6 ..... 1500
    三同：1=1000，2=200，3=300，4=400，5=500，6=600
    四同/五同/六同：在三同基础上连续翻倍（2 倍 / 4 倍 / 8 倍）

一回合的流程：
    掷全部能掷的骰子 → 至少留出一颗计分骰（不碰计分骰 = 爆骰，本回合分清零）
    → 掷剩下的 / 或者收分落袋。六颗全留下 = 洗手重掷（本回合分保留，六颗骰子全回来）。
"""

import random
from collections import Counter

MAX_DICE = 6
DEFAULT_TARGET = 4000

SINGLE = {1: 100, 5: 50}
TRIPLE = {1: 1000, 2: 200, 3: 300, 4: 400, 5: 500, 6: 600}
STRAIGHTS = {(1, 2, 3, 4, 5): 500, (2, 3, 4, 5, 6): 750, (1, 2, 3, 4, 5, 6): 1500}

_STRAIGHT_LABEL = {
    (1, 2, 3, 4, 5): "1-2-3-4-5 顺子",
    (2, 3, 4, 5, 6): "2-3-4-5-6 顺子",
    (1, 2, 3, 4, 5, 6): "1-6 一条龙",
}


class RuleError(Exception):
    """玩家操作不合法（不是掷骰时机、留法里混了不计分的骰子之类）"""


def kind_score(face, n):
    """同一花色 n 颗的分数；n<3 时按单颗算"""
    if n >= 3:
        return TRIPLE[face] * (2 ** (n - 3))
    return SINGLE.get(face, 0) * n


_MEMO = {}


def _split(dice):
    """把一组骰子完整拆成合法组合，返回 (分数, 说明列表)；拆不干净（有闲骰）返回 None"""
    if not dice:
        return (0, [])
    if dice in _MEMO:
        return _MEMO[dice]

    best = None
    if dice in STRAIGHTS:
        best = (STRAIGHTS[dice], [_STRAIGHT_LABEL[dice]])

    c = Counter(dice)
    # 单颗 1 / 5
    for face, val in SINGLE.items():
        if c.get(face):
            rest = list(dice)
            rest.remove(face)
            sub = _split(tuple(rest))
            if sub is not None:
                cand = (sub[0] + val, sub[1] + ["单%d" % face])
                if best is None or cand[0] > best[0]:
                    best = cand
    # 三同及以上
    for face, cnt in c.items():
        for n in range(3, cnt + 1):
            rest = list(dice)
            for _ in range(n):
                rest.remove(face)
            sub = _split(tuple(rest))
            if sub is not None:
                cand = (sub[0] + kind_score(face, n), sub[1] + ["%d个%d" % (n, face)])
                if best is None or cand[0] > best[0]:
                    best = cand

    _MEMO[dice] = best
    return best


def score_selection(dice):
    """这组骰子能算多少分。返回 (分数, 组合说明)；0 分表示不能这么留。"""
    dice = tuple(sorted(dice))
    if not dice:
        return (0, [])
    got = _split(dice)
    return got if got else (0, [])


def can_keep(dice):
    """这手骰子里有没有能留的东西（只剩闲骰 = 爆骰）

    注意别写成"整理手全都能拆开"：桌上剩下的 6、2、3 这类闲骰不用管，
    只要有任意一部分是计分的就能接着玩。
    """
    dice = list(dice)
    if not dice:
        return False
    c = Counter(dice)
    if c.get(1) or c.get(5):
        return True
    for face, cnt in c.items():
        if cnt >= 3:
            return True
    for mask in range(1, 1 << len(dice)):
        vals = tuple(sorted(dice[i] for i in range(len(dice)) if mask >> i & 1))
        if score_selection(vals)[0]:
            return True
    return False


def legal_keeps(rolled):
    """列出当前这手骰子所有"干净"的留法，按分数从高到低，供界面按钮/AI 用。

    每项：{"indices": [...], "dice": [...], "score": n, "label": "..."}
    """
    rolled = list(rolled)
    n = len(rolled)
    seen, out = set(), []
    for mask in range(1, 1 << n):
        idx = [i for i in range(n) if mask & (1 << i)]
        vals = tuple(sorted(rolled[i] for i in idx))
        if vals in seen:
            continue
        sc, parts = score_selection(vals)
        if not sc:
            continue
        seen.add(vals)
        out.append({
            "indices": idx,
            "dice": list(vals),
            "score": sc,
            "label": "%s = %d" % (" + ".join(parts), sc),
        })
    out.sort(key=lambda o: (-o["score"], len(o["dice"])))
    return out


class Player:
    __slots__ = ("name", "bot", "uid", "total")

    def __init__(self, name, bot=False, uid=""):
        self.name = name
        self.bot = bot
        self.uid = str(uid)
        self.total = 0

    def as_dict(self):
        return {"name": self.name, "bot": self.bot, "uid": self.uid, "total": self.total}


class Table:
    """一张桌子。players 顺序就是轮流顺序；机器人一般放最后一位。"""

    def __init__(self, players, target=DEFAULT_TARGET, rng=None):
        if not players:
            raise ValueError("桌子至少要有一个人")
        self.players = players
        self.target = int(target)
        self.rng = rng or random.Random()
        self.turn = 0
        self.turn_score = 0
        self.held = []          # 本回合已经收下的骰子
        self.rolled = []        # 刚掷出来、还在桌面上的骰子
        self.phase = "roll"     # roll 该掷了 | decide 留下/收分 | bust 爆了还没缓过来 | over 结束
        self.winner = None
        self.busted = None      # 刚爆的这一手：{"dice": [...], "lost": n, "who": 名字, "seat": 座位}
        self.log = []
        self.last_event = {}
        self.rolls = 0          # 本回合掷了几次，洗手重掷时提示用

    # ---------- 小工具 ----------
    @property
    def cur(self):
        return self.players[self.turn]

    def _say(self, text):
        self.log.append(text)
        del self.log[:-40]

    def _reset_turn(self, keep_turn=False):
        self.turn_score = 0
        self.held = []
        self.rolled = []
        self.rolls = 0
        self.busted = None
        self.phase = "roll"
        if not keep_turn:
            self.turn = (self.turn + 1) % len(self.players)

    # ---------- 操作 ----------
    def roll(self):
        if self.phase == "over":
            raise RuleError("牌局已经结束了")
        if self.phase == "bust":
            raise RuleError("这一手还没缓过来呢")
        if self.phase != "roll":
            raise RuleError("现在桌面上还有骰子，先决定留哪颗")
        n = MAX_DICE - len(self.held)
        self.rolled = [self.rng.randint(1, 6) for _ in range(n)]
        self.rolls += 1
        if not can_keep(self.rolled):
            lost = self.turn_score
            # 爆骰不要把骰子清掉：先停在这一手让界面把点数亮出来，由 settle() 收场
            self.turn_score = 0
            self.phase = "bust"
            self.busted = {"dice": list(self.rolled), "lost": lost,
                           "who": self.cur.name, "seat": self.turn}
            self._say("%s 掷出 %s —— 一颗都留不出，爆了%s"
                      % (self.cur.name, self._fmt(self.rolled),
                         "，%d 分飞了" % lost if lost else ""))
            self.last_event = {"type": "bust", "dice": list(self.rolled),
                               "lost": lost, "who": self.cur.name, "seat": self.turn}
            return self.last_event
        self.phase = "decide"
        self._say("%s 掷出 %s" % (self.cur.name, self._fmt(self.rolled)))
        self.last_event = {"type": "roll", "dice": list(self.rolled),
                           "options": legal_keeps(self.rolled), "who": self.cur.name}
        return self.last_event

    def settle(self):
        """爆骰之后缓一下：清桌面、换人。界面停够了再调它。"""
        if self.phase != "bust":
            return None
        who = self.busted["who"] if self.busted else ""
        self._reset_turn()
        self.last_event = {"type": "settled", "next": self.cur.name, "who": who}
        return self.last_event

    def keep(self, indices):
        if self.phase == "bust":
            raise RuleError("这一手还没缓过来呢")
        if self.phase != "decide":
            raise RuleError("现在没得留，先掷骰子")
        try:
            idx = sorted(set(int(i) for i in indices))
        except (TypeError, ValueError):
            raise RuleError("留骰的下标不对")
        if not idx:
            raise RuleError("至少留一颗")
        if any(i < 0 or i >= len(self.rolled) for i in idx):
            raise RuleError("留骰的下标越界了")
        vals = [self.rolled[i] for i in idx]
        sc, parts = score_selection(vals)
        if not sc:
            raise RuleError("%s 这手不合规矩：要么有闲骰，要么根本不计分" % self._fmt(vals))

        self.turn_score += sc
        self.held = sorted(self.held + vals)
        self.rolled = []                  # 桌上的闲骰要重掷，不能直接接着用
        self.phase = "roll"
        self._say("%s 留下 %s（+%d 分，本回合 %d）"
                  % (self.cur.name, self._fmt(vals), sc, self.turn_score))
        self.last_event = {"type": "keep", "dice": vals, "score": sc,
                           "parts": parts, "turn_score": self.turn_score,
                           "who": self.cur.name}
        if len(self.held) >= MAX_DICE:      # 六颗全留下 —— 洗手重掷
            self.held = []
            self.rolled = []
            self.phase = "roll"
            self._say("%s 把六颗全留下了，洗手重掷（本回合 %d 分留着）"
                      % (self.cur.name, self.turn_score))
            self.last_event["hot"] = True
        return self.last_event

    def bank(self):
        if self.phase == "over":
            raise RuleError("牌局已经结束了")
        if self.phase == "bust":
            raise RuleError("这一手还没缓过来呢")
        if not self.turn_score:
            raise RuleError("手上还没分可收")
        p = self.cur
        p.total += self.turn_score
        got = self.turn_score
        self._say("%s 收下 %d 分，总分 %d" % (p.name, got, p.total))
        self.last_event = {"type": "bank", "score": got, "total": p.total,
                           "who": p.name, "seat": self.turn}
        if p.total >= self.target:
            self.winner = self.turn
            self.phase = "over"
            self._say("%s 先到 %d 分，牌局结束" % (p.name, self.target))
            self.last_event["win"] = True
        else:
            self._reset_turn()
        return self.last_event

    # ---------- 给界面的快照 ----------
    def state(self, extra=None):
        d = {
            "target": self.target,
            "phase": self.phase,
            "turn": self.turn,
            "turn_score": self.turn_score,
            "held": list(self.held),
            "rolled": list(self.rolled),
            "rolls": self.rolls,
            "players": [p.as_dict() for p in self.players],
            "winner": self.winner,
            "busted": self.busted,
            "who": getattr(self, "who", None) or {"who": "stranger", "label": "陌生的酒客"},
            "legal": legal_keeps(self.rolled) if self.phase == "decide" else [],
            "log": self.log[-16:],
            "last": self.last_event,
        }
        if extra:
            d.update(extra)
        return d

    @staticmethod
    def _fmt(dice):
        return " ".join(str(d) for d in dice)
