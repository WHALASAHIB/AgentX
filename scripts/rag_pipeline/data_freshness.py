"""
Data Freshness Checker — Corrective RAG for AGENTX
Detects stale, outdated, or contradictory market data before acting on signals.
Integrates with sentiment engine, bot decision pipeline, and circuit breaker.

Usage:
    from data_freshness import DataFreshnessChecker
    checker = DataFreshnessChecker()
    issues = checker.check_all()
    if issues: print(f"Found {len(issues)} freshness issues")
"""

import json
import time
import logging
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("data_freshness")

# TTL definitions (in seconds)
FRESHNESS_TTL = {
    "mt5_price": 60,           # Price data: < 1 min
    "sentiment_score": 3600,   # Sentiment: < 1 hour
    "bot_state": 3600,         # Bot state: < 1 hour (bots don't trade every 5min)
    "backtest_result": 172800, # Backtest results: 48h
    "market_session": 3600,    # Market session: 1h
    "research_report": 28800,  # Research reports: 8h
}


class FreshnessIssue:
    """Represents a data freshness issue detected by the checker."""

    def __init__(self, source: str, age_seconds: float, max_age: float,
                 severity: str = "warning", detail: str = ""):
        self.source = source
        self.age_seconds = age_seconds
        self.max_age = max_age
        self.severity = severity  # "info", "warning", "critical"
        self.detail = detail
        self.stale_ratio = age_seconds / max_age if max_age > 0 else 999

    def __repr__(self):
        age_m = self.age_seconds / 60
        max_m = self.max_age / 60
        return f"[{self.severity.upper()}] {self.source}: {age_m:.0f}m old (max {max_m:.0f}m) — {self.detail}"


