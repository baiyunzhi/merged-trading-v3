class Account:
    def __init__(self, initial_equity: float):
        self.initial_equity = float(initial_equity)
        self.realized_pnl = 0.0
        self.commission_paid = 0.0

    def charge_commission(self, amount: float):
        self.commission_paid += amount
        self.realized_pnl -= amount

    def realize_trade_pnl(self, pnl_before_commission: float, exit_commission: float):
        self.realized_pnl += pnl_before_commission
        self.charge_commission(exit_commission)

    def equity(self, unrealized_pnl: float = 0.0) -> float:
        return self.initial_equity + self.realized_pnl + unrealized_pnl
