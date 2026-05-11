# 03 — Implementation Plan

## Phase 0 — Preserve existing audit scripts

Do not delete existing audit scripts. Move or keep them under `scripts/`.

Existing useful scripts:

```text
scripts/test_ibkr_connection.py
scripts/audit_ibkr_basic.py
scripts/audit_ibkr_option_chains.py
scripts/audit_ibkr_option_greeks.py
scripts/audit_ibkr_delayed_market_data.py
scripts/audit_lseg_connection.py
scripts/audit_lseg_options_access.py
```

## Phase 1 — Repo foundation

Create:

- folder tree
- `requirements.txt`
- `pyproject.toml`
- `.gitignore`
- config YAML files
- package `__init__.py` files

Acceptance:

```bash
python -m compileall src scripts
```

## Phase 2 — Black-Scholes engine

Implement:

- price
- delta
- gamma
- vega
- theta
- all-in-one output
- implied vol bisection

Acceptance:

```bash
pytest -q tests/test_black_scholes.py tests/test_implied_vol.py
```

Minimum numeric sanity:

- call Delta between 0 and 1
- put Delta between -1 and 0
- Gamma positive
- Vega positive
- option price positive
- implied vol solver approximately recovers input vol from model price

## Phase 3 — Portfolio exposures

Implement:

- `OptionPosition`
- `PortfolioBook`
- config loader
- per-position Greek calculation
- portfolio aggregation by underlying

Acceptance:

```bash
pytest -q tests/test_exposures.py
python scripts/run_demo.py
```

Expected outputs:

```text
outputs/reports/greeks_by_position.csv
outputs/reports/portfolio_exposures.csv
outputs/reports/hedge_orders.csv
```

## Phase 4 — Delta hedge rules

Implement:

- target hedge quantity
- current hedge position input
- threshold rule
- max notional rule
- transaction cost estimate
- order side BUY/SELL
- dry-run recommendation object

Acceptance:

```bash
pytest -q tests/test_delta_hedger.py tests/test_transaction_costs.py
python scripts/run_demo.py
```

## Phase 5 — LSEG backtest mode

Implement:

- `lseg_loader.py`
- `run_lseg_backtest.py`
- historical underlying returns
- rolling realized volatility input, e.g. 20d/60d
- synthetic ATM option book
- daily Greeks recalculation
- daily hedge order simulation
- hedged vs unhedged PnL
- transaction costs

Acceptance:

```bash
python scripts/run_lseg_backtest.py
```

Expected outputs:

```text
outputs/reports/hedged_vs_unhedged_pnl.csv
outputs/reports/daily_exposures.csv
outputs/reports/daily_hedge_orders.csv
outputs/reports/transaction_costs.csv
```

## Phase 6 — IBKR dry-run daily hedge

Implement:

- `ibkr_connection.py`
- delayed spot retrieval
- account summary reader
- positions reader
- contract mapper
- dry-run hedge recommendation

Acceptance:

```bash
python scripts/run_daily_hedge.py --dry-run
```

Must not send orders.

## Phase 7 — IBKR paper execution mode

Implement only after dry-run works.

Requirements:

- `--paper-execute` flag required
- terminal prompt required: `Send PAPER order? y/N`
- default answer must be No
- log all proposed and executed orders
- no live mode

Acceptance:

```bash
python scripts/run_daily_hedge.py --paper-execute
```

Only in TWS Simulated / Paper Trading.

## Phase 8 — Reporting and README images

Implement:

- charts
- tables
- tearsheet markdown
- README chart gallery

Acceptance:

```bash
python scripts/build_readme_outputs.py
```

## Phase 9 — Final test sweep

Run:

```bash
pytest -q
python -m compileall src scripts
python scripts/run_demo.py
python scripts/run_lseg_backtest.py
python scripts/run_daily_hedge.py --dry-run
```

Project is finished when all pass or fail gracefully with clear environment messages.
