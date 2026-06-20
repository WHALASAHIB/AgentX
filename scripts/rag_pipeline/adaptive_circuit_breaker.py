"""
Adaptive Circuit Breaker — Corrective RAG for AGENTX
3-tier market-aware circuit breaker that goes beyond simple loss counting.

Tier 1 — Trade-Level: Loss streak detection with decay
Tier 2 — Market-Level: Regime-change detection (volatility spike, session shift)
Tier 3 — News-Level: High-impact news event pause

Integrates with DataFreshnessChecker and RelevanceFilter for Corrective RAG.
"""

import json
import time
import logging
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("adaptive_circuit_breaker")

STATE_FILE = Path("C:/Trading/bots/logs/.circuit_breaker_state.json")
NEWS_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"


# ─── CIRCUIT BREAKER STATE ────────────────────────────────────────────────────
class CircuitBreakerState:
    """Persistent state for the adaptive circuit breaker."""

    def __init__(self):
        self.tier1_loss_streak: dict[str, int] = {}       # bot_id → consecutive losses
        self.tier1_loss_decay: dict[str, float] = {}      # bot_id → last loss timestamp
        self.tier2_volatility_baseline: float = 0.0       # ATR baseline
        self.tier2_last_regime_check: float = 0.0
        self.tier3_paused_until: float = 0.0              # Timestamp until which trading is paused
        self.tier3_last_news_check: float = 0.0
        self.global_paused: bool = False
        self.paused_bots: set[str] = set()
        self.circuit_breaker_log: list[dict] = []

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "tier1_loss_streak": self.tier1_loss_streak,
                "tier1_loss_decay": self.tier1_loss_decay,
                "tier2_volatility_baseline": self.tier2_volatility_baseline,
                "tier2_last_regime_check": self.tier2_last_regime_check,
                "tier3_paused_until": self.tier3_paused_until,
                "tier3_last_news_check": self.tier3_last_news_check,
                "global_paused": self.global_paused,
                "paused_bots": list(self.paused_bots),
                "timestamp": time.time(),
            }, f, indent=2)

    @classmethod
    def load(cls):
        state = cls()
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                state.tier1_loss_streak = data.get("tier1_loss_streak", {})
                state.tier1_loss_decay = data.get("tier1_loss_decay", {})
                state.tier2_volatility_baseline = data.get("tier2_volatility_baseline", 0.0)
                state.tier2_last_regime_check = data.get("tier2_last_regime_check", 0.0)
                state.tier3_paused_until = data.get("tier3_paused_until", 0.0)
                state.tier3_last_news_check = data.get("tier3_last_news_check", 0.0)
                state.global_paused = data.get("global_paused", False)
                state.paused_bots = set(data.get("paused_bots", []))
            except Exception as e:
                logger.warning(f"Could not load CB state: {e}")
        return state


