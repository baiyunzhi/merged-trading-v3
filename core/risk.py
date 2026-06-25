"""
仓位管理器 — claude系统交易改善版

改善2: 结构止损（使用前摆动点而非固定ATR倍数）
改善3: 分批止盈（1.5R平50%，剩余跑趋势）
改善6: 分级滑点（开仓0.5tick，止损出场2tick惩罚）
改善7: 时间止损（N根K线内浮盈不足0.5R主动平仓）
"""
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Position:
    symbol: str
    direction: str
    entry_time: str
    entry_price: float
    size: int                    # 当前持有手数（分批出场后会减少）
    original_size: int           # 原始开仓手数
    atr: float
    stop_loss: float
    structure_stop: Optional[float]  # 改善2：结构止损价
    best_price: float
    score: float
    risk_multiplier: float
    reason_entry: dict
    entry_commission: float
    contract_multiplier: int
    bars_held: int = 0           # 改善7：持仓K线数
    partial_exited: bool = False # 改善3：是否已触发分批平仓


class PositionManager:
    def __init__(self, settings, account):
        self.settings = settings
        self.account = account
        self.open_positions: dict[str, Position] = {}
        self.trades = []

    # ── 容量检查 ──────────────────────────────────────────────────────────────

    def can_open(self, symbol=None):
        if symbol is not None and symbol in self.open_positions:
            return False
        return len(self.open_positions) < int(self.settings.get("max_open_positions", 6))

    # ── 风险 / 保证金查询 ─────────────────────────────────────────────────────

    def current_open_risk(self):
        total = 0.0
        for p in self.open_positions.values():
            if p.direction == "short":
                dist = max(0.0, p.stop_loss - p.entry_price)
            else:
                dist = max(0.0, p.entry_price - p.stop_loss)
            total += dist * p.size * p.contract_multiplier
        return total

    def current_occupied_margin(self):
        margin_rate = self.settings.get("margin_rate", 0.12)
        return sum(
            p.entry_price * p.contract_multiplier * margin_rate * p.size
            for p in self.open_positions.values()
        )

    # ── 板块持仓查询（改善5 由 replay_engine 调用）────────────────────────────

    def sector_exposure(self, sector_map: dict) -> dict:
        """返回 {sector: {"long": n, "short": n}} 统计。"""
        result = {}
        for symbol, p in self.open_positions.items():
            sector = sector_map.get(symbol, "unknown")
            if sector not in result:
                result[sector] = {"long": 0, "short": 0}
            result[sector][p.direction] += 1
        return result

    # ── 开仓 ──────────────────────────────────────────────────────────────────

    def open_position(self, row, signal, size):
        if signal.get("direction") == "short":
            return self._open(row, signal, size, "short")
        return self._open(row, signal, size, "long")

    def _open(self, row, signal, size, direction):
        symbol = row["symbol"]
        if size <= 0 or not self.can_open(symbol):
            return None

        mult = self._get_multiplier(row)
        # 改善6：开仓用普通滑点
        entry_slip = float(self.settings.get("entry_slippage_ticks", 0.5))
        atr = float(signal["atr"])
        reason = signal.get("reason", {})

        if direction == "long":
            entry = float(row["open"]) + entry_slip
            atr_stop = entry - atr * self.settings["atr_stop_mult"]
            # 改善2：取结构止损与ATR止损中更紧的那个（结构止损优先）
            structure_stop = reason.get("structure_stop_loss")
            stop_loss = float(structure_stop) if structure_stop else atr_stop
            stop_loss = min(stop_loss, atr_stop)  # 不允许比ATR止损更宽
        else:
            entry = float(row["open"]) - entry_slip
            atr_stop = entry + atr * self.settings["atr_stop_mult"]
            structure_stop = reason.get("structure_stop_loss")
            stop_loss = float(structure_stop) if structure_stop else atr_stop
            stop_loss = max(stop_loss, atr_stop)

        entry_commission = self._commission(size, mult)
        self.account.charge_commission(entry_commission)

        pos = Position(
            symbol=symbol,
            direction=direction,
            entry_time=row["datetime"],
            entry_price=entry,
            size=size,
            original_size=size,
            atr=atr,
            stop_loss=stop_loss,
            structure_stop=float(structure_stop) if structure_stop else None,
            best_price=entry,
            score=signal.get("score", 0),
            risk_multiplier=float(signal.get("risk_multiplier", 1.0)),
            reason_entry=reason,
            entry_commission=entry_commission,
            contract_multiplier=mult,
        )
        self.open_positions[symbol] = pos
        return pos

    # ── 每根K线更新（盘中止损/追踪/分批/时间） ─────────────────────────────

    def update(self, row):
        symbol = row["symbol"]
        if symbol not in self.open_positions:
            return []

        p = self.open_positions[symbol]
        p.bars_held += 1
        closed_trades = []

        bar_open = float(row["open"])
        bar_low = float(row["low"])
        bar_high = float(row["high"])
        bar_close = float(row["close"])
        risk_distance = p.atr * self.settings["atr_stop_mult"]

        # ── 改善6：止损出场用惩罚滑点 ──
        stop_slip = float(self.settings.get("stop_slippage_ticks", 2.0))

        # ── 止损触发 ──
        if p.direction == "long" and bar_low <= p.stop_loss:
            actual_stop = min(p.stop_loss, bar_open)
            exit_price = actual_stop - stop_slip
            closed_trades.append(self._close(row, exit_price, "stop_loss", p.size))
            return closed_trades

        if p.direction == "short" and bar_high >= p.stop_loss:
            actual_stop = max(p.stop_loss, bar_open)
            exit_price = actual_stop + stop_slip
            closed_trades.append(self._close(row, exit_price, "stop_loss", p.size))
            return closed_trades

        # ── 改善3：分批止盈（1.5R平50%，仅触发一次） ──
        partial_r = float(self.settings.get("partial_exit_r", 1.5))
        partial_ratio = float(self.settings.get("partial_exit_ratio", 0.5))
        if not p.partial_exited and p.original_size > 1:
            if p.direction == "long":
                profit_r = (bar_high - p.entry_price) / max(risk_distance, 1e-9)
                if profit_r >= partial_r:
                    partial_size = max(1, int(p.original_size * partial_ratio))
                    if partial_size < p.size:
                        ep = min(bar_high, bar_open) - float(self.settings.get("entry_slippage_ticks", 0.5))
                        closed_trades.append(self._close(row, ep, "partial_exit_1R5", partial_size))
                        p.partial_exited = True
            else:
                profit_r = (p.entry_price - bar_low) / max(risk_distance, 1e-9)
                if profit_r >= partial_r:
                    partial_size = max(1, int(p.original_size * partial_ratio))
                    if partial_size < p.size:
                        ep = max(bar_low, bar_open) + float(self.settings.get("entry_slippage_ticks", 0.5))
                        closed_trades.append(self._close(row, ep, "partial_exit_1R5", partial_size))
                        p.partial_exited = True

        # ── 改善7：时间止损 ──
        time_stop_bars = int(self.settings.get("time_stop_bars", 20))
        time_stop_min_r = float(self.settings.get("time_stop_min_r", 0.5))
        if p.bars_held >= time_stop_bars and symbol in self.open_positions:
            if p.direction == "long":
                current_r = (bar_close - p.entry_price) / max(risk_distance, 1e-9)
            else:
                current_r = (p.entry_price - bar_close) / max(risk_distance, 1e-9)
            if current_r < time_stop_min_r:
                exit_price = bar_close - float(self.settings.get("entry_slippage_ticks", 0.5)) if p.direction == "long" else bar_close + float(self.settings.get("entry_slippage_ticks", 0.5))
                if symbol in self.open_positions:
                    closed_trades.append(self._close(row, exit_price, "time_stop", p.size))
                    return closed_trades

        # ── 追踪止损更新 ──
        if symbol in self.open_positions:
            self._update_trailing(row)

        return closed_trades

    def _update_trailing(self, row):
        p = self.open_positions.get(row["symbol"])
        if p is None:
            return
        risk_distance = p.atr * self.settings["atr_stop_mult"]
        bar_close = float(row["close"])

        if p.direction == "long":
            p.best_price = max(p.best_price, float(row["high"]))
            if p.best_price - p.entry_price >= risk_distance * self.settings.get("breakeven_r", 1.0):
                p.stop_loss = max(p.stop_loss, p.entry_price)
            if p.best_price - p.entry_price >= risk_distance * self.settings.get("trailing_start_r", 2.0):
                trail = bar_close - p.atr * self.settings.get("trailing_atr_mult", 2.0)
                p.stop_loss = max(p.stop_loss, trail)
        else:
            p.best_price = min(p.best_price, float(row["low"]))
            if p.entry_price - p.best_price >= risk_distance * self.settings.get("breakeven_r", 1.0):
                p.stop_loss = min(p.stop_loss, p.entry_price)
            if p.entry_price - p.best_price >= risk_distance * self.settings.get("trailing_start_r", 2.0):
                trail = bar_close + p.atr * self.settings.get("trailing_atr_mult", 2.0)
                p.stop_loss = min(p.stop_loss, trail)

    # ── 开盘平仓（道氏结构信号） ──────────────────────────────────────────────

    def close_at_open(self, row, exit_reason):
        symbol = row["symbol"]
        if symbol not in self.open_positions:
            return []
        p = self.open_positions[symbol]
        slip = float(self.settings.get("entry_slippage_ticks", 0.5))
        exit_price = float(row["open"]) - slip if p.direction == "long" else float(row["open"]) + slip
        return [self._close(row, exit_price, exit_reason, p.size)]

    def close_signal_for_next_open(self, row):
        symbol = row["symbol"]
        if symbol not in self.open_positions:
            return None
        p = self.open_positions[symbol]
        close = float(row["close"])
        pure_state = row.get("pure_dow_trend_state")
        dow_state = row.get("dow_trend_state")

        if p.direction == "long" and p.structure_stop is not None and close < p.structure_stop:
            return "structure_stop_break"
        if p.direction == "short" and p.structure_stop is not None and close > p.structure_stop:
            return "structure_stop_break"
        if p.direction == "long" and pure_state in ("BEAR_TREND", "EXPANDING_RANGE"):
            return "dow_trend_reversal"
        if p.direction == "short" and pure_state in ("BULL_TREND", "EXPANDING_RANGE"):
            return "dow_trend_reversal"
        if p.direction == "long" and dow_state in ("BEAR_WARNING", "BEAR_CONFIRMED"):
            return "dow_state_exit"
        return None

    # ── 强平 / 未平仓盈亏 ─────────────────────────────────────────────────────

    def force_close(self, row):
        symbol = row["symbol"]
        if symbol not in self.open_positions:
            return []
        p = self.open_positions[symbol]
        slip = float(self.settings.get("entry_slippage_ticks", 0.5))
        ep = float(row["close"]) - slip if p.direction == "long" else float(row["close"]) + slip
        return [self._close(row, ep, "force_close_on_end", p.size)]

    def unrealized_pnl(self, marks):
        total = 0.0
        for symbol, p in self.open_positions.items():
            if symbol not in marks:
                continue
            mark = float(marks[symbol])
            mult = p.contract_multiplier
            if p.direction == "short":
                total += (p.entry_price - mark) * p.size * mult
            else:
                total += (mark - p.entry_price) * p.size * mult
        return total

    def snapshot(self):
        return {s: asdict(p) for s, p in self.open_positions.items()}

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    def _close(self, row, exit_price, exit_reason, size):
        symbol = row["symbol"]
        p = self.open_positions.get(symbol)
        if p is None:
            return None
        mult = p.contract_multiplier
        is_full = (size >= p.size)

        if p.direction == "short":
            pnl_gross = (p.entry_price - exit_price) * size * mult
            pnl_pct = (p.entry_price - exit_price) / p.entry_price
        else:
            pnl_gross = (exit_price - p.entry_price) * size * mult
            pnl_pct = (exit_price - p.entry_price) / p.entry_price

        exit_commission = self._commission(size, mult)
        self.account.realize_trade_pnl(pnl_gross, exit_commission)
        entry_commission_share = p.entry_commission * (size / max(p.original_size, 1))
        pnl_net = pnl_gross - entry_commission_share - exit_commission

        trade = {
            "symbol": p.symbol,
            "direction": p.direction,
            "entry_time": p.entry_time,
            "exit_time": row["datetime"],
            "entry_price": round(p.entry_price, 4),
            "exit_price": round(exit_price, 4),
            "size": size,
            "original_size": p.original_size,
            "contract_multiplier": mult,
            "score": p.score,
            "pnl": round(pnl_net, 2),
            "pnl_pct": round(pnl_pct, 6),
            "bars_held": p.bars_held,
            "reason_exit": exit_reason,
            "reason_entry": p.reason_entry,
            "partial_exit": not is_full,
        }
        self.trades.append(trade)

        if is_full:
            self.open_positions.pop(symbol, None)
        else:
            p.size -= size

        return trade

    def _get_multiplier(self, row):
        val = row.get("contract_multiplier")
        try:
            v = int(float(val))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
        return int(self.settings.get("contract_multiplier", 10))

    def _commission(self, size, multiplier=None):
        per_contract = float(self.settings.get("commission_per_contract", 3.0))
        return per_contract * size
