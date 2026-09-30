import json
from pathlib import Path
from datetime import datetime, timedelta

MARKET_OPEN = "09:15:00"
MARKET_CLOSE = "15:30:00"  # exclusive upper bound — candles tile [09:15, 15:30)


def _resolve_one_timeframe(tf):
    if not isinstance(tf, dict):
        raise ValueError(
            f'each timeframe entry must be an object like {{"seconds": 60}}, got: {tf!r}'
        )
    if "seconds" in tf:
        return int(tf["seconds"])
    if "minutes" in tf:
        return int(tf["minutes"]) * 60
    return 60


def resolve_timeframe_seconds(cfg):
    """
    Single-timeframe resolver (back-compat). cfg["timeframe"] is an object,
    not a bare number, so more fields can be added later without changing
    its type:
        {"seconds": 60}   -> 1-min candles
        {"seconds": 12}   -> 12-sec candles
        {"minutes": 5}    -> also accepted, converted to seconds internally

    Everything downstream works in seconds only — "minutes" is just a
    convenience spelling at the config layer. Source ticks are 1-second
    resolution, so anything below 1s isn't meaningful and isn't supported.

    Falls back to 60s (1 min) if cfg["timeframe"] is missing entirely. If
    cfg["timeframe"] is a list, only the first entry is used — use
    resolve_timeframes_seconds() for the full swept list.
    """
    tf = cfg.get("timeframe", {})
    if isinstance(tf, list):
        return _resolve_one_timeframe(tf[0]) if tf else 60
    return _resolve_one_timeframe(tf)


def resolve_timeframes_seconds(cfg):
    """
    Like resolve_timeframe_seconds(), but timeframe-as-a-sweep-list aware:
        "timeframe": [{"seconds": 12}, {"seconds": 60}, {"seconds": 180}]
    sweeps all three. A single object (not a list) is treated as a
    one-element list, so existing single-timeframe configs keep working
    unchanged. Returns a de-duplicated list of ints, in the order given.
    """
    tf = cfg.get("timeframe", {})
    entries = tf if isinstance(tf, list) else [tf]
    seconds_list = [_resolve_one_timeframe(e) for e in entries]
    seen = []
    for s in seconds_list:
        if s not in seen:
            seen.append(s)
    return seen or [60]


def timeframe_label(timeframe_seconds):
    if timeframe_seconds % 60 == 0:
        return f"{timeframe_seconds // 60}min"
    return f"{timeframe_seconds}sec"


