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
MAX_SPOT_AGE = 300

def parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def validate(data, now=None):
    now = now or datetime.now(timezone.utc)
    generated = parse_dt(data["generated_at"])
    age = (now - generated).total_seconds()
    if age < -60 or age > 900:
        raise ValueError(f"generated_at outside allowed freshness window: {age:.0f}s")
    report = {"generated_at": data["generated_at"], "age_seconds": round(age), "symbols": {}, "overall": "ok"}
    for symbol in SYMBOLS:
        item = data.get("symbols", {}).get(symbol)
        if not isinstance(item, dict):
            raise ValueError(f"missing symbol {symbol}")
        spot = item.get("spot_price") or {}
        price = spot.get("price")
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError(f"{symbol}: missing/invalid spot price")
        authority = spot.get("price_authority")
        if authority == "BINANCE" and not str(spot.get("source", "")).startswith("Binance Spot"):
            raise ValueError(f"{symbol}: BINANCE authority/source mismatch")
        if spot.get("source_status") not in ("ok", "fallback"):
            raise ValueError(f"{symbol}: invalid spot source_status")
        if not spot.get("observed_at"):
            raise ValueError(f"{symbol}: spot price missing observed_at timestamp")
        spot_age = (now - parse_dt(spot["observed_at"])).total_seconds()
        if spot_age < -60 or spot_age > MAX_SPOT_AGE:
            raise ValueError(f"{symbol}: spot price is stale or future-dated ({spot_age:.0f}s)")
        tfs = item.get("timeframes", {})
        usable = {}
        for tf in REQUIRED_TFS:
            entry = tfs.get(tf, {})
            candles = entry.get("candles", [])
            good = entry.get("source_status") == "ok" and len(candles) >= (200 if tf in ("1d", "12h", "4h", "1h") else 100)
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
            usable[tf] = {"ok": bool(good), "source": entry.get("exchange"), "candles": len(candles)}
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
            higher_report[htf] = {"ok": True, "source": entry.get("source_exchange"), "candles": len(bars)}
        ctx = item.get("futures_context", {})
        metrics = {}
        for metric in ("funding_rate", "open_interest", "global_long_short_ratio"):
            value = ctx.get(metric, {})
            metrics[metric] = {"available": isinstance(value.get("value"), (int,float)) and math.isfinite(value.get("value", float("nan"))),
                               "source": value.get("source"), "status": value.get("status", "ok" if "value" in value else "unavailable")}
        report["symbols"][symbol] = {
            "spot": {"price": price, "source": spot.get("source"), "authority": authority or "NON_BINANCE_FALLBACK", "status": spot.get("source_status")},
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
