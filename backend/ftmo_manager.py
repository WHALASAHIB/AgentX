"""
FTMO Challenge Manager — Track prop firm challenge progress.
Manages challenges from Phase 1 → Phase 2 → Funded.
Data stored in backend's JSON store for persistence.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Standard FTMO rules
FTMO_RULES = {
    "phase1": {
        "profit_target_pct": 10.0,
        "max_drawdown_pct": 10.0,
        "min_trading_days": 10,
        "description": "Phase 1: Hit 10% profit, stay under 10% DD, min 10 trading days"
    },
    "phase2": {
        "profit_target_pct": 5.0,
        "max_drawdown_pct": 5.0,
        "min_trading_days": 10,
        "description": "Phase 2: Hit 5% profit, stay under 5% DD, min 10 trading days"
    },
    "funded": {
        "description": "Funded account — no profit target, 10% max DD, 80% profit split"
    }
}

# Account size pricing and targets
ACCOUNT_SIZES = {
    "10k":  {"fee": 155,  "capital": 10000,  "p1_target": 1000,  "p1_max_dd": 1000,  "p2_target": 500,   "p2_max_dd": 500,   "profit_split": 0.80},
    "25k":  {"fee": 325,  "capital": 25000,  "p1_target": 2500,  "p1_max_dd": 2500,  "p2_target": 1250,  "p2_max_dd": 1250,  "profit_split": 0.80},
    "50k":  {"fee": 540,  "capital": 50000,  "p1_target": 5000,  "p1_max_dd": 5000,  "p2_target": 2500,  "p2_max_dd": 2500,  "profit_split": 0.80},
    "100k": {"fee": 1080, "capital": 100000, "p1_target": 10000, "p1_max_dd": 10000, "p2_target": 5000,  "p2_max_dd": 5000,  "profit_split": 0.80},
    "200k": {"fee": 2160, "capital": 200000, "p1_target": 20000, "p1_max_dd": 20000, "p2_target": 10000, "p2_max_dd": 10000, "profit_split": 0.80},
}

# Path for local JSON storage (backup to backend JSON store)
CHALLENGES_FILE = Path(__file__).resolve().parent.parent / "backend" / "db" / "ftmo_challenges.json"


def _load_challenges() -> list[dict]:
    """Load challenges from local JSON file."""
    if not CHALLENGES_FILE.exists():
        return []
    try:
        with open(CHALLENGES_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load FTMO challenges: %s", e)
        return []


def _save_challenges(challenges: list[dict]) -> None:
    """Save challenges to local JSON file."""
    CHALLENGES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHALLENGES_FILE, "w") as f:
        json.dump(challenges, f, indent=2, default=str)
    logger.info("Saved %d FTMO challenges", len(challenges))


def list_challenges() -> list[dict]:
    """Return all challenges."""
    return _load_challenges()


def get_challenge(challenge_id: str) -> Optional[dict]:
    """Get a single challenge by ID."""
    for c in _load_challenges():
        if c.get("id") == challenge_id:
            return c
    return None


def create_challenge(
    account_size: str,
    bot_name: str = "gold_bot",
    notes: str = "",
) -> dict:
    """
    Create a new FTMO challenge tracking record.
    
    Args:
        account_size: "10k", "25k", "50k", "100k", or "200k"
        bot_name: Which bot is running this challenge
        notes: Optional notes
    
    Returns:
        The challenge dict
    """
    size_info = ACCOUNT_SIZES.get(account_size)
    if not size_info:
        raise ValueError(f"Unknown account size: {account_size}. Use: {', '.join(ACCOUNT_SIZES.keys())}")

    import uuid
    challenge = {
        "id": str(uuid.uuid4())[:8],
        "account_size": account_size,
        "capital": size_info["capital"],
        "fee": size_info["fee"],
        "bot_name": bot_name,
        "phase": "phase1",
        "status": "active",  # active, passed, failed
        "profit_pct": 0.0,
        "loss_pct": 0.0,
        "current_balance": size_info["capital"],
        "peak_balance": size_info["capital"],
        "trading_days": 0,
        "trades_taken": 0,
        "consecutive_losses": 0,
        "max_consecutive_losses": 0,
        "max_drawdown_pct": 0.0,
        "p1_profit_target": size_info["p1_target"],
        "p1_max_dd": size_info["p1_max_dd"],
        "p2_profit_target": size_info["p2_target"],
        "p2_max_dd": size_info["p2_max_dd"],
        "profit_split": size_info["profit_split"],
        "started_at": datetime.utcnow().isoformat(),
        "phase1_started_at": datetime.utcnow().isoformat(),
        "phase2_started_at": None,
        "funded_at": None,
        "payouts": [],
        "notes": notes,
    }
    
    challenges = _load_challenges()
    challenges.append(challenge)
    _save_challenges(challenges)
    
    logger.info("Created FTMO %s challenge #%s (bot=%s)", account_size, challenge["id"], bot_name)
    return challenge


def update_challenge(challenge_id: str, updates: dict) -> Optional[dict]:
    """Update a challenge's fields."""
    challenges = _load_challenges()
    for i, c in enumerate(challenges):
        if c.get("id") == challenge_id:
            challenges[i].update(updates)
            _save_challenges(challenges)
            return challenges[i]
    return None


