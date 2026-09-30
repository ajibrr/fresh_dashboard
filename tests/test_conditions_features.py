import unittest

from app.features.indicators import bollinger
from app.strategy.features import build_features
from app.strategy.conditions import evaluate
from app.data.loader import _build_ohlc


class TestBollinger(unittest.TestCase):
    def test_constant_series_has_zero_width_bands(self):
        mid, upper, lower = bollinger([100.0] * 10, 5, 2.0)
        self.assertEqual(mid[6], 100.0)
        self.assertEqual(upper[6], 100.0)
        self.assertEqual(lower[6], 100.0)

    def test_known_values(self):
        # window [1, 2, 3, 4, 5]: mean=3, population variance=2, std=sqrt(2)
        mid, upper, lower = bollinger([1.0, 2.0, 3.0, 4.0, 5.0], 5, 2.0)
        self.assertAlmostEqual(mid[4], 3.0)
        self.assertAlmostEqual(upper[4], 3.0 + 2 * (2 ** 0.5))
        self.assertAlmostEqual(lower[4], 3.0 - 2 * (2 ** 0.5))

    def test_warmup_and_gap_yield_none(self):
        mid, _, _ = bollinger([1.0, 2.0, 3.0, 4.0], 3, 2.0)
        self.assertIsNone(mid[1])  # warmup
        self.assertIsNotNone(mid[2])
        vals = [1.0, 2.0, None, 4.0, 5.0, 6.0]
        mid, upper, lower = bollinger(vals, 3, 2.0)
        for i in (2, 3, 4):  # windows containing the None
            self.assertIsNone(mid[i])
            self.assertIsNone(upper[i])
            self.assertIsNone(lower[i])
        self.assertIsNotNone(mid[5])  # first clean window after the gap


def bb_condition(typ, bb_period, bb_num_std):
    return {"type": typ, "bb_period": bb_period, "bb_num_std": bb_num_std, "enabled": True}


class TestBollingerConditions(unittest.TestCase):
    def setUp(self):
        # closes 0..29; BB(20, 2) at i=29: mean=19.5, population std=sqrt(33.25)
        self.closes = [float(x) for x in range(30)]
        self.rows = []
        for idx, close in enumerate(self.closes):
            self.rows.append({
                "date": "2026-09-18", "time": f"09:{15 + idx:02d}:00",
                "open": close, "high": close, "low": close, "close": close,
                "tick_count": 1,
            })
        self.config = {"entry": {}, "feature_periods": {}}

    def features_for(self, condition):
        config = {"entry": {}, "feature_periods": {},
                  "entry": {"LONG": {"conditions": [condition]}}}
        return build_features(self.rows, config)

    def test_low_below_lower_band(self):
        condition = bb_condition("low_below_bollinger_lower", 20, 2.0)
        features = self.features_for(condition)
        i = 29
        mean = 19.5
        std = (33.25) ** 0.5
        lower = mean - 2 * std
        self.rows[i]["low"] = lower - 1.0   # pierces
        self.assertTrue(evaluate(condition, self.rows, features, i))
        self.rows[i]["low"] = lower + 1.0   # inside the band
        self.assertFalse(evaluate(condition, self.rows, features, i))

    def test_high_above_upper_band(self):
        condition = bb_condition("high_above_bollinger_upper", 20, 2.0)
        features = self.features_for(condition)
        i = 29
        mean = 19.5
        std = (33.25) ** 0.5
        upper = mean + 2 * std
        self.rows[i]["high"] = upper + 1.0  # pierces
        self.assertTrue(evaluate(condition, self.rows, features, i))
        self.rows[i]["high"] = upper - 1.0  # inside the band
        self.assertFalse(evaluate(condition, self.rows, features, i))

    def test_sweep_list_num_std_registers_every_band(self):
        condition = bb_condition("low_below_bollinger_lower", 22, [1.5, 2, 2.5])
        features = self.features_for(condition)
        for ns in (1.5, 2.0, 2.5):
            self.assertIn(f"bb_22_{ns:g}", features)


class TestOICarryForward(unittest.TestCase):
    def _raw(self):
        return {
            "nifty_seconds": [
                {"timestamp": "2026-09-18 09:15:05", "nifty": 100.0},
                {"timestamp": "2026-09-18 09:15:20", "nifty": 101.0},
                {"timestamp": "2026-09-18 09:16:05", "nifty": 102.0},
            ],
            "flow": [
                {"timestamp": "2026-09-18 09:15:00", "cumulative_ce": 10, "cumulative_pe": 20},
                {"timestamp": "2026-09-18 09:17:00", "cumulative_ce": 30, "cumulative_pe": 40},
            ],
        }

    def test_sub_minute_candles_carry_last_known_oi(self):
        rows = _build_ohlc(self._raw(), "2026-09-18", 12)
        by_time = {r["time"]: r for r in rows}
        # candle with its own flow row
        self.assertEqual(by_time["09:15:00"]["cumulative_ce"], 10)
        self.assertEqual(by_time["09:15:00"]["cumulative_pe"], 20)
        # minute-boundary candle 09:16:00 has its own flow row (the 09:16:00
        # flow row doesn't exist, so it carries forward 09:15:00's row)
        self.assertEqual(by_time["09:16:00"]["cumulative_ce"], 10)
        # non-boundary candles carry the last known row forward
        self.assertEqual(by_time["09:15:12"]["cumulative_pe"], 20)
        self.assertEqual(by_time["09:15:48"]["cumulative_pe"], 20)
        # after the 09:17:00 flow row appears, candles from 09:17:00 on see it
        self.assertEqual(by_time["09:17:00"]["cumulative_ce"], 30)
        self.assertEqual(by_time["09:17:24"]["cumulative_pe"], 40)

    def test_no_flow_at_all_stays_none(self):
        raw = self._raw()
        raw["flow"] = []
        rows = _build_ohlc(raw, "2026-09-18", 12)
        self.assertIsNone(rows[0]["cumulative_ce"])
        self.assertIsNone(rows[5]["cumulative_pe"])


if __name__ == "__main__":
    unittest.main()
