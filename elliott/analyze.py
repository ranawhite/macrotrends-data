"""Elliott Wave analysis for any ticker.

    python3 elliott/analyze.py AAPL                 # US stock
    python3 elliott/analyze.py RELIANCE.NS TCS.NS   # NSE India (.BO for BSE)
    python3 elliott/analyze.py ^NSEI BHP.AX         # Nifty 50 index, ASX stock
    python3 elliott/analyze.py XYZ --csv prices.csv # offline, from a CSV

Prints the primary and alternate wave count for two degrees and writes an
interactive chart to docs/elliott/<TICKER>.html (skip with --no-html).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elliott import analyze, fetch_yahoo, load_csv  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "elliott")


def fmt(x, cur=""):
    if x is None:
        return "-"
    if isinstance(x, (list, tuple)):
        return " - ".join(fmt(v) for v in sorted(x))
    return f"{x:,.2f}"


def structure(c) -> str:
    if c.kind == "abc":
        return "A-B-C correction of a prior " + ("advance" if c.direction > 0 else "decline")
    return ("bullish" if c.direction > 0 else "bearish") + " impulse"


NO_COUNT = ("No clean count at this degree - price is likely in a complex correction "
            "(triangle or W-X-Y); wait for a breakout of the range.")


def text_report(r: dict) -> str:
    info = r["info"]
    lines = [f"{info.get('name', '')} ({info.get('symbol', '')}) {info.get('exchange', '')}".strip(),
             f"Last close {fmt(r['last'])} {info.get('currency', '')} on {r['date']}", ""]
    for deg in r["degrees"]:
        lines.append(f"== {deg['name']}")
        if not deg["entries"]:
            lines.append("   " + NO_COUNT)
            continue
        for k, e in enumerate(deg["entries"]):
            c, p = e["count"], e["proj"]
            tag = "Primary  " if k == 0 else "Alternate"
            lines.append(f"   {tag} [{structure(c)}, score {c.score:.2f}] now in wave {p['wave']}: {p['desc']}")
            path = "  ".join(f"{lab}:{fmt(px)}{'' if ok else '?'} ({d})" for d, px, lab, ok in e["points"])
            lines.append(f"      Path      {path}")
            lines.append(f"      Bias      {p['bias']}")
            if p.get("target"):
                lines.append(f"      Target    {fmt(p['target'])}")
            if p.get("cap"):
                lines.append(f"      Cap       {fmt(p['cap'])} (wave 5 may not exceed wave 3 here)")
            lines.append(f"      Invalid   {fmt(p['invalid'])} (count is wrong if price trades beyond this)")
            nz = f" -> {fmt(p['next_zone'])}" if p.get("next_zone") else ""
            lines.append(f"      Next      {p['next']}{nz}")
            if c.notes:
                lines.append(f"      Notes     {', '.join(c.notes)}")
        lines.append("")
    lines.append("Elliott counts are probabilistic, not advice. '?' = pivot not yet confirmed.")
    return "\n".join(lines)


def html_report(r: dict) -> str:
    info = r["info"]
    payload = []
    for deg in r["degrees"]:
        s = deg["series"]
        entries = []
        for e in deg["entries"]:
            p = e["proj"]
            entries.append({
                "structure": structure(e["count"]), "score": round(e["count"].score, 2),
                "points": [{"d": d, "p": px, "l": lab, "ok": ok} for d, px, lab, ok in e["points"]],
                "wave": p["wave"], "desc": p["desc"], "bias": p["bias"],
                "target": p.get("target"), "invalid": p["invalid"], "cap": p.get("cap"),
                "next": p["next"], "next_zone": p.get("next_zone"), "notes": e["count"].notes,
            })
        payload.append({"name": deg["name"],
                        "bars": [[b.date, b.high, b.low, b.close] for b in s],
                        "entries": entries})
    title = f"{info.get('symbol', '')} Elliott Wave"
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")) as f:
        tpl = f.read()
    return (tpl.replace("{{TITLE}}", html.escape(title))
               .replace("{{NAME}}", html.escape(f"{info.get('name', '')} ({info.get('symbol', '')})"))
               .replace("{{SUB}}", html.escape(f"{info.get('exchange', '')} · last close "
                                               f"{fmt(r['last'])} {info.get('currency', '')} on {r['date']}"))
               .replace("{{NOCOUNT}}", NO_COUNT)
               .replace("{{DATA}}", json.dumps(payload).replace("</", "<\\/")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--csv", help="read daily OHLC from this CSV instead of downloading")
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--range", default="5y", help="history to download (default 5y)")
    a = ap.parse_args(argv)
    rc = 0
    for t in a.tickers:
        try:
            if a.csv:
                bars, info = load_csv(a.csv), {"symbol": t.upper(), "name": t.upper()}
            else:
                bars, info = fetch_yahoo(t, a.range)
            r = analyze(bars, info)
        except Exception as e:  # keep going for the other tickers
            print(f"{t}: {e}", file=sys.stderr)
            rc = 1
            continue
        print(text_report(r))
        if not a.no_html:
            os.makedirs(OUT_DIR, exist_ok=True)
            safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in info["symbol"])
            path = os.path.join(OUT_DIR, f"{safe}.html")
            with open(path, "w") as f:
                f.write(html_report(r))
            print(f"Chart: {os.path.relpath(path, ROOT)}")
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
