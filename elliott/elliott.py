"""Elliott Wave engine: price data, swing pivots, wave counts and Fibonacci targets.

Standard library only. The method:

1. Fetch daily OHLC bars (Yahoo Finance chart API, or a local CSV).
2. Find swing pivots with a ZigZag on highs/lows. The swing threshold scales
   with the stock's own volatility and several thresholds are tried, so each
   ticker gets swings that fit how it trades.
3. Try every way of reading the most recent pivots as an Elliott structure:
   an impulse (waves 1-5) in progress, or a finished impulse followed by an
   A-B-C correction in progress, in either direction.
4. Throw out counts that break the three hard rules (wave 2 never retraces
   all of wave 1, wave 3 is never the shortest, wave 4 never enters wave 1
   territory), then score the rest on the Fibonacci guidelines
   (2 = 50-61.8% of 1, 3 = 1.618 x 1, 4 = 38.2% of 3, 5 = 1 x 1, alternation,
   B = 50-78.6% of A, C = 1-1.618 x A).
5. For the best count, report the wave in progress, its Fibonacci target
   zone, the level that invalidates the count, and the next expected wave.

Wave counting is subjective; this gives a rules-based primary count and an
alternate. It is not financial advice.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

UA = "Mozilla/5.0 (elliott-wave-tracker)"


# --------------------------------------------------------------------------- data

@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float


def fetch_yahoo(ticker: str, range_: str = "5y", interval: str = "1d") -> tuple[list[Bar], dict]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(ticker)
        + f"?range={range_}&interval={interval}&includePrePost=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise ValueError(f"{ticker}: {chart['error'].get('description', chart['error'])}")
    res = (chart.get("result") or [None])[0]
    if not res or not res.get("timestamp"):
        raise ValueError(f"{ticker}: no price data returned (check the symbol, e.g. RELIANCE.NS, BHP.AX)")
    q = res["indicators"]["quote"][0]
    bars = []
    for i, ts in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        bars.append(Bar(d, o, h, l, c))
    meta = res.get("meta", {})
    info = {
        "symbol": meta.get("symbol", ticker),
        "name": meta.get("longName") or meta.get("shortName") or meta.get("symbol", ticker),
        "currency": meta.get("currency", ""),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName", ""),
    }
    return bars, info


def load_csv(path: str) -> list[Bar]:
    """CSV with Date, Open, High, Low, Close columns (case-insensitive)."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        k = {key.strip().lower(): v for key, v in r.items()}
        try:
            c = float(k.get("close") or k.get("adj close"))
            out.append(Bar(k["date"], float(k.get("open") or c), float(k.get("high") or c),
                           float(k.get("low") or c), c))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda b: b.date)
    return out


def to_weekly(bars: list[Bar]) -> list[Bar]:
    out: list[Bar] = []
    key = None
    for b in bars:
        y, w, _ = datetime.strptime(b.date, "%Y-%m-%d").isocalendar()
        if (y, w) != key:
            out.append(Bar(b.date, b.open, b.high, b.low, b.close))
            key = (y, w)
        else:
            cur = out[-1]
            cur.high = max(cur.high, b.high)
            cur.low = min(cur.low, b.low)
            cur.close = b.close
    return out


# ------------------------------------------------------------------------ pivots

@dataclass
class Pivot:
    i: int
    price: float
    kind: str  # "H" or "L"
    confirmed: bool = True


