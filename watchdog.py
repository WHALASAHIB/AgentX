#!/usr/bin/env python3
"""
AGENTX Watchdog — lightweight port-based health check.
Checks backend (8000) and bridge (5000) every 60 seconds.
Restarts any that are down. Silent when healthy.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

TRADING_DIR = Path("C:/Trading")
LOGS_DIR = TRADING_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

BACKEND_PORT = 8000
BRIDGE_PORT = 5000


def port_listening(port: int) -> bool:
    """Check if a TCP port is in LISTENING state."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("127.0.0.1", port))
        s.close()
        return result == 0
    except Exception:
        return False


def find_pid_on_port(port: int):
    """Find PID listening on a given port."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    return parts[-1]
    except Exception:
        pass
    return None


def kill_port(port: int):
    """Kill process holding a port."""
    pid = find_pid_on_port(port)
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
        time.sleep(2)


def start_service(name: str, module: str, port: int, args: str = ""):
    """Start a Python service module."""
    logfile = LOGS_DIR / f"{name}.log"
    cmd = f'start /B "" python -m {module} {args}'
    # Use subprocess with shell=True to run the Windows start command
    subprocess.run(
        f'cd /d "{TRADING_DIR}" && {cmd} > "{logfile}" 2>&1',
        shell=True, timeout=10
    )
    # Wait for port to be ready
    for _ in range(15):
        time.sleep(1)
        if port_listening(port):
            return True
    return False


def check_and_restart():
    """Check both services and restart if needed."""
    actions = []

    # Check bridge
    if not port_listening(BRIDGE_PORT):
        print(f"[{time.strftime('%H:%M:%S')}] Bridge DOWN on port {BRIDGE_PORT}")
        kill_port(BRIDGE_PORT)
        if start_service("bridge", "bridge", BRIDGE_PORT):
            actions.append("bridge restarted")
        else:
            actions.append("bridge FAILED to start")
    else:
        actions.append("bridge ok")

    # Check backend
    if not port_listening(BACKEND_PORT):
        print(f"[{time.strftime('%H:%M:%S')}] Backend DOWN on port {BACKEND_PORT}")
        kill_port(BACKEND_PORT)
        if start_service("backend", "backend", BACKEND_PORT, "--host 0.0.0.0"):
            actions.append("backend restarted")
        else:
            actions.append("backend FAILED to start")
    else:
        actions.append("backend ok")

    status = " | ".join(actions)
    if "restarted" in status or "FAILED" in status:
        print(f"[{time.strftime('%H:%M:%S')}] {status}")
        return status
    return None  # Silent when healthy


if __name__ == "__main__":
    # First run: check once and exit (for cron job usage)
    result = check_and_restart()
    if result:
        print(result)
    else:
        # Silent exit — nothing to report
        pass
