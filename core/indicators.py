"""
指标计算模块
新增：布林带宽度过滤，供 ADX+BB_WIDTH 双重市场环境过滤使用
"""
import pandas as pd


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    prev_close = df.groupby("symbol", sort=False)["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = df.groupby("symbol", sort=False)["tr"].transform(
        lambda s: s.rolling(period).mean()
    )
    return df


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    grouped = df.groupby("symbol", sort=False)
    df["prev_close"] = grouped["close"].shift(1)
    df["ma20"] = grouped["close"].transform(lambda s: s.rolling(20).mean())
    df["ma60"] = grouped["close"].transform(lambda s: s.rolling(60).mean())
    df["ma120"] = grouped["close"].transform(lambda s: s.rolling(120).mean())
    df["vol_ma20"] = grouped["volume"].transform(lambda s: s.rolling(20).mean())
    df["oi_ma5"] = grouped["oi"].transform(lambda s: s.rolling(5).mean())
    df["oi_ma20"] = grouped["oi"].transform(lambda s: s.rolling(20).mean())
    df["turnover"] = df["close"] * df["volume"]
    df["turnover_ma20"] = grouped["turnover"].transform(lambda s: s.rolling(20).mean())
    df["volume_ratio_20"] = (df["volume"] / df["vol_ma20"].replace(0, pd.NA)).fillna(0)
    df["oi_ratio_5"] = (df["oi"] / df["oi_ma5"].replace(0, pd.NA)).fillna(1)
    df["ret_5"] = grouped["close"].pct_change(5)
    df["ma20_slope_5"] = grouped["ma20"].pct_change(5)
    df["ma60_slope_10"] = grouped["ma60"].pct_change(10)
    df["atr_pct"] = df["atr"] / df["close"]
    df["highest_20"] = grouped["high"].transform(lambda s: s.rolling(20).max().shift(1))
    df["lowest_20"] = grouped["low"].transform(lambda s: s.rolling(20).min().shift(1))
    df["highest_55"] = grouped["high"].transform(lambda s: s.rolling(55).max().shift(1))
    df["lowest_55"] = grouped["low"].transform(lambda s: s.rolling(55).min().shift(1))
    df["donchian_width_55"] = (df["highest_55"] - df["lowest_55"]) / df["close"]

    # 改善4：布林带宽度用于震荡市场过滤
    bb_mid = grouped["close"].transform(lambda s: s.rolling(20).mean())
    bb_std = grouped["close"].transform(lambda s: s.rolling(20).std())
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    df["bb_width_pct"] = (bb_upper - bb_lower) / bb_mid.replace(0, pd.NA)

    df = _add_adx(df)
    df = _add_dow_structure(df)
    df = _add_selection_scores(df)
    df = _add_display_indicators(df)
    return df


def _add_display_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """搭建系经典指标：MACD/RSI/MA5/MA10/布林上下轨/量均线，供选品评分与Dash展示。
    大写列名与 交易系统搭建 保持一致，便于直接复用其 selector 与 dashboard。"""
    df = df.copy()
    grouped = df.groupby("symbol", sort=False)

    # 均线（大写别名）
    df["MA5"] = grouped["close"].transform(lambda s: s.rolling(5).mean())
    df["MA10"] = grouped["close"].transform(lambda s: s.rolling(10).mean())
    df["MA20"] = df["ma20"]
    df["MA60"] = df["ma60"]

    # RSI(14)
    def _rsi(s):
        delta = s.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        return 100 - 100 / (1 + rs)
    df["RSI"] = grouped["close"].transform(_rsi)

    # MACD (12,26,9)
    def _ema(s, span):
        return s.ewm(span=span, adjust=False).mean()
    dif = grouped["close"].transform(lambda s: _ema(s, 12) - _ema(s, 26))
    df["DIF"] = dif
    df["DEA"] = dif.groupby(df["symbol"], sort=False).transform(lambda s: _ema(s, 9))
    df["HIST"] = (df["DIF"] - df["DEA"]) * 2

    # 布林带上下轨（绝对值，用于K线绘图）
    bb_mid = df["ma20"]
    bb_std = grouped["close"].transform(lambda s: s.rolling(20).std())
    df["BB_MID"] = bb_mid
    df["BB_UPPER"] = bb_mid + 2 * bb_std
    df["BB_LOWER"] = bb_mid - 2 * bb_std

    # 量均线 + ATR 大写别名
    df["VOL_MA5"] = grouped["volume"].transform(lambda s: s.rolling(5).mean())
    df["ATR"] = df["atr"]
    df["ADX"] = df["adx14"]
    return df


