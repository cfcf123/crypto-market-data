import unittest
from datetime import datetime, timezone
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
        item = make_item("bull")
        item["timeframes"]["4h"]["indicators"] = dict(item["timeframes"]["4h"]["indicators"])
        item["timeframes"]["4h"]["indicators"]["ema20"] = 95.0
        result = analyze_symbol(item)
        levels = result["levels"]
        self.assertEqual(levels["status"], "conditional")
        self.assertGreater(levels["long"]["entry_trigger"], levels["reference_price"])
        self.assertLess(levels["long"]["stop_loss"], levels["long"]["entry_trigger"])
        self.assertGreater(levels["long"]["take_profit_2"], levels["long"]["take_profit_1"])
        self.assertLess(levels["short"]["entry_trigger"], levels["reference_price"])
        self.assertGreater(levels["short"]["stop_loss"], levels["short"]["entry_trigger"])
        self.assertIn("已收盘K线", levels["long"]["condition"])
        self.assertEqual(levels["pullback_long"]["status"], "conditional")
        self.assertEqual(levels["rebound_short"]["status"], "conditional")
        self.assertLess(levels["pullback_long"]["entry_zone"][1], levels["reference_price"])
        self.assertGreater(levels["rebound_short"]["entry_zone"][0], levels["reference_price"])
        self.assertLess(levels["pullback_long"]["stop_loss"], levels["pullback_long"]["entry_zone"][0])
        self.assertGreater(levels["rebound_short"]["stop_loss"], levels["rebound_short"]["entry_zone"][1])
        self.assertIn("结构支撑", levels["pullback_long"]["structure_basis"])
        self.assertIn("结构压力", levels["rebound_short"]["structure_basis"])

    def test_ema20_is_not_a_hard_veto_for_either_left_side_setup(self):
        item = make_item("bear")
        item["timeframes"]["4h"]["indicators"] = dict(item["timeframes"]["4h"]["indicators"])
        item["timeframes"]["4h"]["indicators"]["ema20"] = 105.0
        levels = analyze_symbol(item)["levels"]
        self.assertEqual(levels["pullback_long"]["status"], "conditional")
        self.assertEqual(levels["rebound_short"]["status"], "conditional")
        self.assertLess(levels["pullback_long"]["entry_zone"][1], levels["reference_price"])
        self.assertGreater(levels["rebound_short"]["entry_zone"][0], levels["reference_price"])
        self.assertGreater(levels["rebound_short"]["stop_loss"], levels["rebound_short"]["entry_zone"][1])
        self.assertIn("EMA20/EMA50仅参与评分", levels["rebound_short"]["structure_basis"])

    def test_left_side_requires_real_structure_and_rejects_missing_levels(self):
        item=make_item("bear")
        item["timeframes"]["4h"]["indicators"]=dict(item["timeframes"]["4h"]["indicators"])
        item["timeframes"]["4h"]["indicators"]["swing_high_20"]=100.2
        item["timeframes"]["4h"]["indicators"]["swing_low_20"]=99.8
        levels=analyze_symbol(item)["levels"]
        self.assertEqual(levels["pullback_long"]["status"],"unavailable")
        self.assertEqual(levels["rebound_short"]["status"],"unavailable")

    def test_old_candle_close_is_not_used_as_live_exchange_basis(self):
        item = make_item("bull")
        stamp = datetime.now(timezone.utc).isoformat()
        item["spot_price"].update({"observed_at":stamp,
            "cross_exchange":[{"source":"OKX USDT Swap","price":100.1,"observed_at":stamp}]})
        levels = analyze_symbol(item)["levels"]
        self.assertEqual(levels["source_last_close"], 110.0)
        self.assertAlmostEqual(levels["reference_basis_difference_pct"], 0.1, places=3)
        self.assertTrue(levels["execution_allowed"])
        self.assertEqual(levels["execution_status"], "allowed")
        self.assertIsNone(levels["basis_warning"])
        self.assertAlmostEqual(levels["atr14"], 2.0)

    def test_same_time_live_basis_over_half_percent_pauses_execution(self):
        item = make_item("bull")
        stamp = datetime.now(timezone.utc).isoformat()
        item["spot_price"].update({"observed_at":stamp,
            "cross_exchange":[{"source":"OKX USDT Swap","price":100.6,"observed_at":stamp}]})
        levels = analyze_symbol(item)["levels"]
        self.assertFalse(levels["execution_allowed"])
        self.assertEqual(levels["execution_status"], "paused_basis_mismatch")
        self.assertGreater(levels["reference_basis_difference_pct"], 0.5)
        self.assertIsNotNone(levels["basis_warning"])

    def test_missing_live_ticker_timestamp_pauses_as_unverified(self):
        item = make_item("bull")
        stamp = datetime.now(timezone.utc).isoformat()
        item["spot_price"].update({"observed_at":stamp,
            "cross_exchange":[{"source":"OKX USDT Swap","price":100.1}]})
        levels = analyze_symbol(item)["levels"]
        self.assertFalse(levels["execution_allowed"])
        self.assertEqual(levels["execution_status"], "paused_basis_unverified")

    def test_derivatives_crowded_longs_add_only_small_bearish_tilt(self):
        item = make_item("bull")
        item["futures_context"] = {
            "funding_rate": {"value": 0.0002, "source": "test"},
            "global_long_short_ratio": {"value": 2.0, "source": "test"},
            "open_interest": {"value": 1000000.0, "unit": "USD", "source": "test"},
        }
        result = analyze_symbol(item)
        self.assertEqual(result["derivatives_adjustment"], -0.04)
        self.assertIn("open_interest", result["derivatives_context"])
        self.assertTrue(any("OI仅作" in note for note in result["derivatives_notes"]))

    def test_derivatives_crowded_shorts_add_only_small_bullish_tilt(self):
        item = make_item("bear")
        item["futures_context"] = {
            "funding_rate": {"value": -0.0002, "source": "test"},
            "global_long_short_ratio": {"value": 0.5, "source": "test"},
        }
        result = analyze_symbol(item)
        self.assertEqual(result["derivatives_adjustment"], 0.04)

    def test_open_interest_alone_does_not_change_direction_score(self):
        baseline = analyze_symbol(make_item("bull"))
        item = make_item("bull")
        item["futures_context"] = {
            "open_interest": {"value": 999999999.0, "unit": "USD", "source": "test"}
        }
        with_oi = analyze_symbol(item)
        self.assertEqual(with_oi["derivatives_adjustment"], 0.0)
        self.assertEqual(with_oi["evidence_score"], baseline["evidence_score"])

    def test_r_multiples_are_present_for_all_conditional_setups(self):
        for direction in ("bull", "bear"):
            levels = analyze_symbol(make_item(direction))["levels"]
            for key in ("long", "short"):
                rr = levels[key]["risk_reward"]
                self.assertEqual(rr["status"], "calculated")
                self.assertAlmostEqual(rr["tp1_r"], 1.0, places=3)
                self.assertAlmostEqual(rr["tp2_r"], 1.667, places=3)
            for key in ("pullback_long", "rebound_short"):
                if levels[key]["status"] == "conditional":
                    self.assertEqual(levels[key]["risk_reward"]["status"], "calculated")
                    self.assertGreater(levels[key]["risk_reward"]["tp1_r"], 0)
                    self.assertGreater(levels[key]["risk_reward"]["tp2_r"], 0)

    def test_four_strategy_weights_and_no_trade_sum_to_100(self):
        for direction in ("bull", "bear"):
            result = analyze_symbol(make_item(direction))
            weights = result["strategy_weights_pct"]
            self.assertEqual(set(weights), {
                "left_pullback_long", "right_breakout_long",
                "left_rebound_short", "right_breakdown_short", "no_trade"
            })
            self.assertAlmostEqual(sum(weights.values()), 100.0, places=1)
            self.assertEqual(weights, result["levels"]["strategy_weights_pct"])
            self.assertAlmostEqual(
                weights["left_pullback_long"] + weights["right_breakout_long"]
                + weights["left_rebound_short"] + weights["right_breakdown_short"]
                + weights["no_trade"], 100.0, places=9
            )

    def test_strategy_weights_are_attached_to_each_setup(self):
        result = analyze_symbol(make_item("bull"))
        levels = result["levels"]
        self.assertEqual(
            levels["pullback_long"]["strategy_weight_pct"],
            result["strategy_weights_pct"]["left_pullback_long"]
        )
        self.assertEqual(
            levels["long"]["strategy_weight_pct"],
            result["strategy_weights_pct"]["right_breakout_long"]
        )
        self.assertEqual(
            levels["rebound_short"]["strategy_weight_pct"],
            result["strategy_weights_pct"]["left_rebound_short"]
        )
        self.assertEqual(
            levels["short"]["strategy_weight_pct"],
            result["strategy_weights_pct"]["right_breakdown_short"]
        )

    def test_missing_left_structure_gets_zero_left_strategy_weight(self):
        item = make_item("bear")
        item["timeframes"]["4h"]["indicators"] = dict(item["timeframes"]["4h"]["indicators"])
        item["timeframes"]["4h"]["indicators"]["swing_high_20"] = 100.2
        item["timeframes"]["4h"]["indicators"]["swing_low_20"] = 99.8
        result = analyze_symbol(item)
        self.assertEqual(result["strategy_weights_pct"]["left_pullback_long"], 0.0)
        self.assertEqual(result["strategy_weights_pct"]["left_rebound_short"], 0.0)
        self.assertGreater(result["strategy_weights_pct"]["no_trade"], 0.0)

    def test_missing_authoritative_price_keeps_analysis_and_weights_without_levels(self):
        item = make_item("bull")
        item["spot_price"] = {
            "source_status": "unavailable",
            "price_authority": "BINANCE_USDM_PERPETUAL_REQUIRED",
            "error": "Binance USD-M endpoint unavailable"
        }
        result = analyze_symbol(item)
        self.assertEqual(result["levels"]["status"], "unavailable")
        self.assertAlmostEqual(sum(result["strategy_weights_pct"].values()), 100.0, places=1)
        self.assertEqual(result["strategy_weights_pct"]["left_pullback_long"], 0.0)
        self.assertEqual(result["strategy_weights_pct"]["left_rebound_short"], 0.0)

    def test_dataset_missing_symbol_is_explicit(self):
        result = analyze_dataset({"symbols": {"BTCUSDT": make_item()}})
        self.assertEqual(result["symbols"]["ETHUSDT"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()


class NvdaCrossAssetTests(unittest.TestCase):
    def test_dataset_includes_nvda_and_explicit_linkage(self):
        from decision_engine import analyze_dataset
        result = analyze_dataset({"symbols": {
            "BTCUSDT": make_item("bull"),
            "ETHUSDT": make_item("bear"),
            "NVDAUSDT": make_item("bull")
        }})
        self.assertIn("NVDAUSDT", result["symbols"])
        self.assertEqual(result["symbols"]["NVDAUSDT"]["asset_type"], "NVDAUSDT equity perpetual")
        self.assertEqual(result["symbols"]["NVDAUSDT"]["market_data_source"], "Binance Spot")
        self.assertIn("Binance Spot", result["symbols"]["NVDAUSDT"]["market_session_context"]["asset"])
        self.assertIn("NVDAUSDT_vs_BTCUSDT", result["cross_asset_linkage"]["pairs"])
        self.assertIn("NVDAUSDT_vs_ETHUSDT", result["cross_asset_linkage"]["pairs"])


    def test_strong_countertrend_rebound_reduces_bearish_direction_weight(self):
        baseline = analyze_symbol(make_item("bear"))
        item = make_item("bear")
        for tf in ("4h", "1h", "15m"):
            candles = item["timeframes"][tf]["candles"]
            for offset in range(7):
                close = 90.0 + offset * 2.0
                candles[-7 + offset].update({
                    "open": close - 0.5, "high": close + 1.0,
                    "low": close - 1.0, "close": close
                })
            item["timeframes"][tf]["indicators"].update({
                "atr14": 2.0, "rsi14": 68.0,
                "macd": 2.0, "macd_signal9": -1.0
            })
        rebound = analyze_symbol(item)
        self.assertGreater(
            rebound["category_scores"]["rebound_strength"],
            baseline["category_scores"]["rebound_strength"]
        )
        self.assertLess(
            rebound["weights_pct"]["short"],
            baseline["weights_pct"]["short"]
        )
        self.assertEqual(rebound["direction_model"], "balanced_categories_v1")
