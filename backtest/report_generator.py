#!/usr/bin/env python3
"""
BTC Snap-Back Long - HTML 报告生成器
生成中文回测报告，包含详细交易记录
"""

import json
import datetime
from pathlib import Path
from typing import Optional

# 尝试导入需要的库，如果没有则使用基础 HTML 生成
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def load_json(file_path: str) -> dict:
    """加载 JSON 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_trades_from_json(trades_file: str) -> list:
    """从交易 JSON 文件中提取交易列表"""
    try:
        data = load_json(trades_file)
        # 可能是 {"metrics": ..., "trades": [...]} 或直接是 [...]
        if isinstance(data, dict) and "trades" in data:
            return data["trades"]
        elif isinstance(data, list):
            return data
        else:
            return []
    except:
        return []


def get_windows_from_json(rolling_file: str) -> list:
    """从滚动窗口 JSON 文件中提取窗口结果"""
    try:
        data = load_json(rolling_file)
        # 可能是 {"windows": [...]} 或直接是 [...]
        if isinstance(data, dict) and "windows" in data:
            return data["windows"]
        elif isinstance(data, list):
            return data
        else:
            return []
    except:
        return []


def format_money(amount: float, currency: str = "USD") -> str:
    """格式化货币"""
    if amount >= 0:
        return f"+${amount:,.2f}"
    else:
        return f"-${abs(amount):,.2f}"


def format_percent(value: float) -> str:
    """格式化百分比"""
    if value >= 0:
        return f"+{value:.2f}%"
    else:
        return f"{value:.2f}%"


def format_timestamp(ts) -> str:
    """格式化时间戳为可读字符串"""
    if ts is None:
        return "N/A"
    if isinstance(ts, (int, float)):
        # 纳秒时间戳
        try:
            dt = datetime.datetime.fromtimestamp(ts / 1e9, tz=datetime.timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return str(ts)[:16]
    return str(ts)[:16]


def create_equity_curve_chart(trades: list) -> str:
    """生成权益曲线 SVG"""
    if not trades:
        return ""
    
    # 计算权益曲线
    equity = 10000  # 初始资金
    equity_curve = [equity]
    times = ["开始"]
    
    for trade in trades:
        equity += trade.get("pnl", 0)
        equity_curve.append(equity)
        times.append(format_timestamp(trade.get("exit_time")))
    
    # 找到最小值用于缩放
    min_val = min(equity_curve)
    max_val = max(equity_curve)
    range_val = max_val - min_val if max_val != min_val else 1
    
    # SVG 尺寸
    width, height = 800, 300
    padding = 40
    
    # 生成路径
    points = []
    for i, (eq, t) in enumerate(zip(equity_curve, times)):
        x = padding + (i / (len(equity_curve) - 1)) * (width - 2 * padding)
        y = height - padding - ((eq - min_val) / range_val) * (height - 2 * padding)
        points.append(f"{x:.1f},{y:.1f}")
    
    path_d = "M " + " L ".join(points)
    
    # 填充区域
    fill_path = path_d + f" L {width - padding},{height - padding} L {padding},{height - padding} Z"
    
    return f'''
    <svg viewBox="0 0 {width} {height}" class="equity-curve">
        <defs>
            <linearGradient id="equityGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:#10b981;stop-opacity:0.3"/>
                <stop offset="100%" style="stop-color:#10b981;stop-opacity:0"/>
            </linearGradient>
        </defs>
        <rect x="{padding}" y="{padding}" width="{width - 2*padding}" height="{height - 2*padding}" fill="#1f2937" rx="4"/>
        <path d="{fill_path}" fill="url(#equityGradient)"/>
        <path d="{path_d}" stroke="#10b981" stroke-width="2" fill="none"/>
        <!-- 夏普线 -->
        <line x1="{padding}" y1="{height - padding - ((0 - min_val) / range_val) * (height - 2 * padding)}" x2="{width - padding}" y2="{height - padding - ((0 - min_val) / range_val) * (height - 2 * padding)}" stroke="#6b7280" stroke-width="1" stroke-dasharray="4"/>
    </svg>
    '''


def create_trades_table(trades: list) -> str:
    """生成交易表格 HTML"""
    if not trades:
        return "<p>无交易记录</p>"
    
    rows = []
    for i, trade in enumerate(trades, 1):
        entry_time = format_timestamp(trade.get("entry_time"))
        exit_time = format_timestamp(trade.get("exit_time"))
        entry_price = f"${trade.get('entry_price', 0):,.2f}"
        exit_price = f"${trade.get('exit_price', 0):,.2f}"
        pnl = trade.get("pnl", 0)
        pnl_pct = trade.get("pnl_pct", 0)
        pnl_class = "profit" if pnl >= 0 else "loss"
        holding = trade.get("holding_minutes", 0)
        
        rows.append(f'''
        <tr>
            <td>{i}</td>
            <td>{entry_time}</td>
            <td>{exit_time}</td>
            <td>{entry_price}</td>
            <td>{exit_price}</td>
            <td class="{pnl_class}">{format_money(pnl)}</td>
            <td class="{pnl_class}">{format_percent(pnl_pct)}</td>
            <td>{holding:.0f} 分钟</td>
        </tr>
        ''')
    
    return f'''
    <table class="trades-table">
        <thead>
            <tr>
                <th>#</th>
                <th>入场时间</th>
                <th>出场时间</th>
                <th>入场价格</th>
                <th>出场价格</th>
                <th>盈亏</th>
                <th>盈亏 %</th>
                <th>持仓时间</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    '''


def create_rolling_window_table(results: list) -> str:
    """生成滚动窗口表格 HTML"""
    if not results:
        return "<p>无窗口结果</p>"
    
    rows = []
    for i, w in enumerate(results, 1):
        trades_count = w.get("trades_count", 0)
        return_pct = w.get("return_pct", 0)
        sharpe = w.get("sharpe", 0)
        max_dd = w.get("max_drawdown", 0)
        
        return_class = "profit" if return_pct >= 0 else "loss"
        sharpe_class = "profit" if sharpe >= 0 else "loss"
        
        rows.append(f'''
        <tr>
            <td>{i}</td>
            <td>{format_timestamp(w.get('start_date', 'N/A')).split()[0] if isinstance(w.get('start_date'), (int, float)) else str(w.get('start_date', 'N/A'))[:10]}</td>
            <td>{format_timestamp(w.get('end_date', 'N/A')).split()[0] if isinstance(w.get('end_date'), (int, float)) else str(w.get('end_date', 'N/A'))[:10]}</td>
            <td>{trades_count}</td>
            <td class="{return_class}">{format_percent(return_pct)}</td>
            <td class="{sharpe_class}">{sharpe:.2f}</td>
            <td>{format_percent(max_dd)}</td>
        </tr>
        ''')
    
    return f'''
    <table class="window-table">
        <thead>
            <tr>
                <th>窗口</th>
                <th>开始日期</th>
                <th>结束日期</th>
                <th>交易数</th>
                <th>收益率</th>
                <th>夏普比率</th>
                <th>最大回撤</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    '''


def generate_html_report(
    full_backtest: dict = None,
    rolling_window: dict = None,
    trades: list = None,
    window_results: list = None,
    output_path: str = "backtest_report.html"
) -> str:
    """生成 HTML 报告"""
    
    # 加载数据
    if full_backtest is None:
        try:
            full_backtest = load_json("backtest/full_backtest_results.json")
        except:
            full_backtest = {}
    
    if rolling_window is None:
        try:
            rolling_window = load_json("backtest/rolling_window_results.json")
        except:
            rolling_window = {}
    
    if trades is None:
        trades = get_trades_from_json("backtest/full_backtest_trades.json")
    
    if window_results is None:
        window_results = get_windows_from_json("backtest/rolling_window_results.json")
    
    # 计算汇总统计
    total_trades = full_backtest.get("total_trades", 0)
    winning_trades = full_backtest.get("winning_trades", 0)
    losing_trades = full_backtest.get("losing_trades", 0)
    win_rate = full_backtest.get("win_rate", 0) * 100 if full_backtest.get("win_rate") else 0
    total_pnl = full_backtest.get("total_pnl", 0)
    total_return = full_backtest.get("total_return", 0) * 100 if full_backtest.get("total_return") else 0
    sharpe = full_backtest.get("sharpe_ratio", 0)
    max_dd = full_backtest.get("max_drawdown", 0) * 100 if full_backtest.get("max_drawdown") else 0
    avg_holding = full_backtest.get("avg_holding_minutes", 0)
    
    # 滚动窗口汇总
    window_count = len(window_results)
    profitable_windows = sum(1 for w in window_results if w.get("return_pct", 0) > 0)
    avg_return = sum(w.get("return_pct", 0) for w in window_results) / window_count if window_count > 0 else 0
    avg_sharpe = sum(w.get("sharpe", 0) for w in window_results) / window_count if window_count > 0 else 0
    
    report_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = f'''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTC Snap-Back Long 回测报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e5e7eb;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            color: #10b981;
            margin-bottom: 10px;
            font-size: 2.5em;
        }}
        .subtitle {{
            text-align: center;
            color: #9ca3af;
            margin-bottom: 30px;
        }}
        .card {{
            background: #1f2937;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }}
        .card h2 {{
            color: #10b981;
            border-bottom: 2px solid #10b981;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }}
        .stat-item {{
            background: #374151;
            padding: 16px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 1.8em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #9ca3af;
            font-size: 0.9em;
        }}
        .profit {{ color: #10b981; }}
        .loss {{ color: #ef4444; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #4b5563;
        }}
        th {{
            background: #374151;
            color: #10b981;
            font-weight: 600;
        }}
        tr:hover {{ background: #374151; }}
        .equity-curve {{
            width: 100%;
            height: auto;
            margin: 20px 0;
        }}
        .summary-box {{
            background: #374151;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .summary-box h3 {{
            color: #10b981;
            margin-bottom: 12px;
        }}
        .footer {{
            text-align: center;
            color: #6b7280;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #374151;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 BTC Snap-Back Long</h1>
        <p class="subtitle">Mean Reversion Trading Strategy Backtest Report</p>
        
        <!-- 策略说明 -->
        <div class="card">
            <h2>策略说明</h2>
            <div class="summary-box">
                <h3>参数配置</h3>
                <ul>
                    <li><strong>指标:</strong> RSI(14) &lt; 20, StochK(14,3) &lt; 25</li>
                    <li><strong>趋势过滤:</strong> EMA(200) × 0.9 (价格必须在 EMA200 × 0.9 之上)</li>
                    <li><strong>止损:</strong> 2.5%</li>
                    <li><strong>止盈:</strong> 7.5%</li>
                    <li><strong>方向:</strong> 仅做多</li>
                    <li><strong>杠杆:</strong> 5x</li>
                </ul>
            </div>
        </div>
        
        <!-- 3年全程回测结果 -->
        <div class="card">
            <h2>3年全程回测 (2023-05 ~ 2024-12)</h2>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value">{total_trades}</div>
                    <div class="stat-label">总交易数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{winning_trades} / {losing_trades}</div>
                    <div class="stat-label">盈利 / 亏损</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{"{:.1f}%".format(win_rate)}</div>
                    <div class="stat-label">胜率</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value {"profit" if total_pnl >= 0 else "loss"}">{format_money(total_pnl)}</div>
                    <div class="stat-label">总盈亏</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value {"profit" if total_return >= 0 else "loss"}">{"{:.2f}%".format(total_return)}</div>
                    <div class="stat-label">总收益率</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{"{:.2f}".format(sharpe)}</div>
                    <div class="stat-label">夏普比率</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value loss">{"{:.2f}%".format(max_dd)}</div>
                    <div class="stat-label">最大回撤</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{"{:.0f}".format(avg_holding)} 分钟</div>
                    <div class="stat-label">平均持仓</div>
                </div>
            </div>
            
            <h3>权益曲线</h3>
            {create_equity_curve_chart(trades)}
        </div>
        
        <!-- 交易记录 -->
        <div class="card">
            <h2>交易记录明细</h2>
            {create_trades_table(trades)}
        </div>
        
        <!-- 滚动窗口回测 -->
        <div class="card">
            <h2>45天滚动窗口回测</h2>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value">{window_count}</div>
                    <div class="stat-label">窗口总数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{profitable_windows} / {window_count - profitable_windows}</div>
                    <div class="stat-label">盈利 / 亏损窗口</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value {"profit" if avg_return >= 0 else "loss"}">{"{:.2f}%".format(avg_return)}</div>
                    <div class="stat-label">平均收益率</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{"{:.2f}".format(avg_sharpe)}</div>
                    <div class="stat-label">平均夏普</div>
                </div>
            </div>
            
            {create_rolling_window_table(window_results)}
        </div>
        
        <div class="footer">
            <p>报告生成时间: {report_date}</p>
            <p>Powered by NautilusTrader</p>
        </div>
    </div>
</body>
</html>
    '''
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    return output_path


def main():
    """主函数"""
    print("=" * 60)
    print("BTC Snap-Back Long - HTML 报告生成器")
    print("=" * 60)
    
    # 生成报告
    output_path = "backtest/backtest_report.html"
    report_file = generate_html_report(output_path=output_path)
    
    print(f"\n✓ HTML 报告已生成: {report_file}")
    print(f"  打开浏览器访问: file:///{report_file.replace(chr(92), '/')}")


if __name__ == "__main__":
    main()