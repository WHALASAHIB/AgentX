"""
sprint_manager.py — Agile PM + Scrum Master for Research Division
==================================================================
Manages backlog prioritization, sprint lifecycles, scrum ceremonies,
and blocker detection. Integrates with the analytics engine and
strategy innovation pipeline to produce actionable sprint artefacts.

Backlog items flow:
  analytics reports  ──→  generate_backlog()  ──→  sprint_planning()
  innovation results ──→  create_sprint()     ──→  daily_standup()
                     ──→  sprint_review()     ──→  deployment engine

Sprint cycle (24 h):
  08:00 HKT — Sprint planning  (select top-3 backlog items)
  20:00 HKT — Sprint review    (assess progress, draw lessons)
  On demand — Daily standup    (status, blockers, recommendations)
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────────
RESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(RESEARCH_DIR, "state")
SPRINT_STATE_FILE = os.path.join(STATE_DIR, "sprint.json")
HKT_OFFSET = timedelta(hours=8)

# ── Scoring constants ──────────────────────────────────────────────────────────
URGENCY_MULTIPLIERS: Dict[str, float] = {
    "optimize_params": 1.0,
    "add_filter": 1.2,
    "change_strategy": 1.5,
    "reduce_risk": 1.3,
    "session_restrict": 1.1,
}

CATEGORY_EFFORT_HOURS: Dict[str, int] = {
    "optimize_params": 4,
    "add_filter": 6,
    "change_strategy": 8,
    "reduce_risk": 3,
    "session_restrict": 5,
}

TARGET_WIN_RATE = 0.55       # 55% minimum target for all pairs
CRITICAL_LOSS_STREAK = 5     # consecutive losses → critical blocker
CRITICAL_DRAWDOWN_PCT = 15.0 # max drawdown -> critical blocker
WARNING_WR_THRESHOLD = 0.25  # win rate below this -> warning blocker
WARNING_WR_DROP_PCT = 10.0   # percentage-point drop from baseline → warning
FLAT_EQUITY_DAYS = 5         # consecutive days without equity growth → warning

# ── Helpers ─────────────────────────────────────────────────────────────────────


def _now_hkt() -> datetime:
    """Return current time in HKT (UTC+8)."""
    return datetime.now(timezone.utc) + HKT_OFFSET


def _now_iso() -> str:
    """Return ISO-formatted current HKT timestamp."""
    return _now_hkt().isoformat(timespec="seconds")


def _to_native(obj: Any) -> Any:
    """Recursively convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_native(i) for i in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.ndarray,)):
        return _to_native(obj.tolist())
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely coerce a value to float, returning *default* on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _get_report_value(report: dict, *keys: str, default: Any = 0.0) -> Any:
    """Drill into a nested report dict to retrieve a value.

    >>> _get_report_value({'kpis': {'win_rate': 0.45}}, 'kpis', 'win_rate')
    0.45
    """
    current = report
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k, {})
        else:
            return default
    return current if current is not None else default


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Persistence helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _ensure_state_dir() -> None:
    """Create the state directory if it does not exist."""
    os.makedirs(STATE_DIR, exist_ok=True)


