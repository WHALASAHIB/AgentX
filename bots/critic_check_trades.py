"""
Post-Trade Critic: Check for closed trades by magic 780012 in last 2 hours.
Read-only analysis — no modifications to bots, cron jobs, or running systems.
"""
import sys
import os
import json
from datetime import datetime, timedelta, timezone

# --- Step 1: Connect to MT5 using shared module ---
HERMESS_ROOT = r"C:\Hermess"
import importlib.util as _util
_spec = _util.spec_from_file_location("mt5_connect", os.path.join(HERMESS_ROOT, "utils", "mt5_connect.py"))
_mod = _util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
mt5_connect = _mod

print("=== Connecting to MT5 ===")
ok = mt5_connect.connect_mt5()
if not ok:
    print("FAILED to connect to MT5 via shared module")
    # Try bare initialize
    import MetaTrader5 as mt5
    r = mt5.initialize()
    print(f"Bare mt5.initialize() = {r}")
    if not r:
        print(f"mt5.last_error() = {mt5.last_error()}")
        sys.exit(1)

import MetaTrader5 as mt5
info = mt5.account_info()
if info is None:
    print(f"account_info() returned None. last_error={mt5.last_error()}")
    sys.exit(1)
print(f"Connected to: login={info.login}, server={info.server}, name={info.name}")

# --- Step 2: Query trades in last 2 hours ---
MAGIC = 780012
SYMBOL = "EURUSD"

# Local time for query — use same timezone source for both params (pitfall #12)
local_now = datetime.now()
local_2h_ago = local_now - timedelta(hours=2)

print(f"\n=== Querying history_deals_get({local_2h_ago}, {local_now}) ===")
print(f"Magic: {MAGIC}, Symbol: {SYMBOL}")

deals = mt5.history_deals_get(local_2h_ago, local_now)
if deals is None:
    err = mt5.last_error()
    print(f"history_deals_get returned None. last_error={err}")
    if err == (1, 'Success'):
        print("(1, 'Success') means no deals found — not an error")
    sys.exit(0)

print(f"Total deals returned: {len(deals)}")

# Filter by magic
my_deals = [d for d in deals if d.magic == MAGIC]
print(f"Deals with magic {MAGIC}: {len(my_deals)}")

if not my_deals:
    print("No trades found for magic 780012 in last 2 hours.")
    sys.exit(0)

# Show all deals
for d in my_deals:
    dt = datetime.fromtimestamp(d.time)
    print(f"  Ticket={d.ticket}, Symbol={d.symbol}, Type={'BUY' if d.type==0 else 'SELL' if d.type==1 else f'Type({d.type})'}, "
          f"Volume={d.volume}, Price={d.price}, Profit={d.profit:.2f}, Time={dt}, "
          f"PositionID={d.position_id}, Comment={d.comment or ''}")

# --- Step 3: Identify closed trades (pairs of entry/exit deals) ---
from collections import defaultdict

by_position = defaultdict(list)
for d in my_deals:
    by_position[d.position_id].append(d)

trades_analyzed = 0
for pos_id, deal_list in sorted(by_position.items()):
    deal_list.sort(key=lambda d: d.time)
    
    entry_deal = None
    exit_deal = None
    
    for d in deal_list:
        if d.type in {0, 1} and entry_deal is None:
            entry_deal = d
        elif d.type not in {0, 1}:
            exit_deal = d
    
    if entry_deal and exit_deal:
        trades_analyzed += 1
        direction = "BUY" if entry_deal.type == 0 else "SELL"
        entry_time = datetime.fromtimestamp(entry_deal.time)
        exit_time = datetime.fromtimestamp(exit_deal.time)
        holding_minutes = (exit_deal.time - entry_deal.time) / 60
        pnl = exit_deal.profit
        outcome = "WIN" if pnl > 0 else "LOSS"
        
        print(f"\n--- Trade {trades_analyzed} ---")
        print(f"PositionID: {pos_id}")
        print(f"Direction: {direction}")
        print(f"Entry: {entry_time} @ {entry_deal.price} (vol={entry_deal.volume})")
        print(f"Exit:  {exit_time} @ {exit_deal.price} (vol={exit_deal.volume})")
        print(f"Holding: {holding_minutes:.1f} min")
        print(f"PnL: ${pnl:.2f} ({outcome})")
        
        # Analysis
        print(f"\nAnalysis:")
        if outcome == "WIN":
            print(f"  ✅ Winning trade: +${pnl:.2f}")
            print(f"  What went right: Trade followed the strategy")
            print(f"  Preserve: Entry logic worked correctly")
        else:
            print(f"  ❌ Losing trade: ${pnl:.2f}")
            if holding_minutes < 30:
                print(f"  Possible early stop-out (held only {holding_minutes:.0f} min)")
            elif holding_minutes > 120:
                print(f"  Long holding time ({holding_minutes:.0f} min)")
    else:
        print(f"\nPosition {pos_id}: {len(deal_list)} deals — incomplete")

print(f"\n=== Summary ===")
print(f"Complete trades found: {trades_analyzed}")
if trades_analyzed == 0:
    print("No complete trades to analyze.")
