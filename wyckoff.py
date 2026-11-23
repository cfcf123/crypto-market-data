"""Conservative sequential Wyckoff assessment using closed, single-source OHLCV."""
from statistics import mean


def _metrics(row):
    spread=max(float(row["high"])-float(row["low"]),1e-12)
    return {"spread":spread,"close_location":(float(row["close"])-float(row["low"]))/spread,
            "bull":float(row["close"])>float(row["open"]),
            "bear":float(row["close"])<float(row["open"])}


def _break(rows, i, lookback, window, direction):
    if i < max(lookback,window): return None
    prior=rows[i-lookback:i]; hist=rows[i-window:i]; bar=rows[i]
    support=min(float(x["low"]) for x in prior)
    resistance=max(float(x["high"]) for x in prior)
    avgv=mean(float(x.get("volume",0) or 0) for x in hist)
    avgs=mean(float(x["high"])-float(x["low"]) for x in hist)
    m=_metrics(bar); vol=float(bar.get("volume",0) or 0)
    vr=vol/avgv if avgv>0 else 0
    sr=m["spread"]/avgs if avgs>0 else 0
    if direction=="bull":
        ok=float(bar["close"])>resistance and m["bull"] and m["close_location"]>=.70
        level=resistance; event="sos"
    else:
        ok=float(bar["close"])<support and m["bear"] and m["close_location"]<=.30
        level=support; event="sow"
    if ok and vr>=1.15 and sr>=1.20:
        return {"index":i,"event":event,"break_level":level,
                "volume_ratio":round(vr,3),"spread_ratio":round(sr,3)}
    return None


def _retest(rows,event,direction,max_bars=12):
    if not event: return {"status":"not_applicable","confirmed":False}
    post=rows[event["index"]+1:]
    if len(post)<2:
        return {"status":"waiting_for_retest","confirmed":False,"reason":"突破后K线不足，等待回踩/反抽"}
    post=post[-max_bars:]
    impulse=rows[event["index"]]
    iv=float(impulse.get("volume",0) or 0)
    ir=float(impulse["high"])-float(impulse["low"])
    tv=mean(float(x.get("volume",0) or 0) for x in post[:-1])
    tr=mean(float(x["high"])-float(x["low"]) for x in post[:-1])
    last=post[-1]; m=_metrics(last); level=float(event["break_level"])
    tolerance=max(ir*.75,level*.001)
    if direction=="bull":
        extreme=min(float(x["low"]) for x in post)
        near=abs(extreme-level)<=tolerance
        held=float(last["close"])>level
        reject=m["bull"] and m["close_location"]>=.60
        follow=float(last["close"])>max(float(x["high"]) for x in post[:-1])
        label="lps"
    else:
        extreme=max(float(x["high"]) for x in post)
        near=abs(extreme-level)<=tolerance
        held=float(last["close"])<level
        reject=m["bear"] and m["close_location"]<=.40
        follow=float(last["close"])<min(float(x["low"]) for x in post[:-1])
        label="lpsy"
    if not near:
        return {"status":"waiting_for_retest","confirmed":False,"reason":"尚未在突破位附近形成有效测试","break_level":level}
    if not held:
        return {"status":"failed","confirmed":False,"reason":"收盘重新进入原区间，突破暂判失效","break_level":level}
    vc=iv>0 and tv<iv*.80
    sc=ir>0 and tr<ir*.85
    if not (vc and sc):
        return {"status":"weak_or_unconfirmed_test","confirmed":False,"reason":"测试阶段量能/波幅未充分收缩","break_level":level}
    if not (reject and follow):
        return {"status":"candidate_waiting_follow_through","confirmed":False,
                "reason":"缩量窄幅测试成立，仍等待方向性拒绝及跟进","break_level":level}
    return {"status":"confirmed","confirmed":True,"event":label.upper(),
            "break_level":level,"retest_extreme":extreme,
            "test_vs_impulse_volume":round(tv/iv,3),
            "test_vs_impulse_spread":round(tr/ir,3),
            "reason":"守住结构边界，测试量能与波幅收缩，并出现方向性拒绝及跟进"}


