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
5. Do not use workflow_dispatch or any watchdog as a substitute for the per-request push.
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
- There is no cron schedule in collect.yml.
- The scheduled watchdog workflow has been removed; no background workflow may automatically dispatch collection.
- Ordinary documentation edits do not trigger collection.

## Hard failure rules
- A run's success is not enough: artifact, SHA, run number, timestamps, quality report, and trade-analysis must all match.
- If the artifact cannot be downloaded/read or any integrity check fails, mark DATA_UNAVAILABLE and do not produce live price levels from stale data.
- Do not send an email claiming a complete report unless the exact same validated report is also present in the chat.
- Preserve all constraints in TASK_REPORT_OUTPUT_RULES.md, including 600-second maximum data age, Binance Spot reference-price authority when available, same-exchange candles per symbol, and all four left/right long/short strategies for BTC and ETH.
