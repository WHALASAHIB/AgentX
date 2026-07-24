"""
config.py — Research & Innovation Division Central Configuration
================================================================
Single source of truth for API endpoints, magic numbers, cache paths,
request defaults, and trading constants used by the research division.

All modules in this directory import from here rather than hardcoding
values. Change once, propagate everywhere.

Bridge API:   http://10.10.10.100:5000
Dashboard API: http://10.10.10.100:8003
Account ID:    default
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Division Identity
# ═══════════════════════════════════════════════════════════════════════════════

DIVISION_NAME: str = "Research & Innovation"
DIVISION_LEAD: str = "HermesJatti Research AI"
DIVISION_EMOJI: str = "📡"
DIVISION_VERSION: str = "3.4.2"

# ═══════════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# MT5 Bridge Service (trading data, positions, account info)
# Bridge binds to 127.0.0.1:5000 (localhost-only for security)
BRIDGE_BASE: str = "http://127.0.0.1:5000"

# Dashboard / Backend API (sentiment, bots status, aggregated stats)
# Backend moved from 8003→8005→8006→8008→8005 (back to 8005 after zombie PID cleared)
# Current active backend is on port 8005 — see agentx-platform skill "Port Zombie Problem"
DASHBOARD_BASE: str = "http://127.0.0.1:8005"

# Sentiment Engine HTTP endpoint (when accessed remotely)
SENTIMENT_API: str = f"{DASHBOARD_BASE}/api/sentiment/score"
SENTIMENT_REFRESH_API: str = f"{DASHBOARD_BASE}/api/sentiment/refresh"

# Local Ollama LLM (on host PC at 10.10.10.1)
OLLAMA_BASE: str = "http://10.10.10.1:11434"
OLLAMA_MODEL: str = "qwen2.5:14b"
OLLAMA_MODEL_HEAVY: str = "qwen3.6:27b"
OLLAMA_TIMEOUT: int = 60          # seconds (increased from 30s default)
OLLAMA_TIMEOUT_HEAVY: int = 120   # seconds for the 27b model

# ── Account ───────────────────────────────────────────────────────────────────
ACCOUNT_ID: str = "ftmo-100k"

# ── Bridge URL helpers ─────────────────────────────────────────────────────────


def bridge_url(path: str) -> str:
    """Build a fully qualified bridge API URL.

    >>> bridge_url("/api/v1/accounts/default/history")
    'http://10.10.10.100:5000/api/v1/accounts/default/history'
    """
    return f"{BRIDGE_BASE.rstrip('/')}/{path.lstrip('/')}"


def dashboard_url(path: str) -> str:
    """Build a fully qualified dashboard API URL."""
    return f"{DASHBOARD_BASE.rstrip('/')}/{path.lstrip('/')}"


def ollama_url() -> str:
    """Ollama chat completions endpoint."""
    return f"{OLLAMA_BASE.rstrip('/')}/v1/chat/completions"


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP Request Defaults
# ═══════════════════════════════════════════════════════════════════════════════

REQUEST_TIMEOUT: int = 10            # seconds (general-purpose)
REQUEST_TIMEOUT_LONG: int = 30       # seconds (data-heavy endpoints)

# Default headers sent with every outbound request
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

MAX_RETRIES: int = 3
RETRY_BACKOFF_SEC: float = 1.0  # exponential backoff factor

# Polymarket API requires a User-Agent header or returns HTTP 403
POLYMARKET_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# ═══════════════════════════════════════════════════════════════════════════════
# File Paths & Caching
# ═══════════════════════════════════════════════════════════════════════════════

# Root directory for this research module
RESEARCH_DIR: str = os.path.dirname(os.path.abspath(__file__))

# State directory (runtime data: cache files, scrum JSONs, etc.)
STATE_DIR: str = os.path.join(RESEARCH_DIR, "state")

# Report / brief output directory (date-stamped markdown files)
REPORT_DIR: str = RESEARCH_DIR  # reports saved alongside this module

# ── Trade Data Cache ──────────────────────────────────────────────────────────

CACHE_DIR: str = STATE_DIR
CACHE_FILE: str = os.path.join(CACHE_DIR, "trade_cache.json")
CACHE_TTL_SEC: int = 1800  # 30 minutes

# ── Sentiment Engine Cache ────────────────────────────────────────────────────

SENTIMENT_CACHE_TTL_SEC: int = 1800  # 30 minutes (same as sentiment_engine.py)

# ── Social Sentiment ──────────────────────────────────────────────────────────

SOCIAL_SENTIMENT_DIR: str = RESEARCH_DIR
SOCIAL_SENTIMENT_PREFIX: str = "social_sentiment"
SOCIAL_SENTIMENT_DATE_FORMAT: str = "%Y-%m-%d"

# ── Board Meeting Reports ─────────────────────────────────────────────────────

BOARD_MEETING_PREFIX: str = "daily_board_meeting_"
BOARD_MEETING_DATE_FORMAT: str = "%Y-%m-%d"

# ── Division Reports ──────────────────────────────────────────────────────────

DIVISION_REPORT_PREFIX: str = "division_reports_"
DIVISION_REPORT_DATE_FORMAT: str = "%Y-%m-%d"

# ── Discovery / Innovation Reports ────────────────────────────────────────────

DISCOVERIES_FILE: str = os.path.join(RESEARCH_DIR, "discoveries.md")

# ═══════════════════════════════════════════════════════════════════════════════
# Bot Magic-Number Mapping
# ═══════════════════════════════════════════════════════════════════════════════
# Each AGENTX bot is identified by a unique "magic number" in MT5.
# These are referenced throughout the research division for trade attribution.

# Legacy XAUUSD bots
XAUUSD_LEGACY_MAGICS: Dict[str, int] = {
    "gold_bot": 777556,
    "scalping_bot": 999112,
    "streaming_bot": 666334,
    "gold_phoenix": 777888,
}

# Multi-pair bots (XAUUSD range)
XAUUSD_MULTI_MAGICS: range = range(780001, 780010)  # 780001 … 780009

# Non-XAUUSD pairs only use multi bots 780002 … 780009
NON_XAUUSD_MULTI_MAGICS: range = range(780002, 780010)

# All known XAUUSD magic numbers (legacy + multi) for quick membership checks
ALL_XAUUSD_MAGICS: set = set(XAUUSD_LEGACY_MAGICS.values()) | set(XAUUSD_MULTI_MAGICS)

# All known bot magic numbers (across all pairs)
ALL_KNOWN_MAGICS: set = ALL_XAUUSD_MAGICS | set(NON_XAUUSD_MULTI_MAGICS)


def is_xauusd_magic(magic: int) -> bool:
    """Return True if *magic* belongs to any XAUUSD bot (legacy or multi)."""
    return magic in ALL_XAUUSD_MAGICS


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


# ═══════════════════════════════════════════════════════════════════════════════
# Market Session Configuration
# ═══════════════════════════════════════════════════════════════════════════════
# Session classification is used in trade-performance root-cause analysis.

SESSION_LIQUIDITY_MAP: Dict[int, float] = {
    # Hour (UTC) → liquidity rating (0.0 = dead, 1.0 = peak)
    0: 0.15,  1: 0.10,  2: 0.10,  3: 0.10,  4: 0.10,  5: 0.15,
    6: 0.20,  7: 0.25,  8: 0.35,  9: 0.70, 10: 0.85, 11: 0.90,
    12: 0.85, 13: 0.80, 14: 0.75, 15: 0.70, 16: 0.60, 17: 0.50,
    18: 0.45, 19: 0.40, 20: 0.35, 21: 0.30, 22: 0.25, 23: 0.20,
}


def get_session_name(hour_utc: int) -> str:
    """Classify a UTC hour into a named trading session."""
    if 0 <= hour_utc < 8:
        return "Asian"
    elif 8 <= hour_utc < 17:
        return "London"
    elif 17 <= hour_utc < 23:
        return "US"
    else:
        return "Post-US"  # hour 23


def get_liquidity_rating(hour_utc: int) -> float:
    """Return the liquidity rating (0.0–1.0) for a given UTC hour."""
    return SESSION_LIQUIDITY_MAP.get(hour_utc, 0.0)


def should_trade(hour_utc: int, min_liquidity: float = 0.2) -> bool:
    """Return True if a trade should fire at *hour_utc*.

    Args:
        hour_utc: Hour in UTC (0-23).
        min_liquidity: Minimum liquidity threshold (default 0.2).

    Returns:
        True if liquidity >= min_liquidity.
    """
    return get_liquidity_rating(hour_utc) >= min_liquidity


# ═══════════════════════════════════════════════════════════════════════════════
# Sentiment Lexicon (from sentiment_engine.py)
# ═══════════════════════════════════════════════════════════════════════════════

BULLISH_WORDS: set = {
    "bullish", "buy", "long", "uptrend", "breakout", "rally", "surge", "moon",
    "accumulation", "support", "oversold", "dip buy", "buying opportunity",
    "gold rush", "safe haven", "inflation hedge", "wealth preservation",
    "bouncing", "reversal up", "gains", "recovery", "bull run", "going up",
    "momentum", "strong demand", "outperform", "upward", "rising",
    "break above", "resistance break", "higher high", "bullish flag",
}

BEARISH_WORDS: set = {
    "bearish", "sell", "short", "downtrend", "breakdown", "dump", "crash",
    "distribution", "resistance", "overbought", "sell off", "selloff",
    "correction", "reversal down", "puts", "negative outlook",
    "downgrade", "weak demand", "underperform", "downward", "falling",
    "losses", "decline", "bear run", "going down", "top in",
    "overvalued", "bubble", "risk off", "liquidate", "panic",
    "break below", "support break", "lower low", "bearish flag",
}

SENTIMENT_THRESHOLD_BULLISH: int = 3     # ≥ +3 = bullish bias
SENTIMENT_THRESHOLD_BEARISH: int = -3    # ≤ -3 = bearish bias
SENTIMENT_SCORE_MIN: int = -10
SENTIMENT_SCORE_MAX: int = 10

# Contribution weights per source (sums to 10)
SENTIMENT_WEIGHT_NEWS: int = 5       # Google News RSS contributes ±5
SENTIMENT_WEIGHT_POLYMARKET: int = 3  # Polymarket contributes ±3
SENTIMENT_WEIGHT_TREND: int = 1       # MT5 price trend contributes ±1
SENTIMENT_WEIGHT_LLM: int = 1         # Optional LLM analysis contributes ±1

# ═══════════════════════════════════════════════════════════════════════════════
# Polymarket Risk Events
# ═══════════════════════════════════════════════════════════════════════════════
# Keywords used by the sentiment engine to detect geopolitical risk.

POLYMARKET_EVENTS_URL: str = (
    "https://gamma-api.polymarket.com/events?closed=false&limit=50"
)

POLYMARKET_RISK_KEYWORDS: Dict[str, float] = {
    "geopolitics": 0.5,
    "military clash": 0.7,
    "invasion": 0.9,
    "war": 0.9,
    "nuclear": 1.0,
    "conflict": 0.6,
    "troops": 0.6,
    "sanctions": 0.3,
    "political turmoil": 0.4,
    "election": 0.2,
    "Macron out": 0.3,
    "Starmer": 0.2,
    "Ukraine": 0.5,
    "Russia": 0.6,
    "China": 0.5,
    "Taiwan": 0.7,
    "NATO": 0.6,
}

# ═══════════════════════════════════════════════════════════════════════════════
# Google News RSS
# ═══════════════════════════════════════════════════════════════════════════════

GOOGLE_NEWS_RSS_URL: str = (
    "https://news.google.com/rss/search?q=gold+XAUUSD&hl=en-US&gl=US&ceid=US:en"
)
GOOGLE_NEWS_MAX_ARTICLES: int = 30  # fetch latest N articles

# ═══════════════════════════════════════════════════════════════════════════════
# Data Source URLs
# ═══════════════════════════════════════════════════════════════════════════════

REDDIT_FOREX_RSS: str = "https://old.reddit.com/r/Forex/.rss"
REDDIT_ALGOTRADING_RSS: str = "https://old.reddit.com/r/algotrading/.rss"
REDDIT_GOLD_RSS: str = "https://old.reddit.com/r/Gold/.rss"

INVESTING_COM_RSS: str = "https://www.investing.com/rss/news_25.rss"  # commodities

# ═══════════════════════════════════════════════════════════════════════════════
# Trading Instruments
# ═══════════════════════════════════════════════════════════════════════════════

SUPPORTED_INSTRUMENTS: Dict[str, Dict] = {
    "XAUUSD": {"name": "Gold vs USD", "spread_pips": 1.0, "pip_value": 0.01, "digits": 2, "contract_size": 100},
    "EURUSD": {"name": "Euro vs USD", "spread_pips": 1.0, "pip_value": 0.0001, "digits": 5, "contract_size": 100000},
    "BTCUSD": {"name": "Bitcoin vs USD", "spread_pips": 10.0, "pip_value": 1.0, "digits": 2, "contract_size": 1},
    "GBPUSD": {"name": "Pound vs USD", "spread_pips": 1.0, "pip_value": 0.0001, "digits": 5, "contract_size": 100000},
    "USDJPY": {"name": "Dollar vs Yen", "spread_pips": 0.8, "pip_value": 0.01, "digits": 3, "contract_size": 100000},
    "USDCHF": {"name": "Dollar vs Franc", "spread_pips": 1.0, "pip_value": 0.0001, "digits": 5, "contract_size": 100000},
    "USDCAD": {"name": "Dollar vs Canadian", "spread_pips": 1.0, "pip_value": 0.0001, "digits": 5, "contract_size": 100000},
    "AUDUSD": {"name": "Aussie vs USD", "spread_pips": 1.2, "pip_value": 0.0001, "digits": 5, "contract_size": 100000},
    "NZDUSD": {"name": "Kiwi vs USD", "spread_pips": 1.5, "pip_value": 0.0001, "digits": 5, "contract_size": 100000},
}

# ═══════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════


def date_stamp(fmt: str = "%Y-%m-%d") -> str:
    """Return today's date as a string (default: YYYY-MM-DD)."""
    return datetime.now().strftime(fmt)


def report_path(prefix: str, suffix: str = ".md") -> str:
    """Build a date-stamped report file path under REPORT_DIR.

    Args:
        prefix: File name prefix (e.g. 'daily_board_meeting_').
        suffix: File extension (default '.md').

    Returns:
        Absolute path like ``C:\\Trading\\research\\daily_board_meeting_2026-06-18.md``.
    """
    return os.path.join(REPORT_DIR, f"{prefix}{date_stamp()}{suffix}")
