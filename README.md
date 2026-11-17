# crypto-market-data

Automated public-market collection for BTCUSDT and ETHUSDT.

## Collected data
- Binance Spot ticker price, validating symbol and reading the JSON price field.
- Binance USD-M Futures OHLCV candles for 1d, 12h, 4h, 1h, 15m and 5m (up to 500 per interval).
- Closed-candle indicators: EMA20/50/200, RSI14, MACD(12,26,9), Bollinger Bands(20,2), ATR14, Wilder ADX14 and 20-candle swing high/low.
- Futures context: latest funding rate, open interest and global long/short account ratio where available.
- Source, timestamps, candle counts and request errors are retained.

## Schedule
GitHub Actions runs daily at 00:25 and 12:25 UTC (08:25 and 20:25 Asia/Shanghai). Manual runs are available in Actions → Collect crypto market data → Run workflow.

## Output
The workflow uploads output/market-data.json as an artifact for 7 days; it does not commit market snapshots into the repository.

## Run locally
Requires Python 3.10+ and no third-party packages: python collector.py

## Safety and limitations
- Public market-data endpoints only. No exchange login, API key, secret, withdrawal or trading permission is needed.
- Binance Futures candles are not silently mixed with other exchanges. Failed requests are reported rather than replaced with fabricated values.
- GitHub-hosted runners and exchange endpoints may be delayed, rate-limited or regionally unavailable. Cron is best-effort, not a guaranteed execution time.
- This is a data collector, not an automated trading system or financial advice.
- Never add passwords, API secrets, recovery codes or private account data to this public repository.
