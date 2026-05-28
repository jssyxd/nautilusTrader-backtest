#!/usr/bin/env python3
"""Debug CSV parsing - check what pandas actually reads"""
from pathlib import Path
import pandas as pd

DATA_DIR = Path(r"w:\nautilusTrader\data\binance_klines")
first_file = list(DATA_DIR.glob("BTCUSDT-15m-*.csv"))[0]
print(f"File: {first_file.name}")

# Try reading without specifying column names
df_raw = pd.read_csv(first_file, header=None)
print(f"Raw shape: {df_raw.shape}")
print(f"Raw columns: {list(df_raw.columns)}")
print(f"First row values: {df_raw.iloc[0].tolist()}")
print(f"First 3 rows of column 0: {df_raw[0].head(3).tolist()}")

# Read with column names
COLUMN_NAMES = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base_volume", "taker_buy_quote_volume",
]

df = pd.read_csv(first_file, header=None, names=COLUMN_NAMES)
print(f"\nWith names shape: {df.shape}")
print(f"First row: {df.iloc[0].to_dict()}")