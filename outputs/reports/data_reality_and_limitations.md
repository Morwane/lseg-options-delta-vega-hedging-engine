# Data Reality and Limitations

## What data is actually available

### LSEG (primary data source)

| Data | Status | Details |
|---|---|---|
| SPY daily close (TRDPRC_1) | Validated | Used as underlying spot in backtest |
| QQQ.O, TLT.O, GLD daily close | Validated | Available for multi-underlying extension |
| SPY option bid/ask (daily) | Validated | 120 call RICs, Jan 2027 expiry, ~30 trading days |
| SPY option IV (TR.ImpliedVolatility) | Not available | EMPTY/ERROR under current entitlement |
| SPY option Greeks (TR.Delta etc.) | Not available | EMPTY/ERROR under current entitlement |
| Snapshot option Greeks | Single-row only | Only 1 row per RIC in audit — not usable in backtest |

### IBKR (optional safety layer)

| Data | Status | Details |
|---|---|---|
| Paper TWS connection (port 7497) | Validated | Connects to simulated paper trading account |
| Account summary | Validated | AvailableFunds, NetLiquidation |
| Underlying contracts | Validated | SPY, QQQ, TLT, GLD |
| Option chains | Validated | Expirations and strikes available |
| Delayed spot (reqMarketDataType(3)) | Validated | SPY ~$714 in operational validation |
| IBKR option Greeks (modelGreeks) | Not available | Requires market data subscription |
| Real IBKR option positions | Not implemented | Future extension |

---

## Greeks engine

Because neither LSEG nor IBKR provide reliable option Greeks under current access:

1. **Black-Scholes IV bisection** solves for implied volatility from the LSEG market mid `(bid+ask)/2`.
2. **Black-Scholes Greeks** are then computed from the solved IV.
3. **Rolling realised-vol fallback** is used if bisection fails (rare; 0% fallback rate in tested period).

This approach is academically standard for reconstructing option Greeks from observed prices.
The `market_vs_bs_gap_bps` diagnostic records the gap between the BS price and the observed mid.

---

## Option universe constraints

- **Confirmed RICs:** 120 SPY call options, Jan 2027 expiry, strikes $50–$645
- **Spot at audit time:** ~$702 (2026-04-29)
- **Moneyness:** All 120 RICs are 8–57% ITM; no near-ATM or OTM calls confirmed
- **Date range:** ~30 trading days (2026-03-18 to 2026-04-29)
- **No puts confirmed** in the current RIC audit

This means the delta-hedging backtest uses a portfolio of deep-ITM calls.
True near-ATM delta hedging (most common in practice) would require higher-strike RICs.

---

## Reference book vs live positions

The daily hedge engine (`run_daily_hedge.py`) uses a **configured reference book**
from `config/demo_portfolio.yaml` — not live IBKR option positions.

Real IBKR option-position ingestion (reading open positions from the IBKR API and
using them as the book) is a planned future extension, not implemented in this version.

---

## Known limitations summary

| Limitation | Impact |
|---|---|
| Confirmed RICs all ITM | Delta hedging results reflect deep-ITM book, not ATM |
| Single expiry | No term structure; no gamma/vega across expirations |
| ~30 days of history | Small sample; results not statistically robust |
| No puts | One-sided universe; no put-call parity verification |
| BS-only Greeks | Model risk if true IV surface deviates from flat BS |
| Flat cost model | 2 bps ignores market impact and bid/ask crossing |
| No real IBKR positions | Book is configured, not live |
| Paper TWS required for IBKR features | Requires TWS 10.x running locally |
