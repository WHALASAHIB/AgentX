"""
Post-Trade Critic Agent — Cron Run
Checks MT5 for closed trades by magic 780012 in the last 2 hours.
Read-only analysis only.
"""
import importlib.util as _util
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_HERMESS_ROOT = r"C:\Hermess"
_TRADING_ROOT = r"C:\Trading"
_MAGIC = 780012
_SYMBOL = "EURUSD"
_LOOKBACK_HOURS = 2

# --- Load shared mt5_connect ---
_spec = _util.spec_from_file_location(
    "mt5_connect",
    os.path.join(_HERMESS_ROOT, "utils", "mt5_connect.py")
)
_mod = _util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
mt5 = _mod.mt5  # grab the imported mt5 module reference

# Load config
config_path = os.path.join(_HERMESS_ROOT, "mt5_config.json")
with open(config_path) as f:
    cfg = json.load(f)
expected_login = int(cfg["login"])
expected_server = cfg["server"]

# --- Step 0: Check UTC time ---
utc_now = datetime.now(timezone.utc)
local_now = datetime.now()
utc_hour = utc_now.hour

# Bot session window: 13-15 UTC
SESSION_WINDOW = "13:00-15:00 UTC"

# Decision matrix for output
window_active = 13 <= utc_hour < 15
window_passed = utc_hour >= 15
window_ahead = utc_hour < 13

print(f"=== Post-Trade Critic Agent ===")
print(f"UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Local time: {local_now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Bot session window: {SESSION_WINDOW}")
print(f"Window status: {'ACTIVE' if window_active else 'PASSED' if window_passed else 'AHEAD'}")
print(f"Looking back {_LOOKBACK_HOURS}h for magic={_MAGIC} {_SYMBOL}")
print()

# --- Step 1: Try gentle connect (no kill) ---
mt5.shutdown()
time.sleep(0.5)
connected = mt5.initialize(timeout=10000)
if not connected:
    error = mt5.last_error()
    print(f"❌ mt5.initialize() failed: {error}")
    print(f"Terminal may not be running or IPC issue.")
    sys.exit(0)  # Don't return EMERGENCY, just report

acct = mt5.account_info()
if not acct:
    print(f"❌ No account_info after connect")
    mt5.shutdown()
    sys.exit(0)

actual_login = int(acct.login)
actual_server = acct.server
print(f"Connected: login={actual_login} server={actual_server} balance={acct.balance:.2f}")

if actual_login != expected_login or actual_server != expected_server:
    print(f"⚠️ WRONG ACCOUNT: connected to {actual_login}/{actual_server}, expected {expected_login}/{expected_server}")
    print("Querying trades anyway — may return valid trades from wrong account.")
else:
    print(f"✅ Correct account")

# --- Step 2: Query history deals in last 2 hours ---
# Use local naive datetimes for MT5 API (pitfall #3)
from_time = local_now - timedelta(hours=_LOOKBACK_HOURS)
to_time = local_now
print(f"Query window: {from_time} → {to_time}")

deals = mt5.history_deals_get(from_time, to_time)
if deals is None:
    err = mt5.last_error()
    print(f"history_deals_get returned None. last_error: {err}")
    print("Likely no deals in range (not an error).")
    mt5.shutdown()
    print("\n[SILENT]")
    sys.exit(0)

print(f"Total deals in window: {len(deals)}")

# --- Step 3: Filter by magic ---
my_deals = [d for d in deals if d.magic == _MAGIC and d.symbol == _SYMBOL]
print(f"Deals matching magic {_MAGIC} {_SYMBOL}: {len(my_deals)}")

if not my_deals:
    print("No matching trades found.")
    mt5.shutdown()
    print("\n[SILENT]")
    sys.exit(0)

# --- Step 4: Group by position_id and find closed trades ---
pos_deals = defaultdict(list)
for d in my_deals:
    pos_deals[d.position_id].append(d)

print(f"Unique position IDs: {len(pos_deals)}")

# --- Step 5: Analyze each position ---
def get_trade_direction(deals_for_pos):
    """Determine trade direction from deals for a position.
    Handles the deal-type inversion for close-only deals (pitfall #15)."""
    entry_deals = [d for d in deals_for_pos if d.entry == 0]  # DEAL_ENTRY_IN
    close_deals = [d for d in deals_for_pos if d.entry == 1]  # DEAL_ENTRY_OUT
    if entry_deals:
        return "BUY" if entry_deals[0].type == 0 else "SELL"
    elif close_deals:
        # Close-only deal — type is opposite of direction
        return "SELL" if close_deals[0].type == 0 else "BUY"
    return "UNKNOWN"

