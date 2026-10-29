# -*- coding: utf-8 -*-
"""骰子酒馆的单元测试：规则、留骰、爆骰帧、认人。

跑法：python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai          # noqa: E402
import identity    # noqa: E402
import rules       # noqa: E402


class FixedRng:
    """按给定序列出点数的骰子"""

    def __init__(self, seq):
        self.seq = list(seq)

    def randint(self, a, b):
        return self.seq.pop(0)


class ScoreTest(unittest.TestCase):
    def test_singles(self):
        self.assertEqual(rules.score_selection([1])[0], 100)
        self.assertEqual(rules.score_selection([5])[0], 50)

    def test_triples_and_more(self):
        for v, s in ((1, 1000), (2, 200), (3, 300), (4, 400), (5, 500), (6, 600)):
            self.assertEqual(rules.score_selection([v, v, v])[0], s)
        self.assertEqual(rules.score_selection([4, 4, 4, 4])[0], 800)
        self.assertEqual(rules.score_selection([1, 1, 1, 1, 1])[0], 4000)
        self.assertEqual(rules.score_selection([6, 6, 6, 6, 6, 6])[0], 4800)

    def test_straights(self):
        self.assertEqual(rules.score_selection([1, 2, 3, 4, 5])[0], 500)
        self.assertEqual(rules.score_selection([2, 3, 4, 5, 6])[0], 750)
        self.assertEqual(rules.score_selection([1, 2, 3, 4, 5, 6])[0], 1500)

    def test_mixed_selection_takes_everything_scoring(self):
        self.assertEqual(rules.score_selection([1, 1, 5])[0], 250)
        self.assertEqual(rules.score_selection([1, 1, 1, 5, 5])[0], 1100)

    def test_illegal(self):
        self.assertEqual(rules.score_selection([2, 3, 4])[0], 0)
        self.assertEqual(rules.score_selection([2, 2, 3, 3, 4, 4])[0], 0)


class KeepTest(unittest.TestCase):
    def test_can_keep(self):
        self.assertTrue(rules.can_keep([6, 2, 1, 3, 3, 5]))
        self.assertFalse(rules.can_keep([2, 3, 4, 6, 6, 2]))
        self.assertTrue(rules.can_keep([2, 3, 4, 5, 6, 6]))
        self.assertFalse(rules.can_keep([2, 2, 3, 3, 4, 4]))

    def test_legal_keeps_of_one_and_five(self):
        opts = rules.legal_keeps([1, 5])
        self.assertEqual({o["score"] for o in opts}, {150, 100, 50})


class TableTest(unittest.TestCase):
    def make(self, seq=None, target=4000):
        players = [rules.Player("你"), rules.Player("哦鲸鲸", bot=True)]
        return rules.Table(players, target=target, rng=FixedRng(seq or []))

    def test_roll_keep_bank(self):
        t = self.make([1, 5, 5, 2, 2, 3])
        t.roll()
        self.assertEqual(t.phase, "decide")
        self.assertEqual(t.rolled, [1, 5, 5, 2, 2, 3])
        ev = t.keep([0, 1])                 # 1 + 5 = 150
        self.assertEqual(ev["score"], 150)
        self.assertEqual(t.phase, "roll")   # 闲骰要重掷
        self.assertEqual(t.rolled, [])
        self.assertEqual(t.turn_score, 150)
        t.bank()
        self.assertEqual(t.players[0].total, 150)
        self.assertEqual(t.turn, 1)

    def test_hot_dice(self):
        t = self.make()
        t.held = [1, 1, 1, 1, 1]
        t.rolled = [5]
        t.phase = "decide"
        ev = t.keep([0])
        self.assertTrue(ev.get("hot"))
        self.assertEqual(t.held, [])
        self.assertEqual(t.phase, "roll")
        self.assertEqual(t.turn_score, 50)

    def test_bust_keeps_dice_on_table(self):
        t = self.make([2, 3, 4, 6, 6, 4])
        t.turn_score = 300
        ev = t.roll()
        self.assertEqual(ev["type"], "bust")
        self.assertEqual(t.phase, "bust")
        self.assertEqual(t.rolled, [2, 3, 4, 6, 6, 4])   # 骰子还亮在桌上
        self.assertEqual(ev["lost"], 300)
        with self.assertRaises(rules.RuleError):
            t.roll()
        t.settle()
        self.assertEqual(t.phase, "roll")
        self.assertEqual(t.turn, 1)
        self.assertEqual(t.busted, None)

    def test_bank_wins(self):
        t = self.make()
        t.turn_score = 4000
        ev = t.bank()
        self.assertTrue(ev["win"])
        self.assertEqual(t.phase, "over")
        self.assertEqual(t.winner, 0)


class BrainTest(unittest.TestCase):
    def test_ev_table_ready(self):
        ev = ai.get_ev()
        self.assertEqual(len(ev), rules.MAX_DICE + 1)
        self.assertGreater(ev[6], ev[1])

    def test_local_decide_is_legal(self):
        t = TableTest().make([1, 5, 5, 2, 2, 3])
        t.roll()
        act, idx = ai.decide(t)
        self.assertIn(act, ("roll", "keep", "bank"))
        if act == "keep":
            self.assertTrue(idx)
            self.assertTrue(all(0 <= i < len(t.rolled) for i in idx))


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.old = {k: os.environ.get(k) for k in
                    ("DICE_OWNER_QQ", "DICE_OWNER_IPS", "DICE_BEHIND_PROXY")}
        for k in self.old:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_qq_owner(self):
        os.environ["DICE_OWNER_QQ"] = "10001,10002"
        self.assertEqual(identity.classify("", "10001")["who"], "owner")
        self.assertEqual(identity.classify("", "999")["who"], "stranger")

    def test_loopback_is_owner(self):
        self.assertEqual(identity.classify("127.0.0.1")["who"], "owner")
        self.assertEqual(identity.classify("192.168.1.9")["who"], "owner")
        self.assertEqual(identity.classify("8.8.8.8")["who"], "stranger")

    def test_owner_ip_pattern(self):
        os.environ["DICE_OWNER_IPS"] = "1.2.3.*"
        self.assertEqual(identity.classify("1.2.3.44")["who"], "owner")
        self.assertEqual(identity.classify("1.2.4.44")["who"], "stranger")

    def test_behind_proxy_loopback_is_stranger(self):
        os.environ["DICE_BEHIND_PROXY"] = "1"
        self.assertEqual(identity.classify("127.0.0.1")["who"], "stranger")


if __name__ == "__main__":
    unittest.main()
