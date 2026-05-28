#!/usr/bin/env python3
"""Debug the gap filling issue"""
from pathlib import Path
import pandas as pd
from datetime import datetime

DATA_DIR = Path(r"w:\nautilusTrader\data\binance_klines")

# Read first CSV
csv_files = sorted(DATA_DIR.glob("BTCUSDT-15m-*.csv"))
first_file = csv_files[0]
print(f"Reading: {first_file.name}")

COLUMN_NAMES = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base_volume", "taker_buy_quote_volume",
]

df = pd.read_csv(first_file, header=None, names=COLUMN_NAMES)

# Convert types
for col in ["open", "high", "low", "close", "volume", "quote_volume",
            "taker_buy_base_volume", "taker_buy_quote_volume"]:
    df[col] = df[col].astype("float64")

for col in ["open_time", "close_time", "trades"]:
    df[col] = df[col].astype("int64")

print(f"Original rows: {len(df)}")
print(f"First 3 open_time: {df['open_time'].head(3).tolist()}")
print(f"Last 3 open_time: {df['open_time'].tail(3).tolist()}")

# Check time diffs
df = df.sort_values("open_time").reset_index(drop=True)
time_diffs = df["open_time"].diff()
print(f"\nTime diff stats:")
print(f"  Min diff: {time_diffs.min()}")
print(f"  Max diff: {time_diffs.max()}")
print(f"  Expected: 900000 (15 min in ms)")
print(f"  Normal bars (>0 and <=900000): {((time_diffs > 0) & (time_diffs <= 900000)).sum()}")
print(f"  Gaps (not 900000): {(~((time_diffs == 900000) | time_diffs.isna())).sum()}")

# The issue: timestamps are NOT 900000ms apart?
# Let's check what the actual time differences look like
print(f"\nFirst 10 time diffs:")
for i, diff in enumerate(time_diffs.head(10)):
    print(f"  {i}: {diff}")

# It seems the data might have 1-minute bars or different spacing
# Let's see the actual timestamps
print(f"\nFirst few timestamps as datetime:")
for ts in df['open_time'].head(5):
    dt = pd.to_datetime(ts, unit='ms', utc=True)
    print(f"  {ts} -> {dt}")