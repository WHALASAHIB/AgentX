"""
deployment_engine.py — Deploys strategy improvements with backup, validation,
bot restart, and rollback.

Pipeline:
    1) Backup current strategy file
    2) Modify strategy params via regex on __init__ signature
    3) Verify the file is valid (can be imported)
    4) Restart affected bot(s) via dashboard API or local process management
    5) Record deployment in state/deployment_history.json
    6) Canary + auto-rollback for safe_deploy()

Usage:
    python deployment_engine.py --deploy --pair EURUSD --strategy macd ^
        --params '{"fast_period": 12, "slow_period": 26}'
    python deployment_engine.py --rollback --pair EURUSD --strategy macd
    python deployment_engine.py --status --pair EURUSD
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent  # C:\Trading
RESEARCH_DIR = BASE_DIR / "research_division"
STRATEGIES_DIR = BASE_DIR / "backtester" / "active_strategies"
BOTS_DIR = BASE_DIR / "bots"
ACTIVE_BOTS_DIR = BOTS_DIR / "active_bots"
STATE_DIR = RESEARCH_DIR / "state"
DEPLOYMENT_HISTORY_FILE = STATE_DIR / "deployment_history.json"

os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(STRATEGIES_DIR, exist_ok=True)

# ── API endpoints ───────────────────────────────────────────────────────────
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://10.10.10.100:8003")
DASHBOARD_TIMEOUT = 15  # seconds

# ── Strategy file name mapping ──────────────────────────────────────────────
STRATEGY_FILE_MAP: Dict[str, str] = {
    "macd": "macd_crossover.py",
    "goldphoenix": "gold_phoenix.py",
    "bollinger": "bollinger_bands.py",
    "sma": "sma_crossover.py",
}

# ── Strategy display name → bot name key (matches backend _STRATEGY_DISPLAY_MAP)
STRATEGY_DISPLAY_MAP: Dict[str, str] = {
    "macd": "MACD",
    "goldphoenix": "GoldPhoenix",
    "bollinger": "Bollinger",
    "sma": "SMA",
}

# ── Helpers ─────────────────────────────────────────────────────────────────


def _strategy_file_name(strategy: str) -> str:
    """Return the actual .py filename for a strategy key (e.g. 'macd' -> 'macd_crossover.py')."""
    return STRATEGY_FILE_MAP.get(strategy, f"{strategy}.py")


def _strategy_display_name(strategy: str) -> str:
    """Return the display name used in bot naming (e.g. 'macd' -> 'MACD')."""
    return STRATEGY_DISPLAY_MAP.get(strategy, strategy.capitalize())


def _strategy_file_path(pair: str, strategy: str) -> Path:
    """Full path to the strategy file: active_strategies/<PAIR>/<strategy>.py"""
    return STRATEGIES_DIR / pair.upper() / _strategy_file_name(strategy)


def _bot_name(pair: str, strategy: str) -> str:
    """Bot name as used by the backend: e.g. 'MACD_EURUSD'."""
    display = _strategy_display_name(strategy)
    return f"{display}_{pair.upper()}"


def _bot_script_path(pair: str, strategy: str) -> Path:
    """Path to the bot runner script: active_bots/<PAIR>/run_<strategy>.py"""
    # strategy for the run script name uses the short key (macd, goldphoenix, etc.)
    return ACTIVE_BOTS_DIR / pair.upper() / f"run_{strategy}.py"


# ════════════════════════════════════════════════════════════════════════════
# 1. STRATEGY FILE OPERATIONS
# ════════════════════════════════════════════════════════════════════════════


def read_strategy_file(pair: str, strategy: str) -> str:
    """Read the full content of a strategy file.

    Args:
        pair: Trading pair (e.g. 'EURUSD', 'XAUUSD')
        strategy: Strategy key (e.g. 'macd', 'goldphoenix')

    Returns:
        File content as string, or raises FileNotFoundError.
    """
    path = _strategy_file_path(pair, strategy)
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path}")
    return path.read_text(encoding="utf-8")


def modify_strategy_params(
    pair: str,
    strategy: str,
    new_params: Dict[str, Any],
) -> bool:
    """Modify parameter default values in a strategy file's __init__ method.

    Creates a timestamped backup in active_strategies/<PAIR>/backups/ first.
    Uses regex to find 'param=value' or 'param: type = value' in the __init__
    signature and replaces the default value.

    Args:
        pair: Trading pair (e.g. 'EURUSD')
        strategy: Strategy key (e.g. 'macd')
        new_params: Dict mapping param name -> new default value
                    e.g. {'fast': 10, 'slow': 21}

    Returns:
        True on success, False on failure.
    """
    path = _strategy_file_path(pair, strategy)
    if not path.exists():
        logger.error("Strategy file not found: %s", path)
        return False

    # ── 1. Backup ──────────────────────────────────────────────────────────
    backup_path = _create_backup(pair, strategy)
    if not backup_path:
        logger.error("Backup creation failed, aborting modification.")
        return False

    # ── 2. Read & modify ───────────────────────────────────────────────────
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to read %s: %s", path, e)
        return False

    modified = _apply_param_modifications(content, new_params)
    if modified == content:
        logger.warning("No parameters were modified (params may not match __init__ signature).")
        return False

    try:
        path.write_text(modified, encoding="utf-8")
        logger.info("Modified %s with params %s (backup: %s)", path.name, new_params, backup_path)
    except Exception as e:
        logger.error("Failed to write modified file %s: %s", path, e)
        return False

    return True


def _create_backup(pair: str, strategy: str) -> Optional[Path]:
    """Create a timestamped backup of a strategy file.

    Returns the backup path, or None on failure.
    """
    src = _strategy_file_path(pair, strategy)
    if not src.exists():
        return None

    backups_dir = STRATEGIES_DIR / pair.upper() / "backups"
    os.makedirs(backups_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    stem = src.stem  # e.g. 'macd_crossover'
    backup_path = backups_dir / f"{stem}_{timestamp}.py.bak"

    try:
        shutil.copy2(str(src), str(backup_path))
        logger.info("Backup created: %s", backup_path)
        return backup_path
    except Exception as e:
        logger.error("Failed to create backup: %s", e)
        return None


def _apply_param_modifications(content: str, new_params: Dict[str, Any]) -> str:
    """Replace parameter default values in a strategy __init__ signature.

    Handles three patterns:
        - param=value         (no type annotation)
        - param: type = value (with type annotation, spaces around '=')
        - param:type=value    (with type annotation, no spaces)

    Also handles:
        - self.slow = slow    (assignment after params are stored)

    Works with single-line and multi-line __init__ signatures.
    """
    lines = content.splitlines(keepends=True)
    result = []

    # Track whether we are inside __init__ to limit scope
    in_init = False
    init_params_seen = set()

    # Pre-compile patterns for each param
    param_patterns: List[Tuple[str, Any, re.Pattern, re.Pattern, re.Pattern]] = []
    for param_name, new_value in new_params.items():
        val_str = _format_param_value(new_value)
        # Pattern 1: param: type = value  (typed annotation)
        p1 = re.compile(r"(\b" + re.escape(param_name) + r"\s*:\s*\w+\s*=\s*)[\d.]+")
        # Pattern 2: param=value  (bare, no type)
        p2 = re.compile(r"(\b" + re.escape(param_name) + r"\s*=\s*)[\d.]+")
        # Pattern 3: self.param = ...
        p3 = re.compile(r"(self\.\s*" + re.escape(param_name) + r"\s*=\s*)[\d.\w]+")
        param_patterns.append((param_name, val_str, p1, p2, p3))

    # Patterns shared across params
    init_def_re = re.compile(r"def\s+__init__\s*\(")
    init_close_re = re.compile(r"\)\s*:")

    for line in lines:
        modified_line = line

        # Detect start of __init__ signature
        if init_def_re.search(line):
            in_init = True

        # Apply signature param patterns to ANY line inside __init__ def
        # (handles single-line defs and multi-line continuation signatures)
        if in_init:
            for param_name, val_str, p1, p2, p3 in param_patterns:
                if param_name in init_params_seen:
                    # Already found in signature; still apply self.X assignment
                    m3 = p3.search(modified_line)
                    if m3:
                        modified_line = p3.sub(rf"\g<1>{val_str}", modified_line)
                    continue

                # Try typed param pattern first  (param: type = value)
                m1 = p1.search(modified_line)
                if m1:
                    modified_line = p1.sub(rf"\g<1>{val_str}", modified_line)
                    init_params_seen.add(param_name)
                    # Also apply self.X assignment on this same line if present
                    m3 = p3.search(modified_line)
                    if m3:
                        modified_line = p3.sub(rf"\g<1>{val_str}", modified_line)
                    continue

                # Try bare param pattern  (param=value)
                m2 = p2.search(modified_line)
                if m2:
                    modified_line = p2.sub(rf"\g<1>{val_str}", modified_line)
                    init_params_seen.add(param_name)
                    m3 = p3.search(modified_line)
                    if m3:
                        modified_line = p3.sub(rf"\g<1>{val_str}", modified_line)

        # Detect end of __init__ signature
        if in_init and init_close_re.search(line):
            in_init = False

        result.append(modified_line)

    return "".join(result)


def _format_param_value(value: Any) -> str:
    """Format a parameter value as a Python literal string."""
    if isinstance(value, float):
        # Preserve trailing zero? repr() does the right thing for floats
        return repr(value)
    elif isinstance(value, bool):
        return "True" if value else "False"
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, str):
        return f'"{value}"'
    return str(value)


def rollback_strategy(pair: str, strategy: str) -> bool:
    """Restore a strategy file from the most recent backup.

    Finds the newest .bak file in active_strategies/<PAIR>/backups/ and
    copies it over the current strategy file.

    Args:
        pair: Trading pair
        strategy: Strategy key

    Returns:
        True on success, False if no backup exists.
    """
    backups_dir = STRATEGIES_DIR / pair.upper() / "backups"
    if not backups_dir.is_dir():
        logger.error("No backups directory for %s/%s", pair, strategy)
        return False

    # Find all .bak files matching this strategy
    stem = _strategy_file_path(pair, strategy).stem
    bak_files = sorted(backups_dir.glob(f"{stem}_*.py.bak"), reverse=True)
    if not bak_files:
        logger.error("No backup files found in %s", backups_dir)
        return False

    latest_backup = bak_files[0]
    target = _strategy_file_path(pair, strategy)

    try:
        shutil.copy2(str(latest_backup), str(target))
        logger.info("Rolled back %s/%s from %s", pair, strategy, latest_backup.name)
        return True
    except Exception as e:
        logger.error("Rollback failed: %s", e)
        return False


# ════════════════════════════════════════════════════════════════════════════
# 2. DEPLOYMENT PIPELINE
# ════════════════════════════════════════════════════════════════════════════


def deploy_improvement(
    improvement_item: Dict[str, Any],
    sprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Deploy a validated strategy improvement to live.

    Pipeline:
        1) Backup current strategy file
        2) Modify strategy params
        3) Verify the file can be imported
        4) Restart affected bot(s)
        5) Record deployment in history

    Args:
        improvement_item: A validated improvement dict from the sprint manager.
            Expected structure:
            {
                'pair': 'EURUSD',
                'strategy_name': 'macd',
                'strategy_params_used': {'fast': 10, 'slow': 26, 'signal': 9},
                'variant_name': 'macd_fast=10',
                ... (other metrics)
            }
        sprint: Optional sprint context dict (for richer history).

    Returns:
        Dict with {success, new_file, backup_file, restart_result, ...}
    """
    pair = improvement_item.get("pair", "").upper()
    strategy = improvement_item.get("strategy_name", "")
    params = improvement_item.get("strategy_params_used", {})
    variant_name = improvement_item.get("variant_name", "unknown")

    if not pair or not strategy:
        return {"success": False, "error": "Missing pair or strategy_name in improvement_item"}

    if not params:
        return {"success": False, "error": "No strategy_params_used in improvement_item"}

    new_params = _normalize_params_for_strategy(strategy, params)

    result: Dict[str, Any] = {
        "pair": pair,
        "strategy": strategy,
        "variant_name": variant_name,
        "new_params": new_params,
        "sprint_id": (sprint or {}).get("sprint_id", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # 1) Backup
        backup_file = _create_backup(pair, strategy)
        result["backup_file"] = str(backup_file) if backup_file else None
        if not backup_file:
            result.update({"success": False, "error": "Backup creation failed"})
            save_deployment(result)
            return result

        # 2) Modify params
        if not modify_strategy_params(pair, strategy, new_params):
            result.update({"success": False, "error": "Parameter modification failed"})
            save_deployment(result)
            return result

        result["new_file"] = str(_strategy_file_path(pair, strategy))
        # Record the file's content hash for audit
        result["content_hash"] = _file_hash(_strategy_file_path(pair, strategy))

        # 3) Verify — try to import the module
        valid, verify_msg = _verify_strategy_file(pair, strategy)
        result["verification"] = {"valid": valid, "message": verify_msg}
        if not valid:
            logger.error("Verification failed: %s — rolling back", verify_msg)
            rollback_strategy(pair, strategy)
            result.update({"success": False, "error": f"Verification failed: {verify_msg}", "rolled_back": True})
            save_deployment(result)
            return result

        # 4) Restart bot(s)
        restart_result = restart_all_bots_for_pair(pair)
        result["restart_result"] = restart_result
        all_ok = all(r.get("success", False) for r in restart_result)
        result["success"] = all_ok
        if not all_ok:
            result["warning"] = "Some bots may not have restarted cleanly"

        # 5) Record
        save_deployment(result)

    except Exception as e:
        logger.error("Deploy failed: %s\n%s", e, traceback.format_exc())
        result.update({"success": False, "error": str(e)})
        save_deployment(result)

    return result


def safe_deploy(
    improvement_item: Dict[str, Any],
    sprint: Optional[Dict[str, Any]] = None,
    canary_bots: int = 1,
    monitor_trades: int = 5,
    monitor_timeout_minutes: int = 60,
) -> Dict[str, Any]:
    """Canary-safe deployment with automatic rollback on performance degradation.

    1) Deploy to a subset of bots (canary)
    2) Monitor for N trades or timeout
    3) If performance degrades → auto-rollback
    4) If healthy → roll out to all remaining bots

    Args:
        improvement_item: Same as deploy_improvement.
        sprint: Optional sprint context.
        canary_bots: Number of canary bots to test (default 1).
        monitor_trades: Trades to observe before full rollout (default 5).
        monitor_timeout_minutes: Max time to wait before aborting canary.

    Returns:
        Dict with detailed canary + rollout results.
    """
    pair = improvement_item.get("pair", "").upper()
    strategy = improvement_item.get("strategy_name", "")
    params = improvement_item.get("strategy_params_used", {})

    # ── Step 1: Backup & modify (same as deploy) ───────────────────────────
    base_result = deploy_improvement(improvement_item, sprint)
    if not base_result.get("success"):
        return base_result

    result: Dict[str, Any] = {
        **base_result,
        "canary": {"deployed": False, "passed": False, "trades_observed": 0, "rollback_triggered": False},
        "full_rollout": None,
    }

    # ── Step 2: Canary — restart only one bot ──────────────────────────────
    canary_bot_name = _bot_name(pair, strategy)
    canary_result = restart_bot(pair, strategy)
    result["canary"]["deployed"] = True
    result["canary"]["bot"] = canary_bot_name

    if not canary_result["success"]:
        result["canary"]["error"] = f"Canary bot restart failed: {canary_result}"
        rollback_strategy(pair, strategy)
        result["canary"]["rollback_triggered"] = True
        result["success"] = False
        save_deployment(result)
        return result

    # ── Step 3: Monitor ────────────────────────────────────────────────────
    logger.info(
        "Canary deployment active for %s/%s. Monitoring for %d trades or %d min...",
        pair, strategy, monitor_trades, monitor_timeout_months_minutes,
    )
    # Actually use the parameter we already have
    timeout_seconds = monitor_timeout_minutes * 60
    start_time = time.time()
    trades_before = _count_trades(pair, strategy)
    trades_observed = 0
    canary_passed = False

    while time.time() - start_time < timeout_seconds:
        time.sleep(30)  # Check every 30 seconds
        trades_now = _count_trades(pair, strategy)
        new_trades = trades_now - trades_before
        if new_trades >= monitor_trades:
            trades_observed = new_trades
            # Evaluate performance of canary
            if _check_canary_health(pair, strategy):
                canary_passed = True
                logger.info("Canary passed — %d trades observed, performance healthy", new_trades)
                break
            else:
                logger.warning("Canary failed — performance degradation detected after %d trades", new_trades)
                break
        logger.debug("Canary monitoring: %d/%d trades observed, %d min elapsed",
                      new_trades, monitor_trades,
                      int((time.time() - start_time) / 60))

    result["canary"]["trades_observed"] = trades_observed
    result["canary"]["passed"] = canary_passed

    # ── Step 4: Rollback if canary failed ──────────────────────────────────
    if not canary_passed and trades_observed > 0:
        logger.warning("Canary performance degraded. Auto-rolling back %s/%s...", pair, strategy)
        if rollback_strategy(pair, strategy):
            restart_result = restart_all_bots_for_pair(pair)
            result["canary"]["rollback_triggered"] = True
            result["canary"]["rollback_result"] = restart_result
            result["success"] = False
        else:
            result["canary"]["error"] = "Rollback attempted but failed"
    elif trades_observed == 0 and (time.time() - start_time) >= timeout_seconds:
        # Timeout — no trades happened, roll back to be safe
        logger.warning("Canary timeout (%d min) with no trades. Rolling back.", monitor_timeout_minutes)
        rollback_strategy(pair, strategy)
        restart_all_bots_for_pair(pair)
        result["canary"]["rollback_triggered"] = True
        result["canary"]["error"] = "Timeout — no trades observed"
        result["success"] = False
    elif canary_passed:
        # ── Step 5: Full rollout ───────────────────────────────────────────
        logger.info("Canary passed! Rolling out %s/%s to all bots.", pair, strategy)
        rollout = restart_all_bots_for_pair(pair)
        result["full_rollout"] = rollout
        result["success"] = all(r.get("success", False) for r in rollout)

    save_deployment(result)
    return result


def _normalize_params_for_strategy(strategy: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize parameter names from variant naming to actual __init__ params.

    The strategy_innovation module may use names like 'fast_period' while the
    strategy __init__ uses 'fast'. This mapping bridges common differences.
    """
    # Common alias mappings
    ALIASES: Dict[str, Dict[str, str]] = {
        "macd": {
            "fast_period": "fast",
            "slow_period": "slow",
            "signal_period": "signal",
        },
        "bollinger": {
            "period": "bb_period",
            "std_dev": "bb_std",
        },
        "goldphoenix": {},
        "sma": {
            "fast_period": "fast",
            "slow_period": "slow",
        },
    }

    aliases = ALIASES.get(strategy, {})
    normalized: Dict[str, Any] = {}
    for key, value in params.items():
        real_key = aliases.get(key, key)
        normalized[real_key] = value
    return normalized


def _verify_strategy_file(pair: str, strategy: str) -> Tuple[bool, str]:
    """Try to import the strategy module to verify it's syntactically valid.

    Returns (valid, message).
    """
    try:
        path = _strategy_file_path(pair, strategy)
        spec = importlib.util.spec_from_file_location(
            f"active_strategies.{pair}.{path.stem}", str(path)
        )
        if spec is None:
            return False, f"Could not create module spec for {path}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True, "Module loaded successfully"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Import error: {e}"


def _file_hash(path: Path) -> str:
    """Quick content hash for audit trail."""
    import hashlib
    try:
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]
    except Exception:
        return ""


# ════════════════════════════════════════════════════════════════════════════
# 3. BOT MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════


def restart_bot(pair: str, strategy: str) -> Dict[str, Any]:
    """Restart a bot by stopping it and starting a new instance.

    Strategy:
        1. Try dashboard API first (/api/bots/{name}/stop + /api/bots/{name}/start)
        2. Fall back to local process management (find PID → kill → subprocess)

    Args:
        pair: Trading pair (e.g. 'EURUSD')
        strategy: Strategy key (e.g. 'macd')

    Returns:
        Dict with {success, method, bot_name, pid (new), error?}
    """
    bot_name = _bot_name(pair, strategy)
    result: Dict[str, Any] = {
        "bot_name": bot_name,
        "pair": pair,
        "strategy": strategy,
    }

    # ── Try dashboard API first ────────────────────────────────────────────
    api_ok = _api_restart_bot(bot_name, result)
    if api_ok:
        return result

    # If 404 (bot not found in API), try starting from scratch
    if result.get("error") and "404" in str(result.get("error")):
        # Maybe the bot doesn't exist in the API — start it directly
        pass  # Fall through to local

    # ── Fall back to local process management ──────────────────────────────
    logger.info("Dashboard API unavailable for %s — using local process control.", bot_name)
    return _local_restart_bot(pair, strategy, result)


def _api_restart_bot(bot_name: str, result: Dict[str, Any]) -> bool:
    """Attempt to restart a bot via the dashboard API.

    Returns True if API-based restart succeeded.
    Modifies result dict in-place.
    """
    # Stop
    try:
        stop_resp = requests.post(
            f"{DASHBOARD_URL}/api/bots/{bot_name}/stop",
            timeout=DASHBOARD_TIMEOUT,
        )
        if stop_resp.status_code == 404:
            # Bot not known to API — may not be registered yet
            result["warning"] = f"Bot {bot_name} not found in API (404 on stop)"
            return False
        stop_resp.raise_for_status()
        result["api_stop"] = stop_resp.json()
    except requests.ConnectionError:
        result["error"] = f"Dashboard unreachable at {DASHBOARD_URL}"
        return False
    except requests.Timeout:
        result["error"] = f"Dashboard timeout stopping {bot_name}"
        return False
    except requests.RequestException as e:
        result["error"] = str(e)
        return False

    # Brief cooldown for process to release resources
    time.sleep(2)

    # Start
    try:
        start_resp = requests.post(
            f"{DASHBOARD_URL}/api/bots/{bot_name}/start",
            timeout=DASHBOARD_TIMEOUT,
        )
        if start_resp.status_code == 409:
            # Already running — still mark as success
            result["warning"] = f"Bot {bot_name} was already running after stop"
        start_resp.raise_for_status()
        start_data = start_resp.json()
        result["method"] = "api"
        result["pid"] = start_data.get("pid")
        result["success"] = True
        return True
    except requests.RequestException as e:
        result["error"] = f"Started stopped, but start failed: {e}"
        return False


def _local_restart_bot(
    pair: str, strategy: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Restart a bot using local subprocess management (kill + spawn)."""
    # Kill existing process
    proc_info = get_bot_process_info(pair, strategy)
    if proc_info.get("pid"):
        try:
            _kill_process(proc_info["pid"])
            logger.info("Killed existing bot process PID %s", proc_info["pid"])
            result["killed_pid"] = proc_info["pid"]
            time.sleep(2)
        except Exception as e:
            logger.warning("Could not kill existing process: %s", e)

    # Start a new bot
    return _start_bot_local(pair, strategy, result)


def _start_bot_local(
    pair: str, strategy: str, result: Dict[str, Any]
) -> Dict[str, Any]:
    """Start a bot as a subprocess using multi_symbol_bot.py."""
    multi_bot_path = BOTS_DIR / "multi_symbol_bot.py"
    if not multi_bot_path.exists():
        result["success"] = False
        result["error"] = f"multi_symbol_bot.py not found at {multi_bot_path}"
        return result

    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                str(multi_bot_path),
                "--symbol", pair.upper(),
                "--strategy", strategy,
            ],
            cwd=str(BOTS_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS
                if hasattr(subprocess, "DETACHED_PROCESS") else 0,
        )
        result["method"] = "local"
        result["pid"] = proc.pid
        result["success"] = True
        logger.info("Started %s/%s bot (PID %d)", pair, strategy, proc.pid)
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)

    return result


def restart_all_bots_for_pair(pair: str) -> List[Dict[str, Any]]:
    """Restart every bot running a given trading pair.

    Scans active_bots/<PAIR>/ for all run_*.py scripts and restarts each one.

    Args:
        pair: Trading pair (e.g. 'EURUSD')

    Returns:
        List of restart result dicts.
    """
    pair_dir = ACTIVE_BOTS_DIR / pair.upper()
    if not pair_dir.is_dir():
        logger.warning("No active bots directory for pair %s at %s", pair, pair_dir)
        return []

    results = []
    for run_file in sorted(pair_dir.glob("run_*.py")):
        # Extract strategy key from filename: run_macd.py -> macd
        strategy = run_file.stem[len("run_"):]
        logger.info("Restarting bot for %s/%s", pair, strategy)
        result = restart_bot(pair, strategy)
        results.append(result)
        time.sleep(1)  # Brief stagger between restarts

    return results


def get_bot_process_info(pair: str, strategy: str) -> Dict[str, Any]:
    """Get information about a running bot process.

    Checks the dashboard API first, then falls back to psutil scan.

    Returns:
        Dict with {pid, running, uptime, method} or default with running=False.
    """
    bot_name = _bot_name(pair, strategy)
    result: Dict[str, Any] = {
        "bot_name": bot_name,
        "running": False,
        "pid": None,
        "uptime": None,
        "method": None,
    }

    # Try API first
    try:
        resp = requests.get(
            f"{DASHBOARD_URL}/api/bots/{bot_name}/status",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            result["running"] = data.get("running", False)
            result["pid"] = data.get("pid")
            if result["pid"]:
                result["method"] = "api"
            return result
    except (requests.ConnectionError, requests.Timeout, requests.RequestException):
        pass

    # Fall back to local process scan
    try:
        import psutil
    except ImportError:
        logger.debug("psutil not available for local bot scan")
        return result

    try:
        target_name = f"run_{strategy}.py"
        pair_upper = pair.upper()
        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(cmdline).lower()
                if target_name.lower() in cmd_str and pair_upper.lower() in cmd_str:
                    result["pid"] = proc.info["pid"]
                    result["running"] = True
                    result["method"] = "local_scan"
                    create_time = proc.info.get("create_time")
                    if create_time:
                        uptime_sec = time.time() - create_time
                        result["uptime"] = f"{uptime_sec:.0f}s"
                    return result
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Also check for multi_symbol_bot.py with matching --symbol and --strategy
        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(cmdline).lower()
                if ("multi_symbol_bot.py" in cmd_str
                        and f"--symbol {pair_upper.lower()}" in cmd_str
                        and f"--strategy {strategy.lower()}" in cmd_str):
                    result["pid"] = proc.info["pid"]
                    result["running"] = True
                    result["method"] = "local_scan"
                    create_time = proc.info.get("create_time")
                    if create_time:
                        uptime_sec = time.time() - create_time
                        result["uptime"] = f"{uptime_sec:.0f}s"
                    return result
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug("psutil scan failed: %s", e)

    return result


def _kill_process(pid: int) -> None:
    """Kill a process by PID. Tries graceful termination first, then force kill.

    On Windows, uses taskkill for reliability. Falls back to os.kill.
    """
    try:
        # Windows: taskkill /F as a reliable method
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            timeout=10,
        )
        return
    except Exception:
        pass

    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


# ════════════════════════════════════════════════════════════════════════════
# 4. DEPLOYMENT HISTORY
# ════════════════════════════════════════════════════════════════════════════


def save_deployment(deployment_result: Dict[str, Any]) -> None:
    """Append a deployment result to the deployment history file.

    Creates the history file if it doesn't exist. Thread-safe-ish via append.
    """
    history = load_deployment_history()
    # Ensure consistent fields
    entry = {
        **deployment_result,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    if "id" not in entry:
        entry["id"] = f"deploy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    history.append(entry)

    try:
        DEPLOYMENT_HISTORY_FILE.write_text(
            json.dumps(history, indent=2, default=str),
            encoding="utf-8",
        )
        logger.debug("Deployment saved (total: %d entries)", len(history))
    except Exception as e:
        logger.error("Failed to save deployment history: %s", e)


def load_deployment_history() -> List[Dict[str, Any]]:
    """Load all past deployment records.

    Returns:
        List of deployment result dicts, newest first.
    """
    if not DEPLOYMENT_HISTORY_FILE.exists():
        return []

    try:
        data = json.loads(DEPLOYMENT_HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Sort newest first by saved_at or timestamp
            return sorted(
                data,
                key=lambda x: x.get("saved_at", x.get("timestamp", "")),
                reverse=True,
            )
        return []
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to load deployment history: %s", e)
        return []


def get_deployment_stats() -> Dict[str, Any]:
    """Compute aggregate statistics from deployment history.

    Returns:
        Dict with {total, success_count, failure_count, rollback_count,
                   avg_improvement, strategies_deployed, success_rate_pct, ...}
    """
    history = load_deployment_history()
    if not history:
        return {
            "total": 0,
            "success_count": 0,
            "failure_count": 0,
            "rollback_count": 0,
            "success_rate_pct": 0.0,
            "strategies_deployed": [],
            "pairs_deployed": [],
        }

    total = len(history)
    success_count = sum(1 for d in history if d.get("success"))
    failure_count = total - success_count
    rollback_count = sum(
        1 for d in history
        if d.get("canary", {}).get("rollback_triggered")
           or d.get("rolled_back")
           or d.get("success") is False
    )

    # Aggregate strategies and pairs
    strategies_deployed = list(dict.fromkeys(
        d.get("strategy", "") for d in history if d.get("strategy")
    ))
    pairs_deployed = list(dict.fromkeys(
        d.get("pair", "") for d in history if d.get("pair")
    ))

    # Attempt to compute average improvement from variant deploy_score deltas
    improvements = []
    for d in history:
        if d.get("success") and "improvement_item" in d:
            item = d["improvement_item"]
            for v in item.get("all_variants", []):
                if v.get("variant_name") == d.get("variant_name"):
                    score = v.get("metrics", {}).get("deploy_score")
                    if score is not None:
                        improvements.append(score)
                    break
    avg_improvement = sum(improvements) / len(improvements) if improvements else None

    return {
        "total": total,
        "success_count": success_count,
        "failure_count": failure_count,
        "rollback_count": rollback_count,
        "success_rate_pct": round((success_count / total) * 100, 1) if total else 0.0,
        "avg_improvement_score": avg_improvement,
        "strategies_deployed": strategies_deployed,
        "pairs_deployed": pairs_deployed,
        "last_deployment": history[0] if history else None,
    }


# ════════════════════════════════════════════════════════════════════════════
# MONITORING HELPERS (for canary deployment)
# ════════════════════════════════════════════════════════════════════════════


def _count_trades(pair: str, strategy: str) -> int:
    """Count recent trades for a bot, used to detect if the bot is trading.

    Checks the state JSON files in bots/logs/ for trade counts.
    """
    state_file = BOTS_DIR / "logs" / f"{pair.upper()}_{strategy}_state.json"
    if not state_file.exists():
        return 0
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return state.get("total_trades", 0) or state.get("trade_count", 0)
    except (json.JSONDecodeError, Exception):
        return 0


def _check_canary_health(pair: str, strategy: str) -> bool:
    """Check if the canary bot is performing acceptably.

    Returns True if performance is healthy (no degradation detected).
    Right now this is a simple heuristic:
        - Bot must still be running
        - No critical errors in recent log lines
    """
    # 1. Check if bot is still running
    info = get_bot_process_info(pair, strategy)
    if not info.get("running"):
        logger.warning("Canary bot has stopped — performance check failed")
        return False

    # 2. Check recent logs for error patterns
    log_file = BOTS_DIR / "logs" / f"{pair.upper()}_{strategy}.log"
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            recent = lines[-100:]  # Last 100 lines
            error_count = sum(
                1 for line in recent
                if "ERROR" in line or "CRITICAL" in line or "Traceback" in line
            )
            if error_count > 5:
                logger.warning("Canary bot has %d recent errors — unhealthy", error_count)
                return False
        except Exception:
            pass

    return True


# ════════════════════════════════════════════════════════════════════════════
# 5. STANDALONE CLI
# ════════════════════════════════════════════════════════════════════════════


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AGENTX Deployment Engine — deploy, rollback, and manage bots.",
    )

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--deploy",
        action="store_true",
        help="Deploy a strategy improvement",
    )
    action_group.add_argument(
        "--safe-deploy",
        action="store_true",
        help="Canary-safe deployment with monitoring",
    )
    action_group.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback a strategy to the most recent backup",
    )
    action_group.add_argument(
        "--status",
        action="store_true",
        help="Show deployment status and history stats",
    )
    action_group.add_argument(
        "--history",
        action="store_true",
        help="Show full deployment history",
    )
    action_group.add_argument(
        "--restart",
        action="store_true",
        help="Restart a bot or all bots for a pair",
    )

    parser.add_argument("--pair", type=str, help="Trading pair (e.g. EURUSD)")
    parser.add_argument("--strategy", type=str, help="Strategy key (e.g. macd, goldphoenix)")
    parser.add_argument(
        "--params",
        type=str,
        default="{}",
        help='JSON string of params to modify (e.g. \'{"fast": 10, "slow": 21}\')',
    )
    parser.add_argument("--all", action="store_true", help="With --restart, restart ALL bots for the pair")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    return parser.parse_args()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Also log to a file
    log_dir = RESEARCH_DIR / "logs"
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(log_dir / "deployment_engine.log", encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(fh)


def main() -> None:
    args = _parse_cli()
    _setup_logging(args.verbose)

    if args.status:
        stats = get_deployment_stats()
        print(json.dumps(stats, indent=2, default=str))
        return

    if args.history:
        history = load_deployment_history()
        print(json.dumps(history, indent=2, default=str))
        return

    if not args.pair:
        print("ERROR: --pair is required for this action", file=sys.stderr)
        sys.exit(1)

    pair = args.pair.upper()

    if args.deploy or args.safe_deploy:
        if not args.strategy:
            print("ERROR: --strategy is required with --deploy", file=sys.stderr)
            sys.exit(1)
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid --params JSON: {e}", file=sys.stderr)
            sys.exit(1)

        # Build a minimal improvement_item from CLI args
        improvement_item = {
            "pair": pair,
            "strategy_name": args.strategy,
            "strategy_params_used": params,
            "variant_name": f"{args.strategy}_cli_{datetime.now(timezone.utc).strftime('%H%M%S')}",
        }

        if args.safe_deploy:
            result = safe_deploy(improvement_item)
        else:
            result = deploy_improvement(improvement_item)

        print(json.dumps(result, indent=2, default=str))
        if result.get("success"):
            print(f"\n✓ Deployment successful for {pair}/{args.strategy}")
        else:
            print(f"\n✗ Deployment failed: {result.get('error', 'unknown error')}")
            sys.exit(1)

    elif args.rollback:
        if not args.strategy:
            print("ERROR: --strategy is required with --rollback", file=sys.stderr)
            sys.exit(1)
        ok = rollback_strategy(pair, args.strategy)
        if ok:
            print(f"✓ Rolled back {pair}/{args.strategy} to previous version")
            # Restart the bot after rollback
            restart_result = restart_all_bots_for_pair(pair)
            print(f"  Bot restart: {json.dumps(restart_result, indent=2)}")
        else:
            print(f"✗ Rollback failed for {pair}/{args.strategy}", file=sys.stderr)
            sys.exit(1)

    elif args.restart:
        if args.all:
            results = restart_all_bots_for_pair(pair)
            print(json.dumps(results, indent=2, default=str))
        elif args.strategy:
            result = restart_bot(pair, args.strategy)
            print(json.dumps(result, indent=2, default=str))
        else:
            print("ERROR: Use --strategy or --all with --restart", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
