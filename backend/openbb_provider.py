"""
OpenBB Data Provider — supplementary market data for AgentX.

Uses OpenBB (yfinance provider) for forex pairs and direct yfinance
for futures/crypto (XAUUSD, BTCUSD) since OpenBB auto-appends =X.

Usage:
    from backend.openbb_provider import get_all_forex_prices
    prices = get_all_forex_prices()
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# OpenBB for forex pairs
try:
    from openbb import obb
    OPENBB_AVAILABLE = True
    logger.info("OpenBB v%s loaded", obb.system.version)
except ImportError:
    obb = None
    OPENBB_AVAILABLE = False

# Direct yfinance for special symbols (Gold futures, BTC)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    yf = None
    YFINANCE_AVAILABLE = False

# Mappings: our symbol -> (provider, yahoo_symbol)
SYMBOL_MAP = {
    # Forex via OpenBB/yfinance (OpenBB auto-appends =X)
    "EURUSD": ("openbb", "EURUSD"),
    "GBPUSD": ("openbb", "GBPUSD"),
    "USDJPY": ("openbb", "USDJPY"),
    "USDCHF": ("openbb", "USDCHF"),
    "USDCAD": ("openbb", "USDCAD"),
    "AUDUSD": ("openbb", "AUDUSD"),
    "NZDUSD": ("openbb", "NZDUSD"),
    # Special assets via direct yfinance (OpenBB mangles these)
    "XAUUSD": ("yfinance", "GC=F"),       # Gold futures
    "BTCUSD": ("yfinance", "BTC-USD"),    # Bitcoin
}

ALL_PAIRS = list(SYMBOL_MAP.keys())


def get_forex_ohlc(symbol: str, days: int = 60) -> Optional[dict]:
    """
    Fetch OHLC data for a forex pair / asset.

    Args:
        symbol: e.g. "EURUSD", "XAUUSD", "BTCUSD"
        days: How many days of history to return

    Returns:
        dict with date, open, high, low, close, volume or None
    """
    symbol = symbol.upper()
    entry = SYMBOL_MAP.get(symbol)
    if not entry:
        logger.warning("Unknown symbol: %s", symbol)
        return None

    provider, yahoo_symbol = entry

    try:
        if provider == "openbb":
            if not OPENBB_AVAILABLE:
                return None
            result = obb.currency.price.historical(symbol=yahoo_symbol, provider="yfinance")
            df = result.to_dataframe()
        else:
            if not YFINANCE_AVAILABLE:
                return None
            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(period=f"{days*2}d")
            # yfinance returns uppercase column names
            df.columns = [c.lower() for c in df.columns]

        if df.empty:
            return None

        recent = df.tail(days)
        data = {
            "symbol": symbol,
            "source": provider,
            "date": [str(d) for d in recent.index],
            "open": [float(v) for v in recent["open"]],
            "high": [float(v) for v in recent["high"]],
            "low": [float(v) for v in recent["low"]],
            "close": [float(v) for v in recent["close"]],
            "volume": [float(v) if v else 0 for v in recent["volume"]],
        }
        return {
            "symbol": symbol,
            "source": f"openbb/{provider}",
            "data": data,
            "count": len(recent),
            "date_from": data["date"][0],
            "date_to": data["date"][-1],
        }
    except Exception as e:
        logger.error("Fetch error for %s: %s", symbol, e)
        return None


def get_latest_forex_price(symbol: str) -> Optional[dict]:
    """Get latest price (bid, ask, close) for a symbol."""
    ohlc = get_forex_ohlc(symbol, days=5)
    if not ohlc or not ohlc.get("data"):
        return None

    d = ohlc["data"]
    closes = d.get("close", [])
    opens = d.get("open", [])
    highs = d.get("high", [])
    lows = d.get("low", [])

    if not closes:
        return None

    c, o, h, lo = closes[-1], opens[-1] if opens else None, highs[-1] if highs else None, lows[-1] if lows else None

    change = None
    change_pct = None
    if o and o != 0:
        change = c - o
        change_pct = (change / o) * 100

    spread = 0.0002 if symbol != "XAUUSD" else 0.02
    if symbol == "BTCUSD":
        spread = 5.0

    return {
        "symbol": symbol,
        "bid": round(c, 2 if symbol == "BTCUSD" else 2 if symbol == "XAUUSD" else 5),
        "ask": round(c + spread, 2 if symbol == "BTCUSD" else 2 if symbol == "XAUUSD" else 5),
        "close": round(c, 5),
        "high": round(h, 5) if h else None,
        "low": round(lo, 5) if lo else None,
        "change": round(change, 5) if change else None,
        "change_pct": round(change_pct, 3) if change_pct else None,
        "source": f"openbb/{ohlc['source']}",
        "timestamp": str(datetime.now(timezone.utc).isoformat()),
        "date": d.get("date", [None])[-1],
    }


def get_all_forex_prices() -> dict:
    """Get latest prices for all tracked pairs/assets."""
    result = {}
    for pair in ALL_PAIRS:
        try:
            price = get_latest_forex_price(pair)
            if price:
                result[pair] = price
        except Exception as e:
            logger.error("Error fetching %s: %s", pair, e)
    return result
