#!/usr/bin/env python3
"""Public BTCUSDT/ETHUSDT market collector. No credentials or trading permissions."""
import json, os, time, urllib.request
from datetime import datetime, timezone

TIMEOUT = 8
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1d", "12h", "4h", "1h", "15m", "5m"]
PRICE_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com",
 "https://api-gcp.binance.com", "https://api1.binance.com", "https://api2.binance.com",
 "https://api3.binance.com", "https://api4.binance.com"]

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"crypto-market-data/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status != 200: raise RuntimeError("HTTP "+str(r.status))
        return json.loads(r.read().decode("utf-8"))

def fetch_price(symbol):
    errors=[]
    for host in PRICE_HOSTS:
        try:
            d=get_json(host+"/api/v3/ticker/price?symbol="+symbol)
            p=float(d["price"])
            if d.get("symbol") != symbol or p <= 0: raise ValueError("symbol/price validation failed")
            return {"price":p,"source":host,"observed_at":datetime.now(timezone.utc).isoformat()}
        except Exception as e: errors.append({"host":host,"error":str(e)})
    return {"error":"all Binance Spot price endpoints failed","attempts":errors}

def fetch_klines(symbol, interval, limit=500):
    errors=[]
    try:
        rows=get_json("https://fapi.binance.com/fapi/v1/klines?symbol="+symbol+"&interval="+interval+"&limit="+str(limit))
        if not isinstance(rows,list) or len(rows)<30: raise ValueError("insufficient kline rows")
        now=int(time.time()*1000); out=[]
        for r in rows:
            if int(r[6]) < now:
                out.append({"open_time":int(r[0]),"open":float(r[1]),"high":float(r[2]),
                 "low":float(r[3]),"close":float(r[4]),"volume":float(r[5]),"close_time":int(r[6])})
        if len(out)<30: raise ValueError("insufficient closed candles")
        return {"exchange":"Binance USD-M Futures","interval":interval,"requested":limit,
         "received":len(rows),"closed_count":len(out),
         "last_closed_utc":datetime.fromtimestamp(out[-1]["close_time"]/1000,timezone.utc).isoformat(),
         "candles":out}
    except Exception as e:
        errors.append({"host":"https://fapi.binance.com","error":str(e)})
    return {"error":"Binance Futures klines unavailable","interval":interval,"attempts":errors}

def ema(values, period):
    if len(values)<period:return None
    x=sum(values[:period])/period; alpha=2/(period+1)
    for z in values[period:]: x=alpha*z+(1-alpha)*x
    return x

def rsi(values, period=14):
    if len(values)<=period:return None
    ds=[values[i]-values[i-1] for i in range(1,len(values))]
    up=sum(max(x,0) for x in ds[:period])/period
    dn=sum(max(-x,0) for x in ds[:period])/period
    for x in ds[period:]:
        up=(up*(period-1)+max(x,0))/period
        dn=(dn*(period-1)+max(-x,0))/period
    return 100 if dn==0 else 100-100/(1+up/dn)

def indicators(candles):
    c=[x["close"] for x in candles]; h=[x["high"] for x in candles]; l=[x["low"] for x in candles]
    tr=[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,len(c))]
    mid=sum(c[-20:])/20 if len(c)>=20 else None
    sd=(sum((x-mid)**2 for x in c[-20:])/20)**0.5 if mid is not None else None
    macd_series=[]
    for i in range(25,len(c)):
        macd_series.append(ema(c[:i+1],12)-ema(c[:i+1],26))
    return {"ema20":ema(c,20),"ema50":ema(c,50),"ema200":ema(c,200),
     "rsi14":rsi(c),"macd":macd_series[-1] if macd_series else None,
     "macd_signal9":ema(macd_series,9) if len(macd_series)>=9 else None,
     "bollinger20":{"middle":mid,"upper":mid+2*sd if mid is not None else None,
                    "lower":mid-2*sd if mid is not None else None},
     "atr14":sum(tr[-14:])/14 if len(tr)>=14 else None,
     "swing_high_20":max(h[-20:]) if len(h)>=20 else None,
     "swing_low_20":min(l[-20:]) if len(l)>=20 else None}

def futures_context(symbol):
    paths={"funding_rate":"/fapi/v1/fundingRate?symbol="+symbol+"&limit=1",
     "open_interest":"/fapi/v1/openInterest?symbol="+symbol,
     "global_long_short_ratio":"/futures/data/globalLongShortAccountRatio?symbol="+symbol+"&period=1h&limit=1"}
    out={}
    for key,path in paths.items():
        try: out[key]=get_json("https://fapi.binance.com"+path)
        except Exception as e: out[key]={"error":str(e)}
    return out

def main():
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"collector_version":"1.0",
     "disclaimer":"Public market data only; not financial advice; no trading actions.","symbols":{}}
    for symbol in SYMBOLS:
        item={"spot_price":fetch_price(symbol),"futures_context":futures_context(symbol),"timeframes":{}}
        for tf in INTERVALS:
            k=fetch_klines(symbol,tf)
            if "candles" in k:k["indicators"]=indicators(k["candles"])
            item["timeframes"][tf]=k
        result["symbols"][symbol]=item
    os.makedirs("output",exist_ok=True)
    with open("output/market-data.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    warnings=[]
    for symbol,item in result["symbols"].items():
        if "error" in item["spot_price"]:warnings.append(symbol+" Spot price unavailable")
        if not any("candles" in x for x in item["timeframes"].values()):warnings.append(symbol+" all kline intervals unavailable")
    print(json.dumps({"output":"output/market-data.json","generated_at":result["generated_at"],"warnings":warnings}))
    if warnings:raise SystemExit(1)

if __name__=="__main__":main()
