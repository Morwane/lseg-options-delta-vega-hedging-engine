# Delta-Vega Hedge Optimizer Methodology

## Research goal

Compare four hedge strategies for a configured SPY option book to quantify
the marginal risk reduction and cost of adding vega hedging on top of
delta hedging, and the value of sparse multi-instrument optimisation.

---

## Four methods

| ID | Method | Instruments | Objective |
|---|---|---|---|
| 1 | No hedge | None | Baseline reference |
| 2 | Delta-only | Underlying shares | Zero residual delta |
| 3 | Delta-Vega | Underlying + 1 option | Zero residual delta and vega |
| 4 | Optimized | Underlying + ≤N options | Minimise weighted quadratic objective |

---

## Objective function (Methods 3 and 4)

```
J = λ_Δ × residual_delta²
  + λ_ν × residual_vega²
  + λ_cost × transaction_cost
  + λ_turnover × turnover

residual_delta = book_delta + h + Σ(w_i × delta_i × 100)
residual_vega  = book_vega  + Σ(w_i × vega_i  × 100)

transaction_cost = |h| × spot × bps/10000
                 + Σ |w_i| × mid_i × 100 × bps/10000

turnover = |h − prev_h| + Σ |w_i − prev_w_i|
```

Default weights: λ_Δ=1.0, λ_ν=0.5, λ_cost=0.05, λ_turnover=0.02

---

## Method 3: Delta-Vega (analytic closed-form)

For a single option candidate, the vega-neutral weight is:

```
w* = −book_vega / (vega_candidate × 100)
h* = −book_delta − w* × delta_candidate × 100
```

All candidates from the hedge universe are evaluated; the one minimising J is selected.

---

## Method 4: Optimized (scipy SLSQP)

For the top-N candidates (ranked by bid/ask spread):

```
minimise J(h, w_1, ..., w_N)
subject to:
    −max_shares ≤ h ≤ max_shares
    −max_contracts ≤ w_i ≤ max_contracts  (for each i)
```

Solved with `scipy.optimize.minimize` (SLSQP), warm-started at the delta-neutral
underlying position with zero option weights.

---

## Candidate hedge universe

Instruments are filtered from the LSEG-audited SPY call RICs:

| Filter | Default |
|---|---|
| Max bid/ask spread | 300 bps |
| Max moneyness distance | ±15% from spot |
| IV bisection required | Yes |
| Minimum vega | 0.005 per share |
| Maximum candidates | 20 (ranked by tightest spread) |

---

## Metrics reported

| Metric | Description |
|---|---|
| `total_net_pnl` | Cumulative net P&L (option + hedge − costs) |
| `pnl_volatility` | Std dev of daily net P&L |
| `max_drawdown` | Maximum drawdown from high-water mark |
| `avg_abs_residual_delta` | Mean |residual delta| over backtest |
| `avg_abs_residual_vega` | Mean |residual vega| over backtest |
| `total_transaction_costs` | Sum of all transaction costs paid |

---

## Limitations

- Option weights are continuous (not rounded to integer contracts) for research comparability.
- Candidate universe restricted to LSEG-audited SPY calls — no puts or other underlyings.
- Single expiry (Jan 2027) — no term structure optimisation.
- Transaction cost model uses flat bps — no market impact or queue priority.
- Optimizer runs per-day independently (no multi-day look-ahead constraint).
