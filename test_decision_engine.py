import unittest
from decision_engine import analyze_symbol, analyze_dataset


def make_item(direction="bull", available=None):
    available = set(available or ("1M", "1w", "1d", "12h", "4h", "1h", "15m"))
    item = {"spot_price": {"price": 100.0, "source": "Binance Spot"},
            "timeframes": {}, "higher_timeframes": {}}
    bull = direction == "bull"
    metrics = {
        "ema20": 105.0 if bull else 95.0,
        "ema50": 103.0 if bull else 97.0,
        "ema200": 99.0 if bull else 101.0,
        "rsi14": 65.0 if bull else 35.0,
        "macd": 2.0 if bull else -2.0,
        "macd_signal9": 1.0 if bull else -1.0,
        "atr14": 2.0, "swing_high_20": 110.0, "swing_low_20": 90.0,
    }
    candles = [{"open": 99.0, "high": 101.0, "low": 98.0,
                "close": 110.0 if bull else 90.0, "volume": 10.0,
                "open_time": i * 60000, "close_time": (i + 1) * 60000 - 1}
               for i in range(220)]
    for tf in ("1M", "1w"):
        if tf in available:
            item["higher_timeframes"][tf] = {"candles": candles}
    for tf in ("1d", "12h", "4h", "1h", "15m"):
        if tf in available:
            item["timeframes"][tf] = {"source_status": "ok", "candles": candles,
                                      "indicators": metrics}
    return item


class DecisionEngineTests(unittest.TestCase):
    def test_weights_always_sum_to_100(self):
        for direction in ("bull", "bear"):
            result = analyze_symbol(make_item(direction))
            self.assertAlmostEqual(sum(result["weights_pct"].values()), 100.0, places=1)

    def test_bullish_evidence_favors_long(self):
        result = analyze_symbol(make_item("bull"))
        self.assertGreater(result["weights_pct"]["long"], result["weights_pct"]["short"])

    def test_bearish_evidence_favors_short(self):
        result = analyze_symbol(make_item("bear"))
        self.assertGreater(result["weights_pct"]["short"], result["weights_pct"]["long"])

    def test_low_timeframe_coverage_increases_neutral_weight(self):
        full = analyze_symbol(make_item("bull"))
        sparse = analyze_symbol(make_item("bull", available=("15m",)))
        self.assertGreater(sparse["weights_pct"]["neutral"], full["weights_pct"]["neutral"])
        self.assertLess(sparse["available_weight_pct"], full["available_weight_pct"])

    def test_conditional_levels_are_ordered_and_marked(self):
        result = analyze_symbol(make_item("bull"))
        levels = result["levels"]
        self.assertEqual(levels["status"], "conditional")
        self.assertGreater(levels["long"]["entry_trigger"], levels["reference_price"])
        self.assertLess(levels["long"]["stop_loss"], levels["long"]["entry_trigger"])
        self.assertGreater(levels["long"]["take_profit_2"], levels["long"]["take_profit_1"])
        self.assertLess(levels["short"]["entry_trigger"], levels["reference_price"])
        self.assertGreater(levels["short"]["stop_loss"], levels["short"]["entry_trigger"])
        self.assertIn("已收盘K线", levels["long"]["condition"])

    def test_levels_scale_candle_structure_to_reference_price_basis(self):
        result = analyze_symbol(make_item("bull"))
        levels = result["levels"]
        self.assertEqual(levels["reference_price"], 100.0)
        self.assertEqual(levels["source_last_close"], 110.0)
        self.assertAlmostEqual(levels["reference_basis_difference_pct"], 9.0909, places=3)
        self.assertIsNotNone(levels["basis_warning"])
        self.assertGreater(levels["long"]["entry_trigger"], levels["reference_price"])

    def test_dataset_missing_symbol_is_explicit(self):
        result = analyze_dataset({"symbols": {"BTCUSDT": make_item()}})
        self.assertEqual(result["symbols"]["ETHUSDT"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
