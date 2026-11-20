#!/usr/bin/env python3
"""Strict structural validation for collected market data; optional metrics are reported, not fatal."""
import json, math, sys, calendar
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA = Path("output/market-data.json")
REPORT = Path("output/data-quality.json")
SYMBOLS = ("BTCUSDT", "ETHUSDT")
REQUIRED_TFS = ("1d", "12h", "4h", "1h", "15m", "5m", "1m")
MAX_CANDLE_AGE = {"1m":600,"5m":1200,"15m":2700,"1h":10800,"4h":43200,"12h":129600,"1d":129600}
MAX_DATA_AGE_SECONDS = 600
MAX_SPOT_AGE = MAX_DATA_AGE_SECONDS
MAX_CONTEXT_RETRIEVAL_AGE = MAX_DATA_AGE_SECONDS

def parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def validate(data, now=None):
    now = now or datetime.now(timezone.utc)
    generated = parse_dt(data["generated_at"])
    age = (now - generated).total_seconds()
    if age < -60 or age > MAX_DATA_AGE_SECONDS:
        raise ValueError(f"generated_at outside allowed freshness window: {age:.0f}s")
    started_value = data.get("collection_started_at")
    started_age = None
    duration_seconds = None
    if started_value:
        started = parse_dt(started_value)
        duration_seconds = (generated - started).total_seconds()
        if duration_seconds < 0:
            raise ValueError("collection_started_at is later than generated_at")
        started_age = round((now - started).total_seconds())
    report = {"generated_at": data["generated_at"], "age_seconds": round(age),
              "collection_started_at": started_value,
              "collection_completed_at": data.get("collection_completed_at", data["generated_at"]),
              "collection_duration_seconds": round(duration_seconds, 2) if duration_seconds is not None else None,
              "symbols": {}, "overall": "ok"}
    for symbol in SYMBOLS:
        item = data.get("symbols", {}).get(symbol)
        if not isinstance(item, dict):
            raise ValueError(f"missing symbol {symbol}")
        spot = item.get("spot_price") or {}
        price = spot.get("price")
        authority = spot.get("price_authority")
        if spot.get("source_status") == "unavailable":
            if price is not None:
                raise ValueError(f"{symbol}: unavailable spot source must not contain a substitute price")
            if authority != "BINANCE_REQUIRED":
                raise ValueError(f"{symbol}: unavailable spot source missing Binance-only authority marker")
            spot_freshness = {"status":"unavailable","reason":spot.get("error","Binance Spot unavailable"),
                              "attempts":spot.get("attempts",[])}
        else:
            if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                raise ValueError(f"{symbol}: missing/invalid spot price")
            if authority != "BINANCE" or not str(spot.get("source", "")).startswith("Binance Spot"):
                raise ValueError(f"{symbol}: non-Binance spot price is not authoritative")
            if spot.get("source_status") != "ok":
                raise ValueError(f"{symbol}: invalid Binance spot source_status")
            if not spot.get("observed_at"):
                raise ValueError(f"{symbol}: spot price missing observed_at timestamp")
            spot_age = (now - parse_dt(spot["observed_at"])).total_seconds()
            if spot_age < -60 or spot_age > MAX_SPOT_AGE:
                raise ValueError(f"{symbol}: spot price is stale or future-dated ({spot_age:.0f}s)")
            spot_freshness = {"age_seconds": round(spot_age), "max_age_seconds": MAX_SPOT_AGE,
                              "status": "fresh", "observed_at": spot.get("observed_at")}
        # Only compare simultaneous live quotes; a candle close is never a ticker.
        cross_reports = []
        primary_stamp = spot.get("observed_at")
        if price is not None and primary_stamp:
            primary_dt = parse_dt(primary_stamp)
            for venue in spot.get("cross_exchange", []) or []:
                venue_price = venue.get("price")
                if not isinstance(venue_price, (int, float)) or not math.isfinite(venue_price) or venue_price <= 0:
                    continue
                venue_stamp = venue.get("observed_at")
                if not venue_stamp:
                    raise ValueError(f"{symbol}: secondary live ticker missing observed_at timestamp")
                venue_dt = parse_dt(venue_stamp)
                venue_age = (now - venue_dt).total_seconds()
                skew = abs((venue_dt - primary_dt).total_seconds())
                if venue_age < -60 or venue_age > MAX_SPOT_AGE:
                    raise ValueError(f"{symbol}: secondary live ticker stale/future-dated ({venue_age:.0f}s)")
                difference = abs(float(venue_price) - float(price)) / float(price) * 100
                cross_reports.append({"source":venue.get("source","unknown"),"price":float(venue_price),
                                      "difference_pct":round(difference,5),"timestamp_skew_seconds":round(skew,3),
                                      "freshness":"fresh" if skew <= 30 else "misaligned"})
        cross_valid = [x for x in cross_reports if x["freshness"] == "fresh"]
        cross_basis = {"status":"verified" if cross_valid and max(x["difference_pct"] for x in cross_valid) <= 0.5 else ("mismatch" if cross_valid else "unverified"),
                       "execution_allowed":bool(cross_valid) and max(x["difference_pct"] for x in cross_valid) <= 0.5,
                       "comparisons":cross_reports,"threshold_pct":0.5,"max_timestamp_skew_seconds":30}

        tfs = item.get("timeframes", {})
        usable = {}
        for tf in REQUIRED_TFS:
            entry = tfs.get(tf, {})
            candles = entry.get("candles", [])
            good = entry.get("source_status") == "ok" and len(candles) >= (200 if tf in ("1d", "12h", "4h", "1h") else 100)
            retrieval_value = entry.get("retrieved_at")
            retrieval_age = (now - parse_dt(retrieval_value)).total_seconds() if retrieval_value else None
            has_source_data = entry.get("source_status") == "ok" and bool(candles)
            if has_source_data and retrieval_age is None:
                raise ValueError(f"{symbol}/{tf}: missing data retrieval timestamp")
            if has_source_data and (retrieval_age < -60 or retrieval_age > MAX_DATA_AGE_SECONDS):
                raise ValueError(f"{symbol}/{tf}: data retrieval is stale or future-dated ({retrieval_age:.0f}s)")
            if good:
                times = [c.get("open_time") for c in candles]
                if times != sorted(times) or len(times) != len(set(times)):
                    raise ValueError(f"{symbol}/{tf}: candles not strictly chronological")
                if any(not isinstance(c.get("close_time"), (int, float)) or c["close_time"] >= now.timestamp()*1000 for c in candles):
                    raise ValueError(f"{symbol}/{tf}: contains unclosed/future candle")
                latest_age = now.timestamp() - float(candles[-1]["close_time"]) / 1000
                if latest_age < 0 or latest_age > MAX_CANDLE_AGE[tf]:
                    raise ValueError(f"{symbol}/{tf}: latest closed candle is stale ({latest_age:.0f}s)")
                for candle in candles:
                    try:
                        o,h,l,close,volume = (float(candle[k]) for k in ("open","high","low","close","volume"))
                    except (KeyError,TypeError,ValueError):
                        raise ValueError(f"{symbol}/{tf}: missing/invalid OHLCV field")
                    if not all(math.isfinite(x) for x in (o,h,l,close,volume)):
                        raise ValueError(f"{symbol}/{tf}: non-finite candle field")
                    if volume < 0 or h < max(o,close,l) or l > min(o,close,h):
                        raise ValueError(f"{symbol}/{tf}: invalid OHLCV relationship")
            latest_close = candles[-1].get("close_time") if candles else None
            latest_age = round(now.timestamp() - float(latest_close) / 1000) if good and latest_close is not None else None
            usable[tf] = {"ok": bool(good), "status": "fresh" if good else "unavailable",
                          "source": entry.get("exchange"), "candles": len(candles),
                          "latest_closed_at": datetime.fromtimestamp(float(latest_close)/1000, timezone.utc).isoformat() if latest_close is not None else None,
                          "age_seconds": latest_age, "max_age_seconds": MAX_CANDLE_AGE[tf],
                          "retrieved_at": retrieval_value,
                          "retrieval_age_seconds": round(retrieval_age) if retrieval_age is not None else None,
                          "max_retrieval_age_seconds": MAX_DATA_AGE_SECONDS,
                          "retrieval_freshness": "fresh" if good and retrieval_age is not None else "unavailable"}
        count = sum(1 for v in usable.values() if v["ok"])
        if count < 3:
            raise ValueError(f"{symbol}: only {count} usable timeframes")

        # Higher timeframes are mandatory for the multi-timeframe Wyckoff layer.
        higher = item.get("higher_timeframes", {})
        daily_source = tfs.get("1d", {}).get("exchange")
        higher_report = {}
        for htf, minimum, expected_days in (("1w", 42, 7), ("1M", 8, None)):
            entry = higher.get(htf, {}) if isinstance(higher, dict) else {}
            bars = entry.get("candles", [])
            if entry.get("source_exchange") != daily_source or entry.get("source_timeframe") != "1d":
                raise ValueError(f"{symbol}/{htf}: higher-timeframe source does not match daily source")
            if len(bars) < minimum:
                raise ValueError(f"{symbol}/{htf}: only {len(bars)} completed bars; need at least {minimum}")
            if entry.get("wyckoff", {}).get("status") != "ok":
                raise ValueError(f"{symbol}/{htf}: Wyckoff analysis is not usable")
            times = [int(b.get("open_time", -1)) for b in bars]
            if times != sorted(times) or len(times) != len(set(times)):
                raise ValueError(f"{symbol}/{htf}: higher-timeframe bars not strictly chronological")
            offsets = [b.get("calendar_offset_hours") for b in bars]
            if any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in offsets) or len(set(offsets)) != 1:
                raise ValueError(f"{symbol}/{htf}: missing or inconsistent source calendar offset")
            offset_ms = round(offsets[0] * 3600000)
            shift = timedelta(milliseconds=(86400000 - offset_ms) % 86400000)
            for bar in bars:
                opened = int(bar["open_time"])
                closed = int(bar["close_time"])
                local_start = datetime.fromtimestamp(opened / 1000, timezone.utc) + shift
                if htf == "1w":
                    days = 7
                    if local_start.weekday() != 0 or local_start.hour or local_start.minute:
                        raise ValueError(f"{symbol}/{htf}: candle is not aligned to source-calendar Monday")
                else:
                    days = calendar.monthrange(local_start.year, local_start.month)[1]
                    if local_start.day != 1 or local_start.hour or local_start.minute:
                        raise ValueError(f"{symbol}/{htf}: candle is not aligned to source-calendar month start")
                if int(bar.get("source_days", -1)) != days or closed - opened + 1 != days * 86400000:
                    raise ValueError(f"{symbol}/{htf}: incomplete aggregated period")
                if closed >= now.timestamp() * 1000:
                    raise ValueError(f"{symbol}/{htf}: contains unclosed/future period")
                values = [float(bar[k]) for k in ("open", "high", "low", "close", "volume")]
                if not all(math.isfinite(x) for x in values):
                    raise ValueError(f"{symbol}/{htf}: non-finite OHLCV")
                o, h, l, c, vol = values
                if vol < 0 or h < max(o, c, l) or l > min(o, c, h):
                    raise ValueError(f"{symbol}/{htf}: invalid OHLCV relationship")
            htf_age = round(now.timestamp() - float(bars[-1]["close_time"]) / 1000)
            higher_report[htf] = {"ok": True, "status": "fresh", "source": entry.get("source_exchange"),
                                  "candles": len(bars), "latest_closed_at": datetime.fromtimestamp(float(bars[-1]["close_time"])/1000, timezone.utc).isoformat(),
                                  "age_seconds": htf_age,
                                  "source_data_retrieved_at": tfs.get("1d", {}).get("retrieved_at"),
                                  "max_source_retrieval_age_seconds": MAX_DATA_AGE_SECONDS}
        ctx = item.get("futures_context", {})
        metrics = {}
        for metric in ("funding_rate", "open_interest", "global_long_short_ratio"):
            value = ctx.get(metric, {})
            available = isinstance(value.get("value"), (int,float)) and math.isfinite(value.get("value", float("nan")))
            retrieved_at = value.get("observed_at")
            retrieval_age = (now - parse_dt(retrieved_at)).total_seconds() if retrieved_at else None
            if available and retrieval_age is None:
                raise ValueError(f"{symbol}/{metric}: available derivative metric missing retrieval timestamp")
            if retrieval_age is not None and (retrieval_age < -60 or retrieval_age > MAX_CONTEXT_RETRIEVAL_AGE):
                raise ValueError(f"{symbol}/{metric}: context retrieval timestamp is stale or future-dated ({retrieval_age:.0f}s)")
            metrics[metric] = {"available": available,
                               "source": value.get("source"),
                               "status": value.get("status", "ok" if available else "unavailable"),
                               "retrieved_at": retrieved_at,
                               "retrieval_age_seconds": round(retrieval_age) if retrieval_age is not None else None,
                               "max_retrieval_age_seconds": MAX_CONTEXT_RETRIEVAL_AGE,
                               "freshness": "fresh" if available and retrieval_age is not None else ("timestamp_missing" if available else "unavailable")}
        report["symbols"][symbol] = {
            "spot": {"price": price, "source": spot.get("source"), "authority": authority or "NON_BINANCE_FALLBACK", "status": spot.get("source_status"), "freshness": spot_freshness, "cross_exchange_basis": cross_basis if price is not None else {"status":"unverified","execution_allowed":False,"comparisons":[]}},
            "timeframes": usable, "usable_timeframes": count, "higher_timeframes": higher_report, "derivatives": metrics
        }
    return report

def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    report = validate(data)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"DATA_QUALITY_FAILURE: {exc}", file=sys.stderr)
        raise
