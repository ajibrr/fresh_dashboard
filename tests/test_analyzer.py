import unittest
from unittest import mock

import app.analyzer
from app.strategy.features import build_features
from app.analyzer import (
    _analyze_day,
    _find_entry_candle,
    StrategyAnalyzer,
)


def make_rows(closes, tick_count=1):
    """Candles from a close series; O/H/L derived around each close
    (open = close-1, high = close+2, low = close-2)."""
    rows = []
    for idx, close in enumerate(closes):
        if tick_count == 0:
            o = h = l = c = 0.0
            n = 0
        else:
            o = close - 1.0
            h = close + 2.0
            l = close - 2.0
            c = close
            n = tick_count
        rows.append({
            "date": "2026-09-18",
            "time": f"{9 + (15 + idx) // 60:02d}:{(15 + idx) % 60:02d}:00",
            "timestamp": f"2026-09-18 {9 + (15 + idx) // 60:02d}:{(15 + idx) % 60:02d}:00",
            "open": o, "high": h, "low": l, "close": c,
            "tick_count": n,
            "cumulative_ce": None, "cumulative_pe": None,
            "ce_oi_change": None, "pe_oi_change": None,
        })
    return rows


def run_sim(rows, direction, trigger_indices, sma_period=3, window=3, rr_multiples=(2.0, 3.0, 4.0)):
    """Run _analyze_day with the condition layer stubbed: candles whose
    index is in trigger_indices are the only triggers. This isolates the
    trigger -> entry-candle -> exit orchestration from the (independently
    unchanged) condition evaluators."""
    config = {
        "strategy": {
            "entry_candle": {"sma_period": sma_period, "window_candles": window},
            "entry": {direction: {"conditions": []}},
            "feature_periods": {"sma": [sma_period], "rsi": [14], "atr": [14]},
        },
        "analysis": {"rr_multiples": list(rr_multiples)},
    }
    features = build_features(rows, config["strategy"])
    with mock.patch.object(app.analyzer, "evaluate_all",
                           side_effect=lambda c, r, f, i: i in trigger_indices):
        return _analyze_day(
            rows, features, direction, [],
            list(rr_multiples), {}, 12, "12sec", "test", "default",
            {"sma_period": sma_period, "window_candles": window},
        )


class TestFindEntryCandle(unittest.TestCase):
    def setUp(self):
        self.features = {"sma_3": [None, None, None, 100.0, 100.0, 100.0, 100.0, 100.0]}

    def test_first_close_above_sma_within_window(self):
        rows = make_rows([95, 96, 97, 99, 101, 100, 100, 100])
        self.assertEqual(_find_entry_candle(rows, 3, "LONG", self.features, 3, 3), 4)

    def test_close_below_sma_never_qualifies_for_long(self):
        rows = make_rows([95, 96, 97, 101, 99, 99, 99, 99])
        self.assertIsNone(_find_entry_candle(rows, 3, "LONG", self.features, 3, 3))

    def test_trigger_candle_itself_excluded(self):
        rows = make_rows([95, 96, 97, 105, 99, 99, 99, 99])
        # candle 3 is above the SMA but the window starts at candle 4
        self.assertIsNone(_find_entry_candle(rows, 3, "LONG", self.features, 3, 3))

    def test_window_cuts_off_too_late_close(self):
        rows = make_rows([95, 96, 97, 99, 99, 99, 99, 105])
        # candle 7 is above the SMA but sits outside the 3-candle window (4, 5, 6)
        self.assertIsNone(_find_entry_candle(rows, 3, "LONG", self.features, 3, 3))

    def test_short_qualifies_on_close_below_sma(self):
        rows = make_rows([105, 104, 103, 101, 99, 100, 100, 100])
        self.assertEqual(_find_entry_candle(rows, 3, "SHORT", self.features, 3, 3), 4)

    def test_data_gap_candle_cannot_be_entry(self):
        rows = make_rows([95, 96, 97, 100, 105, 100, 100, 100])
        rows[4]["tick_count"] = 0
        # candle 4 would qualify but is a data gap; candles 5-6 are back below
        self.assertIsNone(_find_entry_candle(rows, 3, "LONG", self.features, 3, 3))


