import unittest
from wyckoff import analyze


def candles(rows):
    return [{"open": o, "high": h, "low": l, "close": c, "volume": v}
            for o, h, l, c, v in rows]


class WyckoffTests(unittest.TestCase):
    def test_insufficient_data(self):
        self.assertEqual(analyze(candles([(1, 2, 0, 1, 10)]))["status"],
                         "insufficient_data")

    def test_spring_candidate_requires_reclaim(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        data[-1] = {"open": 96, "high": 101, "low": 94, "close": 100, "volume": 150}
        out = analyze(data)
        self.assertTrue(out["events"]["spring_candidate"])
        self.assertFalse(out["events"]["utad_candidate"])
        self.assertEqual(out["phase"], "spring_candidate_waiting_confirmation")

    def test_utad_candidate_requires_failure_back_inside(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        data[-1] = {"open": 104, "high": 107, "low": 99, "close": 100, "volume": 150}
        out = analyze(data)
        self.assertTrue(out["events"]["utad_candidate"])
        self.assertEqual(out["phase"], "utad_candidate_waiting_confirmation")

    def test_sos_requires_breakout_and_volume(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        data[-1] = {"open": 104, "high": 107, "low": 103, "close": 106, "volume": 150}
        out = analyze(data)
        self.assertTrue(out["events"]["sos_candidate"])
        self.assertEqual(out["phase"], "strength_confirmation")

    def test_breakout_without_volume_is_not_sos(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        data[-1] = {"open": 104, "high": 107, "low": 103, "close": 106, "volume": 100}
        out = analyze(data)
        self.assertFalse(out["events"]["sos_candidate"])

    def test_range_location_alone_does_not_claim_accumulation(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        data[-1] = {"open": 96, "high": 97, "low": 94, "close": 95, "volume": 100}
        out = analyze(data)
        self.assertIn("accumulation_watch", out["phase_candidates"])
        self.assertEqual(out["phase"], "trading_range_or_unclassified")

    def test_no_spring_required(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        out = analyze(data)
        self.assertFalse(out["events"]["spring_candidate"])
        self.assertFalse(out["events"]["utad_candidate"])
        self.assertEqual(out["status"], "ok")

    def test_invalid_ohlcv_rejected(self):
        data = candles([(100, 95, 105, 100, 100)] * 42)
        self.assertEqual(analyze(data)["status"], "invalid_data")

    def test_no_trade_signal_generated(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        out = analyze(data)
        self.assertNotIn("entry", out)
        self.assertNotIn("trade_direction", out)


if __name__ == "__main__":
    unittest.main()