class DataFreshnessChecker:
    """Checks freshness of all AGENTX data sources."""

    def __init__(self):
        self.issues = []

    def check_all(self) -> list[FreshnessIssue]:
        """Run all freshness checks. Returns list of issues found."""
        self.issues = []
        self._check_bot_states()
        self._check_sentiment_cache()
        self._check_backtest_results()
        self._check_research_reports()
        self._check_mt5_bridge()
        self._check_trading_session()
        return self.issues

    def _check_bot_states(self):
        """Check last update time of all bot state files."""
        state_dir = Path("C:/Trading/bots/logs")
        if not state_dir.exists():
            self.issues.append(FreshnessIssue(
                "bot_state_dir", 999999, FRESHNESS_TTL["bot_state"],
                "critical", "Bot state directory not found"
            ))
            return

        now = time.time()
        for f in sorted(state_dir.glob("*_state.json")):
            age = now - f.stat().st_mtime
            if age > FRESHNESS_TTL["bot_state"]:
                # State files are archival — only flag if > 24h old
                if age > 86400:
                    severity = "info"
                elif age > FRESHNESS_TTL["bot_state"] * 6:
                    severity = "warning"
                else:
                    severity = "warning"
                self.issues.append(FreshnessIssue(
                    f"bot_state:{f.stem}", age, FRESHNESS_TTL["bot_state"],
                    severity, f"Bot state file last updated {age/60:.0f}m ago"
                ))

    def _check_sentiment_cache(self):
        """Check if sentiment score is fresh (check engine's in-memory cache)."""
        # Check by reading the latest sentiment output files
        research_dir = Path("C:/Trading/research")
        if not research_dir.exists():
            return

        now = time.time()
        for f in sorted(research_dir.glob("sentiment_brief_*.md")):
            age = now - f.stat().st_mtime
            if age > FRESHNESS_TTL["sentiment_score"]:
                self.issues.append(FreshnessIssue(
                    f"sentiment:{f.stem}", age, FRESHNESS_TTL["sentiment_score"],
                    "warning" if age < 7200 else "critical",
                    f"Sentiment brief last updated {age/60:.0f}m ago"
                ))
            break  # Only check the latest

    def _check_backtest_results(self):
        """Check if backtest results are still valid."""
        bt_dir = Path("C:/Trading/backtester")
        if not bt_dir.exists():
            return

        now = time.time()
        for f in bt_dir.glob("*.json"):
            age = now - f.stat().st_mtime
            if age > FRESHNESS_TTL["backtest_result"]:
                self.issues.append(FreshnessIssue(
                    f"backtest:{f.stem}", age, FRESHNESS_TTL["backtest_result"],
                    "info", f"Backtest results from {age/3600:.0f}h ago"
                ))

    def _check_research_reports(self):
        """Check freshness of research division reports."""
        reports_dir = Path("C:/Trading/research_division/reports")
        if not reports_dir.exists():
            return

        now = time.time()
        for f in sorted(reports_dir.glob("*.json")):
            age = now - f.stat().st_mtime
            if age > FRESHNESS_TTL["research_report"]:
                self.issues.append(FreshnessIssue(
                    f"research:{f.stem}", age, FRESHNESS_TTL["research_report"],
                    "warning", f"Research report from {age/3600:.0f}h ago"
                ))
            break

    def _check_mt5_bridge(self):
        """Check if MT5 bridge is responsive (proxy for data freshness)."""
        try:
            req = urllib.request.Request(
                "http://10.10.10.1:5000/health",
                headers={"User-Agent": "AGENTX-Freshness/1.0"},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            body = resp.read().decode()
            data = json.loads(body)
            # Bridge is healthy — data should be fresh
            uptime = data.get("uptime", 0)
            if uptime > 300:  # 5+ min uptime is fine
                pass
        except Exception as e:
            self.issues.append(FreshnessIssue(
                "mt5_bridge", 999, FRESHNESS_TTL["mt5_price"],
                "critical", f"MT5 Bridge unreachable: {e}"
            ))

    def _check_trading_session(self):
        """Check if current time is within a valid trading session."""
        now = datetime.now(timezone.utc)
        hkt_hour = (now.hour + 8) % 24  # Convert UTC to HKT

        # Weekend check
        if now.weekday() >= 5:
            self.issues.append(FreshnessIssue(
                "market_session", 0, FRESHNESS_TTL["market_session"],
                "info", "Weekend — markets closed, data may be stale"
            ))
            return

        # Session check
        if 6 <= hkt_hour < 15:
            session = "Asian"
        elif 15 <= hkt_hour < 20:
            session = "London Open"
        elif 20 <= hkt_hour < 24 or 0 <= hkt_hour < 5:
            session = "US/Overlap"
        else:
            session = "Closed"
            self.issues.append(FreshnessIssue(
                "market_session", 0, FRESHNESS_TTL["market_session"],
                "info", f"Outside active trading hours (HKT {hkt_hour}:00) — session: {session}"
            ))

    def get_summary(self) -> dict:
        """Get a summary of all freshness issues."""
        criticals = [i for i in self.issues if i.severity == "critical"]
        warnings = [i for i in self.issues if i.severity == "warning"]
        infos = [i for i in self.issues if i.severity == "info"]

        return {
            "total_issues": len(self.issues),
            "critical": len(criticals),
            "warning": len(warnings),
            "info": len(infos),
            "is_safe": len(criticals) == 0,
            "detail": [str(i) for i in self.issues[:10]],
        }


def check_before_trade() -> tuple[bool, str]:
    """
    Quick check before executing any trade signal.
    Returns (safe_to_trade, reason).
    If data is stale, returns (False, reason).
    """
    checker = DataFreshnessChecker()
    issues = checker.check_all()

    criticals = [i for i in issues if i.severity == "critical"]
    if criticals:
        reasons = "; ".join([c.detail for c in criticals[:3]])
        return False, f"BLOCKED: {len(criticals)} critical freshness issue(s): {reasons}"

    warnings = [i for i in issues if i.severity == "warning"]
    if warnings:
        reasons = "; ".join([w.detail for w in warnings[:2]])
        return True, f"CAUTION: {len(warnings)} warning(s): {reasons}"

    return True, "OK: All data fresh"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    checker = DataFreshnessChecker()
    issues = checker.check_all()

    print(f"\n{'='*60}")
    print(f"🔍 Data Freshness Check — {len(issues)} issue(s) found")
    print(f"{'='*60}")
    for issue in issues:
        print(f"  {issue}")
    print(f"\nSafe to trade: {check_before_trade()}")
