# 合并版本 v3 · 期货量化交易系统

融合两套独立系统的第三版，取长补短：

- **回测内核** 来自 *claude系统交易*：事件驱动、**下一根K线开盘成交（无前瞻偏差）**、组合级风控、分级滑点
- **选品 + 实时数据 + 交互可视化** 来自 *交易系统搭建*：多因子评分、akshare 实时、Dash 仪表盘

## 在线仪表盘

**https://baiyunzhi.github.io/merged-trading-v3/**（静态导出，点开即看，无需后端）

## 架构

```
数据层  data_hub.py        双通道：CSV历史(严谨回测) / akshare实时(盯盘选品)，失败回退仿真
核心层  core/indicators.py  道氏结构+ADX+布林带 ⊕ MACD/RSI/MA5(展示用)
        core/strategy.py    道氏123 + 双底双顶 + 量能/实体确认 + ADX/布林带环境过滤
        core/engine.py      事件驱动回测引擎（下一根开盘成交）
        core/risk.py        组合风控 + 板块限制 + 分批/追踪/时间止损 + 分级滑点
        core/sizer.py       ATR定额 + 保证金约束
        core/selector.py    多因子选品（趋势40%+动量35%+波动25%）
        core/stats.py       绩效统计
        core/market_state.py 5级市场状态
展示层  dashboard.py        Dash 动态盘（实时交互）
        export_static.py    静态导出 → docs/index.html（GitHub Pages）
入口    main.py             全流程 + 启动Dash
        run_backtest.py     纯CLI回测
```

## 运行

```bash
pip install -r requirements.txt
pip install pyarrow

python run_backtest.py     # 纯回测，打印绩效
python main.py             # 启动Dash → http://127.0.0.1:8050
python export_static.py    # 生成 docs/index.html
```

## 双通道 vs 双模式

| | 选项 | 用途 |
|---|------|------|
| **数据通道** | `csv`（默认） | 历史数据，严谨可复现，**回测专用** |
| | `akshare` | 实时行情，盯盘选品 |
| **展示模式** | Dash 动态 | 本地交互，实时切换 |
| | 静态导出 | 在线网址，点开即看 |

切换数据通道：改 `config/settings.json` 的 `data_source`。

## 它如何取长补短

| 痛点（旧系统） | 本版修复 |
|----------------|----------|
| 搭建系回测**当根收盘价成交**（前瞻偏差，结果偏乐观） | 改用 claude 系引擎：信号收盘确认 → **下一根开盘成交** |
| 搭建系风控**仅单品种ATR止损** | 引入组合总风险2% + 板块同向≤2 + 保证金约束 |
| 搭建系无滑点建模 | 分级滑点（止损出场2tick惩罚） |
| claude 系**无选品能力** | 引入多因子评分，先选品再交易 |
| claude 系前端**只有静态页** | 增加 Dash 动态盘 + 保留静态导出 |

## 关于回测结果

本版在 10 品种历史数据上的回测结果**如实呈现**，未做参数调优粉饰。
由于修掉了前瞻偏差并加入真实滑点/手续费，结果通常比"理想成交"的旧回测更保守——
**这正是严谨回测的价值**：宁可在历史上看到真实的不足，也不要被乐观数字误导实盘。

## 免责声明

仅用于技术研究与学习。历史回测不代表未来表现，期货交易风险极高，据此操作风险自负。
