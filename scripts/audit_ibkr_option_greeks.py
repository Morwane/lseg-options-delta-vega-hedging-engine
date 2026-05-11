from ib_insync import IB, Stock, Option
import math

ib = IB()

print("Connecting to IBKR Paper Trading...")
ib.connect("127.0.0.1", 7497, clientId=6)

# delayed market data
ib.reqMarketDataType(3)

symbol = "SPY"

print("\n=== UNDERLYING ===")
stock = Stock(symbol, "SMART", "USD")
ib.qualifyContracts(stock)

ticker = ib.reqMktData(stock, "", False, False)
ib.sleep(10)

spot_candidates = [ticker.marketPrice(), ticker.last, ticker.close, ticker.bid, ticker.ask]
spot = next((x for x in spot_candidates if x is not None and not math.isnan(x) and x > 0), None)

print("spot:", spot)
print("bid:", ticker.bid)
print("ask:", ticker.ask)
print("last:", ticker.last)

ib.cancelMktData(stock)

if spot is None:
    print("No valid spot. Stop.")
    ib.disconnect()
    raise SystemExit

print("\n=== OPTION CHAIN ===")
chains = ib.reqSecDefOptParams(symbol, "", "STK", stock.conId)

# choose chain with most expirations/strikes
chain = max(chains, key=lambda c: len(c.expirations) * len(c.strikes))

expirations = sorted(chain.expirations)
strikes = sorted(chain.strikes)

# choose a near-term expiry but avoid same-day if possible
expiry = expirations[2] if len(expirations) > 2 else expirations[0]
strike = min(strikes, key=lambda k: abs(k - spot))

print("exchange:", chain.exchange)
print("tradingClass:", chain.tradingClass)
print("expiry:", expiry)
print("strike:", strike)

print("\n=== OPTION CONTRACT ===")
option = Option(symbol, expiry, strike, "C", "SMART", currency="USD", multiplier="100")
qualified = ib.qualifyContracts(option)

if not qualified:
    print("Could not qualify option.")
    ib.disconnect()
    raise SystemExit

option = qualified[0]
print(option)

print("\n=== OPTION MARKET DATA + GREEKS ===")
opt_ticker = ib.reqMktData(option, "", False, False)
ib.sleep(15)

print("bid:", opt_ticker.bid)
print("ask:", opt_ticker.ask)
print("last:", opt_ticker.last)
print("close:", opt_ticker.close)
print("marketPrice:", opt_ticker.marketPrice())

mg = opt_ticker.modelGreeks
if mg is None:
    print("\nNo modelGreeks received.")
    print("Next step: build Black-Scholes fallback Greeks.")
else:
    print("\nmodelGreeks received:")
    print("impliedVol:", mg.impliedVol)
    print("delta:", mg.delta)
    print("gamma:", mg.gamma)
    print("vega:", mg.vega)
    print("theta:", mg.theta)
    print("optPrice:", mg.optPrice)
    print("pvDividend:", mg.pvDividend)

ib.cancelMktData(option)
ib.disconnect()
print("\nDisconnected.")