def record_trade(challenge_id: str, pnl: float, pnl_pips: float) -> Optional[dict]:
    """
    Record a completed trade's effect on a challenge.
    Updates balance, drawdown, profit %, trading days.
    Also checks if phase conditions are met.
    
    Args:
        challenge_id: Which challenge
        pnl: Profit/loss in dollars
        pnl_pips: Profit/loss in pips
    
    Returns:
        Updated challenge dict with status check
    """
    challenge = get_challenge(challenge_id)
    if not challenge:
        return None
    
    # Update state
    challenge["trades_taken"] += 1
    challenge["current_balance"] += pnl
    if challenge["current_balance"] > challenge["peak_balance"]:
        challenge["peak_balance"] = challenge["current_balance"]
    
    # Calculate drawdown from peak
    dd_from_peak = (challenge["peak_balance"] - challenge["current_balance"]) / challenge["peak_balance"] * 100
    if dd_from_peak > challenge["max_drawdown_pct"]:
        challenge["max_drawdown_pct"] = round(dd_from_peak, 2)
    
    # Profit/loss percentages
    challenge["profit_pct"] = round((challenge["current_balance"] - challenge["capital"]) / challenge["capital"] * 100, 2)
    challenge["loss_pct"] = round(max(0, -challenge["profit_pct"]), 2)
    
    # Consecutive loss tracking
    if pnl < 0:
        challenge["consecutive_losses"] += 1
        challenge["max_consecutive_losses"] = max(challenge["max_consecutive_losses"], challenge["consecutive_losses"])
    else:
        challenge["consecutive_losses"] = 0
    
    # Trading day tracking (count unique dates)
    today = date.today().isoformat()
    if not challenge.get("_trading_dates"):
        challenge["_trading_dates"] = []
    if today not in challenge["_trading_dates"]:
        challenge["_trading_dates"].append(today)
    challenge["trading_days"] = len(challenge["_trading_dates"])
    
    # Check phase conditions
    result = check_phase_status(challenge)
    
    # Save
    return update_challenge(challenge_id, challenge)


