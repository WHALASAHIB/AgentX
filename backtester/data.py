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

# ── Bridge HTTP API endpoint ───────────────────────────────────────────────
BRIDGE_URL = "http://127.0.0.1:5000"

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


def _fetch_from_bridge(
    ticker: str,
    date_from: str,
    date_to: str,
    interval: str = "1h",
    bridge_url: str = BRIDGE_URL,
) -> Optional[object]:
    """Fetch OHLC data from the MT5 Bridge HTTP API.
    Returns a DataFrame with columns time, open, high, low, close, tick_volume.
    Returns None on failure."""
    import requests

    # Use mt5-demo account (has market data access)
    account_id = "mt5-demo"

    # Map interval to bridge format
    interval_map = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "H1": "1h", "1h": "1h", "H4": "4h", "4h": "4h",
        "D1": "1d", "1d": "1d", "W1": "1w", "1w": "1w",
    }
    tf = interval_map.get(interval, "1h")

    url = f"{bridge_url}/api/v1/history/{account_id}/{ticker}"
    params = {
        "date_from": date_from,
        "date_to": date_to,
        "timeframe": tf,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning(
                "Bridge history returned %d for %r %s",
                resp.status_code, ticker, interval,
            )
            return None

        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            logger.warning("Bridge history returned empty list for %r", ticker)
            return None

        df = pd.DataFrame(data)
        df["time"] = pd.to_datetime(df["time"])

        logger.info(
            "Fetched %d real bars via bridge for %r %s [%s to %s]",
            len(df), ticker, interval, date_from, date_to,
        )
        return df
    except ImportError:
        logger.warning("requests package not available for bridge fetch")
        return None
    except Exception as e:
        logger.warning("Bridge fetch error for %r: %s", ticker, e)
        return None


def _fetch_from_mt5_direct(
    ticker: str,
    date_from: str,
    date_to: str,
    interval: str = "1h",
) -> Optional[object]:
    """Direct MT5 fetch as fallback (if bridge is down but MT5 is available)."""
    try:
        import MetaTrader5 as mt5

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

        if not mt5.initialize(**init_kw):
            return None

        tf_minutes = _mt5_timeframe(interval) or 60
        mt5_tf_map = {
            1: mt5.TIMEFRAME_M1, 5: mt5.TIMEFRAME_M5, 15: mt5.TIMEFRAME_M15,
            30: mt5.TIMEFRAME_M30, 60: mt5.TIMEFRAME_H1, 240: mt5.TIMEFRAME_H4,
            1440: mt5.TIMEFRAME_D1, 10080: mt5.TIMEFRAME_W1,
        }
        mt5_tf = mt5_tf_map.get(tf_minutes, mt5.TIMEFRAME_H1)

        dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        mt5.symbol_select(ticker, True)
        rates = mt5.copy_rates_range(ticker, mt5_tf, dt_from, dt_to)
        mt5.shutdown()

        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            logger.info(
                "Fetched %d direct MT5 bars for %r %s [%s to %s]",
                len(df), ticker, interval, date_from, date_to,
            )
            return df

        return None
    except ImportError:
        return None
    except Exception as e:
        logger.debug("Direct MT5 fetch error for %r: %s", ticker, e)
        try:
            mt5.shutdown()
        except Exception:
            pass
        return None


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
    """Fetch OHLC data from the MT5 Bridge HTTP API.
    Falls back to synthetic data if bridge is unavailable."""

    # 1) Try bridge HTTP API first
    bridge_data = _fetch_from_bridge(ticker, date_from, date_to, interval)
    if bridge_data is not None and len(bridge_data) >= 20:
        return bridge_data

    # 2) Fallback: try direct MT5 (backup)
    mt5_data = _fetch_from_mt5_direct(ticker, date_from, date_to, interval)
    if mt5_data is not None and len(mt5_data) >= 20:
        return mt5_data

    # 3) Last resort: synthetic data
    if try_synthetic:
        logger.info("Bridge and MT5 unavailable for %r %s — using synthetic fallback", ticker, interval)
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
