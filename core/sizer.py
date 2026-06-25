class PositionSizer:
    def __init__(self, settings):
        self.settings = settings

    def size_by_atr(
        self,
        atr: float,
        atr_stop_mult: float,
        equity: float,
        price: float,
        risk_multiplier: float = 1.0,
        risk_budget_override=None,
        available_margin: float = None,
        contract_multiplier: int = None,
    ) -> int:
        multiplier = contract_multiplier if contract_multiplier is not None else int(self.settings.get("contract_multiplier", 10))
        stop_distance = atr * atr_stop_mult
        risk_per_contract = stop_distance * multiplier
        try:
            risk_multiplier = max(0.0, min(1.0, float(risk_multiplier)))
        except (TypeError, ValueError):
            return 0
        if risk_per_contract <= 0 or equity <= 0 or price <= 0 or risk_multiplier <= 0:
            return 0

        fixed_risk = self.settings["risk_per_trade"] * risk_multiplier
        pct_risk = equity * self.settings.get("max_risk_pct", 0.005) * risk_multiplier
        risk_budget = min(fixed_risk, pct_risk)
        if risk_budget_override is not None:
            try:
                risk_budget = min(risk_budget, max(0.0, float(risk_budget_override)))
            except (TypeError, ValueError):
                return 0

        risk_size = int(risk_budget // risk_per_contract)
        margin_rate = self.settings.get("margin_rate", 0.12)
        margin_per_contract = price * multiplier * margin_rate
        effective_margin = available_margin if available_margin is not None else equity
        margin_size = int(effective_margin // margin_per_contract) if margin_per_contract > 0 else 0
        max_size = int(self.settings.get("max_position_size", risk_size))
        return max(0, min(risk_size, margin_size, max_size))