def _add_selection_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    volume_rank = df.groupby("datetime", sort=False)["vol_ma20"].rank(pct=True).fillna(0)
    turnover_rank = df.groupby("datetime", sort=False)["turnover_ma20"].rank(pct=True).fillna(0)
    oi_rank = df.groupby("datetime", sort=False)["oi_ma20"].rank(pct=True).fillna(0)
    volume_abs_score = (df["volume_ratio_20"].clip(lower=0, upper=2) / 2).fillna(0)
    oi_abs_score = (df["oi_ratio_5"].clip(lower=0, upper=1.5) / 1.5).fillna(0)
    df["liquidity_score"] = (
        45 * volume_rank + 35 * turnover_rank + 10 * oi_rank + 10 * volume_abs_score
    ).round(2)
    df["participation_score"] = (100 * (0.7 * volume_abs_score + 0.3 * oi_abs_score)).round(2)
    ma_stack = ((df["close"] > df["ma60"]) & (df["ma60"] > df["ma120"])).astype(float)
    ma20_slope = (df["ma20_slope_5"].clip(lower=0, upper=0.05) / 0.05).fillna(0)
    ma60_slope = (df["ma60_slope_10"].clip(lower=0, upper=0.05) / 0.05).fillna(0)
    adx_score = (df["adx14"].clip(lower=0, upper=40) / 40).fillna(0)
    channel_score = (df["donchian_width_55"].clip(lower=0, upper=0.25) / 0.25).fillna(0)
    structure_score = df["dow_trend_state"].isin(["BULL_CONFIRMED", "BULL_PULLBACK"]).astype(float)
    df["trend_score"] = (
        25 * ma_stack + 20 * ma20_slope + 15 * ma60_slope
        + 20 * adx_score + 10 * channel_score + 10 * structure_score
    ).round(2)
    atr_pct = df["atr_pct"].fillna(0)
    df["risk_heat"] = (100 * (atr_pct.clip(lower=0, upper=0.08) / 0.08)).round(2)
    df["selection_score"] = (
        0.35 * df["liquidity_score"]
        + 0.45 * df["trend_score"]
        + 0.20 * df["participation_score"]
    ).round(2)
    df["selection_rank"] = df.groupby("datetime", sort=False)["selection_score"].rank(
        method="first", ascending=False
    )
    return df


def _add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    grouped = df.groupby("symbol", sort=False)
    prev_high = grouped["high"].shift(1)
    prev_low = grouped["low"].shift(1)
    up_move = df["high"] - prev_high
    down_move = prev_low - df["low"]
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    def _wilder(series: pd.Series) -> pd.Series:
        return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    tr_smooth = df.groupby("symbol", sort=False)["tr"].transform(_wilder)
    plus_dm_smooth = plus_dm.groupby(df["symbol"], sort=False).transform(_wilder)
    minus_dm_smooth = minus_dm.groupby(df["symbol"], sort=False).transform(_wilder)
    plus_di = 100 * plus_dm_smooth / tr_smooth.replace(0, pd.NA)
    minus_di = 100 * minus_dm_smooth / tr_smooth.replace(0, pd.NA)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    df["adx14"] = dx.groupby(df["symbol"], sort=False).transform(_wilder)
    return df


