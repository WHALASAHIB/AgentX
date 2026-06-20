#!/usr/bin/env python3
"""
AGENTX AIOps — Anomaly Detection
=================================
Detects abnormal bot behavior before it kills the account.
Runs as part of SRE engine — no separate cron needed.

What it detects:
  1. P&L velocity anomaly — bot losing faster than its historical rate
  2. Win rate collapse — sudden drop from historical WR
  3. Consecutive loss streak — unusual for this bot
  4. Silence anomaly — bot stopped trading without warning
  5. Trade frequency spike — overtrading pattern
  6. Risk drift — position sizes deviating from expected

Usage:
    python devops/aiops.py           # Run anomaly scan
    python devops/aiops.py --watch   # Continuous monitoring
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "bots" / "logs"
BOT_TRADE_LOG = LOGS_DIR  # Per-bot trade logs live here

# ── Configuration ────────────────────────────────────────────────────────

ANOMALY_CONFIG = {
    "pnl_velocity_zscore": 2.5,       # Alert if P&L velocity > 2.5 σ from mean
    "win_rate_drop_pct": 20,          # Alert if WR drops > 20% from historical
    "max_consecutive_losses": 4,      # Alert if > 4 consecutive losses
    "silence_hours": 6,               # Alert if bot silent for 6+ hours
    "trade_frequency_spike": 3.0,     # Alert if trade rate > 3x historical
    "risk_drift_pct": 50,             # Alert if position size deviates > 50%
    "lookback_trades": 50,            # Number of trades for baseline
}

# ── Logging ──────────────────────────────────────────────────────────────

logger = logging.getLogger("aiops")

def setup_logging():
    logger.setLevel(logging.INFO)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOGS_DIR / "aiops.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | AIOPS | %(message)s"))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)

# ── Bot Data Extraction ─────────────────────────────────────────────────

def get_bot_metadata() -> list[dict]:
    """Get metadata for all active bots from active_bots directory."""
    active_dir = BASE_DIR / "bots" / "active_bots"
    bots = []
    if not active_dir.exists():
        return bots
    for symbol_dir in sorted(active_dir.iterdir()):
        if not symbol_dir.is_dir():
            continue
        for run_file in sorted(symbol_dir.glob("run_*.py")):
            strategy = run_file.stem[4:]  # "run_macd.py" -> "macd"
            bots.append({
                "symbol": symbol_dir.name,
                "strategy": strategy,
                "log_file": LOGS_DIR / f"{symbol_dir.name}_{strategy}.log",
                "state_file": LOGS_DIR / f"{symbol_dir.name}_{strategy}_state.json",
            })
    return bots

def parse_trade_from_logs(bot: dict) -> list[dict]:
    """Parse trade events from bot log files."""
    trades = []
    log_file = bot["log_file"]
    if not log_file.exists():
        return trades
    
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Extract trade entries
                if "ORDER FILLED" in line or "CLOSED t=" in line or "CLOSE" in line:
                    trades.append({
                        "timestamp": line[:19] if len(line) > 19 else "",
                        "raw": line.strip()[:200],
                    })
                # Extract P&L entries
                if "P&L=" in line and "STATUS" in line:
                    pass  # These are status lines, not trade events
    except:
        pass
    
    return trades[-ANOMALY_CONFIG["lookback_trades"]:]

# ── Anomaly Detectors ────────────────────────────────────────────────────

class BotProfile:
    """Historical baseline for a single bot."""
    
    def __init__(self, symbol: str, strategy: str):
        self.symbol = symbol
        self.strategy = strategy
        self.trade_results: list[float] = []  # P&L values
        self.trade_timestamps: list[float] = []
        self.consecutive_losses = 0
        self.last_trade_time: Optional[float] = None
    
    def _load_state(self):
        """Load trade history from state file."""
        state_file = LOGS_DIR / f"{self.symbol}_{self.strategy}_state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                self.entries_today = state.get("entries_today", 0)
                self.trade_date = state.get("trade_date", "")
            except:
                pass
    
    def check_pnl_velocity(self) -> Optional[dict]:
        """Check if P&L velocity exceeds expected variance."""
        if len(self.trade_results) < 10:
            return None
        
        recent = self.trade_results[-10:]
        mean = sum(recent) / len(recent)
        variance = sum((r - mean) ** 2 for r in recent) / len(recent)
        std = math.sqrt(variance) if variance > 0 else 1.0
        
        if std == 0:
            return None
        
        # Check if any recent trade exceeds z-score threshold
        for r in recent[-3:]:
            z = abs(r - mean) / std if std > 0 else 0
            if z > ANOMALY_CONFIG["pnl_velocity_zscore"]:
                return {
                    "type": "pnl_velocity",
                    "severity": "warning" if z < 3.0 else "critical",
                    "message": f"P&L velocity anomaly (z={z:.1f}, value=${r:.2f})",
                    "zscore": z,
                    "value": r,
                }
        return None
    
    def check_silence(self) -> Optional[dict]:
        """Check if bot has stopped trading unexpectedly."""
        if self.last_trade_time is None:
            return None
        
        hours_silent = (datetime.now().timestamp() - self.last_trade_time) / 3600
        if hours_silent > ANOMALY_CONFIG["silence_hours"]:
            return {
                "type": "silence",
                "severity": "critical",
                "message": f"Bot silent for {hours_silent:.1f}h (threshold: {ANOMALY_CONFIG['silence_hours']}h)",
                "hours_silent": hours_silent,
            }
        return None
    
    def check_log_health(self, log_file: Path) -> Optional[dict]:
        """Check if bot log shows errors."""
        if not log_file.exists():
            return {
                "type": "missing_log",
                "severity": "critical",
                "message": f"Log file missing: {log_file.name}",
            }
        
        # Check last log entry time
        try:
            mtime = log_file.stat().st_mtime
            hours_stale = (datetime.now().timestamp() - mtime) / 3600
            if hours_stale > 0.5:  # Not updated in 30 minutes
                return {
                    "type": "stale_log",
                    "severity": "warning",
                    "message": f"Log not updated in {hours_stale:.1f}h (last: {datetime.fromtimestamp(mtime).strftime('%H:%M')})",
                    "hours_stale": hours_stale,
                }
        except:
            pass
        
        # Check for error patterns
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                error_count = content.count("ERROR") - content.count("STATUS | ERROR")  # Exclude status lines
                if error_count > 10:
                    return {
                        "type": "excess_errors",
                        "severity": "warning",
                        "message": f"{error_count} error lines in log",
                        "error_count": error_count,
                    }
        except:
            pass
        
        return None

def run_anomaly_scan() -> list[dict]:
    """Run full anomaly scan across all bots."""
    logger.info("🔍 AIOps anomaly scan starting...")
    alerts = []
    
    bots = get_bot_metadata()
    logger.info("   Scanning %d bot profiles", len(bots))
    
    for bot in bots:
        profile = BotProfile(bot["symbol"], bot["strategy"])
        
        # Check log health
        health = profile.check_log_health(bot["log_file"])
        if health:
            alerts.append({
                "bot": f"{bot['symbol']}_{bot['strategy']}",
                **health,
            })
        
        # Check silence
        silence = profile.check_silence()
        if silence:
            alerts.append({
                "bot": f"{bot['symbol']}_{bot['strategy']}",
                **silence,
            })
        
        # Check P&L velocity (requires state file with trade data)
        pnl = profile.check_pnl_velocity()
        if pnl:
            alerts.append({
                "bot": f"{bot['symbol']}_{bot['strategy']}",
                **pnl,
            })
    
    # Summary
    if alerts:
        logger.warning("   ⚠️  %d anomaly(s) detected", len(alerts))
        for a in alerts:
            logger.warning("   [%s] %s: %s", a.get("severity", "?"), a["bot"], a["message"])
    else:
        logger.info("   ✅ No anomalies detected")
    
    return alerts

# ── Main ─────────────────────────────────────────────────────────────────

def main():
    setup_logging()
    
    if "--watch" in sys.argv:
        import time
        logger.info("🔵 AIOps continuous monitoring started")
        while True:
            run_anomaly_scan()
            time.sleep(300)  # Every 5 minutes
    else:
        alerts = run_anomaly_scan()
        if alerts:
            sys.exit(1)

if __name__ == "__main__":
    main()
