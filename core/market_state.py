"""
市场状态分析（综合选品评分 + 道氏状态 → 操作建议）
融合：搭建系的5级状态分类 + claude系的道氏结构判断
"""
import pandas as pd


def analyze(rank_df: pd.DataFrame, data_ind: dict) -> pd.DataFrame:
    """返回市场状态表：品种/状态/评分/方向/入场/止损/止盈。"""
    rows = []
    for _, r in rank_df.iterrows():
        sym = r["symbol"]
        df = data_ind.get(sym)
        if df is None or df.empty:
            continue
        last = df.dropna(subset=["MA20", "ATR"]).iloc[-1] if not df.dropna(subset=["MA20", "ATR"]).empty else df.iloc[-1]
        score = r["score"]
        direction = r["direction"]
        close = float(last.get("close", 0))
        atr = float(last.get("ATR", 0)) or float(last.get("atr", 0))
        dow = last.get("dow_trend_state", "NEUTRAL")

        # 5级状态（搭建系阈值 + 道氏增强）
        if score >= 65 and direction == "多" and dow in ("BULL_CONFIRMED", "BULL_PULLBACK"):
            state, sl_sign, tp_sign = "🟢 趋势做多", -1, 1
        elif score >= 65 and direction == "空" and dow in ("BEAR_CONFIRMED", "BEAR_PULLBACK"):
            state, sl_sign, tp_sign = "🔴 趋势做空", 1, -1
        elif 45 <= score < 65 and direction == "多":
            state, sl_sign, tp_sign = "🟡 轻仓做多", -1, 1
        elif 45 <= score < 65 and direction == "空":
            state, sl_sign, tp_sign = "🟡 轻仓做空", 1, -1
        else:
            state, sl_sign, tp_sign = "⚪ 观望", -1, 1

        rows.append({
            "品种": r["name"],
            "板块": r.get("sector", ""),
            "市场状态": state,
            "评分": score,
            "方向": direction,
            "现价": round(close, 1),
            "入场": round(close, 1),
            "止损": round(close + sl_sign * 2 * atr, 1),
            "止盈": round(close + tp_sign * 3 * atr, 1),
            "ADX": round(float(last.get("ADX", 0) or 0), 1),
            "RSI": round(float(last.get("RSI", 50) or 50), 1),
        })
    return pd.DataFrame(rows)
