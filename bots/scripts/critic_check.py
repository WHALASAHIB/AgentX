#!/usr/bin/env python3
"""Post-Trade Critic — check for closed trades by magic 780012 in last 2 hours."""
import sys, os, json
from datetime import datetime, timedelta, timezone

# Use shared mt5_connect module
_HERMESS_ROOT = r"C:\Hermess"
import importlib.util as _util
_spec = _util.spec_from_file_location("mt5_connect", os.path.join(_HERMESS_ROOT, "utils", "mt5_connect.py"))
_mod = _util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
mt5_connect = _mod

# Connect to MT5
ok = mt5_connect.connect_mt5()
if not ok:
    print("MT5_CONNECT_FAILED", flush=True)
    sys.exit(0)

import MetaTrader5 as mt5

# Verify account info
info = mt5.account_info()
if info is None:
    print("ACCOUNT_INFO_FAILED", flush=True)
    mt5.shutdown()
    sys.exit(0)

# Check time
utc_now = datetime.now(timezone.utc)
local_now = datetime.now()
print(f"UTC: {utc_now.isoformat()}", flush=True)
print(f"Local: {local_now.isoformat()}", flush=True)
print(f"Account: login={info.login} server={info.server} balance={info.balance}", flush=True)

# Query last 2 hours using local time (MT5 API requirement - timezone-naive)
from_time = local_now - timedelta(hours=2)
to_time = local_now
print(f"Query window: {from_time.isoformat()} -> {to_time.isoformat()}", flush=True)

# Magic
TARGET_MAGIC = 780012
TARGET_SYMBOL = "EURUSD"

deals = mt5.history_deals_get(from_time, to_time)
if deals is None:
    err = mt5.last_error()
    print(f"DEALS_NONE: last_error={err}", flush=True)
    mt5.shutdown()
    sys.exit(0)

print(f"Total deals in window: {len(deals)}", flush=True)

# Filter by magic and symbol
my_deals = [d for d in deals if d.magic == TARGET_MAGIC and d.symbol == TARGET_SYMBOL]
print(f"Deals for magic {TARGET_MAGIC} / {TARGET_SYMBOL}: {len(my_deals)}", flush=True)

if not my_deals:
    print("NO_TRADES", flush=True)
    mt5.shutdown()
    sys.exit(0)

# Group by position_id
from collections import defaultdict
pos_deals = defaultdict(list)
for d in my_deals:
    pos_deals[d.position_id].append(d)

print(f"Unique positions: {len(pos_deals)}", flush=True)

# Analyze each position
for pos_id, dlist in sorted(pos_deals.items()):
    entry_deals = [d for d in dlist if d.entry == 0]  # DEAL_ENTRY_IN
    close_deals = [d for d in dlist if d.entry == 1]  # DEAL_ENTRY_OUT
    
    print(f"\n--- Position {pos_id} ---", flush=True)
    print(f"  Entry deals: {len(entry_deals)}", flush=True)
    print(f"  Close deals: {len(close_deals)}", flush=True)
    
    for d in dlist:
        dt = datetime.fromtimestamp(d.time)
        print(f"  Deal {d.ticket}: type={'BUY' if d.type==0 else 'SELL'} entry={d.entry} "
              f"price={d.price:.5f} profit={d.profit:.2f} volume={d.volume} "
              f"time={dt.isoformat()} comment={d.comment}", flush=True)
    
    # Determine direction
    if entry_deals:
        direction = "BUY" if entry_deals[0].type == 0 else "SELL"
        entry_price = entry_deals[0].price
    elif close_deals:
        # Close-only deal — type is opposite of direction
        direction = "SELL" if close_deals[0].type == 0 else "BUY"
        entry_price = None
    else:
        direction = "UNKNOWN"
        entry_price = None
    
    # Calculate PnL
    total_pnl = sum(d.profit for d in dlist)
    exit_price = close_deals[0].price if close_deals else None
    exit_reason = "close"
    if close_deals and close_deals[0].comment:
        comment = close_deals[0].comment
        if "[sl" in comment.lower():
            exit_reason = "SL"
        elif "[tp" in comment.lower():
            exit_reason = "TP"
    
    print(f"  Direction: {direction}", flush=True)
    print(f"  Entry price: {entry_price}", flush=True)
    print(f"  Exit price: {exit_price}", flush=True)
    print(f"  Total PnL: {total_pnl:.2f}", flush=True)
    print(f"  Exit reason: {exit_reason}", flush=True)
    
    outcome = "win" if total_pnl > 0 else "loss"
    print(f"  Outcome: {outcome}", flush=True)

    # Detailed analysis for JSON
    trade_data = {
        "position_id": pos_id,
        "symbol": TARGET_SYMBOL,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl": round(total_pnl, 2),
        "volume": dlist[0].volume,
        "outcome": outcome,
        "exit_reason": exit_reason,
        "deals": [
            {
                "ticket": d.ticket,
                "type": "BUY" if d.type == 0 else "SELL",
                "entry": d.entry,
                "price": d.price,
                "profit": round(d.profit, 2),
                "time": datetime.fromtimestamp(d.time).isoformat(),
                "comment": d.comment
            }
            for d in dlist
        ]
    }
    print(f"  TRADE_JSON: {json.dumps(trade_data)}", flush=True)

mt5.shutdown()
