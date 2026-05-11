# Execution Safety Summary

## Safety architecture

This project operates under a strict paper-only safety model with multiple independent gates.
No live orders can be placed regardless of configuration.

---

## Safety gates (layered)

| Gate | Layer | Mechanism |
|---|---|---|
| Live port hard-blocked | Code | `IBKRConnection.__init__` raises `ValueError` if `port == 7496` |
| allow_live_trading=false | Config | `HedgeRules.__post_init__` raises `ValueError` if `allow_live_trading=True` |
| paper_trading_only=true | Config | Required field; HedgeRules raises if False |
| dry_run_default=true | Config | Default mode; no order is built in dry-run |
| transmit=False default | Code | `IBKROrderSpec.transmit` is always `False` by default |
| Per-order confirmation | Runtime | `--paper-execute` requires user `y` for each order |
| Notional cap | Runtime | Orders > $25,000 are `blocked=True` and never presented to user |
| Below-threshold suppression | Runtime | `|order| < delta_threshold_shares` → side=NONE → no order |
| All orders logged | Audit | Every proposed, declined, and blocked order written to CSV |

---

## Port configuration

| Port | Role | Status |
|---|---|---|
| 7497 | IBKR Paper Trading | Used and validated |
| 7496 | IBKR Live Trading | Hard-blocked in `IBKRConnection.__init__` |
| Any other | N/A | Not relevant to this project |

---

## Paper execution flow

```
scripts/run_daily_hedge.py --paper-execute

1. Connect to TWS paper (port 7497 only)
2. reqMarketDataType(3)  — delayed data, no live data
3. Load reference option book from config
4. Compute Black-Scholes Greeks
5. Aggregate portfolio delta
6. Generate HedgeRecommendation for each underlying
7. For each recommendation:
   - If side=NONE: print "no order"
   - If blocked=True: print "blocked (notional limit)"
   - If actionable: print proposed order and prompt [y/N]
     - y/Y: build IBKROrderSpec (transmit=False), call place_paper_order()
             which sets transmit=True and sends to paper TWS
     - any other key: log as "declined"
8. Write paper_execution_log.csv
9. Disconnect cleanly
```

---

## Operational validation

Validated 2026-04-30 in paper-execute mode:

| Check | Result |
|---|---|
| Connection to port 7497 | Success |
| SPY delayed spot | ~$714.87 |
| Account AvailableFunds | ~$1,000,041 |
| Hedge recommendations generated | 2 (SPY, QQQ) |
| Both blocked by notional cap | Yes (>$25,000 each) |
| Orders sent | 0 |
| Log file written | Yes |

---

## What this project will never do

- Connect to IBKR live port 7496
- Enable `allow_live_trading: true`
- Place orders without per-order `[y/N]` confirmation
- Send an order without `transmit=True` being deliberately set
- Ingest live IBKR option positions as the book source (this is a future extension)
- Override notional cap without code change and re-review
