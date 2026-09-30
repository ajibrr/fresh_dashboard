# NIFTY Directional Strategy Engine

Two-stage candle simulation over per-day `NIFTY_*_DASHBOARD.json` tick dumps, built for **mode-by-mode optimization**: find the best parameter set for one condition group first, then feed those findings into the next mode, and finally combine modes into stage-2 variations.

## Trade model (same for every mode)

Every mode uses the same two-stage evaluation, candle by candle on each timeframe:

1. **Trigger candle** — every enabled entry condition for the direction passes (all AND-ed together). LONG triggers read `strategy.entry.LONG.conditions`; SHORT triggers read `strategy.entry.SHORT.conditions`, from the active config.
2. **Entry candle** — within the next `strategy.entry_candle.window_candles` candles (default 3, never counting the trigger candle itself), the first candle whose **close** crosses beyond SMA(`strategy.entry_candle.sma_period`, default 9): close **above** SMA for LONG, close **below** SMA for SHORT.

If no candle qualifies inside the window, the trigger is recorded with outcome **"No Entry"** (one row, no trade).

For a trigger that does produce an entry candle:

| Field         | LONG                          | SHORT                         |
|---------------|-------------------------------|-------------------------------|
| Entry price   | entry candle's **close**      | entry candle's **close**      |
| Stop-loss     | entry candle's **low**        | entry candle's **high**       |
| Targets       | entry + RR × risk, RR ∈ `analysis.rr_multiples` (default 1:2, 1:3, 1:4) | entry − RR × risk |

- The exit walk starts at the candle **after** the entry candle.
- If a bar touches both stop and target, **stop wins** (conservative tie-break).
- A trade still open at end-of-data closes at the last valid candle's close (outcome "End Of Data").
- A degenerate entry candle (close == stop, risk 0) is recorded as "Zero Risk — Skipped" and not traded.

Every trigger is scored independently — overlapping trades are allowed.
`ALL_TRADES` dedupes to one row per physical trade (highest-R:R outcome of each path); `ALL_TRIGGER_ROWS` is the raw per-R:R detail.

## How the optimization workflow is meant to run

The project is designed for **sequential mode optimization**, not one giant config sweep:

1. Pick one condition group for the first mode (for example `sma_rising_atr`).
2. Sweep that mode's parameters one by one / cartesian-product style, with everything else disabled.
3. Read the Excel `RANKINGS` sheet and pick the parameter set(s) with the best hit rate (subject to `analysis.min_setups_for_ranking`).
4. Freeze those findings into the next mode's config so the new mode is evaluated **on top of** the chosen base.
5. Repeat for each new mode.
6. Once individual modes are nailed down, build stage-2 configs that combine mode findings (mode 1 + mode 2, mode 2 + mode 4, and so on).
7. Compare stage-2 combinations the same way, then keep combining until you have the quality signals you want.

In other words: variant-upon-variant, one mode at a time, with each round's best results driving the next round.

## Condition library

Trigger conditions live in `app/strategy/conditions.py`. Any condition parameter that is a list is swept as part of the cartesian product, and each combination is reported separately.

Current condition types:

- **SMA trend / crossover (ATR-gated)** — slope or cross of an SMA, with an optional ATR filter so the move has enough range.
- **RSI range / extreme / signal lookbacks** — RSI staying in a band, hitting an extreme, or producing a signal over a lookback window.
- **Price vs SMA9 windows** — price relationship to SMA(9) over a configurable window.
- **SMA(44) high/low band** — price relative to an SMA(44)-based band.
- **Cumulative CE/PE OI compare** — `side: pe_greater` for LONG, `ce_greater` for SHORT. The OI flow series is 1-minute resolution; at sub-minute timeframes the loader carries the last known values forward so every candle has OI state.
- **Bollinger band pierces** — `low_below_bollinger_lower` (LONG) / `high_above_bollinger_upper` (SHORT), using population std. Both `bb_period` and `bb_num_std` accept sweep lists.

## Config structure

- `configs/paths.json` — input folder, file pattern, output folder, and other paths.
- `configs/optimization.json` — the active strategy config: entry-candle rule, stop rule, R:R multiples, worker count, and the enabled condition list for LONG and SHORT.
- `configs/modes/` — optional per-mode config fragments. Each mode can keep its own condition set and parameter sweep range so you can switch between modes without editing one monolithic file.

## Run

```
python main.py --mode optimize --config configs/optimization.json
# or
./run.sh
```

`main.py` accepts only `--mode optimize` and defaults to `configs/optimization.json`.

Input day files are read from the folder configured in `configs/paths.json` (by default a folder named `input data` next to the code). Per-day Excel reports, a combined workbook, and run logs are written to `output_data/optimize_results/`.

## What a run does

`app/optimizer/optimizer.py` — `run_optimize(config)`:

1. Globs `data.input_dir` for files matching `data.file_pattern` (default `NIFTY_*_DASHBOARD.json`).
2. For each file, in order: builds a per-file config copy with `file_pattern` narrowed to that exact filename, loads that single day at every configured timeframe, runs the simulation, writes that day's Excel report (`optimize_results_<date>_<tfs>.xlsx`), prints a short summary, then moves to the next file.
3. Writes one combined workbook (`optimize_combined_<timestamp>.xlsx`) covering every trade from every file processed this run, with a `SUMMARY` sheet and an `ALL_TRADES_COMBINED` sheet.