def analyze(candles,lookback=40,volume_window=20):
    minimum=max(lookback,volume_window)+2
    if not isinstance(candles,list) or len(candles)<minimum:
        return {"status":"insufficient_data","phase":"unclassified","confidence":"low","evidence":["需要更多已收盘K线"]}
    rows=list(candles)
    try:
        for x in rows:
            vals=[float(x[k]) for k in ("open","high","low","close")]
            if not all(v==v and abs(v)!=float("inf") for v in vals): raise ValueError()
            if vals[2]>vals[1] or not(vals[2]<=vals[0]<=vals[1] and vals[2]<=vals[3]<=vals[1]): raise ValueError()
            if float(x.get("volume",0) or 0)<0: raise ValueError()
    except (KeyError,TypeError,ValueError):
        return {"status":"invalid_data","phase":"unclassified","confidence":"low","evidence":["K线OHLCV字段缺失或数值不合法"]}
    last=rows[-1]; base=rows[-lookback-1:-1]
    support=min(float(x["low"]) for x in base); resistance=max(float(x["high"]) for x in base)
    width=resistance-support; close=float(last["close"])
    avgv=mean(float(x.get("volume",0) or 0) for x in rows[-volume_window-1:-1])
    vr=float(last.get("volume",0) or 0)/avgv if avgv>0 else None
    spring=float(last["low"])<support and close>support
    utad=float(last["high"])>resistance and close<resistance
    pos=(close-support)/width if width>0 else None
    start=max(lookback,len(rows)-13)
    bulls=[_break(rows,i,lookback,volume_window,"bull") for i in range(start,len(rows))]
    bears=[_break(rows,i,lookback,volume_window,"bear") for i in range(start,len(rows))]
    sos=next((x for x in reversed(bulls) if x),None)
    sow=next((x for x in reversed(bears) if x),None)
    lps=_retest(rows,sos,"bull") if sos else {"status":"not_applicable","confirmed":False}
    lpsy=_retest(rows,sow,"bear") if sow else {"status":"not_applicable","confirmed":False}
    low_zone=pos is not None and pos<=.25; high_zone=pos is not None and pos>=.75
    candidates=(["accumulation_watch"] if low_zone else [])+(["distribution_watch"] if high_zone else [])
    if lps["confirmed"]: phase="lps_confirmed"
    elif lpsy["confirmed"]: phase="lpsy_confirmed"
    elif sos: phase="sos_waiting_lps_confirmation"
    elif sow: phase="sow_waiting_lpsy_confirmation"
    elif spring: phase="spring_candidate_waiting_confirmation"
    elif utad: phase="utad_candidate_waiting_confirmation"
    else: phase="trading_range_or_unclassified"
    evidence=[]
    if low_zone:evidence.append("区间下沿观察，不等于吸筹确认")
    if high_zone:evidence.append("区间上沿观察，不等于派发确认")
    if spring:evidence.append("Spring候选：下破支撑后收回，等待后续确认")
    if utad:evidence.append("UTAD候选：上破阻力后回落，等待后续确认")
    if sos:evidence.append("SOS候选：收盘突破区间阻力，放量扩幅且收盘靠近高点")
    if sow:evidence.append("SOW候选：收盘跌破区间支撑，放量扩幅且收盘靠近低点")
    if lps.get("confirmed"):evidence.append("LPS已确认：回踩守住突破位，缩量窄幅并向上跟进")
    elif sos:evidence.append("LPS状态："+lps["status"]+"；"+lps.get("reason",""))
    if lpsy.get("confirmed"):evidence.append("LPSY已确认：反抽守住跌破结构，缩量窄幅并向下跟进")
    elif sow:evidence.append("LPSY状态："+lpsy["status"]+"；"+lpsy.get("reason",""))
    if vr is not None:evidence.append("最新成交量/此前均量={:.2f}x".format(vr))
    if not evidence:evidence.append("未发现足够明确的威科夫事件，保持中性观察")
    return {
      "status":"ok","phase":phase,"phase_candidates":candidates,
      "confidence":"medium" if any((spring,utad,bool(sos),bool(sow),lps["confirmed"],lpsy["confirmed"])) else "low",
      "confidence_note":"结构证据完整度，不代表交易胜率；SOS/SOW必须等待LPS/LPSY测试",
      "range":{"support":support,"resistance":resistance,"close_position":pos},
      "events":{"spring_candidate":spring,"utad_candidate":utad,"sos_candidate":bool(sos),"sow_candidate":bool(sow),
                "lps_candidate":lps["status"] in ("candidate_waiting_follow_through","confirmed"),
                "lps_confirmed":lps["confirmed"],"lpsy_candidate":lpsy["status"] in ("candidate_waiting_follow_through","confirmed"),
                "lpsy_confirmed":lpsy["confirmed"]},
      "sequence":{"latest_sos":sos,"latest_sow":sow,"lps":lps,"lpsy":lpsy},
      "volume":{"last_vs_previous_average":vr},
      "squeeze_assessment":{"status":"unverified","reason":"缺少连续OI变化、强平序列及主动买卖成交流；单点OI/单根放量K线不能区分真实需求与空头回补",
                           "required_data":["连续OI变化","多空强平数据","主动买卖成交量/taker flow"]},
      "evidence":evidence,
      "limitations":["仅为单一数据源OHLCV结构假设，不能识别具体主力身份",
        "Spring/UTAD不是必需形态，单根事件不能确认反转",
        "SOS/SOW必须观察后续LPS/LPSY测试；回踩失败或量价不收缩则不确认",
        "缺少连续OI、强平和taker flow时无法区分真实需求与空头回补",
        "本模块不单独生成交易方向或入场点位"]
    }
