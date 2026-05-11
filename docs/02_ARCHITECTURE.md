# 02 — Repository Architecture

## Target tree

```text
automatic-delta-hedging-interactive-brokers-api/
│
├── config/
│   ├── universe.yaml
│   ├── demo_portfolio.yaml
│   ├── hedge_rules.yaml
│   └── broker.yaml
│
├── src/
│   ├── data/
│   │   ├── __init__.py
│   │   ├── lseg_loader.py
│   │   ├── ibkr_connection.py
│   │   └── data_quality.py
│   │
│   ├── pricing/
│   │   ├── __init__.py
│   │   ├── black_scholes.py
│   │   └── implied_vol.py
│   │
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── positions.py
│   │   ├── exposures.py
│   │   └── pnl.py
│   │
│   ├── hedging/
│   │   ├── __init__.py
│   │   ├── delta_hedger.py
│   │   ├── rebalance_rules.py
│   │   └── transaction_costs.py
│   │
│   ├── broker/
│   │   ├── __init__.py
│   │   ├── contract_mapper.py
│   │   ├── order_builder.py
│   │   ├── paper_executor.py
│   │   └── execution_logger.py
│   │
│   └── reporting/
│       ├── __init__.py
│       ├── charts.py
│       ├── tables.py
│       └── tearsheet.py
│
├── scripts/
│   ├── audit_ibkr_basic.py
│   ├── audit_ibkr_option_chains.py
│   ├── audit_ibkr_option_greeks.py
│   ├── audit_lseg_connection.py
│   ├── audit_lseg_options_access.py
│   ├── run_demo.py
│   ├── run_lseg_backtest.py
│   ├── run_daily_hedge.py
│   └── build_readme_outputs.py
│
├── outputs/
│   ├── audits/
│   ├── reports/
│   ├── charts/
│   ├── executions/
│   └── logs/
│
├── tests/
│   ├── test_black_scholes.py
│   ├── test_implied_vol.py
│   ├── test_exposures.py
│   ├── test_delta_hedger.py
│   ├── test_transaction_costs.py
│   └── test_order_builder.py
│
├── docs/
│   └── images/
│
├── CLAUDE.md
├── README.md
├── requirements.txt
├── pyproject.toml
└── .gitignore
```

## Module responsibilities

### `src/pricing/black_scholes.py`

Pure math module. No broker calls. No LSEG calls. Should include:

- `BlackScholesInputs` dataclass
- `black_scholes_price()`
- `black_scholes_delta()`
- `black_scholes_gamma()`
- `black_scholes_vega()`
- `black_scholes_theta()`
- optional `black_scholes_all()` returning a dataclass/dict

### `src/pricing/implied_vol.py`

Pure numerical solver. Should include:

- `implied_vol_bisection()`
- robust bounds, max iterations, tolerance
- graceful `None` or `np.nan` return when impossible

### `src/portfolio/positions.py`

Domain objects and config parsing:

- `OptionPosition`
- `UnderlyingPosition`
- `PortfolioBook`
- YAML loader for `config/demo_portfolio.yaml`

### `src/portfolio/exposures.py`

Book-level Greeks aggregation:

- per-position Greeks
- group by underlying
- net Delta/Gamma/Vega/Theta by underlying
- portfolio totals

### `src/hedging/delta_hedger.py`

Hedge-order recommendation logic:

```text
target_underlying_position = - portfolio_delta
hedge_order_quantity = target_underlying_position - current_underlying_position
```

Must support thresholds and max notional constraints.

### `src/hedging/rebalance_rules.py`

Rules:

- delta threshold
- max order notional
- min rebalance interval
- manual approval flag
- paper-only flag

### `src/hedging/transaction_costs.py`

Cost estimates:

- half-spread cost if bid/ask available
- fallback bps cost from config
- aggregate estimated cost by order and by day

### `src/data/lseg_loader.py`

LSEG historical data loader:

- open session safely
- fetch underlying history
- try configured fields in priority order
- return clean DataFrame
- fail gracefully when LSEG unavailable

### `src/data/ibkr_connection.py`

IBKR connection helper:

- connect to TWS paper on `127.0.0.1:7497`
- delayed market data mode
- disconnect safely
- never use live port

### `src/broker/order_builder.py`

Converts hedge recommendations into IBKR-style orders. Must not send orders.

### `src/broker/paper_executor.py`

Paper execution wrapper. Must require explicit approval.

### `src/reporting/charts.py`

Matplotlib charts for README. No seaborn required.

## Config files

### `config/universe.yaml`

```yaml
underlyings:
  SPY:
    ibkr_symbol: SPY
    ibkr_exchange: SMART
    ibkr_currency: USD
    lseg_ric_candidates: [SPY, SPY.N, SPY.P]
    multiplier: 100
  QQQ:
    ibkr_symbol: QQQ
    ibkr_exchange: SMART
    ibkr_currency: USD
    lseg_ric_candidates: [QQQ.O, QQQ, QQQ.OQ]
    multiplier: 100
  TLT:
    ibkr_symbol: TLT
    ibkr_exchange: SMART
    ibkr_currency: USD
    lseg_ric_candidates: [TLT.O, TLT, TLT.OQ]
    multiplier: 100
  GLD:
    ibkr_symbol: GLD
    ibkr_exchange: SMART
    ibkr_currency: USD
    lseg_ric_candidates: [GLD, GLD.P, GLD.N]
    multiplier: 100
```

### `config/hedge_rules.yaml`

```yaml
paper_trading_only: true
allow_live_trading: false
dry_run_default: true
manual_approval_required: true

delta_threshold_shares: 100
max_order_notional_usd: 25000
min_rebalance_interval_minutes: 30
fallback_transaction_cost_bps: 2.0
```

### `config/broker.yaml`

```yaml
ibkr:
  host: 127.0.0.1
  paper_port: 7497
  live_port_blocked: 7496
  client_id: 101
  market_data_type: delayed
```
