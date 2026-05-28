#!/usr/bin/env python3
"""
CSV → Parquet 转换脚本
将 Binance K线 CSV 文件转换为 Parquet 格式，供 NautilusTrader 和 DuckDB 使用
"""

import os
import glob
from pathlib import Path
from datetime import datetime
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm
import duckdb

# ===================== 配置 =====================
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
# 数据实际路径在 w:\nautilusTrader\data\binance_klines（向上查找）
DATA_DIR = PROJECT_DIR / "data" / "binance_klines"
if not DATA_DIR.exists():
    DATA_DIR = PROJECT_DIR.parent / "data" / "binance_klines"

OUTPUT_DIR = PROJECT_DIR / "data"
OUTPUT_FILE = OUTPUT_DIR / "btc_klines_15m_aligned.parquet"
CATALOG_FILE = OUTPUT_DIR / "catalog.parquet"
DUCKDB_FILE = OUTPUT_DIR / "btc_klines.duckdb"
# =============================================

# Binance CSV 列名（12列，最后一列忽略）
COLUMN_NAMES = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",  # 最后一列，可能是 filler
]

# Parquet schema 定义
PARQUET_SCHEMA = pa.schema([
    ("open_time", pa.int64()),       # 毫秒时间戳
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("volume", pa.float64()),
    ("close_time", pa.int64()),
    ("quote_volume", pa.float64()),
    ("trades", pa.int64()),
    ("taker_buy_base_volume", pa.float64()),
    ("taker_buy_quote_volume", pa.float64()),
    ("bar_date", pa.date32()),       # 便于 DuckDB 过滤
    ("bar_hour", pa.int16()),        # 便于按小时过滤
])


