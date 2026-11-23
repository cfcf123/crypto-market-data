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


def _realtime_basis_check(spot_block, max_skew_seconds=30, threshold_pct=0.5):
    """Compare Binance Spot with same-time live venue tickers, never candle closes."""
    from datetime import datetime, timezone
    primary, stamp = spot_block.get("price"), spot_block.get("observed_at")
    if not _finite(primary) or primary <= 0 or not stamp:
        return {"status":"unverified","execution_allowed":False,"reason":"Binance reference price/timestamp unavailable","comparisons":[],"threshold_pct":threshold_pct}
    try:
        primary_dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if primary_dt.tzinfo is None: raise ValueError("timezone missing")
    except Exception:
        return {"status":"unverified","execution_allowed":False,"reason":"Binance reference timestamp invalid","comparisons":[],"threshold_pct":threshold_pct}
    comparisons=[]
    for venue in spot_block.get("cross_exchange", []) or []:
        price, venue_stamp = venue.get("price"), venue.get("observed_at")
        if not _finite(price) or price <= 0 or not venue_stamp: continue
        try:
            venue_dt=datetime.fromisoformat(str(venue_stamp).replace("Z", "+00:00"))
            if venue_dt.tzinfo is None: continue
            skew=abs((venue_dt-primary_dt).total_seconds())
            age=abs((datetime.now(timezone.utc)-venue_dt).total_seconds())
        except Exception: continue
        if skew > max_skew_seconds or age > 600: continue
        diff=abs(float(price)-float(primary))/float(primary)*100
        comparisons.append({"source":venue.get("source","unknown"),"price":float(price),"difference_pct":round(diff,5),"timestamp_skew_seconds":round(skew,3),"observed_at":venue_stamp})
    if not comparisons:
        return {"status":"unverified","execution_allowed":False,"reason":"No fresh secondary-exchange ticker within timestamp alignment window","comparisons":[],"threshold_pct":threshold_pct,"max_timestamp_skew_seconds":max_skew_seconds}
    maximum=max(x["difference_pct"] for x in comparisons)
    allowed=maximum <= threshold_pct
    return {"status":"verified" if allowed else "mismatch","execution_allowed":allowed,"reason":None if allowed else "Same-time live exchange price difference exceeds threshold","max_difference_pct":round(maximum,5),"comparisons":comparisons,"threshold_pct":threshold_pct,"max_timestamp_skew_seconds":max_skew_seconds}


def _risk_reward(entry, stop, tp1, tp2):
    """Return approximate R multiples; zones use their midpoint as entry reference."""
    risk = abs(float(entry) - float(stop))
    if not _finite(risk) or risk <= 0:
        return {"status": "unavailable", "reason": "entry and stop must define positive risk"}
    return {
        "status": "calculated",
        "entry_reference": round(float(entry), 8),
        "risk_per_unit": round(risk, 8),
        "tp1_r": round(abs(float(tp1) - float(entry)) / risk, 3),
        "tp2_r": round(abs(float(tp2) - float(entry)) / risk, 3),
        "note": "conditional estimate; zone entries use zone midpoint; actual R depends on fill price and fees"
    }


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
    """Sequence-aware, bounded adjustment; confirmed tests outweigh candidates."""
    adjustment = 0.0
    evidence = []
    for tf in ("1M", "1w", "1d", "4h"):
        block = item.get("higher_timeframes", {}).get(tf, {}) if tf in ("1M", "1w") else item.get("timeframes", {}).get(tf, {})
        w = block.get("wyckoff", {}) if isinstance(block, dict) else {}
        events = w.get("events", {}) if isinstance(w, dict) else {}
        phase = w.get("phase", "")
        if events.get("lps_confirmed") or phase == "lps_confirmed":
            adjustment += 0.05
            evidence.append(tf + ": LPS回踩确认 (+)")
        elif events.get("sos_candidate") or phase == "sos_waiting_lps_confirmation":
            adjustment += 0.02
            evidence.append(tf + ": SOS候选/等待LPS（小幅+）")
        if events.get("lpsy_confirmed") or phase == "lpsy_confirmed":
            adjustment -= 0.05
            evidence.append(tf + ": LPSY反抽确认 (-)")
        elif events.get("sow_candidate") or phase == "sow_waiting_lpsy_confirmation":
            adjustment -= 0.02
            evidence.append(tf + ": SOW候选/等待LPSY（小幅-）")
        if events.get("spring_candidate"):
            adjustment += 0.01
            evidence.append(tf + ": Spring候选（未确认，极小+）")
        if events.get("utad_candidate"):
            adjustment -= 0.01
            evidence.append(tf + ": UTAD候选（未确认，极小-）")
    return _clamp(adjustment, -0.16, 0.16), evidence


