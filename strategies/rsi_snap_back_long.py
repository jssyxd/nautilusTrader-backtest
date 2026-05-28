# -*- coding: utf-8 -*-
"""
BTC Snap-Back Long Strategy for NautilusTrader

基于 RSI 和 Stochastic 的均值回归策略
- Long-only（不做空）
- 入场: RSI < 20, Stochastic %K < 25, close > EMA200 * 0.9
- 出场: SL=2.5%, TP=7.5%（3:1 R:R）
- 允许出场后立即反手

作者: 基于 PineScript V2 版本适配
"""

# -------------------------------------------------------------------------------------------------
# Copyright (C) 2024-2026 Nautech Systems Pty Ltd. All rights reserved.
# https://nautechsystems.io
#
# Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# -------------------------------------------------------------------------------------------------

from decimal import Decimal
from typing import Optional

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import PositiveFloat
from nautilus_trader.config import PositiveInt
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.indicators import RelativeStrengthIndex
from nautilus_trader.indicators import Stochastics
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.orders import StopMarketOrder
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.trading.strategy import Strategy


class RSISnapBackLongConfig(StrategyConfig, frozen=True):
    """
    BTC Snap-Back Long 策略配置

    Parameters
    ----------
    instrument_id : InstrumentId
        交易标的 ID
    bar_type : BarType
        K 线类型
    trade_size : Decimal
        每次交易数量（按保证金比例）
    ema_period : int, default 200
        EMA 周期
    rsi_period : int, default 14
        RSI 周期
    rsi_buy_threshold : float, default 20.0
        RSI 超卖阈值（0-100）
    stoch_period_k : int, default 14
        Stochastic %K 周期
    stoch_period_d : int, default 3
        Stochastic %D 周期
    stoch_buy_threshold : float, default 25.0
        Stochastic 超卖阈值（0-100）
    stop_loss_pct : float, default 0.025
        止损百分比（2.5%）
    take_profit_pct : float, default 0.075
        止盈百分比（7.5%）
    ema_filter_ratio : float, default 0.9
        EMA 过滤比例（价格 > EMA * ratio）
    """

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    ema_period: PositiveInt = 200
    rsi_period: PositiveInt = 14
    rsi_buy_threshold: PositiveFloat = 20.0  # RSI < 20 入场
    stoch_period_k: PositiveInt = 14
    stoch_period_d: PositiveInt = 3
    stoch_buy_threshold: PositiveFloat = 25.0  # Stoch K < 25 入场
    stop_loss_pct: PositiveFloat = 0.025  # 2.5% 止损
    take_profit_pct: PositiveFloat = 0.075  # 7.5% 止盈
    ema_filter_ratio: PositiveFloat = 0.9  # 价格 > EMA * 0.9


