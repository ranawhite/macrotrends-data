"""Render the tracker: writes docs/index.html (Australia + Sydney) and prints text summaries.

Usage:  python3 tracker/render.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model  # noqa: E402

ROOT = model.ROOT
TEMPLATE = Path(__file__).resolve().parent / "template.html"
OUT = ROOT / "docs" / "index.html"


def summary(d: dict) -> str:
    a = d["analogue"]
    lines = [
        f"{d['name']} property cycle tracker  (data to {d['as_of']})",
        f"Regime: {d['regime']['label']}   composite signal {d['score_now']['composite']:+d} "
        f"(1989-92 at same stage: {d['score_then']['composite']:+d})",
        f"Months since price peak: {a['months_from_peak']}",
        *( [f"Includes RBA decision {d['rba_update']['date']}: cash rate {d['rba_update']['cash_rate']:.2f}% "
            f"({d['rba_update']['change']:+.2f})"] if d.get("rba_update") else [] ),
        "",
        "Indicators now:",
    ]
    for i in d["score_now"]["indicators"]:
        lines.append(f"  {i['label']:<52} {i['value']:>12}  score {i['score']:+.2f}")
    lines += ["", "Turning-point checklist:"]
    for c in d["checklist"]:
        lines.append(f"  [{'x' if c['met'] else ' '}] {c['rule']}  ({c['detail']})")
    lines += ["", "12-month scenarios:"]
    for s in d["scenarios"]:
        lines.append(
            f"  {s['label']:<22} p={s['probability']:.0%}  trough {s['trough_period']} "
            f"({s['trough_from_peak']:+.1f}% vs peak)  12m change {s['twelve_month_change']:+.1f}%"
        )
    lines += [
        "",
        f"1989-92: nominal trough {a['hist_trough_nominal']['from_peak']:+.1f}% at "
        f"{a['hist_trough_nominal']['period']}, real trough {a['hist_trough_real']['from_peak']:+.1f}% at "
        f"{a['hist_trough_real']['period']}, nominal peak regained {a['hist_recovered']}.",
    ]
    return "\n".join(lines)


def main() -> None:
    data = model.build_all()
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print("\n\n".join(summary(data["regions"][k]) for k in data["order"]))
    print(f"\nWrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
