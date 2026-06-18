from typing import Dict, Any

class PortfolioAllocatorAgent:
    def __init__(self):
        self.name = "PortfolioAllocatorAgent"

    def calculate_allocation(self, total_balance: float, active_symbols: list) -> Dict[str, Any]:
        """
        Determines capital allocation percentages for the portfolio.
        Returns target allocations and absolute risk amounts.
        """
        if not active_symbols:
            return {"allocations": {}, "status": "EMPTY"}
            
        weight = 1.0 / len(active_symbols)
        allocations = {}
        for sym in active_symbols:
            allocations[sym] = {
                "target_weight_pct": round(weight * 100, 2),
                "allocated_capital": round(total_balance * weight, 2),
                "max_risk_amount": round(total_balance * weight * 0.01, 2) # 1% risk per symbol allocation
            }
            
        return {
            "allocations": allocations,
            "status": "BALANCED",
            "total_monitored": len(active_symbols)
        }
