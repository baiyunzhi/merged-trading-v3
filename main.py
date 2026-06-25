"""
主入口 — 合并版本 v3
数据 → 指标 → 选品 → 回测 → 启动Dash动态盘
运行: python main.py  →  http://127.0.0.1:8050
"""
import io
import json
import logging
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("main")

import pandas as pd
from data_hub import load_for_backtest, history_to_symbol_dict, load_symbol_maps
from core.indicators import add_atr, add_basic_features
from core.event_recorder import EventRecorder
from core.engine import ReplayEngine
from core.strategy import ClaudeStrategy
from core.stats import StatsEngine
from core.selector import rank_symbols
from core.market_state import analyze


def load_settings():
    raw = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def build_pipeline(settings):
    """返回 (rank_df, state_df, data_ind, equity_curve, summary, name_map)。"""
    name_map, sector_map = load_symbol_maps()

    logger.info("Step 1/4  加载历史CSV + 计算指标...")
    df = load_for_backtest(settings)
    df = add_atr(df, period=settings.get("atr_period", 14))
    df = add_basic_features(df)
    data_ind = history_to_symbol_dict(df)
    logger.info(f"  {len(data_ind)} 个品种")

    logger.info("Step 2/4  多因子选品评分...")
    weights = settings.get("score_weights", {"trend": 0.4, "momentum": 0.35, "volatility": 0.25})
    rank_df = rank_symbols(data_ind, name_map, sector_map, weights)
    for i, row in rank_df.head(5).iterrows():
        logger.info(f"    {i}. {row['name']:6s} 评分={row['score']:.1f} 方向={row['direction']}")

    logger.info("Step 3/4  市场状态分析...")
    state_df = analyze(rank_df, data_ind)

    logger.info("Step 4/4  事件驱动回测（无前瞻偏差）...")
    recorder = EventRecorder(str(ROOT / "data" / "reports" / "events"))
    engine = ReplayEngine(ClaudeStrategy(settings), recorder, settings)
    trades, equity_curve = engine.run(df)
    summary = StatsEngine(trades, equity_curve, settings["initial_equity"]).summary()
    logger.info(f"  回测完成：{summary.get('total_trades')}笔 净利{summary.get('net_profit'):,.0f} "
                f"胜率{summary.get('win_rate'):.0%} 盈亏比{summary.get('profit_factor'):.2f}")

    return rank_df, state_df, data_ind, equity_curve, summary, name_map


def main():
    settings = load_settings()
    logger.info("=" * 56)
    logger.info("  合并版本 v3  启动中...")
    logger.info("=" * 56)
    rank_df, state_df, data_ind, equity_curve, summary, name_map = build_pipeline(settings)

    from dashboard import create_app
    app = create_app(rank_df, state_df, data_ind, equity_curve, summary, name_map)
    logger.info("")
    logger.info("  ▶  浏览器访问: http://127.0.0.1:8050")
    logger.info("  按 Ctrl+C 退出")
    app.run(debug=False, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("已停止。")
