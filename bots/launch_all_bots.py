#!/usr/bin/env python3
"""Launch all active bot processes as independent subprocesses."""
import subprocess
import sys
import os
import time

BOTS_DIR = os.path.dirname(os.path.abspath(__file__))

BOTS = [
    # Bollinger
    ("AUDUSD", "bollinger", os.path.join(BOTS_DIR, "active_bots", "AUDUSD", "run_bollinger.py")),
    ("NZDUSD", "bollinger", os.path.join(BOTS_DIR, "active_bots", "NZDUSD", "run_bollinger.py")),
    ("USDCHF", "bollinger", os.path.join(BOTS_DIR, "active_bots", "USDCHF", "run_bollinger.py")),
    # MACD
    ("AUDUSD", "macd", os.path.join(BOTS_DIR, "active_bots", "AUDUSD", "run_macd.py")),
    ("BTCUSD", "macd", os.path.join(BOTS_DIR, "active_bots", "BTCUSD", "run_macd.py")),
    ("GBPUSD", "macd", os.path.join(BOTS_DIR, "active_bots", "GBPUSD", "run_macd.py")),
    ("NZDUSD", "macd", os.path.join(BOTS_DIR, "active_bots", "NZDUSD", "run_macd.py")),
    ("USDCAD", "macd", os.path.join(BOTS_DIR, "active_bots", "USDCAD", "run_macd.py")),
    ("USDCHF", "macd", os.path.join(BOTS_DIR, "active_bots", "USDCHF", "run_macd.py")),
    ("USDJPY", "macd", os.path.join(BOTS_DIR, "active_bots", "USDJPY", "run_macd.py")),
    ("XAUUSD", "macd", os.path.join(BOTS_DIR, "active_bots", "XAUUSD", "run_macd.py")),
    # SMA
    ("BTCUSD", "sma", os.path.join(BOTS_DIR, "active_bots", "BTCUSD", "run_sma.py")),
    ("USDJPY", "sma", os.path.join(BOTS_DIR, "active_bots", "USDJPY", "run_sma.py")),
    # Propfirm
    ("EURUSD", "propfirm_pass", os.path.join(BOTS_DIR, "active_bots", "EURUSD", "run_propfirm_pass.py")),
    # Volatility Breakout (different script)
    ("XAUUSD", "volatilitybreakout", os.path.join(BOTS_DIR, "volatility_breakout_bot.py")),
]

processes = []
for symbol, strategy, script in BOTS:
    logfile = os.path.join(BOTS_DIR, "logs", f"{symbol}_{strategy}.log")
    env = os.environ.copy()
    # Add Hermess repo paths for shared modules
    hermess_dir = os.path.abspath(os.path.join(BOTS_DIR, "..", "..", "Hermess"))
    hermes_bots = os.path.join(hermess_dir, "bots")
    existing = env.get("PYTHONPATH", "")
    paths = [p for p in [hermess_dir, hermes_bots] if os.path.isdir(p)]
    if paths:
        env["PYTHONPATH"] = ";".join(paths + ([existing] if existing else []))
    try:
        p = subprocess.Popen(
            [sys.executable, script],
            stdout=open(logfile, "a"),
            stderr=subprocess.STDOUT,
            cwd=BOTS_DIR,
            env=env,
        )
        processes.append((symbol, strategy, p.pid))
        print(f"  [{symbol}] {strategy:20s} → PID {p.pid}")
    except Exception as e:
        print(f"  [{symbol}] {strategy:20s} → FAILED: {e}")

print(f"\n{len(processes)} bots launched. Use tasklist to monitor.")
print("To stop all: taskkill /F /PID ... (each PID listed above)")
