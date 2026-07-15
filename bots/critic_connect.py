"""
Critic: Try all connection strategies for MT5.
Run with timeout at shell level.
"""
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import sys, os

LOCAL = datetime.now()
print(f"Local: {LOCAL}")
utc = datetime.now(timezone.utc)
print(f"UTC:   {utc}")

# Strategy 1: Bare init
print("\n=== Strategy 1: bare init ===")
r1 = mt5.initialize()
print(f"Result: {r1}")
if r1:
    a = mt5.account_info()
    print(f"Account: login={a.login}, server={a.server}" if a else "account_info()=None")
else:
    print(f"Error: {mt5.last_error()}")

if not r1:
    # Strategy 2: Bare init AGAIN (intermittent)
    print("\n=== Strategy 2: bare init (redo) ===")
    r2 = mt5.initialize()
    print(f"Result: {r2}")
    if r2:
        a = mt5.account_info()
        print(f"Account: login={a.login}, server={a.server}" if a else "account_info()=None")
    else:
        print(f"Error: {mt5.last_error()}")

if not r1 and not mt5.account_info():
    # Try with path
    print("\n=== Strategy 3: path-based init ===")
    r3 = mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    print(f"Result: {r3}")
    if r3:
        a = mt5.account_info()
        print(f"Account: login={a.login}, server={a.server}" if a else "account_info()=None")
    else:
        print(f"Error: {mt5.last_error()}")

# Check terminal
if mt5.account_info():
    info = mt5.account_info()
    print(f"\nActive account: {info.login} / {info.server}")
    print(f"Balance: {info.balance}")
    
    # Query history for last 14 hours
    local_14h = LOCAL - timedelta(hours=14)
    print(f"\nQuerying deals from {local_14h} to {LOCAL}")
    deals = mt5.history_deals_get(local_14h, LOCAL)
    
    if deals is None:
        err = mt5.last_error()
        print(f"history_deals_get returned None: {err}")
    else:
        print(f"Total deals: {len(deals)}")
        magic_targets = [d for d in deals if d.magic == 780012]
        print(f"Magic 780012 deals: {len(magic_targets)}")
        
        if magic_targets:
            for d in magic_targets:
                dt = datetime.fromtimestamp(d.time)
                print(f"  Ticket={d.ticket} Sym={d.symbol} Type={'BUY' if d.type==0 else 'SELL'} Price={d.price} Profit={d.profit} Time={dt} Comment={d.comment}")
        
        # Also check other magics
        for d in deals:
            if d.magic != 780012 and d.magic != 0:
                print(f"  Other magic: {d.magic} sym={d.symbol} profit={d.profit} time={datetime.fromtimestamp(d.time)}")

mt5.shutdown()
print("\nDone.")