## Excel sheets (per day)

- `SUMMARY` — strategy name, entry-candle rule, stop rule, trigger/entry counts.
- `RANKINGS` — variations ranked by hit rate (min `analysis.min_setups_for_ranking` setups). This is the sheet you use to pick the next mode's base findings.
- `OVERALL_SUMMARY` — per timeframe/direction/variant/R:R trade stats.
- `DAILY_BREAKDOWN` — same, per date.
- `NO_ENTRY_COUNTS` — triggers per variant that never produced an entry candle.
- `TOP_TRADES`, `ALL_TARGETS_HIT`, `ALL_TRADES`, `ALL_TRIGGER_ROWS`.

## Parameters worth knowing (`configs/optimization.json`)

- `strategy.entry_candle.sma_period` / `window_candles` — the entry rule.
- `analysis.rr_multiples` — targets, as fractions of risk (2.0 = 1:2).
- `analysis.num_workers` — parallel workers for the simulation.
- `analysis.min_setups_for_ranking` — minimum setups before a variant is eligible for the `RANKINGS` sheet.
- `strategy.entry.LONG/SHORT.conditions` — the trigger conditions; any parameter set to a list sweeps the cartesian product of those values, and each combination is reported separately (with `"enabled": true/false` per condition).

## Project structure

```
.
├── configs
│   ├── paths.json                  # input/output paths and file pattern
│   ├── optimization.json          # active strategy + condition config
│   └── modes/                     # optional per-mode config fragments
│       ├── sma_rising_atr.json    # example first mode config
│       └── ...
├── app
│   ├── __init__.py
│   ├── main.py                     # CLI entry point (optimize mode only)
│   ├── data_loader.py             # NIFTY_*_DASHBOARD.json loader, per-timeframe OHLC + OI carry-forward
│   ├── strategy
│   │   ├── __init__.py
│   │   ├── conditions.py          # condition library: SMA/ATR, RSI, price-vs-SMA, SMA44 band, OI, Bollinger
│   │   └── trade_model.py        # two-stage trigger/entry/SL/RR simulation
│   └── optimizer
│       ├── __init__.py
│       └── optimizer.py          # cartesian sweep, per-day Excel, combined workbook, RANKINGS
├── output_data
│   └── optimize_results/          # per-day Excel reports + combined workbook + logs
├── tests
│   └── ...                        # condition, trade model, and optimizer output-shape tests
├── docs
│   └── optimize_readme.md         # detailed optimize-mode reference
├── requirements.txt
└── run.sh
```

## Condition references

- `cumulative_oi_compare` (`side`: `pe_greater` for LONG, `ce_greater` for SHORT) compares the cumulative CE/PE open interest carried on each candle row. The flow series is 1-minute resolution; at sub-minute timeframes the loader carries the last known values forward, so every candle has OI state (updated once per minute).
- `low_below_bollinger_lower` (LONG) / `high_above_bollinger_upper` (SHORT): the candle's low/high must pierce the Bollinger band (`bb_period`, `bb_num_std` — population std). Both params accept sweep lists, e.g. `"bb_period": [20, 22, 26]`.

## Tests

```
python -m unittest discover -s tests
```

## Planned modes and how they chain

The first mode you want to build is **sma_rising_atr**. The idea for the overall mode pipeline is:

- **Mode A — `sma_rising_atr`**
  - One condition group first. Sweep that group's parameters, find which parameter set gives the highest hit rate, and freeze that finding.
  - This mode is the starting point for everything that follows.

- **Mode B, Mode C, ...**
  - Each new mode is discovered the same way: enable that mode's condition group, disable the rest, sweep its parameters, read the `RANKINGS` sheet, pick the best parameter set.
  - Each mode's best finding is then available to be used as a base for the next mode.

- **Stage 2 — combining modes**
  - Once individual modes are nailed down, combine them: mode 1 + mode 2, mode 2 + mode 4, and so on.
  - Stage-2 configs are ranked the same way as single modes, so you can compare a combined variation directly against its parts.
  - Keep combining stages — mode 1 + stage-2 mode 1, mode 1 + stage-2 mode 2, and so on — until the signal quality is where you want it.

The point of this structure is to avoid one massive config with dozens of active conditions. Each mode's best parameter set is discovered first, then reused as the foundation for the next mode and for stage-2 combinations. The `RANKINGS` sheet is the handoff point between rounds.

## Recommended workflow (mode-by-mode)

1. Start one mode at a time. Disable every condition except the one group you are studying.
2. Sweep that group's parameters. Let the cartesian product run, then open the day/combined `RANKINGS` sheet.
3. Pick the parameter set with the best hit rate that also clears `analysis.min_setups_for_ranking`.
4. Write that finding into the next mode's config so the new mode is layered on top of the chosen base.
5. Repeat for each new mode.
6. Once individual modes are stable, combine them: mode 1 + mode 2, mode 2 + mode 4, and so on — same ranking process, same ranking sheet.
7. Keep combining stages until the signal quality is where you want it.

The idea is to avoid one massive config with dozens of active conditions. Instead, each mode's best parameter set is discovered first, then reused as the foundation for the next mode and for stage-2 combinations.
