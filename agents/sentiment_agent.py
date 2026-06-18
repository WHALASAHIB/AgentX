import random
from typing import Dict, Any

class MarketSentimentAgent:
    def __init__(self):
        self.name = "MarketSentimentAgent"
        self.mock_headlines = [
            "Fed hints at potential rate cuts in upcoming quarters.",
            "Gold surges as geopolitical tensions remain elevated.",
            "Retail sales numbers show slight economic contraction.",
            "Treasury yields slide amidst global risk-off sentiment.",
            "Central bank buying of precious metals accelerates."
        ]

    def analyze_sentiment(self, symbol: str) -> str:
        """
        Parses external text feeds and evaluates sentiment.
        Returns 'POSITIVE', 'NEGATIVE', or 'NEUTRAL'.
        """
        headline = random.choice(self.mock_headlines)
        sentiment = random.choice(["POSITIVE", "NEUTRAL", "NEGATIVE"])
        
        # Simple rule: if gold surges, sentiment is positive for XAUUSD
        if "Gold surges" in headline and symbol == "XAUUSD":
            sentiment = "POSITIVE"
            
        return sentiment
