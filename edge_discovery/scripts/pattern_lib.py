#!/usr/bin/env python3
"""
Pattern Library — candlestick patterns, session effects, day-of-week patterns.
"""

from __future__ import annotations
import numpy as np
from datetime import datetime, timezone
from typing import Callable, Dict, List, Tuple


# ============================================================================
# Candlestick Pattern Detection
# ============================================================================

def detect_doji(open_p: np.ndarray, high: np.ndarray, low: np.ndarray,
                close: np.ndarray) -> np.ndarray:
    """
    Doji: open ≈ close, small body relative to range.
    Returns 1 (possible reversal) or 0.
    """
    body = np.abs(close - open_p)
    range_p = high - low
    doji_size = np.maximum(range_p * 0.05, 0.0001)  # 5% of range or 0.1 pip
    result = np.zeros(len(open_p), dtype=int)
    result[(body < doji_size) & (range_p > 0)] = 1
    return result


def detect_engulfing(open_p: np.ndarray, high: np.ndarray, low: np.ndarray,
                     close: np.ndarray) -> np.ndarray:
    """
    Bullish/Bearish Engulfing: current body fully engulfs previous body.
    Returns: 1 = bullish engulfing, -1 = bearish engulfing, 0 = none
    """
    result = np.zeros(len(open_p), dtype=int)
    if len(open_p) < 2:
        return result

    prev_body = np.abs(close[:-1] - open_p[:-1])
    curr_body = np.abs(close[1:] - open_p[1:])

    # Bullish: green engulfs previous red
    bullish = (close[1:] > open_p[1:]) & (close[:-1] < open_p[:-1]) & \
              (close[1:] > open_p[:-1]) & (open_p[1:] < close[:-1])
    # Bearish: red engulfs previous green
    bearish = (close[1:] < open_p[1:]) & (close[:-1] > open_p[:-1]) & \
              (close[1:] < open_p[:-1]) & (open_p[1:] > close[:-1])

    result[1:][bullish] = 1
    result[1:][bearish] = -1
    return result


def detect_hammer(open_p: np.ndarray, high: np.ndarray, low: np.ndarray,
                  close: np.ndarray) -> np.ndarray:
    """
    Hammer: small body at top, long lower wick (≥ 2× body).
    Returns 1 for bullish hammer, -1 for shooting star.
    """
    result = np.zeros(len(open_p), dtype=int)
    body = np.abs(close - open_p)
    lower_wick = np.minimum(open_p, close) - low
    upper_wick = high - np.maximum(open_p, close)
    total_range = high - low

    min_body = total_range * 0.05
    valid = (body >= min_body) & (total_range > 0)

    # Hammer: small body in upper half, long lower wick
    hammer = valid & (lower_wick >= 2 * body) & (upper_wick <= body * 0.5)
    result[hammer] = 1

    # Shooting Star: small body in lower half, long upper wick
    shooting_star = valid & (upper_wick >= 2 * body) & (lower_wick <= body * 0.5)
    result[shooting_star] = -1

    return result


def detect_harami(open_p: np.ndarray, high: np.ndarray, low: np.ndarray,
                  close: np.ndarray) -> np.ndarray:
    """
    Harami: current body inside previous body (opposite color).
    Returns 1 (bullish harami) or -1 (bearish harami).
    """
    result = np.zeros(len(open_p), dtype=int)
    if len(open_p) < 2:
        return result

    prev_open = open_p[:-1]
    prev_close = close[:-1]
    curr_open = open_p[1:]
    curr_close = close[1:]

    prev_bull = prev_close > prev_open
    curr_bull = curr_close > curr_open

    prev_body_top = np.maximum(prev_open, prev_close)
    prev_body_bot = np.minimum(prev_open, prev_close)
    curr_body_top = np.maximum(curr_open, curr_close)
    curr_body_bot = np.minimum(curr_open, curr_close)

    # Bearish harami: green body inside red body (reversal down)
    bearish = prev_bull & ~curr_bull & \
              (curr_body_top <= prev_body_top) & (curr_body_bot >= prev_body_bot)
    # Bullish harami: red body inside green body (reversal up)
    bullish = ~prev_bull & curr_bull & \
              (curr_body_top <= prev_body_top) & (curr_body_bot >= prev_body_bot)

    result[1:][bullish] = 1
    result[1:][bearish] = -1
    return result


