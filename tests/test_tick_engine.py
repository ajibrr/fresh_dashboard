"""
Unit tests for the shared tick-to-trade engine (app.features.tick_engine).

The engine is the chart-validated reference implementation, so these tests
pin its *current* semantics (regression lock) rather than aspirational
behavior:

- build_candles: full-window bucket tiling, OHLC resampling, zero-filled
  gaps, OI-flow window join + carry-forward across buckets.
- signals/filters: pattern gating, OI side selection, entry-condition
  3-candle window.
- run_trades: one-trade-at-a-time overlap skipping; empty/flat inputs
  produce no trades.
- sma: reference window-sum SMA agrees with the O(n) rolling-sum
  implementation in app.features.indicators on gapless input.
- Real-data parity: on the repo's actual input data the engine must
  reproduce, trade for trade, the JSON trade table embedded in the
  committed chart.html - the lock between engine and chart.

Run: python -m unittest tests.test_tick_engine -v
"""
import json
import re
import unittest
from pathlib import Path

from app.features import tick_engine as te
from app.features.indicators import sma as rolling_sma

REPO = Path(__file__).resolve().parents[1]
INPUT = REPO / "input data"
CHART = REPO / "chart.html"
TIMEFRAMES = [("12sec", 12), ("1min", 60), ("3min", 180), ("5min", 300)]


def row(time, open_, high, low, close, ticks=1, cum_ce=None, cum_pe=None):
    return {
        "date": "2026-01-01",
        "time": time,
        "open": open_, "high": high, "low": low, "close": close,
        "tick_count": ticks,
        "cum_ce": cum_ce, "cum_pe": cum_pe,
    }


def gap_row(time):
    return row(time, 0.0, 0.0, 0.0, 0.0, ticks=0)


class SmaTests(unittest.TestCase):
    def test_basic_and_warmup(self):
        s = te.sma([1.0, 2, 3, 4, 5], 3)
        self.assertEqual(s[:2], [None, None])
        self.assertEqual(s[2:], [2.0, 3.0, 4.0])

    def test_gap_yields_none_until_window_clears_it(self):
        # series: [1, None, 3, 4, 5, 6]; windows containing the None
        # (i=1..3) get None, from i=4 (window 3,4,5) values resume
        s = te.sma([1.0, None, 3.0, 4.0, 5.0, 6.0], 3)
        self.assertIsNone(s[1])
        self.assertIsNone(s[2])
        self.assertIsNone(s[3])
        self.assertEqual(s[4], 4.0)
        self.assertEqual(s[5], 5.0)

    def test_matches_rolling_implementation_on_gapless_series(self):
        vals = [100 + (i * 7 % 23) / 3.0 for i in range(200)]
        for period in (9, 44):
            pairs = [(a, b) for a, b in zip(te.sma(vals, period), rolling_sma(vals, period))
                     if a is not None and b is not None]
            self.assertAlmostEqual(0.0, max(abs(a - b) for a, b in pairs), places=9)


