"""
数据中枢 data_hub — 双通道

csv     : 历史 CSV（33品种多年日线）→ 严谨回测（默认，可复现）
akshare : 实时拉取主力合约 → 盯盘/选品；失败回退仿真数据

统一输出标准列：datetime, symbol, open, high, low, close, volume, oi, contract_multiplier
"""
import json
import time
import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger("data_hub")


# ── 品种名 / 板块映射（来自 china_commodity_pool.json）─────────────────────

def load_symbol_maps() -> tuple[dict, dict]:
    pool = ROOT / "config" / "china_commodity_pool.json"
    name_map, sector_map = {}, {}
    if pool.exists():
        data = json.loads(pool.read_text(encoding="utf-8"))
        for item in data.get("symbols", []):
            name_map[item["symbol"]] = item.get("name", item["symbol"])
            sector_map[item["symbol"]] = item.get("sector", "其他")
    return name_map, sector_map


# ── 通道一：历史 CSV ────────────────────────────────────────────────────────

def load_history_csv(settings: dict) -> pd.DataFrame:
    """加载历史CSV并校验，复用 core.data_validator（含合约乘数注入）。"""
    from core.data_validator import DataValidator
    path = ROOT / settings["data_path"]
    logger.info(f"[CSV] 加载 {path}")
    df = pd.read_csv(path)
    df = DataValidator().validate(df)
    return df


def history_to_symbol_dict(df: pd.DataFrame) -> dict:
    """长表 → {symbol: df}，列名转小写标准，供选品/绘图。"""
    out = {}
    for sym, g in df.groupby("symbol", sort=False):
        g = g.copy()
        g["date"] = pd.to_datetime(g["datetime"])
        out[sym] = g.sort_values("date").reset_index(drop=True)
    return out


# ── 通道二：akshare 实时（失败回退仿真）───────────────────────────────────

CACHE_DIR = ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PRICE_ANCHORS = {
    "RB0": 3800, "HC0": 3900, "I0": 800, "J0": 2200, "JM0": 1700,
    "CU0": 68000, "AL0": 18500, "ZN0": 22000, "NI0": 130000,
    "M0": 3200, "Y0": 8200, "C0": 2400, "SR0": 6200, "CF0": 15000,
}


def _fetch_akshare(symbol: str) -> pd.DataFrame | None:
    try:
        import akshare as ak
        df = ak.futures_zh_daily_sina(symbol=symbol)
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "date": "date", "open": "open", "high": "high", "low": "low",
            "close": "close", "volume": "volume", "hold": "oi", "持仓量": "oi",
        })
        df["date"] = pd.to_datetime(df["date"])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        if "oi" not in df.columns:
            df["oi"] = 0
        return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    except Exception as e:
        logger.warning(f"akshare 获取 {symbol} 失败: {e}")
        return None


def _simulate(symbol: str, days: int = 500) -> pd.DataFrame:
    np.random.seed(hash(symbol) % (2**31))
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=days)
    base = PRICE_ANCHORS.get(symbol, 5000)
    trend = np.random.choice([-1, 0, 1], p=[0.3, 0.2, 0.5])
    rets = np.random.randn(days) * 0.012 + trend * 0.0018 + 0.02 * np.sin(np.arange(days) / 30)
    close = base * np.cumprod(1 + rets)
    high = close * (1 + np.abs(np.random.randn(days)) * 0.006)
    low = close * (1 - np.abs(np.random.randn(days)) * 0.006)
    op = np.roll(close, 1) * (1 + np.random.randn(days) * 0.002); op[0] = base
    return pd.DataFrame({
        "date": dates, "open": np.round(op), "high": np.round(high),
        "low": np.round(low), "close": np.round(close),
        "volume": np.random.randint(50000, 500000, days).astype(float),
        "oi": np.random.randint(50000, 500000, days).astype(float),
        "is_simulated": True,
    })


def get_realtime_data(settings: dict, use_cache: bool = True) -> dict:
    """实时通道：拉取所有品种，返回 {symbol: df}（含指标前的原始OHLCV）。"""
    name_map, _ = load_symbol_maps()
    cache_hours = settings.get("akshare_cache_hours", 4)
    days = settings.get("akshare_lookback_days", 500)
    out = {}
    for sym in name_map:
        cache = CACHE_DIR / f"{sym}.parquet"
        if use_cache and cache.exists() and (time.time() - cache.stat().st_mtime) / 3600 < cache_hours:
            out[sym] = pd.read_parquet(cache)
            continue
        df = _fetch_akshare(sym)
        if df is None or len(df) < 60:
            df = _simulate(sym, days)
        else:
            df["is_simulated"] = False
        try:
            df.to_parquet(cache, index=False)
        except Exception:
            pass
        out[sym] = df
    return out


# ── 统一入口 ────────────────────────────────────────────────────────────────

def load_for_backtest(settings: dict) -> pd.DataFrame:
    """回测用：始终走历史CSV长表（严谨、可复现）。"""
    return load_history_csv(settings)
