from ib_insync import IB, Stock

ib = IB()

print("Connecting to IBKR Paper Trading...")
ib.connect("127.0.0.1", 7497, clientId=2)

print("\n=== CONNECTION ===")
print("Connected:", ib.isConnected())
print("Accounts:", ib.managedAccounts())

print("\n=== ACCOUNT SUMMARY ===")
summary = ib.accountSummary()
for row in summary[:20]:
    print(row)

print("\n=== POSITIONS ===")
positions = ib.positions()
if not positions:
    print("No positions found in paper account.")
else:
    for p in positions:
        print(p)

print("\n=== CONTRACT DETAILS TEST ===")
symbols = ["SPY", "QQQ", "TLT", "GLD"]

for symbol in symbols:
    contract = Stock(symbol, "SMART", "USD")
    details = ib.reqContractDetails(contract)
    print(f"{symbol}: {len(details)} contract detail(s) found")
    if details:
        print("  conId:", details[0].contract.conId)
        print("  exchange:", details[0].contract.exchange)
        print("  primaryExchange:", details[0].contract.primaryExchange)

ib.disconnect()
print("\nDisconnected.")