def zigzag(bars: list[Bar], pct: float) -> list[Pivot]:
    """Alternating swing highs/lows; a swing needs a `pct` reversal to confirm.
    The final pivot is the extreme since the last confirmed one (unconfirmed)."""
    if len(bars) < 3:
        return []
    piv: list[Pivot] = []
    hi_i = lo_i = 0
    direction = 0
    cand_i = 0
    for i in range(1, len(bars)):
        b = bars[i]
        if direction == 0:
            if b.high > bars[hi_i].high:
                hi_i = i
            if b.low < bars[lo_i].low:
                lo_i = i
            if bars[hi_i].high >= bars[lo_i].low * (1 + pct) and hi_i > lo_i:
                piv.append(Pivot(lo_i, bars[lo_i].low, "L"))
                direction, cand_i = 1, hi_i
            elif bars[lo_i].low <= bars[hi_i].high * (1 - pct) and lo_i > hi_i:
                piv.append(Pivot(hi_i, bars[hi_i].high, "H"))
                direction, cand_i = -1, lo_i
        elif direction == 1:
            if b.high > bars[cand_i].high:
                cand_i = i
            elif b.low <= bars[cand_i].high * (1 - pct):
                piv.append(Pivot(cand_i, bars[cand_i].high, "H"))
                direction, cand_i = -1, i
        else:
            if b.low < bars[cand_i].low:
                cand_i = i
            elif b.high >= bars[cand_i].low * (1 + pct):
                piv.append(Pivot(cand_i, bars[cand_i].low, "L"))
                direction, cand_i = 1, i
    if direction == 1:
        piv.append(Pivot(cand_i, bars[cand_i].high, "H", confirmed=False))
    elif direction == -1:
        piv.append(Pivot(cand_i, bars[cand_i].low, "L", confirmed=False))
    return piv


def volatility(bars: list[Bar]) -> float:
    rets = [abs(math.log(bars[i].close / bars[i - 1].close)) for i in range(1, len(bars))
            if bars[i - 1].close > 0 and bars[i].close > 0]
    return statistics.median(rets) if rets else 0.01


# ---------------------------------------------------------------------- counting

IMPULSE_LABELS = ["0", "1", "2", "3", "4", "5"]
FULL_LABELS = IMPULSE_LABELS + ["A", "B", "C"]


def _fib(r: float, targets: list[tuple[float, float]], tol: float = 0.12) -> float:
    """Closeness of ratio r to the nearest Fibonacci target (weight, value)."""
    return max(w * math.exp(-((r - t) / (tol * max(t, 0.3))) ** 2) for t, w in targets)


@dataclass
class Count:
    direction: int                      # +1 bullish impulse, -1 bearish impulse
    pivots: list[Pivot]                 # pivots labelled 0,1,2,... in order
    score: float
    notes: list[str] = field(default_factory=list)
    degree: str = ""
    threshold: float = 0.0
    kind: str = "impulse"               # "impulse" (0-5 then A-B-C) or "abc" (correction only)

    @property
    def labels(self) -> list[str]:
        if self.kind == "abc":
            return ["5", "A", "B", "C"][: len(self.pivots)]
        return FULL_LABELS[: len(self.pivots)]

    @property
    def current(self) -> str:
        return self.labels[-1]


