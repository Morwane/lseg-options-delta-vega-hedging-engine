# 00 — Project Brief

## Project name

**Automatic Delta Hedging with Interactive Brokers API**

## One-line description

A Python engine that calculates option Greeks, aggregates portfolio Delta, generates hedge orders, and routes them to Interactive Brokers Paper Trading with conservative safeguards and full audit logs.

## Desk-style positioning

This is a **risk-management and execution prototype** for an options book. It is not an alpha engine. It does not claim to predict the market or guarantee PnL.

The project demonstrates:

- Options pricing and Greeks knowledge.
- Dynamic Delta exposure aggregation.
- Transaction-cost-aware rebalancing rules.
- Broker API integration using Interactive Brokers Paper Trading.
- LSEG historical data usage for backtesting and reporting.
- Honest handling of real data-access limitations.

## Final architecture decision

Because IBKR and LSEG did not return direct option Greeks under the current permissions, the project must use this design:

```text
IBKR = broker connectivity, account summary, contracts, option chains, delayed spot, dry-run/paper orders
LSEG = historical underlying data, backtest inputs, charts, data audit
Black-Scholes = fallback option pricing and Greeks engine
```

## Validated universe

Use liquid ETF underlyings with listed options:

| Underlying | Role | Why useful |
|---|---|---|
| SPY | US equity beta | Most important first implementation target |
| QQQ | US growth / tech beta | Higher vol equity ETF |
| TLT | rates-duration proxy | Different macro risk driver |
| GLD | gold / commodity proxy | Diversifies stress behavior |

Implement SPY first; keep QQQ/TLT/GLD config-ready.

## What the project should output

Minimum deliverables:

```text
outputs/audits/*.csv
outputs/reports/greeks_by_position.csv
outputs/reports/portfolio_exposures.csv
outputs/reports/hedge_orders.csv
outputs/reports/backtest_summary.csv
outputs/executions/orders_YYYYMMDD.csv
outputs/executions/fills_YYYYMMDD.csv
docs/images/hedged_vs_unhedged_pnl.png
docs/images/net_delta_before_after.png
docs/images/transaction_costs_over_time.png
docs/images/drawdown_hedged_vs_unhedged.png
```

## Core financial logic

For each option position:

```text
position_delta = quantity × multiplier × option_delta
position_gamma = quantity × multiplier × option_gamma
position_vega  = quantity × multiplier × option_vega
```

For each underlying:

```text
target_underlying_position = - portfolio_delta
hedge_order_quantity = target_underlying_position - current_underlying_position
```

## Literature anchors

- *Exotic Options and Hybrids* covers vanilla options, Black-Scholes assumptions, the cost of hedging, volatility/skew/term structure, and option sensitivities such as Delta, Gamma, Vega and Theta.
- *Machine Learning for Algorithmic Trading* motivates disciplined backtesting, transaction costs, timing of decisions, and point-in-time data discipline.
- Cont & Vuletic, *Data-driven hedging with generative models* compares delta and delta-vega hedging and explicitly incorporates transaction costs into hedging optimization.
