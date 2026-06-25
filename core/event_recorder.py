
import json
from pathlib import Path

class EventRecorder:
    def __init__(self, output_dir="data/events"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.bars = []
        self.signals = []
        self.positions = []
        self.trades = []
        self.equity = []

    def record_bar(self, row):
        self.bars.append({
            "datetime": row["datetime"],
            "symbol": row["symbol"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "oi": row["oi"],
            "atr": row.get("atr"),
            "liquidity_score": row.get("liquidity_score"),
            "trend_score": row.get("trend_score"),
            "participation_score": row.get("participation_score"),
            "risk_heat": row.get("risk_heat"),
            "selection_score": row.get("selection_score"),
            "selection_rank": row.get("selection_rank"),
            "dow_trend_state": row.get("dow_trend_state"),
            "pure_dow_trend_state": row.get("pure_dow_trend_state"),
            "top_pattern": row.get("top_pattern"),
            "top_breakdown": row.get("top_breakdown"),
        })

    def record_signal(self, signal):
        self.signals.append(signal)

    def record_position(self, position):
        self.positions.append(position.__dict__)

    def record_trade(self, trade):
        self.trades.append(trade)

    def record_equity(self, snapshot):
        self.equity.append(snapshot)

    def _write_jsonl(self, name, events):
        with open(self.output_dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")

    def save_all(self):
        self._write_jsonl("bars", self.bars)
        self._write_jsonl("signals", self.signals)
        self._write_jsonl("positions", self.positions)
        self._write_jsonl("trades", self.trades)
        self._write_jsonl("equity", self.equity)
