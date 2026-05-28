#!/usr/bin/env python3
"""Test pyarrow schema syntax"""
import pyarrow as pa
print(f"pyarrow version: {pa.__version__}")

# Test 1: with parentheses (function call)
try:
    t1 = pa.schema([("a", pa.int64())])
    print(f"int64() works: {t1}")
except Exception as e:
    print(f"int64() failed: {e}")

# Test 2: without parentheses
try:
    t2 = pa.schema([("a", pa.int64)])
    print(f"int64 (no parens) works: {t2}")
except Exception as e:
    print(f"int64 (no parens) failed: {e}")