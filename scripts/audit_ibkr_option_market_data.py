from ib_insync import IB, Stock, Option
import math
import time

ib = IB()

print("Connecting to IBKR Paper Trading...")
ib.connect("127.0.0.1", 7497, clientId=4)

symbol = "SPY"

print("\n=== UNDERLYING SNAPSHOT ===")
stock = Stock(symbol, "SMART", "USD")
ib.qualifyContracts(stock)

ticker = ib.reqMktData(stock, "", False, False)
ib.sleep(3)

spot_candidates = [ticker.marketPrice(), ticker.last, ticker.close, ticker.bid, ticker.ask]
spot = next((x for x in spot_candidates if x is not None and not math.isnan(x) and x > 0), None)

print("Symbol:", symbol)
print("conId:", stock.conId)
print("bid:", ticker.bid)
print("ask:", ticker.ask)
print("last:", ticker.last)
print("close:", ticker.close)
print("marketPrice:", ticker.marketPrice())
print("chosen spot:", spot)

ib.cancelMktData(stock)

if spot is None:
    print("\nNo valid spot price. Market data may be delayed/not subscribed.")
    ib.disconnect()
    raise SystemExit

print("\n=== OPTION CHAIN ===")
chains = ib.reqSecDefOptParams(symbol, "", "STK", stock.conId)
chain = chains[0]

expirations = sorted(chain.expirations)
strikes = sorted(chain.strikes)

expiry = expirations[0]
strike = min(strikes, key=lambda k: abs(k - spot))

print("Chosen expiry:", expiry)
print("Chosen strike:", strike)

print("\n=== OPTION SNAPSHOT ===")
opt = Option(symbol, expiry, strike, "C", "SMART", multiplier="100", currency="USD")
qualified = ib.qualifyContracts(opt)

if not qualified:
    print("Could not qualify option contract.")
    ib.disconnect()
    raise SystemExit

opt = qualified[0]
print("Option contract:", opt)

opt_ticker = ib.reqMktData(opt, "", False, False)
ib.sleep(5)

print("bid:", opt_ticker.bid)
print("ask:", opt_ticker.ask)
print("last:", opt_ticker.last)
print("close:", opt_ticker.close)
print("marketPrice:", opt_ticker.marketPrice())

print("\n=== MODEL GREEKS ===")
mg = opt_ticker.modelGreeks
if mg is None:
    print("No modelGreeks received.")
    print("This may mean you need market data permissions, delayed data, or a different option exchange.")
else:
    print("impliedVol:", mg.impliedVol)
    print("delta:", mg.delta)
    print("gamma:", mg.gamma)
    print("vega:", mg.vega)
    print("theta:", mg.theta)
    print("optPrice:", mg.optPrice)
    print("pvDividend:", mg.pvDividend)

ib.cancelMktData(opt)
ib.disconnect()
print("\nDisconnected.")
