# Optimize Mode — the project's only mode

## The trade model

Two stages, evaluated candle by candle on each timeframe:

1. **Trigger candle** — every enabled entry condition for the direction
   passes (all conditions AND-ed together). LONG triggers read
   `strategy.entry.LONG.conditions`; SHORT triggers read
   `strategy.entry.SHORT.conditions`, from `configs/optimization.json`.
2. **Entry candle** — within the next `strategy.entry_candle.window_candles`
   candles (default 3, never counting the trigger candle itself), the first
   candle whose **close** crosses beyond SMA(`strategy.entry_candle.sma_period`,
   default 9): close **above** SMA for LONG, close **below** SMA for SHORT.

If no candle qualifies inside the window, the trigger is recorded with
outcome **"No Entry"** (one row, no trade).

For a trigger that does produce an entry candle:

| Field         | LONG                          | SHORT                         |
|---------------|-------------------------------|-------------------------------|
| Entry price   | entry candle's **close**      | entry candle's **close**      |
| Stop-loss     | entry candle's **low**        | entry candle's **high**       |
| Targets       | entry + RR × risk, RR ∈ `analysis.rr_multiples` (default 1:2, 1:3, 1:4) | entry − RR × risk |

- The exit walk starts at the candle **after** the entry candle (the entry
  candle's own low/high printed before the close-entry existed, so it can't
  be an exit bar).
- If a bar touches both stop and target, **stop wins** (conservative tie-break).
- A trade still open at end-of-data closes at the last valid candle's close
  (outcome "End Of Data").
- A degenerate entry candle (close == stop, risk 0) is recorded as
  "Zero Risk — Skipped" and not traded.

Every trigger is scored independently — overlapping trades are allowed.
`ALL_TRADES` dedupes to one row per physical trade (highest-R:R outcome of
each path); `ALL_TRIGGER_ROWS` is the raw per-R:R detail.

## Usage

```
python main.py --mode optimize --config configs/optimization.json
./run.sh                       # same thing (defaults below)
```

`main.py` accepts only `--mode optimize` and defaults to
`configs/optimization.json`.

## What a run does

`app/optimizer/optimizer.py` — `run_optimize(config)`:

1. Globs `data.input_dir` for files matching `data.file_pattern`
   (default `NIFTY_*_DASHBOARD.json`).
2. For each file, in order: builds a per-file config copy with
   `file_pattern` narrowed to that exact filename, loads that single day
   at every configured timeframe, runs the simulation, writes that day's
   Excel report (`optimize_results_<date>_<tfs>.xlsx`), prints a short
   summary, then moves to the next file.
3. Writes one combined workbook (`optimize_combined_<timestamp>.xlsx`)
   covering every trade from every file processed this run, with a
   SUMMARY sheet and an ALL_TRADES_COMBINED sheet.

## Excel sheets (per day)

- `SUMMARY` — strategy name, entry-candle rule, stop rule, trigger/entry counts.
- `RANKINGS` — variations ranked by hit rate (min `analysis.min_setups_for_ranking` setups).
- `OVERALL_SUMMARY` — per timeframe/direction/variant/R:R trade stats.
- `DAILY_BREAKDOWN` — same, per date.
- `NO_ENTRY_COUNTS` — triggers per variant that never produced an entry candle.
- `TOP_TRADES`, `ALL_TARGETS_HIT`, `ALL_TRADES`, `ALL_TRIGGER_ROWS`.

## Parameters worth knowing (`configs/optimization.json`)

- `strategy.entry_candle.sma_period` / `window_candles` — the entry rule.
- `analysis.rr_multiples` — targets, as fractions of risk (2.0 = 1:2).
- `analysis.num_workers` — parallel workers for the simulation.
- `strategy.entry.LONG/SHORT.conditions` — the trigger conditions; any
  parameter set to a list sweeps the cartesian product of those values,
  and each combination is reported separately (with `"enabled": true/false`
  per condition).

## OI and Bollinger conditions

- `cumulative_oi_compare` (`side`: `pe_greater` for LONG, `ce_greater`
  for SHORT) compares the cumulative CE/PE open interest carried on each
  candle row. The flow series is 1-minute resolution; at sub-minute
  timeframes the loader carries the last known values forward, so every
  candle has OI state (updated once per minute).
- `low_below_bollinger_lower` (LONG) / `high_above_bollinger_upper`
  (SHORT): the candle's low/high must pierce the Bollinger band
  (`bb_period`, `bb_num_std` — population std). Both params accept sweep
  lists, e.g. `"bb_period": [20, 22, 26]`.
