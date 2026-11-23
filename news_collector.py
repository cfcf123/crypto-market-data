"""Seven-day public RSS news collector. Headlines are triage, never trade signals."""
import re, time, urllib.request, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote

TIMEOUT=5
WINDOW_HOURS=168
BASE="https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en"
TOPICS=[
("crypto_market","crypto","(Bitcoin OR BTC OR Ethereum OR ETH) (market OR regulation OR exchange OR stablecoin) when:7d"),
("etf_flows","etf","(spot Bitcoin ETF OR Ethereum ETF OR crypto ETF) (inflows OR outflows OR approval OR flows) when:7d"),
("fed_macro","fed","(Federal Reserve OR Fed OR FOMC OR inflation OR CPI OR jobs OR Treasury yields OR dollar) when:7d"),
("us_policy","us_policy","(Trump OR White House OR US Congress) (tariff OR sanctions OR crypto OR China OR regulation) when:7d"),
("geopolitics","geopolitics","(war OR ceasefire OR sanctions OR Taiwan OR Middle East) (markets OR oil OR trade) when:7d"),
("ai_semiconductors","ai","(Nvidia OR Jensen Huang OR semiconductor OR AI chip) when:7d"),
("exchange_industry","exchange","(Binance OR CZ OR CoinGlass OR crypto exchange) (announcement OR investigation OR outage OR liquidation OR regulation) when:7d")]
FEEDS=[{"id":i,"category":c,"url":BASE.format(quote(q))} for i,c,q in TOPICS]+[
{"id":"federal_reserve_official","category":"fed_official","url":"https://www.federalreserve.gov/feeds/press_all.xml"},
{"id":"sec_official","category":"regulatory_official","url":"https://www.sec.gov/news/pressreleases.rss"},
{"id":"whitehouse_official","category":"us_policy_official","url":"https://www.whitehouse.gov/feed/"}]

def _txt(node,tag):
 x=node.find(tag)
 return re.sub(r"\\s+"," ",unescape("".join(x.itertext()))).strip() if x is not None else ""

def _date(s):
 if not s:return None
 try:
  d=parsedate_to_datetime(s)
  if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
  return d.astimezone(timezone.utc)
 except Exception:
  try:
   d=datetime.fromisoformat(s.replace("Z","+00:00"))
   return d.replace(tzinfo=d.tzinfo or timezone.utc).astimezone(timezone.utc)
  except Exception:return None

def _fetch(feed,now):
 t=time.monotonic()
 try:
  req=urllib.request.Request(feed["url"],headers={"User-Agent":"crypto-market-data/4.0","Accept":"application/rss+xml,application/atom+xml,application/xml"})
  with urllib.request.urlopen(req,timeout=TIMEOUT) as r:raw=r.read(1200000)
  root=ET.fromstring(raw);items=root.findall(".//item")
  if not items:items=root.findall(".//{http://www.w3.org/2005/Atom}entry")
  out=[]
  for x in items[:60]:
   title=_txt(x,"title");link=_txt(x,"link")
   if not link:
    ln=x.find("{http://www.w3.org/2005/Atom}link")
    if ln is not None:link=ln.attrib.get("href","")
   d=_date(_txt(x,"pubDate") or _txt(x,"published") or _txt(x,"updated"))
   if not title or not link or not d:continue
   age=(now-d).total_seconds()/3600
   if age < -3 or age > WINDOW_HOURS:continue
   out.append({"title":title[:500],"url":link,"publisher":_txt(x,"source") or feed["id"],
    "published_at":d.isoformat(),"age_hours":round(max(0,age),2),"category":feed["category"],
    "feed_id":feed["id"],"summary":(_txt(x,"description") or _txt(x,"summary"))[:1000]})
  return {"feed_id":feed["id"],"category":feed["category"],"status":"ok","articles_found":len(out),
   "elapsed_ms":round((time.monotonic()-t)*1000),"articles":out}
 except Exception as e:
  return {"feed_id":feed["id"],"category":feed["category"],"status":"unavailable","error":str(e)[:250],
   "elapsed_ms":round((time.monotonic()-t)*1000),"articles":[]}

def _priority(title):
 s=title.lower()
 if any(k in s for k in ("reinstat","resign","resignation","war ","invasion","rate decision","fed decision","etf approved","hack","exploit","bankruptcy","default","sanction")):return "critical"
 if any(k in s for k in ("nvidia","jensen huang","federal reserve","fomc","cpi","inflation","tariff","trump","bitcoin etf","ethereum etf","binance","liquidation","taiwan","china")):return "high"
 return "normal"

def collect_news(now=None):
 now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
 with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
  futures=[pool.submit(_fetch,f,now) for f in FEEDS]
  results=[f.result() for f in as_completed(futures)]
 results.sort(key=lambda x:x["feed_id"]);seen=set();articles=[]
 for f in results:
  for a in f["articles"]:
   key=re.sub(r"[^a-z0-9]+","",a["title"].lower())
   if key in seen:continue
   seen.add(key);a["priority"]=_priority(a["title"]);articles.append(a)
 articles.sort(key=lambda a:a["published_at"],reverse=True)
 ok=sum(x["status"]=="ok" for x in results)
 return {"status":"ok" if ok else "unavailable","collected_at":now.isoformat(),"window_hours":WINDOW_HOURS,
  "source_count":len(FEEDS),"sources_ok":ok,"sources_failed":len(FEEDS)-ok,"article_count":len(articles),
  "feeds":[{k:v for k,v in x.items() if k!="articles"} for x in results],"articles":articles[:100],
  "policy":{"priority":"keyword triage only, not factual severity or directional score",
   "impact":"analyst must assess BTC and ETH transmission separately; headlines never auto-generate trades",
   "limitations":["RSS/index coverage is not exhaustive","timestamps/summaries may be delayed",
    "economic calendar and live ETF flow datasets require separate structured sources"]}}
