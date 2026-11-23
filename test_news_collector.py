import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import news_collector
class NewsTests(unittest.TestCase):
 def test_nvidia_reinstatement_critical(self):
  self.assertEqual(news_collector._priority("NVIDIA Board Reinstates Jensen Huang as CEO"),"critical")
 def test_fed_cpi_high(self):
  self.assertEqual(news_collector._priority("Federal Reserve CPI outlook"),"high")
 def test_failures_disclosed(self):
  now=datetime(2026,11,23,tzinfo=timezone.utc)
  with patch("news_collector._fetch",side_effect=lambda f,n:{"feed_id":f["id"],"category":f["category"],"status":"unavailable","error":"offline","elapsed_ms":1,"articles":[]}):
   r=news_collector.collect_news(now)
  self.assertEqual(r["sources_failed"],r["source_count"])
  self.assertEqual(r["status"],"unavailable")
 def test_deduplication(self):
  now=datetime(2026,11,23,tzinfo=timezone.utc)
  a={"title":"NVIDIA Board Reinstates Jensen Huang","url":"https://x","publisher":"x","published_at":now.isoformat(),"age_hours":0,"category":"ai","feed_id":"x","summary":""}
  with patch("news_collector._fetch",side_effect=lambda f,n:{"feed_id":f["id"],"category":f["category"],"status":"ok","articles_found":1,"elapsed_ms":1,"articles":[dict(a)]}):
   r=news_collector.collect_news(now)
  self.assertEqual(r["article_count"],1)
if __name__=="__main__":unittest.main()
