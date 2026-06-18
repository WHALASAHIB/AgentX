"""
AGENTX Backtester — Market Data Fetcher
Supports MT5 live data and Yahoo Finance fallback.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Supported instruments with their MT5 symbols and pip info
INSTRUMENTS = {
    "XAUUSD": {"ticker": "XAUUSD", "name": "Gold vs USD", "spread_pips": 1.0, "pip_value": 0.01, "digits": 2, "contract_size": 100},
    "EURUSD": {"ticker": "EURUSD", "name": "Euro vs USD", "spread_pips": 1.0, "pip_value": 0.0001, "digits": 5, "contract_size": 100000},
    "BTCUSD": {"ticker": "BTCUSD", "name": "Bitcoin vs USD", "spread_pips": 10.0, "pip_value": 1.0, "digits": 2, "contract_size": 1},
}

# Yahoo Finance symbol overrides (MT5 ticker → Yahoo ticker)
YAHOO_SYMBOL_MAP = {
    "XAUUSD": "GC=F",       # Gold Futures
    "EURUSD": "EURUSD=X",   # EUR/USD Forex
    "BTCUSD": "BTC-USD",    # Bitcoin USD
}

TIMEFRAME_MAP = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440, "1w": 10080,
}


def fetch(symbol: str, date_from: str, date_to: str, interval: str = "1h") -> Optional[pd.DataFrame]:
    """
    Fetch historical OHLCV data for backtesting.

    Args:
        symbol: Instrument ticker (e.g. 'XAUUSD')
        date_from: Start date string ('YYYY-MM-DD')
        date_to: End date string ('YYYY-MM-DD')
        interval: Timeframe string ('1m', '5m', '15m', '1h', '4h', '1d', '1w')

    Returns:
        DataFrame with columns: date, open, high, low, close, volume
        Returns None if data cannot be fetched.
    """
    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d")

    # Try MT5 first — best data quality
    df = _fetch_mt5(symbol, dt_from, dt_to, interval)
    if df is not None and len(df) >= 20:
        return df

    logger.warning("MT5 returned insufficient data for %s (%s→%s, %s), trying Yahoo Finance fallback",
                   symbol, date_from, date_to, interval)

    # Try Yahoo Finance fallback
    df = _fetch_yahoo(symbol, dt_from, dt_to, interval)
    if df is not None and len(df) >= 20:
        return df

    logger.error("No data source available for %s from %s to %s (MT5 + Yahoo both failed)",
                 symbol, date_from, date_to)
    return None


def _fetch_mt5(symbol: str, dt_from: datetime, dt_to: datetime, interval: str) -> Optional[pd.DataFrame]:
    """Fetch historical data from MetaTrader 5."""
    try:
        import MetaTrader5 as mt5

        tf_map = {
            "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5, "15m": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30, "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1, "1w": mt5.TIMEFRAME_W1,
        }
        tf = tf_map.get(interval, mt5.TIMEFRAME_H1)

        # Ensure MT5 is initialized
        if not mt5.initialize():
            logger.error("MT5 initialize failed: %s", mt5.last_error())
            return None

        # Check symbol
        if not mt5.symbol_select(symbol, True):
            logger.warning("Cannot select symbol %s on MT5", symbol)
            return None

        rates = mt5.copy_rates_range(symbol, tf, dt_from, dt_to)
        if rates is None or len(rates) == 0:
            logger.warning("No MT5 data for %s from %s to %s", symbol, dt_from.date(), dt_to.date())
            return None

        df = pd.DataFrame(rates)
        df["date"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["date", "open", "high", "low", "close", "volume", "spread", "real_volume"]]
        df.sort_values("date", inplace=True)

        logger.info("Fetched %d MT5 bars for %s (%s → %s)", len(df), symbol,
                    df["date"].iloc[0], df["date"].iloc[-1])
        return df

    except ImportError:
        logger.warning("MetaTrader5 package not available")
        return None
    except Exception as e:
        logger.error("MT5 fetch error: %s", e)
        return None


def _fetch_yahoo(symbol: str, dt_from: datetime, dt_to: datetime, interval: str) -> Optional[pd.DataFrame]:
    """Fetch historical data from Yahoo Finance as fallback."""
    try:
        import yfinance as yf

        # Map interval to yfinance format
        # yfinance supports: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
        yf_interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "60m", "4h": "60m",  # 4h not supported — download 1h and resample
            "1d": "1d", "1w": "1wk",
        }
        yf_interval = yf_interval_map.get(interval, "1d")

        # Map symbol to Yahoo ticker
        yahoo_symbol = YAHOO_SYMBOL_MAP.get(symbol, symbol)

        logger.info("Yahoo Finance fallback: %s %s %s→%s", yahoo_symbol, yf_interval,
                    dt_from.date(), dt_to.date())

        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(start=dt_from, end=dt_to + timedelta(days=1), interval=yf_interval)

        if df is None or df.empty:
            logger.warning("Yahoo Finance returned no data for %s", yahoo_symbol)
            return None

        # Normalize column names
        df = df.reset_index()
        # yfinance uses 'Datetime' for intraday, 'Date' for daily+
        time_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={
            time_col: "date",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df[["date", "open", "high", "low", "close", "volume"]].copy()
        df.sort_values("date", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # If 4h was requested, resample 1h → 4h
        if interval == "4h":
            df = df.set_index("date").resample("4h").agg({
                "open": "first", "high": "max", "low": "min",
                "close": "last", "volume": "sum",
            }).dropna().reset_index()

        logger.info("Fetched %d Yahoo bars for %s (%s → %s)", len(df), symbol,
                    df["date"].iloc[0], df["date"].iloc[-1])
        return df

    except ImportError:
        logger.warning("yfinance package not available, no fallback possible")
        return None
    except Exception as e:
        logger.error("Yahoo Finance fetch error for %s: %s", symbol, e)
        return None
