"""Conservative Wyckoff-style structure assessment for crypto OHLCV candles.

This module labels hypotheses, not participants or guaranteed setups. It requires
closed candles from one exchange/source and deliberately treats Spring/UTAD as
optional events.
"""
from statistics import mean


def analyze(candles, lookback=40, volume_window=20):
    """Return a compact Wyckoff evidence summary for chronological OHLCV candles."""
    if not isinstance(candles, list) or len(candles) < max(lookback, volume_window) + 2:
        return {"status": "insufficient_data", "phase": "unclassified",
                "confidence": "low", "evidence": ["需要更多已收盘K线"]}

    rows = candles[:-1] + [candles[-1]]
    recent = rows[-lookback:]
    prior = rows[-lookback-1:-1]
    vols = [float(x.get("volume", 0) or 0) for x in rows]
    closes = [float(x["close"]) for x in rows]
    highs = [float(x["high"]) for x in rows]
    lows = [float(x["low"]) for x in rows]
    last = rows[-1]
    avg_vol = mean(vols[-volume_window-1:-1])
    last_vol = vols[-1]
    vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else None

    # Trading range is estimated from the preceding closed candles, excluding
    # the latest candle so a possible sweep can be detected without look-ahead.
    base = rows[-lookback-1:-1]
    support = min(float(x["low"]) for x in base)
    resistance = max(float(x["high"]) for x in base)
    width = resistance - support
    close = float(last["close"])
    low = float(last["low"])
    high = float(last["high"])
    open_ = float(last["open"])
    candle_range = max(high - low, 1e-12)
    close_location = (close - low) / candle_range

    # Spring/UTAD are provisional single-bar events. Require reclaim/failure
    # back inside the prior range; subsequent SOS/SOW is reported separately.
    spring = low < support and close > support
    utad = high > resistance and close < resistance
    range_position = ((close - support) / width) if width > 0 else None

    # Effort vs result: elevated volume with little net progress is absorption-
    # compatible evidence, never proof of a specific actor.
    move = abs(close - open_)
    effort_result = None
    if vol_ratio is not None:
        effort_result = ("high_effort_limited_result"
                         if vol_ratio >= 1.5 and move <= candle_range * 0.35
                         else "high_effort_directional"
                         if vol_ratio >= 1.5 else "ordinary")

    prior_closes = closes[-volume_window-1:-1]
    prior_high = max(float(x["high"]) for x in rows[-volume_window-1:-1])
    prior_low = min(float(x["low"]) for x in rows[-volume_window-1:-1])
    sos = close > prior_high and (vol_ratio is None or vol_ratio >= 1.15)
    sow = close < prior_low and (vol_ratio is None or vol_ratio >= 1.15)

    # Trend context is kept deliberately simple and descriptive.
    old_close = closes[-min(lookback, len(closes))]
    trend_change = (close / old_close - 1) if old_close else 0
    if spring or (range_position is not None and range_position <= 0.25 and trend_change < 0):
        phase = "possible_accumulation"
    elif utad or (range_position is not None and range_position >= 0.75 and trend_change > 0):
        phase = "possible_distribution"
    elif sos:
        phase = "strength_confirmation"
    elif sow:
        phase = "weakness_confirmation"
    else:
        phase = "trading_range_or_unclassified"

    evidence = []
    if spring: evidence.append("疑似Spring：下破前区间支撑后收回，仍需后续SOS/LPS确认")
    if utad: evidence.append("疑似UTAD：上破前区间阻力后回落，仍需后续SOW/LPSY确认")
    if sos: evidence.append("出现SOS候选：收盘突破近端区间高点")
    if sow: evidence.append("出现SOW候选：收盘跌破近端区间低点")
    if vol_ratio is not None:
        evidence.append("最新成交量/前20根均量={:.2f}x".format(vol_ratio))
    if effort_result == "high_effort_limited_result":
        evidence.append("高成交量但价格推进有限：存在吸收/供需对抗可能，方向未定")
    if not evidence:
        evidence.append("未发现足够明确的威科夫事件，保持中性观察")

    # Confidence is about data/structure quality, not trade win probability.
    confidence = "medium" if (spring or utad or sos or sow) and vol_ratio is not None else "low"
    return {
        "status": "ok",
        "phase": phase,
        "confidence": confidence,
        "confidence_note": "结构证据完整度，不代表胜率",
        "range": {"support": support, "resistance": resistance,
                  "close_position": range_position},
        "events": {"spring_candidate": spring, "utad_candidate": utad,
                   "sos_candidate": sos, "sow_candidate": sow},
        "volume": {"last_vs_previous_20_average": vol_ratio,
                   "effort_vs_result": effort_result},
        "evidence": evidence,
        "limitations": [
            "仅为单一数据源OHLCV的结构假设，不能识别具体主力身份",
            "Spring/UTAD不是必需形态，单根K线信号必须等待后续确认",
            "本模块不单独生成交易方向或入场点位"
        ]
    }
