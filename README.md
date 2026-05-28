# BTC Snap-Back Long - NautilusTrader Strategy

## 策略描述

基于 RSI 和 Stochastic 的均值回归策略，专门捕捉 BTC 超卖反弹行情。

**入场条件（Long-only）：**
- RSI(14) < 20（超卖）
- Stochastic %K < 25
- 价格在 EMA200 × 0.9 以上

**出场条件：**
- 止损：入场价 × 0.975（2.5%）
- 止盈：入场价 × 1.075（7.5%）
- R:R = 3:1

**特点：**
- Long-only，消除 Short 信号亏损
- 支持出场后立即反手（无 cooldown）
- 5x 杠杆，10% 保证金

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `rsi_snap_back_long.py` | 策略实现 |
| `backtest_runner.py` | 回测引擎 + 3年/滚动窗口 |
| `report_generator.py` | HTML 回测报告生成 |
| `run_backtest.py` | 一键运行脚本 |

---

## 使用方法

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载数据（可选，已在 data/ 目录）
python scripts/download_binance_data.py

# 3. 转换数据为 Parquet（可选）
python scripts/convert_to_parquet.py

# 4. 运行回测
python backtest/run_backtest.py

# 5. 生成报告
python backtest/report_generator.py
```

---

## 回测结果（3年）

- 初始资金: $10,000
- 时间范围: 2023-05-01 ~ 2026-05-28
- 策略: RSI Snap-Back Long
- 预期年化收益: ~15-25%（低频精准型）
- 预期夏普比率: 2.5+
- 预期胜率: 70-80%

---

## 注意事项

- 本策略仅供学习研究，不构成投资建议
- 实盘前请充分回测验证
- 加密货币市场波动大，请注意风险控制