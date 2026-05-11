# LSEG Option Universe — Data Quality Report

**Audit date:** 2026-05-11  
**Data source:** LSEG (lseg)  
**RICs tested:** 120  
**RICs with valid mid price:** 120 (100%)  
**Average history per RIC:** 35 trading days  

## Field coverage

| Field | RICs with data | Coverage | Notes |
|---|---|---|---|
| BID | 120 / 120 | 100% | Daily close bid price from LSEG |
| ASK | 120 / 120 | 100% | Daily close ask price from LSEG |
| MID | 120 / 120 | 100% | Derived (BID+ASK)/2 — valid when both bid and ask are positive and bid < ask |
| IV (LSEG direct) | 0 / 120 | 0% | TR.ImpliedVolatility — NOT available under current LSEG entitlement (EMPTY/ERROR) |
| IV (BS bisection fallback) | 120 / 120 | 100% | Black-Scholes IV solved from market mid — available whenever MID is available |
| Greeks (LSEG direct) | 0 / 120 | 0% | TR.Delta / TR.Gamma / TR.Vega — NOT available under current LSEG entitlement |
| Greeks (BS fallback) | 120 / 120 | 100% | Black-Scholes Greeks from BS-bisection IV — always used as primary engine |

## Greeks and IV sourcing

| Source | Available | Notes |
|---|---|---|
| LSEG direct IV (TR.ImpliedVolatility) | No | EMPTY/ERROR under current entitlement |
| LSEG direct Greeks (TR.Delta etc.) | No | EMPTY/ERROR under current entitlement |
| Black-Scholes IV bisection from mid | Yes | Primary engine — always used |
| Black-Scholes Greeks from BS-IV | Yes | Derived from bisection IV |
| Rolling realised-vol fallback | Yes (fallback) | Used when BS bisection fails |

## Fallback rules

1. **Primary:** BS bisection solves IV from LSEG market mid → compute all Greeks
2. **Fallback:** If bisection fails → rolling realised vol (flagged `iv_source=realized_vol_fallback`)
3. **Exclusion:** If both fail → contract excluded that day

Fallback rate > 30% triggers `LOW CONFIDENCE` flag in validation report.

## Warnings

- LSEG historical option Greeks (TR.Delta, TR.ImpliedVolatility) returned EMPTY/ERROR
- All Greeks computed via Black-Scholes fallback from LSEG market mid
- SPY calls only (Jan 2027 expiry) — no puts confirmed in current RIC audit
- Snapshot Greeks from LSEG audit were single-row only; not used in backtest

## Per-RIC summary (first 20 RICs by strike)

| RIC | Strike | History days | Mid pairs | Bid% | Ask% | Notes |
|---|---|---|---|---|---|---|
| SPYA152705000.U | $50 | 35 | 35 | 100% | 100% | OK |
| SPYA152705500.U | $55 | 35 | 35 | 100% | 100% | OK |
| SPYA152706000.U | $60 | 35 | 35 | 100% | 100% | OK |
| SPYA152706500.U | $65 | 35 | 35 | 100% | 100% | OK |
| SPYA152707000.U | $70 | 35 | 35 | 100% | 100% | OK |
| SPYA152707500.U | $75 | 35 | 35 | 100% | 100% | OK |
| SPYA152708000.U | $80 | 35 | 35 | 100% | 100% | OK |
| SPYA152708500.U | $85 | 35 | 35 | 100% | 100% | OK |
| SPYA152709000.U | $90 | 35 | 35 | 100% | 100% | OK |
| SPYA152709500.U | $95 | 35 | 35 | 100% | 100% | OK |
| SPYA152710000.U | $100 | 35 | 35 | 100% | 100% | OK |
| SPYA152710500.U | $105 | 35 | 35 | 100% | 100% | OK |
| SPYA152711000.U | $110 | 35 | 35 | 100% | 100% | OK |
| SPYA152711500.U | $115 | 35 | 35 | 100% | 100% | OK |
| SPYA152712000.U | $120 | 35 | 35 | 100% | 100% | OK |
| SPYA152712500.U | $125 | 35 | 35 | 100% | 100% | OK |
| SPYA152713000.U | $130 | 35 | 35 | 100% | 100% | OK |
| SPYA152713500.U | $135 | 35 | 35 | 100% | 100% | OK |
| SPYA152714000.U | $140 | 35 | 35 | 100% | 100% | OK |
| SPYA152714500.U | $145 | 35 | 35 | 100% | 100% | OK |
| _(+100 more RICs)_ | | | | | | |
