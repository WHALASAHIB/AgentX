"""
Post-Trade Critic — Cron check for magic 780012 closed trades.
Autonomous mode: no user present.
Checks: last 14 hours (covers Friday 13-15 UTC session) since it's now Saturday 00:26 UTC.
"""
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import json
import sys

LOCAL_NOW = datetime.now()
UTC_NOW = datetime.now(timezone.utc)
LOCAL_14H_AGO = LOCAL_NOW - timedelta(hours=14)

print(f"Local time: {LOCAL_NOW}")
print(f"UTC time:   {UTC_NOW}")
print(f"Local 14h ago: {LOCAL_14H_AGO}")

# Step 1: Try bare initialize first
init_result = mt5.initialize()
print(f"\nmt5.initialize() bare: {init_result}")

if init_result:
    info = mt5.account_info()
    if info:
        print(f"Connected to: login={info.login}, server={info.server}, name={info.name}")
        print(f"Account type: {'Hedge' if (info.account_info().trade_flags & 1) else 'Netting'}")
    else:
        print(f"account_info() returned None")
    
    # Query deals for magic 780012 in the lookback window
    print(f"\nQuerying deals from {LOCAL_14H_AGO} to {LOCAL_NOW}...")
    deals = mt5.history_deals_get(LOCAL_14H_AGO, LOCAL_NOW)
    
    if deals is None:
        err = mt5.last_error()
        print(f"history_deals_get returned None. last_error={err}")
        print("No deals found (None result).")
        mt5.shutdown()
        sys.exit(0)
    
    print(f"Total deals returned: {len(deals)}")
    
    # Filter by magic 780012
    target_deals = [d for d in deals if d.magic == 780012]
    print(f"Deals with magic 780012: {len(target_deals)}")
    
    for d in target_deals:
        dt = datetime.fromtimestamp(d.time)
        dt_utc = datetime.fromtimestamp(d.time, tz=timezone.utc)
        print(f"\n  --- Deal {d.ticket} ---")
        print(f"  Symbol:    {d.symbol}")
        print(f"  Type:      {'BUY' if d.type == 0 else 'SELL' if d.type == 1 else d.type}")
        print(f"  Magic:     {d.magic}")
        print(f"  Volume:    {d.volume}")
        print(f"  Price:     {d.price}")
        print(f"  Profit:    {d.profit}")
        print(f"  Commission:{d.commission}")
        print(f"  Swap:      {d.swap}")
        print(f"  Time(local): {dt}")
        print(f"  Time(UTC):   {dt_utc}")
        print(f"  Comment:   {d.comment}")
        print(f"  Position ID: {d.position_id}")
    
    # Also report non-780012 deals for reference
    other_deals = [d for d in deals if d.magic != 780012]
    if other_deals:
        magics_found = set(d.magic for d in other_deals)
        print(f"\nOther magics found in window: {magics_found}")
    
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"mt5.initialize() failed. last_error={err}")
    
    # Try path-based as fallback
    print(f"\nTrying path-based initialize...")
    init2 = mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    print(f"mt5.initialize(path=...): {init2}")
    
    if init2:
        info = mt5.account_info()
        if info:
            print(f"Connected to: login={info.login}, server={info.server}")
        mt5.shutdown()
    else:
        print(f"Path-based also failed.")
