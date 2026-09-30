"""
Optimize mode — the project's only mode.

Loads every day file matching data.file_pattern in data.input_dir, one at
a time, and runs the two-stage trade simulation on each:

  1. TRIGGER candle — all of the direction's AND conditions pass
     (configs/optimization.json, strategy.entry.LONG / .SHORT).
  2. ENTRY candle — within the next `entry_candle.window_candles` candles,
     the first whose CLOSE crosses beyond SMA(entry_candle.sma_period)
     (above for LONG, below for SHORT). The trade enters at that candle's
     close; stop-loss is the entry candle's low (LONG) / high (SHORT);
     each configured R:R multiple of that risk is a target. With
     entry_candle.enabled=false the trigger candle itself is the entry
     candle. A trigger with no qualifying close in its window is recorded
     as "No Entry".

The console report mirrors sample.log: run header, sweep scope, per-day
top-variant tables by hit rate, and a combined summary with best /
near-best bands and a data-driven conclusion. Per-day and combined Excel
workbooks are still written.
"""

import copy
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.analyzer import StrategyAnalyzer
from app.data.loader import load_dashboard_data_multi
from app.reports.reporter import write_sheet

_NO_ENTRY = "No Entry"
_ZERO_RISK = "Zero Risk - Skipped"

# Every row field that is NOT a swept condition parameter. Whatever is
# left after removing these is a sweep param (candles, atr_multiplier,
# bb_period, ...) and gets its own column in the variant tables.
_KNOWN_ROW_FIELDS = {
    "timeframe", "timeframe_seconds", "date", "trigger_time", "direction",
    "variant", "entry_candle_time", "entry_price", "stop_price",
    "target_price", "rr_multiple", "outcome", "exit_time", "exit_price",
    "pnl_points", "holding_minutes", "condition",
}


