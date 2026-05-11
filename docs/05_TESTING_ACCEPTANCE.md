# 05 — Testing and Acceptance Criteria

## Required test suite

Run all tests:

```bash
pytest -q
```

## Pricing tests

File: `tests/test_black_scholes.py`

Required tests:

- call price is positive
- put price is positive
- call Delta is between 0 and 1
- put Delta is between -1 and 0
- Gamma is positive
- Vega is positive
- shorter time to expiry changes Greeks
- invalid inputs raise clear errors

## Implied vol tests

File: `tests/test_implied_vol.py`

Required tests:

- bisection recovers known input vol from Black-Scholes price
- impossible price returns `None`
- solver handles low/high bounds without crashing

## Exposure tests

File: `tests/test_exposures.py`

Required tests:

- `position_delta = quantity × multiplier × option_delta`
- aggregation by underlying works
- long call has positive Delta
- long put has negative Delta
- short option flips sign correctly

## Hedge engine tests

File: `tests/test_delta_hedger.py`

Required tests:

- target hedge equals negative portfolio Delta
- order quantity equals target minus current position
- threshold suppresses small orders
- max notional blocks oversized orders
- SELL/BUY side correct

## Transaction cost tests

File: `tests/test_transaction_costs.py`

Required tests:

- bps cost estimate positive
- half-spread cost estimate positive
- zero quantity gives zero cost

## Order builder tests

File: `tests/test_order_builder.py`

Required tests:

- no order built for blocked recommendation
- no order built for side `NONE`
- order side and quantity map correctly for BUY/SELL

## Script acceptance

### Demo mode

```bash
python scripts/run_demo.py
```

Must create:

```text
outputs/reports/greeks_by_position.csv
outputs/reports/portfolio_exposures.csv
outputs/reports/hedge_orders.csv
```

### LSEG backtest mode

```bash
python scripts/run_lseg_backtest.py
```

Must either:

- create backtest outputs, or
- fail gracefully with a clear LSEG access message.

### IBKR dry-run mode

```bash
python scripts/run_daily_hedge.py --dry-run
```

Must either:

- produce dry-run recommendations, or
- fail gracefully if TWS is closed.

Must never place orders.

## Final acceptance definition

The project is considered finished only when:

```bash
pytest -q
python scripts/run_demo.py
python scripts/run_lseg_backtest.py
python scripts/run_daily_hedge.py --dry-run
python scripts/build_readme_outputs.py
```

all pass or fail gracefully with documented environment limitations.
