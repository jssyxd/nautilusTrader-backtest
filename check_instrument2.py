from nautilus_trader.model.instruments import CryptoPerpetual

# Check what parameters from_dict expects
import json

# Create a minimal dict to see the expected format
test_dict = {
    "instrument_id": "BTCUSDT-PERP.BINANCE",
    "instrument_class": "CRYPTO_PERPETUAL",
    "base_currency": "BTC",
    "quote_currency": "USDT",
    "settlement_currency": "USDT",
    "is_inverse": False,
    "price_precision": 2,
    "size_precision": 6,
    "price_increment": "0.01",
    "size_increment": "0.000001",
    "max_quantity": "1000",
    "min_quantity": "0.000001",
    "max_notional": "1000000 USD",
    "min_notional": "0.000001 USD",
    "maker_fee": "0.0004",
    "taker_fee": "0.0004",
    "ts_event": 0,
    "ts_init": 0,
}

try:
    inst = CryptoPerpetual.from_dict(test_dict)
    print("Successfully created from dict!")
    print("Instrument:", inst)
except Exception as e:
    print("Error:", e)

# Also check attributes directly
print("\nDefault values:")
print("margin_init:", getattr(CryptoPerpetual, 'margin_init', 'N/A'))
print("margin_maint:", getattr(CryptoPerpetual, 'margin_maint', 'N/A'))
print("maker_fee:", getattr(CryptoPerpetual, 'maker_fee', 'N/A'))
print("taker_fee:", getattr(CryptoPerpetual, 'taker_fee', 'N/A'))