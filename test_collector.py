import unittest
import collector


class FuturesContextValidationTests(unittest.TestCase):
    def test_binance_funding_valid(self):
        data = [{"fundingRate": "0.0001"}]
        self.assertEqual(collector.validate_context_response("Binance USD-M Futures", "funding_rate", data), data)

    def test_binance_http_200_error_payload_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_context_response("Binance USD-M Futures", "open_interest", {"code": -1003, "msg": "rate limited"})

    def test_bybit_retcode_error_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_context_response("Bybit V5 Linear", "funding_rate", {"retCode": 10006, "retMsg": "too many visits", "result": {}})

    def test_bybit_valid_open_interest(self):
        data = {"retCode": 0, "result": {"list": [{"openInterest": "123.4"}]}}
        self.assertEqual(collector.validate_context_response("Bybit V5 Linear", "open_interest", data), data)

    def test_okx_code_error_rejected(self):
        with self.assertRaises(ValueError):
            collector.validate_context_response("OKX USDT Swap", "funding_rate", {"code": "50011", "msg": "rate limit", "data": []})

    def test_okx_valid_open_interest(self):
        data = {"code": "0", "data": [{"oi": "321.0"}]}
        self.assertEqual(collector.validate_context_response("OKX USDT Swap", "open_interest", data), data)

    def test_first_ok_falls_back_after_invalid_payload(self):
        calls = [
            ("Binance USD-M Futures", lambda: {"code": -1003, "msg": "blocked"}),
            ("Bybit V5 Linear", lambda: {"retCode": 0, "result": {"list": [{"openInterest": "10"}]}}),
        ]
        result = collector.first_ok(calls, "open_interest")
        self.assertEqual(result["source"], "Bybit V5 Linear")
        self.assertEqual(result["data"]["result"]["list"][0]["openInterest"], "10")
        self.assertEqual(len(result.get("attempts", [])), 0)


if __name__ == "__main__":
    unittest.main()
