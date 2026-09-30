import itertools
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.strategy.definition import StrategyDefinition
from app.strategy.features import build_features
from app.strategy.conditions import evaluate_all, get_feature
from app.reports.reporter import write_sheet
from app.data.loader import resolve_timeframes_seconds, timeframe_label

try:
    import psutil
except ImportError:
    psutil = None


# ============================================================
# PURE SIMULATION FUNCTIONS
#
# Module-level (not methods) so they're picklable by reference for
# multiprocessing — a worker process only needs to re-import this module
# to call them, no StrategyAnalyzer instance has to cross the process
# boundary.
#
# TRADE MODEL (two stages):
#   1. TRIGGER candle — all of the direction's AND conditions pass.
#   2. ENTRY candle — within the next `window_candles` candles, the first
#      one whose CLOSE crosses beyond SMA(sma_period) (above for LONG,
#      below for SHORT). The trade enters at that candle's close.
#   Stop-loss = entry candle's low (LONG) / high (SHORT); targets are the
#   configured R:R multiples of that risk. Stop wins a same-bar tie.
# ============================================================

def _duration_minutes(start_time, end_time):
    if start_time is None or end_time is None:
        return None
    fmt = "%H:%M:%S"
    delta = datetime.strptime(end_time, fmt) - datetime.strptime(start_time, fmt)
    return round(delta.total_seconds() / 60.0, 2)


def _find_entry_candle(rows, i, direction, features, sma_period, window_candles):
    """Index of the ENTRY candle for the trigger at candle i, or None.

    Scans the next `window_candles` candles (i+1 .. i+window, never the
    trigger itself) and returns the first candle whose CLOSE crosses the
    SMA: close > SMA for LONG, close < SMA for SHORT. Data-gap candles
    (tick_count == 0) can't qualify — but they still occupy a window slot,
    so a gap inside the window effectively shortens it.
    """
    sma_key = f"sma_{int(sma_period)}"
    for j in range(i + 1, min(i + int(window_candles) + 1, len(rows))):
        row = rows[j]
        if row["tick_count"] == 0:
            continue
        sma_val = get_feature(features, sma_key, j)
        if sma_val is None:
            continue
        if direction == "LONG" and row["close"] > sma_val:
            return j
        if direction == "SHORT" and row["close"] < sma_val:
            return j
    return None


def _trigger_row(rows, i, direction, outcome, variant,
                 tf_seconds, tf_label, condition_str, variant_label):
    """A trigger that never produced a trade (no qualifying entry candle
    inside the window). One row per trigger — R:R is not applicable."""
    return {
        "timeframe": tf_label,
        "timeframe_seconds": tf_seconds,
        "date": rows[i]["date"],
        "trigger_time": rows[i]["time"],
        "direction": direction,
        "condition": condition_str,
        "variant": variant_label,
        "entry_candle_time": None,
        "entry_price": None,
        "stop_price": None,
        "target_price": None,
        "rr_multiple": None,
        "outcome": outcome,
        "exit_time": None,
        "exit_price": None,
        "pnl_points": None,
        "holding_minutes": None,
        **variant,  # each swept param (e.g. candles, lookback) as its own column
    }


def _trade_row(rows, i, entry_idx, direction, entry_price, stop_price, rr, outcome,
               exit_time, exit_price, variant,
               tf_seconds, tf_label, condition_str, variant_label):
    """A trade that actually entered at the entry candle's close."""
    target_price = None
    pnl = None
    if exit_price is not None:
        pnl = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
        pnl = round(pnl, 2)
    if rr is not None:
        risk = abs(entry_price - stop_price)
        target_price = entry_price + rr * risk if direction == "LONG" else entry_price - rr * risk

    return {
        "timeframe": tf_label,
        "timeframe_seconds": tf_seconds,
        "date": rows[i]["date"],
        "trigger_time": rows[i]["time"],
        "direction": direction,
        "condition": condition_str,
        "variant": variant_label,
        "entry_candle_time": rows[entry_idx]["time"],
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "rr_multiple": rr,
        "outcome": outcome,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "pnl_points": pnl,
        "holding_minutes": _duration_minutes(rows[entry_idx]["time"], exit_time),
        **variant,
    }


