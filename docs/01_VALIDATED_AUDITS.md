# 01 — Validated Audits and Data Access

This file records the real access tests already run by the user. Do not invent additional access.

## Environment already observed

- macOS MacBook Air 2018 Intel.
- Python 3.11 environment available.
- Interactive Brokers account validated.
- Trader Workstation installed and connected in **Simulated / Paper Trading** mode.
- TWS API active, read-only mode disabled for proper API calls.
- IBKR Paper Trading port: `7497`.

## IBKR basic connection audit

Script used: `scripts/test_ibkr_connection.py`

Result:

```text
Connecting to IBKR Paper Trading...
Connected: True
Accounts: ['DUP885508']
Disconnected.
```

Interpretation:

- Python can connect to IBKR Paper Trading through TWS.
- The account ID must not be committed in non-redacted public outputs.

## IBKR account and contract audit

Script used: `scripts/audit_ibkr_basic.py`

Key result:

```text
Connected: True
Accounts: ['DUP885508']
AvailableFunds: 1000000.00 EUR
NetLiquidation: 1000000.00 EUR
Positions: No positions found in paper account.
```

Contract details validated:

```text
SPY: 1 contract detail found, conId 756733, primaryExchange ARCA
QQQ: 1 contract detail found, conId 320227571, primaryExchange NASDAQ
TLT: 1 contract detail found, conId 15547841, primaryExchange NASDAQ
GLD: 1 contract detail found, conId 51529211, primaryExchange ARCA
```

Interpretation:

- Underlying stock/ETF contracts are discoverable through IBKR.
- No paper positions currently exist, which is normal.

## IBKR option chain audit

Script used: `scripts/audit_ibkr_option_chains.py`

Validated output:

```text
SPY: 35 expirations, 462 strikes, multiplier 100
QQQ: 34 expirations, 465 strikes, multiplier 100
TLT: 28 expirations, 74 strikes, multiplier 100
GLD: 28 expirations, 374 strikes, multiplier 100
```

Interpretation:

- Listed option chains are available for all four underlyings.
- Multiplier should default to 100 for equity/ETF options unless contract metadata says otherwise.

## IBKR live market data limitation

Initial live market data request for SPY returned:

```text
Error 10089: market data requested requires additional subscription for API connections.
Delayed market data is available.
```

Interpretation:

- Real-time market data API is not currently subscribed.
- The project should use delayed data for paper/dry-run mode and LSEG for historical backtests.

## IBKR delayed market data audit

Script used: `scripts/audit_ibkr_delayed_market_data.py`

Validated output:

```text
Requesting delayed market data...
bid: 712.03
ask: 712.08
last: 712.08
close: 711.69
marketPrice: 712.08
chosen spot: 712.08
```

Interpretation:

- Delayed market data works for SPY.
- Production code must explicitly call `ib.reqMarketDataType(3)` when using delayed data.

## IBKR option Greeks audit

Script used: `scripts/audit_ibkr_option_greeks.py`

Tested option:

```text
SPY 20260501 C 712
Option conId=863993951
```

Result:

```text
Option close: 4.53
bid: -1.0
ask: -1.0
last: -1.0
No modelGreeks received.
```

Interpretation:

- IBKR can qualify option contracts.
- Direct option Greeks are not currently available with the user's market-data permissions.
- Implement Black-Scholes fallback Greeks.

## LSEG connection audit

Script used: `scripts/audit_lseg_connection.py`

Validated:

```text
Opening LSEG session...
LSEG session opened.
.SPX TRDPRC_1: OK
SPY TRDPRC_1: OK
QQQ.O TRDPRC_1: OK
TLT.O TRDPRC_1: OK
GLD TRDPRC_1: OK
```

Interpretation:

- LSEG Data Library works in this repo.
- Historical underlying prices are available.

## LSEG option/Greeks audit

Script used: `scripts/audit_lseg_options_access.py`

Underlying price access:

```text
SPY TRDPRC_1 -> OK rows=5
QQQ.O TRDPRC_1 -> OK rows=5
TLT.O TRDPRC_1 -> OK rows=5
GLD TRDPRC_1 -> OK rows=5
```

Option-style field probes:

```text
TRDPRC_1 -> OK
BID -> OK
ASK -> OK
TR.BIDPRICE -> OK
TR.ASKPRICE -> OK
TR.CLOSEPRICE -> OK
TR.PriceClose -> OK
TR.ImpliedVolatility -> EMPTY
TR.IV -> ERROR
TR.Delta -> EMPTY
TR.Gamma -> EMPTY
TR.Vega -> EMPTY
TR.Theta -> EMPTY
```

Interpretation:

- LSEG underlying historical prices are validated.
- Direct option Greeks were not available in this field probe.
- Do not claim LSEG option Greeks are available.
- Use LSEG for historical underlyings and Black-Scholes fallback for Greeks.

## Final data policy

The code must handle data availability with this fallback order:

1. Use IBKR delayed spot for daily dry-run/paper mode if available.
2. Use LSEG historical spot for backtest mode.
3. Use configured or estimated volatility for Black-Scholes.
4. Use Black-Scholes for price and Greeks.
5. If required input is missing, fail clearly and write an audit warning.
