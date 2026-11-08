"""Checks the engine on a textbook impulse: python3 elliott/test_elliott.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elliott import Bar, analyze, evaluate, Pivot, zigzag  # noqa: E402


def path(points, steps=20):
    """Daily bars walking linearly between (price) waypoints, with a small wiggle."""
    out, d = [], 0
    for a, b in zip(points, points[1:]):
        for k in range(steps):
            c = a + (b - a) * k / steps + (0.4 if k % 2 else -0.4)
            out.append(Bar(f"2024-{1 + d // 28:02d}-{1 + d % 28:02d}", c, c + 0.3, c - 0.3, c))
            d += 1
    return out


class T(unittest.TestCase):
    # 0=100, 1=120 (+20), 2=108 (61.8%), 3=140 (1.618x), 4=128 (38.2%), 5=148 (=1)
    WAVES = [130, 100, 120, 107.6, 140, 127.8, 148, 139]

    def test_zigzag_finds_swings(self):
        piv = zigzag(path(self.WAVES), 0.05)
        for got, want in zip([p.price for p in piv], [130, 100, 120, 107.6, 140, 127.8, 148]):
            self.assertAlmostEqual(got, want, delta=1.5)

    def test_rules(self):
        P = lambda *xs: [Pivot(i * 10, x, "") for i, x in enumerate(xs)]  # noqa: E731
        self.assertIsNotNone(evaluate(P(100, 120, 108, 140, 128, 148), 1, [], 60))
        self.assertIsNone(evaluate(P(100, 120, 99), 1, [], 60))                 # 2 below 0
        self.assertIsNone(evaluate(P(100, 120, 108, 140, 118), 1, [], 60))      # 4 overlaps 1
        self.assertIsNone(evaluate(P(100, 130, 110, 135, 128, 160), 1, [], 60))  # 3 shortest

    def test_reads_wave_A_after_impulse(self):
        r = analyze(path(self.WAVES, 30), {"symbol": "TEST"})
        e = r["degrees"][1]["entries"][0]
        self.assertEqual(e["count"].direction, 1)
        self.assertEqual(e["proj"]["wave"], "A")
        self.assertAlmostEqual(e["proj"]["invalid"], 148.3, delta=1)


if __name__ == "__main__":
    unittest.main()