def parse_csv_to_df(csv_path: Path) -> pd.DataFrame:
    """解析单个 CSV 文件为 DataFrame"""
    df = pd.read_csv(
        csv_path,
        header=None,
        names=COLUMN_NAMES,
    )

    # 去除忽略的列
    df = df.drop(columns=["ignore"])

    # 转换时间戳为 datetime（UTC+0）- open_time 已经是毫秒
    df["datetime"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

    # 添加日期和小时列（便于过滤）
    df["bar_date"] = df["datetime"].dt.date
    df["bar_hour"] = df["datetime"].dt.hour

    # 去除不需要的列
    df = df.drop(columns=["datetime"])

    return df


def validate_bar_continuity(df: pd.DataFrame, expected_period_ms: int = None) -> dict:
    """验证 Bar 的连续性（15分钟 = 900,000 ms 或 900 s）"""
    if len(df) < 2:
        return {"valid": True, "gaps": 0}

    df = df.sort_values("open_time").reset_index(drop=True)
    
    # 自动检测时间戳单位
    sample_ts = df["open_time"].iloc[0]
    if expected_period_ms is None:
        if sample_ts < 1e10:
            expected_period_ms = 900  # 秒
        else:
            expected_period_ms = 900_000  # 毫秒
    
    time_diffs = df["open_time"].diff()

    # 正常间隔
    normal_mask = (time_diffs == expected_period_ms) | (time_diffs.isna())

    # 检测异常
    gaps = time_diffs[~normal_mask & time_diffs.notna()]

    if len(gaps) > 0:
        return {
            "valid": False,
            "gaps": len(gaps),
            "total_bars": len(df),
            "gap_details": gaps.head(10).to_dict()
        }

    return {"valid": True, "gaps": 0, "total_bars": len(df)}


def forward_fill_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """向前填充缺失的 Bar（用上一个 Bar 的收盘价填充）"""
    df = df.sort_values("open_time").reset_index(drop=True)

    # Timestamps are already in milliseconds (converted in parse_csv_to_df)
    expected_period_ms = 900_000  # 15 分钟=900000毫秒
    all_times = []
    current_time = df["open_time"].min()
    end_time = df["open_time"].max()

    while current_time <= end_time:
        all_times.append(current_time)
        current_time += expected_period_ms

    # 创建完整时间序列
    full_df = pd.DataFrame({"open_time": all_times})
    merged = full_df.merge(df, on="open_time", how="left")

    # 向前填充
    merged["open"] = merged["open"].ffill()
    merged["high"] = merged["high"].ffill()
    merged["low"] = merged["low"].ffill()
    merged["close"] = merged["close"].ffill()
    merged["volume"] = merged["volume"].fillna(0)
    merged["quote_volume"] = merged["quote_volume"].fillna(0)
    merged["trades"] = merged["trades"].fillna(0).astype("int64")
    merged["taker_buy_base_volume"] = merged["taker_buy_base_volume"].ffill()
    merged["taker_buy_quote_volume"] = merged["taker_buy_quote_volume"].ffill()

    # 重新计算日期和小时
    merged["datetime"] = pd.to_datetime(merged["open_time"], unit="ms", utc=True)
    merged["bar_date"] = merged["datetime"].dt.date
    merged["bar_hour"] = merged["datetime"].dt.hour
    merged = merged.drop(columns=["datetime"])

    return merged


def main():
    """主函数"""
    print("=" * 60)
    print("Binance K线 CSV → Parquet 转换器")
    print("=" * 60)

    # 查找所有 CSV 文件
    csv_files = sorted(DATA_DIR.glob("BTCUSDT-15m-*.csv"))

    if not csv_files:
        print(f"\n⚠ 未找到 CSV 文件，请先运行 download_binance_data.py")
        return

    print(f"\n找到 {len(csv_files)} 个 CSV 文件")
    print(f"输出目录: {OUTPUT_DIR}")

    all_dfs = []
    all_validations = []

    # 逐个处理 CSV 文件
    for csv_file in tqdm(csv_files, desc="处理 CSV 文件"):
        try:
            df = parse_csv_to_df(csv_file)

            # 验证连续性
            validation = validate_bar_continuity(df)
            validation["file"] = csv_file.name
            all_validations.append(validation)

            # 如果有缺失 Bar，进行填充
            if not validation["valid"]:
                print(f"\n  ⚠ {csv_file.name}: 发现 {validation['gaps']} 个间隙，进行填充...")
                df = forward_fill_gaps(df)
                validation = validate_bar_continuity(df)
                validation["file"] = csv_file.name + " (after fill)"
                all_validations.append(validation)

            all_dfs.append(df)

        except Exception as e:
            print(f"\n  ⚠ {csv_file.name}: 处理失败 - {str(e)}")

    # 合并所有 DataFrame
    print("\n合并数据...")
    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df = combined_df.sort_values("open_time").reset_index(drop=True)

    print(f"合并后总行数: {len(combined_df):,}")

    # 去除重复
    combined_df = combined_df.drop_duplicates(subset=["open_time"], keep="first")

    # 验证时间范围
    start_time = pd.to_datetime(combined_df["open_time"].min(), unit="ms", utc=True)
    end_time = pd.to_datetime(combined_df["open_time"].max(), unit="ms", utc=True)
    print(f"时间范围: {start_time} ~ {end_time}")

    # 转换为 Parquet
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n写入 Parquet 文件...")
    table = pa.Table.from_pandas(combined_df, schema=PARQUET_SCHEMA, preserve_index=False)

    # 使用分块写入避免内存溢出
    with pq.ParquetWriter(OUTPUT_FILE, schema=PARQUET_SCHEMA) as writer:
        batch_size = 100_000
        for i in range(0, len(combined_df), batch_size):
            batch_df = combined_df.iloc[i:i+batch_size]
            batch_table = pa.Table.from_pandas(batch_df, schema=PARQUET_SCHEMA)
            writer.write_table(batch_table)

    print(f"✓ Parquet 文件已保存: {OUTPUT_FILE}")

    # 创建 catalog
    catalog_data = {
        "file": str(OUTPUT_FILE),
        "row_count": len(combined_df),
        "start_time": str(start_time),
        "end_time": str(end_time),
        "columns": list(combined_df.columns),
        "source_files": [f.name for f in csv_files],
    }

    catalog_df = pd.DataFrame([catalog_data])
    catalog_df.to_parquet(CATALOG_FILE, index=False)
    print(f"✓ Catalog 已保存: {CATALOG_FILE}")

    # 创建 DuckDB 数据库
    print("\n创建 DuckDB 数据库...")
    if DUCKDB_FILE.exists():
        DUCKDB_FILE.unlink()
    con = duckdb.connect(DUCKDB_FILE)

    # 注册 Parquet 文件
    con.execute(f"""
        CREATE TABLE btc_klines AS SELECT * FROM read_parquet('{OUTPUT_FILE}')
    """)

    # 创建索引以加速查询
    con.execute("""
        CREATE INDEX idx_open_time ON btc_klines(open_time)
    """)
    con.execute("""
        CREATE INDEX idx_bar_date ON btc_klines(bar_date)
    """)

    # 验证数据
    result = con.execute("""
        SELECT
            MIN(open_time) as min_time,
            MAX(open_time) as max_time,
            COUNT(*) as total_rows,
            COUNT(DISTINCT bar_date) as total_days
        FROM btc_klines
    """).fetchone()

    print(f"\nDuckDB 验证结果:")
    print(f"  时间范围: {pd.to_datetime(result[0], unit='ms', utc=True)} ~ {pd.to_datetime(result[1], unit='ms', utc=True)}")
    print(f"  总行数: {result[2]:,}")
    print(f"  总天数: {result[3]:,}")
    print(f"✓ DuckDB 数据库已保存: {DUCKDB_FILE}")

    # 关闭连接
    con.close()

    # 打印 Gap 汇总
    print("\n" + "=" * 60)
    print("数据验证汇总:")
    print("=" * 60)
    for v in all_validations:
        status = "✓" if v["valid"] else "⚠"
        if "gaps" in v:
            print(f"{status} {v['file']}: {v.get('total_bars', 0):,} bars, {v.get('gaps', 0)} gaps")
        else:
            print(f"{status} {v['file']}: {v.get('error', 'Unknown error')}")

    print("\n" + "=" * 60)
    print("转换完成！")
    print(f"Parquet: {OUTPUT_FILE}")
    print(f"DuckDB: {DUCKDB_FILE}")
    print("下一步: 运行 backtest/rsi_snap_back_long.py 进行回测")
    print("=" * 60)


if __name__ == "__main__":
    main()