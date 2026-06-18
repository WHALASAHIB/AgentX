import random
from typing import Dict, Any

class OrderExecutionAgent:
    def __init__(self):
        self.name = "OrderExecutionAgent"

    def execute_order(self, symbol: str, direction: str, lot_size: float, price: float) -> Dict[str, Any]:
        """
        Simulates order routing and handles slippage checks.
        Returns execution details.
        """
        slippage = random.uniform(0.01, 0.15) if symbol == "XAUUSD" else random.uniform(0.00002, 0.00010)
        executed_price = price + slippage if direction == "BUY" else price - slippage
        
        # Simulating deal ticket
        ticket = random.randint(10000000, 99999999)
        
        return {
            "status": "FILLED",
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "volume": lot_size,
            "requested_price": round(price, 5),
            "executed_price": round(executed_price, 5),
            "slippage": round(slippage, 5),
            "execution_time_ms": random.randint(45, 180)
        }