def check_phase_status(challenge: dict) -> dict:
    """
    Evaluate whether the current phase is passed or failed.
    
    Returns:
        dict with: phase_status, message, passed (bool), failed (bool)
    """
    phase = challenge["phase"]
    balance = challenge["current_balance"]
    capital = challenge["capital"]
    profit_pct = challenge["profit_pct"]
    max_dd_pct = challenge["max_drawdown_pct"]
    trading_days = challenge["trading_days"]
    
    result = {
        "phase": phase,
        "phase_status": "in_progress",
        "passed": False,
        "failed": False,
        "message": "",
        "progress_pct": 0.0,
    }
    
    if phase == "phase1":
        target = challenge["p1_profit_target"]
        dd_limit = challenge["p1_max_dd"]
        progress = min(100, round((balance - capital) / target * 100, 1))
        result["progress_pct"] = progress
        
        # Check failure
        if balance <= capital - dd_limit:
            result["phase_status"] = "failed"
            result["failed"] = True
            result["message"] = f"❌ PHASE 1 FAILED: Drawdown exceeded ${dd_limit} (balance=${balance:.2f})"
            return result
        
        # Check pass
        min_days_met = trading_days >= FTMO_RULES["phase1"]["min_trading_days"]
        profit_met = balance >= capital + target
        
        if profit_met and min_days_met:
            result["phase_status"] = "passed"
            result["passed"] = True
            result["message"] = f"✅ PHASE 1 PASSED! Profit=${balance - capital:.2f} in {trading_days} trading days"
        elif profit_met:
            result["message"] = f"⚠️ Profit target met! Need {FTMO_RULES['phase1']['min_trading_days'] - trading_days} more trading days"
        elif min_days_met:
            result["message"] = f"📊 Need ${capital + target - balance:.2f} more profit to pass Phase 1"
        else:
            result["message"] = f"📊 {progress}% to target | {trading_days}/{FTMO_RULES['phase1']['min_trading_days']} trading days"
    
    elif phase == "phase2":
        target = challenge["p2_profit_target"]
        dd_limit = challenge["p2_max_dd"]
        progress = min(100, round((balance - capital) / target * 100, 1))
        result["progress_pct"] = progress
        
        if balance <= capital - dd_limit:
            result["phase_status"] = "failed"
            result["failed"] = True
            result["message"] = f"❌ PHASE 2 FAILED: Drawdown exceeded ${dd_limit} (balance=${balance:.2f})"
            return result
        
        min_days_met = trading_days >= FTMO_RULES["phase2"]["min_trading_days"]
        profit_met = balance >= capital + target
        
        if profit_met and min_days_met:
            result["phase_status"] = "passed"
            result["passed"] = True
            result["message"] = f"✅ PHASE 2 PASSED! Account FUNDED! Profit=${balance - capital:.2f}"
        elif profit_met:
            result["message"] = f"⚠️ Profit target met! Need {FTMO_RULES['phase2']['min_trading_days'] - trading_days} more trading days"
        elif min_days_met:
            result["message"] = f"📊 Need ${capital + target - balance:.2f} more profit to pass Phase 2"
        else:
            result["message"] = f"📊 {progress}% to target | {trading_days}/{FTMO_RULES['phase2']['min_trading_days']} trading days"
    
    elif phase == "funded":
        dd_limit = challenge.get("p1_max_dd", capital * 0.10)
        if balance <= capital - dd_limit:
            result["phase_status"] = "failed"
            result["failed"] = True
            result["message"] = f"❌ ACCOUNT BREACHED: Drawdown exceeded ${dd_limit}"
        else:
            profit = balance - capital
            result["message"] = f"💰 Funded account | Current P&L: ${profit:.2f} ({profit_pct:.2f}%)"
    
    return result


def advance_phase(challenge_id: str) -> Optional[dict]:
    """Move challenge to next phase (Phase 1 → Phase 2, Phase 2 → Funded)."""
    challenge = get_challenge(challenge_id)
    if not challenge:
        return None
    
    phase = challenge["phase"]
    now = datetime.utcnow().isoformat()
    
    if phase == "phase1":
        challenge["phase"] = "phase2"
        challenge["phase2_started_at"] = now
        challenge["consecutive_losses"] = 0
        challenge["_trading_dates"] = []
        challenge["trading_days"] = 0
        challenge["max_drawdown_pct"] = 0.0
        msg = "📈 Advanced to Phase 2!"
    elif phase == "phase2":
        challenge["phase"] = "funded"
        challenge["funded_at"] = now
        challenge["consecutive_losses"] = 0
        challenge["_trading_dates"] = []
        challenge["max_drawdown_pct"] = 0.0
        msg = "🎉 Account FUNDED! Profit split activated."
    else:
        return challenge  # Already funded
    
    logger.info("FTMO %s: %s (phase=%s)", challenge_id, msg, challenge["phase"])
    challenge["_message"] = msg
    return update_challenge(challenge_id, challenge)


def get_summary() -> dict:
    """Get consolidated summary across all challenges."""
    challenges = _load_challenges()
    active = [c for c in challenges if c["status"] == "active"]
    total_capital = sum(c["capital"] for c in challenges if c["status"] == "active")
    total_pnl = sum(c["current_balance"] - c["capital"] for c in challenges if c["status"] == "active")
    total_fees = sum(c["fee"] for c in challenges)
    
    return {
        "total_challenges": len(challenges),
        "active_challenges": len(active),
        "total_capital": total_capital,
        "total_pnl": round(total_pnl, 2),
        "total_fees_paid": total_fees,
        "net_equity": round(total_capital + total_pnl - total_fees, 2),
        "funded_accounts": len([c for c in challenges if c["phase"] == "funded"]),
        "phases": {
            "phase1": len([c for c in challenges if c["phase"] == "phase1"]),
            "phase2": len([c for c in challenges if c["phase"] == "phase2"]),
            "funded": len([c for c in challenges if c["phase"] == "funded"]),
        },
    }
