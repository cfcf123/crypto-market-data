# ChatGPT execution protocol (mandatory)

This document fixes the operational integration between ChatGPT and GitHub Actions. It is not a market-data source and does not relax TASK_REPORT_OUTPUT_RULES.md.

## Repository
- Repository: cfcf123/crypto-market-data
- Collector workflow: .github/workflows/collect.yml
- Workflow ID: 421501405 (verify from current run metadata; do not hardcode a stale run ID)
- Artifact naming: market-data-<run_number>
- Required artifact files: output/market-data.json, output/data-quality.json, output/trade-analysis.json, trigger.txt, test-status.txt

## Correct way to inspect Actions from ChatGPT
1. Use the GitHub fetch action on the browser URL:
   https://github.com/cfcf123/crypto-market-data/actions/runs
2. Do NOT use https://api.github.com/... with the generic GitHub fetch action; that connector may reject API URLs even when the repository itself is accessible.
3. Parse workflow_runs and select the newest run whose path is .github/workflows/collect.yml and branch is main. Record id, run_number, head_sha, event, status, conclusion, created_at, updated_at.
4. If status is queued or in_progress, wait by re-fetching the Actions browser URL; do not read an older artifact as the current run.
5. Once completed with conclusion=success, call fetch_workflow_run_jobs(repo_full_name, run_id) and require every collection, validation, analysis, and artifact-upload step to be successful.
6. Call fetch_workflow_run_artifacts(repo_full_name, run_id). Select only artifact named market-data-<same run_number>, require expired=false, and record artifact id, created_at, digest.
7. Download that exact artifact with download_workflow_artifact. Inspect its ZIP and require all five files. Cross-check trigger.txt run_id/run_number/sha against Actions metadata and ensure all JSON generated_at timestamps agree.
8. Require data-quality.json to report age_seconds <= 600 and all required symbol/timeframe/context freshness checks valid. Require trade-analysis.json for BOTH BTCUSDT and ETHUSDT and validate the mandatory four strategy branches per symbol before writing the report.
9. Record run id, run number, head SHA, artifact id/digest, generated_at, data age, and workflow conclusion in the report.

## Manual execution / recovery
- The generic GitHub connector currently exposes read and rerun operations but may not expose workflow_dispatch. Never claim that workflow_dispatch was invoked unless a dispatch action actually returned success.
- The collector workflow has a push-to-main trigger. If a fresh run is not available and direct dispatch is unavailable, use an explicitly authorized, harmless documentation-only commit (for example, update this protocol file) to trigger the existing push workflow. Then inspect the new run using the exact procedure above. Never make a dummy change to trading logic merely to trigger a run.
- Do not treat a watchdog run as a collection run. Filter by workflow path/name and verify its artifact/run metadata.
- If a recent successful run is already within the 600-second data-age limit, reuse that exact run/artifact rather than launching duplicate concurrent collections.
- If the newest collection failed, inspect its job steps/logs and artifact before deciding whether to rerun failed jobs. Do not silently substitute a prior successful snapshot.

## Hard failure rules
- A run's success is not enough: artifact, SHA, run number, timestamps, quality report, and trade-analysis must all match.
- If the artifact cannot be downloaded/read or any integrity check fails, mark DATA_UNAVAILABLE and do not produce live price levels from stale data.
- Do not send an email claiming a complete report unless the exact same validated report is also present in the chat.
- Preserve all constraints in TASK_REPORT_OUTPUT_RULES.md, including 600-second maximum data age, Binance Spot reference-price authority when available, same-exchange candles per symbol, and all four left/right long/short strategies for BTC and ETH.
