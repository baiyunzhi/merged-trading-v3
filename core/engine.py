"""
ReplayEngine — claude系统交易

改善5: 板块风险检查（同板块同向仓位≤max_sector_same_direction，板块总风险≤max_sector_risk_pct）
"""
import json
from pathlib import Path

from core.account import Account
from core.risk import PositionManager
from core.sizer import PositionSizer


def _load_sector_map() -> dict:
    pool_path = Path(__file__).resolve().parents[1] / "config" / "china_commodity_pool.json"
    if pool_path.exists():
        data = json.loads(pool_path.read_text(encoding="utf-8"))
        return {item["symbol"]: item.get("sector", "other") for item in data.get("symbols", [])}
    return {}


class ReplayEngine:
    def __init__(self, strategy, recorder, settings):
        self.strategy = strategy
        self.recorder = recorder
        self.settings = settings
        self.account = Account(settings["initial_equity"])
        self.position_manager = PositionManager(settings, self.account)
        self.sizer = PositionSizer(settings)
        self.sector_map = _load_sector_map()

        # 改善5参数
        self._max_sector_same = int(settings.get("max_sector_same_direction", 2))
        self._max_sector_risk = float(settings.get("max_sector_risk_pct", 0.03))

    def run(self, df):
        all_trades = []
        pending_signals = {}
        pending_exit_reasons = {}
        marks = {}
        latest_rows = {}
        last_equity_date = None

        for _, row in df.iterrows():
            row = row.to_dict()
            symbol = row["symbol"]
            marks[symbol] = row["close"]
            latest_rows[symbol] = row
            self.recorder.record_bar(row)

            exited_at_open = False
            pending_exit_reason = pending_exit_reasons.pop(symbol, None)
            if pending_exit_reason:
                closed = self.position_manager.close_at_open(row, pending_exit_reason)
                for trade in closed:
                    if trade:
                        self.recorder.record_trade(trade)
                        all_trades.append(trade)
                exited_at_open = bool(closed)

            pending_signal = pending_signals.pop(symbol, None)
            if (
                pending_signal
                and pending_signal["direction"] in ("long", "short")
                and self.position_manager.can_open(symbol)
                and not exited_at_open
            ):
                unrealized = self.position_manager.unrealized_pnl(marks)
                equity = self.account.equity(unrealized)

                # 改善5：板块风险检查
                if not self._sector_allows(symbol, pending_signal["direction"], equity):
                    pass  # 板块限额已满，跳过此信号
                else:
                    portfolio_risk_budget = equity * self.settings.get("max_portfolio_risk_pct", 0.02)
                    remaining_risk = max(0.0, portfolio_risk_budget - self.position_manager.current_open_risk())
                    occupied_margin = self.position_manager.current_occupied_margin()
                    available_margin = max(0.0, equity - occupied_margin)
                    contract_multiplier = self._get_multiplier(row)

                    size = self.sizer.size_by_atr(
                        pending_signal["atr"],
                        self.settings["atr_stop_mult"],
                        equity,
                        float(row["open"]),
                        pending_signal.get("risk_multiplier", 1.0),
                        remaining_risk,
                        available_margin=available_margin,
                        contract_multiplier=contract_multiplier,
                    )
                    if size > 0:
                        pos = self.position_manager.open_position(row, pending_signal, size)
                        if pos:
                            self.recorder.record_position(pos)

            closed = self.position_manager.update(row)
            for trade in closed:
                if trade:
                    self.recorder.record_trade(trade)
                    all_trades.append(trade)

            signal = self.strategy.generate_signal(row)
            signal["atr"] = row.get("atr", 0)
            self.recorder.record_signal(signal)
            pending_signals[symbol] = signal
            pending_exit_reason = self.position_manager.close_signal_for_next_open(row)
            if pending_exit_reason:
                pending_exit_reasons[symbol] = pending_exit_reason

            current_date = str(row["datetime"])[:10]
            if current_date != last_equity_date:
                last_equity_date = current_date
                self._record_equity(row, marks)

        if self.settings.get("force_close_on_end", True) and len(df) > 0:
            for sym, last_row in latest_rows.items():
                for trade in self.position_manager.force_close(last_row):
                    if trade:
                        self.recorder.record_trade(trade)
                        all_trades.append(trade)
            self._record_equity(df.iloc[-1].to_dict(), marks)

        self.recorder.save_all()
        return all_trades, self.recorder.equity

    # ── 改善5：板块限制检查 ──────────────────────────────────────────────────

    def _sector_allows(self, symbol: str, direction: str, equity: float) -> bool:
        sector = self.sector_map.get(symbol, "unknown")
        exposure = self.position_manager.sector_exposure(self.sector_map)
        sect = exposure.get(sector, {"long": 0, "short": 0})

        # 同板块同向数量限制
        if sect[direction] >= self._max_sector_same:
            return False

        # 板块总风险限制
        sector_risk = sum(
            self._position_risk(p)
            for sym, p in self.position_manager.open_positions.items()
            if self.sector_map.get(sym, "unknown") == sector
        )
        if equity > 0 and sector_risk / equity >= self._max_sector_risk:
            return False

        return True

    def _position_risk(self, p) -> float:
        if p.direction == "short":
            dist = max(0.0, p.stop_loss - p.entry_price)
        else:
            dist = max(0.0, p.entry_price - p.stop_loss)
        return dist * p.size * p.contract_multiplier

    def _get_multiplier(self, row) -> int:
        val = row.get("contract_multiplier")
        try:
            v = int(float(val))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
        return int(self.settings.get("contract_multiplier", 10))

    def _record_equity(self, row, marks):
        unrealized = self.position_manager.unrealized_pnl(marks)
        self.recorder.record_equity({
            "datetime": str(row["datetime"])[:10],
            "symbol": row["symbol"],
            "realized_pnl": round(self.account.realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "commission_paid": round(self.account.commission_paid, 2),
            "equity": round(self.account.equity(unrealized), 2),
            "open_risk": round(self.position_manager.current_open_risk(), 2),
            "occupied_margin": round(self.position_manager.current_occupied_margin(), 2),
            "position": self.position_manager.snapshot(),
        })
