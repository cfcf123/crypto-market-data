import unittest
from wyckoff import analyze


def candles(rows):
    return [{"open":o,"high":h,"low":l,"close":c,"volume":v}
            for o,h,l,c,v in rows]


class WyckoffTests(unittest.TestCase):
    def test_insufficient_data(self):
        self.assertEqual(analyze(candles([(1,2,0,1,10)]))["status"], "insufficient_data")

    def test_spring_candidate_requires_reclaim(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        data[-1] = {"open":96,"high":101,"low":94,"close":100,"volume":80}
        out = analyze(data)
        self.assertTrue(out["events"]["spring_candidate"])
        self.assertFalse(out["events"]["utad_candidate"])

    def test_utad_candidate_requires_failure_back_inside(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        data[-1] = {"open":104,"high":107,"low":99,"close":100,"volume":80}
        out = analyze(data)
        self.assertTrue(out["events"]["utad_candidate"])

    def test_no_spring_required(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        out = analyze(data)
        self.assertFalse(out["events"]["spring_candidate"])
        self.assertFalse(out["events"]["utad_candidate"])
        self.assertEqual(out["status"], "ok")

    def test_no_trade_signal_generated(self):
        data = candles([(100, 105, 95, 100, 100)] * 42)
        out = analyze(data)
        self.assertNotIn("entry", out)
        self.assertNotIn("trade_direction", out)


if __name__ == "__main__":
    unittest.main()
