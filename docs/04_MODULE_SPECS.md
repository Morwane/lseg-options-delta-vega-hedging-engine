# 04 — Module Specifications

## `src/pricing/black_scholes.py`

### Dataclass

```python
@dataclass(frozen=True)
class BlackScholesInputs:
    spot: float
    strike: float
    time_to_expiry: float
    risk_free_rate: float
    dividend_yield: float
    volatility: float
    option_type: Literal["call", "put"]
```

### Expected functions

```python
def validate_inputs(inputs: BlackScholesInputs) -> None: ...
def d1(inputs: BlackScholesInputs) -> float: ...
def d2(inputs: BlackScholesInputs) -> float: ...
def black_scholes_price(inputs: BlackScholesInputs) -> float: ...
def black_scholes_delta(inputs: BlackScholesInputs) -> float: ...
def black_scholes_gamma(inputs: BlackScholesInputs) -> float: ...
def black_scholes_vega(inputs: BlackScholesInputs) -> float: ...
def black_scholes_theta(inputs: BlackScholesInputs) -> float: ...
def black_scholes_all(inputs: BlackScholesInputs) -> dict[str, float]: ...
```

### Implementation notes

- Use `scipy.stats.norm.cdf` and `norm.pdf`, or implement normal CDF/PDF with standard library if SciPy unavailable.
- `vega` should be per 1.00 volatility point unless clearly documented. Prefer documenting both if needed.
- `theta` should be annualized unless clearly converted to daily.
- Handle expiry edge cases explicitly.

## `src/pricing/implied_vol.py`

### Expected function

```python
def implied_vol_bisection(
    target_price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    dividend_yield: float,
    option_type: Literal["call", "put"],
    low: float = 1e-4,
    high: float = 5.0,
    tolerance: float = 1e-6,
    max_iter: int = 200,
) -> float | None: ...
```

### Requirements

- Return `None` if target price is impossible or solver does not converge.
- Do not throw uncaught exceptions in scripts; report cleanly.

## `src/portfolio/positions.py`

### Dataclasses

```python
@dataclass(frozen=True)
class OptionPosition:
    underlying: str
    option_type: Literal["call", "put"]
    quantity: float
    strike: float
    expiry: date
    implied_volatility: float
    multiplier: int = 100
    risk_free_rate: float = 0.03
    dividend_yield: float = 0.0

@dataclass(frozen=True)
class UnderlyingPosition:
    underlying: str
    quantity: float
    average_price: float | None = None

@dataclass(frozen=True)
class PortfolioBook:
    options: list[OptionPosition]
    underlyings: list[UnderlyingPosition]
```

### Functions

```python
def load_portfolio_from_yaml(path: Path) -> PortfolioBook: ...
def time_to_expiry(expiry: date, valuation_date: date) -> float: ...
```

## `src/portfolio/exposures.py`

### Dataclass

```python
@dataclass(frozen=True)
class PositionGreeks:
    underlying: str
    quantity: float
    multiplier: int
    option_delta: float
    option_gamma: float
    option_vega: float
    option_theta: float
    position_delta: float
    position_gamma: float
    position_vega: float
    position_theta: float
```

### Functions

```python
def compute_position_greeks(position: OptionPosition, spot: float, valuation_date: date) -> PositionGreeks: ...
def aggregate_exposures(greeks: list[PositionGreeks]) -> pd.DataFrame: ...
def exposures_to_csv(...): ...
```

## `src/hedging/delta_hedger.py`

### Dataclass

```python
@dataclass(frozen=True)
class HedgeRecommendation:
    underlying: str
    portfolio_delta: float
    current_underlying_position: float
    target_underlying_position: float
    order_quantity: float
    side: Literal["BUY", "SELL", "NONE"]
    spot: float
    estimated_notional: float
    estimated_transaction_cost: float
    reason: str
    blocked: bool
```

### Function

```python
def recommend_delta_hedge(
    underlying: str,
    portfolio_delta: float,
    current_underlying_position: float,
    spot: float,
    rules: HedgeRules,
) -> HedgeRecommendation: ...
```

### Required behavior

- If `abs(order_quantity) < delta_threshold_shares`, side must be `NONE`.
- If notional exceeds max notional, return `blocked=True` and do not create executable order.
- Always include a human-readable reason.

## `src/broker/order_builder.py`

### Function

```python
def build_market_order_from_recommendation(rec: HedgeRecommendation) -> object: ...
```

Requirements:

- Do not build orders for `NONE` or blocked recommendations.
- Use whole-share rounding policy clearly.
- Keep paper/live logic outside this pure builder.

## `scripts/run_demo.py`

Must work offline. No IBKR. No LSEG.

Inputs:

- `config/demo_portfolio.yaml`
- hard-coded demo spot map or `config/demo_market.yaml`

Outputs:

- `outputs/reports/greeks_by_position.csv`
- `outputs/reports/portfolio_exposures.csv`
- `outputs/reports/hedge_orders.csv`

## `scripts/run_lseg_backtest.py`

Must use LSEG if available. If not available, fail gracefully and explain:

```text
LSEG session unavailable. Run demo mode instead: python scripts/run_demo.py
```

## `scripts/run_daily_hedge.py`

Modes:

```bash
python scripts/run_daily_hedge.py --dry-run
python scripts/run_daily_hedge.py --paper-execute
```

Rules:

- `--dry-run` must never place orders.
- `--paper-execute` must ask confirmation.
- No live mode.