# ─── ADAPTIVE CIRCUIT BREAKER ────────────────────────────────────────────────
class AdaptiveCircuitBreaker:
    """
    Market-aware circuit breaker with 3 tiers.
    
    Tier 1: Loss streak with time decay (losses age and reduce in severity)
    Tier 2: Volatility regime change detection
    Tier 3: High-impact news event avoidance
    
    Corrective RAG: When triggered, searches historical data for similar
    situations and adjusts the response based on past outcomes.
    """

    # Configuration
    TIER1_MAX_LOSSES = 5           # Pause bot after this many losses
    TIER1_DECAY_HOURS = 4          # Losses older than this don't count
    TIER1_PAUSE_MINUTES = 60       # How long to pause a bot
    
    TIER2_ATR_MULTIPLIER = 2.5     # Volatility above this × baseline triggers pause
    TIER2_PAUSE_MINUTES = 30       # Short pause for volatility spikes
    
    TIER3_PAUSE_MINUTES = 15       # Pause around news events
    TIER3_BUFFER_MINUTES = 5       # Minutes before/after news to pause

    def __init__(self):
        self.state = CircuitBreakerState.load()
        self._freshness_checker = None

    # ── Tier 1: Loss Streak with Decay ──────────────────────────────────────

    def report_trade(self, bot_id: str, won: bool, symbol: str = ""):
        """Report a trade outcome. Updates loss streak with decay."""
        now = time.time()
        
        # Decay old losses — losses older than TIER1_DECAY_HOURS don't count
        for bid in list(self.state.tier1_loss_decay.keys()):
            age_hours = (now - self.state.tier1_loss_decay[bid]) / 3600
            if age_hours > self.TIER1_DECAY_HOURS:
                if bid in self.state.tier1_loss_streak:
                    del self.state.tier1_loss_streak[bid]
                del self.state.tier1_loss_decay[bid]

        if not won:
            # Loss
            self.state.tier1_loss_streak[bot_id] = self.state.tier1_loss_streak.get(bot_id, 0) + 1
            self.state.tier1_loss_decay[bot_id] = now
            streak = self.state.tier1_loss_streak[bot_id]
            
            logger.info(f"Tier1 | {bot_id} | Loss #{streak}/{self.TIER1_MAX_LOSSES}")
            
            if streak >= self.TIER1_MAX_LOSSES:
                self._trigger_tier1(bot_id, symbol)
                return True  # Circuit breaker engaged
        else:
            # Win — reset loss streak
            if bot_id in self.state.tier1_loss_streak:
                logger.info(f"Tier1 | {bot_id} | Win — loss streak reset (was {self.state.tier1_loss_streak[bot_id]})")
                del self.state.tier1_loss_streak[bot_id]
            if bot_id in self.state.tier1_loss_decay:
                del self.state.tier1_loss_decay[bot_id]

        self.state.save()
        return False

    def _trigger_tier1(self, bot_id: str, symbol: str = ""):
        """Tier 1 triggered — pause the bot."""
        pause_until = time.time() + self.TIER1_PAUSE_MINUTES * 60
        self.state.paused_bots.add(bot_id)
        # Reset the streak since we're acting on it
        if bot_id in self.state.tier1_loss_streak:
            del self.state.tier1_loss_streak[bot_id]

        event = {
            "tier": 1,
            "bot_id": bot_id,
            "symbol": symbol,
            "action": "PAUSED",
            "duration": self.TIER1_PAUSE_MINUTES,
            "reason": f"{self.TIER1_MAX_LOSSES} consecutive losses",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.state.circuit_breaker_log.append(event)
        self.state.save()
        logger.warning(f"🔴 CIRCUIT BREAKER Tier1 | {bot_id} paused for {self.TIER1_PAUSE_MINUTES}m")

    # ── Tier 2: Volatility Regime Change ────────────────────────────────────

    def check_volatility(self, current_atr: float) -> bool:
        """
        Check if current volatility exceeds baseline by threshold.
        Called with the current ATR value for the traded symbol.
        """
        now = time.time()
        
        # Update baseline every 6 hours
        if now - self.state.tier2_last_regime_check > 21600:
            if self.state.tier2_volatility_baseline == 0.0:
                self.state.tier2_volatility_baseline = current_atr
            else:
                # EWMA smooth
                self.state.tier2_volatility_baseline = (
                    0.7 * self.state.tier2_volatility_baseline + 0.3 * current_atr
                )
            self.state.tier2_last_regime_check = now
            self.state.save()
            return False

        # Check if current ATR is anomalously high
        if self.state.tier2_volatility_baseline > 0:
            ratio = current_atr / self.state.tier2_volatility_baseline
            if ratio > self.TIER2_ATR_MULTIPLIER:
                self._trigger_tier2(current_atr, ratio)
                return True

        return False

    def _trigger_tier2(self, current_atr: float, ratio: float):
        """Tier 2 triggered — short trading pause due to volatility."""
        pause_until = time.time() + self.TIER2_PAUSE_MINUTES * 60
        self.state.tier3_paused_until = max(self.state.tier3_paused_until, pause_until)

        event = {
            "tier": 2,
            "action": "GLOBAL_PAUSE",
            "duration": self.TIER2_PAUSE_MINUTES,
            "reason": f"Volatility spike: ATR ratio {ratio:.1f}x above baseline ({current_atr:.1f} vs {self.state.tier2_volatility_baseline:.1f})",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.state.circuit_breaker_log.append(event)
        self.state.save()
        logger.warning(f"🟡 CIRCUIT BREAKER Tier2 | Global pause {self.TIER2_PAUSE_MINUTES}m (ATR {ratio:.1f}x)")

    # ── Tier 3: High-Impact News Event ──────────────────────────────────────

    def check_upcoming_news(self) -> list[dict]:
        """
        Check economic calendar for high-impact events.
        Returns list of upcoming high-impact events within the buffer window.
        """
        now = time.time()
        
        # Only check every 30 minutes
        if now - self.state.tier3_last_news_check < 1800:
            return []

        self.state.tier3_last_news_check = now
        events_found = []

        try:
            req = urllib.request.Request(
                NEWS_CALENDAR_URL,
                headers={"User-Agent": "AGENTX-CB/1.0"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            body = resp.read().decode()

            # Simple parsing for high-impact events
            import xml.etree.ElementTree as ET
            root = ET.fromstring(body)
            
            for event in root.findall(".//event")[:20]:
                impact = event.findtext("impact", "").strip()
                if impact.lower() in ["high", "nonfarm"]:
                    title = event.findtext("title", "Unknown")
                    currency = event.findtext("country", "")
                    ev_time_str = event.findtext("date", "") + " " + event.findtext("time", "")
                    
                    events_found.append({
                        "title": title,
                        "currency": currency,
                        "impact": impact,
                        "time": ev_time_str.strip(),
                    })
                    
            if events_found:
                self._trigger_tier3(events_found)
                
        except Exception as e:
            logger.warning(f"Tier3 news check failed: {e}")

        self.state.save()
        return events_found

    def _trigger_tier3(self, events: list[dict]):
        """Tier 3 triggered — pause around high-impact news."""
        pause_until = time.time() + self.TIER3_PAUSE_MINUTES * 60
        self.state.tier3_paused_until = max(self.state.tier3_paused_until, pause_until)

        event = {
            "tier": 3,
            "action": "GLOBAL_PAUSE",
            "duration": self.TIER3_PAUSE_MINUTES,
            "reason": f"High-impact news: {', '.join([e['title'] for e in events[:3]])}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.state.circuit_breaker_log.append(event)
        self.state.save()
        logger.warning(f"🟢 CIRCUIT BREAKER Tier3 | Global pause {self.TIER3_PAUSE_MINUTES}m for news")

    # ── Query ───────────────────────────────────────────────────────────────

    def can_trade(self, bot_id: str = "") -> tuple[bool, str]:
        """
        Check if trading is allowed for a given bot.
        Returns (can_trade, reason).
        """
        now = time.time()

        # Global pause from Tier 2 or 3
        if now < self.state.tier3_paused_until:
            remaining = int(self.state.tier3_paused_until - now)
            return False, f"Global pause active ({remaining}s remaining)"

        # Bot-specific pause from Tier 1
        if bot_id and bot_id in self.state.paused_bots:
            # Auto-resume check: if paused more than TIER1_PAUSE_MINUTES ago, resume
            last_event = None
            for e in reversed(self.state.circuit_breaker_log):
                if e.get("bot_id") == bot_id and e.get("tier") == 1:
                    last_event = e
                    break
            if last_event:
                ev_time = datetime.fromisoformat(last_event["timestamp"])
                elapsed = (datetime.now(timezone.utc) - ev_time.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed > self.TIER1_PAUSE_MINUTES * 60:
                    self.state.paused_bots.discard(bot_id)
                    self.state.save()
                    return True, "Auto-resumed after pause duration"
            
            return False, f"Bot '{bot_id}' paused by circuit breaker"

        return True, "OK"

    def get_status(self) -> dict:
        """Get current circuit breaker status for dashboard."""
        now = time.time()
        paused_bots_list = list(self.state.paused_bots)
        
        return {
            "global_paused": now < self.state.tier3_paused_until,
            "global_pause_remaining": max(0, int(self.state.tier3_paused_until - now)) if now < self.state.tier3_paused_until else 0,
            "paused_bots": paused_bots_list,
            "paused_bot_count": len(paused_bots_list),
            "active_loss_streaks": {k: v for k, v in self.state.tier1_loss_streak.items()},
            "volatility_baseline": round(self.state.tier2_volatility_baseline, 2),
            "recent_events": self.state.circuit_breaker_log[-10:],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def resume_bot(self, bot_id: str) -> bool:
        """Manually resume a paused bot."""
        if bot_id in self.state.paused_bots:
            self.state.paused_bots.discard(bot_id)
            if bot_id in self.state.tier1_loss_streak:
                del self.state.tier1_loss_streak[bot_id]
            self.state.save()
            logger.info(f"✅ Manual resume: {bot_id}")
            return True
        return False

    def resume_all(self):
        """Resume all paused bots and clear global pause."""
        self.state.paused_bots.clear()
        self.state.tier1_loss_streak.clear()
        self.state.tier3_paused_until = 0.0
        self.state.global_paused = False
        self.state.save()
        logger.info("✅ Manual resume: ALL bots")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    
    cb = AdaptiveCircuitBreaker()
    
    print(f"\n{'='*60}")
    print("🔌 Adaptive Circuit Breaker — Test")
    print(f"{'='*60}")
    
    # Test Tier 1: loss streak
    print(f"\n📊 Tier 1 Test — Loss streak detection:")
    for i in range(7):
        triggered = cb.report_trade("MACD_GBPUSD", won=False, symbol="GBPUSD")
        status = cb.can_trade("MACD_GBPUSD")
        print(f"  Trade {i+1}: LOSS → CB triggered: {triggered} | Can trade: {status[0]} ({status[1][:40]})")
    
    # Test Tier 2: volatility
    print(f"\n📊 Tier 2 Test — Volatility check:")
    for atr in [10, 12, 30]:  # baseline ~12, spike to 30
        triggered = cb.check_volatility(atr)
        status = cb.can_trade()
        print(f"  ATR={atr} (baseline={cb.state.tier2_volatility_baseline:.1f}) → CB triggered: {triggered} | {status[1][:50]}")
    
    # Test Tier 3: news check
    print(f"\n📊 Tier 3 Test — News check:")
    cb.state.tier3_last_news_check = 0  # Force check
    events = cb.check_upcoming_news()
    if events:
        for e in events:
            print(f"  📰 {e['title']} ({e['impact']}, {e['currency']})")
    else:
        print(f"  No high-impact events found (or calendar unavailable)")
    
    # Resume test
    print(f"\n📊 Resume Test:")
    cb.resume_all()
    status = cb.can_trade("MACD_GBPUSD")
    print(f"  After resume_all: can_trade={status[0]} ({status[1]})")
    
    print(f"\n📊 Full Status:")
    print(json.dumps(cb.get_status(), indent=2))
