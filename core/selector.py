"""
多因子选品（移植自 交易系统搭建/variety_selector.py）

综合评分 = 趋势40% + 动量35% + 波动25%
适配合并版：指标已由 core/indicators.add_basic_features 预计算，直接取最新行评分。
"""
import numpy as np
import pandas as pd


def _trend_score(row, df) -> float:
    score = 0.0
    ma5, ma10, ma20, ma60 = row.get("MA5"), row.get("MA10"), row.get("MA20"), row.get("MA60")
    if all(pd.notna([ma5, ma10, ma20, ma60])):
        if ma5 > ma10:  score += 10
        if ma10 > ma20: score += 15
        if ma20 > ma60: score += 15
    adx = row.get("ADX", np.nan)
    if pd.notna(adx):
        score += min(40, adx)
    return min(100, score)


def _momentum_score(row, df) -> float:
    score = 50.0
    if len(df) >= 20:
        ret5 = (df["close"].iloc[-1] / df["close"].iloc[-5] - 1) * 100
        ret20 = (df["close"].iloc[-1] / df["close"].iloc[-20] - 1) * 100
        score += np.clip(ret5 * 3, -20, 20)
        score += np.clip(ret20 * 1.5, -20, 20)
    rsi = row.get("RSI", np.nan)
    if pd.notna(rsi):
        if 40 <= rsi <= 65:
            score += 10
        elif rsi < 30 or rsi > 75:
            score -= 10
    return float(np.clip(score, 0, 100))


def _volatility_score(row, df) -> float:
    atr = row.get("ATR", np.nan)
    close = row.get("close", np.nan)
    if pd.isna(atr) or pd.isna(close) or close == 0:
        return 50.0
    atr_pct = atr / close * 100
    if 0.8 <= atr_pct <= 2.5:
        score = 100 - abs(atr_pct - 1.6) * 20
    elif atr_pct < 0.8:
        score = atr_pct / 0.8 * 60
    else:
        score = max(0, 100 - (atr_pct - 2.5) * 25)
    vol = row.get("volume", np.nan)
    volma5 = row.get("VOL_MA5", np.nan)
    if pd.notna(vol) and pd.notna(volma5) and volma5 > 0 and vol / volma5 > 1.2:
        score = min(100, score + 10)
    return float(np.clip(score, 0, 100))


def score_symbol(symbol, df_ind, name_map, sector_map, weights) -> dict:
    """对单品种（已含指标的DataFrame）打综合分。"""
    valid = df_ind.dropna(subset=["MA20", "RSI", "ATR"])
    if valid.empty:
        return None
    row = valid.iloc[-1]
    ts = _trend_score(row, df_ind)
    ms = _momentum_score(row, df_ind)
    vs = _volatility_score(row, df_ind)
    total = ts * weights["trend"] + ms * weights["momentum"] + vs * weights["volatility"]
    direction = "多" if row.get("MA5", 0) > row.get("MA20", 0) else "空"
    return {
        "symbol": symbol,
        "name": name_map.get(symbol, symbol),
        "sector": sector_map.get(symbol, ""),
        "score": round(total, 1),
        "trend_score": round(ts, 1),
        "mom_score": round(ms, 1),
        "vol_score": round(vs, 1),
        "direction": direction,
        "close": round(float(row.get("close", 0)), 1),
        "atr": round(float(row.get("ATR", 0)), 1),
        "rsi": round(float(row.get("RSI", 50)), 1),
        "adx": round(float(row.get("ADX", 0)), 1),
        "ma5": round(float(row.get("MA5", 0)), 1),
        "ma20": round(float(row.get("MA20", 0)), 1),
    }


def rank_symbols(data_ind: dict, name_map: dict, sector_map: dict, weights: dict) -> pd.DataFrame:
    """对所有品种打分排序。data_ind: {symbol: df_with_indicators}。"""
    rows = []
    for symbol, df in data_ind.items():
        if len(df) < 60:
            continue
        try:
            info = score_symbol(symbol, df, name_map, sector_map, weights)
            if info:
                rows.append(info)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"评分 {symbol} 异常: {e}")
    rank_df = pd.DataFrame(rows)
    if not rank_df.empty:
        rank_df = rank_df.sort_values("score", ascending=False).reset_index(drop=True)
        rank_df.index += 1
    return rank_df
