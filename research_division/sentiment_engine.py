"""
Sentiment Engine — real market sentiment from free financial news RSS feeds.
───────────────────────────────────────────────────────────────────────────────
Fetches headlines from multiple globally-accessible sources (no API keys),
scores them with a keyword dictionary, and caches results for 4 hours.

Sources used (all free, no auth required):
  - Google News RSS (XAUUSD, gold, forex, market search)
  - Yahoo Finance RSS (XAUUSD headline feed)
  - Investing.com RSS (forex news)

Sentiment scale: -10 (extremely bearish) to +10 (extremely bullish)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 4 * 60 * 60  # 4 hours
REQUEST_TIMEOUT = 15  # seconds per feed fetch

# ── Free RSS news feeds (globally accessible, no API keys) ──────────────────
NEWS_FEEDS = [
    # Google News — gold & forex search
    ("Google News Gold", "https://news.google.com/rss/search?q=XAUUSD+gold+market+outlook&hl=en-US&gl=US&ceid=US:en"),
    ("Google News Forex", "https://news.google.com/rss/search?q=forex+market+currency+major+pairs+outlook&hl=en-US&gl=US&ceid=US:en"),
    # Yahoo Finance — XAUUSD headline feed
    ("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=XAUUSD&region=US&lang=en-US"),
    # Investing.com — forex news
    ("Investing.com", "https://www.investing.com/rss/news_301.rss"),
]

# ── Keyword Sentiment Scoring ────────────────────────────────────────────────
# Each keyword maps to a score adjustment. Title matches are case-insensitive.
# Positive = bullish for gold/markets, Negative = bearish for gold/markets.
SENTIMENT_KEYWORDS: dict[str, float] = {
    # 🟢 Strong Bullish
    "surge": 2.0, "surges": 2.0, "surged": 2.0,
    "soar": 2.0, "soars": 2.0, "soared": 2.0,
    "rally": 2.0, "rallies": 2.0, "rallied": 2.0,
    "breakout": 2.0, "break out": 2.0,
    "record high": 2.5, "all-time high": 2.5, "new high": 2.0,
    "skyrocket": 2.5, "skyrockets": 2.5, "skyrocketed": 2.5,
    "explode": 2.0, "explodes": 2.0,
    "boom": 2.0, "booming": 2.0,
    "bull run": 2.5, "bull market": 2.0,
    # 🟢 Moderate Bullish
    "gain": 1.0, "gains": 1.0, "gained": 1.0,
    "rise": 1.0, "rises": 1.0, "rose": 1.0, "rising": 1.0,
    "climb": 1.0, "climbs": 1.0, "climbed": 1.0,
    "jump": 1.5, "jumps": 1.5, "jumped": 1.5,
    "upside": 1.0, "uptick": 1.0, "uptrend": 1.0,
    "recovery": 1.0, "rebound": 1.5, "rebounds": 1.5,
    "positive outlook": 1.5, "optimistic": 1.0,
    "rate cut": 2.0, "cuts rate": 2.0, "easing": 1.5,
    "stimulus": 1.5, "safe haven": 1.5, "inflation hedge": 1.5,
    "outperform": 1.0, "outperformance": 1.0,
    "buy": 1.0, "buying": 1.0, "bullish": 2.0,
    "support": 0.5, "holds support": 1.0, "bounce": 1.0,
    "upgrade": 1.0, "overweight": 1.0,
    "demand spike": 1.5, "supply crunch": 1.5,
    # 🔴 Strong Bearish
    "crash": -2.5, "crashes": -2.5, "crashed": -2.5,
    "plunge": -2.0, "plunges": -2.0, "plunged": -2.0,
    "collapse": -2.5, "collapses": -2.5, "collapsed": -2.5,
    "tumble": -2.0, "tumbles": -2.0, "tumbled": -2.0,
    "dump": -2.0, "dumps": -2.0, "dumped": -2.0,
    "freefall": -2.5, "free fall": -2.5,
    "record low": -2.5, "new low": -2.0, "all-time low": -2.5,
    "meltdown": -2.5, "sell-off": -2.0, "selloff": -2.0,
    "bear market": -2.0, "bearish": -2.0,
    "liquidation": -2.0, "liquidations": -2.0,
    # 🔴 Moderate Bearish
    "decline": -1.0, "declines": -1.0, "declined": -1.0,
    "drop": -1.0, "drops": -1.0, "dropped": -1.0,
    "fall": -1.0, "falls": -1.0, "fell": -1.0, "falling": -1.0,
    "slip": -0.5, "slips": -0.5, "slipped": -0.5,
    "slide": -1.0, "slides": -1.0, "slid": -1.0,
    "downside": -1.0, "downtick": -1.0, "downtrend": -1.0,
    "correction": -1.5, "recession": -2.0,
    "negative outlook": -1.5, "pessimistic": -1.0,
    "rate hike": -2.0, "hikes rate": -2.0, "tightening": -1.5,
    "inflation fear": -1.5, "inflation worry": -1.5,
    "geopolitical risk": -1.5, "escalation": -1.5,
    "downgrade": -1.0, "underweight": -1.0,
    "slump": -1.5, "slumps": -1.5, "slumped": -1.5,
    "weakness": -1.0, "weak": -0.5,
    "fear": -1.0, "fears": -1.0, "panic": -1.5,
    "sell": -1.0, "selling": -1.0, "sell-off": -1.5,
    "resistance": -0.5, "reject": -0.5, "rejection": -0.5,
}

# ── Data model ──────────────────────────────────────────────────────────────

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
    # Bot stats (factual context, not sentiment source)
    total_pnl: float = 0.0
    win_rate: float = 0.0
    open_positions: int = 0
    running_bots: int = 0
    total_bots: int = 0
    running_ratio: float = 0.0

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "bias": self.bias,
            "news": {
                "bullish": self.bullish_news,
                "bearish": self.bearish_news,
                "total": self.news_count,
            },
            "geopolitical_risk": round(self.polymarket_risk, 2),
            "gold_trend": self.gold_trend,
            "drivers": self.drivers,
            "generated_at": self.generated_at,
            "real_data": {
                "total_pnl": self.total_pnl,
                "win_rate": round(self.win_rate * 100, 1),
                "open_positions": self.open_positions,
                "running_bots": self.running_bots,
                "total_bots": self.total_bots,
                "running_ratio": self.running_ratio,
            },
        }


# ── Cache ────────────────────────────────────────────────────────────────────

_sentiment_cache: Optional[SentimentScore] = None
_cache_time: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════

async def get_sentiment(force_refresh: bool = False) -> SentimentScore:
    """Return sentiment score. Cached for 4 hours unless force_refresh=True."""
    global _sentiment_cache, _cache_time

    now = datetime.now(timezone.utc).isoformat()
    now_ts = time.time()

    # Return cache if fresh
    if not force_refresh and _sentiment_cache is not None:
        elapsed = now_ts - _cache_time
        if elapsed < CACHE_TTL_SECONDS:
            remaining = int(CACHE_TTL_SECONDS - elapsed)
            logger.debug("Sentiment cache hit (%d seconds remaining)", remaining)
            return _sentiment_cache

    try:
        result = await _fetch_news_sentiment()
        _sentiment_cache = result
        _cache_time = now_ts
        logger.info("Sentiment refreshed: score=%.1f bias=%s drivers=%d",
                     result.score, result.bias, len(result.drivers))
        return result
    except Exception as exc:
        logger.error("Sentiment fetch failed", exc_info=True)
        # Return stale cache if available, otherwise fallback
        if _sentiment_cache is not None:
            logger.info("Sentiment: returning stale cache")
            return _sentiment_cache
        return SentimentScore(
            score=0.0, bias="neutral",
            gold_trend="neutral",
            drivers=[f"News fetch unavailable: {exc}"],
            generated_at=now,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  News Fetching & Scoring
# ═══════════════════════════════════════════════════════════════════════════════

async def _fetch_news_sentiment() -> SentimentScore:
    """Fetch news from all RSS feeds, score headlines, return aggregated result."""
    all_headlines: list[dict] = []
    feed_errors: list[str] = []

    for feed_name, feed_url in NEWS_FEEDS:
        try:
            logger.info("Fetching news from %s ...", feed_name)
            raw = await _fetch_rss(feed_url)
            if raw is None:
                feed_errors.append(f"{feed_name}: no data")
                continue
            for entry in raw:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = entry.get("summary", "") or ""
                published = entry.get("published", "")
                if not title or len(title) < 10:
                    continue
                score, matched = _score_title(title)
                all_headlines.append({
                    "title": title,
                    "link": link,
                    "summary": summary[:200],
                    "score": score,
                    "matched": matched,
                    "source": feed_name,
                    "published": published,
                })
            logger.info("  %s: %d headlines", feed_name, len(raw) if raw else 0)
        except Exception as exc:
            feed_errors.append(f"{feed_name}: {exc}")
            logger.warning("Failed to fetch %s: %s", feed_name, exc)

    logger.info("Total fetched: %d headlines from %d feeds",
                len(all_headlines), len(NEWS_FEEDS))

    if not all_headlines:
        return SentimentScore(
            score=0.0, bias="neutral",
            gold_trend="neutral",
            drivers=feed_errors or ["No news data available"],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Aggregate scoring ────────────────────────────────────────────────
    total_score = sum(h["score"] for h in all_headlines)
    abs_score = sum(abs(h["score"]) for h in all_headlines)

    # Normalised sentiment: average per-headline, clamped to [-10, +10]
    normalized = max(-10.0, min(10.0, total_score / max(len(all_headlines), 1) * 3.0))
    score = round(normalized, 1)

    # Bias
    bias = "neutral"
    if score >= 2.0:
        bias = "bullish"
    elif score <= -2.0:
        bias = "bearish"

    # Count bullish/bearish headlines
    bullish_count = sum(1 for h in all_headlines if h["score"] > 0)
    bearish_count = sum(1 for h in all_headlines if h["score"] < 0)

    # ── Gold trend from keyword analysis ─────────────────────────────────
    gold_trend = _compute_gold_trend(all_headlines)

    # ── Impactful drivers (top 5 most extreme-scoring headlines) ─────────
    sorted_headlines = sorted(all_headlines, key=lambda h: abs(h["score"]), reverse=True)
    drivers = []
    for h in sorted_headlines[:5]:
        direction = "🟢" if h["score"] > 0 else "🔴" if h["score"] < 0 else "🟡"
        drivers.append(f"{direction} {h['title'][:120]}")
    if feed_errors:
        drivers.append(f"ℹ️ {len(feed_errors)} feed(s) unavailable")

    # ── Geopolitical risk proxy ──────────────────────────────────────────
    risk_terms = ["geopolitical", "escalation", "war", "conflict", "sanction",
                  "crisis", "tariff", "trade war", "invasion", "nuclear",
                  "shutdown", "default", "debt ceiling"]
    risk_score = 0.0
    for h in all_headlines:
        lower = h["title"].lower()
        for term in risk_terms:
            if term in lower:
                risk_score += 0.25
    geop_risk = round(min(1.0, risk_score / 5.0), 2)

    now = datetime.now(timezone.utc).isoformat()

    return SentimentScore(
        score=score,
        bias=bias,
        bullish_news=bullish_count,
        bearish_news=bearish_count,
        news_count=len(all_headlines),
        polymarket_risk=geop_risk,
        gold_trend=gold_trend,
        drivers=drivers[:6],
        generated_at=now,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

async def _fetch_rss(url: str) -> Optional[list[dict]]:
    """Fetch and parse an RSS feed asynchronously. Returns list of entry dicts or None."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        if feed.bozo and not feed.entries:
            logger.warning("RSS parse error for %s: %s", url, feed.bozo_exception)
        return feed.entries if feed.entries else None
    except Exception as exc:
        logger.debug("RSS fetch failed for %s: %s", url, exc)
        return None


