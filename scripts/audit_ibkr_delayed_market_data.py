from ib_insync import IB, Stock
import math

ib = IB()

print("Connecting to IBKR Paper Trading...")
ib.connect("127.0.0.1", 7497, clientId=5)

# 1 = live, 2 = frozen, 3 = delayed, 4 = delayed frozen
print("Requesting delayed market data...")
ib.reqMarketDataType(3)

symbol = "SPY"
stock = Stock(symbol, "SMART", "USD")
ib.qualifyContracts(stock)

print("\n=== DELAYED MARKET DATA SNAPSHOT ===")
ticker = ib.reqMktData(stock, "", False, False)

ib.sleep(10)

values = {
    "bid": ticker.bid,
    "ask": ticker.ask,
    "last": ticker.last,
    "close": ticker.close,
    "marketPrice": ticker.marketPrice(),
}

for k, v in values.items():
    print(f"{k}: {v}")

spot_candidates = [
    ticker.marketPrice(),
    ticker.last,
    ticker.close,
    ticker.bid,
    ticker.ask,
]

spot = next(
    (x for x in spot_candidates if x is not None and not math.isnan(x) and x > 0),
    None,
)

print("chosen spot:", spot)

ib.cancelMktData(stock)
ib.disconnect()
print("\nDisconnected.")
