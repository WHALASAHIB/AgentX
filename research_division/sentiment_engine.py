"""
Sentiment Engine — gold market sentiment scoring (-10 to +10).

Computes sentiment from REAL bot data:
- Reads bot states from backend DB
- Reads trade history for total PnL and win rate
- Uses bots/trades data only (avoids MT5/bridge async conflicts)
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR.parent))


@dataclass
class SentimentScore:
    score: float = 0.0
    bias: str = "neutral"
    bullish_news: int = 0
    bearish_news: int = 0
    news_count: int = 0
    polymarket_risk: float = 0.0
    gold_trend: str = "neutral"
    drivers: list[str] = field(default_factory=list)
    generated_at: str = ""
    total_pnl: float = 0.0
    win_rate: float = 0.0
    open_positions: int = 0
    running_bots: int = 0
    total_bots: int = 0
    running_ratio: float = 0.0


_sentiment_cache: Optional[SentimentScore] = None


async def get_sentiment(force_refresh: bool = False) -> SentimentScore:
    global _sentiment_cache

    now = datetime.now(timezone.utc).isoformat()
    if not force_refresh and _sentiment_cache is not None:
        return _sentiment_cache

    try:
        from backend.db.pool import get_db
        db = get_db()

        bots = []
        trades = []
        try:
            bots = db.get_bots()
        except Exception as exc:
            logger.info("Sentiment: bots fetch failed: %s", exc)

        try:
            trades = db.get_trades(limit=500)
        except Exception as exc:
            logger.info("Sentiment: trades fetch failed: %s", exc)

        logger.info("Sentiment: %d bots, %d trades", len(bots), len(trades))

        result = _compute_from_db(bots, trades, now)
        _sentiment_cache = result
        return result

    except Exception as exc:
        logger.error("Sentiment error", exc_info=True)
        # Don't cache error results — return fresh but allow retry
        return SentimentScore(
            score=0.0, bias="neutral",
            gold_trend="neutral",
            drivers=[f"Data fetch error: {exc}"],
            generated_at=now,
        )


def _compute_from_db(bots: list[dict], trades: list[dict], now: str) -> SentimentScore:
    total_bots = len(bots)
    running_bots = sum(1 for b in bots if b.get("status") == "running")
    running_ratio = running_bots / max(total_bots, 1)

    real_trades = [
        t for t in trades
        if t.get("symbol")
        and t.get("exit_price") is not None
        and t.get("close_time", "") != "OPEN"
        and t.get("net_profit", 0) != 10000
    ]
    total_pnl = sum(float(t.get("net_profit", 0)) for t in real_trades)
    winning = [t for t in real_trades if float(t.get("net_profit", 0)) > 0]
    losing = [t for t in real_trades if float(t.get("net_profit", 0)) < 0]
    win_rate = len(winning) / max(len(real_trades), 1) if real_trades else 0.5

    score = 0.0
    drivers: list[str] = []

    pnl_factor = max(-3.0, min(3.0, total_pnl / 500.0))
    score += pnl_factor
    if abs(total_pnl) > 100:
        drivers.append(f"Total PnL: ${total_pnl:+.2f}")

    wr_factor = (win_rate - 0.5) * 6.0
    score += wr_factor
    drivers.append(f"Win rate: {win_rate*100:.1f}% ({len(winning)}W/{len(losing)}L)")

    ratio_factor = (running_ratio - 0.5) * 4.0
    score += ratio_factor
    drivers.append(f"Bots running: {running_bots}/{total_bots}")

    open_positions = len([t for t in real_trades if t.get("close_time", "") == "OPEN"])
    if open_positions <= 3:
        pos_factor = 1.0
    elif open_positions <= 8:
        pos_factor = 0.0
    else:
        pos_factor = -2.0
    score += pos_factor
    drivers.append(f"Recent trades: {len(real_trades)}")

    score = round(max(-10.0, min(10.0, score)), 1)

    bias = "neutral"
    if score >= 3.0:
        bias = "bullish"
    elif score <= -3.0:
        bias = "bearish"

    bullish_count = sum(1 for t in real_trades if float(t.get("net_profit", 0)) > 0)
    bearish_count = sum(1 for t in real_trades if float(t.get("net_profit", 0)) < 0)

    return SentimentScore(
        score=score,
        bias=bias,
        bullish_news=bullish_count,
        bearish_news=bearish_count,
        news_count=bullish_count + bearish_count,
        polymarket_risk=round(1.0 - min(1.0, max(0.0, (win_rate + running_ratio) / 2)), 2),
        gold_trend="neutral",
        drivers=drivers[:6],
        generated_at=now,
        total_pnl=round(total_pnl, 2),
        win_rate=round(win_rate, 4),
        open_positions=open_positions,
        running_bots=running_bots,
        total_bots=total_bots,
        running_ratio=round(running_ratio, 2),
    )
