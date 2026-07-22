#!/usr/bin/env python3
"""
Post-Trade Critic — autonomous cron run.
Checks MT5 for closed trades by magic 780012 (EURUSD) in the last 2 hours.

Rules:
  - NEVER kill terminal64.exe from headless/cron sessions (Rule 1)
  - Use bare mt5.initialize() to attach to running terminal
  - Check account_info() matches config after connecting
  - If wrong account, report but don't attempt mt5.login() — may hang
"""
import os, sys, json
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ── Paths ──────────────────────────────────────────────────────────────
TRADING_ROOT = r"C:\Trading"
HERMESS_ROOT = r"C:\Hermess"
CONFIG_PATH = os.path.join(TRADING_ROOT, "mt5_config.json")
MISTAKES_LEDGER_PATH = os.path.join(TRADING_ROOT, "strategy_council", "mistakes_ledger.json")
CRITIQUE_DIR = os.path.join(TRADING_ROOT, "bots", "analytics")
os.makedirs(CRITIQUE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(MISTAKES_LEDGER_PATH), exist_ok=True)

# ── Config ─────────────────────────────────────────────────────────────
with open(CONFIG_PATH) as f:
    CFG = json.load(f)

EXPECTED_LOGIN = int(CFG.get("login", 0))
EXPECTED_SERVER = CFG.get("server", "")
MAGIC = 780012

# ── Connect (bare init — do NOT kill terminal) ──────────────────────
print("=" * 60)
print(f"Post-Trade Critic | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Magic: {MAGIC} | Symbol: EURUSD")
print("=" * 60)

import MetaTrader5 as mt5

# Try bare init first (attaches to running terminal without killing it)
print("\nStep 1: mt5.initialize() bare...")
init_ok = mt5.initialize()
if not init_ok:
    err = mt5.last_error()
    print(f"  Failed: {err}")
    # Try with path (still no kill)
    print("Step 2: mt5.initialize(path=terminal64.exe)...")
    term_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    init_ok = mt5.initialize(path=term_path)
    if not init_ok:
        err2 = mt5.last_error()
        print(f"  Failed: {err2}")
        print("CRITICAL: Cannot connect to MT5 terminal.")
        print(f"  Terminal PID should be running per tasklist check.")
        print(f"  Account may be wrong or IPC handshake failed.")
        mt5.shutdown()
        sys.exit(0)

print("  Connected successfully.")

# Verify account
info = mt5.account_info()
if info is None:
    print("ERROR: mt5.account_info() returned None")
    mt5.shutdown()
    sys.exit(0)

actual_login = info.login
actual_server = info.server
print(f"\nActive account: login={actual_login}, server={actual_server}")
print(f"Expected:       login={EXPECTED_LOGIN}, server={EXPECTED_SERVER}")

if actual_login != EXPECTED_LOGIN or actual_server.upper() != EXPECTED_SERVER.upper():
    print(f"WARNING: Account mismatch!")
    print(f"  Will query trades from active account ({actual_login})")
    print(f"  Trades may show wrong account's data.")

# ── Fetch trades (last 2 hours, local time) ──────────────────────────
local_now = datetime.now()
local_2h_ago = local_now - timedelta(hours=2)

print(f"\nQuery window: {local_2h_ago} → {local_now} (local)")
deals = mt5.history_deals_get(local_2h_ago, local_now)

if deals is None:
    err = mt5.last_error()
    if err == (1, 'Success'):
        print("No deals found in window (Success) — nothing to report.")
    else:
        print(f"history_deals_get failed: {err}")
    mt5.shutdown()
    sys.exit(0)

deals = list(deals)
print(f"Total deals in window: {len(deals)}")

# Filter by magic
my_deals = [d for d in deals if d.magic == MAGIC]
print(f"Deals with magic {MAGIC}: {len(my_deals)}")

if len(my_deals) == 0:
    print("\nNo trades found for magic 780012 in the last 2 hours.")
    mt5.shutdown()
    sys.exit(0)

# ── Group by position_id to build round-trip trades ──────────────────
pos_pnls = defaultdict(float)
pos_deals = defaultdict(list)
for d in my_deals:
    pos_pnls[d.position_id] += d.profit
    pos_deals[d.position_id].append(d)

closed_trades = []
for pos_id, deals_list in pos_deals.items():
    total_pnl = pos_pnls[pos_id]
    
    # Find entry and exit deals
    entry_deal = None
    exit_deal = None
    for d in deals_list:
        if d.type in (0, 1):  # DEAL_TYPE_BUY or SELL
            entry_deal = d
        elif d.type in (2, 3):  # DEAL_TYPE_BUY_CLOSE or SELL_CLOSE
            exit_deal = d
    
    if entry_deal is None or exit_deal is None:
        sorted_deals = sorted(deals_list, key=lambda x: x.time)
        if len(sorted_deals) >= 2:
            entry_deal = sorted_deals[0]
            exit_deal = sorted_deals[-1]
    
    if entry_deal and exit_deal:
        direction = "BUY" if entry_deal.type == 0 else "SELL"
        closed_trades.append({
            "position_id": pos_id,
            "symbol": entry_deal.symbol,
            "direction": direction,
            "entry_price": entry_deal.price,
            "exit_price": exit_deal.price,
            "volume": entry_deal.volume,
            "pnl": round(total_pnl, 2),
            "entry_time": datetime.fromtimestamp(entry_deal.time).strftime("%Y-%m-%d %H:%M:%S"),
            "exit_time": datetime.fromtimestamp(exit_deal.time).strftime("%Y-%m-%d %H:%M:%S"),
            "outcome": "win" if total_pnl > 0 else "loss",
            "commission": round(sum(d.commission for d in deals_list), 2),
            "swap": round(sum(d.swap for d in deals_list), 2),
        })

