from nautilus_trader.test_kit.providers import TestInstrumentProvider

# Get the BTCUSDT instrument
btcusdt = TestInstrumentProvider.btcusdt_binance()
print("Type:", type(btcusdt))
print("Instrument:", btcusdt)
print("\nDict representation:")
d = btcusdt.to_dict()
for k, v in d.items():
    print(f"  {k}: {v}")