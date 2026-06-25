"""
data_collector.py — Research Division Data Collection Module

Aggregates trade data from the MT5 bridge API and dashboard API,
with caching, error handling, and pair/magic splitting utilities.

Bridge API:   http://10.10.10.100:5000
Dashboard API: http://10.10.10.100:8003
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ── API Base URLs ──────────────────────────────────────────────────────────────
# Bridge binds to 127.0.0.1:5000 (localhost-only for security).
# Backend uses port 8006 (escalated from 8003→8005→8006 due to orphaned PIDs).
# Uses 127.0.0.1 (not 10.10.10.100) to match actual service bindings.
try:
    from config import BRIDGE_BASE as _CFG_BRIDGE, DASHBOARD_BASE as _CFG_DASHBOARD
    BRIDGE_BASE = _CFG_BRIDGE
    DASHBOARD_BASE = _CFG_DASHBOARD
except ImportError:
    BRIDGE_BASE = "http://127.0.0.1:5000"
    DASHBOARD_BASE = "http://127.0.0.1:8006"

# ── Request defaults ───────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 10  # seconds

# ── Cache path ─────────────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.dirname(__file__) or ".", "state")
CACHE_FILE = os.path.join(CACHE_DIR, "trade_cache.json")

# ── Bot magic-number mapping ───────────────────────────────────────────────────
# XAUUSD has both legacy bots and multi bots.
XAUUSD_LEGACY_MAGICS: Dict[str, int] = {
    "gold_bot": 777556,
    "scalping_bot": 999112,
    "streaming_bot": 666334,
    "gold_phoenix": 777888,
}
XAUUSD_MULTI_MAGICS: range = range(780001, 780010)  # 780001 … 780009
# Non-XAUUSD pairs only use multi bots 780002 … 780009.
NON_XAUUSD_MULTI_MAGICS: range = range(780002, 780010)

# ── Generic API helpers ────────────────────────────────────────────────────────


def _get_json(url: str, params: Optional[Dict] = None) -> Any:
    """Perform a GET request and return parsed JSON, or None on failure."""
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        logger.warning("ConnectionError — cannot reach %s", url)
    except requests.Timeout:
        logger.warning("Timeout — %s did not respond within %ds", url, REQUEST_TIMEOUT)
    except requests.HTTPError as e:
        logger.warning("HTTPError %s — %s", e.response.status_code, url)
    except json.JSONDecodeError:
        logger.warning("JSONDecodeError — non-JSON response from %s", url)
    except Exception as e:
        logger.exception("Unexpected error fetching %s: %s", url, e)
    return None


def _ensure_list(data: Any) -> list:
    """Coerce None → [], return other values unchanged (caller expects list)."""
    return data if data is not None else []


def _ensure_dict(data: Any) -> dict:
    """Coerce None → {}, return other values unchanged."""
    return data if data is not None else {}


# ── Bridge API functions ───────────────────────────────────────────────────────


def fetch_trade_history(days: int = 30) -> List[dict]:
    """Fetch closed trades from the bridge history endpoint.

    Returns a list of trade dicts (empty list on failure).
    """
    url = f"{BRIDGE_BASE}/api/v1/accounts/default/history"
    data = _get_json(url, params={"days": days})
    return _ensure_list(data)


def fetch_open_positions() -> List[dict]:
    """Fetch currently open positions from the bridge.

    Returns a list of position dicts (empty list on failure).
    """
    url = f"{BRIDGE_BASE}/api/v1/accounts/default/positions"
    data = _get_json(url)
    return _ensure_list(data)


def fetch_equity_curve(days: int = 30) -> List[dict]:
    """Fetch historical equity curve from the bridge.

    Returns a list of equity-point dicts (empty list on failure).
    """
    url = f"{BRIDGE_BASE}/api/v1/accounts/default/equity"
    data = _get_json(url, params={"days": days})
    return _ensure_list(data)


def fetch_account_stats(days: int = 30) -> dict:
    """Fetch aggregated account statistics from the bridge.

    Returns a dict (empty dict on failure).
    """
    url = f"{BRIDGE_BASE}/api/v1/accounts/default/stats"
    data = _get_json(url, params={"days": days})
    return _ensure_dict(data)


def get_live_tick(symbol: str) -> dict:
    """Fetch the latest live tick for a symbol from the bridge.

    Returns a dict (empty dict on failure).
    """
    url = f"{BRIDGE_BASE}/api/v1/accounts/default/tick/{symbol}"
    data = _get_json(url)
    return _ensure_dict(data)


# ── Dashboard API functions ────────────────────────────────────────────────────


def fetch_dashboard_stats() -> dict:
    """Fetch consolidated dashboard stats.

    Returns a dict (empty dict on failure).
    """
    url = f"{DASHBOARD_BASE}/api/stats"
    data = _get_json(url)
    return _ensure_dict(data)


def fetch_bots_status() -> List[dict]:
    """Fetch status of all bots from the dashboard.

    Returns a list of bot dicts (empty list on failure).
    """
    url = f"{DASHBOARD_BASE}/api/bots"
    data = _get_json(url)
    return _ensure_list(data)


def fetch_sentiment() -> dict:
    """Fetch sentiment score from the dashboard.

    Returns a dict (empty dict on failure).
    """
    url = f"{DASHBOARD_BASE}/api/sentiment/score"
    data = _get_json(url)
    return _ensure_dict(data)


# ── Caching ────────────────────────────────────────────────────────────────────


def cache_trade_data() -> bool:
    """Fetch trade history and persist to ``state/trade_cache.json``.

    Creates the state directory if it does not exist.
    Returns True on success, False on failure.
    """
    trades = fetch_trade_history(days=30)
    if not trades:
        logger.warning("cache_trade_data — no trades returned, not caching")
        return False

    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {
        "cached_at": datetime.utcnow().isoformat(),
        "count": len(trades),
        "trades": trades,
    }
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info("Cached %d trades to %s", len(trades), CACHE_FILE)
        return True
    except (OSError, IOError) as e:
        logger.exception("Failed to write cache file %s: %s", CACHE_FILE, e)
        return False


def load_cached_data() -> Optional[dict]:
    """Load previously cached trade data from ``state/trade_cache.json``.

    Returns the full payload dict (keys: ``cached_at``, ``count``, ``trades``)
    or ``None`` if the cache file is missing or corrupt.
    """
    if not os.path.isfile(CACHE_FILE):
        logger.info("No cache file found at %s", CACHE_FILE)
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError, IOError) as e:
        logger.warning("Failed to load cache file %s: %s", CACHE_FILE, e)
        return None


# ── Trade splitting helpers ────────────────────────────────────────────────────


def split_trades_by_pair(trades: List[dict]) -> Dict[str, List[dict]]:
    """Group a list of trades by their trading pair (symbol).

    Args:
        trades: List of trade dicts, each expected to have a ``symbol`` key
                (or ``pair`` as fallback).

    Returns:
        Dict mapping pair symbol → list of trades for that pair.
    """
    grouped: Dict[str, List[dict]] = {}
    for t in trades:
        pair = t.get("symbol") or t.get("pair")
        if not pair:
            continue
        grouped.setdefault(pair, []).append(t)
    return grouped


def split_trades_by_magic(trades: List[dict]) -> Dict[int, List[dict]]:
    """Group a list of trades by their magic number.

    Args:
        trades: List of trade dicts, each expected to have a ``magic`` key
                (or ``magic_number`` as fallback).

    Returns:
        Dict mapping magic number → list of trades with that magic.
    """
    grouped: Dict[int, List[dict]] = {}
    for t in trades:
        magic = t.get("magic") or t.get("magic_number")
        if magic is None:
            continue
        magic = int(magic)
        grouped.setdefault(magic, []).append(t)
    return grouped


# ── Bot-magic helpers ──────────────────────────────────────────────────────────


def is_xauusd_magic(magic: int) -> bool:
    """Return True if *magic* belongs to any XAUUSD bot (legacy or multi)."""
    if magic in XAUUSD_LEGACY_MAGICS.values():
        return True
    if magic in XAUUSD_MULTI_MAGICS:
        return True
    return False


def bot_name_for_magic(magic: int) -> Optional[str]:
    """Return a human-friendly bot name for a magic number, or None."""
    # Legacy bots (reverse lookup)
    for name, mid in XAUUSD_LEGACY_MAGICS.items():
        if mid == magic:
            return name
    # Multi bots
    if magic in XAUUSD_MULTI_MAGICS:
        return f"multi_bot_{magic}"
    return None


# ── Convenience: fetch all ─────────────────────────────────────────────────────


def fetch_all(days: int = 30) -> Dict[str, Any]:
    """Utility: call every fetch function in one shot and return results.

    Returns a dict keyed by endpoint name.
    """
    return {
        "trade_history": fetch_trade_history(days=days),
        "open_positions": fetch_open_positions(),
        "equity_curve": fetch_equity_curve(days=days),
        "account_stats": fetch_account_stats(days=days),
        "dashboard_stats": fetch_dashboard_stats(),
        "bots_status": fetch_bots_status(),
        "sentiment": fetch_sentiment(),
    }