def _derivatives_adjustment(item):
    """Very small contrarian context adjustment; OI is descriptive, not directional."""
    context = item.get("futures_context", {})
    if not isinstance(context, dict):
        context = {}
    adjustment = 0.0
    notes = []
    details = {}
    funding = context.get("funding_rate", {})
    funding_value = funding.get("value") if isinstance(funding, dict) else None
    if _finite(funding_value):
        details["funding_rate"] = funding_value
        details["funding_source"] = funding.get("source")
        # Only unusually positive/negative funding receives a small contrarian tilt.
        if funding_value >= 0.0001:
            adjustment -= 0.02
            notes.append("正资金费率偏高：多头持仓成本上升，轻微逆向偏空")
        elif funding_value <= -0.0001:
            adjustment += 0.02
            notes.append("负资金费率偏低：空头拥挤风险增加，轻微逆向偏多")
    ratio = context.get("global_long_short_ratio", {})
    ratio_value = ratio.get("value") if isinstance(ratio, dict) else None
    if _finite(ratio_value) and ratio_value > 0:
        details["global_long_short_ratio"] = ratio_value
        details["long_short_source"] = ratio.get("source")
        if ratio_value >= 1.5:
            adjustment -= 0.02
            notes.append("多空账户比偏向多头：作为拥挤度提示，轻微逆向偏空")
        elif ratio_value <= 0.67:
            adjustment += 0.02
            notes.append("多空账户比偏向空头：作为拥挤度提示，轻微逆向偏多")
    oi = context.get("open_interest", {})
    oi_value = oi.get("value") if isinstance(oi, dict) else None
    if _finite(oi_value) and oi_value >= 0:
        details["open_interest"] = oi_value
        details["open_interest_unit"] = oi.get("unit")
        details["open_interest_source"] = oi.get("source")
        notes.append("OI仅作持仓规模背景；缺少连续变化序列，不参与方向打分")
    return _clamp(adjustment, -0.04, 0.04), details, notes



