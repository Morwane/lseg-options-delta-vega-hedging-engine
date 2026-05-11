# LSEG Listed-Options Delta-Hedging & Delta-Vega Optimization Engine
## Final Project Summary

---

## Project identity

| Field | Value |
|---|---|
| Project name | LSEG Listed-Options Delta-Hedging & Delta-Vega Optimization Engine |
| Language | Python 3.11 |
| Primary data source | LSEG Data Library (historical bid/ask for 120 SPY call RICs) |
| Greeks engine | Black-Scholes IV bisection from LSEG market mid |
| Hedge engine | Transaction-cost-aware delta hedger + scipy delta-vega optimizer |
| Broker integration | IBKR Paper Trading (optional, port 7497 only) |
| Execution model | Dry-run by default; paper execute requires explicit CLI flag + per-order `y/N` |

---

## What was built

### Core engine

- **Black-Scholes module** (`src/pricing/`): price, delta, gamma, vega, theta; IV bisection solver
- **Portfolio module** (`src/portfolio/`): OptionPosition, PortfolioBook, exposure aggregation
- **Hedging module** (`src/hedging/`): delta hedge recommendation, rebalance rules, cost estimation
- **LSEG data pipeline** (`src/data/`, `src/backtesting/`): loader, quality reporter, IV hierarchy
- **Historical backtest** (`src/backtesting/historical_delta_hedge_engine.py`): 30-day SPY backtest
- **Delta-Vega optimizer** (`src/optimization/`): hedge universe, objective function, scipy optimizer
- **4-method comparison backtest** (`src/backtesting/optimized_hedge_backtest.py`)
- **IBKR broker integration** (`src/broker/`, `src/data/ibkr_connection.py`): paper-only

### Scripts

- `run_demo.py` — offline Greeks + hedge demo
- `run_lseg_historical_hedge_backtest.py` — LSEG delta-only backtest
- `run_delta_vega_hedge_optimizer.py` — 4-method optimizer comparison
- `run_daily_hedge.py` — IBKR dry-run / paper-execute
- `audit_lseg_option_universe.py` — LSEG data quality audit
- `build_readme_outputs.py` — regenerate all charts and reports

### Tests

- **311 tests, all passing** (281 original + 30 optimizer tests)

---

## LSEG backtest results (synthetic mock data)

| Metric | Value |
|---|---|
| Period | 2026-03-18 → 2026-04-28 (30 days) |
| Reference book | 5 nearest-ITM SPY Jan 2027 calls |
| Cumulative P&L (hedged) | −$1,706.66 |
| Cumulative P&L (unhedged) | −$1,826.00 |
| Hedge improvement | +$119.34 |
| Total transaction costs | $74.48 |
| Rebalance days | 17/30 (56.7%) |
| IV solve success rate | 100% (0% fallback) |

---

## Optimizer comparison (synthetic mock data)

| Method | Description |
|---|---|
| no_hedge | No hedge; baseline book P&L |
| delta_only | Underlying-only delta neutralisation |
| delta_vega | Underlying + best single LSEG option leg |
| optimized | scipy SLSQP: underlying + ≤2 LSEG option legs |

Run `python scripts/run_delta_vega_hedge_optimizer.py --mock` for current results.

---

## Safety summary

- Paper trading only (live port 7496 hard-blocked)
- Default mode: dry-run (no orders sent)
- Per-order confirmation required for paper execute
- Notional cap: $25,000 per order
- IBKR real option positions not ingested

---

## Key files to review

| File | Purpose |
|---|---|
| `src/optimization/delta_vega_optimizer.py` | Core optimizer |
| `src/backtesting/optimized_hedge_backtest.py` | 4-method comparison |
| `src/backtesting/historical_delta_hedge_engine.py` | Delta-only backtest engine |
| `src/pricing/black_scholes.py` | Greeks computation |
| `src/pricing/implied_vol.py` | IV bisection |
| `tests/test_delta_vega_optimizer.py` | Optimizer unit tests |
| `outputs/reports/` | All backtest and methodology reports |
| `outputs/research/` | Optimizer comparison outputs |
| `docs/images/` | All charts |
