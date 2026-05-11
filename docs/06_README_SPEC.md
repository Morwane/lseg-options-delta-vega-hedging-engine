# 06 — README Specification

The README must be honest, professional, and desk-oriented.

## Required title

```markdown
# Automatic Delta Hedging with Interactive Brokers API
```

## Required opening paragraph

This project implements an automatic delta hedging engine for option portfolios using Interactive Brokers Paper Trading. Because direct option Greeks were not available under the current IBKR and LSEG permissions, the engine implements a Black-Scholes fallback Greeks module and uses LSEG historical underlying data for backtesting.

## Required sections

1. Project Overview
2. What This Project Is / Is Not
3. Validated Data Access
4. Architecture
5. Methodology
6. Black-Scholes Fallback Greeks
7. Delta Hedging Logic
8. Transaction-Cost-Aware Rebalancing
9. LSEG Historical Backtest
10. IBKR Paper Trading Dry-Run
11. Outputs
12. Charts
13. How to Run
14. Tests
15. Limitations
16. Interview / Desk Use Case

## Required data access table

| Component | Status | Notes |
|---|---:|---|
| IBKR Paper Connection | Validated | TWS Simulated / Paper Trading on port 7497 |
| IBKR Underlying Contracts | Validated | SPY, QQQ, TLT, GLD |
| IBKR Option Chains | Validated | Expirations and strikes available |
| IBKR Delayed Spot | Validated | SPY delayed snapshot worked |
| IBKR Option Greeks | Not available | Current market data permissions did not return modelGreeks |
| LSEG Session | Validated | Historical underlying prices available |
| LSEG Direct Option Greeks | Not available in audit | Fields returned EMPTY/ERROR |
| Black-Scholes Fallback | Implemented | Used for price and Greeks |

## Required methodology formula block

```text
position_delta = quantity × multiplier × option_delta
portfolio_delta = sum(position_delta by underlying)
target_underlying_position = - portfolio_delta
hedge_order = target_underlying_position - current_underlying_position
```

## Required charts

Place generated charts in `docs/images/`:

```text
hedged_vs_unhedged_pnl.png
net_delta_before_after.png
hedge_orders_by_underlying.png
transaction_costs_over_time.png
drawdown_hedged_vs_unhedged.png
gamma_vega_monitoring.png
ibkr_audit_summary.png
lseg_audit_summary.png
```

## Required commands

```bash
pip install -r requirements.txt
pytest -q
python scripts/run_demo.py
python scripts/run_lseg_backtest.py
python scripts/run_daily_hedge.py --dry-run
```

## Required safety disclaimer

This repository is for research, education, and paper-trading demonstration only. It is not investment advice and it does not place live orders. Live trading is intentionally disabled.

## Required CV bullet

Built an automatic delta hedging engine for option portfolios using Interactive Brokers Paper Trading API, combining IBKR option-chain discovery and execution logs with LSEG historical data, Black-Scholes fallback Greeks, transaction-cost-aware rebalancing rules, and hedged vs unhedged P&L diagnostics.

## Required interview explanation

The goal was not to build an alpha bot. It was a risk-management prototype for an options book. The engine computes Greeks, aggregates Delta by underlying, generates hedge orders, applies cost-aware thresholds, and logs paper-trading execution diagnostics.
