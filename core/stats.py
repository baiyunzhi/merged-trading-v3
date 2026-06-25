import pandas as pd


class StatsEngine:
    def __init__(self, trades, equity_curve=None, initial_equity=0):
        self.df = pd.DataFrame(trades)
        self.equity = pd.DataFrame(equity_curve or [])
        self.initial_equity = float(initial_equity)

    def summary(self):
        base = {
            "total_trades": 0,
            "net_profit": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "max_drawdown": 0,
            "max_drawdown_pct": 0,
            "expectancy": 0,
            "final_equity": round(self._final_equity(), 2),
        }
        if self.df.empty:
            return base

        pnl = self.df["pnl"]
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        gross_win = wins.sum()
        gross_loss = abs(losses.sum())
        max_dd, max_dd_pct = self.max_drawdown()

        return {
            "total_trades": int(len(self.df)),
            "net_profit": round(float(pnl.sum()), 2),
            "win_rate": round(float((pnl > 0).mean()), 4),
            "avg_win": round(float(wins.mean()), 2) if len(wins) else 0,
            "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0,
            "profit_factor": round(float(gross_win / gross_loss), 4) if gross_loss else float("inf"),
            "max_drawdown": round(float(max_dd), 2),
            "max_drawdown_pct": round(float(max_dd_pct), 6),
            "expectancy": round(float(pnl.mean()), 2),
            "best_trade": round(float(pnl.max()), 2),
            "worst_trade": round(float(pnl.min()), 2),
            "final_equity": round(self._final_equity(), 2),
        }

    def max_drawdown(self):
        if self.equity.empty or "equity" not in self.equity:
            return 0, 0
        equity = self.equity["equity"].astype(float)
        peak = equity.cummax()
        dd = equity - peak
        dd_pct = dd / peak.replace(0, pd.NA)
        return dd.min(), dd_pct.min()

    def _final_equity(self):
        if self.equity.empty or "equity" not in self.equity:
            return self.initial_equity
        return float(self.equity["equity"].iloc[-1])
