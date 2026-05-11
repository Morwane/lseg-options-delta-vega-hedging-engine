# 08 — Next Prompts for Claude Code

Use these prompts one by one. Do not give Claude everything at once.

## Prompt A — Initialize and inspect

```text
Read @CLAUDE.md and all files under @docs/. Do not modify files yet. Summarize the project objective, the validated IBKR/LSEG access, the safety constraints, and the first implementation phase.
```

## Prompt B — Create structure

```text
Read @docs/02_ARCHITECTURE.md. Create the target repository structure, config files, pyproject.toml, requirements.txt, .gitignore, and package __init__.py files. Do not implement business logic yet. Run python -m compileall src scripts and report results.
```

## Prompt C — Implement pricing engine

```text
Read @docs/04_MODULE_SPECS.md. Implement src/pricing/black_scholes.py and src/pricing/implied_vol.py with tests. Use Python 3.11 typing and dataclasses. Run pytest -q tests/test_black_scholes.py tests/test_implied_vol.py and fix failures.
```

## Prompt D — Implement exposures and demo

```text
Implement config/demo_portfolio.yaml, src/portfolio/positions.py, src/portfolio/exposures.py, and scripts/run_demo.py. The demo must run offline without IBKR or LSEG. It must output greeks_by_position.csv, portfolio_exposures.csv, and hedge_orders.csv. Run pytest -q tests/test_exposures.py and python scripts/run_demo.py.
```

## Prompt E — Implement hedge rules

```text
Implement src/hedging/delta_hedger.py, src/hedging/rebalance_rules.py, src/hedging/transaction_costs.py and tests. Include delta threshold, max notional block, transaction cost estimate, BUY/SELL/NONE side, and human-readable reason. Run pytest -q tests/test_delta_hedger.py tests/test_transaction_costs.py.
```

## Prompt F — Implement LSEG backtest

```text
Implement src/data/lseg_loader.py and scripts/run_lseg_backtest.py. Use LSEG underlying historical prices only. Do not assume option history or Greeks. Build synthetic ATM option book, estimate rolling realized volatility, recalc Black-Scholes Greeks daily, simulate hedged vs unhedged PnL, and output CSVs. Fail gracefully if LSEG is unavailable. Run python scripts/run_lseg_backtest.py.
```

## Prompt G — Implement IBKR dry-run daily hedge

```text
Implement src/data/ibkr_connection.py, src/broker/contract_mapper.py, src/broker/order_builder.py, and scripts/run_daily_hedge.py --dry-run. Connect only to paper TWS on port 7497, request delayed market data, read positions, generate hedge recommendations, and do not place orders. Run python scripts/run_daily_hedge.py --dry-run.
```

## Prompt H — Add reporting and README

```text
Implement src/reporting/charts.py, src/reporting/tables.py, src/reporting/tearsheet.py, scripts/build_readme_outputs.py, and update README.md according to @docs/06_README_SPEC.md. Generate charts under docs/images/. Run python scripts/build_readme_outputs.py.
```

## Prompt I — Final hardening

```text
Run the full test and script suite: pytest -q, python scripts/run_demo.py, python scripts/run_lseg_backtest.py, python scripts/run_daily_hedge.py --dry-run, python scripts/build_readme_outputs.py. Fix failures. Then audit for secrets, live trading paths, hard-coded account IDs, and unsafe order logic.
```
