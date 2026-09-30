def sma(values, period):
    """Rolling-sum SMA — O(n), not O(n*period) like a naive sum(window) per row."""
    out = [None] * len(values)
    window_sum = 0.0
    valid_count = 0

    for i, v in enumerate(values):
        if v is not None:
            window_sum += v
            valid_count += 1
        if i >= period:
            old = values[i - period]
            if old is not None:
                window_sum -= old
                valid_count -= 1
        if i >= period - 1 and valid_count == period:
            out[i] = window_sum / period
    return out


def bollinger(values, period, num_std):
    """
    Bollinger bands: SMA(period) +/- num_std x rolling standard deviation
    of the values, using POPULATION std (ddof=0) — what TradingView and
    most charting platforms use.

    A window containing a None (a data gap) yields None for that row —
    same "gaps don't get invented data" rule as sma()/rsi(). Returns
    (mid, upper, lower) lists, each aligned with the input.
    """
    n = len(values)
    mid = [None] * n
    upper = [None] * n
    lower = [None] * n
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1]
        if any(v is None for v in window):
            continue
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / period  # population (ddof=0)
        std = variance ** 0.5
        mid[i] = mean
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
    return mid, upper, lower


def rsi(values, period):
    """Wilder's RSI — smoothed average gain/loss, not a naive rolling mean."""
    out = [None] * len(values)
    if len(values) <= period:
        return out

    start = next((i for i in range(1, len(values))
                  if values[i] is not None and values[i - 1] is not None), None)
    if start is None:
        return out

    gains, losses = [], []
    for i in range(start, min(start + period, len(values))):
        if values[i] is None or values[i - 1] is None:
            return out
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    if len(gains) < period:
        return out

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    idx = start + period - 1

    def rsi_value():
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    out[idx] = rsi_value()

    for i in range(idx + 1, len(values)):
        if values[i] is None or values[i - 1] is None:
            continue
        change = values[i] - values[i - 1]
        avg_gain = ((avg_gain * (period - 1)) + max(change, 0)) / period
        avg_loss = ((avg_loss * (period - 1)) + max(-change, 0)) / period
        out[i] = rsi_value()

    return out


def atr(rows, period):
    """
    Wilder's ATR (Average True Range), computed from candle rows (needs
    high/low/close, not just a close series like sma()/rsi()).

    True range at row i is max(high-low, |high-prev_close|,
    |low-prev_close|) — the first fully-valid row after a data gap has no
    usable prev_close, so it falls back to just high-low for that one row.
    A zero-filled gap row (tick_count == 0) has no true range of its own
    (treated as None, not a fake near-zero range), and doesn't advance
    prev_close either — same "gaps don't get invented data" rule the OHLC
    loader itself follows.
    """
    n = len(rows)
    out = [None] * n
    tr = [None] * n
    prev_close = None

    for i, r in enumerate(rows):
        if r["tick_count"] == 0:
            continue
        high, low, close = r["high"], r["low"], r["close"]
        tr[i] = high - low if prev_close is None else max(high - low, abs(high - prev_close), abs(low - prev_close))
        prev_close = close

    start = next((i for i in range(n) if tr[i] is not None), None)
    if start is None:
        return out

    window = []
    i = start
    while i < n and len(window) < period:
        if tr[i] is None:
            return out  # a gap inside the initial window — same bail-out rsi() uses
        window.append(tr[i])
        i += 1
    if len(window) < period:
        return out

    avg = sum(window) / period
    idx = start + period - 1
    out[idx] = avg

    for j in range(idx + 1, n):
        if tr[j] is None:
            continue
        avg = ((avg * (period - 1)) + tr[j]) / period
        out[j] = avg

    return out
