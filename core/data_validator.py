import json
from pathlib import Path

import pandas as pd
import numpy as np


REQUIRED_COLUMNS = ["datetime", "symbol", "open", "high", "low", "close", "volume", "oi"]
PRICE_COLUMNS = ["open", "high", "low", "close"]

_MULTIPLIER_PATH = Path(__file__).resolve().parents[1] / "config" / "contract_multipliers.json"


class DataValidationError(ValueError):
    pass


def load_contract_multipliers() -> dict:
    if _MULTIPLIER_PATH.exists():
        data = json.loads(_MULTIPLIER_PATH.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items() if not k.startswith("_")}
    return {"default": 10}


class DataValidator:
    def __init__(self, multipliers: dict = None):
        self._multipliers = multipliers if multipliers is not None else load_contract_multipliers()

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing:
            raise DataValidationError(f"missing columns: {missing}")

        df = df.copy()
        df["datetime"] = pd.to_datetime(df["datetime"], errors="raise")
        df = df.sort_values(["datetime", "symbol"]).reset_index(drop=True)

        if df[["datetime", "symbol"]].duplicated().any():
            raise DataValidationError("duplicated symbol/datetime rows")

        for col in PRICE_COLUMNS + ["volume", "oi"]:
            df[col] = pd.to_numeric(df[col], errors="raise")

        numeric_cols = PRICE_COLUMNS + ["volume", "oi"]
        if df[numeric_cols].isna().any().any():
            raise DataValidationError("numeric columns contain NaN")
        if not np.isfinite(df[numeric_cols].to_numpy(dtype=float)).all():
            raise DataValidationError("numeric columns contain infinite values")
        if (df[PRICE_COLUMNS] <= 0).any().any():
            raise DataValidationError("price must be positive")
        if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
            raise DataValidationError("high is lower than open/close/low")
        if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
            raise DataValidationError("low is higher than open/close/high")
        if (df[["volume", "oi"]] < 0).any().any():
            raise DataValidationError("volume/oi must be non-negative")

        # 注入合约乘数：优先用数据中已有的字段，否则按品种配置，再fallback到default
        if "contract_multiplier" not in df.columns:
            default_mult = self._multipliers.get("default", 10)
            df["contract_multiplier"] = df["symbol"].map(
                lambda s: self._multipliers.get(s, default_mult)
            )
        else:
            df["contract_multiplier"] = pd.to_numeric(df["contract_multiplier"], errors="coerce").fillna(
                df["symbol"].map(lambda s: self._multipliers.get(s, self._multipliers.get("default", 10)))
            ).astype(int)

        df["datetime"] = df["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S").str.replace(" 00:00:00", "", regex=False)
        return df
