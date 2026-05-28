#!/usr/bin/env python3
"""Debug path configuration"""
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data" / "binance_klines"

print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"PROJECT_DIR: {PROJECT_DIR}")
print(f"DATA_DIR: {DATA_DIR}")
print(f"DATA_DIR exists: {DATA_DIR.exists()}")

if not DATA_DIR.exists():
    ALT_DATA_DIR = PROJECT_DIR.parent / "data" / "binance_klines"
    print(f"ALT_DATA_DIR: {ALT_DATA_DIR}")
    print(f"ALT exists: {ALT_DATA_DIR.exists()}")

csv_files = list(DATA_DIR.glob("*.csv"))[:3]
print(f"CSV files: {csv_files}")