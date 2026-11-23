# ChatGPT execution protocol (mandatory)

This document fixes the operational integration between ChatGPT and GitHub Actions. It is not a market-data source and does not relax TASK_REPORT_OUTPUT_RULES.md.

## Repository
- Repository: cfcf123/crypto-market-data
- Collector workflow: .github/workflows/collect.yml
- Artifact naming: market-data-<run_number>
- Required artifact files: output/market-data.json, output/data-quality.json, output/trade-analysis.json, trigger.txt, test-status.txt

## Trigger policy: user-command-only
1. All cron/scheduled collection and watchdog auto-dispatch mechanisms are disabled. Do not re-enable them unless the user explicitly asks.
2. Every explicit user request to execute a report (including “执行一次任务” and “严格执行一次任务”) MUST start one fresh collection through a new push to main. Do not reuse a previous successful run, even if its data is less than 600 seconds old.
3. Trigger the run by creating or updating the repository-root file manual-trigger.txt. Its content must be unique for every request and include a UTC timestamp plus a short execution identifier. The collector workflow listens for pushes to this file.
4. Wait for the workflow run caused by that exact push. Match its head_sha to the trigger commit, then verify run status and conclusion. Do not select an unrelated run.
5. The collection workflow has no workflow_dispatch trigger; a push to main is the only supported trigger.
6. Do not make unrelated documentation-only commits as a substitute for a user-triggered run. Use manual-trigger.txt for each requested execution.

## Correct way to inspect Actions from ChatGPT
1. Use the GitHub fetch action on the browser URL:
   https://github.com/cfcf123/crypto-market-data/actions/runs
2. Do NOT use https://api.github.com/... with the generic GitHub fetch action if that connector rejects API URLs.
3. Parse workflow_runs and select the run whose path is .github/workflows/collect.yml, branch is main, and head_sha exactly matches the trigger commit. Record id, run_number, head_sha, event, status, conclusion, created_at, updated_at.
4. If status is queued or in_progress, re-fetch Actions until that exact run completes. Never read an older artifact as the current run.
5. Once completed with conclusion=success, call fetch_workflow_run_jobs(repo_full_name, run_id) and require collection, validation, analysis, and artifact-upload steps to be successful.
6. Call fetch_workflow_run_artifacts(repo_full_name, run_id). Select only artifact named market-data-<same run_number>, require expired=false, and record artifact id, created_at, digest.
7. Download that exact artifact with download_workflow_artifact. Inspect its ZIP and require all five files. Cross-check trigger.txt run_id/run_number/sha against Actions metadata and ensure all JSON generated_at timestamps agree.
8. Require data-quality.json and trade-analysis.json to exist and parse successfully. Require trade-analysis.json for BOTH BTCUSDT and ETHUSDT and validate the mandatory four strategy branches per symbol before writing the report. Do not perform a separate data-age/freshness gate after download; the user's explicit push already starts a new collection for every task.
9. Record run id, run number, head SHA, artifact id/digest, generated_at, data age, and workflow conclusion in the report.

## Workflow trigger scope
- collect.yml triggers on push to main only when manual-trigger.txt, Python source, requirements files, or collect.yml changes.
- Push is the only collection trigger; workflow_dispatch is disabled.
- There is no cron schedule in collect.yml.
- The scheduled watchdog workflow has been removed; no background workflow may automatically dispatch collection.
- Ordinary documentation edits do not trigger collection.

## Hard failure rules
- A run's success is not enough: artifact, SHA, run number, timestamps, quality report, and trade-analysis must all match.
- If the artifact cannot be downloaded/read or any integrity check fails, mark DATA_UNAVAILABLE and do not produce live price levels from stale data.
- Do not send an email claiming a complete report unless the exact same validated report is also present in the chat.
- Preserve all constraints in TASK_REPORT_OUTPUT_RULES.md, including Binance Spot reference-price authority when available, same-exchange candles per symbol, and all four left/right long/short strategies for BTC and ETH. Do not apply a separate post-download data-age/freshness threshold; every user request must trigger a new push and use only that push's artifact.


## Permanent user preference: no scheduled collection
The user explicitly requires that market data collection must NOT run every 10 minutes or on any other automatic schedule. Every report execution is initiated only by the user's explicit chat instruction. For each such instruction:
- Generate a unique trigger marker in repository-root `manual-trigger.txt` and push it to `main`.
- That push must trigger exactly one fresh collection run.
- Wait for and verify the run and its matching artifact before analysis.
- Never reuse a prior run's artifact, regardless of its age.
- No cron, scheduled workflow, watchdog, stale-data auto-dispatch, or background refresh may be reintroduced unless the user explicitly changes this preference.
- Do not use unrelated commits to trigger a run.
- This preference applies across new chat windows and is recorded here as the repository's durable source of truth.


