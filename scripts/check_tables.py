import duckdb

con = duckdb.connect('data/btc_klines.duckdb')
tables = con.execute('SHOW TABLES').fetchall()
print("Tables:", tables)

if tables:
    # Get the actual table name
    table_name = tables[0][0]
    print(f"\nTable name: {table_name}")
    
    result = con.execute(f'SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM {table_name}').fetchone()
    print(f"Rows: {result[0]:,}")
    print(f"Min time: {result[1]}")
    print(f"Max time: {result[2]}")
    
    df = con.execute(f'SELECT * FROM {table_name} LIMIT 5').fetchdf()
    print("\nFirst 5 rows:")
    print(df.to_string())

con.close()
print("\nDuckDB check complete!")