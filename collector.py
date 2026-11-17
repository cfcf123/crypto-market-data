#!/usr/bin/env python3
"""Public BTCUSDT/ETHUSDT collector. Read-only; no credentials or trading permissions."""
import json, os, time, urllib.request, urllib.parse
from datetime import datetime, timezone

TIMEOUT = 12
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1d", "12h", "4h", "1h", "15m", "5m"]
PRICE_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com",
 "https://api-gcp.binance.com", "https://api1.binance.com", "https://api2.binance.com",
 "https://api3.binance.com", "https://api4.binance.com"]
BYBIT_INTERVAL = {"1d":"D", "12h":"720", "4h":"240", "1h":"60", "15m":"15", "5m":"5"}
OKX_BAR = {"1d":"1D", "12h":"12H", "4h":"4H", "1h":"1H", "15m":"15m", "5m":"5m"}

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"crypto-market-data/2.0","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status != 200: raise RuntimeError("HTTP "+str(r.status))
        data=json.loads(r.read().decode("utf-8"))
    return data

def qs(params):
    return urllib.parse.urlencode(params)

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

def normalize(rows, source, interval, now_ms, bybit=False, okx=False):
    out=[]
    # All normalized rows are chronological and contain closed candles only.
    for r in rows:
        if bybit:
            ot=int(r[0]); ct=ot
            vals=(float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5]))
            closed=ot < now_ms - 1000
        elif okx:
            ot=int(r[0]); ct=ot
            vals=(float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5]))
            closed=(len(r)>8 and str(r[8])=="1")
        else:
            ot=int(r[0]); ct=int(r[6])
            vals=(float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5]))
            closed=ct < now_ms
        if closed:
            o,h,l,c,v=vals
            out.append({"open_time":ot,"open":o,"high":h,"low":l,"close":c,"volume":v,"close_time":ct})
    out.sort(key=lambda x:x["open_time"])
    return out

def fetch_binance_klines(symbol, interval, limit=500):
    url="https://fapi.binance.com/fapi/v1/klines?"+qs({"symbol":symbol,"interval":interval,"limit":limit})
    rows=get_json(url)
    if not isinstance(rows,list): raise ValueError("unexpected Binance response")
    return normalize(rows,"Binance USD-M Futures",interval,int(time.time()*1000))

def fetch_bybit_klines(symbol, interval, limit=500):
    url="https://api.bybit.com/v5/market/kline?"+qs({"category":"linear","symbol":symbol,"interval":BYBIT_INTERVAL[interval],"limit":limit})
    d=get_json(url)
    if d.get("retCode") != 0: raise RuntimeError("Bybit retCode="+str(d.get("retCode"))+" "+str(d.get("retMsg")))
    rows=d.get("result",{}).get("list",[])
    if not rows: raise ValueError("empty Bybit kline response")
    return normalize(rows,"Bybit V5 Linear",interval,int(time.time()*1000),bybit=True)

def fetch_okx_klines(symbol, interval, limit=300):
    inst=symbol.replace("USDT","-USDT-SWAP")
    url="https://www.okx.com/api/v5/market/candles?"+qs({"instId":inst,"bar":OKX_BAR[interval],"limit":str(min(limit,300))})
    d=get_json(url)
    if d.get("code") != "0": raise RuntimeError("OKX code="+str(d.get("code"))+" "+str(d.get("msg")))
    rows=d.get("data",[])
    if not rows: raise ValueError("empty OKX candle response")
    return normalize(rows,"OKX USDT Swap",interval,int(time.time()*1000),okx=True)

def fetch_klines(symbol, interval, limit=500):
    attempts=[]
    providers=[("Binance USD-M Futures",fetch_binance_klines),
               ("Bybit V5 Linear",fetch_bybit_klines),
               ("OKX USDT Swap",fetch_okx_klines)]
    for name,fn in providers:
        try:
            candles=fn(symbol,interval,limit)
            if len(candles)<30: raise ValueError("only "+str(len(candles))+" closed candles; minimum 30")
            return {"exchange":name,"source_status":"ok","interval":interval,"requested":limit,
             "received_closed":len(candles),"last_closed_utc":datetime.fromtimestamp(candles[-1]["close_time"]/1000,timezone.utc).isoformat(),
             "candles":candles}
        except Exception as e:
            attempts.append({"exchange":name,"error":str(e)})
    return {"error":"all futures kline providers failed","source_status":"unavailable","interval":interval,"attempts":attempts}

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

