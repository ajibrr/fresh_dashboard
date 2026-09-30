from app.features.indicators import sma, rsi, atr, bollinger
from app.strategy.definition import enabled_conditions


def build_features(rows, strategy_config):
    """
    Auto-registers whatever SMA/RSI/ATR periods the strategy's entry
    conditions actually reference (sma_rising_candles/sma_falling_candles,
    sma_rising_atr/sma_falling_atr, sma_cross_above/below, rsi_range, ...),
    plus anything explicitly listed under feature_periods, then computes
    each one once.
    """
    sma_periods = set(strategy_config.get("feature_periods", {}).get("sma", []))
    sma_high_periods = set()  # SMA computed from the high series, not close
    sma_low_periods = set()   # SMA computed from the low series, not close
    rsi_periods = set(strategy_config.get("feature_periods", {}).get("rsi", []))
    atr_periods = set(strategy_config.get("feature_periods", {}).get("atr", []))
    rsi_signal_periods = set()  # {(rsi_period, signal_period), ...}
    bollinger_params = set()    # {(period, num_std), ...}

    # The entry-candle rule (close crossing SMA within the window) reads
    # the SMA series directly, so make sure that period is computed even
    # if no entry CONDITION references it.
    for candidate in (strategy_config.get("entry", {}), strategy_config):
        ec = candidate.get("entry_candle")
        if isinstance(ec, dict):
            sma_periods.add(int(ec.get("sma_period", 9)))

    conditions = []
    for direction in ("LONG", "SHORT"):
        conditions.extend(enabled_conditions(strategy_config.get("entry", {}).get(direction, {}).get("conditions", [])))

    for c in conditions:
        if c["type"] in {"sma_rising_candles", "sma_falling_candles"}:
            sma_periods.add(int(c["period"]))
        if c["type"] in {"sma_rising_atr", "sma_falling_atr"}:
            sma_periods.add(int(c["period"]))
            atr_periods.add(int(c["atr_period"]))
        if c["type"] in {"sma_cross_above", "sma_cross_below"}:
            sma_periods.add(int(c["fast_period"]))
            sma_periods.add(int(c["slow_period"]))
            atr_periods.add(int(c["cross_atr_period"]))
        if c["type"] in {"rsi_range", "rsi_extreme_lookback"}:
            rsi_periods.add(int(c["period"]))
        if c["type"] in {"price_stuck_below_sma", "price_stuck_above_sma"}:
            sma_periods.add(int(c["period"]))
        if c["type"] in {"rsi_below_signal_lookback", "rsi_above_signal_lookback"}:
            p = int(c["period"])
            sp = int(c["signal_period"])
            rsi_periods.add(p)
            rsi_signal_periods.add((p, sp))
        if c["type"] in {"low_in_sma_band", "high_in_sma_band"}:
            sma_high_periods.add(int(c["period"]))
            sma_low_periods.add(int(c["period"]))
        if c["type"] in {"low_below_bollinger_lower", "high_above_bollinger_upper"}:
            # bb_period / bb_num_std may each be a sweep list — register
            # every (period, num_std) pair they can produce.
            periods = c["bb_period"]
            num_stds = c["bb_num_std"]
            for p in (periods if isinstance(periods, list) else [periods]):
                for value in (num_stds if isinstance(num_stds, list) else [num_stds]):
                    bollinger_params.add((int(p), float(value)))

    closes = [r["close"] if r["tick_count"] > 0 else None for r in rows]
    highs = [r["high"] if r["tick_count"] > 0 else None for r in rows]
    lows = [r["low"] if r["tick_count"] > 0 else None for r in rows]

    features = {}
    for p in sma_periods:
        features[f"sma_{p}"] = sma(closes, p)
    for p in sma_high_periods:
        features[f"sma_high_{p}"] = sma(highs, p)
    for p in sma_low_periods:
        features[f"sma_low_{p}"] = sma(lows, p)
    for p in rsi_periods:
        features[f"rsi_{p}"] = rsi(closes, p)
    for p in atr_periods:
        features[f"atr_{p}"] = atr(rows, p)
    for p, sp in rsi_signal_periods:
        # "Signal line" for RSI — an SMA of the RSI series itself, same idea as a MACD signal line.
        features[f"rsi_signal_{p}_{sp}"] = sma(features[f"rsi_{p}"], sp)
    for p, ns in bollinger_params:
        features[f"bb_{p}_{ns:g}"] = bollinger(closes, p, ns)
    return features