def detect_pin_bar(open_p: np.ndarray, high: np.ndarray, low: np.ndarray,
                   close: np.ndarray) -> np.ndarray:
    """
    Pin Bar / Rejection: one wick ≥ 3× body, other wick tiny.
    Returns 1 (bullish rejection), -1 (bearish rejection).
    """
    result = np.zeros(len(open_p), dtype=int)
    body = np.abs(close - open_p)
    lower_wick = np.minimum(open_p, close) - low
    upper_wick = high - np.maximum(open_p, close)
    total_range = high - low

    min_body = total_range * 0.02
    valid = (body >= min_body) & (total_range > 0)

    # Bullish pin: long lower wick
    bullish_pin = valid & (lower_wick >= 3 * body) & (upper_wick <= body)
    result[bullish_pin] = 1

    # Bearish pin: long upper wick
    bearish_pin = valid & (upper_wick >= 3 * body) & (lower_wick <= body)
    result[bearish_pin] = -1

    return result


def detect_inside_bar(open_p: np.ndarray, high: np.ndarray, low: np.ndarray,
                      close: np.ndarray) -> np.ndarray:
    """
    Inside Bar: current range inside previous range.
    Returns 1 (inside bar formed — potential breakout setup).
    """
    result = np.zeros(len(open_p), dtype=int)
    if len(open_p) < 2:
        return result

    inside = (high[1:] <= high[:-1]) & (low[1:] >= low[:-1])
    result[1:][inside] = 1
    return result


