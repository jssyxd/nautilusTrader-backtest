#!/usr/bin/env python3
"""
DuckDB 验证脚本
使用 DuckDB 检索 Parquet 数据，验证数据完整性
"""

import duckdb
from pathlib import Path
from datetime import datetime
import pandas as pd

# ===================== 配置 =====================
PROJECT_DIR = Path(__file__).parent.parent
DUCKDB_FILE = PROJECT_DIR / "data" / "btc_klines.duckdb"
PARQUET_FILE = PROJECT_DIR / "data" / "btc_klines_15m_aligned.parquet"
# =============================================


def query_duckdb():
    """使用 DuckDB 查询数据"""
    print("=" * 60)
    print("DuckDB 数据验证")
    print("=" * 60)

    if not DUCKDB_FILE.exists():
        print(f"\n⚠ DuckDB 文件不存在: {DUCKDB_FILE}")
        print("请先运行 convert_to_parquet.py")
        return

    con = duckdb.connect(DUCKDB_FILE, read_only=True)

    # 1. 基本统计
    print("\n【1. 基本统计】")
    result = con.execute("""
        SELECT
            MIN(open_time) as min_time,
            MAX(open_time) as max_time,
            COUNT(*) as total_rows,
            COUNT(DISTINCT bar_date) as total_days,
            SUM(trades) as total_trades
        FROM btc_klines
    """).fetchone()

    min_dt = pd.to_datetime(result[0], unit="ms", utc=True)
    max_dt = pd.to_datetime(result[1], unit="ms", utc=True)

    print(f"  时间范围: {min_dt} ~ {max_dt}")
    print(f"  总行数: {result[2]:,}")
    print(f"  总天数: {result[3]:,}")
    print(f"  总交易笔数: {result[4]:,}")

    # 2. 每月统计
    print("\n【2. 每月 Bar 数量统计】")
    result = con.execute("""
        SELECT
            DATE_TRUNC('month', open_time) as month,
            COUNT(*) as bar_count,
            SUM(trades) as trade_count
        FROM btc_klines
        GROUP BY DATE_TRUNC('month', open_time)
        ORDER BY month
    """).fetchall()

    print(f"  {'月份':<15} {'Bar数':>12} {'交易数':>15}")
    print(f"  {'-'*15} {'-'*12} {'-'*15}")
    for row in result:
        month_str = row[0].strftime("%Y-%m") if hasattr(row[0], 'strftime') else str(row[0])
        print(f"  {month_str:<15} {row[1]:>12,} {row[2]:>15,}")

    # 3. 验证 Bar 间隔
    print("\n【3. Bar 间隔验证】")
    result = con.execute("""
        WITH time_diffs AS (
            SELECT
                open_time,
                open_time - LAG(open_time) OVER (ORDER BY open_time) as diff_ms
            FROM btc_klines
        )
        SELECT
            diff_ms,
            COUNT(*) as count
        FROM time_diffs
        WHERE diff_ms IS NOT NULL
        GROUP BY diff_ms
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()

    for row in result:
        diff_min = row[0] / 60_000 if row[0] else 0
        print(f"  间隔 {diff_min:.0f} 分钟: {row[1]:,} 次")

    # 4. 价格统计
    print("\n【4. 价格统计】")
    result = con.execute("""
        SELECT
            MIN(LOW) as min_low,
            MAX(HIGH) as max_high,
            AVG(close) as avg_close,
            MAX(trades) as max_trades_in_bar
        FROM btc_klines
    """).fetchone()

    print(f"  最低价: ${result[0]:,.2f}")
    print(f"  最高价: ${result[1]:,.2f}")
    print(f"  平均收盘价: ${result[2]:,.2f}")
    print(f"  单 Bar 最高交易数: {result[3]:,}")

    # 5. 按日统计交易量
    print("\n【5. 每日交易量 Top 10】")
    result = con.execute("""
        SELECT
            bar_date,
            SUM(volume) as total_volume,
            SUM(trades) as total_trades
        FROM btc_klines
        GROUP BY bar_date
        ORDER BY total_volume DESC
        LIMIT 10
    """).fetchall()

    print(f"  {'日期':<15} {'交易量(BTC)':>18} {'交易笔数':>15}")
    print(f"  {'-'*15} {'-'*18} {'-'*15}")
    for row in result:
        date_str = str(row[0])
        print(f"  {date_str:<15} {row[1]:>18,.2f} {row[2]:>15,}")

    con.close()

    print("\n" + "=" * 60)
    print("验证完成！")
    print("=" * 60)


def direct_parquet_query():
    """直接查询 Parquet 文件（不通过 DuckDB）"""
    import pyarrow.parquet as pq

    print("\n" + "=" * 60)
    print("Parquet 文件直接读取")
    print("=" * 60)

    if not PARQUET_FILE.exists():
        print(f"\n⚠ Parquet 文件不存在: {PARQUET_FILE}")
        return

    # 读取 schema
    schema = pq.read_schema(PARQUET_FILE)
    print(f"\nSchema 字段:")
    for field in schema:
        print(f"  {field.name}: {field.type}")

    # 读取 row groups
    parquet_file = pq.ParquetFile(PARQUET_FILE)
    print(f"\nRow Groups: {parquet_file.metadata.num_row_groups}")
    print(f"总行数: {parquet_file.metadata.num_rows:,}")

    # 读取前几行
    df = pq.read_table(PARQUET_FILE, columns=["open_time", "open", "high", "low", "close", "volume"]).to_pandas()
    print(f"\n前 5 行数据:")
    print(df.head())


if __name__ == "__main__":
    query_duckdb()
    print()
    direct_parquet_query()