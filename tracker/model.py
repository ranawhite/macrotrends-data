"""Australian property cycle tracker: 1989-92 recession analogue vs today.

Loads two CSVs (the 1988-94 cycle and the current cycle), aligns them on
"months from the price peak", scores the current macro backdrop, checks the
turning-point rules, and projects three 12-month scenarios.

Everything is plain Python (no third-party packages) so it runs anywhere.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

FIELDS = ("cash_rate", "mortgage_rate", "unemployment", "cpi_yoy", "gdp_yoy", "price_index")


@dataclass
class Row:
    period: str  # YYYY-MM
    month: int  # absolute month number (year*12 + month-1)
    cash_rate: float
    mortgage_rate: float
    unemployment: float
    cpi_yoy: float
    gdp_yoy: float
    price_index: float
    note: str = ""
    real_index: float = 0.0
    months_from_peak: int = 0


@dataclass
class Cycle:
    name: str
    rows: list[Row]
    peak_period: str | None = None  # defaults to the highest price_index
    peak: Row = field(init=False)

    def __post_init__(self) -> None:
        self.rows.sort(key=lambda r: r.month)
        if self.peak_period:
            self.peak = next(r for r in self.rows if r.period == self.peak_period)
        else:
            self.peak = max(self.rows, key=lambda r: r.price_index)
        self._deflate()
        for r in self.rows:
            r.months_from_peak = r.month - self.peak.month

    def _deflate(self) -> None:
        """Build a real (inflation-adjusted) index, rebased to 100 at the peak.

        Monthly inflation is approximated from the year-on-year CPI rate of
        each observation and compounded across the gap between observations.
        """
        level = 1.0
        prev = None
        levels = []
        for r in self.rows:
            if prev is not None:
                gap = r.month - prev.month
                level *= (1 + r.cpi_yoy / 100) ** (gap / 12)
            levels.append(level)
            prev = r
        peak_level = levels[self.rows.index(self.peak)]
        for r, lvl in zip(self.rows, levels):
            r.real_index = r.price_index / (lvl / peak_level)

    def at(self, month: int) -> Row:
        """Latest observation at or before an absolute month."""
        best = self.rows[0]
        for r in self.rows:
            if r.month <= month:
                best = r
        return best

    def at_offset(self, months_from_peak: int) -> Row:
        return self.at(self.peak.month + months_from_peak)

    @property
    def latest(self) -> Row:
        return self.rows[-1]


def load(path: Path, name: str, peak_period: str | None = None) -> Cycle:
    rows = []
    with path.open(newline="") as fh:
        for rec in csv.DictReader(fh):
            y, m = (int(x) for x in rec["period"].split("-"))
            rows.append(
                Row(
                    period=rec["period"],
                    month=y * 12 + m - 1,
                    note=(rec.get("note") or "").strip(),
                    **{f: float(rec[f]) for f in FIELDS},
                )
            )
    return Cycle(name, rows, peak_period)


# --------------------------------------------------------------------------
# Indicator scoring. Each indicator maps to -1 (strong downward pressure on
# prices) .. +1 (strong upward pressure). The composite is a weighted mean
# scaled to -100..+100.
# --------------------------------------------------------------------------

def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def change(cycle: Cycle, row: Row, field_name: str, months: int) -> tuple[float, int]:
    prev = cycle.at(row.month - months)
    gap = max(1, row.month - prev.month)
    return getattr(row, field_name) - getattr(prev, field_name), gap


def min_over(cycle: Cycle, row: Row, field_name: str, months: int) -> float:
    vals = [getattr(r, field_name) for r in cycle.rows if row.month - months <= r.month <= row.month]
    return min(vals)


INDICATORS = [
    # key, label, weight
    ("policy", "RBA direction (6-month change in cash rate)", 0.25),
    ("real_rate", "Real cash rate (cash rate minus CPI)", 0.10),
    ("jobs", "Unemployment momentum (rise from 12-month low)", 0.20),
    ("prices", "Home value momentum (annualised, latest ~3 months)", 0.25),
    ("inflation", "Inflation vs RBA 2-3% target (room to cut)", 0.10),
    ("growth", "GDP growth", 0.10),
]


def score(cycle: Cycle, row: Row) -> dict:
    d_cash, _ = change(cycle, row, "cash_rate", 6)
    real = row.cash_rate - row.cpi_yoy
    jobs_rise = row.unemployment - min_over(cycle, row, "unemployment", 12)
    d_price, gap = change(cycle, row, "price_index", 3)
    prev_price = row.price_index - d_price
    price_ann = ((row.price_index / prev_price) ** (12 / gap) - 1) * 100

    parts = {
        "policy": (-clamp(d_cash / 0.75), f"{d_cash:+.2f} pts"),
        # A real cash rate near 0.5% is roughly neutral for Australia.
        "real_rate": (-clamp((real - 0.5) / 2.0), f"{real:+.2f}%"),
        # +0.5pt from the 12-month low is the classic recession trigger (Sahm-style).
        "jobs": (clamp(0.4 - jobs_rise / 0.5 * 1.4), f"+{jobs_rise:.1f} pts"),
        "prices": (clamp(price_ann / 8.0), f"{price_ann:+.1f}% p.a."),
        "inflation": (-clamp((row.cpi_yoy - 2.5) / 1.5), f"{row.cpi_yoy:.1f}%"),
        "growth": (clamp((row.gdp_yoy - 2.0) / 1.5), f"{row.gdp_yoy:+.1f}%"),
    }
    out = []
    total = 0.0
    for key, label, w in INDICATORS:
        s, shown = parts[key]
        total += s * w
        out.append({"key": key, "label": label, "weight": w, "score": round(s, 2), "value": shown})
    return {"composite": round(total * 100), "indicators": out, "price_ann": price_ann}


def regime(composite: int) -> tuple[str, str]:
    if composite <= -40:
        return "Downturn", "critical"
    if composite <= -10:
        return "Softening", "warning"
    if composite < 25:
        return "Stabilising", "neutral"
    return "Upswing", "good"


# --------------------------------------------------------------------------
# Turning-point checklist. These are the conditions that preceded the price
# trough in 1991 and in later downturns (2019, early 2023).
# --------------------------------------------------------------------------

def checklist(cycle: Cycle) -> list[dict]:
    r = cycle.latest
    d_cash3, _ = change(cycle, r, "cash_rate", 3)
    d_cash6, _ = change(cycle, r, "cash_rate", 6)
    d_unemp, _ = change(cycle, r, "unemployment", 3)
    d_price, _ = change(cycle, r, "price_index", 1)
    rules = [
        ("RBA has stopped hiking (no rise in last 3 months)", d_cash3 <= 0,
         f"cash rate {d_cash3:+.2f} pts over 3 months"),
        ("RBA has started cutting", d_cash6 < 0, f"{d_cash6:+.2f} pts over 6 months"),
        ("Inflation back under 3%", r.cpi_yoy < 3.0, f"CPI {r.cpi_yoy:.1f}% y/y"),
        ("Unemployment no longer rising", d_unemp <= 0, f"{d_unemp:+.1f} pts over 3 months"),
        ("Monthly home values back above zero", d_price > 0, f"{d_price:+.1f} index pts last month"),
    ]
    return [{"rule": a, "met": bool(b), "detail": c} for a, b, c in rules]


# --------------------------------------------------------------------------
# 12-month scenarios. Paths are monthly % changes in the national index.
# Probabilities start from a judgement-based prior and tilt with the
# composite score so that a re-run on fresh data moves them.
# --------------------------------------------------------------------------

SCENARIOS = {
    "bull": {
        "label": "Early pivot",
        "story": "Inflation drops back faster than expected; RBA holds then cuts by mid-2027. "
                 "Prices bottom around Jan-Feb 2027 and recover modestly.",
        "path": [-0.8, -0.5, -0.3, -0.1, 0.2, 0.4, 0.5, 0.6, 0.7, 0.7, 0.7, 0.7],
        "prior": 0.20,
    },
    "base": {
        "label": "Grinding correction",
        "story": "One more hike or a long hold. Falls slow through summer, trough around "
                 "Apr-Jun 2027, flat to slightly up by late 2027. No boom inside 12 months.",
        "path": [-1.0, -0.9, -0.8, -0.6, -0.5, -0.3, -0.1, 0.0, 0.1, 0.2, 0.3, 0.3],
        "prior": 0.55,
    },
    "bear": {
        "label": "1990-style recession",
        "story": "Unemployment pushes past 5.5%, forced selling rises, RBA cuts late and hard. "
                 "Prices keep falling through 2027; the rebound comes in 2028.",
        "path": [-1.3, -1.3, -1.2, -1.1, -1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4, -0.3],
        "prior": 0.25,
    },
}


def scenarios(cycle: Cycle, composite: int) -> list[dict]:
    # Tilt: every 10 points of composite below -30 moves 3pp from bull to bear;
    # every 10 points above -30 moves 3pp the other way. Bounded.
    tilt = clamp((-30 - composite) / 10 * 0.03, -0.15, 0.15)
    probs = {
        "bull": max(0.05, SCENARIOS["bull"]["prior"] - tilt),
        "base": SCENARIOS["base"]["prior"],
        "bear": max(0.05, SCENARIOS["bear"]["prior"] + tilt),
    }
    norm = sum(probs.values())
    start = cycle.latest
    out = []
    for key, sc in SCENARIOS.items():
        level = start.price_index
        path = []
        y, m = divmod(start.month, 12)
        trough = (level, start.period)
        for i, pct in enumerate(sc["path"], start=1):
            level *= 1 + pct / 100
            yy, mm = divmod(start.month + i, 12)
            period = f"{yy}-{mm + 1:02d}"
            path.append({"period": period, "months_from_peak": start.months_from_peak + i,
                         "index": round(level, 2)})
            if level < trough[0]:
                trough = (level, period)
        out.append({
            "key": key, "label": sc["label"], "story": sc["story"],
            "probability": round(probs[key] / norm, 2),
            "path": path,
            "trough_period": trough[1],
            "trough_from_peak": round(trough[0] - 100, 1),
            "end_from_peak": round(level - 100, 1),
            "twelve_month_change": round((level / start.price_index - 1) * 100, 1),
        })
    return out


def analogue(hist: Cycle, cur: Cycle) -> dict:
    """What the 1989-92 cycle looked like at the same distance from its peak."""
    n = cur.latest.months_from_peak
    then = hist.at_offset(n)
    ahead = hist.at_offset(n + 12)
    post = [r for r in hist.rows if r.month >= hist.peak.month]
    trough_nom = min(post, key=lambda r: r.price_index)
    trough_real = min(post, key=lambda r: r.real_index)
    recovered = next((r for r in hist.rows if r.month > trough_nom.month and r.price_index >= 100), None)
    return {
        "months_from_peak": n,
        "then": vars(then) | {},
        "twelve_months_later": vars(ahead) | {},
        "hist_trough_nominal": {"period": trough_nom.period, "from_peak": round(trough_nom.price_index - 100, 1),
                                "months": trough_nom.months_from_peak},
        "hist_trough_real": {"period": trough_real.period, "from_peak": round(trough_real.real_index - 100, 1),
                             "months": trough_real.months_from_peak},
        "hist_recovered": recovered.period if recovered else None,
        "hist_recovered_months": recovered.months_from_peak if recovered else None,
    }


def build() -> dict:
    # The 1989-92 cycle peaked in Dec 1989; prices passed that level again in 1993-94.
    hist = load(DATA / "cycle_1988_1994.csv", "1989-92", peak_period="1989-12")
    cur = load(DATA / "current_2024_2026.csv", "2026")
    sc_now = score(cur, cur.latest)
    sc_then = score(hist, hist.at_offset(cur.latest.months_from_peak))
    label, tone = regime(sc_now["composite"])
    return {
        "as_of": cur.latest.period,
        "regime": {"label": label, "tone": tone},
        "score_now": sc_now,
        "score_then": sc_then,
        "checklist": checklist(cur),
        "scenarios": scenarios(cur, sc_now["composite"]),
        "analogue": analogue(hist, cur),
        "series": {
            "hist": [vars(r) for r in hist.rows],
            "cur": [vars(r) for r in cur.rows],
        },
        "peaks": {"hist": hist.peak.period, "cur": cur.peak.period},
        "score_history": [
            {"period": r.period, "months_from_peak": r.months_from_peak,
             "cur": score(cur, r)["composite"]}
            for r in cur.rows
        ],
        "score_history_hist": [
            {"period": r.period, "months_from_peak": r.months_from_peak,
             "hist": score(hist, r)["composite"]}
            for r in hist.rows
        ],
    }


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(build(), indent=2)[:3000])