class BuildCandlesTests(unittest.TestCase):
    def test_resamples_ohlc_and_tiles_full_window(self):
        # 10-second candles from per-second ticks inside 09:15:00-09:15:06
        def ts(sec):
            return "2026-01-05 09:15:%02d" % sec

        ticks = [(te.parse_ts(ts(0)), 100.0, 0.0),
                 (te.parse_ts(ts(2)), 102.0, 0.0),   # high
                 (te.parse_ts(ts(4)), 98.0, 0.0),    # low
                 (te.parse_ts(ts(5)), 101.0, 0.0)]   # close
        rows = te.build_candles(ticks, [], "2026-01-05", 10)
        # the full 09:15-15:30 window is tiled: (6h15m * 60) / 10 = 2250 buckets
        self.assertEqual(len(rows), 2250)
        self.assertEqual(rows[0]["time"], "09:15:00")
        self.assertEqual(rows[0]["open"], 100.0)
        self.assertEqual(rows[0]["high"], 102.0)
        self.assertEqual(rows[0]["low"], 98.0)
        self.assertEqual(rows[0]["close"], 101.0)
        self.assertEqual(rows[0]["tick_count"], 4)
        # bucket starting 09:15:10 has no ticks -> zero-filled gap
        self.assertEqual(rows[1]["time"], "09:15:10")
        self.assertEqual(rows[1]["tick_count"], 0)
        self.assertEqual(rows[1]["close"], 0.0)
        # every later bucket is empty too (all ticks fell in the first one)
        self.assertTrue(all(r["tick_count"] == 0 for r in rows[1:]))
        self.assertEqual(rows[-1]["time"], "15:29:50")

    def test_flow_join_window_and_carry_forward(self):
        # 60s candles; flow rows land mid-bucket
        flow = [(te.parse_ts("2026-01-05 09:15:30"), {"cumulative_ce": 10, "cumulative_pe": 20}),
                (te.parse_ts("2026-01-05 09:16:30"), {"cumulative_ce": 11, "cumulative_pe": 22})]
        ticks = [(te.parse_ts("2026-01-05 09:15:00"), 100.0, 0.0)]
        rows = te.build_candles(ticks, flow, "2026-01-05", 60)
        # 09:15 candle: the 09:15:30 flow row is inside its window
        self.assertEqual(rows[0]["cum_ce"], 10)
        self.assertEqual(rows[0]["cum_pe"], 20)
        # 09:16 candle: the 09:16:30 flow row is inside its window
        self.assertEqual(rows[1]["cum_ce"], 11)
        self.assertEqual(rows[1]["cum_pe"], 22)
        # 09:17 candle: nothing inside its window; the last seen row
        # carries forward (documented semantics)
        self.assertEqual(rows[2]["cum_ce"], 11)
        self.assertEqual(rows[2]["cum_pe"], 22)

    def test_candle_without_any_flow_gets_none(self):
        ticks = [(te.parse_ts("2026-01-05 09:15:00"), 100.0, 0.0)]
        rows = te.build_candles(ticks, [], "2026-01-05", 60)
        self.assertIsNone(rows[0]["cum_ce"])
        self.assertIsNone(rows[0]["cum_pe"])


class SignalTests(unittest.TestCase):
    def test_long_signal_gated_by_flat_history(self):
        # flat candles: SMA9 == SMA44 and SMA44 slope is 0, so even a
        # breakout close above SMA9 must NOT fire (slope/pattern gating)
        rows = [row("09:15:%02d" % i, 49.0, 51.0, 48.0, 50.0) for i in range(12)]
        rows[-1] = row("09:15:11", 50.0, 52.0, 49.0, 51.0)
        s9 = te.sma([r["close"] for r in rows], 9)
        s44 = te.sma([r["close"] for r in rows], 44)
        self.assertFalse(te.pine_long(rows, (s9, s44), len(rows) - 1))
        self.assertFalse(te.pine_short(rows, (s9, s44), len(rows) - 1))

    def test_signal_fails_on_gap_inside_pattern_window(self):
        rows = [row("09:15:%02d" % i, 49.0, 51.0, 48.0, 50.0) for i in range(12)]
        rows[3] = gap_row("09:15:03")
        s9 = te.sma([r["close"] if r["tick_count"] else None for r in rows], 9)
        s44 = te.sma([r["close"] if r["tick_count"] else None for r in rows], 44)
        self.assertFalse(te.pine_long(rows, (s9, s44), len(rows) - 1))
        self.assertFalse(te.pine_short(rows, (s9, s44), len(rows) - 1))

    def test_oi_filter_sides(self):
        rows = [row("09:15:00", 1, 2, 0, 1, cum_ce=100, cum_pe=50)]
        self.assertTrue(te.oi_ok(rows, 0, "SHORT"))
        self.assertFalse(te.oi_ok(rows, 0, "LONG"))
        rows = [row("09:15:00", 1, 2, 0, 1, cum_ce=50, cum_pe=100)]
        self.assertTrue(te.oi_ok(rows, 0, "LONG"))
        self.assertFalse(te.oi_ok(rows, 0, "SHORT"))
        rows = [row("09:15:00", 1, 2, 0, 1)]  # no flow data at all
        self.assertFalse(te.oi_ok(rows, 0, "LONG"))
        self.assertFalse(te.oi_ok(rows, 0, "SHORT"))

    def test_entry_condition_window_is_three_candles(self):
        rows = [row("09:15:%02d" % i, 50, 51, 49, 50.0) for i in range(12)]
        # synthetic SMA: flat 50 everywhere, so closes 49/49.5/49.9 stay
        # below it; only candles i+1..i+3 (indices 12,13,14) may trigger
        s9 = [50.0] * 20
        rows += [row("09:15:12", 50, 51, 49, 49.0),
                 row("09:15:13", 50, 51, 49, 49.5),
                 row("09:15:14", 50, 51, 49, 49.9),
                 row("09:15:15", 50, 51, 49, 40.0)]
        self.assertIsNone(te.entry_cond_candle(rows, s9, 11, "LONG"))
        # SHORT re-cross (close below SMA) fires at the first in-window candle
        self.assertEqual(te.entry_cond_candle(rows, s9, 11, "SHORT"), 12)
        # a close above SMA at i+2 (index 13) is found for LONG
        rows[13] = row("09:15:13", 50, 51, 49, 51.0)
        self.assertEqual(te.entry_cond_candle(rows, s9, 11, "LONG"), 13)
        # all in-window candles above SMA -> no SHORT trigger; a crossing
        # close below SMA at i+4 (index 15) is OUTSIDE the window
        for j in (12, 13, 14):
            rows[j] = row("09:15:%02d" % j, 50, 51, 49, 55.0)
        rows[15] = row("09:15:15", 50, 51, 49, 20.0)
        self.assertIsNone(te.entry_cond_candle(rows, s9, 11, "SHORT"))

    def test_entry_condition_skips_gap_candles(self):
        rows = [row("09:15:%02d" % i, 50, 51, 49, 50.0) for i in range(12)]
        s9 = [50.0] * 20
        rows += [gap_row("09:15:12"),
                 row("09:15:13", 50, 51, 49, 60.0)]
        # i+1 is a zero-filled gap: the crossing candle at i+2 is still found
        self.assertEqual(te.entry_cond_candle(rows, s9, 11, "LONG"), 13)


