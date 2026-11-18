#!/usr/bin/env python3
"""Strict structural validation for collected market data; optional metrics are reported, not fatal."""
import json, math, sys
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("output/market-data.json")
REPORT = Path("output/data-quality.json")
SYMBOLS = ("BTCUSDT", "ETHUSDT")
REQUIRED_TFS = ("1d", "12h", "4h", "1h", "15m", "5m", "1m")

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
                if any(not isinstance(c.get("close_time"), (int, float)) or c["close_time"] >= generated.timestamp()*1000 for c in candles):
                    raise ValueError(f"{symbol}/{tf}: contains unclosed/future candle")
                if any(not all(math.isfinite(float(c[k])) for k in ("open","high","low","close","volume")) for c in candles):
                    raise ValueError(f"{symbol}/{tf}: non-finite candle field")
            usable[tf] = {"ok": bool(good), "source": entry.get("exchange"), "candles": len(candles)}
        count = sum(1 for v in usable.values() if v["ok"])
        if count < 3:
            raise ValueError(f"{symbol}: only {count} usable timeframes")
        ctx = item.get("futures_context", {})
        metrics = {}
        for metric in ("funding_rate", "open_interest", "global_long_short_ratio"):
            value = ctx.get(metric, {})
            metrics[metric] = {"available": isinstance(value.get("value"), (int,float)) and math.isfinite(value.get("value", float("nan"))),
                               "source": value.get("source"), "status": value.get("status", "ok" if "value" in value else "unavailable")}
        report["symbols"][symbol] = {
            "spot": {"price": price, "source": spot.get("source"), "authority": authority or "NON_BINANCE_FALLBACK", "status": spot.get("source_status")},
            "timeframes": usable, "usable_timeframes": count, "derivatives": metrics
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
