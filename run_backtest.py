"""
纯CLI回测入口 — 合并版本 v3
运行: python run_backtest.py
始终用历史CSV（严谨、无前瞻偏差、可复现）。
"""
import io
import json
import sys
from pathlib import Path

# Windows 终端 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from data_hub import load_for_backtest
from core.indicators import add_atr, add_basic_features
from core.event_recorder import EventRecorder
from core.engine import ReplayEngine
from core.strategy import ClaudeStrategy
from core.stats import StatsEngine


def load_settings() -> dict:
    raw = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def run():
    settings = load_settings()
    df = load_for_backtest(settings)
    df = add_atr(df, period=settings.get("atr_period", 14))
    df = add_basic_features(df)

    out_dir = ROOT / "data" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    recorder = EventRecorder(str(out_dir / "events"))
    strategy = ClaudeStrategy(settings)
    engine = ReplayEngine(strategy, recorder, settings)

    print("[合并版v3] 开始回测（历史CSV，事件驱动，下一根开盘成交）...")
    trades, equity_curve = engine.run(df)

    stats = StatsEngine(trades, equity_curve, settings["initial_equity"])
    s = stats.summary()

    print("\n" + "=" * 52)
    print("  合并版本 v3 — 回测结果")
    print("=" * 52)
    print(f"  总交易次数:   {s.get('total_trades', 0)}")
    print(f"  净利润:       {s.get('net_profit', 0):,.2f}")
    print(f"  胜率:         {s.get('win_rate', 0):.1%}")
    print(f"  盈亏比:       {s.get('profit_factor', 0):.2f}")
    print(f"  最大回撤:     {s.get('max_drawdown', 0):,.2f} ({s.get('max_drawdown_pct', 0):.1%})")
    print(f"  单笔期望:     {s.get('expectancy', 0):,.2f}")
    print(f"  最终权益:     {s.get('final_equity', 0):,.2f}")
    print("=" * 52)

    pd.DataFrame(trades).to_csv(out_dir / "trades.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(equity_curve).to_csv(out_dir / "equity_curve.csv", index=False, encoding="utf-8-sig")
    print(f"\n[输出] {out_dir/'trades.csv'}")
    return trades, equity_curve, s


if __name__ == "__main__":
    run()
