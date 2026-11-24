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


class HttpRetryPolicyTests(unittest.TestCase):
    def test_permanent_http_error_is_not_retried(self):
        from unittest.mock import patch
        import urllib.error
        error = urllib.error.HTTPError("https://example.test", 451, "Unavailable", {}, None)
        with patch("collector.urllib.request.urlopen", side_effect=error) as request:
            with self.assertRaises(urllib.error.HTTPError):
                collector.get_json("https://example.test")
        request.assert_called_once()

    def test_timeout_retries_only_once(self):
        from unittest.mock import patch
        with patch("collector.urllib.request.urlopen", side_effect=TimeoutError("slow")) as request, \
             patch("collector.time.sleep") as sleep:
            with self.assertRaises(TimeoutError):
                collector.get_json("https://example.test")
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_successful_json_is_returned_without_retry(self):
        from unittest.mock import patch
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"ok":true}'
        with patch("collector.urllib.request.urlopen", return_value=Response()) as request:
            self.assertEqual(collector.get_json("https://example.test"), {"ok":True})
        request.assert_called_once()


class NvdaPerpetualPriceTests(unittest.TestCase):
    def test_nvda_reference_uses_binance_usdm_perpetual_ticker_not_spot(self):
        from unittest.mock import patch
        payload = {"symbol":"NVDAUSDT","price":"150.25"}
        with patch("collector.get_json", return_value=payload) as request, \
             patch("collector.validate_price_cross_exchange", return_value=[]) as cross:
            result = collector.fetch_perpetual_price("NVDAUSDT")
        self.assertIn("/fapi/v1/ticker/price?", request.call_args.args[0])
        self.assertEqual(result["price"], 150.25)
        self.assertEqual(result["price_authority"], "BINANCE_USDM_PERPETUAL")
        self.assertEqual(result["reference_price_type"], "perpetual_contract_last_price")
        self.assertIn("perpetual ticker", result["source"])
        cross.assert_called_once_with("NVDAUSDT", 150.25)

    def test_nvda_falls_back_to_okx_perpetual_after_binance_is_blocked(self):
        from unittest.mock import patch
        import urllib.error
        blocked=urllib.error.HTTPError("https://fapi.binance.com",451,"Unavailable",{},None)
        okx={"code":"0","data":[{"instId":"NVDA-USDT-SWAP","last":"151.75"}]}
        with patch("collector.get_json", side_effect=[blocked, okx]) as request, \
             patch("collector.validate_price_cross_exchange", return_value=[]):
            result=collector.fetch_perpetual_price("NVDAUSDT")
        self.assertEqual(result["price"],151.75)
        self.assertEqual(result["price_authority"],"OKX_USDT_SWAP_PERPETUAL")
        self.assertEqual(result["reference_price_type"],"perpetual_contract_last_price")
        self.assertIn("OKX USDT Swap perpetual ticker",result["source"])
        self.assertEqual(request.call_count,2)

    def test_nvda_is_in_collected_symbol_set(self):
        self.assertIn("NVDAUSDT", collector.SYMBOLS)


class NvdaCrossVenueTickerTests(unittest.TestCase):
    def test_nvda_cross_venue_comparison_never_uses_eth_ticker(self):
        from unittest.mock import patch
        requested = []
        def fake_get_json(url, retries=collector.MAX_HTTP_ATTEMPTS, timeout=collector.TIMEOUT):
            requested.append(url)
            if "bybit.com" in url:
                return {"result":{"list":[{"lastPrice":"150.0"}]}}
            return {"data":[{"last":"150.0"}]}
        with patch("collector.get_json", side_effect=fake_get_json):
            checks = collector.validate_price_cross_exchange("NVDAUSDT", 150.0)
        self.assertTrue(any("symbol=NVDAUSDT" in url for url in requested))
        self.assertTrue(any("instId=NVDA-USDT-SWAP" in url for url in requested))
        self.assertFalse(any("ETH-USDT-SWAP" in url for url in requested))
        self.assertEqual(len(checks), 2)
