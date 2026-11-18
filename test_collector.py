import unittest
import collector


class FuturesContextValidationTests(unittest.TestCase):
    def test_binance_global_long_short_uses_documented_fapi_endpoint(self):
        from unittest.mock import patch
        payload = [{"symbol": "BTCUSDT", "longShortRatio": "1.2", "longAccount": "0.5454", "shortAccount": "0.4546", "timestamp": 1}]
        with patch("collector.binance_fapi_get", return_value=payload) as request:
            result = collector.fetch_binance_global_long_short_ratio("BTCUSDT")
        request.assert_called_once_with("/futures/data/globalLongShortAccountRatio", {"symbol": "BTCUSDT", "period": "1h", "limit": 1})
        normalized = collector.validate_context_response("Binance USD-M Futures", "global_long_short_ratio", result)
        self.assertAlmostEqual(normalized["value"], 1.2)

    def test_binance_funding_normalized(self):
        data = [{"fundingRate": "0.0001"}]
        out = collector.validate_context_response("Binance USD-M Futures", "funding_rate", data)
        self.assertEqual(out["value"], 0.0001)
        self.assertEqual(out["raw"], data)

    def test_binance_http_200_error_payload_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_context_response("Binance USD-M Futures", "open_interest", {"code": -1003, "msg": "rate limited"})

    def test_bybit_retcode_error_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_context_response("Bybit V5 Linear", "funding_rate", {"retCode": 10006, "retMsg": "too many visits", "result": {}})

    def test_bybit_valid_open_interest(self):
        data = {"retCode": 0, "result": {"list": [{"openInterest": "123.4"}]}}
        out = collector.validate_context_response("Bybit V5 Linear", "open_interest", data)
        self.assertEqual(out["value"], 123.4)

    def test_bybit_long_short_ratio_normalized(self):
        data = {"retCode": 0, "result": {"list": [{"buyRatio": "0.6", "sellRatio": "0.4"}]}}
        out = collector.validate_context_response("Bybit V5 Linear", "global_long_short_ratio", data)
        self.assertAlmostEqual(out["value"], 1.5)

    def test_okx_code_error_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_context_response("OKX USDT Swap", "funding_rate", {"code": "50011", "msg": "rate limit", "data": []})

    def test_okx_valid_open_interest_usd(self):
        data = {"code": "0", "data": [{"oi": "321.0", "oiUsd": "98765.4"}]}
        out = collector.validate_context_response("OKX USDT Swap", "open_interest", data)
        self.assertEqual(out["value"], 98765.4)

    def test_okx_long_short_ratio_array_response(self):
        # Official OKX Rubik API returns each data row as [ts, ratio].
        data = {"code": "0", "data": [["1794988800000", "1.25"]]}
        out = collector.validate_context_response("OKX USDT Swap", "global_long_short_ratio", data)
        self.assertEqual(out["value"], 1.25)
        self.assertEqual(out["raw"], data)

    def test_okx_long_short_ratio_legacy_object_response(self):
        data = {"code": "0", "data": [{"ratio": "1.25"}]}
        out = collector.validate_context_response("OKX USDT Swap", "global_long_short_ratio", data)
        self.assertEqual(out["value"], 1.25)

    def test_invalid_non_finite_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_context_response("Binance USD-M Futures", "funding_rate", [{"fundingRate": "nan"}])

    def test_first_ok_falls_back_after_invalid_payload(self):
        calls = [
            ("Binance USD-M Futures", lambda: {"code": -1003, "msg": "blocked"}),
            ("Bybit V5 Linear", lambda: {"retCode": 0, "result": {"list": [{"openInterest": "10"}]}}),
        ]
        result = collector.first_ok(calls, "open_interest")
        self.assertEqual(result["source"], "Bybit V5 Linear")
        self.assertEqual(result["value"], 10.0)
        self.assertEqual(len(result.get("attempts", [])), 0)

    def test_daily_history_lookback_is_extended_for_monthly_analysis(self):
        self.assertEqual(collector.KLINE_LIMITS["1d"], 800)
        self.assertGreater(collector.KLINE_LIMITS["1d"], 500)

    def test_all_timeframe_provider_mappings_exist(self):
        for tf in collector.INTERVALS:
            self.assertIn(tf, collector.BYBIT_INTERVAL)
            self.assertIn(tf, collector.OKX_BAR)

    def test_okx_daily_history_paginates_older_closed_candles(self):
        from unittest.mock import patch
        day = 86400000
        def row(open_time):
            return [str(open_time), "100", "105", "95", "102", "10", "1020", "0", "1"]
        current = {"code":"0","data":[row(4*day),row(3*day)]}
        history = {"code":"0","data":[row(2*day),row(day),row(0)]}
        with patch("collector.get_json", side_effect=[current, history]) as request:
            candles = collector.fetch_okx_klines("BTCUSDT", "1d", limit=5)
        self.assertEqual(len(candles), 5)
        self.assertEqual([x["open_time"] for x in candles], [0,day,2*day,3*day,4*day])
        self.assertIn("/api/v5/market/history-candles?", request.call_args_list[1].args[0])

    def test_normalize_excludes_open_candle(self):
        now_ms = 119999
        rows = [[0, "1", "2", "0.5", "1.5", "10"], [60000, "1.5", "2.5", "1", "2", "11"]]
        out = collector.normalize(rows, "test", "1m", now_ms, bybit=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["open_time"], 0)

class CollectionTimestampTests(unittest.TestCase):
    def test_generated_at_is_collection_completion_time(self):
        from datetime import datetime, timezone
        started = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        completed = datetime(2026, 11, 18, 12, 3, tzinfo=timezone.utc)
        payload = {"collection_started_at": started.isoformat()}
        result = collector.mark_collection_complete(payload, completed)
        self.assertEqual(result["generated_at"], completed.isoformat())
        self.assertEqual(result["collection_completed_at"], completed.isoformat())
        self.assertEqual(result["collection_started_at"], started.isoformat())


if __name__ == "__main__":
    unittest.main()
