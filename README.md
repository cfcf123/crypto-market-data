# crypto-market-data

Automated public-market collection for BTCUSDT, ETHUSDT and Binance USD-M NVDAUSDT perpetual.

## Collected data
- BTCUSDT/ETHUSDT: Binance Spot ticker prices are authoritative whenever Binance succeeds. NVDAUSDT is a perpetual contract, so its authoritative reference is the Binance USD-M Futures perpetual ticker (never a spot ticker).
- Closed OHLCV candles for 1d, 12h, 4h, 1h, 15m, 5m and 1m. Binance USD-M Futures is preferred, with Bybit Linear, OKX USDT Swap and a clearly labeled Binance Spot technical fallback.
- Weekly (1w) and monthly (1M) candles are aggregated from the same exchange's daily candles. Aggregation follows the source daily-candle calendar (including UTC+8 boundaries) and rejects incomplete periods.
- Closed-candle indicators: EMA20/50/200, RSI14, MACD(12,26,9), Bollinger Bands(20,2), ATR14, Wilder ADX14 and 20-candle swing high/low.
- Futures context: latest funding rate, open interest and global long/short account ratio where available.
- Conservative Wyckoff evidence per timeframe: accumulation/distribution watch zones, Spring/UTAD candidates, SOS/SOW candidates, relative volume and effort-vs-result. Signals remain hypotheses and do not generate trades.
- Data-quality validation checks freshness, source consistency, closed candles, OHLCV integrity, and sufficient complete weekly/monthly history for Wyckoff analysis. The quality report includes spot and per-timeframe age diagnostics.
- `decision_engine.py` fuses monthly, weekly, daily, 12h, 4h, 1h and 15m evidence independently for BTCUSDT, ETHUSDT and NVDAUSDT. NVDAUSDT receives its own four conditional setups and strategy weights; BTC/ETH scoring rules remain unchanged. Synchronized 1h returns provide rolling 24h/72h/168h Pearson correlations between NVDA and BTC/ETH. NVDA session context distinguishes its 24/7 perpetual from the US equity clock; the clock label is not a holiday calendar. It publishes long/short/neutral evidence weights, raises neutral weight when timeframe coverage is weak or signals conflict, and provides four conditional setups: breakout long, pullback long, rebound short and breakdown short. Pullback/rebound zones are shown only when correctly located below/above the Binance reference price; otherwise the setup is explicitly unavailable. All triggers require closed-candle confirmation. Funding and global long/short account ratio add only a small bounded contrarian context adjustment (maximum ±0.04); open interest is displayed as context but does not affect direction without a reliable time series. Weights are evidence tilt, not win probabilities. The quality report exposes per-symbol spot age, per-timeframe latest-close age and age limit, weekly/monthly close age, and collection duration.
- `generated_at` and `collection_completed_at` are stamped only after all collection and calculations finish; `collection_started_at` records the start, so consumers can distinguish collection duration from snapshot age.

## Schedule and recovery
- Primary collector: every 10 minutes at minutes 03, 13, 23, 33, 43 and 53 UTC.
- Freshness watchdog: checks every 5 minutes at offset minutes and calls `workflow_dispatch` when the latest successful collection is older than 570 seconds, leaving a safety margin for artifact creation time. It avoids duplicate dispatches when a collection is already queued/running and cancels a collection stuck for more than 15 minutes.
- Manual collection: Actions -> Collect crypto market data -> Run workflow.
- Pushes to `main` also trigger collection and validation.
- GitHub scheduled events are best-effort and may be delayed or dropped under platform load. The watchdog is a recovery layer, not a guarantee of exact start times.

## Output
The collection workflow uploads `output/market-data.json`, `output/data-quality.json` and `output/trade-analysis.json` as artifacts for 7 days; it does not commit market snapshots into the repository.

## Run locally
Requires Python 3.10+ and no third-party packages: `python collector.py`

## Safety and limitations
- Public market-data endpoints only. No exchange login, API key, secret, withdrawal or trading permission is needed.
- Candle series are never mixed across exchanges. Failed requests are reported rather than replaced with fabricated data.
- GitHub-hosted runners and exchange endpoints may be delayed, rate-limited or regionally unavailable. Cron is best-effort, not a guaranteed execution time.
- This is a data collector, not an automated trading system or financial advice.
- Never add passwords, API secrets, recovery codes or private account data to this public repository.


## News and event-risk collection
- Seven-day RSS snapshot: crypto/ETF flows, Fed and US macro, Trump policy, geopolitics, Nvidia/AI semiconductors, Binance/CZ/CoinGlass.
- Google News topic searches plus Federal Reserve, SEC and White House official RSS.
- Feed health, links, publishers and publication times are retained. Headlines are not trading signals.
- Structured economic calendar and live ETF/derivatives flow sources must be disclosed separately when unavailable.


### NVDAUSDT price-source policy

NVDAUSDT reference price uses a perpetual-contract ticker, not NVIDIA stock spot. Binance USD-M is tried first; if unavailable, the collector falls back to OKX USDT Swap and then Bybit Linear perpetual tickers. The source, contract instrument, quote type, and retrieval timestamp are retained. Equity spot quotes (e.g. Yahoo Finance/Nasdaq) may be used for separate stock-market context and cross-checks, but must never be substituted as an NVDAUSDT perpetual execution price. BTCUSDT and ETHUSDT continue to require Binance Spot as their primary reference price.
