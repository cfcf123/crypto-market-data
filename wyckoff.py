"""Conservative Wyckoff-style structure assessment for closed, single-source OHLCV candles.

Outputs evidence hypotheses only. It never infers the identity or intent of a
specific participant and never creates a trade direction or entry.
"""
from statistics import mean


def analyze(candles, lookback=40, volume_window=20):
    """Assess range events and volume confirmation from chronological closed candles."""
    minimum = max(lookback, volume_window) + 2
    if not isinstance(candles, list) or len(candles) < minimum:
        return {"status": "insufficient_data", "phase": "unclassified",
                "confidence": "low", "evidence": ["需要更多已收盘K线"]}

    rows = list(candles)
    try:
        closes = [float(x["close"]) for x in rows]
        highs = [float(x["high"]) for x in rows]
        lows = [float(x["low"]) for x in rows]
        opens = [float(x["open"]) for x in rows]
        vols = [float(x.get("volume", 0) or 0) for x in rows]
    except (KeyError, TypeError, ValueError):
        return {"status": "invalid_data", "phase": "unclassified",
                "confidence": "low", "evidence": ["K线字段缺失或数值无效"]}

    if any(v < 0 for v in vols) or any(h < l for h, l in zip(highs, lows)):
        return {"status": "invalid_data", "phase": "unclassified",
                "confidence": "low", "evidence": ["成交量或高低价数据不合法"]}

    last = rows[-1]
    close, high, low, open_ = closes[-1], highs[-1], lows[-1], opens[-1]
    base = rows[-lookback-1:-1]
    support = min(float(x["low"]) for x in base)
    resistance = max(float(x["high"]) for x in base)
    width = resistance - support
    avg_vol = mean(vols[-volume_window-1:-1])
    vol_ratio = vols[-1] / avg_vol if avg_vol > 0 else None

    candle_range = max(high - low, 1e-12)
    close_location = (close - low) / candle_range
    spring = low < support and close > support
    utad = high > resistance and close < resistance
    range_position = (close - support) / width if width > 0 else None

    prior_high = max(highs[-volume_window-1:-1])
    prior_low = min(lows[-volume_window-1:-1])
    volume_confirmed = vol_ratio is not None and vol_ratio >= 1.15
    sos = close > prior_high and volume_confirmed
    sow = close < prior_low and volume_confirmed

    move = abs(close - open_)
    effort_result = None
    if vol_ratio is not None:
        if vol_ratio >= 1.5 and move <= candle_range * 0.35:
            effort_result = "high_effort_limited_result"
        elif vol_ratio >= 1.5:
            effort_result = "high_effort_directional"
        else:
            effort_result = "ordinary"

    # Location inside a range is context, not proof of accumulation/distribution.
    low_zone = range_position is not None and range_position <= 0.25
    high_zone = range_position is not None and range_position >= 0.75
    phase_candidates = []
    if low_zone:
        phase_candidates.append("accumulation_watch")
    if high_zone:
        phase_candidates.append("distribution_watch")

    # Do not label a phase from location/trend alone. Require an actual
    # range event or volume-confirmed break before elevating the structure.
    if spring:
        phase = "spring_candidate_waiting_confirmation"
    elif utad:
        phase = "utad_candidate_waiting_confirmation"
    elif sos:
        phase = "strength_confirmation"
    elif sow:
        phase = "weakness_confirmation"
    else:
        phase = "trading_range_or_unclassified"

    evidence = []
    if low_zone:
        evidence.append("价格处于观察区间下沿：仅为吸筹观察条件，不等于已确认吸筹")
    if high_zone:
        evidence.append("价格处于观察区间上沿：仅为派发观察条件，不等于已确认派发")
    if spring:
        evidence.append("疑似Spring：下破前区间支撑后收回，等待后续SOS/LPS")
    if utad:
        evidence.append("疑似UTAD：上破前区间阻力后回落，等待后续SOW/LPSY")
    if sos:
        evidence.append("SOS候选：收盘突破近20根K线高点且成交量至少为前20根均量1.15倍")
    if sow:
        evidence.append("SOW候选：收盘跌破近20根K线低点且成交量至少为前20根均量1.15倍")
    if vol_ratio is not None:
        evidence.append("最新成交量/前20根均量={:.2f}x".format(vol_ratio))
    if effort_result == "high_effort_limited_result":
        evidence.append("高成交量但价格推进有限：可能存在吸收或供需对抗，方向未定")
    if not evidence:
        evidence.append("未发现足够明确的威科夫事件，保持中性观察")

    event_count = sum((spring, utad, sos, sow))
    confidence = "medium" if event_count and volume_confirmed else "low"
    return {
        "status": "ok",
        "phase": phase,
        "phase_candidates": phase_candidates,
        "confidence": confidence,
        "confidence_note": "结构证据完整度，不代表交易胜率；单根事件仍需后续K线确认",
        "range": {"support": support, "resistance": resistance,
                  "close_position": range_position},
        "events": {"spring_candidate": spring, "utad_candidate": utad,
                   "sos_candidate": sos, "sow_candidate": sow},
        "volume": {"last_vs_previous_20_average": vol_ratio,
                   "effort_vs_result": effort_result,
                   "breakout_volume_confirmed": volume_confirmed},
        "evidence": evidence,
        "limitations": [
            "仅为单一数据源OHLCV结构假设，不能识别具体主力身份",
            "区间高低位置不单独构成吸筹/派发结论",
            "Spring/UTAD不是必需形态，单根K线信号必须等待后续确认",
            "本模块不单独生成交易方向或入场点位"
        ]
    }
