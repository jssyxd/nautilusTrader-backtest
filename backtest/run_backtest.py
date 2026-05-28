#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Snap-Back Long 回测运行器

功能:
1. 3年全程回测
2. 45天滚动窗口回测
3. 生成交易记录和性能指标
"""

import sys
import json
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq

# 添加项目根目录到路径
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model import TraderId
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue, InstrumentId, Symbol
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from strategies.rsi_snap_back_long import RSISnapBackLong, RSISnapBackLongConfig


# ===================== 配置 =====================
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
PARQUET_FILE = DATA_DIR / "btc_klines_15m_aligned.parquet"
OUTPUT_DIR = PROJECT_DIR / "backtest"
INITIAL_CAPITAL = 10_000  # $10,000
TRADE_SIZE = Decimal("0.10")  # 10% 保证金（5x杠杆 = 50% 仓位，实际用 10% 保证金）
BAR_INTERVAL = "15-MINUTE"

# 策略参数
EMA_PERIOD = 200
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 20.0
STOCH_PERIOD_K = 14
STOCH_PERIOD_D = 3
STOCH_BUY_THRESHOLD = 25.0
STOP_LOSS_PCT = 0.025  # 2.5%
TAKE_PROFIT_PCT = 0.075  # 7.5%
EMA_FILTER_RATIO = 0.9

# 滚动窗口参数
ROLLING_WINDOW_DAYS = 45
ROLLING_STEP_DAYS = 45
# =============================================


def create_btcusdt_instrument() -> CryptoPerpetual:
    """创建 BTCUSDT 永续合约 - 使用 TestInstrumentProvider"""
    return TestInstrumentProvider.btcusdt_perp_binance()


def load_bars_from_parquet(
    parquet_file: Path,
    instrument: CryptoPerpetual,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> list[Bar]:
    """从 Parquet 文件加载 K 线数据"""
    if not parquet_file.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_file}")

    # 读取 Parquet
    table = pq.read_table(
        parquet_file,
        filters=[
            ("open_time", ">=", int(start_time.timestamp() * 1000)) if start_time else None,
            ("open_time", "<=", int(end_time.timestamp() * 1000)) if end_time else None,
        ] if start_time or end_time else None,
    )
    df = table.to_pandas()

    if df.empty:
        raise ValueError("No data loaded from Parquet")

    # 转换时间戳
    df["datetime"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

    # 过滤时间范围 (确保时区兼容性)
    if start_time:
        start_time_aware = pd.Timestamp(start_time, tz="UTC")
        df = df[df["datetime"] >= start_time_aware]
    if end_time:
        end_time_aware = pd.Timestamp(end_time, tz="UTC")
        df = df[df["datetime"] <= end_time_aware]

    # 按时间排序
    df = df.sort_values("open_time").reset_index(drop=True)

    # 创建 BarType
    bar_type_str = f"{instrument.id}-15-MINUTE-LAST-EXTERNAL"
    bar_type = BarType.from_str(bar_type_str)

    # 创建 BarDataWrangler
    wrangler = BarDataWrangler(bar_type, instrument)

    # 设置 datetime 为索引 (NautilusTrader 要求 DatetimeIndex)
    price_data = df[["open", "high", "low", "close", "volume"]].copy()
    price_data.index = df["datetime"]

    # 转换为 Bar 对象列表
    bars_list: list[Bar] = wrangler.process(price_data)

    return bars_list


def run_backtest(
    bars: list[Bar],
    instrument: CryptoPerpetual,
    start_time: datetime,
    end_time: datetime,
    leverage: Decimal = Decimal("5"),
) -> tuple[BacktestEngine, RSISnapBackLong]:
    """运行单个回测"""

    # 配置回测引擎
    engine_config = BacktestEngineConfig(
        trader_id=TraderId("BACKTEST-SNAPBACK-001"),
        logging=LoggingConfig(log_level="WARNING"),  # 减少日志输出
    )
    engine = BacktestEngine(config=engine_config)

    # 添加交易所
    engine.add_venue(
        venue=Venue("BINANCE"),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(INITIAL_CAPITAL, USD)],
        base_currency=USD,
        default_leverage=leverage,
    )

    # 添加合约
    engine.add_instrument(instrument)

    # 添加 K 线数据
    engine.add_data(bars)

    # 配置策略
    bar_type_str = f"{instrument.id}-15-MINUTE-LAST-EXTERNAL"
    bar_type = BarType.from_str(bar_type_str)

    strategy_config = RSISnapBackLongConfig(
        instrument_id=instrument.id,
        bar_type=bar_type,
        trade_size=TRADE_SIZE,
        ema_period=EMA_PERIOD,
        rsi_period=RSI_PERIOD,
        rsi_buy_threshold=RSI_BUY_THRESHOLD,
        stoch_period_k=STOCH_PERIOD_K,
        stoch_period_d=STOCH_PERIOD_D,
        stoch_buy_threshold=STOCH_BUY_THRESHOLD,
        stop_loss_pct=STOP_LOSS_PCT,
        take_profit_pct=TAKE_PROFIT_PCT,
        ema_filter_ratio=EMA_FILTER_RATIO,
    )

    strategy = RSISnapBackLong(config=strategy_config)
    engine.add_strategy(strategy)

    # 运行回测
    engine.run()

    return engine, strategy


def calculate_metrics(trades: list[dict]) -> dict:
    """计算性能指标"""
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "max_win": 0,
            "max_loss": 0,
            "avg_holding_minutes": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
        }

    df = pd.DataFrame(trades)

    total_trades = len(df)
    winning_trades = len(df[df["pnl"] > 0])
    losing_trades = len(df[df["pnl"] <= 0])

    win_rate = winning_trades / total_trades if total_trades > 0 else 0

    total_pnl = df["pnl"].sum()
    total_pnl_pct = df["pnl_pct"].sum()

    avg_win = df[df["pnl"] > 0]["pnl"].mean() if winning_trades > 0 else 0
    avg_loss = abs(df[df["pnl"] <= 0]["pnl"].mean()) if losing_trades > 0 else 0

    profit_factor = (avg_win * winning_trades) / (avg_loss * losing_trades) if avg_loss > 0 and losing_trades > 0 else float("inf")

    max_win = df["pnl"].max() if not df.empty else 0
    max_loss = abs(df["pnl"].min()) if not df.empty else 0

    avg_holding = df["holding_minutes"].mean() if not df.empty else 0

    # 简化版 Sharpe（假设无风险利率为 0）
    if not df.empty and df["pnl"].std() > 0:
        returns = df["pnl_pct"] / 100
        sharpe = returns.mean() / returns.std() * (252 ** 0.5)  # 年化
    else:
        sharpe = 0

    # 简化版 Max Drawdown
    cumulative = (1 + df["pnl_pct"] / 100).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = abs(drawdown.min()) * 100 if not drawdown.empty else 0

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_win": max_win,
        "max_loss": max_loss,
        "avg_holding_minutes": avg_holding,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
    }


def generate_equity_curve(trades: list[dict], initial_capital: float = INITIAL_CAPITAL) -> list[dict]:
    """生成权益曲线数据"""
    if not trades:
        return []

    equity_curve = []
    equity = initial_capital

    for i, trade in enumerate(trades):
        equity += trade["pnl"]
        equity_curve.append({
            "trade_num": i + 1,
            "timestamp": trade["exit_time"],
            "equity": equity,
            "cumulative_return": (equity - initial_capital) / initial_capital * 100,
        })

    return equity_curve


def main():
    """主函数"""
    print("=" * 60)
    print("BTC Snap-Back Long - 3年回测")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 检查数据文件
    if not PARQUET_FILE.exists():
        print(f"\n⚠ 数据文件不存在: {PARQUET_FILE}")
        print("请先运行: python scripts/download_binance_data.py")
        print("然后运行: python scripts/convert_to_parquet.py")
        return

    # 创建合约
    instrument = create_btcusdt_instrument()
    print(f"\n合约: {instrument.id}")

    # ========== 3年全程回测 ==========
    print("\n" + "-" * 60)
    print("开始 3年全程回测...")
    print("-" * 60)

    # 定义时间范围（36个月）
    start_date = datetime(2023, 5, 1, tzinfo=None)
    end_date = datetime(2026, 5, 28, tzinfo=None)

    try:
        # 加载全部数据
        print(f"\n加载数据: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
        all_bars = load_bars_from_parquet(PARQUET_FILE, instrument, start_date, end_date)
        print(f"加载完成: {len(all_bars):,} 根 K 线")

        # 运行回测
        engine, strategy = run_backtest(all_bars, instrument, start_date, end_date)

        # 获取结果
        trades = strategy.get_trade_log()
        metrics = calculate_metrics(trades)
        equity_curve = generate_equity_curve(trades)

        # 打印结果
        print(f"\n3年全程回测结果:")
        print(f"  总交易次数: {metrics['total_trades']}")
        print(f"  盈利交易: {metrics['winning_trades']}, 亏损交易: {metrics['losing_trades']}")
        print(f"  胜率: {metrics['win_rate']:.1%}")
        print(f"  总盈亏: ${metrics['total_pnl']:.2f} ({metrics['total_pnl_pct']:.2f}%)")
        print(f"  盈亏比: {metrics['profit_factor']:.2f}")
        print(f"  夏普比率: {metrics['sharpe_ratio']:.2f}")
        print(f"  最大回撤: {metrics['max_drawdown']:.2f}%")
        print(f"  平均持仓时间: {metrics['avg_holding_minutes']:.1f} 分钟")

        # 保存交易记录
        trades_file = OUTPUT_DIR / "full_backtest_trades.json"
        with open(trades_file, "w", encoding="utf-8") as f:
            json.dump({
                "metrics": metrics,
                "trades": trades,
                "equity_curve": equity_curve,
            }, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n✓ 交易记录已保存: {trades_file}")

        # 清理
        engine.dispose()

    except Exception as e:
        print(f"\n⚠ 回测失败: {str(e)}")
        import traceback
        traceback.print_exc()

    # ========== 滚动窗口回测 ==========
    print("\n" + "-" * 60)
    print("开始 45天滚动窗口回测...")
    print("-" * 60)

    window_results = []
    current_start = start_date
    window_num = 0

    while current_start + timedelta(days=ROLLING_WINDOW_DAYS) <= end_date:
        window_num += 1
        window_end = current_start + timedelta(days=ROLLING_WINDOW_DAYS)

        try:
            # 加载窗口数据
            window_bars = load_bars_from_parquet(PARQUET_FILE, instrument, current_start, window_end)

            if len(window_bars) < 100:  # 数据太少跳过
                current_start += timedelta(days=ROLLING_STEP_DAYS)
                continue

            # 运行窗口回测
            window_engine, window_strategy = run_backtest(
                window_bars, instrument, current_start, window_end
            )

            # 获取结果
            window_trades = window_strategy.get_trade_log()
            window_metrics = calculate_metrics(window_trades)
            window_metrics["window_num"] = window_num
            window_metrics["start_date"] = current_start.isoformat()
            window_metrics["end_date"] = window_end.isoformat()
            window_metrics["bars_loaded"] = len(window_bars)

            window_results.append(window_metrics)

            print(
                f"  窗口 {window_num:2d}: {current_start.strftime('%Y-%m-%d')} ~ "
                f"{window_end.strftime('%Y-%m-%d')}: "
                f"{window_metrics['total_trades']} 笔, "
                f"收益 {window_metrics['total_pnl_pct']:+.2f}%, "
                f"夏普 {window_metrics['sharpe_ratio']:.2f}"
            )

            window_engine.dispose()

        except Exception as e:
            print(f"  ⚠ 窗口 {window_num} 失败: {str(e)}")

        current_start += timedelta(days=ROLLING_STEP_DAYS)

    # 保存滚动窗口结果
    if window_results:
        rolling_file = OUTPUT_DIR / "rolling_window_results.json"
        with open(rolling_file, "w", encoding="utf-8") as f:
            json.dump(window_results, f, indent=2, ensure_ascii=False)
        print(f"\n✓ 滚动窗口结果已保存: {rolling_file}")

        # 汇总统计
        winning_windows = sum(1 for w in window_results if w["total_pnl"] > 0)
        avg_trades = sum(w["total_trades"] for w in window_results) / len(window_results)
        avg_pnl = sum(w["total_pnl_pct"] for w in window_results) / len(window_results)
        avg_sharpe = sum(w["sharpe_ratio"] for w in window_results) / len(window_results)

        print(f"\n滚动窗口汇总:")
        print(f"  窗口总数: {len(window_results)}")
        print(f"  盈利窗口: {winning_windows}, 亏损窗口: {len(window_results) - winning_windows}")
        print(f"  平均每窗口交易: {avg_trades:.1f} 笔")
        print(f"  平均收益率: {avg_pnl:+.2f}%")
        print(f"  平均夏普: {avg_sharpe:.2f}")

    print("\n" + "=" * 60)
    print("回测完成！")
    print(f"下一步: python backtest/report_generator.py 生成 HTML 报告")
    print("=" * 60)


if __name__ == "__main__":
    main()