def _candle_buckets(date_str, timeframe_seconds):
    start = datetime.strptime(f"{date_str} {MARKET_OPEN}", "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(f"{date_str} {MARKET_CLOSE}", "%Y-%m-%d %H:%M:%S")
    step = timedelta(seconds=timeframe_seconds)
    buckets, t = [], start
    while t < end:
        buckets.append(t)
        t += step
    return buckets


def _date_from_filename(path):
    # NIFTY_20260918_DASHBOARD.json -> 2026-09-18
    raw = path.stem.replace("NIFTY_", "").replace("_DASHBOARD", "")
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _build_ohlc(raw, date_str, timeframe_seconds):
    """
    DashBoard.log's per-second series (raw["nifty_seconds"]) resampled into
    `timeframe_seconds`-wide OHLC candles covering the full 09:15-15:30
    trading window. Candles with no ticks (data gaps) are zero-filled, not
    dropped, and flagged via tick_count == 0 so downstream code can tell a
    real zero candle apart from a missing one.

    Each candle is also joined with raw["flow"] (the 1-min OI-flow series)
    so cumulative_ce/cumulative_pe are available for the
    cumulative_oi_compare condition — the last flow row inside the candle's
    window is used (its running cumulative total as of the candle's close).
    A candle with no matching flow row gets None for those fields. Below
    1-minute timeframes, most candles simply won't have a matching flow row
    at all (the flow series is itself only 1-min resolution) — that's
    expected, not a bug.
    """
    step = timedelta(seconds=timeframe_seconds)
    buckets = _candle_buckets(date_str, timeframe_seconds)

    ticks = []
    for tick in raw.get("nifty_seconds", []):
        ts = datetime.strptime(tick["timestamp"], "%Y-%m-%d %H:%M:%S")
        ticks.append((ts, tick["nifty"]))
    ticks.sort(key=lambda x: x[0])

    flow_entries = []
    for entry in raw.get("flow", []):
        ts = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
        flow_entries.append((ts, entry))
    flow_entries.sort(key=lambda x: x[0])

    rows = []
    tick_idx = 0
    flow_idx = 0
    n_ticks = len(ticks)
    n_flow = len(flow_entries)
    last_known_flow = None  # most recent flow row seen so far, for carry-forward

    for bucket_start in buckets:
        bucket_end = bucket_start + step

        while tick_idx < n_ticks and ticks[tick_idx][0] < bucket_start:
            tick_idx += 1
        j = tick_idx
        prices = []
        while j < n_ticks and ticks[j][0] < bucket_end:
            prices.append(ticks[j][1])
            j += 1

        if prices:
            o, h, l, c, n = prices[0], max(prices), min(prices), prices[-1], len(prices)
        else:
            o = h = l = c = 0.0
            n = 0

        while flow_idx < n_flow and flow_entries[flow_idx][0] < bucket_start:
            flow_idx += 1
        k = flow_idx
        last_flow = None
        while k < n_flow and flow_entries[k][0] < bucket_end:
            last_flow = flow_entries[k][1]
            k += 1
        if last_flow is not None:
            last_known_flow = last_flow
        # CARRY-FORWARD: the flow series is 1-min resolution, so at
        # sub-minute timeframes most candles have no flow row of their
        # own. Without carry-forward the cumulative_oi_compare condition
        # would auto-fail on ~4 of every 5 12-sec candles; carrying the
        # last known cumulative CE/PE forward keeps the OI state meaningful
        # on every candle (it only updates once per minute, as in reality).
        flow_entry = last_flow or last_known_flow or {}

        rows.append({
            "date": date_str,
            "time": bucket_start.strftime("%H:%M:%S"),
            "timestamp": bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "tick_count": n,
            "cumulative_ce": flow_entry.get("cumulative_ce"),
            "cumulative_pe": flow_entry.get("cumulative_pe"),
            "ce_oi_change": flow_entry.get("ce_oi_change"),
            "pe_oi_change": flow_entry.get("pe_oi_change"),
        })
    return rows


def load_dashboard_data(cfg):
    """
    Loads every NIFTY_*_DASHBOARD.json file in cfg["input_dir"], resampled
    into resolve_timeframe_seconds(cfg)-wide OHLC candles (default 1 min),
    keyed by date.

    Returns: {"2026-09-18": [row, row, ...], ...}
    """
    input_dir = Path(cfg["input_dir"])
    if not input_dir.exists():
        raise FileNotFoundError(input_dir)

    timeframe_seconds = resolve_timeframe_seconds(cfg)
    pattern = cfg.get("file_pattern", "NIFTY_*_DASHBOARD.json")
    result = {}

    for path in sorted(input_dir.glob(pattern)):
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        date_str = _date_from_filename(path)
        rows = _build_ohlc(raw, date_str, timeframe_seconds)

        real_candles = sum(1 for r in rows if r["tick_count"] > 0)
        if real_candles == 0:
            # Silent empty-data guard (Step 9 pitfall): a file whose
            # timestamps fall entirely outside 09:15-15:30 produces an
            # all-zero day that looks like a fast, successful load unless
            # flagged loudly here.
            print(f"WARNING: {path.name} -> 0 real candles inside market "
                  f"hours ({MARKET_OPEN}-{MARKET_CLOSE}); every candle is "
                  f"zero-filled. Check the source file's timestamps.")

        result[date_str] = rows

    return result


def load_dashboard_data_multi(cfg):
    """
    Like load_dashboard_data(), but builds OHLC candles for every timeframe
    in resolve_timeframes_seconds(cfg) — each raw JSON file is parsed once,
    then resampled per requested timeframe, avoiding a re-parse per
    timeframe.

    Returns: {12: {"2026-09-18": [row, ...]}, 60: {...}, 180: {...}}
    """
    input_dir = Path(cfg["input_dir"])
    if not input_dir.exists():
        raise FileNotFoundError(input_dir)

    timeframes = resolve_timeframes_seconds(cfg)
    pattern = cfg.get("file_pattern", "NIFTY_*_DASHBOARD.json")
    result = {tf: {} for tf in timeframes}

    for path in sorted(input_dir.glob(pattern)):
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        date_str = _date_from_filename(path)

        for tf in timeframes:
            rows = _build_ohlc(raw, date_str, tf)

            real_candles = sum(1 for r in rows if r["tick_count"] > 0)
            if real_candles == 0:
                print(f"WARNING: {path.name} -> 0 real candles inside market "
                      f"hours ({MARKET_OPEN}-{MARKET_CLOSE}) at {timeframe_label(tf)}; "
                      f"every candle is zero-filled. Check the source file's timestamps.")

            result[tf][date_str] = rows

    return result