def _score_title(title: str) -> tuple[float, list[str]]:
    """Score a headline using the keyword dictionary.
    Returns (total_score, list_of_matched_terms).

    Keywords are sorted by descending length so longer, more specific terms
    (e.g. 'skyrocketed') match before shorter substrings ('skyrocket'),
    preventing double-counting.
    """
    lower = title.lower()
    total = 0.0
    matched: list[str] = []
    # Sort by descending length so longer terms (more specific) match first
    for keyword in sorted(SENTIMENT_KEYWORDS, key=len, reverse=True):
        value = SENTIMENT_KEYWORDS[keyword]
        if keyword in lower:
            # Skip if already matched by a longer term containing this one
            if not any(keyword in m for m in matched):
                total += value
                matched.append(keyword)
    return round(total, 1), matched


def _compute_gold_trend(headlines: list[dict]) -> str:
    """Determine gold trend direction from headline scoring."""
    # Only consider headlines with gold/XAU/commodity mentions
    gold_keywords = ["gold", "xauusd", "xau", "bullion", "precious metal",
                     "commodity", "metals"]
    relevant = [h for h in headlines if any(
        kw in h["title"].lower() for kw in gold_keywords
    )]
    if not relevant:
        relevant = headlines  # fall back to all if no gold-specific

    avg = sum(h["score"] for h in relevant) / max(len(relevant), 1)
    if avg >= 1.5:
        return "uptrend"
    elif avg >= 0.5:
        return "slight uptrend"
    elif avg <= -1.5:
        return "downtrend"
    elif avg <= -0.5:
        return "slight downtrend"
    return "neutral"
