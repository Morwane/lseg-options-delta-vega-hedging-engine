from ib_insync import IB, Stock

ib = IB()

print("Connecting to IBKR Paper Trading...")
ib.connect("127.0.0.1", 7497, clientId=3)

symbols = ["SPY", "QQQ", "TLT", "GLD"]

print("\n=== OPTION CHAIN AUDIT ===")

for symbol in symbols:
    print(f"\n--- {symbol} ---")

    stock = Stock(symbol, "SMART", "USD")
    qualified = ib.qualifyContracts(stock)

    if not qualified:
        print("Could not qualify underlying contract.")
        continue

    stock = qualified[0]
    print("Underlying conId:", stock.conId)
    print("Primary exchange:", stock.primaryExchange)

    chains = ib.reqSecDefOptParams(
        underlyingSymbol=symbol,
        futFopExchange="",
        underlyingSecType="STK",
        underlyingConId=stock.conId,
    )

    if not chains:
        print("No option chains found.")
        continue

    for chain in chains:
        expirations = sorted(chain.expirations)
        strikes = sorted(chain.strikes)

        print("Exchange:", chain.exchange)
        print("Trading class:", chain.tradingClass)
        print("Multiplier:", chain.multiplier)
        print("Number of expirations:", len(expirations))
        print("First 5 expirations:", expirations[:5])
        print("Number of strikes:", len(strikes))
        print("Strike range:", strikes[0], "to", strikes[-1])
        break

ib.disconnect()
print("\nDisconnected.")
