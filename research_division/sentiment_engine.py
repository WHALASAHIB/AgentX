"""
Sentiment Engine — gold market sentiment scoring (-10 to +10).

Reads the latest Research Division report and computes a sentiment score
based on market performance data and blockers.  Fully self-contained;
no external API dependencies.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REPORTS_DIR = Path(__file__).resolve().parent / "reports"


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


# ── Helpers ────────────────────────────────────────────────────────────────

def _load_latest_report() -> Optional[dict]:
    """Return the contents of ``reports/latest.json``, or *None* on failure."""
    try:
        path = _REPORTS_DIR / "latest.json"
        if not path.exists():
            logger.warning("latest.json not found at %s", path)
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load latest report: %s", exc)
        return None


def _compute_score(report: dict) -> float:
    """
    Derive a sentiment score (-10 … +10) from the research division report.

    Factors (each contributes a sub-score that is clamped and summed):
      * Overall win-rate (0–1) → -5 to +5
      * Net profit (USD) → -3 to +3
      * Gold (XAUUSD) win rate → -2 to +2
      * Critical blockers → -3 to 0
    """
    ms = report.get("market_summary", {})
    pairs = report.get("pairs", {})

    score = 0.0

    # 1. Overall win rate  (0 → -5,  0.5 → 0,  1.0 → +5)
    wr = ms.get("overall_win_rate", 0.5)
    score += (wr - 0.5) * 10.0

    # 2. Net profit  (< -10k → -3,  0 → 0,  > +10k → +3)
    net = ms.get("net_profit", 0.0)
    score += max(-3.0, min(3.0, net / 5000.0))

    # 3. Gold (XAUUSD) win rate
    gold = pairs.get("XAUUSD", {})
    gold_wr = gold.get("win_rate", 0.3)
    score += (gold_wr - 0.3) * 5.0  # 0→-1.5, 0.3→0, 1.0→+3.5, clamped next

    # 4. Critical blockers
    blockers = report.get("blockers", [])
    crit_count = sum(1 for b in blockers if b.get("severity") == "critical")
    score -= min(3.0, crit_count * 1.5)

    return round(max(-10.0, min(10.0, score)), 1)


def _compute_bias(score: float) -> str:
    if score >= 3.0:
        return "bullish"
    elif score <= -3.0:
        return "bearish"
    return "neutral"


def _compute_gold_trend(report: dict) -> str:
    """Simple heuristic based on gold's recent net profit and win rate."""
    gold = report.get("pairs", {}).get("XAUUSD", {})
    net = gold.get("net_profit", 0.0)
    wr = gold.get("win_rate", 0.3)
    if net > 1000 and wr > 0.35:
        return "uptrend"
    elif net < -1000 or wr < 0.25:
        return "downtrend"
    return "neutral"


def _compute_drivers(report: dict) -> list[str]:
    """Return a short list of human-readable drivers."""
    drivers: list[str] = []
    blockers = report.get("blockers", [])
    for b in blockers:
        msg = b.get("message", "")
        if msg:
            drivers.append(msg)
    ms = report.get("market_summary", {})
    pf = ms.get("overall_profit_factor", 0.0)
    if pf >= 2.0:
        drivers.append(f"Profit factor {pf:.1f}x signals strong risk-adjusted returns")
    return drivers[:6]  # cap at 6


# ── Public API ─────────────────────────────────────────────────────────────

_sentiment_cache: Optional[SentimentScore] = None


def get_sentiment(force_refresh: bool = False) -> SentimentScore:
    """
    Return the current gold market sentiment score.

    Parameters
    ----------
    force_refresh : bool
        When *True* the cached value is discarded and re-computed from the
        latest report file.

    Returns
    -------
    SentimentScore
        A dataclass with all fields consumed by the API endpoint.
    """
    global _sentiment_cache

    if not force_refresh and _sentiment_cache is not None:
        return _sentiment_cache

    report = _load_latest_report()

    if report is None:
        # Fallback — provide a neutral score with stale data marker
        now = datetime.now(timezone.utc).isoformat()
        _sentiment_cache = SentimentScore(
            score=0.0,
            bias="neutral",
            bullish_news=0,
            bearish_news=0,
            news_count=0,
            polymarket_risk=0.0,
            gold_trend="neutral",
            drivers=["No recent report available — fallback mode"],
            generated_at=now,
        )
        return _sentiment_cache

    score_val = _compute_score(report)
    bias = _compute_bias(score_val)
    gold_trend = _compute_gold_trend(report)

    # Derive "news" counts from pairs: count pairs with improving
    # (bullish) vs declining (bearish) signals
    pairs = report.get("pairs", {})
    bullish_count = sum(
        1 for p in pairs.values() if p.get("win_rate", 0.5) >= 0.4
    )
    bearish_count = sum(
        1 for p in pairs.values() if p.get("win_rate", 0.5) < 0.3
    )

    drivers = _compute_drivers(report)

    # Extract or default polymarket risk
    polymarket_risk = report.get("geopolitical", {}).get("risk", 0.35)

    generated_at = report.get("generated_at", datetime.now(timezone.utc).isoformat())

    _sentiment_cache = SentimentScore(
        score=score_val,
        bias=bias,
        bullish_news=bullish_count,
        bearish_news=bearish_count,
        news_count=bullish_count + bearish_count,
        polymarket_risk=polymarket_risk,
        gold_trend=gold_trend,
        drivers=drivers,
        generated_at=generated_at,
    )
    return _sentiment_cache
