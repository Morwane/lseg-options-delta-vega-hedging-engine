from ib_insync import IB

ib = IB()

print("Connecting to IBKR Paper Trading...")
ib.connect("127.0.0.1", 7497, clientId=1)

print("Connected:", ib.isConnected())
print("Accounts:", ib.managedAccounts())

ib.disconnect()
print("Disconnected.")
