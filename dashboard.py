"""
Dash 动态仪表盘 — 合并版本 v3
保留搭建系的交互体验，回测结果来自claude系引擎（无前瞻偏差），新增组合风控面板。
"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc


# ── 图表函数 ──────────────────────────────────────────────────────────────

def make_score_heatmap(rank_df: pd.DataFrame) -> go.Figure:
    if rank_df.empty:
        return go.Figure()
    fig = px.bar(
        rank_df, x="name", y="score", color="score",
        color_continuous_scale="RdYlGn", range_color=[0, 100],
        hover_data=["symbol", "direction", "rsi", "adx", "sector"],
        labels={"score": "综合评分", "name": "品种"}, title="品种综合评分排行",
    )
    fig.update_layout(height=340, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font_color="#e0e0e0", xaxis_tickangle=-30, margin=dict(t=46, b=80))
    return fig


def make_kline_chart(symbol: str, name: str, df: pd.DataFrame) -> go.Figure:
    df = df.copy().tail(120)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.55, 0.25, 0.20],
                        vertical_spacing=0.04,
                        subplot_titles=[f"{name} K线+均线+布林带", "MACD", "RSI"])
    fig.add_trace(go.Candlestick(x=df["date"], open=df["open"], high=df["high"],
                                 low=df["low"], close=df["close"],
                                 increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
                                 name="K线"), row=1, col=1)
    for ma, color in {"MA5": "#FFD700", "MA10": "#FFA500", "MA20": "#00BFFF", "MA60": "#FF69B4"}.items():
        if ma in df.columns:
            fig.add_trace(go.Scatter(x=df["date"], y=df[ma], line=dict(color=color, width=1), name=ma), row=1, col=1)
    if "BB_UPPER" in df.columns:
        fig.add_trace(go.Scatter(x=pd.concat([df["date"], df["date"][::-1]]),
                                 y=pd.concat([df["BB_UPPER"], df["BB_LOWER"][::-1]]),
                                 fill="toself", fillcolor="rgba(128,128,255,0.08)",
                                 line=dict(color="rgba(0,0,0,0)"), name="布林带"), row=1, col=1)
    if "HIST" in df.columns:
        colors = ["#ef5350" if v < 0 else "#26a69a" for v in df["HIST"]]
        fig.add_trace(go.Bar(x=df["date"], y=df["HIST"], marker_color=colors, name="MACD柱"), row=2, col=1)
    if "DIF" in df.columns:
        fig.add_trace(go.Scatter(x=df["date"], y=df["DIF"], line=dict(color="#FFD700", width=1), name="DIF"), row=2, col=1)
    if "DEA" in df.columns:
        fig.add_trace(go.Scatter(x=df["date"], y=df["DEA"], line=dict(color="#FF69B4", width=1), name="DEA"), row=2, col=1)
    if "RSI" in df.columns:
        fig.add_trace(go.Scatter(x=df["date"], y=df["RSI"], line=dict(color="#00BFFF", width=1.5), name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", opacity=0.5, row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", opacity=0.5, row=3, col=1)
    fig.update_layout(height=600, paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font_color="#e0e0e0", showlegend=True, legend=dict(orientation="h", y=1.02),
                      xaxis_rangeslider_visible=False, margin=dict(t=60, b=20))
    fig.update_xaxes(gridcolor="#2a2a3e"); fig.update_yaxes(gridcolor="#2a2a3e")
    return fig


def make_equity_curve(equity_curve: list) -> go.Figure:
    fig = go.Figure()
    if equity_curve:
        edf = pd.DataFrame(equity_curve)
        edf = edf.drop_duplicates(subset=["datetime"], keep="last")
        fig.add_trace(go.Scatter(x=pd.to_datetime(edf["datetime"]), y=edf["equity"],
                                 mode="lines", name="组合权益", line=dict(color="#26a69a", width=1.6)))
    fig.update_layout(title="组合回测权益曲线", height=360, paper_bgcolor="#0e1117",
                      plot_bgcolor="#0e1117", font_color="#e0e0e0",
                      xaxis=dict(gridcolor="#2a2a3e"), yaxis=dict(gridcolor="#2a2a3e", title="权益"),
                      margin=dict(t=50, b=30))
    return fig


# ── App ───────────────────────────────────────────────────────────────────

def create_app(rank_df, state_df, data_ind, equity_curve, summary, name_map):
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG], title="合并版v3 交易系统")
    symbols = list(data_ind.keys())
    options = [{"label": f"{name_map.get(s, s)} ({s})", "value": s} for s in symbols]
    default_sym = rank_df["symbol"].iloc[0] if not rank_df.empty else (symbols[0] if symbols else None)

    CARD = {"backgroundColor": "#161b27", "border": "1px solid #2a2a3e",
            "borderRadius": "8px", "padding": "14px", "marginBottom": "16px"}

    def metric_cards():
        m = summary
        items = [
            ("总交易", m.get("total_trades", 0), "#e0e0e0"),
            ("净利润", f"{m.get('net_profit', 0):,.0f}", "#26a69a" if m.get("net_profit", 0) >= 0 else "#ef5350"),
            ("胜率", f"{m.get('win_rate', 0):.0%}", "#FFD700"),
            ("盈亏比", f"{m.get('profit_factor', 0):.2f}", "#00BFFF"),
            ("最大回撤", f"{m.get('max_drawdown_pct', 0):.1%}", "#ef5350"),
            ("最终权益", f"{m.get('final_equity', 0):,.0f}", "#e0e0e0"),
        ]
        cols = []
        for label, val, color in items:
            cols.append(dbc.Col(dbc.Card(dbc.CardBody([
                html.Div(label, style={"color": "#888", "fontSize": "12px"}),
                html.Div(str(val), style={"color": color, "fontSize": "18px", "fontWeight": "bold"}),
            ]), style={"backgroundColor": "#1a2035", "border": "1px solid #2a2a3e",
                       "borderRadius": "6px"}), width=2))
        return dbc.Row(cols, className="mb-3")

    def table(df, page=10):
        if df is None or df.empty:
            return html.P("无数据", style={"color": "#888"})
        return dash_table.DataTable(
            data=df.to_dict("records"),
            columns=[{"name": c, "id": c} for c in df.columns],
            style_table={"overflowX": "auto"},
            style_cell={"backgroundColor": "#161b27", "color": "#e0e0e0",
                        "border": "1px solid #2a2a3e", "textAlign": "center",
                        "fontSize": "11px", "padding": "5px"},
            style_header={"backgroundColor": "#0e1117", "fontWeight": "bold", "color": "#aaa"},
            page_size=page,
        )

    app.layout = dbc.Container([
        dbc.Row(dbc.Col(html.H3("🔭 合并版本 v3 · 道氏123内核 + 多因子选品 + 严谨回测",
                                style={"color": "#fff", "padding": "16px 0 6px"}))),
        dbc.Row(dbc.Col(html.P("回测引擎：事件驱动·下一根开盘成交·分级滑点（无前瞻偏差）",
                               style={"color": "#888", "fontSize": "13px"}))),
        metric_cards(),
        dbc.Row(dbc.Col(dbc.Card([dcc.Graph(figure=make_score_heatmap(rank_df))], style=CARD))),
        dbc.Row(dbc.Col(dbc.Card([
            html.Div([html.Label("选择品种：", style={"color": "#aaa", "marginRight": "8px"}),
                      dcc.Dropdown(id="sym-dd", options=options, value=default_sym, clearable=False,
                                   style={"width": "240px", "display": "inline-block", "color": "#333"})],
                     style={"padding": "8px 12px"}),
            dbc.Row([
                dbc.Col(dcc.Graph(id="kline"), width=8),
                dbc.Col([
                    html.H6("📈 行情深度分析", style={"color": "#26a69a", "marginBottom": "8px"}),
                    html.Pre(id="deep-text", style={
                        "color": "#ccc", "fontSize": "12px", "whiteSpace": "pre-wrap",
                        "wordBreak": "break-word", "maxHeight": "560px", "overflowY": "auto",
                        "backgroundColor": "#0e1117", "padding": "10px", "borderRadius": "6px",
                        "fontFamily": "Consolas, monospace", "lineHeight": "1.6"}),
                ], width=4),
            ]),
        ], style=CARD))),
        dbc.Row(dbc.Col(dbc.Card([dcc.Graph(figure=make_equity_curve(equity_curve))], style=CARD))),
        dbc.Row([
            dbc.Col(dbc.Card([html.H5("📊 回测绩效汇总", style={"color": "#e0e0e0", "marginBottom": "10px"}),
                              table(pd.DataFrame([summary]).T.reset_index().rename(columns={"index": "指标", 0: "数值"}))],
                             style=CARD), width=5),
            dbc.Col(dbc.Card([html.H5("🎯 当前市场状态（选品+道氏）", style={"color": "#e0e0e0", "marginBottom": "10px"}),
                              table(state_df)], style=CARD), width=7),
        ]),
        dbc.Row(dbc.Col(html.P("⚠️ 仅供学习研究，不构成投资建议。历史回测不代表未来表现，期货风险较大。",
                               style={"color": "#666", "fontSize": "12px", "textAlign": "center", "padding": "16px"}))),
    ], fluid=True, style={"backgroundColor": "#0e1117", "minHeight": "100vh"})

    from core.deep_analysis import build_deep_analysis
    score_map = {r["symbol"]: r.to_dict() for _, r in rank_df.iterrows()} if not rank_df.empty else {}

    @app.callback(
        [Output("kline", "figure"), Output("deep-text", "children")],
        Input("sym-dd", "value"),
    )
    def _update(sym):
        if sym and sym in data_ind:
            fig = make_kline_chart(sym, name_map.get(sym, sym), data_ind[sym])
            text = build_deep_analysis(sym, name_map.get(sym, sym), data_ind[sym], score_map.get(sym))
            return fig, text
        return go.Figure(), "请选择品种"

    return app
