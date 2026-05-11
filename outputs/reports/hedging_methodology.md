# Hedging Methodology

## Overview

This engine implements transaction-cost-aware delta hedging and delta-vega
hedge optimization for a configured reference option book. All positions come
from a YAML configuration file or the LSEG-audited RIC universe — not from
live IBKR option positions.

---

## Greeks computation

All Greeks are computed via Black-Scholes with IV recovered from LSEG market mid:

```
d1 = [ln(S/K) + (r - q + σ²/2) T] / (σ √T)
d2 = d1 − σ √T

Delta (call) = e^(−qT) × N(d1)
Delta (put)  = e^(−qT) × (N(d1) − 1)
Gamma        = e^(−qT) × n(d1) / (S σ √T)
Vega         = S × e^(−qT) × n(d1) × √T
Theta        = [−S n(d1) σ e^(−qT) / (2√T) + carry] / 365
```

where n(·) is the standard normal PDF and N(·) is the CDF.

---

## Portfolio delta aggregation

```
position_delta  = quantity × multiplier × option_delta
portfolio_delta = Σ position_delta  (grouped by underlying)
```

---

## Hedge recommendation

```
target_underlying_position = −portfolio_delta
hedge_order = target − current_underlying_position
```

Applied filters:
1. `|hedge_order| < delta_threshold_shares` → side = NONE (no trade)
2. `notional > max_order_notional_usd` → blocked = True (manual review required)

---

## P&L timing (no look-ahead)

```
hedge_pnl[t]   = hedge_shares[t−1] × (spot[t] − spot[t−1])
option_pnl[t]  = Σ (mid[t] − mid[t−1]) × qty × multiplier
net_pnl[t]     = option_pnl[t] + hedge_pnl[t] − transaction_costs[t]
```

The hedge position held on day t−1 is the one that generates P&L on day t.
Rebalancing on day t uses only information available at the close of day t.

---

## IV hierarchy

1. **Primary:** Black-Scholes bisection from LSEG market mid `(bid+ask)/2`
   - Bounds: σ ∈ [0.01, 10.0], tolerance: 1e-6
   - Flagged `iv_source = "bs_bisection"`
2. **Fallback:** Rolling 20-day annualised realised volatility
   - Flagged `iv_source = "realized_vol_fallback"`
   - Only used when BS bisection fails AND `iv_fallback_allowed = true`
3. **Exclusion:** Contract excluded that day if both fail

Fallback rate > 30% triggers `LOW CONFIDENCE` in the validation report.

---

## Transaction costs

```
estimated_cost = |order_quantity| × spot × (bps / 10,000)
```

Default: 2 bps flat. Rebalance suppressed when `|hedge_order| < delta_threshold_shares`.

---

## Configuration

Key parameters in `config/hedge_rules.yaml`:

| Parameter | Default | Notes |
|---|---|---|
| `delta_threshold_shares` | 100 | Minimum rebalance size |
| `max_order_notional_usd` | 25,000 | Hard cap — blocks larger orders |
| `fallback_transaction_cost_bps` | 2.0 | Cost estimate per share traded |
| `paper_trading_only` | true | Non-negotiable safety gate |
| `allow_live_trading` | false | Hard-blocked in code |
| `dry_run_default` | true | Default mode |