## Same-time cross-exchange basis validation (mandatory)
- Never compare Binance Spot live price with a previous candle close to determine exchange basis. Candle close age is not a live quote timestamp.
- Collector must timestamp every secondary live ticker independently (cross_exchange[].observed_at) and timestamp the Binance Spot reference (spot_price.observed_at).
- Compare only valid positive live prices whose timestamps differ by no more than 30 seconds.
- Calculate basis as abs(secondary_live_price - Binance_spot_price) / Binance_spot_price * 100. A verified same-time difference above 0.5% sets execution_allowed=false and execution_status=paused_basis_mismatch.
- If no secondary live quote has a valid aligned timestamp, set execution_allowed=false and execution_status=paused_basis_unverified. Missing data must never be interpreted as zero basis.
- Do not scale ATR, EMA, swing highs/lows, or other candle structure by the ratio between a live spot price and a stale candle close. Keep candle-derived levels in the source candle series native price scale.
- Preserve conditional levels for observation, but clearly pause live execution when basis is mismatched or unverified. Automated tests must cover stale-close false positives, aligned live prices below/above threshold, and missing/misaligned timestamps.


## 左侧预埋策略规则（永久固定，EMA20不得一票否决）
1. BTCUSDT、ETHUSDT必须独立评估左侧回调做多与左侧反弹做空；不得仅因EMA20相对现价的位置不符合旧条件而判定不可用。
2. EMA20/EMA50仅为辅助评分因素，不是硬性门槛；均线一致加分，不一致减分，但不得单独否决。
3. 左侧做空独立检查现价上方有效前高/摆动高点/结构压力；左侧做多独立检查现价下方有效前低/摆动低点/结构支撑。结构缺失、与现价重叠或距离超过8 ATR，方可因结构证据不足判定不可用。
4. 可用候选必须提供入场区间、止损、TP1、TP2、风险收益比、结构依据、质量评分/等级和收盘K线确认条件。评分低于60仅观察，不建议挂单；预埋价不等于成交。
5. 评分综合大周期趋势、结构位置/距离及EMA20/EMA50辅助方向。成交量拒绝、供需区、成交密集区、VWAP、斐波那契、威科夫等仅在数据实际可用时纳入，不得假称已计算。
6. 止损置于结构失效位置之外；止盈在有利方向，TP1/TP2顺序正确，盈亏比有效。
7. 不得取消本次 Push 与本次 Artifact 的对应关系、Binance参考价、同币种K线来源一致、基差超过0.5%暂停执行、用户手动Push触发及四类策略完整输出等既有保护。


## 威科夫结构确认模块（WYCKOFF-SEQUENCE-V2，永久固定）
1. BTCUSDT、ETHUSDT及各可用周期独立分析；只使用同一交易所、已收盘OHLCV，不混合成交量或K线来源。
2. 多头结构按Spring候选（可选）→ SOS候选 → SOS后回踩测试 → LPS确认；空头结构按UTAD候选（可选）→ SOW候选 → SOW后反抽测试 → LPSY确认。Spring/UTAD不是必需条件。
3. SOS筛选条件：收盘有效突破此前结构区间阻力、上涨K线收盘位置靠近高点（至少70%）、成交量不低于此前均量1.15倍、K线波幅不低于此前平均波幅1.20倍。SOW按相反方向对称判定（收盘跌破支撑、收盘位置不高于30%、量能至少1.15倍、波幅至少1.20倍）。阈值是保守筛选参数，不是市场定律。
4. SOS/SOW只能先标记候选/等待测试。SOS后LPS确认需在突破位附近回踩、收盘守住原突破位、测试阶段成交量均值低于突破K线的80%、平均波幅低于突破K线的85%，并出现方向性拒绝及后续跟进。SOW后LPSY按镜像规则判定。
5. 若回踩/反抽收盘重新进入原区间，标记突破失败；若测试量能或波幅未收缩，标记测试弱/未确认；数据不足时标记等待，不得补造事件。
6. 报告展示结构区间、Spring/UTAD候选、SOS/SOW状态、LPS/LPSY状态、突破/测试位置、量能/波幅相对值、失效条件及对应周期。状态区分“未发现、候选、等待确认、已确认、失败、数据不足”。
7. 多周期证据冲突时明确披露（例如周线SOW、4小时SOS），不得只选择有利方向的周期。威科夫证据仅作有限权重辅助，不得覆盖多周期趋势、价格结构或风险约束。
8. 单点OI、资金费率或单根放量阳线不得用来断言空头回补/挤空。缺少连续OI变化、强平数据和主动买卖成交流（taker flow）时，必须写“无法区分真实需求与空头回补”。
9. SOS/LPS与SOW/LPSY是结构证据，不是自动交易指令；实际点位仍由四类策略引擎独立计算。EMA20/EMA50只参与辅助评分，不能单独否决左侧策略。