def _left_side_setup(side, spot, atr, swing_high, swing_low, ema20, ema50, item):
    """Structural left-side planner. EMA20/50 are scoring inputs, never vetoes."""
    short = side == "short"
    level = swing_high if short else swing_low
    if not _finite(level) or (level <= spot + .25*atr if short else level >= spot - .25*atr):
        return {"status":"unavailable","reason":("缺少高于现价至少0.25 ATR的有效结构压力/前高" if short else "缺少低于现价至少0.25 ATR的有效结构支撑/前低")+"，不能建立左侧预埋"}
    distance = (level-spot)/atr if short else (spot-level)/atr
    if distance > 8:
        return {"status":"unavailable","reason":"有效结构位距离现价超过8 ATR，预埋距离过远"}
    lo, hi = level-.15*atr, level+.15*atr
    if (lo <= spot if short else hi >= spot):
        return {"status":"unavailable","reason":"结构区域与现价重叠，缺少安全预埋空间"}
    stop = level+(.8*atr if short else -.8*atr)
    tp1 = spot
    tp2 = (min(swing_low,tp1-.5*atr) if _finite(swing_low) else tp1-2*atr) if short else (max(swing_high,tp1+.5*atr) if _finite(swing_high) else tp1+2*atr)
    if (tp2 >= tp1 if short else tp2 <= tp1): tp2 = tp1+(-2*atr if short else 2*atr)
    aligned = ((spot < ema20 and ema20 < ema50) if short else (spot > ema20 and ema20 > ema50)) if _finite(ema20) and _finite(ema50) else False
    vals=[_timeframe_evidence(item.get("timeframes",{}).get(tf,{}).get("candles",[]),item.get("timeframes",{}).get(tf,{}).get("indicators",{})) for tf in ("1d","12h","4h")]
    vals=[v for v in vals if v is not None]
    trend=sum(vals)/len(vals) if vals else 0.0
    trend_score=max(0.0,min(100.0,50.0+(-35.0 if short else 35.0)*trend))
    proximity=max(0.0,100.0-distance*10.0)
    quality=round(.45*trend_score+.40*proximity+(10 if aligned else 0))
    return {"status":"conditional","entry_zone":[round(lo,8),round(hi,8)],"stop_loss":round(stop,8),
            "take_profit_1":round(tp1,8),"take_profit_2":round(tp2,8),
            "risk_reward":_risk_reward((lo+hi)/2,stop,tp1,tp2),"setup_score":quality,
            "quality_grade":"A" if quality>=75 else "B" if quality>=60 else "C",
            "structure_basis":("近端前高/摆动高点结构压力" if short else "近端前低/摆动低点结构支撑")+"；EMA20/EMA50仅参与评分",
            "condition":("反弹进入结构压力区后，等待已收盘1h K线受阻/转弱确认" if short else "回踩进入结构支撑区后，等待已收盘1h K线止跌/转强确认")+"；评分低于60仅观察、不建议挂单；未触发不追单"}

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
        # Candle structure remains in its native exchange scale. A prior candle
        # close is not a contemporaneous quote and must never be used as basis.
        atr = atr_raw
        swing_high = float(swing_high_raw)
        swing_low = float(swing_low_raw)
        level_basis = "closed " + source_tf + " candles; native candle-source scale; no stale-close basis scaling"
    long_trigger = max(float(spot), float(swing_high)) + 0.10 * atr
    short_trigger = min(float(spot), float(swing_low)) - 0.10 * atr
    retest_long = {"status":"unavailable","reason":"缺少有效结构支撑/ATR数据"}
    rebound_short = {"status":"unavailable","reason":"缺少有效结构压力/ATR数据"}
    if metric is not None:
        retest_long = _left_side_setup("long",float(spot),atr,swing_high,swing_low,metric.get("ema20"),metric.get("ema50"),item)
        rebound_short = _left_side_setup("short",float(spot),atr,swing_high,swing_low,metric.get("ema20"),metric.get("ema50"),item)
    basis_check = _realtime_basis_check(spot_block)
    if basis_check["status"] == "mismatch":
        basis_warning = "同一时刻交易所实时价格差异超过0.5%，已暂停实盘执行建议"
    elif basis_check["status"] == "unverified":
        basis_warning = "缺少时间对齐的有效跨交易所实时价格，基差未验证，已暂停实盘执行建议"
    else:
        basis_warning = None
    return {
        "status": "conditional",
        "execution_allowed": basis_check["execution_allowed"],
        "execution_status": "allowed" if basis_check["execution_allowed"] else ("paused_basis_mismatch" if basis_check["status"] == "mismatch" else "paused_basis_unverified"),
        "basis_check": basis_check,
        "reference_basis_difference_pct": basis_check.get("max_difference_pct"),
        "basis_warning": basis_warning,
        "reference_price": float(spot),
        "reference_source": spot_block.get("source", "unknown"),
        "source_timeframe": source_tf,
        "basis": level_basis,
        "atr14": round(atr, 8),
        "source_exchange": item.get("timeframes", {}).get(source_tf, {}).get("exchange") if source_tf != "spot_estimate" else None,
        "source_last_close": round(candle_close, 8) if metric is not None else None,
        "long": {
            "entry_trigger": round(long_trigger, 8),
            "stop_loss": round(long_trigger - 1.5 * atr, 8),
            "take_profit_1": round(long_trigger + 1.5 * atr, 8),
            "take_profit_2": round(long_trigger + 2.5 * atr, 8),
            "risk_reward": _risk_reward(long_trigger, long_trigger - 1.5 * atr,
                                        long_trigger + 1.5 * atr, long_trigger + 2.5 * atr),
            "condition": "仅在已收盘K线确认突破入场触发价后考虑；未触发不追单"
        },
        "pullback_long": retest_long,
        "short": {
            "entry_trigger": round(short_trigger, 8),
            "stop_loss": round(short_trigger + 1.5 * atr, 8),
            "take_profit_1": round(short_trigger - 1.5 * atr, 8),
            "take_profit_2": round(short_trigger - 2.5 * atr, 8),
            "risk_reward": _risk_reward(short_trigger, short_trigger + 1.5 * atr,
                                        short_trigger - 1.5 * atr, short_trigger - 2.5 * atr),
            "condition": "仅在已收盘K线确认跌破入场触发价后考虑；未触发不追单"
        },
        "rebound_short": rebound_short
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
    derivatives_adjustment, derivatives_context, derivatives_notes = _derivatives_adjustment(item)
    final_score = _clamp(weighted_score + wyckoff_adjustment + derivatives_adjustment)
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
        "derivatives_adjustment": round(derivatives_adjustment, 4),
        "derivatives_context": derivatives_context,
        "derivatives_notes": derivatives_notes,
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
