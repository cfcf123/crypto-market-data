import unittest
from datetime import datetime, timedelta, timezone
from collector import aggregate_closed_candles


class AggregationTests(unittest.TestCase):
    def make_daily(self, start, count):
        rows = []
        for i in range(count):
            dt = start + timedelta(days=i)
            ot = int(dt.timestamp() * 1000)
            rows.append({"open_time": ot, "close_time": ot + 86400000 - 1,
                         "open": 100+i, "high": 105+i, "low": 95+i,
                         "close": 102+i, "volume": 10})
        return rows

    def test_weekly_ohlcv_aggregation_and_current_week_exclusion(self):
        start = datetime(2026, 1, 5, tzinfo=timezone.utc)  # Monday
        rows = self.make_daily(start, 17)
        now = datetime(2026, 1, 21, tzinfo=timezone.utc)  # Wednesday
        weekly = aggregate_closed_candles(rows, "1w", now)
        self.assertEqual(len(weekly), 2)
        self.assertEqual(weekly[0]["source_days"], 7)
        self.assertEqual(weekly[0]["open"], 100)
        self.assertEqual(weekly[0]["close"], 108)
        self.assertEqual(weekly[0]["volume"], 70)
        self.assertEqual(weekly[1]["source_days"], 7)

    def test_monthly_aggregation_excludes_unfinished_month(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = self.make_daily(start, 59)
        now = datetime(2026, 2, 15, tzinfo=timezone.utc)
        monthly = aggregate_closed_candles(rows, "1M", now)
        self.assertEqual(len(monthly), 1)
        self.assertEqual(monthly[0]["source_days"], 31)
        self.assertEqual(monthly[0]["volume"], 310)

    def test_unsupported_timeframe_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_closed_candles([], "3M", datetime(2026, 1, 1, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
