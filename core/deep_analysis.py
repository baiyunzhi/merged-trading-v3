"""
深度分析整合器 — 合并版 v3

把四路分析整合成一段人类可读的"行情深度分析"文字：
  1. 道氏结构状态（合并版内核，来自 indicators 的 dow_trend_state）
  2. 价格结构（structure_analyzer：枢轴高低点 + 趋势/子状态 + 支撑阻力）
  3. K线密度/震荡指数（kline_density：CI + 是否适合交易）
  4. 量价持仓（volume_oi_analyzer：量仓四象限）
再叠加选品评分（selector）。
"""
from core.structure_analyzer import analyze_structure, get_key_levels
from core.kline_density import analyze_density
from core.volume_oi_analyzer import analyze_vol_oi


_DOW_ZH = {
    "BULL_CONFIRMED": "多头确认", "BULL_PULLBACK": "多头回调",
    "BEAR_CONFIRMED": "空头确认", "BEAR_PULLBACK": "空头回调",
    "BEAR_WARNING": "见顶警告", "NEUTRAL": "中性",
}


def build_deep_analysis(symbol: str, name: str, df, score_info: dict | None = None) -> str:
    """生成单品种深度分析文字。df 为含指标的 DataFrame（含 date/ATR/oi 等）。"""
    if df is None or df.empty:
        return f"{name}({symbol})：暂无行情数据"

    last = df.iloc[-1]
    close = float(last.get("close", 0))
    lines = [f"━━ {name}({symbol}) 行情深度分析 ━━", ""]

    # ── 1. 选品评分 ──
    if score_info:
        lines.append(f"【综合评分】{score_info.get('score', 0):.1f} / 100  "
                     f"方向：{score_info.get('direction', '-')}")
        lines.append(f"  趋势分 {score_info.get('trend_score', 0):.0f} ｜ "
                     f"动量分 {score_info.get('mom_score', 0):.0f} ｜ "
                     f"波动分 {score_info.get('vol_score', 0):.0f}")
        lines.append("")

    # ── 2. 道氏结构状态（合并版内核）──
    dow = last.get("dow_trend_state", "NEUTRAL")
    lines.append(f"【道氏结构】{_DOW_ZH.get(dow, dow)}")
    adx = last.get("ADX") or last.get("adx14")
    if adx is not None and adx == adx:
        trend_str = "强趋势" if adx >= 25 else ("有趋势" if adx >= 20 else "弱/无趋势")
        lines.append(f"  ADX={float(adx):.1f}（{trend_str}）")
    lines.append("")

    # ── 3. 价格结构（枢轴）──
    try:
        st = analyze_structure(df)
        lines.append("【价格结构】")
        lines.append(f"  {st.description}")
        lines.append(f"  近期高点 {st.recent_high} ｜ 近期低点 {st.recent_low}")
        lines.append(f"  最近支撑 {st.support} ｜ 最近阻力 {st.resistance}")
        levels = get_key_levels(st, n=2)
        if levels:
            lv = "  关键位：" + "，".join(f"{x['label']}" for x in levels[:4])
            lines.append(lv)
        lines.append("")
    except Exception as e:
        lines.append(f"【价格结构】分析跳过（{e}）"); lines.append("")

    # ── 4. K线密度 / 震荡指数 ──
    try:
        den = analyze_density(df)
        lines.append("【K线密度 / 震荡指数】")
        lines.append(f"  {den.label}（CI={den.ci:.0f}，{den.ci_state}）")
        lines.append(f"  {den.description}")
        lines.append(f"  交易建议：{'适合参与' if den.tradeable else '观望为宜（盘整密集）'}")
        lines.append("")
    except Exception as e:
        lines.append(f"【K线密度】分析跳过（{e}）"); lines.append("")

    # ── 5. 量价持仓 ──
    try:
        vo = analyze_vol_oi(df)
        lines.append("【量价持仓】")
        lines.append(f"  {vo.summary}")
        lines.append(f"  综合信号：{vo.combined_signal}（看多度 {vo.combined_score}/100）")
        lines.append("")
    except Exception as e:
        lines.append(f"【量价持仓】分析跳过（{e}）"); lines.append("")

    lines.append(f"当前收盘价：{close:.1f}")
    lines.append("─" * 24)
    lines.append("⚠️ 仅供研究参考，不构成投资建议。")
    return "\n".join(lines)
