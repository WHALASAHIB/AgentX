from typing import Dict, Any

class RiskManagementAgent:
    def __init__(self):
        self.name = "RiskManagementAgent"

    def validate_trade(self, symbol: str, lot_size: float, current_drawdown: float, max_drawdown_limit: float) -> tuple[bool, str]:
        """
        Validates whether a trade is allowed based on risk parameters.
        Returns (is_valid, reason).
        """
        if current_drawdown >= max_drawdown_limit:
            return False, f"Maximum daily drawdown of {max_drawdown_limit}% breached. Drawdown: {current_drawdown:.2f}%"
        
        if lot_size <= 0:
            return False, "Invalid lot size: must be greater than zero."
            
        if lot_size > 5.0: # Cap at 5.0 lots for safety
            return False, f"Lot size {lot_size} exceeds maximum safe limit of 5.0 lots."
            
        return True, "Risk validation passed."