def save_sprint(state: dict) -> bool:
    """Persist the current sprint state to ``SPRINT_STATE_FILE``.

    Args:
        state: Sprint state dict matching the sprint schema.

    Returns:
        True on success, False on failure.
    """
    _ensure_state_dir()
    try:
        with open(SPRINT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(_to_native(state), f, indent=2, default=str)
        logger.info("Sprint state saved to %s", SPRINT_STATE_FILE)
        return True
    except (OSError, IOError, TypeError) as e:
        logger.exception("Failed to save sprint state: %s", e)
        return False


def load_sprint() -> Optional[dict]:
    """Load the current sprint state from ``SPRINT_STATE_FILE``.

    Returns:
        Sprint state dict, or ``None`` if the file is missing or corrupt.
    """
    if not os.path.isfile(SPRINT_STATE_FILE):
        logger.info("No sprint state file found at %s", SPRINT_STATE_FILE)
        return None
    try:
        with open(SPRINT_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError, IOError) as e:
        logger.warning("Failed to load sprint state: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Backlog management
# ═══════════════════════════════════════════════════════════════════════════════


def _infer_category(pair_report: dict) -> Tuple[str, str, float, float, float]:
    """Infer the most appropriate backlog category for a poorly-performing pair.

    Returns:
        (category, issue_description, current_win_rate, target_value, urgency_mult)
    """
    kpis = pair_report.get("kpis", {})
    wr = _safe_float(kpis.get("win_rate", 0))
    max_dd = _safe_float(kpis.get("max_drawdown_pct", 0))
    max_cons_losses = kpis.get("max_consecutive_losses", 0)
    profit_factor = _safe_float(kpis.get("profit_factor", 0))
    total_trades = kpis.get("total_trades", 0)

    pair = pair_report.get("pair", "unknown")
    strategy = kpis.get("magic", "unknown")

    target_wr = TARGET_WIN_RATE

    # ── Rule-based category selection ──────────────────────────────
    if max_dd > CRITICAL_DRAWDOWN_PCT:
        category = "reduce_risk"
        issue = f"Drawdown {max_dd:.1f}% exceeds {CRITICAL_DRAWDOWN_PCT}% threshold"
        target_value = max(target_wr, wr * 1.15)
    elif max_cons_losses >= CRITICAL_LOSS_STREAK and wr < 0.40:
        category = "add_filter"
        issue = f"{max_cons_losses} consecutive losses, WR={wr:.1%}"
        target_value = max(target_wr, wr * 1.20)
    elif profit_factor < 1.0 and total_trades > 10:
        category = "change_strategy"
        issue = f"Profit factor {profit_factor:.2f} < 1.0"
        target_value = target_wr
    elif wr < 0.30:
        category = "add_filter"
        issue = f"Win rate {wr:.1%} critically low"
        target_value = target_wr
    else:
        category = "optimize_params"
        issue = f"WR={wr:.1%} below {TARGET_WIN_RATE:.0%} target"
        target_value = target_wr

    urgency_mult = URGENCY_MULTIPLIERS.get(category, 1.0)
    return category, issue, wr, target_value, urgency_mult


def _compute_trade_frequency(report: dict) -> float:
    """Compute average trades per day from the report's trade count.

    Uses the pair's total_trade_count divided by the number of days
    the report covers (estimated from monthly breakdown keys, default 30).
    """
    kpis = report.get("kpis", {})
    total_trades = kpis.get("total_trades", 0) or 0
    monthly = kpis.get("monthly_breakdown", {})
    days = len(monthly) * 30 if monthly else 30
    days = max(1, days)
    return total_trades / days


def generate_backlog(all_reports: Dict[str, dict],
                     innovation_results: Optional[List[dict]] = None) -> List[dict]:
    """Generate a prioritised backlog from analytics reports and innovation results.

    For each pair report, evaluates performance gaps and produces a backlog
    item with an impact score. Items are sorted by impact score descending.

    Impact score formula::

        (target_wr - current_wr) * trade_frequency * urgency_multiplier

    Args:
        all_reports:  Dict from :func:`analytics_engine.generate_all_reports`,
                      keyed by pair symbol (including ``"overall"``).
        innovation_results:  Optional list of innovation sprint result dicts.
                             Used to avoid duplicating items for pairs already
                             being actively worked on.

    Returns:
        List of backlog item dicts, each with keys:
            id, pair, strategy, issue, current_value, target_value,
            impact_score, category, effort_hours
    """
    if all_reports is None:
        return []

    backlog: List[dict] = []
    item_counter: int = 0

    # Gather pairs already covered by active innovation sprints
    active_pairs: set = set()
    if innovation_results:
        for ir in innovation_results:
            pair = ir.get("pair", "")
            if pair:
                active_pairs.add(pair.upper())

    for pair_key, report in all_reports.items():
        if pair_key.upper() == "OVERALL":
            continue  # Skip the aggregate; we work on individual pairs

        kpis = report.get("kpis", {})
        wr = _safe_float(kpis.get("win_rate", 0))

        # Skip pairs that are already performing well or have no data
        if wr >= TARGET_WIN_RATE or kpis.get("total_trades", 0) < 5:
            continue

        # Skip if there's already an innovation sprint running for this pair
        if pair_key.upper() in active_pairs:
            logger.debug("Skipping %s — active innovation sprint in progress", pair_key)
            continue

        category, issue, current_wr, target_wr_override, urgency_mult = _infer_category(report)
        trade_freq = _compute_trade_frequency(report)

        # Impact score
        improvement_gap = max(0.0, target_wr_override - current_wr)
        impact_score = improvement_gap * trade_freq * urgency_mult

        item_counter += 1
        backlog.append({
            "id": f"BL-{item_counter:04d}",
            "pair": pair_key,
            "strategy": _get_strategy_for_pair(pair_key, kpis),
            "issue": issue,
            "current_value": round(current_wr, 4),
            "target_value": round(target_wr_override, 4),
            "impact_score": round(impact_score, 4),
            "category": category,
            "effort_hours": CATEGORY_EFFORT_HOURS.get(category, 4),
        })

    # Sort by impact score descending
    backlog.sort(key=lambda x: x["impact_score"], reverse=True)
    logger.info("Generated backlog with %d items", len(backlog))
    return backlog


def _get_strategy_for_pair(pair: str, kpis: dict) -> str:
    """Try to determine which strategy a pair is trading with.

    Falls back to ``magic`` number or ``"unknown"``.
    """
    magic = kpis.get("magic")
    if magic:
        return f"magic_{magic}"
    # Attempt to infer from the pair's best-known strategy
    pair_upper = pair.upper()
    if pair_upper == "XAUUSD":
        return "gold_phoenix"
    if pair_upper in ("EURUSD", "GBPUSD", "USDJPY"):
        return "macd"
    return "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Sprint lifecycle management
# ═══════════════════════════════════════════════════════════════════════════════


def _new_sprint_state() -> dict:
    """Return a bare-minimum sprint state skeleton."""
    return {
        "sprint_number": 0,
        "created_at": _now_iso(),
        "start_time": _now_iso(),
        "end_time": "",
        "items": [],
        "backlog": [],
        "completed": [],
        "metrics": {
            "pairs_analyzed": 0,
            "improvements_deployed": 0,
            "win_rate_change": 0.0,
        },
    }


def create_sprint(backlog_items: List[dict],
                  sprint_number: Optional[int] = None) -> dict:
    """Create a new sprint from the top-priority backlog items (max 3).

    Consumes up to 3 items from *backlog_items*, placing them in the sprint's
    ``items`` list with ``status='pending'``. Remaining backlog items stay
    in the sprint's ``backlog`` field for future sprints.

    Args:
        backlog_items:  Prioritised list from :func:`generate_backlog`.
        sprint_number:  Optional sprint number. Auto-increments if omitted.

    Returns:
        New sprint state dict (also persisted to disk).
    """
    existing = load_sprint()
    if existing and sprint_number is None:
        sprint_number = existing.get("sprint_number", 0) + 1
    else:
        sprint_number = sprint_number or 1

    # Take up to 3 high-priority items
    sprint_items = []
    for item in backlog_items[:3]:
        sprint_items.append({
            "id": item["id"],
            "pair": item["pair"],
            "strategy": item["strategy"],
            "description": item["issue"],
            "current_value": item["current_value"],
            "target_value": item["target_value"],
            "status": "pending",  # pending | in_progress | testing | deployed | failed
            "impact_score": item["impact_score"],
            "category": item["category"],
            "effort_hours": item["effort_hours"],
        })

    remaining_backlog = [_to_native(i) for i in backlog_items[3:]]

    state = _new_sprint_state()
    state["sprint_number"] = sprint_number
    state["created_at"] = _now_iso()
    state["start_time"] = _now_iso()
    state["end_time"] = ""
    state["items"] = sprint_items
    state["backlog"] = remaining_backlog
    state["completed"] = []
    state["metrics"] = {
        "pairs_analyzed": len(sprint_items),
        "improvements_deployed": 0,
        "win_rate_change": 0.0,
    }

    save_sprint(state)
    logger.info("Created sprint #%d with %d item(s)", sprint_number, len(sprint_items))
    return state


def get_sprint() -> Optional[dict]:
    """Load the current sprint state from disk.

    Returns:
        Sprint state dict, or None if no sprint has been created.
    """
    return load_sprint()


def update_sprint_item(item_id: str,
                       status: str = "in_progress",
                       results: Optional[dict] = None) -> Optional[dict]:
    """Update the status (and optionally results) of a sprint item.

    Args:
        item_id:  The item's ``id`` field (e.g. ``"BL-0001"``).
        status:   One of ``'pending'``, ``'in_progress'``, ``'testing'``,
                  ``'deployed'``, ``'failed'``.
        results:  Optional dict with deployment/backtest results to attach.

    Returns:
        Updated sprint state, or ``None`` if the item was not found.
    """
    state = load_sprint()
    if state is None:
        logger.warning("No sprint state to update")
        return None

    VALID_STATUSES = {"pending", "in_progress", "testing", "deployed", "failed"}
    if status not in VALID_STATUSES:
        logger.warning("Invalid status '%s' — must be one of %s", status, VALID_STATUSES)
        return None

    found = False
    for item in state.get("items", []):
        if item["id"] == item_id:
            item["status"] = status
            if results is not None:
                item["results"] = _to_native(results)
            found = True
            logger.info("Updated item %s → status=%s", item_id, status)
            break

    if not found:
        logger.warning("Item %s not found in current sprint", item_id)
        return None

    # If all items are deployed/failed, auto-complete
    all_done = all(
        i.get("status") in ("deployed", "failed")
        for i in state.get("items", [])
    )
    if all_done and status in ("deployed", "failed"):
        logger.info("All sprint items finished — consider calling complete_sprint()")

    save_sprint(state)
    return state


def complete_sprint() -> Optional[dict]:
    """Complete the current sprint and optionally start the next one.

    Moves deployed items to the ``completed`` list. If any backlog items
    remain, creates a new sprint with the next 3 highest-priority items.
    Otherwise, clears the sprint.

    Returns:
        New sprint state (or the completed state if no backlog remains).
    """
    state = load_sprint()
    if state is None:
        logger.warning("No sprint to complete")
        return None

    now = _now_iso()
    state["end_time"] = now

    # Move deployed items to completed list
    for item in state.get("items", []):
        if item.get("status") == "deployed":
            # Add a completion timestamp
            item["completed_at"] = now
            state["completed"].append(item)

    # Update metrics
    deployed = len([i for i in state["items"] if i.get("status") == "deployed"])
    state["metrics"]["improvements_deployed"] = deployed
    state["metrics"]["win_rate_change"] = _compute_sprint_wr_delta(state)
    state["metrics"]["pairs_analyzed"] = len(state["items"])

    # Persist the completed state
    save_sprint(state)
    logger.info("Sprint #%d completed: %d/%d items deployed",
                state["sprint_number"], deployed, len(state["items"]))

    # Create next sprint from leftover backlog
    remaining = state.get("backlog", [])
    if remaining:
        next_sprint = create_sprint(remaining, sprint_number=state["sprint_number"] + 1)
        logger.info("Created sprint #%d with next %d backlog item(s)",
                    next_sprint["sprint_number"], len(next_sprint["items"]))
        return next_sprint

    return state


def _compute_sprint_wr_delta(state: dict) -> float:
    """Estimate the win-rate change achieved by this sprint.

    Compares the average target win rate of deployed items against the
    average current win rate. A rough heuristic — real WR data comes from
    the analytics engine post-deployment.
    """
    deployed = [i for i in state.get("items", []) if i.get("status") == "deployed"]
    if not deployed:
        return 0.0
    avg_current = np.mean([_safe_float(i.get("current_value", 0)) for i in deployed])
    avg_target = np.mean([_safe_float(i.get("target_value", 0)) for i in deployed])
    return round(avg_target - avg_current, 4)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Blocker detection
# ═══════════════════════════════════════════════════════════════════════════════


def detect_blockers(all_reports: Dict[str, dict],
                    open_positions: List[dict]) -> List[dict]:
    """Scan all pairs for urgent issues that require immediate attention.

    Detection rules::

        Critical (must act now):
        - Pair with 5+ consecutive losses
        - Pair with drawdown > 15%
        - Bot not running (no open positions when expected)

        Warning (should monitor):
        - Pair WR < 25%
        - Strategy win rate drop > 10% from baseline
        - Equity curve flat for 5+ consecutive days

    Args:
        all_reports:     Dict of pair → report from analytics engine.
        open_positions:  Currently open positions (list of position dicts).

    Returns:
        List of blocker dicts, each with keys:
            type, severity, pair, message, detail
    """
    blockers: List[dict] = []

    if not all_reports:
        return blockers

    for pair_key, report in all_reports.items():
        if pair_key.upper() == "OVERALL":
            continue

        kpis = report.get("kpis", {})
        total_trades = kpis.get("total_trades", 0) or 0
        wr = _safe_float(kpis.get("win_rate", 0))
        max_dd = _safe_float(kpis.get("max_drawdown_pct", 0))
        max_cons_losses = kpis.get("max_consecutive_losses", 0) or 0
        gross_profit = _safe_float(kpis.get("gross_profit", 0))
        gross_loss = _safe_float(kpis.get("gross_loss", 0))
        profit_factor = _safe_float(kpis.get("profit_factor", 0))

        # ── Critical detections ────────────────────────────────────

        # 5+ consecutive losses
        if max_cons_losses >= CRITICAL_LOSS_STREAK and total_trades >= CRITICAL_LOSS_STREAK:
            blockers.append({
                "type": "consecutive_losses",
                "severity": "critical",
                "pair": pair_key,
                "message": f"{max_cons_losses} consecutive losses",
                "detail": f"Pair {pair_key} has lost {max_cons_losses} trades in a row. "
                          f"WR={wr:.1%}. Immediate intervention required.",
            })

        # Drawdown > 15%
        if max_dd > CRITICAL_DRAWDOWN_PCT:
            blockers.append({
                "type": "drawdown",
                "severity": "critical",
                "pair": pair_key,
                "message": f"Drawdown {max_dd:.1f}% exceeds {CRITICAL_DRAWDOWN_PCT}% threshold",
                "detail": f"Pair {pair_key} has max drawdown of {max_dd:.1f}%. "
                          f"Risk reduction required.",
            })

        # Bot not running — pair has recent trade history but no open positions
        # (This is context-sensitive; we flag pairs with a trade history
        #  where we'd expect ongoing activity.)
        has_positions = any(
            (p.get("symbol") or p.get("pair", "")).upper() == pair_key.upper()
            for p in (open_positions or [])
        )
        if not has_positions and total_trades > 20:
            # Pair has substantial history but no open trades; worth noting
            blockers.append({
                "type": "bot_inactive",
                "severity": "warning",
                "pair": pair_key,
                "message": "No open positions despite active trade history",
                "detail": f"Pair {pair_key} has {total_trades} historical trades "
                          f"but no currently open positions. Bot may be inactive.",
            })

        # ── Warning detections ─────────────────────────────────────

        # WR < 25%
        if wr < WARNING_WR_THRESHOLD and total_trades >= 5:
            blockers.append({
                "type": "low_win_rate",
                "severity": "warning",
                "pair": pair_key,
                "message": f"Win rate {wr:.1%} below {WARNING_WR_THRESHOLD:.0%} threshold",
                "detail": f"Pair {pair_key} WR={wr:.1%} from {total_trades} trades. "
                          f"Needs filter or parameter adjustment.",
            })

        # Profit factor < 0.8 (strategy win rate drop indicator)
        if 0 < profit_factor < 0.8 and total_trades >= 10:
            blockers.append({
                "type": "profit_factor_drop",
                "severity": "warning",
                "pair": pair_key,
                "message": f"Profit factor {profit_factor:.2f} suggests strategy degradation",
                "detail": f"Pair {pair_key} PF={profit_factor:.2f} from {total_trades} trades. "
                          f"Winning efficiency has dropped significantly.",
            })

    # Check equity curve flatness in the overall report
    overall_report = all_reports.get("overall", {})
    if overall_report:
        monthly = overall_report.get("kpis", {}).get("monthly_breakdown", {})
        if isinstance(monthly, dict):
            # Check if the last several months show flat/declining net
            monthly_items = sorted(monthly.items(), key=lambda x: x[0])
            if len(monthly_items) >= 3:
                recent_nets = []
                for _, mdata in monthly_items[-3:]:
                    net_val = _safe_float(mdata.get("net", 0))
                    recent_nets.append(net_val)
                # If all recent months are <= 0 after being profitable, flag it
                if all(n <= 0 for n in recent_nets[-2:]):
                    blockers.append({
                        "type": "equity_flat",
                        "severity": "warning",
                        "pair": "overall",
                        "message": f"Account equity flat/declining for {len(recent_nets)} month(s)",
                        "detail": f"Recent monthly net profits: {recent_nets}. "
                                  f"Strategy overhaul may be needed.",
                    })

    # Sort: critical first, then by pair
    severity_order = {"critical": 0, "warning": 1}
    blockers.sort(key=lambda b: (severity_order.get(b["severity"], 99), b["pair"]))

    logger.info("Detected %d blocker(s): %d critical, %d warning",
                len(blockers),
                sum(1 for b in blockers if b["severity"] == "critical"),
                sum(1 for b in blockers if b["severity"] == "warning"))
    return blockers


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Scrum ceremonies
# ═══════════════════════════════════════════════════════════════════════════════


def daily_standup(all_reports: Dict[str, dict],
                  sprint: Optional[dict] = None) -> str:
    """Generate a formatted daily standup report.

    Structure:
        - What was done since last standup
        - What's in progress
        - Blockers (critical/warning)
        - Recommendations

    Args:
        all_reports:  Dict of pair reports from analytics engine.
        sprint:       Current sprint state dict (optional — skips if None).

    Returns:
        Formatted standup text ready for display or delivery.
    """
    lines: List[str] = []
    now = _now_hkt()
    date_str = now.strftime("%Y-%m-%d %H:%M HKT")

    lines.append(f"## 🤖 Daily Standup — {date_str}")
    lines.append("")

    # ── Sprint summary ────────────────────────────────────────────
    if sprint and sprint.get("items"):
        sprint_num = sprint.get("sprint_number", "?")
        lines.append(f"### 📋 Sprint #{sprint_num}")
        lines.append("")

        in_progress_items = [i for i in sprint["items"] if i.get("status") == "in_progress"]
        pending_items = [i for i in sprint["items"] if i.get("status") == "pending"]
        testing_items = [i for i in sprint["items"] if i.get("status") == "testing"]
        deployed_items = [i for i in sprint["items"] if i.get("status") == "deployed"]
        failed_items = [i for i in sprint["items"] if i.get("status") == "failed"]

        if deployed_items:
            lines.append("**✅ Recently Deployed:**")
            for item in deployed_items:
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — {item['description']}")
            lines.append("")

        if testing_items:
            lines.append("**🧪 In Testing:**")
            for item in testing_items:
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — {item['description']}")
            lines.append("")

        if in_progress_items:
            lines.append("**🔄 In Progress:**")
            for item in in_progress_items:
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — {item['description']}")
            lines.append("")

        if pending_items:
            lines.append("**⏳ Pending:**")
            for item in pending_items:
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — {item['description']}")
            lines.append("")

        if failed_items:
            lines.append("**❌ Failed:**")
            for item in failed_items:
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — {item['description']}")
            lines.append("")

        lines.append(f"**Backlog remaining:** {len(sprint.get('backlog', []))} item(s)")
        lines.append("")
    else:
        lines.append("**No active sprint.**")
        lines.append("")

    # ── Blockers ──────────────────────────────────────────────────
    lines.append("### 🚨 Blockers")
    lines.append("")

    # Use available reports from overall + detect blockers
    positions_from_standup = []
    if all_reports:
        overall_report = all_reports.get("overall", {})
        open_pos_count = overall_report.get("open_positions", 0)
        pos_detail = overall_report.get("position_detail", [])
        positions_from_standup = pos_detail if isinstance(pos_detail, list) else []

    blockers = detect_blockers(all_reports, positions_from_standup)

    criticals = [b for b in blockers if b["severity"] == "critical"]
    warnings_b = [b for b in blockers if b["severity"] == "warning"]

    if criticals:
        lines.append("**🔴 Critical:**")
        for b in criticals:
            lines.append(f"  • {b['pair']} — {b['message']}")
        lines.append("")

    if warnings_b:
        lines.append("**🟡 Warnings:**")
        for b in warnings_b:
            lines.append(f"  • {b['pair']} — {b['message']}")
        lines.append("")

    if not criticals and not warnings_b:
        lines.append("  ✅ No blockers detected.")
        lines.append("")

    # ── Recommendations ────────────────────────────────────────────
    lines.append("### 💡 Recommendations")
    lines.append("")

    if criticals:
        lines.append("  • **Immediate action:** Address critical blockers before proceeding "
                      "with new sprint work.")
    if any("drawdown" in b.get("type", "") for b in blockers):
        lines.append("  • **Risk reduction:** Tighten stop-losses or reduce position sizes "
                      "on pairs with elevated drawdown.")
    if any("consecutive_losses" in b.get("type", "") for b in blockers):
        lines.append("  • **Trading halt:** Consider pausing the affected strategy until "
                      "root cause is identified.")
    if any("low_win_rate" in b.get("type", "") for b in blockers):
        lines.append("  • **Filter review:** Add or tighten entry filters for low-win-rate pairs.")

    if not blockers:
        lines.append("  • Continue executing the current sprint plan.")
        lines.append("  • Monitor performance for early signs of degradation.")

    if sprint and sprint.get("backlog"):
        next_item = sprint["backlog"][0]
        lines.append(f"  • Next backlog candidate: `{next_item['id']}` — "
                      f"{next_item['pair']}: {next_item['issue']} "
                      f"(impact {next_item['impact_score']:.4f})")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated at {date_str} by Research Division Sprint Manager*")

    return "\n".join(lines)


def sprint_review(all_reports: Dict[str, dict],
                  sprint: Optional[dict],
                  innovation_results: Optional[List[dict]] = None) -> str:
    """Generate a formatted sprint review report.

    Structure:
        - Sprint summary (what was achieved)
        - Performance delta (win rate changes per pair)
        - Lessons learned
        - Recommendations for next sprint

    Args:
        all_reports:         Dict of pair reports from analytics engine.
        sprint:              Current (or just-completed) sprint state.
        innovation_results:  Optional list of innovation sprint results.

    Returns:
        Formatted sprint review text.
    """
    lines: List[str] = []
    now = _now_hkt()
    date_str = now.strftime("%Y-%m-%d %H:%M HKT")

    sprint_num = sprint.get("sprint_number", "?") if sprint else "?"
    lines.append(f"## 📊 Sprint Review — Sprint #{sprint_num}")
    lines.append(f"_{date_str}_")
    lines.append("")

    # ── Sprint summary ─────────────────────────────────────────────
    lines.append("### Sprint Summary")
    lines.append("")

    if sprint:
        items = sprint.get("items", [])
        deployed = [i for i in items if i.get("status") == "deployed"]
        failed = [i for i in items if i.get("status") == "failed"]
        in_progress = [i for i in items if i.get("status") in ("in_progress", "testing")]

        lines.append(f"- **Sprint #{sprint_num}** started: {sprint.get('start_time', '?')}")
        lines.append(f"- **Items:** {len(items)} total")
        lines.append(f"- **Deployed:** {len(deployed)}")
        lines.append(f"- **Failed:** {len(failed)}")
        lines.append(f"- **In progress:** {len(in_progress)}")

        if sprint.get("metrics"):
            m = sprint["metrics"]
            lines.append(f"- **Pairs analyzed:** {m.get('pairs_analyzed', 0)}")
            lines.append(f"- **Improvements deployed:** {m.get('improvements_deployed', 0)}")
            wr_change = m.get("win_rate_change", 0)
            direction = "📈" if wr_change >= 0 else "📉"
            lines.append(f"- **Estimated WR change:** {direction} {wr_change:+.2%}")

        lines.append("")

        if deployed:
            lines.append("**✅ Deployed Items:**")
            for item in deployed:
                results = item.get("results", {})
                detail = ""
                if results:
                    metrics_str = ", ".join(
                        f"{k}={v}" for k, v in results.items()
                        if k in ("sharpe_ratio", "profit_factor", "win_rate_pct")
                    )
                    if metrics_str:
                        detail = f" [{metrics_str}]"
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — "
                              f"{item['description']}{detail}")
            lines.append("")

        if failed:
            lines.append("**❌ Failed Items:**")
            for item in failed:
                reason = ""
                results = item.get("results", {})
                if results and isinstance(results, dict):
                    reason = results.get("error", results.get("reason", ""))
                suffix = f" — {reason}" if reason else ""
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — "
                              f"{item['description']}{suffix}")
            lines.append("")

        if in_progress:
            lines.append("**🔄 Carried Over:**")
            for item in in_progress:
                lines.append(f"  • `{item['id']}` {item['pair']}/{item['strategy']} — "
                              f"{item['description']}")
            lines.append("")

    else:
        lines.append("No sprint data available.\n")

    # ── Performance delta ──────────────────────────────────────────
    lines.append("### Performance Delta")
    lines.append("")

    if all_reports:
        # Show per-pair win rate change vs previous analytics snapshot
        overall_report = all_reports.get("overall", {})
        overall_kpis = overall_report.get("kpis", {})
        lines.append(f"- **Overall profit factor:** {_safe_float(overall_kpis.get('profit_factor', 0)):.2f}")
        lines.append(f"- **Overall win rate:** {_safe_float(overall_kpis.get('win_rate', 0)):.1%}")
        lines.append(f"- **Net profit:** ${_safe_float(overall_kpis.get('net_profit', 0)):,.2f}")
        lines.append("")

        for pair_key, report in sorted(all_reports.items()):
            if pair_key.upper() == "OVERALL":
                continue
            kpis = report.get("kpis", {})
            wr = _safe_float(kpis.get("win_rate", 0))
            trades = kpis.get("total_trades", 0) or 0
            net = _safe_float(kpis.get("net_profit", 0))
            dd = _safe_float(kpis.get("max_drawdown_pct", 0))

            # Check if this pair was in the sprint
            sprint_pair = False
            if sprint:
                sprint_pair = any(
                    i.get("pair", "").upper() == pair_key.upper()
                    for i in sprint.get("items", [])
                )

            marker = "★" if sprint_pair else " "
            wr_str = f"{wr:.1%}"
            lines.append(f"  {marker} **{pair_key}:** WR={wr_str}, "
                          f"Trades={trades}, Net=${net:+.2f}, DD={dd:.1f}%")
    else:
        lines.append("No analytics data available.\n")

    # ── Innovation sprint highlights ───────────────────────────────
    if innovation_results:
        lines.append("### Innovation Sprint Results")
        lines.append("")
        for ir in innovation_results[-5:]:  # last 5
            pair = ir.get("pair", "?")
            strat = ir.get("strategy_name", "?")
            summary = ir.get("summary", "")
            lines.append(f"  • **{pair}/{strat}:** {summary[:150]}")
        lines.append("")

    # ── Lessons learned ────────────────────────────────────────────
    lines.append("### Lessons Learned")
    lines.append("")

    # Auto-detect lessons from sprint failures and blockers
    lessons: List[str] = []
    if sprint:
        failed = [i for i in sprint.get("items", []) if i.get("status") == "failed"]
        if failed:
            lessons.append(
                f"**{len(failed)} item(s) failed** — review deployment "
                f"pipeline or backtest expectations."
            )

    if all_reports:
        blockers = detect_blockers(all_reports, [])
        consecutive_loss_blocks = [b for b in blockers if b["type"] == "consecutive_losses"]
        if consecutive_loss_blocks:
            pairs_str = ", ".join(b["pair"] for b in consecutive_loss_blocks)
            lessons.append(
                f"**Consecutive losses** detected on {pairs_str} — "
                f"add a loss-streak circuit breaker."
            )

        dd_blocks = [b for b in blockers if b["type"] == "drawdown"]
        if dd_blocks:
            pairs_str = ", ".join(b["pair"] for b in dd_blocks)
            lessons.append(
                f"**Elevated drawdown** on {pairs_str} — "
                f"review position sizing and stop-loss placement."
            )

    if not lessons:
        lessons.append(
            "No significant issues this sprint. Continue monitoring and "
            "iterating on parameter optimization."
        )

    for lesson in lessons:
        lines.append(f"  • {lesson}")
    lines.append("")

    # ── Recommendations ────────────────────────────────────────────
    lines.append("### Recommendations for Next Sprint")
    lines.append("")

    if sprint and sprint.get("backlog"):
        for item in sprint["backlog"][:3]:
            lines.append(f"  • `{item['id']}` **{item['pair']}:** "
                          f"{item['issue']} "
                          f"(impact {item['impact_score']:.4f}, {item['effort_hours']}h)")
    else:
        lines.append("  • No pending backlog items — generate fresh analytics to populate backlog.")
    lines.append("")

    lines.append("---")
    lines.append(f"*Generated at {date_str} by Research Division Sprint Manager*")

    return "\n".join(lines)