class TestLongSimulation(unittest.TestCase):
    def test_entry_at_entry_candle_close_and_stop_at_its_low(self):
        # trigger at 3; candle 4 closes 105 vs SMA 101.33 -> entry candle
        # entry=105 (close), stop=103 (its low), then price falls -> stop hit
        rows = make_rows([95, 96, 97, 99, 105, 103, 101, 100, 99])
        rows_out = run_sim(rows, "LONG", trigger_indices={3})
        self.assertEqual(len(rows_out), 3)  # one row per R:R
        for trade in rows_out:
            self.assertEqual(trade["trigger_time"], rows[3]["time"])
            self.assertEqual(trade["entry_candle_time"], rows[4]["time"])
            self.assertEqual(trade["entry_price"], 105.0)
            self.assertEqual(trade["stop_price"], 103.0)
            self.assertEqual(trade["outcome"], "Stop Loss")
        by_rr = {t["rr_multiple"]: t for t in rows_out}
        self.assertEqual(by_rr[2.0]["target_price"], 109.0)  # entry + 2 * risk(2)

    def test_no_entry_when_window_closes_without_qualifying(self):
        # trigger at 3; candles 4-6 never close above SMA(3)
        rows = make_rows([95, 96, 97, 99, 98, 97, 96, 95])
        rows_out = run_sim(rows, "LONG", trigger_indices={3})
        self.assertEqual(len(rows_out), 1)
        self.assertEqual(rows_out[0]["outcome"], "No Entry")
        self.assertIsNone(rows_out[0]["entry_price"])
        self.assertIsNone(rows_out[0]["rr_multiple"])
        self.assertEqual(rows_out[0]["trigger_time"], rows[3]["time"])

    def test_target_hit_at_2r_and_3r(self):
        # entry candle 4: close=105, low=103, risk=2
        # 2R target 109, 3R target 111 -> candle 5 high 112 hits both
        # 4R target 113 -> never reached -> End Of Data
        rows = make_rows([95, 96, 97, 99, 105, 110, 110, 110, 110])
        rows_out = run_sim(rows, "LONG", trigger_indices={3})
        by_rr = {t["rr_multiple"]: t for t in rows_out}
        self.assertEqual(by_rr[2.0]["outcome"], "Target")
        self.assertEqual(by_rr[3.0]["outcome"], "Target")
        self.assertEqual(by_rr[4.0]["outcome"], "End Of Data")
        self.assertEqual(by_rr[2.0]["exit_price"], 109.0)
        self.assertEqual(by_rr[4.0]["exit_price"], rows[-1]["close"])

    def test_zero_risk_entry_is_skipped(self):
        rows = make_rows([95, 96, 97, 99, 105, 106, 107, 108, 109])
        rows[4]["low"] = rows[4]["close"]  # degenerate candle: risk = 0
        rows_out = run_sim(rows, "LONG", trigger_indices={3})
        self.assertEqual(len(rows_out), 1)
        self.assertEqual(rows_out[0]["outcome"], "Zero Risk — Skipped")
        self.assertIsNone(rows_out[0]["rr_multiple"])

    def test_data_gap_trigger_candle_is_skipped(self):
        rows = make_rows([95, 96, 97, 99, 105, 106, 107, 108, 109])
        rows[3]["tick_count"] = 0
        rows_out = run_sim(rows, "LONG", trigger_indices={3})
        self.assertEqual(rows_out, [])

    def test_exit_walk_starts_after_entry_candle(self):
        # entry candle's own low equals the stop by definition — it must
        # NOT count as a stop-out (no Stop Loss outcome). Entry at 105,
        # risk 2: 2R=109 and 3R=111 are reached by the later highs, 4R=113
        # never is -> mix of Target and End Of Data.
        rows = make_rows([95, 96, 97, 99, 105, 107, 108, 109, 110])
        rows_out = run_sim(rows, "LONG", trigger_indices={3}, rr_multiples=(2.0, 3.0, 4.0))
        outcomes = {t["rr_multiple"]: t["outcome"] for t in rows_out}
        self.assertNotIn("Stop Loss", outcomes.values())
        self.assertEqual(outcomes[2.0], "Target")
        self.assertEqual(outcomes[3.0], "Target")
        self.assertEqual(outcomes[4.0], "End Of Data")


class TestShortSimulation(unittest.TestCase):
    def test_mirror_entry_stop_and_target(self):
        # trigger at 3; candle 4 closes 95 vs SMA 98.67 -> SHORT entry
        # entry=95 (close), stop=97 (its high), 2R target=91; price then
        # rises through 97 -> stop hit for every R:R
        rows = make_rows([105, 104, 103, 101, 95, 99, 100, 101, 102])
        rows_out = run_sim(rows, "SHORT", trigger_indices={3})
        self.assertEqual(len(rows_out), 3)
        trade = rows_out[0]
        self.assertEqual(trade["direction"], "SHORT")
        self.assertEqual(trade["entry_candle_time"], rows[4]["time"])
        self.assertEqual(trade["entry_price"], 95.0)
        self.assertEqual(trade["stop_price"], 97.0)
        self.assertEqual(trade["outcome"], "Stop Loss")
        by_rr = {t["rr_multiple"]: t for t in rows_out}
        self.assertEqual(by_rr[2.0]["target_price"], 91.0)  # entry - 2 * risk(2)

    def test_short_target_hit(self):
        # entry candle 4: close=95, high=97, risk=2; 2R target=91
        rows = make_rows([105, 104, 103, 101, 95, 91, 90, 89, 88])
        rows_out = run_sim(rows, "SHORT", trigger_indices={3}, rr_multiples=(2.0,))
        self.assertEqual(len(rows_out), 1)
        self.assertEqual(rows_out[0]["outcome"], "Target")
        self.assertEqual(rows_out[0]["exit_price"], 91.0)


class TestDedup(unittest.TestCase):
    def test_dedup_prefers_resolved_target_over_eod(self):
        base = {
            "timeframe_seconds": 12, "date": "2026-09-18", "trigger_time": "09:20:00",
            "direction": "LONG", "entry_price": 100.0, "stop_price": 98.0,
            "entry_candle_time": "09:21:00", "variant": "default", "pnl_points": 4.0,
        }
        eod = {**base, "rr_multiple": 4.0, "outcome": "End Of Data", "exit_price": 104.0}
        target = {**base, "rr_multiple": 4.0, "outcome": "Target", "exit_price": 108.0}
        deduped = StrategyAnalyzer._dedup_trades([eod, target])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["outcome"], "Target")

    def test_dedup_keeps_distinct_triggers_separate(self):
        base = {
            "timeframe_seconds": 12, "date": "2026-09-18", "direction": "LONG",
            "entry_price": 100.0, "stop_price": 98.0, "entry_candle_time": "09:21:00",
            "variant": "default", "rr_multiple": 2.0, "outcome": "Target", "pnl_points": 4.0,
        }
        a = {**base, "trigger_time": "09:20:00"}
        b = {**base, "trigger_time": "10:20:00"}
        self.assertEqual(len(StrategyAnalyzer._dedup_trades([a, b])), 2)


if __name__ == "__main__":
    unittest.main()