def _list_input_files(data_cfg):
    input_dir = Path(data_cfg["input_dir"])
    if not input_dir.exists():
        raise FileNotFoundError(input_dir)
    pattern = data_cfg.get("file_pattern", "NIFTY_*_DASHBOARD.json")
    files = sorted(input_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no files matching {pattern!r} found in {input_dir}")
    return files


# ============================================================
# VARIANT AGGREGATION (shared by day and combined reports)
# ============================================================

def _aggregate_variant_stats(setups, rr_multiples):
    """Collapse raw per-R:R setup rows into one stats dict per
    (direction, variant): trade counts, hit rate at the primary R:R,
    per-R:R target rates, stop rate, avg P&L, and per-day breakdowns.
    Each entered trade contributes exactly one row per R:R, so the
    primary-R:R row count IS the trade count."""
    primary = rr_multiples[0] if rr_multiples else None
    acc = {}

    for s in setups:
        key = (s["direction"], s["variant"])
        st = acc.get(key)
        if st is None:
            st = acc[key] = {
                "direction": s["direction"],
                "variant": s["variant"],
                "params": {k: s[k] for k in s if k not in _KNOWN_ROW_FIELDS},
                "no_entry": 0,
                "zero_risk": 0,
                "eod_keys": set(),
                "per_rr": {rr: {"target": 0, "stop": 0, "total": 0, "pnl": 0.0}
                           for rr in rr_multiples},
                "day_primary": defaultdict(lambda: [0, 0]),  # date -> [targets, total]
            }
        outcome = s["outcome"]
        rr = s["rr_multiple"]
        if outcome == _NO_ENTRY:
            st["no_entry"] += 1
        elif outcome == _ZERO_RISK:
            st["zero_risk"] += 1
        elif rr is not None:
            bucket = st["per_rr"].get(rr)
            if bucket is not None:
                bucket["total"] += 1
                if outcome == "Target":
                    bucket["target"] += 1
                elif outcome == "Stop Loss":
                    bucket["stop"] += 1
                if s["pnl_points"] is not None:
                    bucket["pnl"] += s["pnl_points"]
            if outcome == "End Of Data":
                st["eod_keys"].add((s["timeframe_seconds"], s["date"], s["trigger_time"]))
            if rr == primary:
                day = st["day_primary"][s["date"]]
                day[1] += 1
                if outcome == "Target":
                    day[0] += 1

    stats = []
    for st in acc.values():
        pr = st["per_rr"].get(primary, {"target": 0, "stop": 0, "total": 0, "pnl": 0.0})
        trades = pr["total"]
        st["trades"] = trades
        st["entries"] = trades + st["zero_risk"]
        st["setups_total"] = trades + st["no_entry"] + st["zero_risk"]
        st["hit_rate_pct"] = round(100 * pr["target"] / pr["total"], 2) if pr["total"] else None
        st["stop_rate"] = round(pr["stop"] / pr["total"], 3) if pr["total"] else None
        st["t_rates"] = [
            round(st["per_rr"][rr]["target"] / st["per_rr"][rr]["total"], 3)
            if st["per_rr"][rr]["total"] else None
            for rr in rr_multiples
        ]
        st["avg_pnl"] = round(pr["pnl"] / pr["total"], 2) if pr["total"] else None
        st["total_pnl"] = round(pr["pnl"], 2) if pr["total"] else None
        st["eod"] = len(st["eod_keys"])
        day_rates = [d[0] / d[1] for d in st["day_primary"].values() if d[1] > 0]
        st["day_hit_spread"] = round(100 * (max(day_rates) - min(day_rates)), 1) if day_rates else None
        st["n_days"] = len(st["day_primary"])
        stats.append(st)
    return stats


def _rank_variants(stats, min_setups):
    eligible = [s for s in stats if s["hit_rate_pct"] is not None and s["trades"] >= min_setups]
    return sorted(eligible, key=lambda s: (s["hit_rate_pct"], s["total_pnl"] or 0), reverse=True)


def _direction_param_keys(stats, direction):
    """Swept-param column order for a direction: the keys of its first
    variant (insertion order follows the config's sweep-axes order)."""
    for s in stats:
        if s["direction"] == direction:
            return list(s["params"].keys())
    return []


# ============================================================
# CONSOLE REPORT (mirrors sample.log)
# ============================================================

def _print_run_header(config, config_path, analyzer, n_files, min_setups):
    data_cfg = config.get("data", {})
    output_cfg = config.get("output", {})
    print("=" * 100)
    print("NIFTY DIRECTIONAL STRATEGY ENGINE - OPTIMIZE RUN")
    print("=" * 100)
    print(f"config            : {config_path or '(dict)'}")
    print(f"mode              : optimize")
    print(f"input dir         : {data_cfg.get('input_dir', '?')}")
    print(f"file pattern      : {data_cfg.get('file_pattern', 'NIFTY_*_DASHBOARD.json')}")
    print(f"output dir        : {output_cfg.get('directory', 'output_data/optimize_results')}")
    print()
    print("run settings")
    print(f"  entry rule        : {analyzer.entry_candle_summary()}")
    if analyzer.entry_candle_cfg["enabled"]:
        print(f"  sma_period        : {analyzer.entry_candle_cfg['sma_period']}")
        print(f"  window_candles    : {analyzer.entry_candle_cfg['window_candles']}")
    print(f"  rr multiples      : {' '.join(str(r) for r in analyzer.rr_multiples)}")
    print(f"  min setups        : {min_setups}")
    print(f"  num_workers       : {analyzer._resolve_num_workers()}")
    print(f"  directions        : LONG SHORT")

    print()
    print("sweep scope")
    any_swept = False
    for direction in ("LONG", "SHORT"):
        for c in analyzer.strategy.entry_conditions(direction):
            swept = {k: v for k, v in c.items()
                     if k not in ("type", "enabled") and isinstance(v, list)}
            if not swept:
                continue
            any_swept = True
            print(f"  condition group   : {c['type']} ({direction})")
            for k, v in swept.items():
                print(f"    {k:17s}: {' '.join(str(x) for x in v)}")
    if not any_swept:
        print("  (no swept parameters — single fixed variant per direction)")
    n_long, n_short = len(analyzer.variants["LONG"]), len(analyzer.variants["SHORT"])
    print(f"  cartesian variants: LONG {n_long} x SHORT {n_short} = {n_long + n_short} per timeframe")


def _print_top_table(title, stats, direction, rr_multiples, min_setups, top_n=5):
    print()
    print(f"--- {title} (by hit rate, min setups {min_setups}) ---")
    ranked = _rank_variants([s for s in stats if s["direction"] == direction], min_setups)
    if not ranked:
        print(f"  (no {direction} variant met the minimum setups guard)")
        return ranked

    param_keys = _direction_param_keys(stats, direction)
    header = (f"{'rank':<5} {'variant':<34} {'hit_rate':>8} {'setups':>7} {'entries':>8} "
              f"{'trades':>7} {'no_entry':>9} {'avg_pnl':>8} {'stop':>6}")
    for i in range(len(rr_multiples)):
        header += f" {'t%d' % (i + 1):>6}"
    for k in param_keys:
        header += f" {k[:12]:>12}"
    print(header)

    for rank, s in enumerate(ranked[:top_n], 1):
        line = (f"{rank:<5} {s['variant'][:34]:<34} "
                f"{(s['hit_rate_pct'] or 0) / 100:>8.2f} {s['setups_total']:>7} {s['entries']:>8} "
                f"{s['trades']:>7} {s['no_entry']:>9} {s['avg_pnl'] or 0:>8.2f} {s['stop_rate'] or 0:>6.2f}")
        for rate in s["t_rates"]:
            line += f" {rate or 0:>6.2f}"
        for k in param_keys:
            line += f" {str(s['params'].get(k, ''))[:12]:>12}"
        print(line)
    return ranked


def _print_day_report(day_idx, path_name, analyzer, setups, rr_multiples, min_setups, report_path):
    print()
    print("=" * 100)
    print(f"DAY {day_idx} - {path_name}")
    print("=" * 100)
    print(f"timeframes      : {' '.join(analyzer.timeframe_labels)}")
    print(f"LONG variants   : {len(analyzer.variants['LONG'])}")
    print(f"SHORT variants  : {len(analyzer.variants['SHORT'])}")

    stats = _aggregate_variant_stats(setups, rr_multiples)
    _print_top_table("SHORT top variants", stats, "SHORT", rr_multiples, min_setups)
    _print_top_table("LONG top variants", stats, "LONG", rr_multiples, min_setups)

    n_no_entry = sum(1 for s in setups if s["outcome"] == _NO_ENTRY)
    n_zero_risk = sum(1 for s in setups if s["outcome"] == _ZERO_RISK)
    eod_keys = {(s["timeframe_seconds"], s["date"], s["trigger_time"])
                for s in setups if s["outcome"] == "End Of Data"}
    print()
    print(f"no-entry triggers    : {n_no_entry}")
    print(f"zero-risk skipped    : {n_zero_risk}")
    print(f"eod closes           : {len(eod_keys)}")
    print(f"daily report         : {report_path}")


def _print_best_block(label, s, rr_multiples):
    print(f"combined best {label}")
    print(f"  variant : {s['variant']}")
    for k, v in s["params"].items():
        print(f"  {k:17s}: {v}")
    print(f"  hit_rate: {(s['hit_rate_pct'] or 0) / 100:.3f}")
    print(f"  setups  : {s['setups_total']}")
    print(f"  entries : {s['entries']}")
    print(f"  trades  : {s['trades']}")
    print(f"  no_entry: {s['no_entry']}")
    print(f"  avg_pnl : {s['avg_pnl']}")
    print(f"  stop    : {s['stop_rate']}")
    for i, rate in enumerate(s["t_rates"], 1):
        print(f"  t{i}_rate : {rate}")


def _print_combined_report(combined_setups, analyzer, n_files, rr_multiples, min_setups):
    print()
    print("=" * 100)
    print("COMBINED RUN SUMMARY")
    print("=" * 100)

    stats = _aggregate_variant_stats(combined_setups, rr_multiples)
    n_long, n_short = len(analyzer.variants["LONG"]), len(analyzer.variants["SHORT"])

    total_triggers = sum(s["setups_total"] for s in stats)
    total_entries = sum(s["entries"] for s in stats)
    total_trades = sum(s["trades"] for s in stats)
    total_no_entry = sum(s["no_entry"] for s in stats)
    total_zero_risk = sum(s["zero_risk"] for s in stats)
    total_eod = sum(s["eod"] for s in stats)

    print(f"files processed         : {n_files}")
    print(f"variants evaluated      : LONG {n_long} / SHORT {n_short}")
    print(f"total triggers          : {total_triggers}")
    print(f"total entries           : {total_entries}")
    print(f"total trades            : {total_trades}")
    print(f"no-entry triggers       : {total_no_entry}")
    print(f"zero-risk skipped       : {total_zero_risk}")
    print(f"eod closes              : {total_eod}")

    best_by_dir = {}
    for direction in ("SHORT", "LONG"):
        ranked = _rank_variants([s for s in stats if s["direction"] == direction], min_setups)
        print()
        if not ranked:
            print(f"combined best {direction}")
            print(f"  (no variant met the minimum setups guard)")
            continue
        best = ranked[0]
        best_by_dir[direction] = (best, ranked)
        _print_best_block(direction, best, rr_multiples)

        band = [s for s in ranked
                if (best["hit_rate_pct"] - s["hit_rate_pct"]) <= 3.0]  # within 0.03 hit rate
        print()
        print(f"near-best {direction} band (within 0.03 of best hit rate, setups >= {min_setups})")
        for s in band[:6]:
            print(f"  {s['variant'][:40]:<40} hit {s['hit_rate_pct'] / 100:.3f}  "
                  f"setups {s['setups_total']}  avg_pnl {s['avg_pnl']}  stop {s['stop_rate']}")

    # ---- narrative + conclusion (data-driven) ----
    print()
    print("what the numbers say")
    bullets = []
    for direction, (best, ranked) in best_by_dir.items():
        band = [s for s in ranked if (best["hit_rate_pct"] - s["hit_rate_pct"]) <= 3.0]
        if len(band) > 1:
            bullets.append(f"  - {direction}: best hit rate is not unique — {len(band)} variants sit "
                           f"within 0.03 of the top; the pick is a band, not a single point.")
        else:
            bullets.append(f"  - {direction}: one variant clearly leads the sweep.")
        if best["day_hit_spread"] is not None:
            tone = "stable across days" if best["day_hit_spread"] <= 15 else "day-to-day hit rate varies a lot"
            bullets.append(f"  - {direction} best variant hit rate spans {best['day_hit_spread']:.1f} pts "
                           f"across {best['n_days']} day(s) — {tone}.")
        if best["stop_rate"] is not None and best["stop_rate"] > 0.5:
            bullets.append(f"  - {direction} best variant is stop-heavy (stop rate {best['stop_rate']:.2f}).")
        if len(ranked) > 1 and ranked[1]["avg_pnl"] is not None and best["avg_pnl"] is not None \
                and ranked[1]["avg_pnl"] > best["avg_pnl"]:
            bullets.append(f"  - {direction}: runner-up '{ranked[1]['variant'][:40]}' has higher avg P&L "
                           f"({ranked[1]['avg_pnl']} vs {best['avg_pnl']} pts) at hit rate "
                           f"{ranked[1]['hit_rate_pct'] / 100:.2f}.")
        # day concentration for the best variant
        day_rows = defaultdict(int)
        for s in combined_setups:
            if s["direction"] == direction and s["variant"] == best["variant"] and s["rr_multiple"] is not None:
                day_rows[s["date"]] += 1
        if day_rows:
            top3 = sum(c for _, c in sorted(day_rows.items(), key=lambda kv: kv[1], reverse=True)[:3])
            conc = top3 / sum(day_rows.values())
            bullets.append(f"  - {direction} top3 day conc : {conc:.2f} (share of the best variant's "
                           f"trades coming from its 3 biggest days).")
    for b in bullets:
        print(b)

    print()
    print("ranking conclusion")
    for direction, (best, ranked) in best_by_dir.items():
        print(f"  primary candidate   : {best['variant']}")
        print(f"    why   : highest {direction} hit rate ({best['hit_rate_pct'] / 100:.3f}) "
              f"with {best['trades']} trades and {best['avg_pnl']} avg pts.")
        if len(ranked) > 1:
            second = ranked[1]
            print(f"  secondary candidate : {second['variant']}")
            print(f"    why   : hit rate {second['hit_rate_pct'] / 100:.3f}, "
                  f"avg P&L {second['avg_pnl']} pts.")
        tail = [s for s in ranked if (best["hit_rate_pct"] - s["hit_rate_pct"]) > 3.0]
        if tail:
            shown = ", ".join(f"{s['variant'][:28]} ({s['hit_rate_pct'] / 100:.2f})" for s in tail[:3])
            print(f"  rejected as final pick: {shown}")

    print()
    print("recommended next step")
    if best_by_dir:
        prim = ", ".join(f"{d}: {best['variant']}" for d, (best, _) in best_by_dir.items())
        print(f"  1. freeze the primary candidate{(' (' + prim + ')') if prim else ''}.")
        print(f"  2. keep the secondary as a comparison if avg P&L matters more than hit rate.")
        print(f"  3. confirm the chosen candidate still holds on new days before final.")
    else:
        print(f"  1. no variant met the minimum setups guard — widen the sweep or lower "
              f"min_setups_for_ranking ({min_setups}).")

    print()
    print("one-line conclusion")
    if best_by_dir:
        parts = []
        for direction, (best, _) in best_by_dir.items():
            parts.append(f"{direction} {best['variant']} (hit {(best['hit_rate_pct'] or 0) / 100:.2f}, "
                         f"{best['trades']} trades, {best['avg_pnl']} avg pts)")
        print(f"  Best usable candidates from this cartesian run: {'; '.join(parts)}.")
    else:
        print(f"  No usable candidate — every variant fell below the minimum setups guard.")
    print("=" * 100)


# ============================================================
# MAIN
# ============================================================

def run_optimize(config, config_path=None):
    """Process every file matching data.file_pattern in data.input_dir,
    one at a time: run the full simulation against that single file's
    data, write its Excel output, print its day report, then move to the
    next file. Ends with the combined run summary. Returns a list of
    per-file result dicts."""
    files = _list_input_files(config.get("data", {}))
    min_setups = int(config.get("analysis", {}).get("min_setups_for_ranking", 20))

    proto = StrategyAnalyzer(config)
    _print_run_header(config, config_path, proto, len(files), min_setups)

    results = []
    combined_trades = []
    combined_setups = []

    for idx, path in enumerate(files, 1):
        # A fresh per-file config narrowed to exactly this one file, so
        # load_dashboard_data_multi (unmodified) only ever loads this
        # single day — the next file isn't touched until this one
        # finishes end to end (simulate, write Excel).
        per_file_cfg = copy.deepcopy(config)
        per_file_cfg["data"]["file_pattern"] = path.name

        data = load_dashboard_data_multi(per_file_cfg["data"])
        analyzer = StrategyAnalyzer(per_file_cfg)
        setups = analyzer.run(data)
        output_path = analyzer.write_excel(setups, per_file_cfg.get("output", {}))

        _print_day_report(idx, path.name, analyzer, setups, analyzer.rr_multiples,
                          min_setups, output_path)

        results.append({
            "file": path.name,
            "excel": output_path,
            "triggers": sum(1 for s in setups if s["rr_multiple"] is not None or s["outcome"] == _NO_ENTRY),
            "trades": len(analyzer.all_trades(setups)),
            "no_entry": sum(1 for s in setups if s["outcome"] == _NO_ENTRY),
        })

        combined_setups.extend(setups)
        for t in analyzer.all_trades(setups):
            combined_trades.append({"source_file": path.name, **t})

    combined_excel_path = _write_combined_excel(combined_trades, config.get("output", {}), len(files))
    _print_combined_report(combined_setups, proto, len(files), proto.rr_multiples, min_setups)
    print(f"COMBINED EXCEL: {combined_excel_path}")

    print()
    print("=" * 100)
    print(f"OPTIMIZE MODE COMPLETE: {len(results)}/{len(files)} file(s) processed")
    print("=" * 100)
    return results


def _combined_pnl_stats(combined_trades):
    resolved = [t for t in combined_trades if t["pnl_points"] is not None]
    hits = sum(1 for t in resolved if t["outcome"] == "Target")
    total_pnl = sum(t["pnl_points"] for t in resolved)
    return {
        "total_trades": len(combined_trades),
        "resolved_trades": len(resolved),
        "target_hit": hits,
        "hit_rate_pct": round(100 * hits / len(resolved), 2) if resolved else None,
        "total_pnl_points": round(total_pnl, 2) if resolved else None,
        "avg_pnl_points": round(total_pnl / len(resolved), 2) if resolved else None,
    }


def _write_combined_excel(combined_trades, output_config, num_files):
    """One workbook covering every trade from every file processed this
    run — a SUMMARY sheet with the combined P&L, and an ALL_TRADES sheet
    with every trade (tagged by its source file), timestamped at the end
    with when this combined report was generated."""
    from openpyxl import Workbook

    directory = Path(output_config.get("directory", "output_data/optimize_results"))
    directory.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now()
    path = directory / f"optimize_combined_{generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"

    stats = _combined_pnl_stats(combined_trades)

    wb = Workbook()
    ws = wb.active
    ws.title = "SUMMARY"
    ws.append(["Files Processed", num_files])
    ws.append(["Total Unique Trades", stats["total_trades"]])
    ws.append(["Resolved Trades", stats["resolved_trades"]])
    ws.append(["Target Hit", stats["target_hit"]])
    ws.append(["Overall Hit Rate %", stats["hit_rate_pct"]])
    ws.append(["Total P&L (points)", stats["total_pnl_points"]])
    ws.append(["Avg P&L per Trade (points)", stats["avg_pnl_points"]])
    ws.append(["Generated At", generated_at.strftime("%Y-%m-%d %H:%M:%S")])

    trades_sorted = sorted(
        combined_trades, key=lambda t: (t["timeframe_seconds"], t["date"], t["trigger_time"])
    )
    trades_ws = write_sheet(wb, "ALL_TRADES_COMBINED", trades_sorted)
    trades_ws.append([])
    trades_ws.append([f"Generated At: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}"])

    wb.save(path)
    return path