def sprint_planning(all_reports: Dict[str, dict],
                    backlog: List[dict]) -> str:
    """Generate a formatted sprint planning document.

    Selects the top 3 backlog items, provides rationale for each,
    and estimates the effort required.

    Args:
        all_reports:  Dict of pair reports from analytics engine.
        backlog:      Prioritised backlog from :func:`generate_backlog`.

    Returns:
        Formatted sprint planning text.
    """
    lines: List[str] = []
    now = _now_hkt()
    date_str = now.strftime("%Y-%m-%d %H:%M HKT")

    lines.append(f"## 🎯 Sprint Planning — {date_str}")
    lines.append("")

    if not backlog:
        if all_reports:
            lines.append("⚠️ Backlog is empty. Regenerating from current analytics...")
            lines.append("   Run ``generate_backlog(all_reports)`` to create new items.")
        else:
            lines.append("⚠️ No analytics data available and backlog is empty.")
            lines.append("   Ensure data collection and analytics engine have been executed.")
        lines.append("")
        lines.append("---")
        lines.append(f"*Generated at {date_str} by Research Division Sprint Manager*")
        return "\n".join(lines)

    # Top 3 for the sprint
    sprint_items = backlog[:3]
    total_effort = sum(item.get("effort_hours", 4) for item in sprint_items)

    # ── Sprint goal statement ──────────────────────────────────────
    goal_pairs = ", ".join(item["pair"] for item in sprint_items)
    goal_categories = ", ".join(
        sorted(set(item["category"] for item in sprint_items))
    )
    lines.append(f"**Sprint Goal:** Improve performance on {goal_pairs} "
                  f"via {goal_categories}")
    lines.append("")
    lines.append(f"- **Items:** {len(sprint_items)}")
    lines.append(f"- **Estimated effort:** {total_effort}h")
    lines.append(f"- **Backlog remaining:** {len(backlog[3:])} item(s)")
    lines.append("")

    # ── Selected items ─────────────────────────────────────────────
    lines.append("### Selected Items")
    lines.append("")

    for i, item in enumerate(sprint_items, 1):
        # Gather rationale
        pair_report = all_reports.get(item["pair"], {}) if all_reports else {}
        kpis = pair_report.get("kpis", {}) if pair_report else {}
        wr = _safe_float(kpis.get("win_rate", 0))
        trades = kpis.get("total_trades", 0) or 0
        dd = _safe_float(kpis.get("max_drawdown_pct", 0))
        cons_losses = kpis.get("max_consecutive_losses", 0) or 0

        lines.append(f"**Item #{i}: `{item['id']}` — {item['pair']}**")
        lines.append(f"  - **Issue:** {item['issue']}")
        lines.append(f"  - **Category:** {item['category']}")
        lines.append(f"  - **Impact score:** {item['impact_score']:.4f}")
        lines.append(f"  - **Effort:** {item['effort_hours']}h")
        lines.append(f"  - **Current WR:** {item['current_value']:.1%}")
        lines.append(f"  - **Target WR:** {item['target_value']:.1%}")

        # Rationale
        rationale_parts: List[str] = []
        if item["impact_score"] >= 0.1:
            rationale_parts.append("high impact score")
        if item["category"] == "reduce_risk":
            rationale_parts.append(f"drawdown {dd:.1f}% exceeds risk threshold")
        if item["category"] == "add_filter":
            if cons_losses >= CRITICAL_LOSS_STREAK:
                rationale_parts.append(f"{cons_losses} consecutive losses need filtering")
            if wr < 0.25:
                rationale_parts.append(f"critically low WR ({wr:.1%})")
        if item["category"] == "change_strategy":
            pf = _safe_float(kpis.get("profit_factor", 0))
            rationale_parts.append(f"profit factor {pf:.2f} indicates strategy degradation")
        if item["category"] == "optimize_params":
            rationale_parts.append(f"room for improvement from current {wr:.1%} to target {item['target_value']:.1%}")

        lines.append(f"  - **Rationale:** {', '.join(rationale_parts)}")
        lines.append("")

    # ── Capacity planning ──────────────────────────────────────────
    lines.append("### Capacity Plan")
    lines.append("")

    sprint_hours = 24  # 24-hour sprint (08:00 → next 08:00)
    if total_effort > sprint_hours:
        lines.append(f"⚠️ **Over capacity!** {total_effort}h exceeds {sprint_hours}h sprint window.")
        lines.append(f"Consider reducing scope or adjusting effort estimates.")
    else:
        buffer_h = sprint_hours - total_effort
        lines.append(f"✅ **Within capacity.** {total_effort}/{sprint_hours}h planned "
                      f"({buffer_h}h buffer for blocker resolution and testing).")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated at {date_str} by Research Division Sprint Manager*")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience: run the full sprint lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


