# 用户固定执行规则（长期有效）

本文件记录用户明确要求，适用于所有新旧 ChatGPT 对话窗口。执行任务前必须遵守，不得因换窗口、上下文变化或定时工作流配置而遗忘。

## 一、数据采集触发规则
1. 禁止每 10 分钟自动采集。
2. 禁止任何 cron 定时采集、定时 watchdog、过期自动刷新或后台自动派发采集。
3. 只有用户明确发出“执行一次任务”“严格执行一次任务”等执行指令时，才启动本次采集。
4. 每次用户指令都必须创建或更新仓库根目录的 manual-trigger.txt，并 push 到 main，以此启动一次全新的 GitHub Actions 采集。
5. 每次触发标记必须唯一，包含本次执行标识和 UTC 时间，避免误认其他运行。
6. 不允许用无关文档提交代替本次任务触发；不允许复用上一次运行的 Artifact，即使上一次数据仍在 10 分钟以内。
7. 用户没有要求执行任务时，不得自行触发采集。

## 二、每次执行的强制核验
1. 等待本次 push 对应的 GitHub Actions 完成。
2. 必须核对本次运行的 head SHA 与触发提交一致。
3. 必须确认单元测试、数据采集、数据校验、分析生成和 Artifact 上传步骤状态。
4. 必须下载本次 run 对应的 Artifact，并核对 run_id、run_number、SHA、生成时间及文件完整性。
5. 数据最大允许年龄为 600 秒；本次采集产生的时间戳必须与本次运行对应。
6. 若采集、Artifact 下载、时间戳或质量校验失败，明确报告 DATA_UNAVAILABLE；不得拿旧数据冒充新数据，不得编造实时价格和交易点位。

## 三、交易报告要求
1. BTCUSDT 与 ETHUSDT 都必须分析。
2. 报告开头优先给出交易点位和多空/观望权重。
3. 每个币种必须覆盖四种策略：左侧回调做多、左侧反弹做空、右侧突破做多、右侧跌破做空。
4. 每个策略应给出入场/触发价、止损、TP1、TP2、触发条件及盈亏比；条件不成立时也必须列出，并说明原因。
5. 多头、空头、观望权重合计 100%，权重代表证据倾向，不代表胜率。
6. Binance Spot 价格可用时作为参考价；K线同一币种不得混用交易所来源。关键数据源基差超过 0.5% 时必须醒目警告并暂停相关实际执行建议。
7. 必须遵循仓库中的 TASK_REPORT_OUTPUT_RULES.md 及其他既有策略规则，不得擅自删减。

## 四、邮件规则
只有在用户要求发送邮件或对应定时任务明确要求发送时才发送。邮件收件人固定为 cao2026feng@outlook.com。邮件正文与聊天报告必须是同一份完整报告；未完成本次数据核验，不得发送完整交易报告邮件。

## 五、修改规则
未经用户明确同意，不得恢复定时采集、自动 watchdog 或后台刷新。任何修改均不得降低以上数据核验和交易报告要求。

## 六、当前唯一允许的采集触发模式
用户明确指令 -> 更新 manual-trigger.txt -> push main -> 等待本次 Actions -> 下载并核验本次 Artifact -> 生成 BTC/ETH 报告。

**核心原则：按用户指令采集；不按时间自动采集。**


## Same-time cross-exchange basis validation (mandatory)
- Never compare Binance Spot live price with a previous candle close to determine exchange basis. Candle close age is not a live quote timestamp.
- Collector must timestamp every secondary live ticker independently (cross_exchange[].observed_at) and timestamp the Binance Spot reference (spot_price.observed_at).
- Compare only valid positive live prices whose timestamps differ by no more than 30 seconds and whose retrieval age is no more than 600 seconds.
- Calculate basis as abs(secondary_live_price - Binance_spot_price) / Binance_spot_price * 100. A verified same-time difference above 0.5% sets execution_allowed=false and execution_status=paused_basis_mismatch.
- If no secondary live quote passes timestamp/freshness checks, set execution_allowed=false and execution_status=paused_basis_unverified. Missing data must never be interpreted as zero basis.
- Do not scale ATR, EMA, swing highs/lows, or other candle structure by the ratio between a live spot price and a stale candle close. Keep candle-derived levels in the source candle series native price scale.
- Preserve conditional levels for observation, but clearly pause live execution when basis is mismatched or unverified. Automated tests must cover stale-close false positives, aligned live prices below/above threshold, and missing/misaligned timestamps.


## 左侧预埋策略规则（永久固定，EMA20不得一票否决）
1. BTCUSDT、ETHUSDT必须独立评估左侧回调做多与左侧反弹做空；不得仅因EMA20相对现价的位置不符合旧条件而判定不可用。
2. EMA20/EMA50仅为辅助评分因素，不是硬性门槛；均线一致加分，不一致减分，但不得单独否决。
3. 左侧做空独立检查现价上方有效前高/摆动高点/结构压力；左侧做多独立检查现价下方有效前低/摆动低点/结构支撑。结构缺失、与现价重叠或距离超过8 ATR，方可因结构证据不足判定不可用。
4. 可用候选必须提供入场区间、止损、TP1、TP2、风险收益比、结构依据、质量评分/等级和收盘K线确认条件。评分低于60仅观察，不建议挂单；预埋价不等于成交。
5. 评分综合大周期趋势、结构位置/距离及EMA20/EMA50辅助方向。成交量拒绝、供需区、成交密集区、VWAP、斐波那契、威科夫等仅在数据实际可用时纳入，不得假称已计算。
6. 止损置于结构失效位置之外；止盈在有利方向，TP1/TP2顺序正确，盈亏比有效。
7. 不得放宽600秒数据新鲜度、Binance参考价、同币种K线来源一致、基差超过0.5%暂停执行、用户手动Push触发及四类策略完整输出等既有保护。
