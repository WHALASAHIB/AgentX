"""
Risk-Based Position Sizing Module
==================================
Extracted from the TradingAgents evaluation (Jun 26, 2026).
Council verdict: TradingAgents' risk is LLM-driven debate, not math formulas.
This module provides proper mathematical position sizing for MT5 bots.

Usage:
    from risk_sizing import calculate_position_size, validate_ftmo_limits
    
    lots = calculate_position_size(
        account_balance=9613.51,
        risk_percent=0.15,
        stop_loss_pips=12.0,
        symbol="EURUSD",
        method="fixed_pct"
    )
"""

from __future__ import annotations

import math
from typing import Literal

# ── Pip values per lot for forex pairs ────────────────────────────────────
PIP_VALUE_PER_LOT = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCHF": 9.0, "USDCAD": 8.0, "USDJPY": 9.0,  # approximate
    "XAUUSD": 100.0,  # 1 lot gold = $100 per $1 move (100 oz), pip=$10
    "BTCUSD": 1.0,    # 1 lot = 1 BTC
}

LOT_STEP = 0.01
MIN_LOT = 0.01
MAX_LOT = 50.0


def _get_pip_value(symbol: str) -> float:
    """Get approximate pip value in USD for one standard lot."""
    return PIP_VALUE_PER_LOT.get(symbol.upper(), 10.0)


def _round_lot(lot: float) -> float:
    """Round lot size to the broker's minimum step (0.01)."""
    return max(MIN_LOT, min(MAX_LOT, round(lot / LOT_STEP) * LOT_STEP))


def calculate_position_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_pips: float,
    symbol: str = "EURUSD",
    method: Literal["fixed_pct", "kelly", "equal_risk"] = "fixed_pct",
    kelly_win_rate: float = 0.55,
    kelly_avg_win_loss: float = 2.0,
) -> dict:
    """
    Calculate lot size using the specified method.
    
    Args:
        account_balance: Current account balance in USD
        risk_percent: Percentage of account to risk (e.g., 0.15 = 0.15%)
        stop_loss_pips: Stop loss distance in pips
        symbol: Trading symbol (for pip value lookup)
        method: Sizing method
        kelly_win_rate: Historical win rate (for Kelly method, 0.0-1.0)
        kelly_avg_win_loss: Average win/loss ratio (for Kelly method)
    
    Returns:
        dict with keys: lot_size, risk_amount, max_loss, method, symbol
    """
    risk_amount = account_balance * (risk_percent / 100.0)
    pip_value = _get_pip_value(symbol)
    
    if method == "kelly":
        # Kelly Criterion: f* = (p * b - q) / b
        # p = win probability, q = loss probability (1-p), b = win/loss ratio
        if kelly_avg_win_loss <= 0:
            kelly_pct = 0.01  # safety floor
        else:
            q = 1.0 - kelly_win_rate
            kelly_pct = (kelly_win_rate * kelly_avg_win_loss - q) / kelly_avg_win_loss
            kelly_pct = max(0.01, min(kelly_pct, 0.25))  # clamp 1%-25%
        
        risk_amount = account_balance * kelly_pct
        lot_size = risk_amount / (stop_loss_pips * pip_value) if stop_loss_pips > 0 else MIN_LOT
    
    elif method == "equal_risk":
        # Allocate risk evenly: risk / (SL_pips * pip_value)
        lot_size = risk_amount / (stop_loss_pips * pip_value) if stop_loss_pips > 0 else MIN_LOT
    
    else:  # fixed_pct (default)
        lot_size = risk_amount / (stop_loss_pips * pip_value) if stop_loss_pips > 0 else MIN_LOT
    
    lot_size = _round_lot(lot_size)
    max_loss = lot_size * stop_loss_pips * pip_value
    
    return {
        "lot_size": lot_size,
        "risk_amount": round(risk_amount, 2),
        "max_loss": round(max_loss, 2),
        "method": method,
        "symbol": symbol,
    }


def validate_ftmo_limits(
    account_balance: float,
    daily_loss: float,
    max_drawdown: float,
    proposed_lot: float,
    symbol: str = "EURUSD",
    price: float = 1.0,
    daily_loss_limit_pct: float = 5.0,
    max_drawdown_pct: float = 10.0,
) -> dict:
    """
    Validate a proposed trade against FTMO limits.
    
    Returns:
        dict with 'approved' (bool) and 'reason' (str)
    """
    pip_value = _get_pip_value(symbol)
    daily_remaining = (daily_loss_limit_pct / 100.0 * account_balance) - daily_loss
    dd_remaining = (max_drawdown_pct / 100.0 * account_balance) - max_drawdown
    
    trade_risk_value = proposed_lot * pip_value * price  # rough estimate
    
    issues = []
    if trade_risk_value > daily_remaining:
        issues.append(f"Trade risk ${trade_risk_value:.2f} exceeds daily remaining ${daily_remaining:.2f}")
    if trade_risk_value > dd_remaining:
        issues.append(f"Trade risk ${trade_risk_value:.2f} exceeds drawdown remaining ${dd_remaining:.2f}")
    
    return {
        "approved": len(issues) == 0,
        "reason": "; ".join(issues) if issues else "Passes all FTMO limits",
        "daily_remaining": round(daily_remaining, 2),
        "dd_remaining": round(dd_remaining, 2),
    }