def get_exit_reason(d):
    """Parse SL/TP from deal comment field."""
    comment = d.comment or ""
    if "[sl" in comment.lower():
        return "SL"
    elif "[tp" in comment.lower():
        return "TP"
    return "close"

trades_found = []
for pos_id, dlist in sorted(pos_deals.items()):
    pnl = sum(d.profit for d in dlist)
    # Skip zero-PnL positions (opening deals still open)
    if abs(pnl) < 0.001:
        continue
    
    # Find direction
    direction = get_trade_direction(dlist)
    
    # Find entry and exit prices
    entry_deals = [d for d in dlist if d.entry == 0]
    close_deals = [d for d in dlist if d.entry == 1]
    
    entry_price = entry_deals[0].price if entry_deals else None
    entry_time = datetime.fromtimestamp(entry_deals[0].time) if entry_deals else None
    exit_price = close_deals[0].price if close_deals else None
    exit_time = datetime.fromtimestamp(close_deals[0].time) if close_deals else None
    
    # If only close deals, entry info from close deal type
    if not entry_price and close_deals:
        entry_price = close_deals[0].price  # use close price as approximate
    
    # Exit reason
    exit_reason = get_exit_reason(close_deals[0]) if close_deals else "unknown"
    
    # Holding time
    holding_minutes = None
    if entry_time and exit_time:
        holding_minutes = (exit_time - entry_time).total_seconds() / 60
    
    volume = dlist[0].volume if dlist else 0
    volume_lots = volume / 100000  # MT5 volume units to lots
    
    outcome = "win" if pnl > 0 else "loss"
    
    trade = {
        "position_id": pos_id,
        "ticket": close_deals[0].ticket if close_deals else dlist[-1].ticket,
        "symbol": _SYMBOL,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_time": str(entry_time) if entry_time else "N/A",
        "exit_time": str(exit_time) if exit_time else "N/A",
        "holding_minutes": round(holding_minutes, 1) if holding_minutes else "N/A",
        "volume": volume,
        "volume_lots": volume_lots,
        "pnl": round(pnl, 2),
        "outcome": outcome,
        "exit_reason": exit_reason,
    }
    trades_found.append(trade)

print(f"\n=== Closed Trades Found: {len(trades_found)} ===")
for t in trades_found:
    print(f"  [{t['outcome'].upper()}] pos_id={t['position_id']} {t['direction']} "
          f"PNL={t['pnl']:+.2f} {t['exit_reason']} "
          f"entry={t['entry_price']} exit={t['exit_price']} "
          f"vol={t['volume_lots']:.2f} lots "
          f"hold={t['holding_minutes']}m")

if not trades_found:
    print("All positions have zero PnL (still open or partial fills).")
    mt5.shutdown()
    print("\n[SILENT]")
    sys.exit(0)

# --- Step 6: Analyze each trade ---
print(f"\n=== Trade Analysis ===")
wins = [t for t in trades_found if t['outcome'] == 'win']
losses = [t for t in trades_found if t['outcome'] == 'loss']
total_pnl = sum(t['pnl'] for t in trades_found)

for t in trades_found:
    print(f"\n--- Trade {t['position_id']} ---")
    print(f"  Direction: {t['direction']}")
    print(f"  PnL: {t['pnl']:+.2f}")
    print(f"  Exit: {t['exit_reason']} at {t['exit_price']}")
    
    if t['exit_reason'] == 'SL':
        print(f"  ⚠️ SL hit — stop-loss was triggered")
        print(f"  Root cause: Price moved against {t['direction']} position enough to hit SL")
        print(f"  Holding time: {t['holding_minutes']}m")
    
    if t['outcome'] == 'win':
        print(f"  ✅ Winning trade")
        if t['exit_reason'] == 'TP':
            print(f"  TP hit — target reached")
        elif t['exit_reason'] == 'SL':
            print(f"  ⚠️ SL hit but positive PnL — unusual, check deal details")
        else:
            print(f"  Manual or partial close")
    
    if t['outcome'] == 'loss':
        print(f"  ❌ Losing trade — ${abs(t['pnl']):.2f} loss")
        t['fix'] = "Review stop distance — consider ATR-based dynamic SL or wider initial stop" if t['exit_reason'] == 'SL' else "Review entry criteria — ensure VWAP deviation >= 10 pips + rejection candle before entry"
        if t['exit_reason'] == 'SL':
            print(f"  SL hit: stop distance may have been too tight for current volatility")
        print(f"  Needs mistakes_ledger entry")

print(f"\n=== Summary ===")
print(f"Total closed trades: {len(trades_found)}")
print(f"Wins: {len(wins)}")
print(f"Losses: {len(losses)}")
print(f"Win rate: {len(wins)/len(trades_found)*100:.1f}%" if trades_found else "N/A")
print(f"Total PnL: {total_pnl:+.2f}")

