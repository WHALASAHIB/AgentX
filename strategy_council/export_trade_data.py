#!/usr/bin/env python3
"""Export all M780012 trade data from MT5 before account expires."""
import MetaTrader5 as mt5
from datetime import datetime, timezone
from collections import defaultdict
import json, os, sys

OUT_DIR = r"C:\Trading\strategy_council"
os.makedirs(OUT_DIR, exist_ok=True)

mt5.shutdown()
if not mt5.initialize(timeout=15000):
    print("MT5 init failed")
    sys.exit(1)

acc = mt5.account_info()
print(f"Account: {acc.login} @ {acc.server} balance={acc.balance} equity={acc.equity}")

deals = mt5.history_deals_get(datetime(2026, 7, 1), datetime(2026, 7, 20))
if not deals:
    print("No deals found")
    mt5.shutdown()
    sys.exit(0)

our = [d for d in deals if d.magic == 780012]
by_pos = defaultdict(list)
for d in our:
    by_pos[d.position_id].append(d)

trades = []
for pos_id, ds in sorted(by_pos.items()):
    opens = [d for d in ds if d.profit == 0]
    closes = [d for d in ds if d.profit != 0]
    if opens:
        entry = opens[0]
        exit_d = closes[0] if closes else None
        et = datetime.fromtimestamp(entry.time).strftime("%Y-%m-%d %H:%M")
        xt = datetime.fromtimestamp(exit_d.time).strftime("%Y-%m-%d %H:%M") if exit_d else "OPEN"
        direction = "BUY" if entry.type == 0 else "SELL"
        pnl = float(exit_d.profit) if exit_d else 0.0
        hm = float((exit_d.time - entry.time) / 60) if exit_d else 0
        trades.append({
            "pos_id": int(pos_id),
            "date": et[:10],
            "entry_time": et,
            "exit_time": xt,
            "direction": direction,
            "entry_price": float(entry.price),
            "exit_price": float(exit_d.price) if exit_d else float(entry.price),
            "volume": float(entry.volume),
            "pnl": round(pnl, 2),
            "holding_mins": round(hm, 0),
            "comment": str(exit_d.comment) if exit_d else "OPEN",
            "status": "closed" if exit_d else "open"
        })

path = os.path.join(OUT_DIR, "full_trade_history.json")
with open(path, "w") as f:
    json.dump(trades, f, indent=2)
print(f"Saved: {path} ({len(trades)} trades)")

closed = [t for t in trades if t["status"] == "closed"]
wins = [t for t in closed if t["pnl"] > 0]
losses = [t for t in closed if t["pnl"] < 0]
total_pnl = sum(t["pnl"] for t in closed)

summary = {
    "strategy": "Propfirm Pass v9",
    "magic": 780012,
    "symbol": "EURUSD",
    "account_login": int(acc.login),
    "account_server": str(acc.server),
    "period": "2026-07-08 to 2026-07-15",
    "total_trades": len(closed),
    "wins": len(wins),
    "losses": len(losses),
    "win_rate": round(len(wins)/len(closed)*100, 1) if closed else 0,
    "total_pnl": round(total_pnl, 2),
    "avg_win": round(sum(t["pnl"] for t in wins)/len(wins), 2) if wins else 0,
    "avg_loss": round(sum(t["pnl"] for t in losses)/len(losses), 2) if losses else 0,
    "profit_factor": round(abs(sum(t["pnl"] for t in wins)/sum(t["pnl"] for t in losses)), 2) if wins and losses else 0,
    "final_balance": float(acc.balance),
    "final_equity": float(acc.equity),
    "export_time": datetime.now(timezone.utc).isoformat()
}
spath = os.path.join(OUT_DIR, "strategy_summary.json")
with open(spath, "w") as f:
    json.dump(summary, f, indent=2)
print(f"Saved: {spath}")

# Print full report
print(f'\n{"="*60}')
print(f"STRATEGY PERFORMANCE REPORT")
print(f"{'='*60}")
print(f"Period:    2026-07-08 to 2026-07-15")
print(f"Account:   {acc.login} @ {acc.server}")
print(f"Symbol:    EURUSD | Magic: 780012")
print(f"{'='*60}")
print(f"Total trades:  {len(closed)}")
print(f"Wins:          {len(wins)} ({len(wins)/len(closed)*100:.1f}%)")
print(f"Losses:        {len(losses)} ({len(losses)/len(closed)*100:.1f}%)")
print(f"Total PnL:     ${total_pnl:.2f}")
if wins: print(f"Avg win:       ${sum(t['pnl'] for t in wins)/len(wins):.2f}")
if losses: print(f"Avg loss:      ${sum(t['pnl'] for t in losses)/len(losses):.2f}")
if wins and losses:
    print(f"Profit factor: {abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)):.2f}")
print(f"Final balance: ${acc.balance:.2f}")
print(f"{'='*60}")

print(f"\nTRADE LOG:")
print(f"{'Dir':<6} {'Entry':<12} {'Exit':<12} {'Vol':<6} {'PnL':<10} {'Holding':<8} Result")
print(f"{'-'*70}")
for t in trades:
    emoji = "✅ WIN" if t['pnl'] > 0 else "❌ LOSS" if t['pnl'] < 0 else "🔄 OPEN"
    print(f"{t['direction']:<6} {t['entry_price']:<12.5f} {t['exit_price']:<12.5f} {t['volume']:<6.2f} ${t['pnl']:<+8.2f} {t['holding_mins']:<8.0f}m {emoji}")

mt5.shutdown()
