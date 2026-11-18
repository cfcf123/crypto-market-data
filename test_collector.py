import unittest
import collector


class FuturesContextValidationTests(unittest.TestCase):
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

    def test_okx_long_short_ratio(self):
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

    def test_all_timeframe_provider_mappings_exist(self):
        for tf in collector.INTERVALS:
            self.assertIn(tf, collector.BYBIT_INTERVAL)
            self.assertIn(tf, collector.OKX_BAR)

    def test_normalize_excludes_open_candle(self):
        now_ms = 119999
        rows = [[0, "1", "2", "0.5", "1.5", "10"], [60000, "1.5", "2.5", "1", "2", "11"]]
        out = collector.normalize(rows, "test", "1m", now_ms, bybit=True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["open_time"], 0)

if __name__ == "__main__":
    unittest.main()
