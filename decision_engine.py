#!/usr/bin/env python3
"""Transparent multi-timeframe evidence fusion and conditional level planner.

This module does not place orders. Weights are evidence allocations, not win
probabilities. Levels are conditional triggers derived from closed candles.
"""
import json
import math
from pathlib import Path
from collector import indicators

TIMEFRAME_WEIGHTS = {
    "1M": 0.20, "1w": 0.22, "1d": 0.20,
    "12h": 0.08, "4h": 0.16, "1h": 0.10, "15m": 0.04,
}


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _clamp(value, low=-1.0, high=1.0):
    return max(low, min(high, value))


def _timeframe_evidence(candles, metric):
    if not candles or not isinstance(metric, dict):
        return None
    close = float(candles[-1]["close"])
    points = []
    e20, e50, e200 = metric.get("ema20"), metric.get("ema50"), metric.get("ema200")
    if _finite(e20):
        points.append(0.35 if close > e20 else -0.35 if close < e20 else 0.0)
    if _finite(e20) and _finite(e50):
        points.append(0.35 if e20 > e50 else -0.35 if e20 < e50 else 0.0)
    if _finite(e50) and _finite(e200):
        points.append(0.20 if e50 > e200 else -0.20 if e50 < e200 else 0.0)
    macd, signal = metric.get("macd"), metric.get("macd_signal9")
    if _finite(macd) and _finite(signal):
        points.append(0.20 if macd > signal else -0.20 if macd < signal else 0.0)
    rsi = metric.get("rsi14")
    if _finite(rsi):
        if rsi >= 60:
            points.append(0.15)
        elif rsi <= 40:
            points.append(-0.15)
        elif 45 <= rsi <= 55:
            points.append(0.0)
    if not points:
        return None
    return _clamp(sum(points) / sum(abs(x) if x else 1.0 for x in points))


def _wyckoff_adjustment(item):
    """Small bounded adjustment: Wyckoff confirms/contradicts, never dominates."""
    adjustment = 0.0
    evidence = []
    for tf in ("1M", "1w", "1d", "4h"):
        block = item.get("higher_timeframes", {}).get(tf, {}) if tf in ("1M", "1w") else item.get("timeframes", {}).get(tf, {})
        w = block.get("wyckoff", {}) if isinstance(block, dict) else {}
        events = w.get("events", {})
        phase = w.get("phase", "")
        if events.get("sos_candidate") or phase == "strength_confirmation":
            adjustment += 0.04
            evidence.append(tf + ": SOS/strength evidence (+)")
        if events.get("sow_candidate") or phase == "weakness_confirmation":
            adjustment -= 0.04
            evidence.append(tf + ": SOW/weakness evidence (-)")
        if events.get("spring_candidate"):
            adjustment += 0.02
            evidence.append(tf + ": Spring candidate (small +, unconfirmed)")
        if events.get("utad_candidate"):
            adjustment -= 0.02
            evidence.append(tf + ": UTAD candidate (small -, unconfirmed)")
    return _clamp(adjustment, -0.12, 0.12), evidence


def _levels(item):
    spot_block = item.get("spot_price", {})
    spot = spot_block.get("price")
    if not _finite(spot) or spot <= 0:
        return {"status": "unavailable", "reason": "No valid reference price"}
    source_tf = None
    candles = None
    metric = None
    for tf in ("4h", "1h", "15m"):
        entry = item.get("timeframes", {}).get(tf, {})
        if entry.get("source_status") == "ok" and entry.get("candles"):
            candidate = entry["candles"]
            candidate_metric = entry.get("indicators") or indicators(candidate)
            if _finite(candidate_metric.get("atr14")) and candidate_metric["atr14"] > 0:
                source_tf, candles, metric = tf, candidate, candidate_metric
                break
    if metric is None:
        atr = float(spot) * 0.008
        source_tf = "spot_estimate"
        swing_high, swing_low = float(spot) * 1.005, float(spot) * 0.995
        level_basis = "estimated 0.8% ATR and ±0.5% range; not candle-derived"
    else:
        atr_raw = float(metric["atr14"])
        swing_high_raw = metric.get("swing_high_20")
        swing_low_raw = metric.get("swing_low_20")
        if not _finite(swing_high_raw) or not _finite(swing_low_raw) or swing_high_raw <= swing_low_raw:
            swing_high_raw = max(float(x["high"]) for x in candles[-20:])
            swing_low_raw = min(float(x["low"]) for x in candles[-20:])
        candle_close = float(candles[-1]["close"])
        # Align OHLCV-derived levels to the authoritative reference-price basis
        # (normally Binance Spot) without mixing candle series from exchanges.
        basis_ratio = float(spot) / candle_close if candle_close > 0 else 1.0
        basis_diff_pct = abs(float(spot) - candle_close) / candle_close * 100 if candle_close > 0 else None
        atr = atr_raw * basis_ratio
        swing_high = float(swing_high_raw) * basis_ratio
        swing_low = float(swing_low_raw) * basis_ratio
        level_basis = "closed " + source_tf + " candles; 20-bar swing and ATR14; levels scaled to reference-price basis"
    long_trigger = max(float(spot), float(swing_high)) + 0.10 * atr
    short_trigger = min(float(spot), float(swing_low)) - 0.10 * atr
    return {
        "status": "conditional",
        "reference_price": float(spot),
        "reference_source": spot_block.get("source", "unknown"),
        "source_timeframe": source_tf,
        "basis": level_basis,
        "atr14": round(atr, 8),
        "source_exchange": item.get("timeframes", {}).get(source_tf, {}).get("exchange") if source_tf != "spot_estimate" else None,
        "source_last_close": round(candle_close, 8) if metric is not None else None,
        "reference_basis_difference_pct": round(basis_diff_pct, 4) if metric is not None else None,
        "basis_warning": "参考价与K线源收盘价基差超过0.5%，点位已按参考价比例校准，执行前需复核" if metric is not None and basis_diff_pct > 0.5 else None,
        "long": {
            "entry_trigger": round(long_trigger, 8),
            "stop_loss": round(long_trigger - 1.5 * atr, 8),
            "take_profit_1": round(long_trigger + 1.5 * atr, 8),
            "take_profit_2": round(long_trigger + 2.5 * atr, 8),
            "condition": "仅在已收盘K线确认突破入场触发价后考虑；未触发不追单"
        },
        "short": {
            "entry_trigger": round(short_trigger, 8),
            "stop_loss": round(short_trigger + 1.5 * atr, 8),
            "take_profit_1": round(short_trigger - 1.5 * atr, 8),
            "take_profit_2": round(short_trigger - 2.5 * atr, 8),
            "condition": "仅在已收盘K线确认跌破入场触发价后考虑；未触发不追单"
        }
    }


