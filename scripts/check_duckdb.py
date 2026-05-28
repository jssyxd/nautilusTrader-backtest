#!/usr/bin/env python3
"""Check DuckDB data content"""
import duckdb

con = duckdb.connect('data/btc_klines.duckdb')
result = con.execute('SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM btc_klines_15m').fetchone()
print(f"Row count: {result[0]:,}")
print(f"Min time: {result[1]}")
print(f"Max time: {result[2]}")

df = con.execute('SELECT * FROM btc_klines_15m LIMIT 5').fetchdf()
print("\nFirst 5 rows:")
print(df.to_string())

con.close()
print("\nDuckDB check complete!")