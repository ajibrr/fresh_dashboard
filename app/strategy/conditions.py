def get_feature(features, name, i):
    values = features.get(name)
    return None if values is None or i >= len(values) else values[i]


def evaluate(c, rows, features, i):
    typ = c["type"]
    row = rows[i]

    if typ in ("sma_rising_candles", "sma_falling_candles"):
        # Plain monotonic check over the last N candles — any move counts,
        # however small. Unconditional: this type only ever does this.
        p = int(c["period"])
        n = int(c["candles"])
        if i < n - 1:
            return False
        vals = [get_feature(features, f"sma_{p}", j) for j in range(i - n + 1, i + 1)]
        if any(v is None for v in vals):
            return False
        if typ == "sma_rising_candles":
            return all(vals[j - 1] < vals[j] for j in range(1, len(vals)))
        return all(vals[j - 1] > vals[j] for j in range(1, len(vals)))

    if typ in ("sma_rising_atr", "sma_falling_atr"):
        # Meaningful move relative to volatility: net SMA change over the
        # last N candles must exceed atr_multiplier x ATR, not merely be
        # positive/negative. Unconditional: this type only ever does this.
        p = int(c["period"])
        n = int(c["candles"])
        atr_p = int(c["atr_period"])
        multiplier = float(c["atr_multiplier"])
        if i < n:
            return False
        sma_now = get_feature(features, f"sma_{p}", i)
        sma_then = get_feature(features, f"sma_{p}", i - n)
        atr_now = get_feature(features, f"atr_{atr_p}", i)
        if sma_now is None or sma_then is None or atr_now is None:
            return False
        move = (sma_now - sma_then) if typ == "sma_rising_atr" else (sma_then - sma_now)
        return move >= multiplier * atr_now

    if typ in ("sma_cross_above", "sma_cross_below"):
        # Meaningful crossover relative to volatility: fast/slow SMA gap
        # must exceed atr_multiplier x ATR, not merely be on the right
        # side of zero — a fast SMA a fraction of a point above/below the
        # slow one is noise, not a real crossover. Unconditional: this
        # type only ever does this.
        fast = get_feature(features, f"sma_{int(c['fast_period'])}", i)
        slow = get_feature(features, f"sma_{int(c['slow_period'])}", i)
        atr_p = int(c["cross_atr_period"])
        multiplier = float(c["cross_atr_multiplier"])
        atr_now = get_feature(features, f"atr_{atr_p}", i)
        if fast is None or slow is None or atr_now is None:
            return False
        gap = (fast - slow) if typ == "sma_cross_above" else (slow - fast)
        return gap >= multiplier * atr_now

    if typ == "rsi_range":
        p = int(c["period"])
        value = get_feature(features, f"rsi_{p}", i)
        if value is None:
            return False
        return float(c["min"]) <= value <= float(c["max"])

    if typ == "rsi_extreme_lookback":
        p = int(c["period"])
        n = int(c["lookback"])
        level = float(c["level"])
        side = c["side"]
        if i < n:
            return False  # not enough prior candles for a full lookback window
        vals = [get_feature(features, f"rsi_{p}", j) for j in range(i - n, i)]  # strictly before i
        vals = [v for v in vals if v is not None]
        if not vals:
            return False
        if side == "above":
            return any(v > level for v in vals)
        if side == "below":
            return any(v < level for v in vals)
        raise ValueError(f"Unknown rsi_extreme_lookback side: {side}")

    if typ in ("price_stuck_below_sma", "price_stuck_above_sma"):
        p = int(c["period"])
        n = int(c["window_candles"])
        skip = int(c["skip_recent"])
        start = i - skip - n
        end = i - skip  # exclusive
        if start < 0:
            return False
        for j in range(start, end):
            if rows[j]["tick_count"] == 0:
                return False  # a data gap in the window — can't confirm the price stayed on one side
            sma_val = get_feature(features, f"sma_{p}", j)
            if sma_val is None:
                return False
            if typ == "price_stuck_below_sma":
                if not (rows[j]["open"] < sma_val and rows[j]["close"] < sma_val):
                    return False
            else:
                if not (rows[j]["open"] > sma_val and rows[j]["close"] > sma_val):
                    return False
        return True

    if typ in ("rsi_below_signal_lookback", "rsi_above_signal_lookback"):
        p = int(c["period"])
        sp = int(c["signal_period"])
        n = int(c["signal_window_candles"])
        skip = int(c["skip_recent"])
        start = i - skip - n
        end = i - skip  # exclusive
        if start < 0:
            return False
        for j in range(start, end):
            if rows[j]["tick_count"] == 0:
                return False  # a data gap in the window — can't confirm RSI stayed on one side
            rsi_val = get_feature(features, f"rsi_{p}", j)
            signal_val = get_feature(features, f"rsi_signal_{p}_{sp}", j)
            if rsi_val is None or signal_val is None:
                return False
            if typ == "rsi_below_signal_lookback":
                if not (rsi_val < signal_val):
                    return False
            else:
                if not (rsi_val > signal_val):
                    return False
        return True

    if typ in ("low_in_sma_band", "high_in_sma_band"):
        # SMA computed from the high series and from the low series forms a
        # band, not a single line. BUY: the candle's own low must sit
        # inside that band (price hasn't broken below the SMA structure).
        # SELL: the candle's own high must sit inside the band (price
        # hasn't broken above it). Unconditional: each type only ever
        # checks its own side.
        p = int(c["period"])
        band_high = get_feature(features, f"sma_high_{p}", i)
        band_low = get_feature(features, f"sma_low_{p}", i)
        if band_high is None or band_low is None:
            return False
        lo, hi = min(band_low, band_high), max(band_low, band_high)
        if typ == "low_in_sma_band":
            return lo <= row["low"] <= hi
        return lo <= row["high"] <= hi

    if typ in ("low_below_bollinger_lower", "high_above_bollinger_upper"):
        # Bollinger pierce check. LONG: the candle's own LOW must be below
        # the lower band (price stretched under the band). SHORT: the
        # candle's own HIGH must be above the upper band. Unconditional:
        # each type only ever checks its own side.
        p = int(c["bb_period"])
        num_std = float(c["bb_num_std"])
        # The BB feature is a (mid, upper, lower) TUPLE of three series, not
        # one flat series — fetch it from the dict directly (get_feature
        # would index it as if it were a single series and return None).
        band = features.get(f"bb_{p}_{num_std:g}")
        if not band or band[0] is None or band[0][i] is None:
            return False
        _, upper, lower = band
        if typ == "low_below_bollinger_lower":
            return row["low"] < lower[i]
        return row["high"] > upper[i]

    if typ == "cumulative_oi_compare":
        ce = row.get("cumulative_ce")
        pe = row.get("cumulative_pe")
        if ce is None or pe is None:
            return False
        if c["side"] == "pe_greater":
            return pe > ce
        if c["side"] == "ce_greater":
            return ce > pe
        raise ValueError(f"Unknown cumulative_oi_compare side: {c['side']}")

    raise ValueError(f"Unknown condition type: {typ}")


def evaluate_all(conditions, rows, features, i):
    """No conditions at all => baseline/no-filter mode: every candle passes."""
    return all(evaluate(c, rows, features, i) for c in conditions)