def evaluate(pivs: list[Pivot], direction: int, prior: list[Pivot],
             n_bars: int = 0) -> tuple[float, list[str]] | None:
    """Score pivots read as 0,1,2,... of an impulse (+ A,B,C). None = breaks a rule."""
    q = [direction * p.price for p in pivs]          # flip so the impulse points up
    n = len(q)
    if n < 2 or q[1] <= q[0]:
        return None
    w = [q[k + 1] - q[k] for k in range(min(n, 6) - 1)]  # signed legs of the impulse
    g: list[float] = []      # guideline scores
    notes: list[str] = []
    # ---- hard rules
    if n >= 3 and q[2] <= q[0]:
        return None                                   # 2 retraces >100% of 1
    if n >= 4 and q[3] <= q[1]:
        return None                                   # 3 must pass the end of 1
    if n >= 5 and q[4] <= q[1]:
        return None                                   # 4 overlaps 1
    if n >= 6:
        l1, l3, l5 = w[0], w[2], w[4]
        if l3 < l1 and l3 < l5:
            return None                               # 3 is the shortest
        if q[5] <= q[3]:
            g.append(0.15)                            # truncated fifth: allowed, rare
            notes.append("truncated 5th")
    # ---- guidelines
    if n >= 3:
        r2 = -w[1] / w[0]
        g.append(_fib(r2, [(0.5, 1), (0.618, 1), (0.382, 0.6), (0.786, 0.6)]))
    if n >= 4:
        r3 = w[2] / w[0]
        g.append(_fib(r3, [(1.618, 1), (2.618, 0.8), (1.0, 0.5), (4.236, 0.4)]))
        if n == 4 and r3 < 1.0:
            g.append(0.3)                             # wave 3 so far shorter than 1
    if n >= 5:
        r4 = -w[3] / w[2]
        g.append(_fib(r4, [(0.382, 1), (0.236, 0.8), (0.5, 0.7)]))
        r2 = -w[1] / w[0]
        alt = (r2 > 0.5) != (r4 > 0.5)
        g.append(1.0 if alt else 0.5)                 # alternation of 2 and 4
        if alt:
            notes.append("2/4 alternate")
    if n >= 6:
        r5 = w[4] / w[0]
        r5b = w[4] / (q[3] - q[0])
        g.append(max(_fib(r5, [(1.0, 1), (0.618, 0.8), (1.618, 0.7)]),
                     _fib(r5b, [(0.618, 0.9), (0.382, 0.6)])))
    if n >= 7:
        a = q[5] - q[6]
        if q[6] >= q[5]:
            return None
        if q[6] <= q[0]:
            return None                               # correction erased the whole impulse
        ra = a / (q[5] - q[0])
        g.append(_fib(ra, [(0.382, 1), (0.5, 0.9), (0.618, 0.8), (0.236, 0.6)]))
    if n >= 8:
        a = q[5] - q[6]
        rb = (q[7] - q[6]) / a
        if rb > 1.382:
            return None
        g.append(_fib(rb, [(0.5, 1), (0.618, 1), (0.786, 0.8), (1.0, 0.6), (1.236, 0.5)]))
        if rb > 1:
            notes.append("expanded flat")
    if n >= 9:
        a = q[5] - q[6]
        rc = (q[7] - q[8]) / a
        if q[8] <= q[0]:
            return None
        g.append(_fib(rc, [(1.0, 1), (1.618, 0.9), (0.618, 0.7), (1.272, 0.6)]))
    guide = statistics.mean(g) if g else 0.35
    coverage = (n - 2) / 7
    # wave 0 should be a real turning point, not a mid-trend swing
    start_ok = all(direction * p.price >= q[0] for p in prior[-4:])
    # prefer structures that explain a meaningful part of the chart at this degree
    span = (pivs[-1].i - pivs[0].i) / n_bars if n_bars else 0.5
    score = (0.52 * guide + 0.2 * coverage + 0.1 * (1.0 if start_ok else 0.0)
             + 0.18 * min(1.0, span / 0.4))
    if span < 0.08:
        return None                                   # too small for this degree
    if not start_ok:
        notes.append("starts mid-trend")
    return score, notes


def evaluate_abc(pivs: list[Pivot], direction: int, prior: list[Pivot],
                 n_bars: int) -> tuple[float, list[str]] | None:
    """Pivots read as the end of a prior `direction` move, then A, B, C against it."""
    q = [direction * p.price for p in pivs]
    n = len(q)
    if n < 2 or q[1] >= q[0]:
        return None
    a = q[0] - q[1]
    g: list[float] = []
    notes: list[str] = []
    if n >= 3:
        rb = (q[2] - q[1]) / a
        if rb > 1.382:
            return None
        g.append(_fib(rb, [(0.5, 1), (0.618, 1), (0.786, 0.8), (1.0, 0.6), (1.236, 0.5)]))
        if rb > 1:
            notes.append("expanded flat")
        elif rb > 0.85:
            notes.append("flat")
    if n >= 4:
        rc = (q[2] - q[3]) / a
        g.append(_fib(rc, [(1.0, 1), (1.618, 0.9), (0.618, 0.7), (1.272, 0.6)]))
    guide = statistics.mean(g) if g else 0.35
    span = (pivs[-1].i - pivs[0].i) / n_bars
    if span < 0.08:
        return None
    # the start must be the extreme of the prior move
    start_ok = all(direction * p.price <= q[0] for p in prior[-4:])
    if not start_ok:
        return None
    score = 0.52 * guide + 0.06 * (n - 1) + 0.18 * min(1.0, span / 0.4)
    return score, notes


