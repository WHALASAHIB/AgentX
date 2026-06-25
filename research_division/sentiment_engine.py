"""
Sentiment Engine — gold market sentiment scoring (-10 to +10).

Computes sentiment from REAL bot data:
- Reads bot states from backend DB (agentx_store.json or Postgres)
- Reads trade history for total PnL and win rate
- Counts open positions from the MT5 bridge
- Calculates running/total bots ratio
- Determines gold trend from XAUUSD price movement via bridge tick

Bias: >=3 = bullish, <=-3 = bearish, else neutral.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Ensure backend is importable
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR.parent))

# Lazy imports to avoid circular deps at module level
_IMPORTED = False


def _ensure_imports():
    global _IMPORTED
    if _IMPORTED:
        return
    global get_db, BridgeClient, get_bridge, metaTrader5, mt5
    from backend.db.pool import get_db as _get_db
    get_db = _get_db

    from backend.bridge_client import BridgeClient as _BridgeClient, get_bridge as _get_bridge
    BridgeClient = _BridgeClient
    get_bridge = _get_bridge

    import MetaTrader5 as _mt5
    mt5 = _mt5
    metaTrader5 = _mt5

    _IMPORTED = True


# ── Return type ────────────────────────────────────────────────────────────

@dataclass
class SentimentScore:
    """Container returned by :func:`get_sentiment`."""
    score: float = 0.0                     # -10 (extremely bearish) … +10 (extremely bullish)
    bias: str = "neutral"                  # "bullish" | "bearish" | "neutral"
    bullish_news: int = 0
    bearish_news: int = 0
    news_count: int = 0
    polymarket_risk: float = 0.0           # 0.0 – 1.0  (higher = riskier)
    gold_trend: str = "neutral"            # "uptrend" | "downtrend" | "neutral"
    drivers: list[str] = field(default_factory=list)
    generated_at: str = ""

    # Real-data fields
    total_pnl: float = 0.0
    win_rate: float = 0.0
    open_positions: int = 0
    running_bots: int = 0
    total_bots: int = 0
    running_ratio: float = 0.0


# ── Helpers ────────────────────────────────────────────────────────────────

def _fetch_bots() -> list[dict]:
    """Return all bot records from the backend DB."""
    try:
        _ensure_imports()
        db = get_db()
        return db.get_bots()
    except Exception as exc:
        logger.warning("Failed to fetch bots from DB: %s", exc)
        return []


def _fetch_trades() -> list[dict]:
    """Return trade records from the backend DB."""
    try:
        _ensure_imports()
        db = get_db()
        return db.get_trades(limit=500)
    except Exception as exc:
        logger.warning("Failed to fetch trades from DB: %s", exc)
        return []


def _fetch_positions() -> list[dict]:
    """Return open positions from the MT5 bridge."""
    try:
        _ensure_imports()
        bridge = get_bridge()
        positions = bridge.get_positions()
        # Use synchronous-like call — we are in a sync function, so we
        # need to run the coroutine. This is called from get_sentiment()
        # which may be sync. We'll handle this in the top-level function.
        return positions  # This is a coroutine, handled at call site
    except Exception as exc:
        logger.warning("Failed to fetch positions from bridge: %s", exc)
        return []


def _fetch_xauusd_tick() -> Optional[dict]:
    """Fetch XAUUSD tick data from the MT5 bridge to determine gold trend."""
    try:
        _ensure_imports()
        # Use MetaTrader5 directly to get weekly price change
        config_path = _BACKEND_DIR.parent / "mt5_config.json"
        if not config_path.exists():
            logger.warning("mt5_config.json not found")
            return None

        import json
        with open(config_path) as f:
            cfg = json.load(f)

        terminal_path = cfg.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe")
        login = cfg.get("login")
        password = cfg.get("password")
        server = cfg.get("server")

        mt5.shutdown()
        init_kw = {"path": terminal_path}
        if login and password and server:
            init_kw["login"] = int(login)
            init_kw["password"] = str(password)
            init_kw["server"] = str(server)
        if not mt5.initialize(**init_kw):
            logger.warning("MT5 init failed for XAUUSD fetch: %s", mt5.last_error())
            mt5.shutdown()
            return None

        rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_D1, 0, 2)
        mt5.shutdown()

        if rates is None or len(rates) < 2:
            return None

        prev_close = rates[-2]["close"]
        current_price = rates[-1]["close"]
        change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0

        return {
            "prev_close": prev_close,
            "current_price": current_price,
            "change_pct": change_pct,
        }
    except Exception as exc:
        logger.warning("Failed to fetch XAUUSD data: %s", exc)
        try:
            mt5.shutdown()
        except Exception:
            pass
        return None


def _compute_score_from_bots(
    bots: list[dict],
    trades: list[dict],
    positions: list[dict],
    xauusd: Optional[dict],
) -> tuple[float, str, str, list[str], int, int, int, float, float, float]:
    """
    Compute sentiment score from real bot/trade/position data.

    Returns
    -------
    tuple of (score, bias, gold_trend, drivers, running_bots, total_bots,
              open_positions, total_pnl, win_rate, running_ratio)
    """
    # ── Bot stats ───────────────────────────────────────────────────────
    total_bots = len(bots)
    running_bots = sum(1 for b in bots if b.get("status") == "running")
    running_ratio = running_bots / max(total_bots, 1)

    # ── Trade stats (skip non-real trades like balance entries) ─────────
    real_trades = [
        t for t in trades
        if t.get("symbol")
        and t.get("exit_price") is not None
        and t.get("close_time", "") != "OPEN"
        and t.get("net_profit", 0) != 10000  # Skip initial balance entry
    ]
    total_pnl = sum(float(t.get("net_profit", 0)) for t in real_trades)
    winning = [t for t in real_trades if float(t.get("net_profit", 0)) > 0]
    losing = [t for t in real_trades if float(t.get("net_profit", 0)) < 0]
    win_rate = len(winning) / max(len(real_trades), 1)

    # ── Open positions count ────────────────────────────────────────────
    open_positions = len(positions)

    # ── Score calculation ───────────────────────────────────────────────
    score = 0.0
    drivers: list[str] = []

    # Factor 1: Total PnL (scaled: -3 to +3)
    # Every $500 of net PnL contributes 0.5 points, capped at ±3
    pnl_factor = max(-3.0, min(3.0, total_pnl / 500.0))
    score += pnl_factor
    if abs(total_pnl) > 100:
        drivers.append(f"Total PnL: ${total_pnl:+.2f}")

    # Factor 2: Win rate (0→-3, 0.5→0, 1.0→+3)
    wr_factor = (win_rate - 0.5) * 6.0
    score += wr_factor
    drivers.append(f"Win rate: {win_rate*100:.1f}% ({len(winning)}W/{len(losing)}L)")

    # Factor 3: Running bots ratio (0→-2, 1.0→+2)
    ratio_factor = (running_ratio - 0.5) * 4.0
    score += ratio_factor
    drivers.append(f"Bots running: {running_bots}/{total_bots}")

    # Factor 4: Open positions (too many open = risk)
    # 0-3 positions → +1, 4-8 → 0, >8 → -2
    if open_positions <= 3:
        pos_factor = 1.0
    elif open_positions <= 8:
        pos_factor = 0.0
    else:
        pos_factor = -2.0
    score += pos_factor
    drivers.append(f"Open positions: {open_positions}")

    # Factor 5: Gold trend from price movement
    gold_trend = "neutral"
    if xauusd:
        change = xauusd.get("change_pct", 0)
        if change > 0.3:
            gold_trend = "uptrend"
            score += 1.0
            drivers.append(f"XAUUSD trending up: {change:+.2f}%")
        elif change < -0.3:
            gold_trend = "downtrend"
            score -= 1.0
            drivers.append(f"XAUUSD trending down: {change:+.2f}%")
        else:
            drivers.append(f"XAUUSD flat: {change:+.2f}%")

    # Clamp score to [-10, 10]
    score = round(max(-10.0, min(10.0, score)), 1)

    # Bias
    bias = "neutral"
    if score >= 3.0:
        bias = "bullish"
    elif score <= -3.0:
        bias = "bearish"

    return score, bias, gold_trend, drivers[:6], running_bots, total_bots, open_positions, total_pnl, win_rate, running_ratio


# ── Public API ─────────────────────────────────────────────────────────────

_sentiment_cache: Optional[SentimentScore] = None


async def get_sentiment(force_refresh: bool = False) -> SentimentScore:
    """
    Return the current gold market sentiment score from REAL bot data.

    Parameters
    ----------
    force_refresh : bool
        When *True* the cached value is discarded and re-computed from
        the backend DB and MT5 bridge.

    Returns
    -------
    SentimentScore
        A dataclass with all fields consumed by the API endpoint.
    """
    global _sentiment_cache

    now = datetime.now(timezone.utc).isoformat()

    if not force_refresh and _sentiment_cache is not None:
        return _sentiment_cache

    try:
        # ── Gather real data ────────────────────────────────────────────
        _ensure_imports()
        db = get_db()

        import asyncio
        from backend.bridge_client import BridgeClient as _BridgeClient, get_bridge as _get_bridge
        bridge = _get_bridge()

        bots = db.get_bots()  # sync call
        trades = db.get_trades(limit=500)  # sync call
        try:
            positions = await asyncio.wait_for(bridge.get_positions(), timeout=10)
        except Exception:
            positions = []

        # Fetch XAUUSD price data (sync, uses MT5 directly)
        xauusd = _fetch_xauusd_tick()

        # ── Compute score ───────────────────────────────────────────────
        score_val, bias, gold_trend, drivers, running_bots, total_bots, open_positions, total_pnl, win_rate, running_ratio = \
            _compute_score_from_bots(bots, trades, positions, xauusd)

        # ── Derive news counts from trade sentiment ─────────────────────
        real = [t for t in trades if t.get("symbol") and t.get("close_time", "") != "OPEN"
                and t.get("net_profit", 0) != 10000 and t.get("exit_price") is not None]
        bullish_count = sum(1 for t in real if float(t.get("net_profit", 0)) > 0)
        bearish_count = sum(1 for t in real if float(t.get("net_profit", 0)) < 0)

        # ── Build response ──────────────────────────────────────────────
        _sentiment_cache = SentimentScore(
            score=score_val,
            bias=bias,
            bullish_news=bullish_count,
            bearish_news=bearish_count,
            news_count=bullish_count + bearish_count,
            polymarket_risk=round(1.0 - min(1.0, max(0.0, (win_rate + running_ratio) / 2)), 2),
            gold_trend=gold_trend,
            drivers=drivers,
            generated_at=now,
            total_pnl=round(total_pnl, 2),
            win_rate=round(win_rate, 4),
            open_positions=open_positions,
            running_bots=running_bots,
            total_bots=total_bots,
            running_ratio=round(running_ratio, 2),
        )
        return _sentiment_cache

    except Exception as exc:
        logger.error("Sentiment engine error: %s", exc, exc_info=True)
        # Fallback — provide a neutral score with error marker
        _sentiment_cache = SentimentScore(
            score=0.0,
            bias="neutral",
            bullish_news=0,
            bearish_news=0,
            news_count=0,
            polymarket_risk=0.5,
            gold_trend="neutral",
            drivers=[f"Data fetch error: {exc}"],
            generated_at=now,
        )
        return _sentiment_cache
