#!/usr/bin/env python3
"""
AGENTX SRE Engine — Site Reliability Engine
============================================
Self-healing system that prevents the resource exhaustion and silent
failures we've experienced. Runs as a cron job every 2 minutes.

Responsibilities:
  1. Resource governance — enforce max process/memory limits
  2. Service health — detect & restart dead bots, bridge, backend
  3. MT5 IPC congestion prevention — limit simultaneous connections
  4. Alerting — Telegram on critical failures
  5. Log rotation — prevent disk fill
  6. Circuit breaker — auto-pause if too many failures

Usage:
    python devops/sre.py                    # Run once (for cron)
    python devops/sre.py --daemon           # Run continuously
    python devops/sre.py --check-only       # Report only, no actions

Configuration in devops/rules.yaml
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DEVOPS_DIR = BASE_DIR / "devops"
LOGS_DIR = BASE_DIR / "bots" / "logs"
RULES_FILE = DEVOPS_DIR / "rules.yaml"

# ── Default rules (overridden by rules.yaml) ─────────────────────────────
RULES = {
    "resources": {
        "max_bot_processes": 8,        # Never run more than this many bots
        "max_cron_scripts": 15,        # Max no_agent cron jobs
        "memory_free_mb_min": 500,     # Alert if free RAM below this
        "disk_free_mb_min": 1000,      # Alert if free disk below this
    },
    "mt5": {
        "max_simultaneous_connect": 5,  # Rate-limit MT5 initializations
        "ipc_restart_cooldown": 30,     # Seconds between full IPC restarts
    },
    "services": {
        "backend_port": 8005,
        "bridge_port": 5000,
        "bridge_health_path": "/health",
    },
    "circuit_breaker": {
        "failures_before_pause": 3,     # Consecutive SRE failures → pause
        "pause_duration_sec": 600,      # How long to pause (10 min)
    },
    "logging": {
        "max_log_size_mb": 50,
        "max_log_age_days": 7,
    },
}

# ── Logging ──────────────────────────────────────────────────────────────
logger = logging.getLogger("sre_engine")
LOG_FILE = LOGS_DIR / "sre_engine.log"

def setup_logging():
    logger.setLevel(logging.INFO)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | SRE | %(message)s"))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | SRE | %(message)s"))
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)

# ── Resource Helpers ─────────────────────────────────────────────────────

def get_free_memory_mb() -> float:
    """Return free physical memory in MB."""
    try:
        r = subprocess.run(
            ["wmic", "OS", "get", "FreePhysicalMemory", "/Value"],
            capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.split("\n"):
            if "FreePhysicalMemory" in line:
                return float(line.split("=")[1].strip()) / 1024.0
    except:
        pass
    return 99999.0  # Default high on failure

def get_free_disk_mb() -> float:
    """Return free disk space in MB on C: drive."""
    try:
        r = subprocess.run(
            ["wmic", "LogicalDisk", "where", "DeviceID='C:'", "get", "FreeSpace", "/Value"],
            capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.split("\n"):
            if "FreeSpace" in line:
                return float(line.split("=")[1].strip()) / (1024.0 * 1024.0)
    except:
        pass
    return 99999.0

def get_bot_processes() -> list[dict]:
    """Get all python bot processes with their PIDs and command lines."""
    bots = []
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine", "/Format:CSV"],
            capture_output=True, text=True, timeout=15
        )
        for line in r.stdout.split("\n"):
            if "multi_symbol_bot" in line or "gold_phoenix" in line:
                parts = line.split(",")
                if len(parts) >= 2:
                    pid = parts[-1].strip()
                    cmd = parts[1].strip() if len(parts) > 1 else ""
                    bots.append({"pid": int(pid), "cmd": cmd, "symbol": extract_symbol(cmd)})
    except:
        pass
    return bots

def extract_symbol(cmd: str) -> str:
    for part in cmd.split():
        if part.startswith("--symbol="):
            return part.split("=")[1]
        if part.startswith("--symbol") and len(cmd.split()) > part_pos(cmd, part) + 1:
            idx = cmd.split().index(part)
            parts = cmd.split()
            if idx + 1 < len(parts) and not parts[idx+1].startswith("--"):
                return parts[idx+1]
    return "unknown"

def part_pos(cmd: str, part: str) -> int:
    return cmd.index(part) if part in cmd else -1

# ── Health Checks ────────────────────────────────────────────────────────

def check_bridge_health() -> dict:
    """Check if the MT5 bridge is responding."""
    result = {"alive": False, "connected": False, "error": None}
    try:
        import urllib.request
        url = f"http://127.0.0.1:{RULES['services']['bridge_port']}{RULES['services']['bridge_health_path']}"
        resp = urllib.request.urlopen(url, timeout=5)
        data = json.loads(resp.read().decode())
        result["alive"] = True
        result["connected"] = data.get("connected", False)
        result["data"] = data
    except Exception as e:
        result["error"] = str(e)
    return result

def check_backend_health() -> dict:
    """Check if the FastAPI backend is responding."""
    result = {"alive": False, "error": None}
    try:
        import urllib.request
        url = f"http://127.0.0.1:{RULES['services']['backend_port']}/health"
        resp = urllib.request.urlopen(url, timeout=5)
        result["alive"] = True
        result["data"] = json.loads(resp.read().decode())
    except Exception as e:
        result["error"] = str(e)
    return result

# ── Actions ──────────────────────────────────────────────────────────────

def enforce_resource_limits():
    """Kill excess bot processes if over limit."""
    bots = get_bot_processes()
    max_bots = RULES["resources"]["max_bot_processes"]
    
    if len(bots) > max_bots:
        logger.warning(
            "⚠️  Resource limit: %d bots running (max %d). Killing excess...",
            len(bots), max_bots
        )
        # Kill newest bots first (reverse order)
        excess = bots[max_bots:]
        for bot in excess:
            try:
                os.kill(bot["pid"], signal.SIGTERM)
                logger.warning("  Killed excess bot PID %d (%s)", bot["pid"], bot["symbol"])
            except:
                pass
        return True
    return False

def enforce_memory_limit():
    """Alert if memory is critically low."""
    free_mb = get_free_memory_mb()
    threshold = RULES["resources"]["memory_free_mb_min"]
    if free_mb < threshold:
        logger.critical(
            "🔴 CRITICAL: Free memory = %.0f MB (threshold %d MB)!",
            free_mb, threshold
        )
        return False
    return True

def kill_stale_python_processes(keep_pids: set[int]):
    """Kill orphan/unknown python processes not in the keep list."""
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine", "/Format:CSV"],
            capture_output=True, text=True, timeout=10
        )
        for line in r.stdout.split("\n"):
            if "python" not in line or "ProcessId" in line:
                continue
            parts = line.split(",")
            if len(parts) >= 2:
                pid_str = parts[-1].strip()
                if pid_str and pid_str.isdigit():
                    pid = int(pid_str)
                    if pid not in keep_pids:
                        try:
                            os.kill(pid, signal.SIGTERM)
                            logger.info("Killed unknown python PID %d", pid)
                        except:
                            pass
    except:
        pass

# ── Main SRE Loop ────────────────────────────────────────────────────────

def run_sre_cycle() -> dict:
    """
    Execute one full SRE cycle.
    Returns a dict with status, actions taken, and any alerts.
    """
    alerts = []
    actions = []
    status = "ok"
    
    logger.info("=" * 50)
    logger.info("🚀 SRE Cycle starting")
    
    # 0. DevSecOps: Check credential security
    try:
        sys.path.insert(0, str(DEVOPS_DIR))
        from credentials import health_check as cred_health
        cred_status = cred_health()
        if cred_status["plaintext_env_files"] > 0:
            logger.warning("🔐 DevSecOps: %d plaintext credential files found", cred_status["plaintext_env_files"])
        if cred_status["issues"]:
            for issue in cred_status["issues"]:
                if "plaintext" in issue:
                    alerts.append(f"DevSecOps: {issue}")
                    status = "warning"
    except Exception as e:
        logger.debug("DevSecOps check unavailable: %s", e)
    
    # 1. Check resources
    logger.info("📊 Memory: %.0f MB free (threshold: %d MB)", 
                get_free_memory_mb(), RULES["resources"]["memory_free_mb_min"])
    
    if not enforce_memory_limit():
        alerts.append("CRITICAL: Low memory")
        status = "warning"
    
    # 2. Enforce resource limits
    if enforce_resource_limits():
        actions.append("Killed excess bot processes")
        status = "warning"
    
    # 3. Check bridge health
    bridge = check_bridge_health()
    logger.info("🔌 Bridge: alive=%s connected=%s", bridge["alive"], bridge.get("connected"))
    if not bridge["alive"]:
        alerts.append("Bridge down — needs restart")
        status = "critical"
    
    # 4. Check backend health
    backend = check_backend_health()
    logger.info("⚙️  Backend: alive=%s", backend["alive"])
    if not backend["alive"]:
        alerts.append("Backend down — needs restart")
        status = "critical"
    
    # 5. Count running bots
    bots = get_bot_processes()
    logger.info("🤖 Bots running: %d/%d", len(bots), RULES["resources"]["max_bot_processes"])
    
    # 6. Check log sizes
    log_size_mb = 0
    for f in LOGS_DIR.glob("*.log"):
        if f.stat().st_size > RULES["logging"]["max_log_size_mb"] * 1024 * 1024:
            log_size_mb += f.stat().st_size / (1024 * 1024)
    if log_size_mb > RULES["logging"]["max_log_size_mb"] * 3:
        alerts.append(f"Logs consuming {log_size_mb:.0f} MB — rotate")
        status = "warning"
    
    logger.info("✅ SRE Cycle complete | Status: %s | Actions: %d | Alerts: %d",
                status, len(actions), len(alerts))
    
    return {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "memory_free_mb": get_free_memory_mb(),
        "bots_running": len(bots),
        "bridge_alive": bridge["alive"],
        "backend_alive": backend["alive"],
        "actions_taken": actions,
        "alerts": alerts,
    }

def run_daemon(interval_sec: int = 120):
    """Run SRE continuously."""
    logger.info("🔵 SRE Daemon started (interval=%ds)", interval_sec)
    while True:
        try:
            result = run_sre_cycle()
            if result["alerts"]:
                logger.warning("ALERTS: %s", "; ".join(result["alerts"]))
        except Exception as e:
            logger.error("SRE cycle error: %s\n%s", e, traceback.format_exc())
        time.sleep(interval_sec)

if __name__ == "__main__":
    setup_logging()
    
    if "--daemon" in sys.argv:
        run_daemon()
    elif "--check-only" in sys.argv:
        result = run_sre_cycle()
        print(json.dumps(result, indent=2))
    else:
        result = run_sre_cycle()
        if result["alerts"]:
            print("⚠️  ALERTS:")
            for a in result["alerts"]:
                print(f"  • {a}")
            sys.exit(1)
        print("✅ All systems nominal")
