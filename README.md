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
| `data/rba_decisions.csv` | Latest RBA decision(s), applied if newer than the latest data month |
| `tracker/model.py` | Alignment, scoring, checklist, scenarios; `REGIONS` holds each market's files, peak and scenario paths |
| `tracker/render.py` | Builds the dashboard and text summary |
| `tracker/template.html` | Dashboard template |

## RBA decisions between data months

Home values arrive monthly, but the RBA can move in between. Add the decision to
`data/rba_decisions.csv` (date, new cash rate); if it is newer than the latest data
month, the tracker folds it into the latest row's cash and mortgage rates.

## Suburb projections (Sydney view)

Each suburb follows the Sydney scenario paths scaled by a price-bracket sensitivity
(`beta = 1 + 0.25 × log2(median / $2.6m)`, bounded 0.8–1.45), because dearer suburbs
fell further in 1989–92, 2017–19 and 2022 and rebounded faster. Edit
`data/sydney_north_suburbs.csv` to add suburbs or replace estimates with fresh medians.

## Caveats

Scenario paths and starting probabilities are judgement, not a statistical
forecast. Historical figures are approximate. This is not financial advice.

# Elliott Wave Analyzer (any stock ticker)

`elliott/` counts Elliott Waves for any symbol Yahoo Finance knows, at two degrees:
**Primary** (weekly bars, ~5 years) and **Intermediate** (daily bars, ~1 year).

```bash
python3 elliott/analyze.py AAPL                 # US
python3 elliott/analyze.py RELIANCE.NS TCS.NS   # NSE India (.BO for BSE)
python3 elliott/analyze.py ^NSEI ^NSEBANK ^GSPC # indices
python3 elliott/analyze.py BHP.AX               # ASX
python3 elliott/analyze.py XYZ --csv prices.csv # offline: Date,Open,High,Low,Close
```

For each degree it prints a primary and an alternate count: the wave in progress,
the bias, a Fibonacci target zone, the **invalidation level** (the count is wrong
if price trades beyond it) and the next expected wave. An interactive chart is
written to `docs/elliott/<TICKER>.html` (git-ignored).

How it works (`elliott/elliott.py`, standard library only):

1. ZigZag swing pivots on highs/lows, with thresholds scaled to the stock's own volatility.
2. Every reading of the latest pivots as an impulse (0-1-2-3-4-5, then A-B-C) or as
   a standalone A-B-C correction, in either direction.
3. Hard rules reject counts: wave 2 never retraces all of wave 1, wave 3 is never the
   shortest, wave 4 never enters wave 1 territory, B stays within 138.2% of A.
4. Survivors are ranked on Fibonacci guidelines (2 ≈ 50–61.8% of 1, 3 ≈ 1.618 × 1,
   4 ≈ 38.2% of 3, 5 ≈ 1 × 1, 2/4 alternation, B ≈ 50–78.6% of A, C ≈ 1–1.618 × A),
   how much of the chart the count explains, and whether wave 0 is a real turning point.

Not modelled: diagonals, triangles and W-X-Y combinations (reported as "no clean
count"). Wave counts are probabilistic; this is not financial advice.
`python3 elliott/test_elliott.py` runs the tests.
