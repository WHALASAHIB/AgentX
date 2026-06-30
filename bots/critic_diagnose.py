"""
MT5 Connectivity Diagnostic
Timestamp: 2026-06-30 ~09:27 UTC
Bot: Propfirm Pass v8 (magic 780012, EURUSD)
Trading window: 13:00-15:00 UTC
"""
import subprocess
import sys
import os
from datetime import datetime, timezone

print("=" * 60)
print("MT5 CONNECTIVITY DIAGNOSTIC")
print(f"Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Time (local): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# Step 1: Check terminal processes
print("\n[1/5] Checking MT5 terminal processes...")
result = subprocess.run(
    'tasklist | findstr /i terminal64',
    shell=True, capture_output=True, text=True, timeout=10
)
print(f"  PIDs:\n{result.stdout}")
print(f"  Error: {result.stderr.strip() if result.stderr else 'None'}")

# Step 2: Try bare initialize with short timeout via threading
print("\n[2/5] Testing mt5.initialize() bare...")
import MetaTrader5 as mt5
import threading
import time

init_result = [None]
init_error = [None]

def try_init_bare():
    try:
        ok = mt5.initialize()
        init_result[0] = ok
        if not ok:
            init_error[0] = mt5.last_error()
    except Exception as e:
        init_error[0] = str(e)

t = threading.Thread(target=try_init_bare, daemon=True)
t.start()
t.join(timeout=15)

if t.is_alive():
    print(f"  HUNG — no response in 15s (IPC failure)")
    # Try to force shutdown and re-init
    mt5.shutdown()
    init_result[0] = None
else:
    print(f"  Result: {init_result[0]}")
    if init_error[0]:
        print(f"  Error: {init_error[0]}")

# Step 3: Try path-based initialize
print(f"\n[3/5] Testing mt5.initialize(path=...) -- 15s timeout...")
term_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"

init_result2 = [None]
init_error2 = [None]

def try_init_path():
    try:
        ok = mt5.initialize(path=term_path)
        init_result2[0] = ok
        if not ok:
            init_error2[0] = mt5.last_error()
    except Exception as e:
        init_error2[0] = str(e)

t2 = threading.Thread(target=try_init_path, daemon=True)
t2.start()
t2.join(timeout=15)

if t2.is_alive():
    print(f"  HUNG — no response in 15s (IPC failure persists)")
    init_result2[0] = None
else:
    print(f"  Result: {init_result2[0]}")
    if init_error2[0]:
        err = init_error2[0]
        if isinstance(err, tuple):
            print(f"  Error: code={err[0]}, msg={err[1]}")
        else:
            print(f"  Error: {err}")
    
    if init_result2[0]:
        acc = mt5.account_info()
        if acc:
            print(f"\n  Active account: login={acc.login}, server={acc.server}")
            print(f"  Balance: {acc.balance}, Equity: {acc.equity}")
            print(f"  Margin: {acc.margin}, Free margin: {acc.margin_free}")
            print(f"  Drawdown: {acc.drawdown}")
        mt5.shutdown()

# Step 4: Try the two-step approach (initialize bare + login)
print(f"\n[4/5] Testing two-step approach (mt5.initialize() + mt5.login())...")
# Read config
config_path = r"C:\Trading\mt5_config.json"
import json
with open(config_path) as f:
    config = json.load(f)

print(f"  Config: login={config['login']}, server={config['server']}")

init_result3 = [None]
init_error3 = [None]

def try_init_bare2():
    try:
        ok = mt5.initialize()
        init_result3[0] = ok
        if not ok:
            init_error3[0] = mt5.last_error()
    except Exception as e:
        init_error3[0] = str(e)

t3 = threading.Thread(target=try_init_bare2, daemon=True)
t3.start()
t3.join(timeout=15)

if t3.is_alive():
    print(f"  Bare init: HUNG")
else:
    if init_result3[0]:
        print(f"  Bare init: OK")
        print(f"  Active account before login: login={mt5.account_info().login}, server={mt5.account_info().server}")
        
        login_result = [None]
        login_error = [None]
        def try_login():
            try:
                ok = mt5.login(login=config['login'], password=config['password'], server=config['server'])
                login_result[0] = ok
                if not ok:
                    login_error[0] = mt5.last_error()
            except Exception as e:
                login_error[0] = str(e)
        
        t4 = threading.Thread(target=try_login, daemon=True)
        t4.start()
        t4.join(timeout=15)
        
        if t4.is_alive():
            print(f"  mt5.login(): HUNG (account mismatch suspect)")
        else:
            print(f"  mt5.login(): {login_result[0]}")
            if login_error[0]:
                print(f"  Login error: {login_error[0]}")
            if login_result[0]:
                acc = mt5.account_info()
                print(f"  After login: login={acc.login}, server={acc.server}")
    else:
        print(f"  Bare init: FAILED — {init_error3[0]}")

mt5.shutdown()

# Step 5: Check stale PID locks
print(f"\n[5/5] Checking stale PID locks...")
lock_dir = r"C:\Hermess\bots\locks"
if os.path.isdir(lock_dir):
    for fname in os.listdir(lock_dir):
        fpath = os.path.join(lock_dir, fname)
        with open(fpath) as f:
            content = f.read().strip()
        print(f"  {fname}: PID={content}")
        try:
            pid = int(content)
            # Check if process exists
            check = subprocess.run(
                f'tasklist /FI "PID eq {pid}" /NH',
                shell=True, capture_output=True, text=True, timeout=5
            )
            if "No tasks" in check.stdout:
                print(f"    -> STALE (process {pid} not running)")
            else:
                print(f"    -> Process {pid} appears running")
        except:
            print(f"    -> Invalid PID in file")
else:
    print(f"  Lock dir {lock_dir} not found")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
