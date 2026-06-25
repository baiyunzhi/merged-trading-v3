"""
静态导出 — 合并版本 v3
把选品+回测+K线渲染成自包含 HTML（docs/index.html），发布 GitHub Pages。
运行: python export_static.py
"""
import io
import sys
from pathlib import Path
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import plotly.io as pio

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
CFG = {"displayModeBar": False, "responsive": True}


def _html(fig, div_id, include_js):
    return pio.to_html(fig, include_plotlyjs=("cdn" if include_js else False),
                       full_html=False, div_id=div_id, config=CFG)


def build():
    import html as _htmlmod
    from main import load_settings, build_pipeline
    from dashboard import make_score_heatmap, make_kline_chart, make_equity_curve
    from core.deep_analysis import build_deep_analysis

    settings = load_settings()
    rank_df, state_df, data_ind, equity_curve, summary, name_map = build_pipeline(settings)
    score_map = {r["symbol"]: r.to_dict() for _, r in rank_df.iterrows()} if not rank_df.empty else {}

    parts = [_html(make_score_heatmap(rank_df), "heatmap", True),
             _html(make_equity_curve(equity_curve), "equity", False)]

    symbols = list(data_ind.keys())
    kboxes = []
    dboxes = []
    for i, sym in enumerate(symbols):
        div = _html(make_kline_chart(sym, name_map.get(sym, sym), data_ind[sym]), f"k-{sym}", False)
        disp = "block" if i == 0 else "none"
        kboxes.append(f'<div class="kbox" id="box-{sym}" style="display:{disp}">{div}</div>')
        try:
            txt = build_deep_analysis(sym, name_map.get(sym, sym), data_ind[sym], score_map.get(sym))
        except Exception as e:
            txt = f"深度分析生成失败: {e}"
        dboxes.append(f'<pre class="dbox" id="detail-{sym}" style="display:{disp}">{_htmlmod.escape(txt)}</pre>')
    options = "\n".join(f'<option value="{s}">{name_map.get(s, s)} ({s})</option>' for s in symbols)

    def tbl(df):
        if df is None or df.empty:
            return "<p style='color:#888'>无数据</p>"
        head = "".join(f"<th>{c}</th>" for c in df.columns)
        rows = "".join("<tr>" + "".join(f"<td>{r[c]}</td>" for c in df.columns) + "</tr>"
                       for _, r in df.iterrows())
        return f'<table class="tbl"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'

    import pandas as pd
    summary_df = pd.DataFrame([summary]).T.reset_index()
    summary_df.columns = ["指标", "数值"]

    html = TEMPLATE.format(
        heatmap=parts[0], equity=parts[1], kline_boxes="\n".join(kboxes),
        detail_boxes="\n".join(dboxes), options=options,
        summary_table=tbl(summary_df), state_table=tbl(state_df),
        updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        net=summary.get("net_profit", 0), wr=summary.get("win_rate", 0),
        pf=summary.get("profit_factor", 0), tn=summary.get("total_trades", 0),
    )
    out = DOCS / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"[导出] {out}  ({out.stat().st_size//1024} KB)")


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>合并版本 v3 · 在线仪表盘</title>
<style>
body{{background:#0e1117;color:#e0e0e0;font-family:'Segoe UI',system-ui,sans-serif;margin:0;padding:0 16px 40px}}
h1{{font-size:20px;padding:16px 0 4px;color:#fff}}
.note{{color:#888;font-size:13px;margin-bottom:14px}}
.metrics{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
.metric{{background:#1a2035;border:1px solid #2a2a3e;border-radius:6px;padding:10px 18px}}
.metric .l{{color:#888;font-size:12px}}.metric .v{{font-size:18px;font-weight:bold}}
.card{{background:#161b27;border:1px solid #2a2a3e;border-radius:8px;padding:14px;margin-bottom:16px}}
.grid{{display:flex;gap:16px;flex-wrap:wrap}}.grid .card{{flex:1;min-width:340px}}
h2{{font-size:15px;color:#e0e0e0;margin:0 0 10px}}
select{{background:#0e1117;color:#e0e0e0;border:1px solid #2a2a3e;border-radius:6px;padding:6px 10px}}
table.tbl{{width:100%;border-collapse:collapse;font-size:12px}}
table.tbl th{{background:#0e1117;color:#aaa;padding:6px;border:1px solid #2a2a3e}}
table.tbl td{{padding:5px;border:1px solid #2a2a3e;text-align:center;color:#ddd}}
footer{{color:#555;font-size:12px;text-align:center;padding:20px}}
.kline-row{{display:flex;gap:16px;flex-wrap:wrap}}
.kline-col{{flex:1;min-width:480px}}
.detail-col{{width:340px;min-width:300px;background:#0e1117;border:1px solid #2a2a3e;border-radius:6px;padding:12px}}
.dbox{{color:#ccc;font-size:12px;white-space:pre-wrap;word-break:break-word;max-height:640px;overflow-y:auto;margin:0;font-family:'Consolas','SF Mono',monospace;line-height:1.6}}
</style></head><body>
<h1>🔭 合并版本 v3 · 道氏123内核 + 多因子选品 + 严谨回测</h1>
<div class="note">最后更新：{updated} ｜ 回测引擎：事件驱动·下一根开盘成交·分级滑点（无前瞻偏差）｜ 仅供学习研究</div>
<div class="metrics">
  <div class="metric"><div class="l">总交易</div><div class="v">{tn}</div></div>
  <div class="metric"><div class="l">净利润</div><div class="v">{net:,.0f}</div></div>
  <div class="metric"><div class="l">胜率</div><div class="v">{wr:.0%}</div></div>
  <div class="metric"><div class="l">盈亏比</div><div class="v">{pf:.2f}</div></div>
</div>
<div class="card"><h2>品种综合评分排行</h2>{heatmap}</div>
<div class="card"><h2>K 线分析 + 行情深度分析（可切换品种）</h2>
  <div style="margin-bottom:10px"><label style="color:#aaa;margin-right:8px">选择品种：</label>
  <select id="symSelect" onchange="switchSym(this.value)">{options}</select></div>
  <div class="kline-row">
    <div class="kline-col">{kline_boxes}</div>
    <div class="detail-col"><h3 style="color:#26a69a;font-size:14px;margin:0 0 8px">📈 行情深度分析</h3>{detail_boxes}</div>
  </div>
</div>
<div class="card"><h2>组合回测权益曲线</h2>{equity}</div>
<div class="grid">
  <div class="card"><h2>📊 回测绩效汇总</h2>{summary_table}</div>
  <div class="card"><h2>🎯 当前市场状态</h2>{state_table}</div>
</div>
<footer>⚠️ 历史回测不代表未来表现，商品期货风险较大，请严格执行止损。</footer>
<script>
function switchSym(s){{document.querySelectorAll('.kbox').forEach(function(b){{b.style.display='none';}});
document.querySelectorAll('.dbox').forEach(function(b){{b.style.display='none';}});
var x=document.getElementById('box-'+s);if(x){{x.style.display='block';window.dispatchEvent(new Event('resize'));}}
var d=document.getElementById('detail-'+s);if(d){{d.style.display='block';}}}}
</script></body></html>"""


if __name__ == "__main__":
    build()
