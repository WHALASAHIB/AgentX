#!/usr/bin/env python3
"""
AGENTX — Master Bot Launcher
============================
Launches ALL active bots in background processes.
Each bot runs as an independent process with its own MT5 connection.
Strategies: macd, goldphoenix, bollinger, sma

Usage:
    python start_all_bots.py          # Launch all bots
    python start_all_bots.py --kill   # Kill all running bots first
"""
import os
import signal
import subprocess
import sys
import time

BOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots")
ACTIVE_BOTS_DIR = os.path.join(BOTS_DIR, "active_bots")
LOGS_DIR = os.path.join(BOTS_DIR, "logs")

# All active bot configurations (symbol → strategy file)
# Read from active_bots directory
ACTIVE_BOTS = []

for symbol_dir in sorted(os.listdir(ACTIVE_BOTS_DIR)):
    symbol_path = os.path.join(ACTIVE_BOTS_DIR, symbol_dir)
    if not os.path.isdir(symbol_path):
        continue
    for run_file in sorted(os.listdir(symbol_path)):
        if run_file.startswith("run_") and run_file.endswith(".py"):
            strategy = run_file[4:-3]  # "macd" from "run_macd.py"
            script_path = os.path.join(symbol_path, run_file)
            if os.path.isfile(script_path):
                ACTIVE_BOTS.append((symbol_dir, strategy, script_path))

def kill_all():
    """Kill any existing bot processes."""
    killed = 0
    for symbol, strategy, script in ACTIVE_BOTS:
        # Find processes by symbol pattern
        try:
            result = subprocess.run(
                ['powershell', '-Command', 
                 f'Get-Process python | Where-Object {{$_.CommandLine -match "{symbol}"}} | Select-Object Id'],
                capture_output=True, text=True, timeout=10
            )
        except:
            pass
    
    # Also kill via grep on linux side
    try:
        result = subprocess.run(
            ['ps', 'aux'], capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.split('\n')
        for line in lines:
            if 'multi_symbol_bot.py' in line or 'gold_phoenix_bot' in line:
                parts = line.split()
                if len(parts) > 1:
                    pid = parts[1]
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        killed += 1
                    except:
                        pass
    except:
        pass
    
    print(f"🛑 Killed {killed} bot processes")

def launch_all():
    """Launch all active bots as background processes with staggered timing.
    Staggering prevents MT5 IPC congestion from 19 simultaneous connections."""
    launched = 0
    failed = 0
    
    os.makedirs(LOGS_DIR, exist_ok=True)
    print("⏱️  Staggering launches (3s apart) to prevent MT5 IPC congestion...")
    
    for i, (symbol, strategy, script_path) in enumerate(ACTIVE_BOTS):
        log_file = os.path.join(LOGS_DIR, f"launch_{symbol}_{strategy}.log")
        python = sys.executable
        
        try:
            with open(log_file, 'w') as lf:
                process = subprocess.Popen(
                    [python, script_path],
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATENEWPROCESSGROUP') else 0,
                    start_new_session=True,
                )
            print(f"🚀 {i+1:2d}/{len(ACTIVE_BOTS)} {symbol:8s} ({strategy:12s}) → PID {process.pid}")
            launched += 1
        except Exception as e:
            print(f"❌ {symbol:8s} ({strategy:12s}) → FAILED: {e}")
            failed += 1
        
        # Stagger: 3s delay between launches, except for the last one
        if i < len(ACTIVE_BOTS) - 1:
            time.sleep(3)
    
    print(f"\n{'='*50}")
    print(f"✅ Launched {launched} bots | ❌ Failed {failed}")
    print(f"📊 Bots: log files at {LOGS_DIR}")
    print(f"{'='*50}")
    
    return launched, failed

def show_status():
    """Show which bots are currently running."""
    try:
        result = subprocess.run(
            ['ps', 'aux'], capture_output=True, text=True, timeout=10
        )
        print("=== CURRENT BOT PROCESSES ===")
        found = False
        for line in result.stdout.split('\n'):
            if 'multi_symbol_bot.py' in line or 'gold_phoenix_bot' in line:
                print(f"  {line}")
                found = True
        if not found:
            print("  No bot processes found")
        
        print(f"\n=== ACTIVE BOT CONFIG ===")
        for symbol, strategy, _ in ACTIVE_BOTS:
            print(f"  {symbol:8s} → {strategy}")
    except Exception as e:
        print(f"Status check failed: {e}")

if __name__ == "__main__":
    if "--kill" in sys.argv:
        kill_all()
        time.sleep(1)
    
    if "--status" in sys.argv:
        show_status()
    elif "--kill" in sys.argv:
        pass
    else:
        kill_all()
        time.sleep(2)
        print("="*50)
        print("AGENTX — Bot Launch Sequence")
        print(f"Starting {len(ACTIVE_BOTS)} bot(s)")
        print("="*50)
        launch_all()