def analyze_symbol(item):
    evidence = {}
    available_weight = 0.0
    weighted_score = 0.0
    for tf, weight in TIMEFRAME_WEIGHTS.items():
        if tf in ("1M", "1w"):
            block = item.get("higher_timeframes", {}).get(tf, {})
            candles = block.get("candles", [])
            metric = indicators(candles) if candles else {}
        else:
            block = item.get("timeframes", {}).get(tf, {})
            candles = block.get("candles", [])
            metric = block.get("indicators", {})
        score = _timeframe_evidence(candles, metric)
        evidence[tf] = {"weight": weight, "score": round(score, 4) if score is not None else None,
                        "status": "usable" if score is not None else "unavailable"}
        if score is not None:
            weighted_score += weight * score
            available_weight += weight
    if available_weight:
        weighted_score /= available_weight
    else:
        weighted_score = 0.0
    wyckoff_adjustment, wyckoff_evidence = _wyckoff_adjustment(item)
    final_score = _clamp(weighted_score + wyckoff_adjustment)
    positive_weight = sum(TIMEFRAME_WEIGHTS[tf] for tf, row in evidence.items() if row["score"] is not None and row["score"] > 0)
    negative_weight = sum(TIMEFRAME_WEIGHTS[tf] for tf, row in evidence.items() if row["score"] is not None and row["score"] < 0)
    conflict = (2 * min(positive_weight, negative_weight) / (positive_weight + negative_weight)
                if positive_weight + negative_weight else 0.0)
    neutral = _clamp(0.55 - 0.30 * abs(final_score) + 0.15 * conflict + 0.35 * (1.0 - available_weight), 0.25, 0.85)
    long_weight = (1 - neutral) * (1 + final_score) / 2
    short_weight = (1 - neutral) * (1 - final_score) / 2
    total = long_weight + short_weight + neutral
    weights = {"long": round(long_weight / total * 100, 1),
               "short": round(short_weight / total * 100, 1),
               "neutral": round(neutral / total * 100, 1)}
    # Correct rounding drift so displayed percentages always total exactly 100.0.
    weights["neutral"] = round(100.0 - weights["long"] - weights["short"], 1)
    return {
        "weights_pct": weights,
        "evidence_score": round(final_score, 4),
        "timeframe_conflict": round(conflict, 4),
        "available_weight_pct": round(available_weight * 100, 1),
        "timeframes": evidence,
        "wyckoff_adjustment": round(wyckoff_adjustment, 4),
        "wyckoff_evidence": wyckoff_evidence,
        "levels": _levels(item),
        "interpretation": "权重表示多周期证据倾向，不是胜率；观望权重随方向冲突上升。"
    }


def analyze_dataset(data):
    result = {"generated_at": data.get("generated_at"),
              "analysis_type": "multi_timeframe_evidence_fusion_v1",
              "symbols": {}}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        item = data.get("symbols", {}).get(symbol)
        if not isinstance(item, dict):
            result["symbols"][symbol] = {"status": "unavailable", "reason": "missing symbol"}
            continue
        result["symbols"][symbol] = analyze_symbol(item)
    return result


def main():
    source = Path("output/market-data.json")
    destination = Path("output/trade-analysis.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    result = analyze_dataset(data)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(destination), "symbols": result["symbols"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
