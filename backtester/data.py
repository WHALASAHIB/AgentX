"""
data.py — MT5 Historical Data Fetcher
======================================
Fetches real OHLC data from MetaTrader 5 for any symbol + timeframe + date range.
Exposes INSTRUMENTS metadata dict and fetch() function.
Gracefully handles MT5 connection failures — returns None if unavailable.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Instrument metadata ──────────────────────────────────────────────────────
# Matches research_division/strategy_innovation.py INSTRUMENTS
INSTRUMENTS: dict[str, dict] = {
    "XAUUSD": {"ticker": "XAUUSD", "spread_pips": 1.0, "pip_value": 0.01, "contract_size": 100},
    "EURUSD": {"ticker": "EURUSD", "spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "GBPUSD": {"ticker": "GBPUSD", "spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "USDJPY": {"ticker": "USDJPY", "spread_pips": 0.8, "pip_value": 0.01, "contract_size": 100000},
    "USDCHF": {"ticker": "USDCHF", "spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "USDCAD": {"ticker": "USDCAD", "spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "AUDUSD": {"ticker": "AUDUSD", "spread_pips": 1.2, "pip_value": 0.0001, "contract_size": 100000},
    "NZDUSD": {"ticker": "NZDUSD", "spread_pips": 1.5, "pip_value": 0.0001, "contract_size": 100000},
    "BTCUSD": {"ticker": "BTCUSD", "spread_pips": 10.0, "pip_value": 1.0, "contract_size": 1},
}

# ── MT5 Timeframe mapping ───────────────────────────────────────────────────
TIMEFRAME_MAP = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "H1": 60,
    "4h": 240,
    "H4": 240,
    "1d": 1440,
    "D1": 1440,
    "1w": 10080,
    "W1": 10080,
}

_MT5_AVAILABLE = None
_MT5_INITIALIZED = False


def _ensure_mt5() -> bool:
    """Lazy-initialize MT5. Returns True if connected, False otherwise."""
    global _MT5_AVAILABLE, _MT5_INITIALIZED
    if _MT5_INITIALIZED:
        return _MT5_AVAILABLE

    try:
        import MetaTrader5 as mt5
    except ImportError:
        logger.warning("MetaTrader5 package not installed.")
        _MT5_AVAILABLE = False
        _MT5_INITIALIZED = True
        return False

    if not mt5.initialize():
        err = mt5.last_error()
        logger.warning("MT5 initialize failed: %s", err)
        _MT5_AVAILABLE = False
        _MT5_INITIALIZED = True
        return False

    logger.info("MT5 initialized successfully.")
    _MT5_AVAILABLE = True
    _MT5_INITIALIZED = True
    return True


def _mt5_timeframe(interval: str) -> Optional[int]:
    """Convert a string interval (e.g. '1h', 'H1', 'D1') to an MT5 timeframe in minutes.
    Returns None if unknown, in which case caller should fall back to a default (e.g. H1).
    """
    tf = TIMEFRAME_MAP.get(interval)
    if tf is not None:
        return tf
    # Try to parse as integer minutes
    try:
        return int(interval)
    except (ValueError, TypeError):
        return None


def fetch(
    ticker: str,
    date_from: str,
    date_to: str,
    interval: str = "1h",
) -> Optional[object]:
    """Fetch OHLC data from MT5 for the given symbol and date range.

    Parameters
    ----------
    ticker : str
        MT5 symbol name, e.g. "XAUUSD", "EURUSD".
    date_from : str
        Start date in "YYYY-MM-DD" format.
    date_to : str
        End date in "YYYY-MM-DD" format.
    interval : str
        Timeframe string. Supports: 1m, 5m, 15m, 30m, 1h/H1, 4h/H4, 1d/D1, 1w/W1.
        Falls back to H1 if unrecognised.

    Returns
    -------
    pandas.DataFrame or None
        DataFrame with columns: time, open, high, low, close, tick_volume, spread, real_volume.
        Returns None if MT5 unavailable, symbol not found, or no data.
    """
    if not _ensure_mt5():
        return None

    import MetaTrader5 as mt5
    import pandas as pd

    tf_minutes = _mt5_timeframe(interval)
    if tf_minutes is None:
        logger.warning("Unknown interval %r, falling back to H1", interval)
        tf_minutes = 60  # H1 default

    # Map minutes to MT5 timeframe constant
    mt5_tf_map = {
        1: mt5.TIMEFRAME_M1,
        5: mt5.TIMEFRAME_M5,
        15: mt5.TIMEFRAME_M15,
        30: mt5.TIMEFRAME_M30,
        60: mt5.TIMEFRAME_H1,
        240: mt5.TIMEFRAME_H4,
        1440: mt5.TIMEFRAME_D1,
        10080: mt5.TIMEFRAME_W1,
    }
    mt5_tf = mt5_tf_map.get(tf_minutes, mt5.TIMEFRAME_H1)

    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        logger.error("Date parse error: %s", exc)
        return None

    # Check if symbol is available
    symbol_info = mt5.symbol_info(ticker)
    if symbol_info is None:
        logger.warning("Symbol %r not found on MT5.", ticker)
        return None

    # Ensure symbol is enabled for trading
    if not symbol_info.visible:
        if not mt5.symbol_select(ticker, True):
            logger.warning("Could not enable symbol %r on MT5.", ticker)
            return None

    rates = mt5.copy_rates_range(ticker, mt5_tf, dt_from, dt_to)
    if rates is None or len(rates) == 0:
        logger.warning("No data returned for %r %s [%s to %s]", ticker, interval, date_from, date_to)
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    logger.info(
        "Fetched %d bars for %r %s [%s to %s]",
        len(df), ticker, interval, date_from, date_to,
    )
    return df


def fetch_with_fallback(
    ticker: str,
    date_from: str,
    date_to: str,
    interval: str = "1h",
) -> Optional[object]:
    """Like fetch(), but returns None instead of raising on transient errors.
    Useful for optional data pipelines where MT5 may be offline.
    """
    try:
        return fetch(ticker, date_from, date_to, interval=interval)
    except Exception as exc:
        logger.error("fetch_with_fallback error for %r: %s", ticker, exc)
        return None