# ── Report ────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"CLOSED TRADES FOUND: {len(closed_trades)}")
print(f"{'='*60}")

if len(closed_trades) == 0:
    print("No complete round-trip trades detected.")
    mt5.shutdown()
    sys.exit(0)

wins = [t for t in closed_trades if t['outcome'] == 'win']
losses = [t for t in closed_trades if t['outcome'] == 'loss']
total_pnl = sum(t['pnl'] for t in closed_trades)

print(f"Wins: {len(wins)} | Losses: {len(losses)}")
print(f"Total PnL: ${total_pnl:.2f}")

for t in closed_trades:
    print(f"\n{'─'*50}")
    print(f"Position #{t['position_id']} | {t['symbol']} | {t['direction']}")
    print(f"  Entry: {t['entry_price']} @ {t['entry_time']}")
    print(f"  Exit:  {t['exit_price']} @ {t['exit_time']}")
    print(f"  Volume: {t['volume']}")
    print(f"  PnL: ${t['pnl']:.2f} ({t['outcome'].upper()})")
    print(f"  Comm: ${t['commission']:.2f} | Swap: ${t['swap']:.2f}")

# ── Load mistakes ledger ──────────────────────────────────────────────
ledger = None
if os.path.exists(MISTAKES_LEDGER_PATH):
    with open(MISTAKES_LEDGER_PATH) as f:
        try:
            ledger = json.load(f)
        except json.JSONDecodeError:
            ledger = None

if ledger is None:
    ledger = {"strategy": "Propfirm Pass v8", "mistakes": [], "lessons_learned": []}

# Dedup set
existing = set()
for m in ledger.get("mistakes", []):
    existing.add(f"{m.get('date','')}_{m.get('direction','')}_{m.get('pnl',0)}")

# ── Process losing trades ─────────────────────────────────────────────
new_mistakes = []
for t in losses:
    date_str = t['exit_time'][:10]
    dedup_key = f"{date_str}_{t['direction']}_{t['pnl']}"
    if dedup_key in existing:
        print(f"  SKIP (duplicate): {dedup_key}")
        continue
    
    entry = {
        "date": date_str,
        "direction": t['direction'],
        "entry": t['entry_price'],
        "exit": t['exit_price'],
        "pnl": round(t['pnl'], 2),
        "root_cause": "Loss detected — requires manual review of entry conditions",
        "fix": "Review VWAP deviation, rejection candle, and news calendar at entry time",
        "prevention_rule": "Verify VWAP >= 10 pip deviation AND clear rejection candle before entry; check high-impact news calendar"
    }
    new_mistakes.append(entry)
    ledger["mistakes"].append(entry)
    print(f"  APPEND to ledger: {dedup_key}")

# ── Process winning trades ────────────────────────────────────────────
for t in wins:
    print(f"\n  WIN (+${t['pnl']:.2f}) — {t['symbol']} {t['direction']}")
    print(f"    Entry: {t['entry_price']} → Exit: {t['exit_price']}")
    print(f"    Holding: {t['entry_time']} → {t['exit_time']}")

# ── Save mistakes ledger if modified ──────────────────────────────────
if new_mistakes:
    with open(MISTAKES_LEDGER_PATH, 'w') as f:
        json.dump(ledger, f, indent=2)
    print(f"\nLedger updated: {len(new_mistakes)} new entries at {MISTAKES_LEDGER_PATH}")

# ── Save critique report ──────────────────────────────────────────────
today = local_now.strftime("%Y-%m-%d")
report = {
    "date": today,
    "run_time": local_now.strftime("%Y-%m-%dT%H:%M:%S"),
    "total_trades": len(closed_trades),
    "wins": len(wins),
    "losses": len(losses),
    "win_rate": round(len(wins) / len(closed_trades) * 100, 1) if closed_trades else 0,
    "total_pnl": round(total_pnl, 2),
    "trades": closed_trades,
    "account": {
        "active_login": actual_login,
        "active_server": actual_server,
        "expected_login": EXPECTED_LOGIN,
        "expected_server": EXPECTED_SERVER
    }
}

report_path = os.path.join(CRITIQUE_DIR, f"daily_critique_{today}.json")
with open(report_path, 'w') as f:
    json.dump(report, f, indent=2)
print(f"Report saved: {report_path}")

# ── Final Summary ─────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"SUMMARY")
print(f"{'='*60}")
print(f"Trades: {len(closed_trades)} | Wins: {len(wins)} | Losses: {len(losses)}")
print(f"Total PnL: ${total_pnl:.2f}")

mt5.shutdown()