class RunTradesTests(unittest.TestCase):
    def _engine_over(self, rows):
        s9, s44 = te.features_for(rows)
        return te.run_trades(rows, s9, s44, "LONG"), te.run_trades(rows, s9, s44, "SHORT")

    def test_no_trades_on_empty_rows(self):
        longs, shorts = self._engine_over([])
        self.assertEqual((longs, shorts), ([], []))

    def test_no_trades_on_flat_data(self):
        # flat prices: SMA9 == SMA44, slope gating blocks every signal
        rows = [row("09:15:%02d" % i, 50.0, 50.5, 49.5, 50.0, cum_ce=10, cum_pe=100)
                for i in range(60)]
        longs, shorts = self._engine_over(rows)
        self.assertEqual((longs, shorts), ([], []))


class ParityTests(unittest.TestCase):
    """Lock the engine to the trade table embedded in the committed chart.html."""

    @staticmethod
    def _embedded_trades():
        m = re.search(r"var CHARTS=.*?,TRADES=(\{.*?\}),DAYS=", CHART.read_text(encoding="utf-8"))
        if not m:
            raise AssertionError("embedded TRADES JSON not found in chart.html")
        return json.loads(m.group(1))

    @staticmethod
    def _engine_trades():
        out = {}
        for path in sorted(INPUT.glob("NIFTY_*_DASHBOARD.json")):
            date = path.stem[6:10] + "-" + path.stem[10:12] + "-" + path.stem[12:14]
            ticks, flow, _ = te.load_ticks(INPUT, date)
            for label, tf_sec in TIMEFRAMES:
                rows = te.build_candles(ticks, flow, date, tf_sec)
                s9, s44 = te.features_for(rows)
                key = date + "|" + label
                out[key] = []
                for direction in ("LONG", "SHORT"):
                    for t in te.run_trades(rows, s9, s44, direction):
                        out[key].append({"direction": direction, **t})
        return out

    @unittest.skipUnless(INPUT.exists(), "input data not present")
    @unittest.skipUnless(CHART.exists(), "chart.html not present")
    def test_engine_reproduces_chart_html_trades(self):
        embedded = self._embedded_trades()
        engine = self._engine_trades()
        self.assertEqual(sorted(engine), sorted(embedded), "chart keys changed")

        def sig(trades):
            return [(t["direction"], t["entry_time"], t["entry_price"],
                     t["stop_price"], t["exit_price"], t["outcome"], t["pnl"])
                    for t in trades]

        diffs = []
        for k in embedded:
            if sig(engine[k]) != sig(embedded[k]):
                diffs.append((k, sig(embedded[k]), sig(engine[k])))
        self.assertEqual(diffs, [],
                         "engine output diverges from the committed chart trade table")

        total = sum(len(v) for v in engine.values())
        self.assertEqual(total, 19)
        self.assertEqual(sum(1 for v in engine.values() for t in v if t["direction"] == "LONG"), 10)
        self.assertEqual(sum(1 for v in engine.values() for t in v if t["direction"] == "SHORT"), 9)


if __name__ == "__main__":
    unittest.main()
