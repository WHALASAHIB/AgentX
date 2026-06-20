#!/usr/bin/env python3
"""
AGENTX AgentOps — Agent Decision Logger
========================================
Structured logging for agent decisions, failures, and workflows.
When a cron job or agent makes a decision, this logs WHY.
Enables debugging failed agent runs without replaying the entire session.

Usage:
    from devops.agentops import log_decision, log_failure, Decision

    # Log a trading decision
    log_decision(
        agent="MACD_GBPUSD",
        decision="ENTER_LONG",
        reason="MACD crossover + ADX > 25",
        context={"price": 1.3245, "adx": 28, "signal_strength": "strong"}
    )

    # Log a failure
    log_failure(
        agent="SentimentPipeline",
        error="HTTP 403 fetching Reddit RSS",
        category="network",
        recoverable=True
    )
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "bots" / "logs"
DECISION_LOG = LOGS_DIR / "agent_decisions.jsonl"
FAILURE_LOG = LOGS_DIR / "agent_failures.jsonl"
METRICS_LOG = LOGS_DIR / "agent_metrics.jsonl"

# ── Decision Categories ─────────────────────────────────────────────────

DECISION_CATEGORIES = {
    "ENTER_TRADE": "Bot entered a position",
    "EXIT_TRADE": "Bot closed a position",
    "SKIP_TRADE": "Bot chose not to trade (filter blocked)",
    "CIRCUIT_BREAKER": "Circuit breaker activated",
    "RECONNECT": "Service reconnected after failure",
    "CONFIG_CHANGE": "Configuration was modified",
    "DEPLOY": "Code deployment occurred",
    "SCHEDULE": "Cron job execution decision",
}

FAILURE_CATEGORIES = {
    "network": "Network timeout, DNS, HTTP error",
    "mt5": "MT5 terminal, IPC, or symbol error",
    "auth": "Authentication or credential error",
    "resource": "Memory, CPU, disk exhaustion",
    "logic": "Business logic error in strategy",
    "config": "Configuration or parameter error",
    "unknown": "Unclassified error",
}

# ── Logging ──────────────────────────────────────────────────────────────

_logger = logging.getLogger("agentops")

def _ensure_logs():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Decision Logging ─────────────────────────────────────────────────────

def log_decision(
    agent: str,
    decision: str,
    reason: str,
    context: Optional[dict] = None,
    outcome: Optional[str] = None,
    source: str = "system",
) -> dict:
    """
    Log an agent decision with structured data.
    
    Args:
        agent: Agent name (e.g., "MACD_GBPUSD", "SRE_Engine")
        decision: What was decided (use DECISION_CATEGORIES keys)
        reason: WHY the decision was made (free text)
        context: Key-value data relevant to the decision
        outcome: "success", "failure", "pending"
        source: "system", "cron", "manual"
    
    Returns:
        The logged entry dict
    """
    _ensure_logs()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "decision",
        "agent": agent,
        "decision": decision,
        "category": DECISION_CATEGORIES.get(decision, "unknown"),
        "reason": reason,
        "context": context or {},
        "outcome": outcome or "pending",
        "source": source,
        "pid": os.getpid(),
    }
    with open(DECISION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _logger.info("DECISION [%s] %s: %s — %s", agent, decision, reason, outcome or "")
    return entry

# ── Failure Logging ──────────────────────────────────────────────────────

def log_failure(
    agent: str,
    error: str,
    category: str = "unknown",
    recoverable: bool = True,
    trace: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict:
    """
    Log an agent failure with classification.
    
    Args:
        agent: Agent name
        error: Error message
        category: Failure category (use FAILURE_CATEGORIES keys)
        recoverable: Can this failure be retried?
        trace: Stack trace (auto-captured if None)
        context: Relevant state at time of failure
    
    Returns:
        The logged entry dict
    """
    _ensure_logs()
    if trace is None:
        trace = traceback.format_exc()
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "failure",
        "agent": agent,
        "error": error[:500],
        "category": category,
        "description": FAILURE_CATEGORIES.get(category, "Unknown"),
        "recoverable": recoverable,
        "trace": trace[-1000:] if trace else "",
        "context": context or {},
        "pid": os.getpid(),
    }
    with open(FAILURE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _logger.warning("FAILURE [%s] (%s): %s", agent, category, error[:100])
    return entry

# ── Metrics Logging ──────────────────────────────────────────────────────

def log_metric(
    agent: str,
    metric: str,
    value: float,
    unit: str = "",
    tags: Optional[dict] = None,
):
    """
    Log a numeric metric for tracking over time.
    
    Args:
        agent: Agent name
        metric: Metric name (e.g., "token_cost", "latency_ms")
        value: Numeric value
        unit: Unit string ("ms", "USD", "tokens")
        tags: Key-value tags for filtering
    """
    _ensure_logs()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "metric",
        "agent": agent,
        "metric": metric,
        "value": value,
        "unit": unit,
        "tags": tags or {},
    }
    with open(METRICS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

# ── Query Helpers ───────────────────────────────────────────────────────

def get_recent_decisions(agent: Optional[str] = None, n: int = 20) -> list[dict]:
    """Get the most recent N decisions, optionally filtered by agent."""
    if not DECISION_LOG.exists():
        return []
    entries = []
    with open(DECISION_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if agent is None or entry.get("agent") == agent:
                        entries.append(entry)
                except:
                    pass
    return entries[-n:]

def get_failure_rate(agent: Optional[str] = None, hours: int = 24) -> dict:
    """Get failure statistics for the last N hours."""
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    total = 0
    failures = 0
    categories = {}
    
    if not FAILURE_LOG.exists():
        return {"total": 0, "failures": 0, "rate": 0.0, "categories": {}}
    
    with open(FAILURE_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
                    if ts < cutoff:
                        continue
                    if agent and entry.get("agent") != agent:
                        continue
                    total += 1
                    if entry["type"] == "failure":
                        failures += 1
                        cat = entry.get("category", "unknown")
                        categories[cat] = categories.get(cat, 0) + 1
                except:
                    pass
    
    return {
        "total": total,
        "failures": failures,
        "rate": failures / max(total, 1) * 100,
        "categories": categories,
        "period_hours": hours,
    }

def get_token_costs(hours: int = 168) -> dict:
    """Get estimated LLM token costs from metrics log."""
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    costs = {}
    total = 0.0
    
    if not METRICS_LOG.exists():
        return {"total_cost": 0, "by_agent": {}, "period_hours": hours}
    
    with open(METRICS_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if entry.get("metric") != "token_cost":
                        continue
                    ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
                    if ts < cutoff:
                        continue
                    agent = entry.get("agent", "unknown")
                    cost = entry.get("value", 0)
                    costs[agent] = costs.get(agent, 0) + cost
                    total += cost
                except:
                    pass
    
    return {
        "total_cost": round(total, 4),
        "by_agent": {k: round(v, 4) for k, v in sorted(costs.items(), key=lambda x: -x[1])},
        "period_hours": hours,
    }

# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AGENTX AgentOps Console")
    parser.add_argument("--decisions", action="store_true", help="Show recent decisions")
    parser.add_argument("--failures", action="store_true", help="Show failure stats")
    parser.add_argument("--costs", action="store_true", help="Show token cost estimates")
    parser.add_argument("--agent", type=str, default=None, help="Filter by agent name")
    parser.add_argument("--hours", type=int, default=24, help="Time window in hours")
    
    args = parser.parse_args()
    
    if args.decisions:
        decisions = get_recent_decisions(args.agent, 20)
        print(f"=== Recent Decisions (last {len(decisions)}) ===")
        for d in reversed(decisions):
            ts = d["timestamp"][:19]
            print(f"  [{ts}] {d['agent']}: {d['decision']} → {d['reason'][:70]}")
    
    elif args.failures:
        stats = get_failure_rate(args.agent, args.hours)
        print(f"=== Failure Rate (last {args.hours}h) ===")
        print(f"  Total events: {stats['total']}")
        print(f"  Failures:     {stats['failures']}")
        print(f"  Rate:         {stats['rate']:.1f}%")
        if stats['categories']:
            print(f"\n  By category:")
            for cat, count in sorted(stats['categories'].items(), key=lambda x: -x[1]):
                print(f"    {cat}: {count}")
    
    elif args.costs:
        costs = get_token_costs(args.hours)
        print(f"=== LLM Token Costs (last {args.hours}h) ===")
        print(f"  Total: ${costs['total_cost']:.4f}")
        if costs['by_agent']:
            print(f"\n  By agent:")
            for agent, cost in costs['by_agent'].items():
                print(f"    {agent}: ${cost:.4f}")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