def _walk_to_exit(rows, i, entry_idx, direction, entry_price, stop_price, targets, rr_multiples, variant,
                  tf_seconds, tf_label, condition_str, variant_label):
    """Walk forward from the candle AFTER the entry candle: per R:R, either
    the target or the stop is hit first. Stop wins a same-bar tie
    (conservative default).

    The entry candle itself is never an exit bar: entry fills at that
    candle's close, so its low/high were printed before the position
    existed — counting them would stop out every LONG instantly (its low
    IS the stop by definition)."""
    n = len(rows)
    unresolved = {rr: True for rr in rr_multiples}
    results = []

    for j in range(entry_idx + 1, n):
        if rows[j]["tick_count"] == 0:
            continue

        hit_stop = rows[j]["low"] <= stop_price if direction == "LONG" else rows[j]["high"] >= stop_price

        for rr in rr_multiples:
            if not unresolved[rr]:
                continue
            hit_target = (rows[j]["high"] >= targets[rr]) if direction == "LONG" else (rows[j]["low"] <= targets[rr])

            if hit_stop:
                results.append(_trade_row(rows, i, entry_idx, direction, entry_price, stop_price,
                                          rr, "Stop Loss", rows[j]["time"], stop_price, variant,
                                          tf_seconds, tf_label, condition_str, variant_label))
                unresolved[rr] = False
            elif hit_target:
                results.append(_trade_row(rows, i, entry_idx, direction, entry_price, stop_price,
                                          rr, "Target", rows[j]["time"], targets[rr], variant,
                                          tf_seconds, tf_label, condition_str, variant_label))
                unresolved[rr] = False

        if not any(unresolved.values()):
            break

    if any(unresolved.values()):
        last_valid = n - 1
        while rows[last_valid]["tick_count"] == 0 and last_valid > entry_idx:
            last_valid -= 1
        for rr, still_open in unresolved.items():
            if still_open:
                results.append(_trade_row(rows, i, last_valid, direction, entry_price, stop_price,
                                          rr, "End Of Data", rows[last_valid]["time"],
                                          rows[last_valid]["close"], variant, tf_seconds, tf_label,
                                          condition_str, variant_label))

    return results


def _analyze_day(rows, features, direction, conditions, rr_multiples, variant, tf_seconds, tf_label,
                 condition_str, variant_label, entry_candle_cfg):
    n = len(rows)
    results = []
    sma_period = entry_candle_cfg["sma_period"]
    window = entry_candle_cfg["window_candles"]

    for i in range(n - 1):
        if rows[i]["tick_count"] == 0:
            continue  # data gap, not a real candle — can't be a trigger

        if not evaluate_all(conditions, rows, features, i):
            continue

        entry_idx = _find_entry_candle(rows, i, direction, features, sma_period, window)
        if entry_idx is None:
            results.append(_trigger_row(rows, i, direction, "No Entry", variant,
                                        tf_seconds, tf_label, condition_str, variant_label))
            continue

        entry_price = rows[entry_idx]["close"]
        stop_price = rows[entry_idx]["low"] if direction == "LONG" else rows[entry_idx]["high"]

        risk = abs(entry_price - stop_price)
        if risk == 0:
            results.append(_trade_row(rows, entry_idx, entry_idx, direction, entry_price, stop_price,
                                      None, "Zero Risk — Skipped", None, None, variant,
                                      tf_seconds, tf_label, condition_str, variant_label))
            continue

        targets = {}
        for rr in rr_multiples:
            targets[rr] = entry_price + rr * risk if direction == "LONG" else entry_price - rr * risk

        results.extend(_walk_to_exit(rows, i, entry_idx, direction, entry_price, stop_price,
                                     targets, rr_multiples, variant, tf_seconds, tf_label,
                                     condition_str, variant_label))

    return results


