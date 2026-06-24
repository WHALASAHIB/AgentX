"""
AI Decision Log — persistent JSON-backed store for logging agent decisions.
Provides get_decisions(), log_decision(), and get_summary() used by the
FastAPI /api/decisions and /api/decisions/summary endpoints.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATA_FILE = _DATA_DIR / "decision_log.json"

_MAX_ENTRIES = 10_000  # soft cap; oldest entries trimmed on write


def _ensure_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_entries() -> list[dict]:
    if not _DATA_FILE.exists():
        return []
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_entries(entries: list[dict]):
    _ensure_dir()
    # trim oldest if over cap
    if len(entries) > _MAX_ENTRIES:
        entries = entries[-_MAX_ENTRIES:]
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, default=str)


def _parse_iso_or_none(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ── Public API ──────────────────────────────────────────────────────────────


def get_decisions(
    days: int = 7,
    limit: int = 100,
    agent_id: Optional[str] = None,
) -> list[dict]:
    """Return recent decision entries, newest first."""
    entries = _load_entries()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filtered = []
    for e in entries:
        ts = _parse_iso_or_none(e.get("timestamp"))
        if ts and ts >= cutoff:
            if agent_id is not None and e.get("agent_id") != agent_id:
                continue
            filtered.append(e)

    # newest first
    filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return filtered[:limit]


def log_decision(
    agent_id: str,
    agent_name: str,
    action: str,
    detail: str = "",
    outcome: str = "pending",
    metadata: Optional[dict] = None,
) -> dict:
    """Append a new decision entry and persist."""
    entry = {
        "id": f"dec_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{os.urandom(2).hex()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "agent_name": agent_name,
        "action": action,
        "detail": detail,
        "outcome": outcome,
        "metadata": metadata or {},
    }
    entries = _load_entries()
    entries.append(entry)
    _save_entries(entries)
    return entry


def get_summary(days: int = 7) -> dict:
    """Return aggregate counts grouped by outcome for the given period."""
    entries = _load_entries()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    total = 0
    outcomes: dict[str, int] = {}
    by_agent: dict[str, dict[str, int]] = {}

    for e in entries:
        ts = _parse_iso_or_none(e.get("timestamp"))
        if ts and ts >= cutoff:
            total += 1
            outcome = e.get("outcome", "unknown")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

            agent = e.get("agent_name", e.get("agent_id", "unknown"))
            if agent not in by_agent:
                by_agent[agent] = {}
            by_agent[agent][outcome] = by_agent[agent].get(outcome, 0) + 1

    return {
        "total": total,
        "period_days": days,
        "outcomes": outcomes,
        "by_agent": by_agent,
    }
