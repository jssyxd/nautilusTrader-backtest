# Binace K线数据下载脚本
# BTCUSDT 15分钟K线，近3年数据
# 数据源: https://data.binance.vision

import os
import zipfile
import requests
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ===================== 配置 =====================
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m"
DATA_DIR = Path(__file__).parent.parent / "data" / "binance_klines"
START_DATE = "2023-05-01"
END_DATE = "2026-05-01"
MAX_WORKERS = 4  # 并发下载数
CHUNK_SIZE = 8192
# =============================================

# 月份列表生成
def generate_monthly_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """生成月份范围列表 [(2023-05, 2023-06), ...]"""
    ranges = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        year = current.year
        month = current.month
        next_month = current + timedelta(days=32)
        next_month = next_month.replace(day=1)

        file_key = f"BTCUSDT-15m-{year}-{month:02d}"
        ranges.append((file_key, f"{year}-{month:02d}"))

        current = next_month

    return ranges


def download_file(file_key: str, target_dir: Path) -> tuple[bool, str]:
    """下载单个 zip 文件"""
    zip_url = f"{BASE_URL}/{file_key}.zip"
    zip_path = target_dir / f"{file_key}.zip"
    extract_dir = target_dir / file_key

    # 跳过已存在的完整数据
    csv_file = target_dir / f"{file_key}.csv"
    if csv_file.exists():
        return True, f"{file_key} - CSV already exists, skipping"

    try:
        # 下载 zip
        response = requests.get(zip_url, timeout=60)
        response.raise_for_status()

        # 保存 zip
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                f.write(chunk)

        # 解压
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # 移动 csv 文件到目标位置（有些解压后有子文件夹）
        for csv_path in extract_dir.rglob("*.csv"):
            if csv_path.name == f"{file_key}.csv":
                csv_path.rename(target_dir / f"{file_key}.csv")
                break

        # 删除 zip 和解压目录
        zip_path.unlink(missing_ok=True)
        if extract_dir.exists():
            for f in extract_dir.iterdir():
                f.rename(target_dir / f.name)
            extract_dir.rmdir()

        return True, f"{file_key} - SUCCESS"

    except Exception as e:
        return False, f"{file_key} - FAILED: {str(e)}"


def verify_csv(file_path: Path) -> dict:
    """验证 CSV 文件的完整性"""
    if not file_path.exists():
        return {"valid": False, "error": "File not found"}

    try:
        with open(file_path, 'r') as f:
            header = f.readline().strip()
            # Binance CSV 格式: open_time, open, high, low, close, volume, close_time, ...
            expected_cols = 11
            actual_cols = len(header.split(','))

            if actual_cols != expected_cols:
                return {"valid": False, "error": f"Column count mismatch: {actual_cols} vs {expected_cols}"}

            # 快速统计行数（不加载全部到内存）
            line_count = 0
            last_line = None
            for line in f:
                line_count += 1
                last_line = line.strip()

            return {
                "valid": True,
                "rows": line_count,
                "last_line": last_line,
                "header": header
            }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def main():
    """主函数"""
    # 创建目录
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Binance BTCUSDT 15m K线数据下载器")
    print(f"数据范围: {START_DATE} ~ {END_DATE}")
    print(f"保存目录: {DATA_DIR}")
    print("=" * 60)

    # 生成文件列表
    monthly_ranges = generate_monthly_ranges(START_DATE, END_DATE)
    print(f"\n需要下载 {len(monthly_ranges)} 个月的数据")

    # 下载所有文件
    results = []
    print(f"\n开始下载（并发数: {MAX_WORKERS}）...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(download_file, file_key, DATA_DIR): file_key
            for file_key, _ in monthly_ranges
        }

        for future in tqdm(as_completed(futures), total=len(futures), desc="下载进度"):
            success, message = future.result()
            results.append((success, message))
            if not success:
                print(f"\n  ⚠ {message}")

    # 统计结果
    success_count = sum(1 for s, _ in results if s)
    print(f"\n下载完成: {success_count}/{len(results)} 成功")

    # 验证所有 CSV
    print("\n开始验证 CSV 文件...")
    verification_results = []

    for file_key, _ in monthly_ranges:
        csv_file = DATA_DIR / f"{file_key}.csv"
        result = verify_csv(csv_file)
        result["file"] = file_key
        verification_results.append(result)

    valid_count = sum(1 for r in verification_results if r["valid"])
    print(f"\n验证完成: {valid_count}/{len(verification_results)} 个文件有效")

    # 打印无效文件
    for r in verification_results:
        if not r["valid"]:
            print(f"  ⚠ {r['file']}: {r['error']}")

    # 打印统计
    total_rows = sum(r.get("rows", 0) for r in verification_results if r["valid"])
    print(f"\n总行数: {total_rows:,}")
    print(f"预期行数（每文件29,760行）: {len(monthly_ranges) * 29760:,}")

    # 列出所有已下载的文件
    print("\n已下载文件列表:")
    for file_key, _ in monthly_ranges:
        csv_file = DATA_DIR / f"{file_key}.csv"
        if csv_file.exists():
            size = csv_file.stat().st_size / (1024 * 1024)  # MB
            print(f"  ✓ {file_key}.csv ({size:.2f} MB)")

    print("\n" + "=" * 60)
    print("下载任务完成！")
    print("下一步: 运行 convert_to_parquet.py 转换为 Parquet 格式")
    print("=" * 60)


if __name__ == "__main__":
    main()