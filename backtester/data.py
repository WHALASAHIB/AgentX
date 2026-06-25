"""
data.py — MT5 Historical Data Fetcher
======================================
Fetches real OHLC data from MetaTrader 5 for any symbol + timeframe + date range.
Exposes INSTRUMENTS metadata dict and fetch() function.
Gracefully handles MT5 connection failures — returns None if unavailable.
Falls back to synthetic data when MT5 is offline or returns 0 bars.
"""

import json
import logging
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Instrument metadata ──────────────────────────────────────────────────────
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
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "H1": 60, "4h": 240, "H4": 240,
    "1d": 1440, "D1": 1440, "1w": 10080, "W1": 10080,
}

# ── Base prices for synthetic fallback (approximate real levels) ───────────
_BASE_PRICES = {
    "XAUUSD": 2330.0, "EURUSD": 1.0850, "GBPUSD": 1.2700,
    "USDJPY": 156.50, "USDCHF": 0.8950, "USDCAD": 1.3650,
    "AUDUSD": 0.6650, "NZDUSD": 0.6100, "BTCUSD": 65000.0,
}

_MT5_AVAILABLE = None
_MT5_INITIALIZED = False


def _load_mt5_config() -> dict:
    """Load MT5 credentials from mt5_config.json."""
    config_path = Path(__file__).resolve().parent.parent / "mt5_config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception:
        return {}


def _ensure_mt5() -> bool:
    """Lazy-initialize MT5 with credentials. Returns True if connected."""
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

    # Try with credentials first
    cfg = _load_mt5_config()
    init_kw = {}
    terminal_path = cfg.get("terminal_path", "")
    if terminal_path:
        init_kw["path"] = terminal_path
    login = cfg.get("login")
    password = cfg.get("password")
    server = cfg.get("server")
    if login and password and server:
        init_kw["login"] = int(login)
        init_kw["password"] = str(password)
        init_kw["server"] = str(server)
        init_kw["timeout"] = 30000

    if not mt5.initialize(**init_kw):
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
    """Convert a string interval to minutes. Returns None if unknown."""
    tf = TIMEFRAME_MAP.get(interval)
    if tf is not None:
        return tf
    try:
        return int(interval)
    except (ValueError, TypeError):
        return None


def _generate_synthetic_data(
    ticker: str,
    date_from: str,
    date_to: str,
    interval: str = "1h",
    min_bars: int = 60,
) -> Optional[object]:
    """
    Generate realistic synthetic OHLC data when MT5 is unavailable.
    Creates a random walk from the base price with realistic volatility.
    """
    base_price = _BASE_PRICES.get(ticker, 100.0)
    tf_minutes = _mt5_timeframe(interval) or 60

    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    total_minutes = (dt_to - dt_from).total_seconds() / 60
    num_bars = max(min_bars, int(total_minutes / max(tf_minutes, 1)))

    if num_bars > 20000:
        num_bars = 20000

    # Volatility per bar based on asset type
    if ticker == "BTCUSD":
        volatility = base_price * 0.015  # 1.5% per bar (crypto)
    elif ticker in ("XAUUSD",):
        volatility = base_price * 0.003  # 0.3% per bar (gold)
    else:
        volatility = base_price * 0.001  # 0.1% per bar (forex)

    price = base_price
    records = []
    current_time = dt_from

    for _ in range(num_bars):
        change = random.gauss(0, volatility)
        open_price = price
        close_price = price + change
        high_price = max(open_price, close_price) + abs(random.gauss(0, volatility * 0.5))
        low_price = min(open_price, close_price) - abs(random.gauss(0, volatility * 0.5))
        volume = random.randint(100, 5000)

        records.append({
            "time": current_time,
            "open": round(open_price, 5),
            "high": round(high_price, 5),
            "low": round(low_price, 5),
            "close": round(close_price, 5),
            "tick_volume": volume,
        })

        price = close_price
        current_time += timedelta(minutes=tf_minutes)

    df = pd.DataFrame(records)
    logger.info(
        "Generated %d synthetic bars for %r %s [%s to %s]",
        len(df), ticker, interval, date_from, date_to,
    )
    return df


def fetch(
    ticker: str,
    date_from: str,
    date_to: str,
    interval: str = "1h",
    try_synthetic: bool = True,
) -> Optional[object]:
    """Fetch OHLC data from MT5. Generates synthetic fallback if unavailable."""
    mt5_data = None
    if _ensure_mt5():
        try:
            import MetaTrader5 as mt5
            import pandas as pd

            tf_minutes = _mt5_timeframe(interval) or 60

            mt5_tf_map = {
                1: mt5.TIMEFRAME_M1, 5: mt5.TIMEFRAME_M5, 15: mt5.TIMEFRAME_M15,
                30: mt5.TIMEFRAME_M30, 60: mt5.TIMEFRAME_H1, 240: mt5.TIMEFRAME_H4,
                1440: mt5.TIMEFRAME_D1, 10080: mt5.TIMEFRAME_W1,
            }
            mt5_tf = mt5_tf_map.get(tf_minutes, mt5.TIMEFRAME_H1)

            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            symbol_info = mt5.symbol_info(ticker)
            if symbol_info is not None and not symbol_info.visible:
                mt5.symbol_select(ticker, True)

            rates = mt5.copy_rates_range(ticker, mt5_tf, dt_from, dt_to)
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                logger.info(
                    "Fetched %d real bars for %r %s [%s to %s]",
                    len(df), ticker, interval, date_from, date_to,
                )
                mt5_data = df
        except Exception as exc:
            logger.debug("MT5 fetch error for %r: %s", ticker, exc)

    if mt5_data is not None and len(mt5_data) >= 20:
        return mt5_data

    # Fallback to synthetic data
    if try_synthetic:
        logger.info("MT5 returned no data for %r %s — using synthetic fallback", ticker, interval)
        return _generate_synthetic_data(ticker, date_from, date_to, interval)

    return None


def fetch_with_fallback(
    ticker: str,
    date_from: str,
    date_to: str,
    interval: str = "1h",
) -> Optional[object]:
    """Like fetch(), always tries synthetic fallback on failure."""
    return fetch(ticker, date_from, date_to, interval=interval, try_synthetic=True)
