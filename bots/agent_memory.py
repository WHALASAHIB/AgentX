"""Agent Memory — persistent vector memory using TF-IDF embeddings (fully local).

Zero external API dependencies. Works offline from HK. No DLL issues.
Uses sklearn TfidfVectorizer + cosine similarity. Persists to JSON.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("AgentMemory")

MEMORY_FILE = Path(__file__).resolve().parent.parent / "agent_memory.json"


class AgentMemory:
    """Persistent TF-IDF vector memory for agent knowledge."""

    def __init__(self, memory_file: str | Path = MEMORY_FILE):
        self.memory_file = Path(memory_file)
        self.entries: list[dict] = []
        self._vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        self._vectors = None
        self._fitted = False
        self._load()

    def _load(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, encoding="utf-8") as f:
                    data = json.load(f)
                self.entries = data.get("entries", [])
                self._rebuild_index()
                logger.info("Loaded %d memory entries from %s", len(self.entries), self.memory_file)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load memory: %s", exc)
                self.entries = []

    def _save(self):
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            out = {"entries": []}
            for e in self.entries:
                clean = {k: v for k, v in e.items() if k != "_vector"}
                out["entries"].append(clean)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, default=str)
            logger.debug("Saved %d entries to %s", len(self.entries), self.memory_file)
        except OSError as exc:
            logger.error("Failed to save memory: %s", exc)

    def _rebuild_index(self):
        """Rebuild TF-IDF index from stored entries."""
        if not self.entries:
            self._vectors = None
            self._fitted = False
            return
        texts = [self._entry_text(e) for e in self.entries]
        self._vectors = self._vectorizer.fit_transform(texts)
        self._fitted = True

    @staticmethod
    def _entry_text(entry: dict) -> str:
        parts = [entry.get("key", "")]
        meta = entry.get("metadata", {})
        if isinstance(meta, dict):
            parts.extend(f"{k} {v}" for k, v in meta.items())
        parts.append(entry.get("text", ""))
        return " ".join(str(p) for p in parts if p)

    def store(self, key: str, metadata: dict, text: str = "") -> bool:
        """Store a memory entry with TF-IDF index."""
        entry = {
            "key": key,
            "metadata": metadata,
            "text": text,
            "timestamp": time.time(),
        }
        self.entries.append(entry)
        self._rebuild_index()
        self._save()
        logger.info("Stored memory: %s (%d total)", key, len(self.entries))
        return True

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search memory by TF-IDF similarity."""
        if not self.entries or not self._fitted:
            return []

        q_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self._vectors).flatten()
        top_idx = np.argsort(scores)[-top_k:][::-1]

        results = []
        for idx in top_idx:
            entry = self.entries[idx]
            results.append({
                "key": entry["key"],
                "metadata": entry["metadata"],
                "text": entry.get("text", ""),
                "score": float(scores[idx]),
                "timestamp": entry.get("timestamp", 0),
            })
        return results

    def get_by_key(self, key: str) -> Optional[dict]:
        for e in self.entries:
            if e["key"] == key:
                return e
        return None

    def count(self) -> int:
        return len(self.entries)

    def clear(self):
        self.entries = []
        self._vectors = None
        self._fitted = False
        self._save()
        logger.info("Memory cleared")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mem = AgentMemory()

    # Store FTMO rules
    mem.store("ftmo_rules", {
        "phase": "2-Step",
        "profit_target": "5% per phase",
        "daily_dd": "5% static",
        "max_loss": "10% static",
        "min_trading_days": 4,
    }, text="FTMO 2-Step Challenge Phase 1 and 2 each require 5% profit target. Max daily drawdown is 5% of initial balance. Max total drawdown is 10% static. Minimum 4 trading days per phase. No time limit. Consistency rule: best day cannot exceed 50% of total profit.")

    # Store propfirm pass strategy
    mem.store("propfirm_pass_strategy", {
        "type": "VWAP Mean Reversion",
        "symbol": "EURUSD",
        "session": "13:00-15:00 UTC",
        "magic": 780012,
    }, text="VWAP Deviation Mean Reversion on EURUSD during US Open. Entry: >=10 pip deviation from VWAP + 5M rejection candle. Momentum filter skips trend candles. Fixed SL 12 pips, TP 24 pips (1:2 RR). Max 2 trades/day, stop after 2 consecutive losses.")

    # Store risk management
    mem.store("risk_management", {
        "risk_per_trade": "1%",
        "max_daily_trades": 2,
        "max_consecutive_losses": 2,
        "account": "FTMO-100K",
    }, text="Risk 1% of account per trade. On $100K account, $1,000 risk per trade at 8.3 lots EURUSD. Stop after 2 consecutive losses (max $2,000 daily loss). FTMO static drawdown: 5% daily, 10% total.")

    # Store crawl4ai info
    mem.store("crawl4ai", {
        "type": "web_scraper",
        "version": "0.9.1",
        "license": "Apache-2.0",
    }, text="Crawl4AI is an async web crawler that converts web pages to clean LLM-ready Markdown. Installed via pip. Uses Playwright for JS rendering. Tested on FTMO rules page and ForexFactory calendar.")

    # Search tests
    queries = [
        "What is the profit target for FTMO?",
        "What strategy trades during US Open?",
        "How much risk per trade?",
        "What is crawl4ai?",
    ]

    print(f"Memory entries: {mem.count()}")
    print("=" * 50)

    for q in queries:
        results = mem.search(q, top_k=2)
        print(f"\nQuery: {q}")
        for r in results:
            print(f"  [{r['score']:.3f}] {r['key']}: {r['text'][:70]}...")

    print("\n✅ Agent memory fully operational")
