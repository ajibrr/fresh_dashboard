# fresh_dashboard

NIFTY directional strategy engine — optimize mode only.

A two-stage candle simulation over per-day `NIFTY_*_DASHBOARD.json` tick
dumps:

1. **Trigger candle** — every enabled entry condition for the direction
   passes (all AND-ed together), configured in
   [configs/optimization.json](configs/optimization.json)
   (`strategy.entry.LONG / .SHORT.conditions`).
2. **Entry candle** — within the next N candles (default 3), the first
   whose close crosses SMA(9): above for LONG, below for SHORT
   (`strategy.entry_candle`).

Entry fills at the entry candle's close; stop-loss is that candle's low
(LONG) / high (SHORT); targets are the configured R:R multiples of that
risk (`analysis.rr_multiples`, e.g. 2.0 = 1:2). A trigger whose window
passes without a qualifying close is recorded as "No Entry".

## Run

```
python main.py --mode optimize --config configs/optimization.json
# or
./run.sh
```

Input day files are read from the folder configured in
[configs/paths.json](configs/paths.json) (`input data` next to the code
by default). Per-day Excel reports, a combined workbook, and run logs
are written to `output_data/optimize_results/`.

## Conditions

The trigger condition library (see `app/strategy/conditions.py`)
includes SMA trend/crossover (ATR-gated), RSI range/extreme/signal
lookbacks, price-vs-SMA9 windows, SMA(44) high/low band, cumulative
CE/PE OI comparison (carried forward at sub-minute timeframes), and
Bollinger band pierces (population std, `bb_period` / `bb_num_std` —
both sweepable lists). Any condition parameter set to a list sweeps the
cartesian product and reports each combination separately.

See [docs/optimize_readme.md](docs/optimize_readme.md) for full details.

## Tests

```
python -m unittest discover -s tests
```
