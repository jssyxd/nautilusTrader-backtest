#!/usr/bin/env python3
"""Debug the actual parsing issue"""
from pathlib import Path
import pandas as pd

DATA_DIR = Path(r"w:\nautilusTrader\data\binance_klines")
first_file = list(DATA_DIR.glob("BTCUSDT-15m-*.csv"))[0]
print(f"File: {first_file.name}")

# Read with correct number of column names
COLUMN_NAMES = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base_volume", "taker_buy_quote_volume",
    "ignore"  # Extra column
]

df = pd.read_csv(first_file, header=None, names=COLUMN_NAMES)
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"First row:")
for col in df.columns:
    print(f"  {col}: {df[col].iloc[0]}")

# Check the time range
print(f"\nopen_time min: {df['open_time'].min()}, max: {df['open_time'].max()}")
print(f"These look like milliseconds: {df['open_time'].min() > 1e10}")

# Convert to datetime
df['datetime'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
print(f"\nFirst datetime: {df['datetime'].iloc[0]}")
print(f"Last datetime: {df['datetime'].iloc[-1]}")