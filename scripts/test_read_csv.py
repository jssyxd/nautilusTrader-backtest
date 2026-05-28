#!/usr/bin/env python3
"""Minimal test for CSV processing"""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data" / "binance_klines"
if not DATA_DIR.exists():
    DATA_DIR = PROJECT_DIR.parent / "data" / "binance_klines"

print(f"DATA_DIR: {DATA_DIR}")
print(f"DATA_DIR exists: {DATA_DIR.exists()}")

csv_files = sorted(DATA_DIR.glob("BTCUSDT-15m-*.csv"))
print(f"Found {len(csv_files)} CSV files")
print(f"First 3: {[f.name for f in csv_files[:3]]}")

if csv_files:
    first_file = csv_files[0]
    print(f"\nReading first file: {first_file.name}")
    import pandas as pd
    
    COLUMN_NAMES = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base_volume", "taker_buy_quote_volume",
    ]
    
    df = pd.read_csv(first_file, header=None, names=COLUMN_NAMES)
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    print(f"First row: {df.iloc[0].to_dict()}")
    print("\nTest successful!")
else:
    print("No CSV files found!")