class RSISnapBackLong(Strategy):
    """
    BTC Snap-Back Long 策略

    专门捕捉 BTC 超卖反弹行情的均值回归策略。
    - Long-only，避免 Short 信号亏损
    - 入场: RSI < 20 AND StochK < 25 AND close > EMA * 0.9
    - 出场: SL = 2.5%, TP = 7.5%（3:1 R:R）
    - 出场后允许立即反手

    Parameters
    ----------
    config : RSISnapBackLongConfig
        策略配置
    """

    def __init__(self, config: RSISnapBackLongConfig) -> None:
        super().__init__(config)

        # 交易标的
        self.instrument: Optional[Instrument] = None

        # 指标
        self.ema = ExponentialMovingAverage(config.ema_period)
        self.rsi = RelativeStrengthIndex(config.rsi_period)
        self.stoch = Stochastics(config.stoch_period_k, config.stoch_period_d)

        # 状态跟踪
        self.entry_price: Optional[float] = None
        self.stop_loss_price: Optional[float] = None
        self.take_profit_price: Optional[float] = None
        self.position_opened_at: Optional[int] = None  # ns timestamp

        # 交易记录（用于报告生成）
        self.trade_log: list[dict] = []

        # 上一个 position_size（用于检测仓位变化）
        self._prev_position_size: int = 0

    def on_start(self) -> None:
        """策略启动时调用"""
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"Could not find instrument for {self.config.instrument_id}")
            self.stop()
            return

        # 注册指标
        self.register_indicator_for_bars(self.config.bar_type, self.ema)
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
        self.register_indicator_for_bars(self.config.bar_type, self.stoch)

        # 订阅 K 线数据
        self.subscribe_bars(self.config.bar_type)

        self.log.info(f"RSISnapBackLong started on {self.config.bar_type}", LogColor.GREEN)
        self.log.info(
            f"Params: RSI<{self.config.rsi_buy_threshold}, "
            f"StochK<{self.config.stoch_buy_threshold}, "
            f"EMA>{self.config.ema_filter_ratio}, "
            f"SL={self.config.stop_loss_pct*100}%, "
            f"TP={self.config.take_profit_pct*100}%",
            LogColor.CYAN,
        )

    def on_bar(self, bar: Bar) -> None:
        """每根 K 线结束时调用"""
        # 检查指标是否初始化完成
        if not self.indicators_initialized():
            self.log.debug(
                f"Waiting for indicators warm-up [{self.cache.bar_count(self.config.bar_type)}]",
                color=LogColor.BLUE,
            )
            return

        # 过滤单腿 K 线
        if bar.is_single_price():
            return

        # 获取当前持仓状态
        pos_size = self.portfolio.net_position(self.config.instrument_id)
        is_long = pos_size > 0
        is_flat = pos_size == 0

        # 检测仓位变化（入场或出场）
        if self._prev_position_size == 0 and pos_size > 0:
            # 刚入场 - 记录入场价格
            self.entry_price = bar.close.as_double()
            self.position_opened_at = bar.ts_event
            self.log.info(
                f"Position opened: {self.entry_price}, RSI={self.rsi.value:.1f}, "
                f"StochK={self.stoch.value_k:.1f}, EMA={self.ema.value:.2f}",
                LogColor.YELLOW,
            )

        elif self._prev_position_size > 0 and pos_size == 0:
            # 刚出场 - 记录交易
            exit_price = bar.close.as_double()
            pnl = exit_price - self.entry_price if self.entry_price else 0
            pnl_pct = (pnl / self.entry_price * 100) if self.entry_price else 0
            holding_ns = bar.ts_event - self.position_opened_at if self.position_opened_at else 0
            holding_minutes = holding_ns / 60_000_000_000 if holding_ns else 0

            self.trade_log.append({
                "entry_time": self.position_opened_at,
                "exit_time": bar.ts_event,
                "entry_price": self.entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "holding_minutes": holding_minutes,
                "rsi_entry": self._entry_rsi,
                "stoch_entry": self._entry_stoch,
                "ema_entry": self._entry_ema,
                "reason": self._exit_reason,
            })

            self.log.info(
                f"Position closed: PnL={pnl_pct:.2f}%, Holding={holding_minutes:.1f}min, "
                f"Reason={self._exit_reason}",
                LogColor.GREEN if pnl > 0 else LogColor.RED,
            )

            # 重置状态
            self.entry_price = None
            self.stop_loss_price = None
            self.take_profit_price = None
            self.position_opened_at = None
            self._entry_rsi = None
            self._entry_stoch = None
            self._entry_ema = None
            self._exit_reason = "UNKNOWN"

        # 更新前一持仓状态
        self._prev_position_size = pos_size

        # 入场逻辑（仅在无持仓时检查）
        if is_flat:
            self._check_entry(bar)

        # 出场逻辑（在持仓时检查 - 动态跟踪 SL/TP）
        if is_long and self.entry_price:
            self._check_exit(bar)

    def _check_entry(self, bar: Bar) -> None:
        """检查入场信号"""
        close = bar.close.as_double()

        # 入场条件
        rsi_oversold = self.rsi.value < self.config.rsi_buy_threshold
        stoch_oversold = self.stoch.value_k < self.config.stoch_buy_threshold
        above_ema_filter = close > self.ema.value * self.config.ema_filter_ratio

        if rsi_oversold and stoch_oversold and above_ema_filter:
            # 记录入场时的指标值
            self._entry_rsi = self.rsi.value
            self._entry_stoch = self.stoch.value_k
            self._entry_ema = self.ema.value

            # 入场
            self._open_long(bar)

    def _open_long(self, bar: Bar) -> None:
        """开多单"""
        # 计算 SL/TP 价格
        entry_price = bar.close.as_double()
        self.entry_price = entry_price
        self.stop_loss_price = entry_price * (1 - self.config.stop_loss_pct)
        self.take_profit_price = entry_price * (1 + self.config.take_profit_pct)
        self._exit_reason = "UNKNOWN"

        # 市价入场
        order: MarketOrder = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.instrument.make_qty(self.config.trade_size),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

        # 提交止损单
        sl_order: StopMarketOrder = self.order_factory.stop_market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.instrument.make_qty(self.config.trade_size),
            trigger_price=self.instrument.make_price(self.stop_loss_price),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(sl_order)

        # 提交止盈单
        tp_order: LimitOrder = self.order_factory.limit(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.instrument.make_qty(self.config.trade_size),
            price=self.instrument.make_price(self.take_profit_price),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(tp_order)

        self.log.info(
            f"Entry: LONG @ {entry_price:.2f}, SL={self.stop_loss_price:.2f}, "
            f"TP={self.take_profit_price:.2f}",
            LogColor.YELLOW,
        )

    def _check_exit(self, bar: Bar) -> None:
        """检查是否需要动态调整出场（主要用于记录 exit_reason）"""
        close = bar.close.as_double()

        # 检查是否触发了 SL 或 TP
        if self.stop_loss_price and close <= self.stop_loss_price:
            self._exit_reason = "STOP_LOSS"
        elif self.take_profit_price and close >= self.take_profit_price:
            self._exit_reason = "TAKE_PROFIT"

    def on_event(self, event: Event) -> None:
        """订单事件处理"""
        # 可以在这里处理订单成交事件
        pass

    def on_data(self, data: Data) -> None:
        """自定义数据处理"""
        pass

    def on_stop(self) -> None:
        """策略停止时调用"""
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)
        self.unsubscribe_bars(self.config.bar_type)
        self.log.info(f"RSISnapBackLong stopped. Total trades: {len(self.trade_log)}", LogColor.GREEN)

    def on_reset(self) -> None:
        """策略重置时调用"""
        self.ema.reset()
        self.rsi.reset()
        self.stoch.reset()
        self.entry_price = None
        self.stop_loss_price = None
        self.take_profit_price = None
        self.position_opened_at = None
        self.trade_log = []
        self._prev_position_size = 0
        self._entry_rsi = None
        self._entry_stoch = None
        self._entry_ema = None
        self._exit_reason = "UNKNOWN"

    def on_save(self) -> dict[str, bytes]:
        """保存策略状态"""
        return {}

    def on_load(self, state: dict[str, bytes]) -> None:
        """加载策略状态"""
        pass

    def on_dispose(self) -> None:
        """策略释放时调用"""
        pass

    def get_trade_log(self) -> list[dict]:
        """获取交易记录"""
        return self.trade_log.copy()

    def get_performance_metrics(self) -> dict:
        """计算性能指标"""
        if not self.trade_log:
            return {}

        trades = self.trade_log
        total_trades = len(trades)
        winning_trades = [t for t in trades if t["pnl"] > 0]
        losing_trades = [t for t in trades if t["pnl"] <= 0]

        total_pnl = sum(t["pnl"] for t in trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0

        avg_win = sum(t["pnl"] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = abs(sum(t["pnl"] for t in losing_trades) / len(losing_trades)) if losing_trades else 0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")

        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
        }