# ============================================================
# PARALLEL WORKER PLUMBING
#
# Each worker process receives the full per-timeframe candle data ONCE,
# via the pool's initializer — not re-pickled for every one of the
# thousands of (direction, variant, R:R) tasks. Only the lightweight
# per-task parameters (which date/direction/variant/conditions to run)
# cross the process boundary per task.
# ============================================================

_worker_data_by_timeframe = None
_worker_strategy_config = None
_worker_entry_candle_cfg = None


def _init_worker(data_by_timeframe, strategy_config, entry_candle_cfg):
    global _worker_data_by_timeframe, _worker_strategy_config, _worker_entry_candle_cfg
    _worker_data_by_timeframe = data_by_timeframe
    _worker_strategy_config = strategy_config
    _worker_entry_candle_cfg = entry_candle_cfg


def _run_task(task):
    (tf_seconds, date, direction, conditions, rr_multiples, variant,
     tf_label, condition_str, variant_label) = task
    rows = _worker_data_by_timeframe[tf_seconds][date]
    features = build_features(rows, _worker_strategy_config)
    return _analyze_day(rows, features, direction, conditions, rr_multiples, variant, tf_seconds, tf_label,
                        condition_str, variant_label, _worker_entry_candle_cfg)


class StrategyAnalyzer:
    """
    Two-stage trade simulation over every day file in the input dir:

      1. TRIGGER — a candle where every enabled entry condition for the
         direction passes (all conditions AND-ed together).
      2. ENTRY — within the next N candles, the first candle whose close
         crosses beyond SMA(period) (above for LONG, below for SHORT).
         Entry fills at that candle's close; stop-loss is that candle's
         low (LONG) / high (SHORT); each configured R:R multiple of the
         risk becomes a target. A trigger whose window passes without a
         qualifying close is recorded as "No Entry".

    Every trigger is scored independently — no "one trade at a time"
    portfolio logic. The single-position portfolio engine belongs to a
    future backtest mode.
    """

    def __init__(self, config):
        self.config = config
        self.strategy = StrategyDefinition(config["strategy"])
        self.entry_candle_cfg = self._resolve_entry_candle_cfg(config["strategy"])
        self.rr_multiples = [float(x) for x in config.get("analysis", {}).get("rr_multiples", [2.0, 3.0, 4.0])]
        self.timeframes_seconds = resolve_timeframes_seconds(config.get("data", {}))
        self.timeframe_labels = [timeframe_label(s) for s in self.timeframes_seconds]
        # {"LONG": [{"candles": 3, "lookback": 10}, ...], "SHORT": [...]}
        # Each direction sweeps the cartesian product of every list-valued
        # parameter across its own entry conditions, independently of the
        # other direction (different params, different lengths — no
        # requirement that LONG and SHORT match).
        self.variants = {d: self._direction_variants(d) for d in ("LONG", "SHORT")}

    @staticmethod
    def _resolve_entry_candle_cfg(strategy_config):
        """The entry-candle rule, read from strategy.entry_candle (or
        strategy.entry.entry_candle — same thing, wherever you prefer to
        keep it). Defaults: SMA(9), a 3-candle window."""
        for candidate in (strategy_config.get("entry", {}), strategy_config):
            ec = candidate.get("entry_candle")
            if isinstance(ec, dict):
                return {
                    "sma_period": int(ec.get("sma_period", 9)),
                    "window_candles": int(ec.get("window_candles", 3)),
                }
        return {"sma_period": 9, "window_candles": 3}

    def entry_candle_summary(self):
        return (f"close crosses SMA({self.entry_candle_cfg['sma_period']}) "
                f"within {self.entry_candle_cfg['window_candles']} candles of the trigger")

    def _sweep_axes(self, direction):
        """Every (condition_index, param_name, values) where a condition's
        parameter is a list, e.g. sma_rising.candles=[3,5,7] or
        rsi_extreme_lookback.lookback=[10,15,20]. Param names must be unique
        within a direction's conditions (enforced below) so a flat
        {param_name: value} dict can represent one concrete variant."""
        conditions = self.strategy.entry_conditions(direction)
        axes = []
        seen = set()
        for idx, c in enumerate(conditions):
            for key, value in c.items():
                if key == "type":
                    continue
                if isinstance(value, list):
                    if key in seen:
                        raise ValueError(
                            f"{direction}: sweep parameter '{key}' appears in more than one "
                            f"condition — sweep parameter names must be unique within a direction"
                        )
                    seen.add(key)
                    axes.append((idx, key, value))
        return axes

    def _direction_variants(self, direction):
        axes = self._sweep_axes(direction)
        if not axes:
            return [{}]  # single no-sweep pass
        combos = itertools.product(*(values for _, _, values in axes))
        return [{key: val for (_, key, _), val in zip(axes, combo)} for combo in combos]

    def _concrete_conditions(self, direction, variant):
        conditions = [dict(c) for c in self.strategy.entry_conditions(direction)]
        for c in conditions:
            for key in list(c.keys()):
                if key in variant:
                    c[key] = variant[key]
        return conditions

    @staticmethod
    def _describe_condition(c):
        # "enabled" is a structural on/off flag, not a strategy parameter —
        # every printed condition is one that's already enabled (disabled
        # ones are filtered out before this is ever called), so showing
        # "enabled=True" on every single line would just be noise.
        params = ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("type", "enabled"))
        return f"{c['type']}({params})" if params else c["type"]

    def condition_summary(self, direction, variant):
        """Human-readable description of exactly what's being tested for
        this direction/variant, e.g. 'sma_rising(period=44, candles=8) AND
        rsi_extreme_lookback(period=14, side=above, level=70, lookback=10)'
        — or 'no filter' when entry conditions are empty."""
        conditions = self._concrete_conditions(direction, variant)
        if not conditions:
            return "no filter"
        return " AND ".join(self._describe_condition(c) for c in conditions)

    @staticmethod
    def _variant_label(variant):
        if not variant:
            return "default"
        return ", ".join(f"{k}={v}" for k, v in variant.items())

    def _resolve_num_workers(self):
        """
        cfg["analysis"]["num_workers"] (default 1 = sequential), capped to
        however many CPU cores are actually available on this machine.
        """
        requested = int(self.config.get("analysis", {}).get("num_workers", 1))
        available = os.cpu_count() or 1
        return max(1, min(requested, available))

    @staticmethod
    def _print_progress(done, total, start_time):
        elapsed = time.time() - start_time
        pct = 100 * done / total
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        cpu = f"{psutil.cpu_percent(interval=None):.0f}%" if psutil else "n/a"

        bar_len = 30
        filled = int(bar_len * done / total)
        bar = "#" * filled + "-" * (bar_len - filled)

        print(f"\r[{bar}] {pct:5.1f}% ({done}/{total})  "
              f"elapsed={elapsed:6.1f}s  eta={eta:6.1f}s  cpu={cpu:>4s}",
              end="", file=sys.stderr, flush=True)

    # ============================================================
    # MAIN
    # ============================================================

    def run(self, data_by_timeframe):
        directions = ("LONG", "SHORT")

        tasks = []
        for tf_seconds in self.timeframes_seconds:
            tf_label = timeframe_label(tf_seconds)
            data_by_date = data_by_timeframe[tf_seconds]
            for date in sorted(data_by_date):
                for direction in directions:
                    for variant in self.variants[direction]:
                        conditions = self._concrete_conditions(direction, variant)
                        condition_str = self.condition_summary(direction, variant)
                        variant_label = self._variant_label(variant)
                        tasks.append((tf_seconds, date, direction, conditions, self.rr_multiples, variant,
                                      tf_label, condition_str, variant_label))

        input_dir = self.config.get("data", {}).get("input_dir")
        num_workers = self._resolve_num_workers()
        print(f"Process started for the file : {input_dir}")
        print(f"Timeframes tested : {self.timeframe_labels}")
        print(f"Entry candle rule : {self.entry_candle_summary()}")
        print(f"R:R multiples     : {self.rr_multiples}")
        print(f"Total no of variation : {self._variation_breakdown()} = {len(tasks)}")
        print(f"Workers : {num_workers} (of {os.cpu_count() or 1} CPU cores available)")

        setups = []
        start = time.time()

        if num_workers > 1:
            with ProcessPoolExecutor(max_workers=num_workers, initializer=_init_worker,
                                     initargs=(data_by_timeframe, self.strategy.config,
                                               self.entry_candle_cfg)) as executor:
                futures = [executor.submit(_run_task, t) for t in tasks]
                for i, future in enumerate(as_completed(futures), 1):
                    setups.extend(future.result())
                    self._print_progress(i, len(tasks), start)
        else:
            _init_worker(data_by_timeframe, self.strategy.config, self.entry_candle_cfg)
            for i, t in enumerate(tasks, 1):
                setups.extend(_run_task(t))
                self._print_progress(i, len(tasks), start)

        print(file=sys.stderr)  # newline after the in-place progress bar
        print(f"Completed {len(tasks)} variations in {time.time() - start:.1f}s using {num_workers} worker(s)")

        return setups

    def _variation_breakdown(self):
        """e.g. '3 timeframes x 2 directions x 7 candles x 3 lookback x 3 R:R'
        — assumes LONG/SHORT sweep axes line up 1:1 (true whenever both
        directions mirror each other's condition params, as they do here)."""
        axes = self._sweep_axes("LONG")
        parts = [f"{len(self.timeframes_seconds)} timeframes", "2 directions"]
        for _, key, values in axes:
            parts.append(f"{len(values)} {key}")
        parts.append(f"{len(self.rr_multiples)} R:R")
        return " x ".join(parts)

    @staticmethod
    def _avg_time(time_strs):
        """Average a list of HH:MM:SS clock times (as seconds-since-midnight),
        e.g. to summarize 'triggers in this variation cluster around 10:42am'."""
        values = [v for v in time_strs if v is not None]
        if not values:
            return None
        fmt = "%H:%M:%S"
        total_seconds = sum(
            (datetime.strptime(v, fmt) - datetime.strptime("00:00:00", fmt)).total_seconds()
            for v in values
        )
        avg_seconds = round(total_seconds / len(values))
        hours, remainder = divmod(avg_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # ============================================================
    # SUMMARY
    # ============================================================

    def summarize(self, setups):
        """
        Groups rows once (O(n)) into dicts keyed by the combinations this
        method reports on, instead of re-scanning the full row list per
        combination — with thousands of variations x tens of thousands of
        rows, an O(combinations x n) scan was the actual bottleneck in a
        multi-timeframe run.

        Returns (overall, daily, no_entry, rankings):
          overall  — per timeframe/direction/variant/R:R trade stats
          daily    — same, per date
          no_entry — per timeframe/direction/variant "No Entry" counts
          rankings — variations ranked by hit rate with the configured
                     min-setups guard applied
        """
        resolved = [s for s in setups if s["rr_multiple"] is not None]
        no_entry_rows = [s for s in setups if s["outcome"] == "No Entry"]
        directions = ("LONG", "SHORT")

        by_tf_dir_variant_rr = defaultdict(list)
        for s in resolved:
            by_tf_dir_variant_rr[(s["timeframe_seconds"], s["direction"], s["variant"], s["rr_multiple"])].append(s)

        by_tf_date_dir_variant_rr = defaultdict(list)
        for s in resolved:
            by_tf_date_dir_variant_rr[(s["timeframe_seconds"], s["date"], s["direction"],
                                       s["variant"], s["rr_multiple"])].append(s)

        no_entry_counts = defaultdict(int)
        for s in no_entry_rows:
            no_entry_counts[(s["timeframe_seconds"], s["direction"], s["variant"])] += 1

        overall = []
        for tf_seconds in self.timeframes_seconds:
            tf_label = timeframe_label(tf_seconds)
            for direction in directions:
                for variant in self.variants[direction]:
                    condition = self.condition_summary(direction, variant)
                    variant_label = self._variant_label(variant)
                    n_no_entry = no_entry_counts.get((tf_seconds, direction, variant_label), 0)
                    for rr in self.rr_multiples:
                        subset = by_tf_dir_variant_rr.get((tf_seconds, direction, variant_label, rr), [])
                        total = len(subset)
                        target_hit = sum(1 for s in subset if s["outcome"] == "Target")
                        stop_hit = sum(1 for s in subset if s["outcome"] == "Stop Loss")
                        eod = sum(1 for s in subset if s["outcome"] == "End Of Data")

                        pnls = [s["pnl_points"] for s in subset if s["pnl_points"] is not None]
                        durations = [s["holding_minutes"] for s in subset if s["holding_minutes"] is not None]

                        row = {
                            "timeframe": tf_label,
                            "direction": direction,
                            "condition": condition,
                            "variant": variant_label,
                            "rr_multiple": rr,
                            "total_setups": total,
                            "target_hit": target_hit,
                            "stop_hit": stop_hit,
                            "end_of_data": eod,
                            "no_entry": n_no_entry,
                            "hit_rate_pct": round(100 * target_hit / total, 2) if total else None,
                            "avg_trigger_time": self._avg_time([s["trigger_time"] for s in subset]),
                            "avg_entry_time": self._avg_time([s["entry_candle_time"] for s in subset]),
                            "avg_exit_time": self._avg_time([s["exit_time"] for s in subset]),
                            "avg_holding_minutes": round(sum(durations) / len(durations), 2) if durations else None,
                            "total_pnl_points": round(sum(pnls), 2) if pnls else None,
                            "avg_pnl_points": round(sum(pnls) / len(pnls), 2) if pnls else None,
                            "max_pnl_points": round(max(pnls), 2) if pnls else None,
                            "max_loss_points": round(min(pnls), 2) if pnls else None,
                        }
                        row.update(variant)
                        overall.append(row)

        daily = []
        dates = sorted({s["date"] for s in setups})
        for tf_seconds in self.timeframes_seconds:
            tf_label = timeframe_label(tf_seconds)
            for date in dates:
                for direction in directions:
                    for variant in self.variants[direction]:
                        condition = self.condition_summary(direction, variant)
                        variant_label = self._variant_label(variant)
                        for rr in self.rr_multiples:
                            subset = by_tf_date_dir_variant_rr.get(
                                (tf_seconds, date, direction, variant_label, rr), [])
                            total = len(subset)
                            target_hit = sum(1 for s in subset if s["outcome"] == "Target")
                            pnls = [s["pnl_points"] for s in subset if s["pnl_points"] is not None]
                            row = {
                                "timeframe": tf_label,
                                "date": date,
                                "direction": direction,
                                "condition": condition,
                                "variant": variant_label,
                                "rr_multiple": rr,
                                "total_setups": total,
                                "target_hit": target_hit,
                                "hit_rate_pct": round(100 * target_hit / total, 2) if total else None,
                                "avg_trigger_time": self._avg_time([s["trigger_time"] for s in subset]),
                                "avg_entry_time": self._avg_time([s["entry_candle_time"] for s in subset]),
                                "avg_pnl_points": round(sum(pnls) / len(pnls), 2) if pnls else None,
                            }
                            row.update(variant)
                            daily.append(row)

        no_entry = []
        for tf_seconds in self.timeframes_seconds:
            tf_label = timeframe_label(tf_seconds)
            for direction in directions:
                for variant in self.variants[direction]:
                    condition = self.condition_summary(direction, variant)
                    variant_label = self._variant_label(variant)
                    count = no_entry_counts.get((tf_seconds, direction, variant_label), 0)
                    row = {
                        "timeframe": tf_label,
                        "direction": direction,
                        "condition": condition,
                        "variant": variant_label,
                        "no_entry_setups": count,
                    }
                    row.update(variant)
                    no_entry.append(row)

        rankings = self.rank_variations(overall)

        return overall, daily, no_entry, rankings

    def rank_variations(self, overall, top_n=5):
        """
        Ranks direction/condition/R:R variations (across all timeframes) by
        hit rate, then by total P&L, ignoring anything below
        min_setups_for_ranking (a 2-setup "100% hit rate" is noise, not
        edge). Written to the RANKINGS sheet.
        """
        min_setups = int(self.config.get("analysis", {}).get("min_setups_for_ranking", 20))
        ranked = [
            v for v in overall
            if v["hit_rate_pct"] is not None and v["total_setups"] >= min_setups
        ]
        ranked.sort(key=lambda v: (v["hit_rate_pct"], v["total_pnl_points"] or 0), reverse=True)
        return ranked[:top_n]

    def max_setups_per_timeframe(self, overall):
        """
        The largest total_setups any single variation reached in each
        timeframe — the practical ceiling that min_setups_for_ranking gets
        compared against. If this is below min_setups_for_ranking for a
        timeframe, EVERY variation in it will fail the ranking guard,
        because none of them could ever reach the threshold on this data.
        """
        ceilings = {}
        for tf_label in self.timeframe_labels:
            setups_counts = [v["total_setups"] for v in overall if v["timeframe"] == tf_label]
            ceilings[tf_label] = max(setups_counts, default=0)
        return ceilings

    def target_sweep_trades(self, setups):
        """
        Physical trades (same timeframe/date/trigger_time/direction) whose
        target was hit at EVERY configured R:R multiple — price ran far
        enough to satisfy even the largest target, so every smaller one was
        hit too. Entry/stop/the eventual price path for a given trigger is
        the same regardless of which condition/variant flagged it, so this
        groups across variants (not per-variant) and lists every distinct
        variant that happened to flag this same trade.
        """
        by_trade = defaultdict(dict)       # key -> {rr: row}
        variants_by_trade = defaultdict(set)

        for s in setups:
            if s["rr_multiple"] is None:
                continue
            key = (s["timeframe_seconds"], s["date"], s["trigger_time"], s["direction"])
            by_trade[key][s["rr_multiple"]] = s
            variants_by_trade[key].add(s["variant"])

        results = []
        for key, rr_map in by_trade.items():
            if not all(rr in rr_map and rr_map[rr]["outcome"] == "Target" for rr in self.rr_multiples):
                continue
            tf_seconds, date, trigger_time, direction = key
            any_row = next(iter(rr_map.values()))
            row = {
                "timeframe": timeframe_label(tf_seconds),
                "date": date,
                "direction": direction,
                "trigger_time": trigger_time,
                "entry_candle_time": any_row["entry_candle_time"],
                "entry_price": any_row["entry_price"],
                "stop_price": any_row["stop_price"],
                "num_variants_matched": len(variants_by_trade[key]),
                "variants_matched": " | ".join(sorted(variants_by_trade[key])),
            }
            for rr in self.rr_multiples:
                row[f"exit_time_1_{rr:.0f}"] = rr_map[rr]["exit_time"]
                row[f"pnl_1_{rr:.0f}"] = rr_map[rr]["pnl_points"]
            results.append(row)

        results.sort(key=lambda r: (r["timeframe"], r["date"], r["trigger_time"]))
        return results

    @staticmethod
    def _dedup_trades(setups):
        """The same physical trade (same timeframe/date/trigger_time/
        direction) can appear under many condition variants that all
        happened to include it, once per R:R multiple — collapse to one row
        per unique trade (preferring a resolved Target hit over lower R:R
        outcomes of the same path). Timeframe is part of the key because the
        same wall-clock minute is a genuinely different candle/trade at a
        different timeframe."""
        resolved = [s for s in setups if s["pnl_points"] is not None]
        by_trade = defaultdict(dict)
        for s in resolved:
            key = (s["timeframe_seconds"], s["date"], s["trigger_time"], s["direction"])
            existing = by_trade[key].get(s["rr_multiple"])
            # Keep the first row per R:R, but let an actual Target hit
            # replace a same-R:R End Of Data row (same price path, better
            # label — the exit price differs only by which target is shown).
            if existing is None or (s["outcome"] == "Target" and existing["outcome"] != "Target"):
                by_trade[key][s["rr_multiple"]] = s
        unique = {}
        for key, rr_map in by_trade.items():
            best_rr = max(rr_map)
            unique[key] = rr_map[best_rr]
        return list(unique.values())

    def top_trades(self, setups, top_n=5):
        """The single best individual trades by P&L, no min-setups guard —
        this is about the actual best trades that happened, not a
        statistically-reliable ranking of a condition/variation."""
        ranked = sorted(self._dedup_trades(setups), key=lambda s: s["pnl_points"], reverse=True)
        return ranked[:top_n]

    def all_trades(self, setups):
        """Every unique trade that occurred, in chronological order — for a
        full day-by-day trade log rather than a ranked top-N. One row per
        physical trade (deduped across variants and R:R multiples; the
        highest-R:R outcome of each path is shown)."""
        return sorted(self._dedup_trades(setups), key=lambda s: (s["timeframe_seconds"], s["date"], s["trigger_time"]))

    # ============================================================
    # EXCEL
    # ============================================================

    def write_excel(self, setups, output_config):
        from openpyxl import Workbook

        directory = Path(output_config.get("directory", "output_data/optimize_results"))
        directory.mkdir(parents=True, exist_ok=True)

        dates = sorted({s["date"] for s in setups})
        if dates:
            date_tag = dates[0].replace("-", "") if len(dates) == 1 \
                else f"{dates[0].replace('-', '')}_to_{dates[-1].replace('-', '')}"
        else:
            date_tag = "no_data"

        tf_tag = "_".join(self.timeframe_labels)

        filename = output_config.get("filename", "optimize_results.xlsx")
        stem, ext = filename.rsplit(".", 1)
        filename = f"{stem}_{date_tag}_{tf_tag}.{ext}"
        path = directory / filename

        overall, daily, no_entry, rankings = self.summarize(setups)
        trades = self.all_trades(setups)
        n_no_entry = sum(1 for s in setups if s["outcome"] == "No Entry")

        wb = Workbook()
        ws = wb.active
        ws.title = "SUMMARY"
        ws.append(["Strategy", self.strategy.name])
        ws.append(["Entry Candle Rule", self.entry_candle_summary()])
        ws.append(["Stop-Loss Rule", "low of entry candle (LONG) / high of entry candle (SHORT)"])
        ws.append(["Timeframes Tested", ", ".join(self.timeframe_labels)])
        ws.append(["Dates Analyzed", ", ".join(dates) if dates else "None"])
        ws.append(["Total Trading Days", len(dates)])
        ws.append(["Total Triggers", len(trades) + n_no_entry])
        ws.append(["Triggers With Entry", len(trades)])
        ws.append(["Triggers Without Entry (No Entry)", n_no_entry])
        ws.append(["R:R Multiples Tested", ", ".join(str(r) for r in self.rr_multiples)])
        ws.append(["LONG Conditions", self.condition_summary("LONG", self.variants["LONG"][0] if self.variants["LONG"] else {})])
        ws.append(["SHORT Conditions", self.condition_summary("SHORT", self.variants["SHORT"][0] if self.variants["SHORT"] else {})])
        ws.append(["Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

        write_sheet(wb, "RANKINGS", rankings)
        write_sheet(wb, "OVERALL_SUMMARY", overall)
        write_sheet(wb, "DAILY_BREAKDOWN", daily)
        write_sheet(wb, "NO_ENTRY_COUNTS", no_entry)
        write_sheet(wb, "TOP_TRADES", self.top_trades(setups, top_n=5))
        write_sheet(wb, "ALL_TARGETS_HIT", self.target_sweep_trades(setups))
        write_sheet(wb, "ALL_TRADES", trades)
        write_sheet(wb, "ALL_TRIGGER_ROWS", setups)

        wb.save(path)
        return path
