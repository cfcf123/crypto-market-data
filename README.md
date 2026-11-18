# crypto-market-data

Automated public-market collection for BTCUSDT and ETHUSDT.

## Collected data
- Binance Spot ticker prices are authoritative whenever Binance succeeds; fallback prices are explicitly labeled.
- Closed OHLCV candles for 1d, 12h, 4h, 1h, 15m, 5m and 1m. Binance USD-M Futures is preferred, with Bybit Linear, OKX USDT Swap and a clearly labeled Binance Spot technical fallback.
- Weekly (1w) and monthly (1M) candles are aggregated from the same exchange's daily candles. Aggregation follows the source daily-candle calendar (including UTC+8 boundaries) and rejects incomplete periods.
- Closed-candle indicators: EMA20/50/200, RSI14, MACD(12,26,9), Bollinger Bands(20,2), ATR14, Wilder ADX14 and 20-candle swing high/low.
- Futures context: latest funding rate, open interest and global long/short account ratio where available.
- Conservative Wyckoff evidence per timeframe: accumulation/distribution watch zones, Spring/UTAD candidates, SOS/SOW candidates, relative volume and effort-vs-result. Signals remain hypotheses and do not generate trades.
- Data-quality validation checks freshness, source consistency, closed candles, OHLCV integrity, and sufficient complete weekly/monthly history for Wyckoff analysis. The quality report exposes per-symbol spot age, per-timeframe latest-close age and age limit, weekly/monthly close age, and collection duration.
- `generated_at` and `collection_completed_at` are stamped only after all collection and calculations finish; `collection_started_at` records the start, so consumers can distinguish collection duration from snapshot age.

## Schedule
GitHub Actions runs daily at 00:25 and 12:25 UTC (08:25 and 20:25 Asia/Shanghai). Manual runs are available in Actions -> Collect crypto market data -> Run workflow. Pushes to main also trigger a validation/collection run.

## Output
The workflow uploads output/market-data.json and output/data-quality.json as artifacts for 7 days; it does not commit market snapshots into the repository.

## Run locally
Requires Python 3.10+ and no third-party packages: python collector.py

## Safety and limitations
- Public market-data endpoints only. No exchange login, API key, secret, withdrawal or trading permission is needed.
- Candle series are never mixed across exchanges. Failed requests are reported rather than replaced with fabricated values.
- GitHub-hosted runners and exchange endpoints may be delayed, rate-limited or regionally unavailable. Cron is best-effort, not a guaranteed execution time.
- This is a data collector, not an automated trading system or financial advice.
- Never add passwords, API secrets, recovery codes or private account data to this public repository.
