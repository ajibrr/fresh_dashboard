import csv
from pathlib import Path

# ============================================================
# SHARED DISPLAY NAMES
#
# Every report writer in the project routes column headers through here,
# so a field always shows the same human-readable name everywhere it
# appears — same pattern as this project's option-premium sibling.
# ============================================================

_DISPLAY_HEADERS = {
    "date": "Date",
    "time": "Time",
    "timestamp": "Timestamp",
    "timeframe": "Timeframe",
    "timeframe_seconds": "Timeframe (s)",
    "direction": "Direction",
    "condition": "Condition",
    "variant": "Variant",
    "candles": "Candles",
    "lookback": "Lookback Candles",
    "window_candles": "Price-vs-SMA9 Window",
    "signal_window_candles": "RSI-vs-Signal Window",
    "atr_multiplier": "ATR Multiplier",
    "atr_period": "ATR Period",
    "num_variants_matched": "Variants Matched",
    "variants_matched": "Variants That Matched",
    "trigger_time": "Trigger Time",
    "entry_candle_time": "Entry Candle Time",
    "entry_price": "Entry Price",
    "stop_price": "Stop Price",
    "target_price": "Target Price",
    "rr_multiple": "R:R Multiple",
    "exit_time": "Exit Time",
    "exit_price": "Exit Price",
    "outcome": "Outcome",
    "cumulative_ce": "Cumulative CE",
    "cumulative_pe": "Cumulative PE",
    "tick_count": "Tick Count",
    "pnl_points": "P&L (points)",
    "holding_minutes": "Holding Time (min)",
    "total_pnl_points": "Total P&L (points)",
    "avg_pnl_points": "Avg P&L (points)",
    "max_pnl_points": "Max Profit (points)",
    "max_loss_points": "Max Loss (points)",
    "avg_holding_minutes": "Avg Holding Time (min)",
    "avg_entry_time": "Avg Entry Time",
    "avg_exit_time": "Avg Exit Time",

    "total_setups": "Total Trades",
    "no_entry": "Triggers With No Entry",
    "no_entry_setups": "No Entry Count",
    "avg_trigger_time": "Avg Trigger Time",
    "target_hit": "Target Hit",
    "stop_hit": "Stop Hit",
    "end_of_data": "End Of Data",
    "hit_rate_pct": "Hit Rate %",
}


def display_header(key):
    # target_sweep_trades() builds columns like "exit_time_1_2"/"pnl_1_2"
    # per R:R multiple dynamically (2.0 -> "_1_2", 3.0 -> "_1_3", ...).
    if key.startswith("exit_time_1_"):
        return f"Exit Time 1:{key.rsplit('_', 1)[-1]}"
    if key.startswith("pnl_1_"):
        return f"P&L 1:{key.rsplit('_', 1)[-1]} (points)"
    # _condition_columns() builds cond_1..cond_N — one column per
    # condition in the AND chain, so Excel filters work per condition.
    if key.startswith("cond_") and key[5:].isdigit():
        return f"Cond {key[5:]}"
    return _DISPLAY_HEADERS.get(key, key.replace("_", " ").title())


def _cell_value(value):
    """Coerce any value into something openpyxl accepts in a cell.
    openpyxl raises ValueError("Cannot convert ... to Excel") for
    lists/dicts/etc; a sheet writer must never take the whole run down
    over one weird cell, so containers are joined into a readable string
    ("a | b | c") instead."""
    if isinstance(value, (list, tuple, set)):
        return " | ".join(str(_cell_value(v)) for v in value)
    if isinstance(value, dict):
        return " | ".join(f"{k}={_cell_value(v)}" for k, v in value.items())
    return value


def write_rows(path, rows, display=True):
    if not rows:
        return
    if display:
        rows = [{display_header(k): v for k, v in r.items()} for r in rows]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_sheet(wb, sheet_name, rows):
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    ws = wb.create_sheet(sheet_name)
    if not rows:
        ws.append(["No data"])
        return ws

    headers = list(rows[0].keys())
    ws.append([display_header(h) for h in headers])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for row in rows:
        ws.append([_cell_value(row.get(h)) for h in headers])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in range(1, ws.max_column + 1):
        header = str(ws.cell(1, col).value or "")
        ws.column_dimensions[get_column_letter(col)].width = max(14, min(28, len(header) + 4))

    return ws