# --- Step 7: Update mistakes_ledger if losing trades ---
if losses:
    ledger_path = os.path.join(_TRADING_ROOT, "strategy_council", "mistakes_ledger.json")
    
    # Read existing ledger
    if os.path.exists(ledger_path):
        with open(ledger_path) as f:
            content = f.read().strip()
            if content:
                ledger = json.loads(content)
            else:
                ledger = {"strategy": "Propfirm Pass v11.0 — VWAP 2σ Bands (EURUSD)", "magic": 780012, "mistakes": [], "lessons_learned": []}
    else:
        ledger = {"strategy": "Propfirm Pass v11.0 — VWAP 2σ Bands (EURUSD)", "magic": 780012, "mistakes": [], "lessons_learned": []}
    
    # Dedup check
    existing = set()
    for m in ledger.get("mistakes", []):
        existing.add(f"{m['date']}_{m.get('direction', 'UNKNOWN')}_{m.get('pnl', 0)}")
    
    for t in losses:
        direction = t['direction']
        pnl = t['pnl']
        exit_reason = t['exit_reason']
        holding_minutes = t['holding_minutes']
        
        dedup_key = f"{utc_now.strftime('%Y-%m-%d')}_{direction}_{pnl}"
        
        if dedup_key not in existing:
            if window_active:
                root_cause = f"{'TP' if exit_reason == 'TP' else 'SL'} hit during active session — {direction} position closed at {t['exit_price']}, holding {holding_minutes}m"
            elif holding_minutes is not None and holding_minutes > 120:
                root_cause = f"Overnight {exit_reason} hit — {direction} entered during previous session, closed while bot was offline"
            else:
                root_cause = f"{exit_reason} hit outside session window — {direction} position at {t['entry_price']} → {t['exit_price']}, PnL={pnl:+.2f}"
            
            if exit_reason == 'SL':
                fix = "Review stop distance — consider ATR-based dynamic SL or wider initial stop"
                prevention_rule = "Check ATR (14) at entry; SL must be at least 1.5× ATR from entry to avoid noise-triggered stops"
            else:
                fix = "Review entry criteria — ensure VWAP deviation >= 10 pips + rejection candle before entry"
                prevention_rule = "Before entry, confirm VWAP deviation >= 10 pips AND price reversal candle on 5-min chart"
            
            entry = {
                "date": utc_now.strftime("%Y-%m-%d"),
                "direction": direction,
                "entry": t['entry_price'],
                "exit": t['exit_price'],
                "pnl": round(pnl, 2),
                "root_cause": root_cause,
                "fix": fix,
                "prevention_rule": prevention_rule
            }
            ledger["mistakes"].append(entry)
            print(f"\n📝 Added to mistakes_ledger: {direction} ${abs(pnl):.2f} loss")
        else:
            print(f"\n⏭️ Skipped dedup: {direction} ${abs(pnl):.2f} loss already in ledger")
    
    # Update stats
    ledger["last_updated"] = utc_now.strftime("%Y-%m-%d")
    
    # Write
    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2)
    print(f"Ledger written to {ledger_path}")

# --- Step 8: Report ---
print(f"\n\n=== CRITIQUE REPORT ===")
print(f"Date: {utc_now.strftime('%Y-%m-%d')}")
print(f"Run time (UTC): {utc_now.isoformat()}")
print(f"Total closed trades: {len(trades_found)}")
print(f"Wins: {len(wins)} / Losses: {len(losses)}")
print(f"Win rate: {len(wins)/len(trades_found)*100:.1f}%" if trades_found else "N/A")
print(f"Total PnL: {total_pnl:+.2f}")

if len(trades_found) < 20:
    print(f"\n⚠️ Small sample warning — only {len(trades_found)} trades. Patterns below are suggestive, not statistically significant.")

for t in trades_found:
    if t['outcome'] == 'win':
        print(f"\n✅ WIN: {t['direction']} ${t['pnl']:.2f}")
        print(f"   Exit: {t['exit_reason']} at {t['exit_price']}")
        if t['exit_reason'] == 'TP':
            print(f"   What went right: TP hit — trade direction was correct")
        print(f"   Preserve: {t['direction']} entries at this volatility level appear effective")
    elif t['outcome'] == 'loss':
        print(f"\n❌ LOSS: {t['direction']} ${abs(t['pnl']):.2f}")
        print(f"   Exit: {t['exit_reason']} at {t['exit_price']}")
        print(f"   Root cause: Price moved against position")
        print(f"   Prevention: {t['fix']}" if t.get('fix') else "")

if wins:
    print(f"\n📗 What went right:")
    for t in wins:
        print(f"  - {t['direction']} +${t['pnl']:.2f} ({t['exit_reason']})")

mt5.shutdown()
print("\nDone.")
