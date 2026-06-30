"""Kill MT5 terminal and restart it with correct credentials."""
import subprocess
import time
import sys
import os

# Kill terminal via direct Windows API call
import ctypes
kernel32 = ctypes.windll.kernel32

# First find and kill terminal64.exe processes
result = subprocess.run(
    ["taskkill", "/F", "/IM", "terminal64.exe"],
    capture_output=True, text=True, timeout=10
)
print(f"Kill result: {result.returncode} - {result.stdout.strip() or result.stderr.strip()}")

# Wait a tiny bit for the kill to propagate
time.sleep(0.5)

# Now immediately try init
import MetaTrader5 as mt5

# Shutdown any existing API state
try:
    mt5.shutdown()
except:
    pass
time.sleep(0.3)

print("Initializing MT5...")
sys.stdout.flush()

# Try with full credentials - this should spawn a NEW terminal window
ok = mt5.initialize(
    path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
    login=5051185832,
    password="X$W5359Ni5qL",
    server="MetaQuotes-Demo"
)
print(f"init: {ok}")
if ok:
    info = mt5.account_info()
    if info is not None:
        print(f"SUCCESS: login={info.login} server={info.server} balance={info.balance}")
    else:
        print("No account info returned")
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"error: {err}")
    
    # If that failed, wait for auto-restart and try plain init
    if err:
        print("Waiting 15s for terminal auto-restart...")
        time.sleep(15)
        mt5.shutdown()
        time.sleep(0.5)
        ok2 = mt5.initialize()
        print(f"plain init: {ok2}")
        if ok2:
            info = mt5.account_info()
            if info:
                print(f"on account: {info.login} {info.server} {info.balance}")
            else:
                print("No account info on plain init")
            # Login with our creds
            ok3 = mt5.login(5051185832, "X$W5359Ni5qL", "MetaQuotes-Demo")
            print(f"login: {ok3}")
            if ok3:
                info2 = mt5.account_info()
                if info2:
                    print(f"SUCCESS: {info2.login} {info2.server} {info2.balance}")
            else:
                print(f"login error: {mt5.last_error()}")
            mt5.shutdown()
        else:
            print(f"plain init error: {mt5.last_error()}")