def _add_dow_structure(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    df = df.copy()
    grouped = df.groupby("symbol", sort=False)
    # 【仅适用于回测】实盘逐bar计算时禁止使用此函数
    df["confirmed_swing_high"] = grouped["high"].transform(
        lambda s: _confirmed_swing(s, left, right, "high")
    )
    df["confirmed_swing_low"] = grouped["low"].transform(
        lambda s: _confirmed_swing(s, left, right, "low")
    )
    df["latest_swing_high"] = grouped["confirmed_swing_high"].ffill()
    df["latest_swing_low"] = grouped["confirmed_swing_low"].ffill()
    df["latest_swing_high_age"] = grouped["confirmed_swing_high"].transform(_bars_since_confirmed)
    df["latest_swing_low_age"] = grouped["confirmed_swing_low"].transform(_bars_since_confirmed)
    df["prev_swing_high"] = grouped["confirmed_swing_high"].transform(_previous_confirmed_value)
    df["prev_swing_low"] = grouped["confirmed_swing_low"].transform(_previous_confirmed_value)
    df["higher_high"] = df["latest_swing_high"] > df["prev_swing_high"]
    df["higher_low"] = df["latest_swing_low"] > df["prev_swing_low"]
    df["lower_high"] = df["latest_swing_high"] < df["prev_swing_high"]
    df["lower_low"] = df["latest_swing_low"] < df["prev_swing_low"]
    df["pure_dow_trend_state"] = df.apply(_pure_dow_state, axis=1)
    states = []
    for _, group in df.groupby("symbol", sort=False):
        states.append(_dow_state_machine(group))
    df["dow_trend_state"] = pd.concat(states).sort_index()
    return df


def _pure_dow_state(row) -> str:
    hh = bool(row.get("higher_high"))
    hl = bool(row.get("higher_low"))
    lh = bool(row.get("lower_high"))
    ll = bool(row.get("lower_low"))
    if hh and hl:
        return "BULL_TREND"
    if lh and ll:
        return "BEAR_TREND"
    if hh and ll:
        return "EXPANDING_RANGE"
    if lh and hl:
        return "CONTRACTING_RANGE"
    return "NEUTRAL"


def _confirmed_swing(series: pd.Series, left: int, right: int, kind: str) -> pd.Series:
    window = left + right + 1
    if kind == "high":
        pivot = series.where(series == series.rolling(window, center=True).max())
    else:
        pivot = series.where(series == series.rolling(window, center=True).min())
    return pivot.shift(right)


def _previous_confirmed_value(series: pd.Series) -> pd.Series:
    latest = series.ffill()
    previous_on_confirmation = latest.shift(1).where(series.notna())
    return previous_on_confirmation.ffill()


def _bars_since_confirmed(series: pd.Series) -> pd.Series:
    ages = []
    age = None
    for is_confirmed in series.notna():
        if is_confirmed:
            age = 0
        elif age is not None:
            age += 1
        ages.append(pd.NA if age is None else age)
    return pd.Series(ages, index=series.index)


def _dow_state_machine(group: pd.DataFrame) -> pd.Series:
    states = []
    state = "NEUTRAL"
    for _, row in group.iterrows():
        close = float(row["close"])
        ma60 = row.get("ma60")
        ma120 = row.get("ma120")
        latest_low = row.get("latest_swing_low")
        latest_high = row.get("latest_swing_high")
        has_ma = ma60 == ma60 and ma120 == ma120
        has_swings = latest_low == latest_low and latest_high == latest_high
        bull_confirmed = bool(row.get("higher_high") and row.get("higher_low") and has_ma and close > ma60 > ma120)
        bear_confirmed = bool(row.get("lower_high") and row.get("lower_low") and has_ma and close < ma120)
        bull_broken = bool(has_swings and close < latest_low)

        if bull_confirmed:
            state = "BULL_CONFIRMED"
        elif bear_confirmed:
            state = "BEAR_CONFIRMED"
        elif state in ("BULL_CONFIRMED", "BULL_PULLBACK"):
            if bull_broken or (has_ma and close < ma120):
                state = "BEAR_WARNING"
            elif has_ma and close < ma60:
                state = "BULL_PULLBACK"
            else:
                state = "BULL_CONFIRMED"
        elif state == "BEAR_CONFIRMED":
            if has_ma and close > ma60:
                state = "BEAR_PULLBACK"
        elif state == "BEAR_PULLBACK":
            if bull_confirmed:
                state = "BULL_CONFIRMED"
            elif has_ma and close > ma120:
                state = "NEUTRAL"
            elif has_ma and close < ma120:
                state = "BEAR_CONFIRMED"
        elif state == "BEAR_WARNING":
            if bull_confirmed:
                state = "BULL_CONFIRMED"
            elif bear_confirmed:
                state = "BEAR_CONFIRMED"
            elif has_ma and close > ma120:
                state = "NEUTRAL"
        else:
            if has_ma and row.get("higher_low") and close > ma120:
                state = "BULL_PULLBACK"
            elif has_ma and row.get("lower_high") and close < ma120:
                state = "BEAR_PULLBACK"
        states.append(state)
    return pd.Series(states, index=group.index)