def run_sprint_lifecycle(all_reports: Dict[str, dict],
                         open_positions: List[dict],
                         innovation_results: Optional[List[dict]] = None) -> dict:
    """Run the full sprint lifecycle: generate backlog → create sprint → track.

    This is the primary entry point for the deployment engine. It:

    1. Generates a fresh backlog from analytics
    2. Checks if a sprint already exists — if so, returns its state
    3. Otherwise creates a new sprint from the backlog
    4. Returns the sprint state plus generated artefacts

    Args:
        all_reports:         Dict from analytics engine.
        open_positions:      List of currently open positions.
        innovation_results:  Optional innovation sprint results.

    Returns:
        Dict with keys: ``sprint``, ``backlog``, ``blockers``, ``standup``.
    """
    result: Dict[str, Any] = {}

    # 1. Generate backlog
    backlog = generate_backlog(all_reports, innovation_results)
    result["backlog"] = backlog

    # 2. Check for existing sprint
    existing = get_sprint()
    if existing and existing.get("items"):
        sprint = existing
        logger.info("Reusing existing sprint #%d", sprint.get("sprint_number"))
    else:
        # Create new sprint from backlog
        if backlog:
            sprint = create_sprint(backlog)
            logger.info("Created new sprint #%d", sprint.get("sprint_number"))
        else:
            sprint = _new_sprint_state()
            logger.info("No backlog items — empty sprint created")

    result["sprint"] = sprint

    # 3. Detect blockers
    blockers = detect_blockers(all_reports, open_positions)
    result["blockers"] = blockers

    # 4. Generate standup
    standup = daily_standup(all_reports, sprint)
    result["standup"] = standup

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(description="Sprint Manager — Agile PM + Scrum Master")
    parser.add_argument("--action", choices=["status", "plan", "standup", "review",
                                             "create", "complete", "blockers", "full"],
                        default="status",
                        help="Sprint management action (default: status)")
    parser.add_argument("--item-id", help="Item ID for update actions")
    parser.add_argument("--status", choices=["pending", "in_progress", "testing",
                                              "deployed", "failed"],
                        help="New status for an update action")

    args = parser.parse_args()

    if args.action == "status":
        sprint = get_sprint()
        if sprint:
            print(f"=== Sprint #{sprint['sprint_number']} ===")
            print(f"  Started: {sprint.get('start_time', '?')}")
            print(f"  Status: {'Active' if not sprint.get('end_time') else 'Completed'}")
            print(f"  Items ({len(sprint['items'])}):")
            for item in sprint["items"]:
                status_icon = {"pending": "⏳", "in_progress": "🔄", "testing": "🧪",
                               "deployed": "✅", "failed": "❌"}.get(item["status"], "❓")
                print(f"    {status_icon} {item['id']} {item['pair']} => {item['status']}")
            print(f"  Backlog remaining: {len(sprint.get('backlog', []))}")
            print(f"  Completed items: {len(sprint.get('completed', []))}")
            metrics = sprint.get("metrics", {})
            print(f"  Metrics: deployed={metrics.get('improvements_deployed', 0)}, "
                  f"WR_delta={metrics.get('win_rate_change', 0):+.2%}")
        else:
            print("No active sprint. Run with --action=create to start one.")

    elif args.action == "plan":
        if args.item_id and args.status:
            result = update_sprint_item(args.item_id, args.status)
            if result:
                print(f"Updated {args.item_id} → {args.status}")
            else:
                print(f"Failed to update {args.item_id}")
        else:
            print("Usage: --action=plan --item-id=BL-0001 --status=in_progress")

    elif args.action == "create":
        try:
            from data_collector import fetch_all
            from analytics_engine import generate_all_reports

            data = fetch_all(days=30)
            trades = data.get("trade_history", [])
            equity = data.get("equity_curve", [])
            positions = data.get("open_positions", [])
            reports = generate_all_reports(trades, equity, positions)

            backlog = generate_backlog(reports)
            sprint = create_sprint(backlog)
            print(f"Sprint #{sprint['sprint_number']} created with {len(sprint['items'])} item(s)")
            for item in sprint["items"]:
                print(f"  • {item['id']} {item['pair']}: {item['description']} "
                      f"(impact={item['impact_score']:.4f})")
        except Exception as e:
            print(f"Error creating sprint: {e}")

    elif args.action == "complete":
        result = complete_sprint()
        if result:
            print(f"Sprint completed. Next sprint #{result.get('sprint_number', '?')} ready "
                  f"with {len(result.get('items', []))} item(s).")
        else:
            print("No sprint to complete.")

    elif args.action == "standup":
        try:
            from data_collector import fetch_all
            from analytics_engine import generate_all_reports

            data = fetch_all(days=30)
            trades = data.get("trade_history", [])
            equity = data.get("equity_curve", [])
            positions = data.get("open_positions", [])
            reports = generate_all_reports(trades, equity, positions)
            sprint = get_sprint()
            print(daily_standup(reports, sprint))
        except Exception as e:
            print(f"Error generating standup: {e}")

    elif args.action == "review":
        try:
            from data_collector import fetch_all
            from analytics_engine import generate_all_reports

            data = fetch_all(days=30)
            trades = data.get("trade_history", [])
            equity = data.get("equity_curve", [])
            positions = data.get("open_positions", [])
            reports = generate_all_reports(trades, equity, positions)
            sprint = get_sprint()
            print(sprint_review(reports, sprint))
        except Exception as e:
            print(f"Error generating review: {e}")

    elif args.action == "blockers":
        try:
            from data_collector import fetch_all
            from analytics_engine import generate_all_reports

            data = fetch_all(days=30)
            trades = data.get("trade_history", [])
            equity = data.get("equity_curve", [])
            positions = data.get("open_positions", [])
            reports = generate_all_reports(trades, equity, positions)
            blockers = detect_blockers(reports, positions)
            print(f"=== Blockers ({len(blockers)}) ===")
            for b in blockers:
                icon = "🔴" if b["severity"] == "critical" else "🟡"
                print(f"  {icon} [{b['severity'].upper()}] {b['pair']}: {b['message']}")
                print(f"     {b.get('detail', '')}")
        except Exception as e:
            print(f"Error detecting blockers: {e}")

    elif args.action == "full":
        try:
            from data_collector import fetch_all
            from analytics_engine import generate_all_reports

            data = fetch_all(days=30)
            trades = data.get("trade_history", [])
            equity = data.get("equity_curve", [])
            positions = data.get("open_positions", [])
            reports = generate_all_reports(trades, equity, positions)

            result = run_sprint_lifecycle(reports, positions)
            print("=== Sprint Lifecycle Complete ===")
            print(f"Sprint #{result['sprint']['sprint_number']}")
            print(f"Backlog: {len(result['backlog'])} item(s)")
            print(f"Blockers: {len(result['blockers'])}")
            print(f"\nStandup:\n{result['standup']}")
        except Exception as e:
            print(f"Error in full lifecycle: {e}")
