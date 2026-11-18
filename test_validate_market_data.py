import unittest
from datetime import datetime, timezone
from validate_market_data import validate

def sample():
    candles = [{"open_time": i*60000, "close_time": i*60000+59999, "open":1.0,"high":2.0,"low":0.5,"close":1.5,"volume":10.0} for i in range(300)]
    return {"generated_at":"2026-11-18T07:00:00+00:00","symbols":{
      s: {"spot_price":{"price":100.0,"source":"Binance Spot: https://data-api.binance.vision","source_status":"ok","price_authority":"BINANCE"},
          "timeframes":{tf:{"source_status":"ok","exchange":"OKX USDT Swap","candles":candles} for tf in ("1d","12h","4h","1h","15m","5m","1m")},
          "futures_context":{"funding_rate":{"status":"unavailable"},"open_interest":{"value":1000.0,"source":"OKX"},"global_long_short_ratio":{"status":"unavailable"}}}
      for s in ("BTCUSDT","ETHUSDT")}}

class MarketDataValidationTests(unittest.TestCase):
    def test_valid_data_allows_optional_derivatives_missing(self):
        d=sample()
        out=validate(d, datetime(2026,11,18,7,1,tzinfo=timezone.utc))
        self.assertEqual(out["overall"], "ok")
        self.assertFalse(out["symbols"]["BTCUSDT"]["derivatives"]["funding_rate"]["available"])
    def test_missing_price_fails(self):
        d=sample(); d["symbols"]["ETHUSDT"]["spot_price"]["price"]=None
        with self.assertRaises(ValueError): validate(d, datetime(2026,11,18,7,1,tzinfo=timezone.utc))
    def test_binance_authority_must_match_source(self):
        d=sample(); d["symbols"]["BTCUSDT"]["spot_price"]["source"]="OKX"
        with self.assertRaises(ValueError): validate(d, datetime(2026,11,18,7,1,tzinfo=timezone.utc))
    def test_unclosed_candle_fails(self):
        d=sample(); d["symbols"]["BTCUSDT"]["timeframes"]["1m"]["candles"][-1]["close_time"]=int(datetime(2026,11,18,7,1,tzinfo=timezone.utc).timestamp()*1000)
        with self.assertRaises(ValueError): validate(d, datetime(2026,11,18,7,1,tzinfo=timezone.utc))
    def test_insufficient_timeframes_fails(self):
        d=sample()
        for tf in ("1d","12h","4h","1h","15m"): d["symbols"]["ETHUSDT"]["timeframes"][tf]["source_status"]="unavailable"
        with self.assertRaises(ValueError): validate(d, datetime(2026,11,18,7,1,tzinfo=timezone.utc))
if __name__ == "__main__": unittest.main()
