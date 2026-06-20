"""
Sentiment Relevance Filter — Corrective RAG for AGENTX
Filters out irrelevant content from sentiment analysis.
Detects topic drift (e.g., physical gold jewelry news polluting XAUUSD trading sentiment).
Resolves source contradictions (news says bullish, Polymarket says bearish).

Usage:
    from sentiment_relevance import RelevanceFilter, resolve_contradictions
    filter = RelevanceFilter()
    article = {"title": "...", "summary": "...", "source": "Google News"}
    score, reason = filter.is_relevant(article)
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sentiment_relevance")

# ─── IRRELEVANT TOPICS (for XAUUSD trading) ───────────────────────────────────
# These topics are about physical gold, not gold trading/futures/CFDs
IRRELEVANT_PATTERNS = {
    # Physical gold / jewelry / retail
    "jewelry": re.compile(r"\b(jewelry|jewellery|necklace|bracelet|ring|wedding|engagement)\b", re.I),
    "physical_delivery": re.compile(r"\b(physical gold|gold bar|gold coin|bullion coin|gold sovereign)\b", re.I),
    "retail_gold": re.compile(r"\b(gold shop|gold rate today|22k|24k|carat|hallmark)\b", re.I),
    "festival": re.compile(r"\b(diwali|dhanteras|akshaya tritiya|onam|pongal|wedding season)\b", re.I),
    "gold_loan": re.compile(r"\b(gold loan|loan against gold|gold mortgage)\b", re.I),
    "mining_production": re.compile(r"\b(gold mine|gold mining|mining output|gold production|gold reserves?)\b", re.I),
    "country_local": re.compile(r"\b(indian gold|china gold|turkey gold|dubai gold|pakistan gold)\b", re.I),
}

# ─── RELEVANT TOPICS (for XAUUSD trading) ─────────────────────────────────────
RELEVANT_KEYWORDS = {
    "xauusd": re.compile(r"\b(XAUUSD|gold usd|gold price|gold futures|gold cfd|spot gold)\b", re.I),
    "central_bank": re.compile(r"\b(fed|federal reserve|interest rate|rate hike|rate cut|monetary policy)\b", re.I),
    "macro": re.compile(r"\b(inflation|CPI|PPI|GDP|nonfarm|unemployment|jobs report|NFP)\b", re.I),
    "geopolitical": re.compile(r"\b(geopolitical|war|sanctions|tariff|trade war|conflict|tension)\b", re.I),
    "dollar": re.compile(r"\b(DXY|dollar index|us dollar|dollar strength|dollar weakness)\b", re.I),
    "safe_haven": re.compile(r"\b(safe haven|risk off|risk aversion|flight to safety)\b", re.I),
    "technical": re.compile(r"\b(support|resistance|breakout|200 ma|50 ma|golden cross|death cross)\b", re.I),
    "market": re.compile(r"\b(comex|gold etf|GLD|IAU|gold fund|gold holding|speculative)\b", re.I),
}

# ─── CONTRADICTION DETECTION ──────────────────────────────────────────────────
CONTRADICTORY_PAIRS = [
    (re.compile(r"\b(rate hike|tightening|hawkish)\b", re.I),
     re.compile(r"\b(bullish|rally|surge|breakout)\b", re.I)),
    (re.compile(r"\b(rate cut|dovish|easing)\b", re.I),
     re.compile(r"\b(bearish|selloff|dump|crash)\b", re.I)),
    (re.compile(r"\b(safe haven|risk off)\b", re.I),
     re.compile(r"\b(sell.?off|liquidate|dump)\b", re.I)),
]


class RelevanceFilter:
    """Filters sentiment articles for relevance to XAUUSD trading."""

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self._stats = {"scanned": 0, "relevant": 0, "filtered": 0}

    def is_relevant(self, article: dict) -> tuple[bool, str]:
        """
        Check if an article is relevant for trading sentiment.
        Returns (is_relevant, reason).
        """
        self._stats["scanned"] += 1
        text = self._get_text(article)
        if not text:
            return False, "Empty article"

        # Check for irrelevant topics first
        for topic, pattern in IRRELEVANT_PATTERNS.items():
            if pattern.search(text):
                self._stats["filtered"] += 1
                return False, f"Irrelevant topic: {topic}"

        # Check for relevant keywords
        relevance_score = 0
        matched_topics = []
        for topic, pattern in RELEVANT_KEYWORDS.items():
            if pattern.search(text):
                relevance_score += 1
                matched_topics.append(topic)

        if relevance_score >= 2:
            self._stats["relevant"] += 1
            return True, f"Relevant ({relevance_score} matches: {', '.join(matched_topics)})"
        elif relevance_score == 1:
            # Single match — check for XAUUSD specifically
            if RELEVANT_KEYWORDS["xauusd"].search(text):
                self._stats["relevant"] += 1
                return True, f"Relevant (XAUUSD mentioned directly)"
            self._stats["filtered"] += 1
            return False, f"Only 1 weak match ({matched_topics[0]}), insufficient for trading signal"
        else:
            self._stats["filtered"] += 1
            return False, "No relevant financial/macro keywords detected"

    def _get_text(self, article: dict) -> str:
        """Extract searchable text from article."""
        parts = []
        for field in ["title", "summary", "content", "description", "headline"]:
            if field in article and article[field]:
                parts.append(str(article[field]))
        return " ".join(parts)

    def filter_articles(self, articles: list[dict]) -> list[dict]:
        """Filter a list of articles, returning only relevant ones."""
        relevant = []
        for article in articles:
            ok, reason = self.is_relevant(article)
            if ok:
                article["_relevance"] = reason
                relevant.append(article)
        return relevant

    def get_stats(self) -> dict:
        """Return filter statistics."""
        return {**self._stats, "filter_rate": f"{self._stats['filtered']/max(1,self._stats['scanned'])*100:.0f}%"}


def resolve_contradictions(sentiments: list[dict]) -> dict:
    """
    Detect and resolve contradictory signals across sentiment sources.
    Returns a consolidated verdict with confidence level.

    Example input:
        [{"source": "news", "bias": "BULLISH", "score": 5},
         {"source": "polymarket", "bias": "BEARISH", "score": -3}]
    """
    if not sentiments:
        return {"verdict": "NEUTRAL", "confidence": 0, "reason": "No data"}

    scores = [s.get("score", 0) for s in sentiments]
    bias_map = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0, "MIXED": 0}

    weighted = 0
    total_weight = 0
    contradictions = []

    for s in sentiments:
        bias_val = bias_map.get(s.get("bias", "NEUTRAL"), 0)
        score_val = s.get("score", 0)

        # Normalize and weight
        weight = 1.0
        if s.get("source") == "mt5_trend":
            weight = 1.5  # Price trend gets higher weight
        elif s.get("source") == "polymarket":
            weight = 0.8  # Prediction markets slightly discounted

        weighted += (bias_val * 0.3 + (score_val / 10) * 0.7) * weight
        total_weight += weight

    # Check contradictions between sources
    for i, a in enumerate(sentiments):
        for j, b in enumerate(sentiments):
            if i >= j:
                continue
            a_text = str(a.get("bias", "") + " " + str(a.get("summary", "")))
            b_text = str(b.get("bias", "") + " " + str(b.get("summary", "")))
            for pattern_a, pattern_b in CONTRADICTORY_PAIRS:
                if pattern_a.search(a_text) and pattern_b.search(b_text):
                    contradictions.append(f"{a.get('source','?')} says bullish, {b.get('source','?')} says bearish")

    avg_score = weighted / max(total_weight, 1)

    if avg_score > 2:
        verdict = "BULLISH"
    elif avg_score < -2:
        verdict = "BEARISH"
    elif avg_score > 0.5:
        verdict = "MILD_BULLISH"
    elif avg_score < -0.5:
        verdict = "MILD_BEARISH"
    else:
        verdict = "NEUTRAL"

    confidence = max(0, min(10, abs(avg_score) * 2))
    if contradictions:
        confidence *= 0.6  # Reduce confidence when sources contradict
        reason = f"Contradiction detected: {'; '.join(contradictions[:2])}"
    else:
        reason = f"Average score: {avg_score:.1f} across {len(sentiments)} sources"

    return {
        "verdict": verdict,
        "confidence": round(confidence, 1),
        "score": round(avg_score, 1),
        "contradictions": len(contradictions),
        "sources": len(sentiments),
        "reason": reason,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with sample articles
    rf = RelevanceFilter()

    test_articles = [
        {"title": "XAUUSD breaks above $2350 resistance on Fed rate cut hopes",
         "summary": "Gold futures rally as dollar weakens", "source": "Reuters"},
        {"title": "Gold jewelry prices rise ahead of Diwali festival in India",
         "summary": "22k gold rates today in Mumbai, Delhi, Chennai", "source": "India Times"},
        {"title": "Gold mining production increases at Barrick Gold operations",
         "summary": "Q1 output rises 5% year over year", "source": "Mining.com"},
        {"title": "Gold steady as traders await US jobs data",
         "summary": "XAUUSD consolidates near $2340 support", "source": "Bloomberg"},
        {"title": "Federal Reserve holds rates steady, gold pares gains",
         "summary": "Dollar index rises after hawkish Fed comments", "source": "CNBC"},
    ]

    print(f"\n{'='*60}")
    print("🔬 Sentiment Relevance Filter — Test")
    print(f"{'='*60}")
    for art in test_articles:
        relevant, reason = rf.is_relevant(art)
        status = "✅ RELEVANT" if relevant else "❌ FILTERED"
        print(f"  {status}: {art['title'][:60]}")
        print(f"    → {reason}")

    print(f"\n📊 Stats: {rf.get_stats()}")

    # Test contradiction resolution
    sentiments = [
        {"source": "news", "bias": "BULLISH", "score": 6,
         "summary": "Gold rallies on safe haven demand"},
        {"source": "polymarket", "bias": "BEARISH", "score": -4,
         "summary": "Rate hike expectations weigh on gold"},
        {"source": "mt5_trend", "bias": "BULLISH", "score": 3,
         "summary": "Price above 50 MA"},
    ]
    result = resolve_contradictions(sentiments)
    print(f"\n🔄 Contradiction Resolution:")
    print(f"  Verdict: {result['verdict']} (confidence: {result['confidence']}/10)")
    print(f"  Reason: {result['reason']}")
    print(f"  Contradictions: {result['contradictions']}")
