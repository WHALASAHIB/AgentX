#!/usr/bin/env python3
"""Post-Trade Critic: check MT5, fetch trades for magic 780012 in last 2h."""
import sys
import os
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 not installed")
    sys.exit(1)

# Step 1: Check if terminal is running (pre-check)
print("=== PRE-CHECK ===")
print(f"Time: {datetime.now().isoformat()}")

# Step 2: Try to initialize
print("\n=== MT5 INIT ===")
init_result = mt5.initialize()
print(f"mt5.initialize() = {init_result}")

if not init_result:
    error = mt5.last_error()
    print(f"last_error(): {error}")
    
    # Try path-based init
    print("\nTrying path-based init...")
    path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    init_result2 = mt5.initialize(path=path)
    print(f"mt5.initialize(path=...) = {init_result2}")
    if not init_result2:
        error2 = mt5.last_error()
        print(f"last_error(): {error2}")
        mt5.shutdown()
        print("\nRESULT: MT5 UNREACHABLE")
        sys.exit(2)
    else:
        print("Path-based init succeeded")

# Check account info
account = mt5.account_info()
if account:
    print(f"\n=== ACCOUNT INFO ===")
    print(f"Login: {account.login}")
    print(f"Server: {account.server}")
    print(f"Name: {account.name}")
    print(f"Balance: {account.balance}")
    print(f"Equity: {account.equity}")
else:
    print(f"\naccount_info() failed: {mt5.last_error()}")

# Step 3: Fetch trades from last 2 hours
print("\n=== FETCHING TRADES ===")
now = datetime.now()
from_time = now - timedelta(hours=2)
print(f"From: {from_time}")
print(f"To: {now}")
print(f"Magic: 780012")
print(f"Symbol: EURUSD")

# Get history deals
deals = mt5.history_deals_get(from_time, now)
print(f"\nhistory_deals_get() returned: {deals}")

if deals is None:
    error = mt5.last_error()
    print(f"last_error(): {error}")
    if error == (1, "Success"):
        print("No deals found (None + Success = genuine empty range)")
    else:
        print(f"Error fetching deals: {error}")
elif len(deals) == 0:
    print("No deals found (empty list)")
else:
    print(f"Total deals: {len(deals)}")
    
    # Filter by magic and symbol
    relevant = [d for d in deals if d.magic == 780012]
    print(f"Deals with magic 780012: {len(relevant)}")
    
    eurusd_deals = [d for d in deals if d.magic == 780012 and d.symbol == "EURUSD"]
    print(f"EURUSD + magic 780012: {len(eurusd_deals)}")
    
    for d in deals:
        print(f"  Deal: ticket={d.ticket}, order={d.order}, time={datetime.fromtimestamp(d.time)}, "
              f"type={'BUY' if d.type==0 else 'SELL' if d.type==1 else 'BUY_LIMIT' if d.type==4 else 'SELL_LIMIT' if d.type==5 else d.type}, "
              f"magic={d.magic}, symbol={d.symbol}, volume={d.volume}, price={d.price}, "
              f"profit={d.profit}, commission={d.commission}, swap={d.swap}, comment={d.comment}")

# Also get positions
print("\n=== OPEN POSITIONS ===")
positions = mt5.positions_get(symbol="EURUSD")
if positions:
    for p in positions:
        print(f"  Position: ticket={p.ticket}, magic={p.magic}, volume={p.volume}, "
              f"price_open={p.price_open}, sl={p.sl}, tp={p.tp}, profit={p.profit}")
else:
    print("No open EURUSD positions")

# Get orders for context
print("\n=== HISTORY ORDERS ===")
orders = mt5.history_orders_get(from_time, now, group="*EURUSD*")
if orders is None:
    error = mt5.last_error()
    print(f"last_error(): {error}")
elif len(orders) == 0:
    print("No history orders found")
else:
    print(f"Total orders: {len(orders)}")
    for o in orders:
        if o.magic == 780012:
            print(f"  Order: ticket={o.ticket}, type={'BUY' if o.type==0 else 'SELL' if o.type==1 else 'BUY_LIMIT' if o.type==2 else 'SELL_LIMIT' if o.type==3 else o.type}, "
                  f"state={'STARTED' if o.state==0 else 'PLACED' if o.state==1 else 'CANCELED' if o.state==2 else 'PARTIAL' if o.state==3 else 'FILLED' if o.state==4 else o.state}, "
                  f"price={o.price_open}, sl={o.sl}, tp={o.tp}, volume={o.volume_current}, symbol={o.symbol}, magic={o.magic}")

mt5.shutdown()
print("\n=== DONE ===")
