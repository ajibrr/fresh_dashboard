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
     each configured R:R multiple of that risk is a target. A trigger
     with no qualifying close in its window is recorded as "No Entry".

Per day it writes that day's own Excel report, then moves to the next
file only once the current one is done. At the end a combined workbook
covers every trade from every file processed this run.
"""

import copy
from datetime import datetime
from pathlib import Path

from app.analyzer import StrategyAnalyzer
from app.data.loader import load_dashboard_data_multi
from app.reports.reporter import write_sheet


def _list_input_files(data_cfg):
    input_dir = Path(data_cfg["input_dir"])
    if not input_dir.exists():
        raise FileNotFoundError(input_dir)
    pattern = data_cfg.get("file_pattern", "NIFTY_*_DASHBOARD.json")
    files = sorted(input_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no files matching {pattern!r} found in {input_dir}")
    return files


def run_optimize(config):
    """Process every file matching data.file_pattern in data.input_dir,
    one at a time: run the full simulation against that single file's
    data, write its Excel output, print a short summary, then move to the
    next file. Returns a list of per-file result dicts."""
    files = _list_input_files(config.get("data", {}))

    results = []
    combined_trades = []
    print(f"OPTIMIZE MODE: {len(files)} file(s) to process, one at a time")
    print("=" * 100)

    for idx, path in enumerate(files, 1):
        print()
        print("-" * 100)
        print(f"[{idx}/{len(files)}] {path.name}")
        print("-" * 100)

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

        overall, _, _, _ = analyzer.summarize(setups)
        all_trades = analyzer.all_trades(setups)
        n_no_entry = sum(1 for s in setups if s["outcome"] == "No Entry")

        print(f"  Triggers: {len(all_trades) + n_no_entry}   Trades entered: {len(all_trades)}   No Entry: {n_no_entry}")

        for row in overall:
            if row["total_setups"] > 0:
                print(f"  [{row['timeframe']}] {row['direction']:5s} 1:{row['rr_multiple']:.0f}  "
                      f"trades={row['total_setups']}  hit_rate={row['hit_rate_pct']}%  "
                      f"total_pnl={row['total_pnl_points']} points")

        results.append({
            "file": path.name,
            "excel": output_path,
            "triggers": len(all_trades) + n_no_entry,
            "trades": len(all_trades),
            "no_entry": n_no_entry,
        })

        for t in all_trades:
            combined_trades.append({"source_file": path.name, **t})

    combined_excel_path = _write_combined_excel(combined_trades, config.get("output", {}), len(files))
    _print_combined_summary(combined_trades, len(files), combined_excel_path)

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


def _print_combined_summary(combined_trades, num_files, combined_excel_path):
    stats = _combined_pnl_stats(combined_trades)
    print()
    print("=" * 100)
    print(f"COMBINED P&L — ALL TRADES ACROSS ALL {num_files} FILE(S)")
    print("=" * 100)
    print(f"  Total unique trades : {stats['total_trades']}")
    print(f"  Resolved trades     : {stats['resolved_trades']}")
    print(f"  Target hit          : {stats['target_hit']}")
    print(f"  Overall hit rate    : {stats['hit_rate_pct']}%" if stats["hit_rate_pct"] is not None
          else "  Overall hit rate    : n/a (no resolved trades)")
    print(f"  TOTAL P&L (COMBINED): {stats['total_pnl_points']} points" if stats["total_pnl_points"] is not None
          else "  TOTAL P&L (COMBINED): n/a")
    print(f"  Avg P&L per trade   : {stats['avg_pnl_points']} points" if stats["avg_pnl_points"] is not None
          else "  Avg P&L per trade   : n/a")

    by_key = {}
    for t in combined_trades:
        if t["pnl_points"] is None:
            continue
        key = (t["timeframe"], t["direction"])
        by_key.setdefault(key, []).append(t["pnl_points"])
    if by_key:
        print("  Breakdown by timeframe/direction:")
        for (tf, direction), pnls in sorted(by_key.items()):
            print(f"    [{tf}] {direction:5s}  trades={len(pnls)}  total_pnl={round(sum(pnls), 2)} points")

    print(f"  COMBINED EXCEL: {combined_excel_path}")


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
