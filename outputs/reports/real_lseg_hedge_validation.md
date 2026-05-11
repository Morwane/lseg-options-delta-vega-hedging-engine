# Real LSEG Historical Hedge Validation Report

| Field | Value |
|-------|-------|
| Generated | 2026-05-10 23:28:56 UTC |
| Data source | LSEG (lseg) |
| Underlying | SPY |
| Option type | Calls only |
| Expiry | 2027-01-15 |
| Selection method | ATM selection |

------------------------------------------------------------------------

## 1. RIC Universe

- Total confirmed RICs: **120**
- Strike range: $50–$645 ($5 increments)
- Expiry: January 2027 (2027-01-15)
- Option type confirmed: **calls only** (no puts confirmed in LSEG audit)

------------------------------------------------------------------------

## 2. Contract Selection

**Selection method:** ATM selection  
**Contracts selected:** 5 of 5 requested  
**Selection spot:** $648.57  

| RIC             | Strike | Moneyness% | Class | Mid$  | Spread$ | Moneyness$ |
| --------------- | ------ | ---------- | ----- | ----- | ------- | ---------- |
| SPYA152764500.U | $645   | +0.6%      | ATM   | 62.40 | 3.88    | $3.6       |
| SPYA152764000.U | $640   | +1.3%      | ATM   | 65.66 | 1.12    | $8.6       |
| SPYA152763500.U | $635   | +2.1%      | ITM   | 68.95 | 3.88    | $13.6      |
| SPYA152763000.U | $630   | +2.9%      | ITM   | 72.29 | 3.88    | $18.6      |
| SPYA152762500.U | $625   | +3.6%      | ITM   | 75.68 | 3.88    | $23.6      |

------------------------------------------------------------------------

## 3. Contract Coverage

Total trading days in backtest: **35**

| RIC             | Strike | Bid days | Ask days | Mid days | IV solved | IV fallback | IV failed | Coverage |
| --------------- | ------ | -------- | -------- | -------- | --------- | ----------- | --------- | -------- |
| SPYA152762500.U | $625   | 35/35    | 35/35    | 35/35    | 35/35     | 0/35        | 0/35      | 100.0%   |
| SPYA152763000.U | $630   | 35/35    | 35/35    | 35/35    | 35/35     | 0/35        | 0/35      | 100.0%   |
| SPYA152763500.U | $635   | 35/35    | 35/35    | 35/35    | 35/35     | 0/35        | 0/35      | 100.0%   |
| SPYA152764000.U | $640   | 35/35    | 35/35    | 35/35    | 35/35     | 0/35        | 0/35      | 100.0%   |
| SPYA152764500.U | $645   | 35/35    | 35/35    | 35/35    | 35/35     | 0/35        | 0/35      | 100.0%   |

------------------------------------------------------------------------

## 4. IV Bisection Quality

| Metric | Value |
|--------|-------|
| Total IV computation attempts | 175 |
| BS bisection success | 175 / 175 (100.0%) |
| Realized vol fallback | 0 / 175 (0.0%) |
| IV failed | 0 / 175 (0.0%) |
| Overall fallback rate | 0.0% |
| Backtest confidence | **HIGH** |

### Per-date IV summary

| Date       | Solved | Fallback | Failed | Fallback rate |
| ---------- | ------ | -------- | ------ | ------------- |
| 2026-03-20 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-03-23 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-03-24 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-03-25 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-03-26 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-03-27 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-03-30 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-03-31 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-01 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-02 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-06 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-07 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-08 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-09 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-10 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-13 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-14 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-15 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-16 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-17 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-20 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-21 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-22 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-23 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-24 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-27 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-28 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-29 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-04-30 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-05-01 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-05-04 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-05-05 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-05-06 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-05-07 | 5/5    | 0/5      | 0/5    | 0.0%          |
| 2026-05-08 | 5/5    | 0/5      | 0/5    | 0.0%          |

------------------------------------------------------------------------

## 5. Backtest Results

| Metric | Value |
|--------|-------|
| Period | 2026-03-20 → 2026-05-08 |
| Trading days | 35 |
| Contracts in book | 5 |
| SPY spot range | $631.97 – $737.62 |
| Cumulative P&L (hedged) | $-2,165.74 |
| Cumulative P&L (unhedged) | +$30,294.50 |
| Hedge improvement | $-32,460.24 |
| Total transaction costs | $66.53 |
| Rebalances | 18 / 35 days (51.4%) |
| IV fallback rate | 0.0% |

------------------------------------------------------------------------

## 6. Limitations

- Calls only — no puts confirmed in LSEG audit
- SPY underlying only
- Jan 2027 expiry only (single expiry, no term structure)
- ~30 trading days of data (2026-03-18 to 2026-04-29)
- Greeks reconstructed from market mid via Black-Scholes IV bisection
- Historical LSEG option Greeks not used (only 1 snapshot row per RIC in audit)
- Portfolio fixed at initial ATM selection — no intraday contract rotation
- No alpha strategy — pure delta-hedge P&L illustration
- No IBKR orders in this phase
- Confirmed RIC universe contains calls with strikes $50–$645; nearest-ATM contracts selected at ~SPY spot
- Overall IV fallback rate: 0.0%
