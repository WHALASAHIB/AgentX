#!/usr/bin/env python3
"""Daily analysis script for XAUUSD bots."""
import json, os, subprocess, sys
sys.path.insert(0, r'C:\Trading')
from utils.mt5_connect import load_config, connect_mt5
import MetaTrader5 as mt5

BOTS_DIR = r'C:\Trading\bots'
LOGS_DIR = r'C:\Trading\logs'
OUTPUT_FILE = r'C:\Trading\logs\daily_report.txt'

config = load_config()
if not config:
    print("NO_CONFIG")
    sys.exit(1)
ok = connect_mt5(config)
if not ok:
    print("MT5_FAIL")
    sys.exit(1)
account = mt5.account_info()
if not account:
    print("NO_ACCOUNT")
    mt5.shutdown()
    sys.exit(1)

bal = account.balance
eq = account.equity
prof = account.profit
lgn = account.login
srv = account.server

print("ACCOUNT|%s|%s|%.2f|%.2f|%.2f" % (srv, lgn, bal, eq, prof))
positions = mt5.positions_get()
total_positions = len(positions) if positions else 0
print("POSITIONS|%d" % total_positions)

pos_list = []
if total_positions > 0 and positions:
    for p in positions:
        pos_list.append("%s %s Lot=%.2f Open=%.2f SL=%.2f TP=%.2f PnL=%.2f" % (p.symbol, p.type_str, p.volume, p.price_open, p.sl, p.tp, p.profit))
        print("POSITION|%s|%s|%.2f|%.2f|%.2f|%.2f|%.2f" % (p.symbol, p.type_str, p.volume, p.price_open, p.sl, p.tp, p.profit))

results = {}
if os.path.isdir(LOGS_DIR):
    for fname in os.listdir(LOGS_DIR):
        if fname.endswith(".log"):
            fpath = os.path.join(LOGS_DIR, fname)
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            last = lines[-30:] if len(lines) > 30 else lines
            results[fname] = "".join(last)
mt5.shutdown()

out = []
out.append("Daily Performance - %s" % srv)
out.append("Account: %s" % lgn)
out.append("Balance: DOLAR%.2f  Equity: DOLAR%.2f  Profit: DOLAR%.2f" % (bal, eq, prof))
out.append("Open Positions: %d" % total_positions)
out.append("")
for p in pos_list:
    out.append("  " + p)
out.append("")
for name, content in results.items():
    out.append("=== %s (last entries) ===" % name)
    out.append(content.strip()[-500:])
    out.append("")

output = "\n".join(out)
output = output.replace("DOLAR", "$")
print(output)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(output)