def best_counts(bars: list[Bar], degree: str, mults: list[float], top: int = 2) -> list[Count]:
    vol = volatility(bars)
    seen = set()
    found: list[Count] = []
    for m in mults:
        pct = min(max(vol * m, 0.02), 0.6)
        pivs = zigzag(bars, pct)
        if len(pivs) < 3:
            continue
        for L in range(3, min(9, len(pivs)) + 1):
            seq = pivs[-L:]
            prior = pivs[:-L]
            direction = 1 if seq[1].price > seq[0].price else -1
            res = evaluate(seq, direction, prior, len(bars))
            if not res:
                continue
            key = ("imp",) + tuple(p.i for p in seq)
            if key in seen:
                continue
            seen.add(key)
            score, notes = res
            found.append(Count(direction, seq, score, notes, degree, pct))
        for L in range(2, min(4, len(pivs)) + 1):
            seq = pivs[-L:]
            direction = 1 if seq[1].price < seq[0].price else -1
            res = evaluate_abc(seq, direction, pivs[:-L], len(bars))
            key = ("abc",) + tuple(p.i for p in seq)
            if not res or key in seen:
                continue
            seen.add(key)
            found.append(Count(direction, seq, res[0], res[1], degree, pct, kind="abc"))
    found.sort(key=lambda c: c.score, reverse=True)
    # alternate must be a genuinely different read (different current wave or start)
    out: list[Count] = []
    for c in found:
        if all((c.current, c.direction) != (o.current, o.direction) for o in out):
            out.append(c)
        if len(out) == top:
            break
    return out


# -------------------------------------------------------------------- projections

