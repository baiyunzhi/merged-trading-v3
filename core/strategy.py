"""
ClaudeStrategy — 职业级期货策略

改善1: 成交量确认（突破K线量≥20日均量×volume_breakout_ratio，实体≥ATR×min_body_atr_ratio）
改善4: ADX>25 + 布林带宽度>阈值，双重市场环境过滤，震荡市不开仓
改善5: 板块风险限制在 replay_engine 层执行，strategy 层传递 sector 标签
"""


def _valid(v):
    try:
        f = float(v)
        return f == f and not (f != f)
    except (TypeError, ValueError):
        return False


def _crossed_above(prev, cur, level):
    if not (_valid(prev) and _valid(cur) and _valid(level)):
        return False
    return float(prev) < float(level) <= float(cur)


def _crossed_below(prev, cur, level):
    if not (_valid(prev) and _valid(cur) and _valid(level)):
        return False
    return float(prev) > float(level) >= float(cur)


def _fmt(v):
    try:
        return f"{float(v):.4f}"
    except (TypeError, ValueError):
        return "—"


class ClaudeStrategy:
    """
    道氏结构 + 123形态 + 双底/双顶，叠加7条职业改善过滤器。
    """

    def __init__(self, settings: dict):
        self.s = settings
        self.min_adx = float(settings.get("min_adx", 25))
        self.min_bb_width = float(settings.get("min_bb_width_pct", 0.20))
        self.vol_ratio = float(settings.get("volume_breakout_ratio", 1.5))
        self.body_atr = float(settings.get("min_body_atr_ratio", 0.6))
        self.allowed_bull = set(settings.get("allowed_dow_states", ["BULL_CONFIRMED", "BULL_PULLBACK"]))
        self.allowed_bear = set(settings.get("allowed_bear_states", ["BEAR_CONFIRMED", "BEAR_PULLBACK"]))

    def generate_signal(self, row: dict) -> dict:
        sym = row["symbol"]
        dt = row["datetime"]

        if not _valid(row.get("atr")):
            return self._none(row, "ATR数据不足")

        atr = float(row["atr"])
        close = float(row["close"])
        prev_close = row.get("prev_close")
        adx = row.get("adx14")
        bb_width = row.get("bb_width_pct")
        vol_ratio_20 = row.get("volume_ratio_20")
        dow_state = row.get("dow_trend_state", "NEUTRAL")
        pure_state = row.get("pure_dow_trend_state", "NEUTRAL")

        # ── 改善4：市场环境双重过滤 ──────────────────────────────────────────
        adx_ok = _valid(adx) and float(adx) >= self.min_adx
        bb_ok = _valid(bb_width) and float(bb_width) >= self.min_bb_width
        env_ok = adx_ok and bb_ok
        if not env_ok:
            reason = []
            if not adx_ok:
                reason.append(f"ADX={_fmt(adx)}<{self.min_adx}(震荡市)")
            if not bb_ok:
                reason.append(f"布林带宽度={_fmt(bb_width)}<{self.min_bb_width}(波动率低位)")
            return self._none(row, "市场环境过滤: " + "，".join(reason))

        # ── 改善1：成交量 + 实体确认 ─────────────────────────────────────────
        body = abs(close - float(row.get("open", close)))
        vol_ok = _valid(vol_ratio_20) and float(vol_ratio_20) >= self.vol_ratio
        body_ok = body >= atr * self.body_atr

        # ── 摆动结构 ──────────────────────────────────────────────────────────
        latest_high = row.get("latest_swing_high")
        latest_low = row.get("latest_swing_low")
        prev_high = row.get("prev_swing_high")
        prev_low = row.get("prev_swing_low")

        # ── 信号判断 ──────────────────────────────────────────────────────────
        # 多头：道氏允许状态 + HH+HL + 突破最近确认高点
        long_123 = (
            dow_state in self.allowed_bull
            and bool(row.get("higher_high"))
            and bool(row.get("higher_low"))
            and _crossed_above(prev_close, close, latest_high)
            and vol_ok and body_ok
        )

        # 空头：道氏允许状态 + LH+LL + 跌破最近确认低点
        short_123 = (
            dow_state in self.allowed_bear
            and bool(row.get("lower_high"))
            and bool(row.get("lower_low"))
            and _crossed_below(prev_close, close, latest_low)
            and vol_ok and body_ok
        )

        # 双底/三底突破
        bottom_ok = (
            row.get("bottom_pattern") in ("double_bottom", "triple_bottom")
            and bool(row.get("bottom_breakout"))
            and _valid(row.get("bottom_pattern_support"))
            and _valid(row.get("bottom_pattern_neckline"))
            and vol_ok and body_ok
        )

        # 双顶/三顶跌破
        top_ok = (
            row.get("top_pattern") in ("double_top", "triple_top")
            and bool(row.get("top_breakdown"))
            and _valid(row.get("top_pattern_resistance"))
            and _valid(row.get("top_pattern_neckline"))
            and vol_ok and body_ok
        )

        direction = "none"
        signal_type = "none"
        trigger = None
        structure_stop = None

        if bottom_ok:
            direction = "long"
            signal_type = "bottom_reversal"
            trigger = float(row["bottom_pattern_neckline"])
            structure_stop = float(row["bottom_pattern_support"])
        elif top_ok:
            direction = "short"
            signal_type = "top_reversal"
            trigger = float(row["top_pattern_neckline"])
            structure_stop = float(row["top_pattern_resistance"])
        elif long_123:
            direction = "long"
            signal_type = "long_123"
            trigger = float(latest_high)
            # 改善2：结构止损放在最近摆动低点下方 0.3ATR
            structure_stop = float(latest_low) - atr * self.s.get("structure_stop_buffer_atr", 0.3)
        elif short_123:
            direction = "short"
            signal_type = "short_123"
            trigger = float(latest_low)
            structure_stop = float(latest_high) + atr * self.s.get("structure_stop_buffer_atr", 0.3)

        # ── 评分 ──────────────────────────────────────────────────────────────
        score = 0
        if direction != "none":
            score += 40  # 基础信号
            score += 20 if vol_ok else 0
            score += 10 if body_ok else 0
            score += 15 if signal_type in ("bottom_reversal", "top_reversal") else 10
            score += 15 if adx_ok else 0

        reason = {
            "signal_type": signal_type,
            "dow_state": dow_state,
            "pure_state": pure_state,
            "adx": round(float(adx), 2) if _valid(adx) else None,
            "bb_width": round(float(bb_width), 4) if _valid(bb_width) else None,
            "vol_ratio": round(float(vol_ratio_20), 2) if _valid(vol_ratio_20) else None,
            "vol_ok": vol_ok,
            "body_ok": body_ok,
            "env_ok": env_ok,
            "higher_high": bool(row.get("higher_high")),
            "higher_low": bool(row.get("higher_low")),
            "lower_high": bool(row.get("lower_high")),
            "lower_low": bool(row.get("lower_low")),
            "latest_swing_high": round(float(latest_high), 4) if _valid(latest_high) else None,
            "latest_swing_low": round(float(latest_low), 4) if _valid(latest_low) else None,
            "trigger_level": round(trigger, 4) if trigger is not None else None,
            "structure_stop_loss": round(structure_stop, 4) if structure_stop is not None else None,
        }

        return {
            "datetime": dt,
            "symbol": sym,
            "direction": direction,
            "score": score,
            "risk_multiplier": 1.0 if direction != "none" else 0.0,
            "atr": atr,
            "reason": reason,
        }

    def _none(self, row, msg):
        return {
            "datetime": row["datetime"],
            "symbol": row["symbol"],
            "direction": "none",
            "score": 0,
            "risk_multiplier": 0.0,
            "atr": float(row["atr"]) if _valid(row.get("atr")) else 0.0,
            "reason": {"skip": msg},
        }
