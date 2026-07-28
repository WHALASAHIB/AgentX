#!/usr/bin/env python3
"""
Data Cache — MT5 data fetcher.
Direct fetch per timeframe (no M1 resampling needed).
3-year depth achieved on M15+ timeframes via MT5 maxbars limit.

MT5 maxbars = 100,000 bars per call.
Expected depth:
  M5:  100K bars = ~347 days
  M15: 100K bars = ~2.85 years  ← minimum 3-year target
  H1:  100K bars = ~11.4 years
  H4:  100K bars = ~45.6 years
  D1:  100K bars = ~273 years
"""

from __future__ import annotations
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import MetaTrader5 as mt5

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE_DIR = os.path.join(BASE_DIR, "state")
CACHE_DIR = os.path.join(STATE_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

logger = logging.getLogger("data_cache")

# Timeframes to scan (M1 skipped — only 69 days depth)
TIMEFRAMES_MT5 = {
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}

TIMEFRAME_NAMES = list(TIMEFRAMES_MT5.keys())

# Minimum bars for meaningful analysis
MIN_BARS = {
    "M5": 200,
    "M15": 150,
    "H1": 100,
    "H4": 50,
    "D1": 30,
}

# Expected bars from 100K max
EXPECTED_BARS = {
    "M5":  100000,
    "M15": 100000,
    "H1":  100000,
    "H4":  100000,
    "D1":  100000,
}

# Rotation order
ROTATION = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF",
            "USDCAD", "AUDUSD", "NZDUSD", "XAUUSD"]

# Bar data type
DTYPE_BAR = np.dtype([
    ("time", "i8"),
    ("open", "f8"),
    ("high", "f8"),
    ("low", "f8"),
    ("close", "f8"),
    ("tick_volume", "i8"),
    ("spread", "i4"),
    ("real_volume", "i8"),
])


# ============================================================================
# MT5 Connection
# ============================================================================

def init_mt5() -> bool:
    """Initialize MT5 terminal connection."""
    return mt5.initialize()


def fetch_bars(symbol: str, tf_name: str) -> Optional[np.ndarray]:
    """
    Fetch bars from MT5 for a symbol+timeframe.
    Uses copy_rates_from_pos with maxbars limit.
    """
    if not init_mt5():
        logger.warning("MT5 init failed: %s", mt5.last_error())
        return None

    tf = TIMEFRAMES_MT5.get(tf_name)
    if tf is None:
        logger.error("Unknown timeframe: %s", tf_name)
        return None

    # Fetch with maxbars limit
    max_fetch = 99999  # MT5 maxbars=100000 but count must be < 100000
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, max_fetch)

    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        logger.warning("No %s data for %s (error: %s)", tf_name, symbol, err)
        return None

    arr = np.array(rates, dtype=DTYPE_BAR)
    n = len(arr)

    # Calculate date range
    first_dt = datetime.fromtimestamp(arr["time"][0], tz=timezone.utc)
    last_dt = datetime.fromtimestamp(arr["time"][-1], tz=timezone.utc)
    span_days = (last_dt - first_dt).days

    logger.info("Fetched %s %s: %d bars | %s → %s (%d days)",
                symbol, tf_name, n,
                first_dt.strftime("%Y-%m-%d"),
                last_dt.strftime("%Y-%m-%d"),
                span_days)

    return arr


# ============================================================================
# Caching
# ============================================================================

def cache_path(symbol: str, timeframe: str) -> str:
    return os.path.join(CACHE_DIR, f"{symbol}_{timeframe}.npy")


def save_cache(symbol: str, timeframe: str, data: np.ndarray) -> None:
    path = cache_path(symbol, timeframe)
    np.save(path, data)
    logger.debug("Cached %s %s: %d bars", symbol, timeframe, len(data))


def load_cache(symbol: str, timeframe: str) -> Optional[np.ndarray]:
    path = cache_path(symbol, timeframe)
    if not os.path.exists(path):
        return None
    data = np.load(path)
    logger.debug("Loaded %s %s from cache: %d bars", symbol, timeframe, len(data))
    return data


# ============================================================================
# Main data loader
# ============================================================================

def get_data(symbol: str, timeframe: str = "H1",
             max_age_hours: int = 1, force_refresh: bool = False) -> Optional[np.ndarray]:
    """
    Get OHLCV data for a symbol+timeframe.
    Cached locally. Refetches if cache is stale.
    """
    assert timeframe in TIMEFRAME_NAMES, f"Invalid timeframe: {timeframe}"

    # Check cache first
    if not force_refresh:
        cached = load_cache(symbol, timeframe)
        if cached is not None:
            # Check age
            mtime = os.path.getmtime(cache_path(symbol, timeframe))
            age_hours = (time.time() - mtime) / 3600
            if age_hours < max_age_hours and len(cached) >= MIN_BARS.get(timeframe, 100):
                return cached
            logger.info("Cache for %s %s is %.1fh old — refetching",
                        symbol, timeframe, age_hours)

    # Fetch fresh
    data = fetch_bars(symbol, timeframe)
    if data is not None and len(data) > 0:
        save_cache(symbol, timeframe, data)
    return data


# ============================================================================
# Rotation
# ============================================================================

def get_next_pair() -> str:
    """Determine which pair to scan this run based on current hour."""
    hour = datetime.now(timezone.utc).hour + 8  # HKT
    session_slots = [7, 13, 19, 1]
    current_slot = None
    for slot in session_slots:
        if hour >= slot:
            current_slot = slot
    if current_slot is None:
        current_slot = 1
    slot_index = session_slots.index(current_slot)
    pair_index = slot_index % len(ROTATION)
    return ROTATION[pair_index]


# ============================================================================
# Summary
# ============================================================================

def print_data_summary(data: Optional[np.ndarray], symbol: str, timeframe: str) -> None:
    """Print data summary line."""
    if data is None or len(data) == 0:
        print(f"  {symbol} {timeframe}: ❌ NO DATA")
        return

    n = len(data)
    first = datetime.fromtimestamp(data["time"][0], tz=timezone.utc)
    last = datetime.fromtimestamp(data["time"][-1], tz=timezone.utc)
    span = (last - first).days
    years = span / 365.25

    print(f"  {symbol} {timeframe}: ✅ {n:,} bars | "
          f"{first.strftime('%Y-%m-%d')} → {last.strftime('%Y-%m-%d')} "
          f"({span}d = {years:.1f}y) | "
          f"${data['close'][0]:.5f} → ${data['close'][-1]:.5f}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    pair = get_next_pair()
    print(f"Next pair: {pair}")
    for tf in TIMEFRAME_NAMES:
        d = get_data(pair, tf)
        print_data_summary(d, pair, tf)
