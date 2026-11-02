# Australian Property Cycle Tracker

Compares today's Australian housing downturn with the 1989–92 recession cycle.
Both cycles are lined up by **months since the national price peak**
(Dec 1989, Mar 2026). The tracker:

- scores the current macro backdrop (RBA direction, real cash rate, unemployment
  momentum, home value momentum, inflation, GDP) into a composite signal from −100 to +100,
- runs a five-point "bottom checklist" built from the 1991, 2019 and 2023 troughs,
- projects three 12-month scenarios for the national home value index, with
  probabilities that tilt as the composite signal changes,
- writes an interactive dashboard to `docs/index.html`.

## Run

```bash
python3 tracker/render.py      # prints a summary and rebuilds docs/index.html
```

No third-party packages are needed. Open `docs/index.html` in a browser.

## Update with new data

Append a row to `data/current_2024_2026.csv` each month (period `YYYY-MM`,
cash rate, mortgage rate, unemployment, CPI y/y, GDP y/y, home value index with
Mar 2026 = 100) and re-run. A month's index is last month's × (1 + Cotality monthly change).

## Files

| Path | What it is |
|---|---|
| `data/cycle_1988_1994.csv` | 1988–94 quarterly cycle (approximate, reconstructed from RBA/ABS/REIA series; illustrative) |
| `data/current_2024_2026.csv` | 2024–26 data (Cotality HVI, ABS Labour Force, ABS CPI, ABS National Accounts, RBA) |
| `tracker/model.py` | Alignment, scoring, checklist, scenarios |
| `tracker/render.py` | Builds the dashboard and text summary |
| `tracker/template.html` | Dashboard template |

## Caveats

Scenario paths and starting probabilities are judgement, not a statistical
forecast. Historical figures are approximate. This is not financial advice.