def detect_morning_evening_star(open_p: np.ndarray, high: np.ndarray,
                                 low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """
    Morning Star (3-bar bullish reversal) / Evening Star (bearish reversal).
    Pattern: long red/green → small body → long green/red
    Returns 1 (morning star) or -1 (evening star).
    """
    result = np.zeros(len(open_p), dtype=int)
    if len(open_p) < 3:
        return result

    body = np.abs(close - open_p)
    avg_body = np.mean(body[body > 0]) if np.any(body > 0) else 0.001

    for i in range(2, len(open_p)):
        b1, b2, b3 = body[i - 2], body[i - 1], body[i]
        c1, c2, c3 = close[i - 2], close[i - 1], close[i]
        o1, o2, o3 = open_p[i - 2], open_p[i - 1], open_p[i]

        # Morning Star: bear → small → bull (reversal up)
        if (c1 < o1 and b1 > avg_body * 0.5 and
                b2 < avg_body * 0.5 and
                c3 > o3 and b3 > avg_body * 0.5 and
                c2 < o1 and c3 > (o1 + c1) / 2):
            result[i] = 1

        # Evening Star: bull → small → bear (reversal down)
        elif (c1 > o1 and b1 > avg_body * 0.5 and
              b2 < avg_body * 0.5 and
              c3 < o3 and b3 > avg_body * 0.5 and
              c2 > o1 and c3 < (o1 + c1) / 2):
            result[i] = -1

    return result


def detect_breakout(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                    period: int = 20) -> np.ndarray:
    """
    Breakout: close above recent high range or below recent low range.
    Returns 1 (breakout up) or -1 (breakout down).
    """
    result = np.zeros(len(close), dtype=int)
    hh = np.full_like(close, np.nan)
    ll = np.full_like(close, np.nan)

    for i in range(period, len(close)):
        hh[i] = np.max(high[i - period + 1:i + 1])
        ll[i] = np.min(low[i - period + 1:i + 1])

    valid = ~(np.isnan(hh) | np.isnan(ll))
    result[valid & (close > hh)] = 1
    result[valid & (close < ll)] = -1
    return result


# ============================================================================
# Session & Calendar Patterns
# ============================================================================

def session_times(timestamps: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Classify each bar into trading session based on timestamp.
    Timestamps are unix seconds (UTC).
    Sessions:
      - Asian: 00:00-09:00 HKT = 16:00-01:00 UTC (previous/current day)
      - London: 09:00-17:00 HKT = 01:00-09:00 UTC (summer) / 02:00-10:00 UTC (winter)
      - US: 17:00-02:00 HKT = 09:00-18:00 UTC (summer) / 10:00-19:00 UTC (winter)
      - Overlap: 17:00-17:00? Actually various overlaps
    Simplified UTC-based approach.
    """
    asian = np.zeros(len(timestamps), dtype=bool)
    london = np.zeros(len(timestamps), dtype=bool)
    us = np.zeros(len(timestamps), dtype=bool)
    london_us_overlap = np.zeros(len(timestamps), dtype=bool)

    for i, ts in enumerate(timestamps):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour = dt.hour
        minute = dt.minute
        hour_dec = hour + minute / 60

        # Asian: 22:00-08:00 UTC (next day's Asian open)
        if hour_dec >= 22 or hour_dec < 8:
            asian[i] = True
        # London: 07:00-16:00 UTC
        if 7 <= hour_dec < 16:
            london[i] = True
        # US: 13:00-22:00 UTC
        if 13 <= hour_dec < 22:
            us[i] = True
        # London-US overlap: 13:00-16:00 UTC
        if 13 <= hour_dec < 16:
            london_us_overlap[i] = True

    return {
        "asian": asian,
        "london": london,
        "us": us,
        "london_us_overlap": london_us_overlap,
    }


def day_of_week(timestamps: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Classify bars by day of week.
    Returns boolean masks for Mon-Fri.
    Monday = 0, Sunday = 6.
    """
    days = {
        "monday": np.zeros(len(timestamps), dtype=bool),
        "tuesday": np.zeros(len(timestamps), dtype=bool),
        "wednesday": np.zeros(len(timestamps), dtype=bool),
        "thursday": np.zeros(len(timestamps), dtype=bool),
        "friday": np.zeros(len(timestamps), dtype=bool),
    }

    dow_names = ["monday", "tuesday", "wednesday", "thursday", "friday",
                 "saturday", "sunday"]

    for i, ts in enumerate(timestamps):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        dow = dt.weekday()  # 0=Mon
        if dow < 5:  # Mon-Fri
            days[dow_names[dow]][i] = True

    return days


# ============================================================================
# Pattern Signal Generator (unified)
# ============================================================================

def compute_pattern_signals(open_p: np.ndarray, high: np.ndarray,
                             low: np.ndarray, close: np.ndarray,
                             volume: np.ndarray, timestamps: np.ndarray,
                             params: dict) -> np.ndarray:
    """
    Compute all pattern-based signals. 
    Combines candle patterns, session effects, day-of-week.
    Returns combined signal array: -1, 0, 1 per bar.
    """
    pattern_type = params.get("pattern", "all")
    signals = np.zeros(len(close), dtype=int)

    # Candlestick patterns
    if pattern_type in ("all", "doji"):
        doji = detect_doji(open_p, high, low, close)
        signals[doji > 0] = 1  # Doji signals reversal possibility

    if pattern_type in ("all", "engulfing"):
        engulf = detect_engulfing(open_p, high, low, close)
        signals[engulf == 1] = 1
        signals[engulf == -1] = -1

    if pattern_type in ("all", "hammer"):
        hammer = detect_hammer(open_p, high, low, close)
        signals[hammer == 1] = 1
        signals[hammer == -1] = -1

    if pattern_type in ("all", "harami"):
        harami = detect_harami(open_p, high, low, close)
        signals[harami == 1] = 1
        signals[harami == -1] = -1

    if pattern_type in ("all", "pinbar"):
        pin = detect_pin_bar(open_p, high, low, close)
        signals[pin == 1] = 1
        signals[pin == -1] = -1

    if pattern_type in ("all", "insidebar"):
        inside = detect_inside_bar(open_p, high, low, close)
        # Inside bar is neutral — wait for breakout
        # signals[inside > 0] = 1

    if pattern_type in ("all", "star"):
        star = detect_morning_evening_star(open_p, high, low, close)
        signals[star == 1] = 1
        signals[star == -1] = -1

    if pattern_type in ("all", "breakout"):
        bp = params.get("breakout_period", 20)
        breakout = detect_breakout(high, low, close, bp)
        signals[breakout == 1] = 1
        signals[breakout == -1] = -1

    # Session/calendar patterns are tested differently (stat accuracy by segment)
    # Not emitted as direct signals — instead the scanner tests each segment's WR
    return signals


# ============================================================================
# Pattern Registry (for scanner integration)
# ============================================================================

PATTERN_REGISTRY = {
    "Candle_Doji": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "doji"}),
        "params": [{}],
        "description": "Doji candle — indecision, potential reversal",
        "family": "pattern",
    },
    "Candle_Engulfing": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "engulfing"}),
        "params": [{}],
        "description": "Engulfing pattern — strong reversal",
        "family": "pattern",
    },
    "Candle_Hammer": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "hammer"}),
        "params": [{}],
        "description": "Hammer/Shooting Star — rejection reversal",
        "family": "pattern",
    },
    "Candle_Harami": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "harami"}),
        "params": [{}],
        "description": "Harami — trend weakening",
        "family": "pattern",
    },
    "Candle_PinBar": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "pinbar"}),
        "params": [{}],
        "description": "Pin Bar — strong rejection wick",
        "family": "pattern",
    },
    "Candle_Star": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "star"}),
        "params": [{}],
        "description": "Morning/Evening Star — 3-bar reversal",
        "family": "pattern",
    },
    "Breakout": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "breakout", "breakout_period": p.get("period", 20)}),
        "params": [{"period": 10}, {"period": 20}, {"period": 50}],
        "description": "Breakout from recent range",
        "family": "pattern",
    },
    "InsideBar_Breakout": {
        "func": lambda o, h, l, c, v, t, p: compute_pattern_signals(o, h, l, c, v, t, {"pattern": "insidebar"}),
        "params": [{}],
        "description": "Inside bar — volatility compression",
        "family": "pattern",
    },
}

# Total pattern combos
PATTERN_COMBOS = sum(len(v["params"]) for v in PATTERN_REGISTRY.values())
