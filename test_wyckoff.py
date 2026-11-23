import unittest
from wyckoff import analyze


def candles(rows):
    return [{"open":o,"high":h,"low":l,"close":c,"volume":v} for o,h,l,c,v in rows]


class WyckoffTests(unittest.TestCase):
    def test_insufficient_data(self):
        self.assertEqual(analyze(candles([(1,2,0,1,10)]))["status"],"insufficient_data")

    def test_spring_candidate_requires_reclaim(self):
        d=candles([(100,105,95,100,100)]*42)
        d[-1]={"open":96,"high":101,"low":94,"close":100,"volume":150}
        o=analyze(d)
        self.assertTrue(o["events"]["spring_candidate"])
        self.assertEqual(o["phase"],"spring_candidate_waiting_confirmation")

    def test_utad_candidate(self):
        d=candles([(100,105,95,100,100)]*42)
        d[-1]={"open":104,"high":107,"low":99,"close":100,"volume":150}
        self.assertTrue(analyze(d)["events"]["utad_candidate"])

    def test_sos_requires_volume_spread_and_close_near_high(self):
        d=candles([(100,105,95,100,100)]*42)
        d[-1]={"open":104,"high":118,"low":103,"close":117,"volume":250}
        o=analyze(d)
        self.assertTrue(o["events"]["sos_candidate"])
        self.assertEqual(o["phase"],"sos_waiting_lps_confirmation")

    def test_breakout_without_volume_is_not_sos(self):
        d=candles([(100,105,95,100,100)]*42)
        d[-1]={"open":104,"high":118,"low":103,"close":117,"volume":100}
        self.assertFalse(analyze(d)["events"]["sos_candidate"])

    def test_lps_sequence_confirmation(self):
        d=candles([(100,105,95,100,100)]*40)
        d += candles([(104,118,103,117,250),(107,111,104.5,106,100),(107,113,106,112,110)])
        o=analyze(d)
        self.assertTrue(o["events"]["lps_confirmed"])
        self.assertEqual(o["phase"],"lps_confirmed")

    def test_lpsy_sequence_confirmation(self):
        d=candles([(100,105,95,100,100)]*40)
        d += candles([(101,102,82,83,250),(93,95,82,94,100),(94,95,80,81,110)])
        o=analyze(d)
        self.assertTrue(o["events"]["lpsy_confirmed"])
        self.assertEqual(o["phase"],"lpsy_confirmed")

    def test_range_location_alone_not_accumulation(self):
        d=candles([(100,105,95,100,100)]*42)
        d[-1]={"open":96,"high":97,"low":94,"close":95,"volume":100}
        o=analyze(d)
        self.assertIn("accumulation_watch",o["phase_candidates"])
        self.assertEqual(o["phase"],"trading_range_or_unclassified")

    def test_no_spring_required(self):
        o=analyze(candles([(100,105,95,100,100)]*42))
        self.assertFalse(o["events"]["spring_candidate"])
        self.assertEqual(o["status"],"ok")

    def test_squeeze_not_claimed_without_series(self):
        o=analyze(candles([(100,105,95,100,100)]*42))
        self.assertEqual(o["squeeze_assessment"]["status"],"unverified")

    def test_invalid_ohlcv(self):
        self.assertEqual(analyze(candles([(100,95,105,100,100)]*42))["status"],"invalid_data")

    def test_no_trade_signal_generated(self):
        o=analyze(candles([(100,105,95,100,100)]*42))
        self.assertNotIn("entry",o)
        self.assertNotIn("trade_direction",o)


if __name__=="__main__":
    unittest.main()
