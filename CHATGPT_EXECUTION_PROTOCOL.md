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
8. Require data-quality.json to report age_seconds <= 600 and all required symbol/timeframe/context freshness checks valid. Require trade-analysis.json for BOTH BTCUSDT and ETHUSDT and validate the mandatory four strategy branches per symbol before writing the report.
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
- Preserve all constraints in TASK_REPORT_OUTPUT_RULES.md, including 600-second maximum data age, Binance Spot reference-price authority when available, same-exchange candles per symbol, and all four left/right long/short strategies for BTC and ETH.


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
