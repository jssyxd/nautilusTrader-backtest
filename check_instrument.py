from nautilus_trader.model.instruments import CryptoPerpetual
import inspect

# Get the source file
print("CryptoPerpetual location:", CryptoPerpetual.__module__)

# Try to get the signature from the class
try:
    sig = inspect.signature(CryptoPerpetual.__init__)
    print("Signature:", sig)
except Exception as e:
    print("Error getting signature:", e)

# List public attributes
attrs = [m for m in dir(CryptoPerpetual) if not m.startswith("_")]
print("\nPublic attributes/methods:", attrs)