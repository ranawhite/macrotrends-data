# Australian Property Cycle Tracker

Compares today's housing downturn with the 1989–92 recession cycle, for
**Australia** and **Sydney** (switch with the toggle at the top of the dashboard,
or open `docs/index.html#sydney`). Each cycle is lined up by **months since its
price peak** (national: Dec 1989 and Mar 2026; Sydney: Sep 1989 and Feb 2026). The tracker:

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

Append a row to `data/current_2024_2026.csv` (national) or
`data/sydney_2024_2026.csv` (Sydney, with NSW unemployment and index Feb 2026 = 100) each month (period `YYYY-MM`,
cash rate, mortgage rate, unemployment, CPI y/y, GDP y/y, home value index with
Mar 2026 = 100) and re-run. A month's index is last month's × (1 + Cotality monthly change).

## Files

| Path | What it is |
|---|---|
| `data/cycle_1988_1994.csv` | 1988–94 quarterly cycle (approximate, reconstructed from RBA/ABS/REIA series; illustrative) |
| `data/current_2024_2026.csv` | 2024–26 data (Cotality HVI, ABS Labour Force, ABS CPI, ABS National Accounts, RBA) |
| `data/sydney_1988_1994.csv` | Sydney 1988–94 cycle with NSW unemployment (approximate; illustrative) |
| `data/sydney_2024_2026.csv` | Sydney 2024–26 (Cotality Sydney readings, NSW unemployment from Jobs and Skills Australia; gaps interpolated) |
| `data/sydney_north_suburbs.csv` | North Shore and nearby suburb house medians (`basis` = reported or estimate) used for suburb projections |
| `tracker/model.py` | Alignment, scoring, checklist, scenarios; `REGIONS` holds each market's files, peak and scenario paths |
| `tracker/render.py` | Builds the dashboard and text summary |
| `tracker/template.html` | Dashboard template |

## Suburb projections (Sydney view)

Each suburb follows the Sydney scenario paths scaled by a price-bracket sensitivity
(`beta = 1 + 0.25 × log2(median / $2.6m)`, bounded 0.8–1.45), because dearer suburbs
fell further in 1989–92, 2017–19 and 2022 and rebounded faster. Edit
`data/sydney_north_suburbs.csv` to add suburbs or replace estimates with fresh medians.

## Caveats

Scenario paths and starting probabilities are judgement, not a statistical
forecast. Historical figures are approximate. This is not financial advice.