def first_ok(calls):
    errors=[]
    for name,fn in calls:
        try:return {"source":name,"data":fn(),"observed_at":datetime.now(timezone.utc).isoformat()}
        except Exception as e:errors.append({"source":name,"error":str(e)})
    return {"status":"unavailable","attempts":errors}

def fetch_futures_context(symbol):
    inst=symbol.replace("USDT","-USDT-SWAP")
    out={}
    out["funding_rate"]=first_ok([
      ("Binance USD-M Futures",lambda:get_json("https://fapi.binance.com/fapi/v1/fundingRate?"+qs({"symbol":symbol,"limit":1}))),
      ("Bybit V5 Linear",lambda:get_json("https://api.bybit.com/v5/market/funding/history?"+qs({"category":"linear","symbol":symbol,"limit":1}))),
      ("OKX USDT Swap",lambda:get_json("https://www.okx.com/api/v5/public/funding-rate?"+qs({"instId":inst})))])
    out["open_interest"]=first_ok([
      ("Binance USD-M Futures",lambda:get_json("https://fapi.binance.com/fapi/v1/openInterest?symbol="+symbol)),
      ("Bybit V5 Linear",lambda:get_json("https://api.bybit.com/v5/market/open-interest?"+qs({"category":"linear","symbol":symbol,"intervalTime":"1h","limit":1}))),
      ("OKX USDT Swap",lambda:get_json("https://www.okx.com/api/v5/public/open-interest?"+qs({"instType":"SWAP","instId":inst})))])
    out["global_long_short_ratio"]=first_ok([
      ("Binance USD-M Futures",lambda:get_json("https://futures-data.binance.com/futures/data/globalLongShortAccountRatio?"+qs({"symbol":symbol,"period":"1h","limit":1}))),
      ("Bybit V5 Linear",lambda:get_json("https://api.bybit.com/v5/market/account-ratio?"+qs({"category":"linear","symbol":symbol,"period":"1h","limit":1})))])
    return out

def main():
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"collector_version":"2.0",
     "disclaimer":"Public market data only; not financial advice; no trading actions. Kline series are never mixed across exchanges.",
     "symbols":{}}
    for symbol in SYMBOLS:
        item={"spot_price":fetch_price(symbol),"futures_context":fetch_futures_context(symbol),"timeframes":{}}
        for tf in INTERVALS:
            k=fetch_klines(symbol,tf)
            if "candles" in k:k["indicators"]=indicators(k["candles"])
            item["timeframes"][tf]=k
        result["symbols"][symbol]=item
    os.makedirs("output",exist_ok=True)
    with open("output/market-data.json","w",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2)
    summary={}
    for symbol,item in result["symbols"].items():
        summary[symbol]={"spot":"ok" if "price" in item["spot_price"] else "unavailable",
         "kline_intervals":{tf:{"status":v.get("source_status","unavailable"),"source":v.get("exchange")} for tf,v in item["timeframes"].items()},
         "funding":item["futures_context"]["funding_rate"].get("source","unavailable"),
         "open_interest":item["futures_context"]["open_interest"].get("source","unavailable"),
         "long_short":item["futures_context"]["global_long_short_ratio"].get("source","unavailable")}
    print(json.dumps({"output":"output/market-data.json","generated_at":result["generated_at"],"summary":summary},ensure_ascii=False))
    # Only fail the workflow if no futures candles are available for either asset.
    if not any("candles" in tf for item in result["symbols"].values() for tf in item["timeframes"].values()):
        raise SystemExit("No futures kline data from Binance, Bybit, or OKX")

if __name__=="__main__":main()