def project(c: Count, last: float) -> dict:
    """Target zone, invalidation and next wave for the wave in progress."""
    d = c.direction
    P = [p.price for p in c.pivots]
    lab = c.current
    if c.kind == "abc":
        P = [None] * 5 + P                # align so the start is P[5], A is P[6]...
    W = lambda a, b: P[b] - P[a]  # noqa: E731
    out: dict = {"wave": lab}

    def lvl(base, length, ratios):
        return [round(base + r * length, 4) for r in ratios]

    trend = "up" if d > 0 else "down"
    counter = "down" if d > 0 else "up"
    if lab == "1":
        out.update(moving=trend, desc="Wave 1 of a new impulse may be forming",
                   target=None, invalid=P[0],
                   next="Wave 2 pullback to 50-61.8% of wave 1",
                   next_zone=lvl(P[1], -W(0, 1), [0.5, 0.618]))
    elif lab == "2":
        out.update(moving=counter, desc="Wave 2 correction",
                   target=lvl(P[1], -W(0, 1), [0.5, 0.618, 0.786]), invalid=P[0],
                   next="Wave 3 (usually strongest), 1.618 x wave 1 from the wave 2 low",
                   next_zone=lvl(P[2], W(0, 1), [1.618, 2.618]))
    elif lab == "3":
        out.update(moving=trend, desc="Wave 3 in progress",
                   target=lvl(P[2], W(0, 1), [1.618, 2.618]), invalid=P[2],
                   next="Wave 4 pullback to 23.6-38.2% of wave 3",
                   next_zone=lvl(P[3], -W(2, 3), [0.236, 0.382]))
    elif lab == "4":
        out.update(moving=counter, desc="Wave 4 correction",
                   target=lvl(P[3], -W(2, 3), [0.236, 0.382, 0.5]), invalid=P[1],
                   next="Wave 5 to new extreme: wave 5 = wave 1, or 0.618 x (0 to 3)",
                   next_zone=sorted([round(P[4] + W(0, 1), 4), round(P[4] + 0.618 * W(0, 3), 4)]))
    elif lab == "5":
        t = sorted([round(P[4] + W(0, 1), 4), round(P[4] + 0.618 * W(0, 3), 4)])
        cap = None
        if abs(W(2, 3)) < abs(W(0, 1)):
            cap = round(P[4] + W(2, 3), 4)   # 5 may not exceed 3 when 3 < 1
        out.update(moving=trend, desc="Wave 5, the last leg of the impulse",
                   target=t, invalid=P[4], cap=cap,
                   next="A-B-C correction, typically back to the wave 4 area",
                   next_zone=sorted([round(P[4], 4), round(P[5] - 0.382 * W(0, 5), 4)]))
    elif lab == "A" and c.kind == "abc":
        out.update(moving=counter, desc="Prior move topped out; wave A of a correction",
                   target=None, invalid=P[5],
                   next="Wave B bounce of 50-78.6% of wave A",
                   next_zone=lvl(P[6], -W(5, 6), [0.5, 0.786]))
    elif lab == "A":
        out.update(moving=counter, desc="Impulse complete; wave A of the correction",
                   target=sorted(lvl(P[5], -W(0, 5), [0.382, 0.5]) + [round(P[4], 4)]),
                   invalid=P[5],
                   next="Wave B bounce of 50-78.6% of wave A",
                   next_zone=lvl(P[6], -W(5, 6), [0.5, 0.786]))
    elif lab == "B":
        out.update(moving=trend, desc="Wave B counter-trend bounce",
                   target=lvl(P[6], -W(5, 6), [0.5, 0.618, 0.786]),
                   invalid=round(P[6] - 1.382 * W(5, 6), 4),
                   next="Wave C, usually equal to A (or 1.618 x A)",
                   next_zone=lvl(P[7], W(5, 6), [1.0, 1.618]))
    elif lab == "C":
        out.update(moving=counter, desc="Wave C, the final leg of the correction",
                   target=lvl(P[7], W(5, 6), [1.0, 1.272, 1.618]), invalid=P[7],
                   next="New impulse in the original trend once C completes",
                   next_zone=None)
    # bias: overall trend of the count plus the near-term move
    tgt = out.get("target")
    leg_up = out["moving"] == "up"
    reached = bool(tgt) and ((last >= min(tgt)) if leg_up else (last <= max(tgt)))
    out["reached"] = reached
    # impulse waves follow the count's direction; the A-B-C correction runs against it
    big = ("Bullish" if d > 0 else "Bearish") if lab in "12345" else ("Bearish" if d > 0 else "Bullish")
    move = "rising" if leg_up else "falling"
    if lab in ("2", "4", "B"):
        s = f"{big} trend; price {move} in a counter-trend wave {lab}"
    else:
        s = f"{big}; price {move} in wave {lab}"
    if reached:
        s += " - target zone reached, wave may be completing"
    out["bias"] = s
    out["invalid"] = round(out["invalid"], 4)
    return out


DEGREES = {
    # name: (bars builder, ZigZag threshold multipliers of median daily move)
    "Primary (weekly, ~5y)": (lambda b: to_weekly(b), [2.5, 3.5, 4.5, 6, 8]),
    "Intermediate (daily, ~1y)": (lambda b: b[-260:], [3, 4, 5, 6.5, 8.5]),
}


def analyze(bars: list[Bar], info: dict | None = None) -> dict:
    info = info or {}
    if len(bars) < 60:
        raise ValueError("need at least 60 daily bars")
    last = bars[-1].close
    result = {"info": info, "last": last, "date": bars[-1].date, "degrees": []}
    for name, (build, mults) in DEGREES.items():
        series = build(bars)
        counts = best_counts(series, name, mults)
        entries = []
        for c in counts:
            entries.append({
                "count": c,
                "proj": project(c, last),
                "points": [(series[p.i].date, p.price, lab, p.confirmed)
                           for p, lab in zip(c.pivots, c.labels)],
            })
        result["degrees"].append({"name": name, "series": series, "entries": entries})
    return result
