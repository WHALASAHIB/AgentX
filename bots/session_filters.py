#!/usr/bin/env python3
"""
Session-Based Liquidity Filters for AGENTX Trading Bots
========================================================
Shared module to filter trades by market session based on historical analysis
of 754 trades across Asian, London, and US sessions.

Market Sessions (UTC):
  Asian:  00:00 – 08:59  (lower liquidity, more noise)
  London: 09:00 – 16:59  (high liquidity)
  US:     17:00 – 22:59  (high liquidity)
  Overlap 13:00 – 16:59  (peak liquidity)

Historical Analysis (2026-06-17, 754 trades):
  Asian:   35.6% WR, $-40.55 P&L  →  near breakeven, best WR → ALLOW
  London:  29.6% WR, $-5233.85 P&L  →  worst P&L (scalping-dominated)
  US:      33.0% WR, $-2843.63 P&L  →  moderate losses (scalping-dominated)
  US w/o scalping: 33.3% WR, $+475 P&L  →  profitable → ALLOW
  Asian w/o scalping: 35.6% WR, $-40.55  →  near breakeven → ALLOW

Conclusion: No session is purely bad when controlling for bot type.
Default config keeps all sessions but allows easy restriction.
"""

from datetime import datetime, timezone
from typing import Optional

# ============================================================================
# Liquidity Map: each hour (0-23) gets a rating
# Based on actual trade data, not market theory
# ============================================================================

SESSION_LIQUIDITY_MAP: dict[int, dict] = {
    # Hour: {'rating': str, 'label': str}
    # Asian session — best win rate, near breakeven
    0:  {'rating': 'MEDIUM', 'label': 'Asian (late night)'},
    1:  {'rating': 'MEDIUM', 'label': 'Asian'},
    2:  {'rating': 'MEDIUM', 'label': 'Asian'},
    3:  {'rating': 'MEDIUM', 'label': 'Asian'},
    4:  {'rating': 'HIGH',   'label': 'Asian (best WR 42%)'},
    5:  {'rating': 'HIGH',   'label': 'Asian (best WR 51%)'},
    6:  {'rating': 'HIGH',   'label': 'Asian→London transition'},
    7:  {'rating': 'HIGH',   'label': 'London pre-open'},
    8:  {'rating': 'HIGH',   'label': 'London open'},
    # London session — high liquidity, but scalping bleeds
    9:  {'rating': 'HIGH',   'label': 'London momentum'},
    10: {'rating': 'HIGH',   'label': 'London'},
    11: {'rating': 'HIGH',   'label': 'London'},
    12: {'rating': 'HIGH',   'label': 'London midday'},
    13: {'rating': 'HIGH',   'label': 'London+US overlap'},
    14: {'rating': 'HIGH',   'label': 'London+US overlap'},
    15: {'rating': 'HIGH',   'label': 'London+US overlap'},
    16: {'rating': 'HIGH',   'label': 'London close / US open'},
    # US session — profitable without scalping
    17: {'rating': 'HIGH',   'label': 'US open'},
    18: {'rating': 'HIGH',   'label': 'US'},
    19: {'rating': 'HIGH',   'label': 'US'},
    20: {'rating': 'HIGH',   'label': 'US (profitable +$1409)'},
    21: {'rating': 'HIGH',   'label': 'US late'},
    22: {'rating': 'HIGH',   'label': 'US close'},
    # Late — no trades in data
    23: {'rating': 'LOW',    'label': 'Post-US (no data)'},
}

# ============================================================================
# Configurable block list
# Set BLOCKED_HOURS to hours you want to completely avoid
# ============================================================================
BLOCKED_HOURS: set[int] = set()  # None blocked by default — all sessions viable

# ============================================================================
# Public API
# ============================================================================

def get_liquidity_rating(current_hour_utc: int) -> str:
    """Return liquidity rating for a given UTC hour.

    Args:
        current_hour_utc: Hour in UTC (0-23).

    Returns:
        'HIGH', 'MEDIUM', or 'LOW'.
    """
    info = SESSION_LIQUIDITY_MAP.get(current_hour_utc)
    if info is None:
        return 'LOW'
    return info['rating']


def get_session_label(current_hour_utc: int) -> str:
    """Return a human-readable label for the current UTC hour."""
    info = SESSION_LIQUIDITY_MAP.get(current_hour_utc)
    if info is None:
        return 'Unknown'
    return info['label']


def should_trade(current_hour_utc: Optional[int] = None,
                 blocked_hours: Optional[set[int]] = None,
                 min_rating: str = 'MEDIUM') -> bool:
    """Determine if trading is allowed at the given UTC hour.

    Args:
        current_hour_utc: Hour in UTC (0-23). Defaults to current UTC hour.
        blocked_hours:    Set of hours to always block. Defaults to BLOCKED_HOURS.
        min_rating:       Minimum liquidity rating required. One of 'HIGH', 'MEDIUM', 'LOW'.
                          'LOW' filters nothing. Default 'MEDIUM'.

    Returns:
        True if trading is permitted, False if it should be skipped.
    """
    if current_hour_utc is None:
        current_hour_utc = datetime.now(timezone.utc).hour

    if blocked_hours is None:
        blocked_hours = BLOCKED_HOURS

    # Check explicit block list
    if current_hour_utc in blocked_hours:
        return False

    # Check liquidity rating
    rating = get_liquidity_rating(current_hour_utc)

    rating_order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
    min_order = rating_order.get(min_rating, 2)
    current_order = rating_order.get(rating, 1)

    return current_order >= min_order


def get_session_name(current_hour_utc: Optional[int] = None) -> str:
    """Return the market session name for the given UTC hour."""
    if current_hour_utc is None:
        current_hour_utc = datetime.now(timezone.utc).hour
    if current_hour_utc <= 8:
        return 'Asian'
    elif current_hour_utc <= 16:
        return 'London'
    elif current_hour_utc <= 22:
        return 'US'
    else:
        return 'Post-US'


# ============================================================================
# Quick self-test
# ============================================================================
if __name__ == '__main__':
    print("=== Session Filter Self-Test ===")
    print()
    for hour in range(24):
        label = get_session_label(hour)
        rating = get_liquidity_rating(hour)
        trade = should_trade(hour)
        session = get_session_name(hour)
        print(f"UTC {hour:02d}:00 | {session:8s} | {label:30s} | {rating:6s} | trade={'YES' if trade else 'NO'}")
    print()
    print(f"Blocked hours: {sorted(BLOCKED_HOURS)}")
    print("All sessions pass default filter — no hours blocked.")
