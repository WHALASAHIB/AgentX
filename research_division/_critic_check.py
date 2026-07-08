"""
Post-Trade Critic — check closed trades in last 2 hours for magic 780012 (EURUSD)
Read-only analysis.
"""
import MetaTrader5 as mt5
import json
from datetime import datetime, timezone, timedelta

# --- Connect ---
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    exit(1)

info = mt5.account_info()
if info is None:
    print(f"account_info() failed: {mt5.last_error()}")
    mt5.shutdown()
    exit(1)

print(f"Connected to: login={info.login}, server={info.server}, name={info.name}")

# --- Time window ---
to_time = datetime.now()  # timezone-naive for MT5 API
from_time = to_time - timedelta(hours=2)

print(f"Query window: {from_time} -> {to_time}")

# --- Fetch history deals ---
deals = mt5.history_deals_get(from_time, to_time)
if deals is None:
    err = mt5.last_error()
    print(f"history_deals_get returned None. last_error={err}")
    mt5.shutdown()
    exit(0)

print(f"Found {len(deals)} total deals in window")

# --- Filter by magic 780012 and symbol EURUSD ---
magic = 780012
symbol = "EURUSD"

relevant = [d for d in deals if d.magic == magic and d.symbol == symbol]
print(f"Found {len(relevant)} deals for magic={magic}, symbol={symbol}")

if not relevant:
    print("NO_TRADES_FOUND")
    mt5.shutdown()
    exit(0)

# --- Group by position_id to pair entry/exit ---
from collections import defaultdict

positions = defaultdict(list)
for d in relevant:
    positions[d.position_id].append(d)

print(f"Found {len(positions)} unique positions")

critiques = []
for pos_id, pos_deals in positions.items():
    entry = None
    exit_deal = None
    for d in pos_deals:
        if d.entry == 0:  # entry deal
            entry = d
        elif d.entry == 1:  # exit deal
            exit_deal = d
    
    if entry is None or exit_deal is None:
        print(f"  Position {pos_id}: incomplete ({len(pos_deals)} deals, entry={entry is not None}, exit={exit_deal is not None})")
        continue
    
    direction = "BUY" if entry.type == 0 else "SELL"
    pnl = exit_deal.profit
    entry_price = entry.price
    exit_price = exit_deal.price
    volume = entry.volume
    commission = exit_deal.commission + entry.commission
    swap = exit_deal.swap
    
    outcome = "win" if pnl > 0 else "loss"
    
    # Calculate R:R
    sl_distance = abs(entry.price - entry.sl) if entry.sl else None
    tp_distance = abs(entry.price - entry.tp) if entry.tp else None
    
    print(f"\n  Position {pos_id}: {direction} {symbol} vol={volume}")
    print(f"    Entry: {entry_price} | Exit: {exit_price}")
    print(f"    SL: {entry.sl} | TP: {entry.tp}")
    print(f"    PnL: ${pnl:.2f} (commission={commission:.2f}, swap={swap:.2f})")
    print(f"    Outcome: {outcome}")
    
    critique = {
        "ticket": exit_deal.ticket,
        "position_id": pos_id,
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "volume": volume,
        "pnl": round(pnl, 2),
        "commission": round(commission, 2),
        "swap": round(swap, 2),
        "outcome": outcome,
        "entry_time": str(entry.time),
        "exit_time": str(exit_deal.time),
        "entry_sl": entry.sl,
        "entry_tp": entry.tp,
    }
    
    # --- Analyze ---
    positives = []
    negatives = []
    root_cause = "N/A (winning trade)"
    fix = ""
    prevention_rule = ""
    
    if outcome == "win":
        positives.append(f"Winning trade: +${pnl:.2f}")
        if pnl > 0 and sl_distance and pnl / sl_distance > 1.5:
            positives.append(f"Good R:R (realized {pnl/sl_distance:.1f}R)")
        if exit_deal.time - entry.time < timedelta(hours=1):
            positives.append("Quick win — held less than 1 hour")
        root_cause = "N/A (winning trade)"
    else:
        negatives.append(f"Losing trade: ${pnl:.2f}")
        if exit_deal.time - entry.time > timedelta(hours=2):
            negatives.append("Held too long on a loser")
        
        # Determine root cause
        if entry.sl and abs(exit_price - entry.sl) < 0.0001 * entry_price:
            root_cause = "Stop-loss hit — price reversed against position"
            fix = "Review SL placement — consider wider SL or check for news before entry"
            prevention_rule = "Check high-impact news calendar before every US session trade"
        elif entry.tp and abs(exit_price - entry.tp) < 0.0001 * entry_price:
            root_cause = "Take-profit hit (loss) — unusual, check for slippage"
            fix = "Review TP placement and broker execution quality"
            prevention_rule = "Verify TP level with broker quote before entry"
        elif exit_deal.time - entry.time < timedelta(minutes=5):
            root_cause = "Immediate stop-out — price gapped or fast reversal after entry"
            fix = "Check spread/volatility before entry; consider wider SL in high vol"
            prevention_rule = "Check ATR and spread before entering during volatile periods"
        else:
            root_cause = "Price moved against position and was manually or automatically closed"
            fix = "Review exit criteria — consider trailing stop or earlier manual exit"
            prevention_rule = "Set trailing stop after 1:1 R:R is reached"
    
    critique.update({
        "positives": positives,
        "negatives": negatives,
        "root_cause": root_cause,
        "fix": fix if outcome == "loss" else "",
        "prevention_rule": prevention_rule if outcome == "loss" else ""
    })
    
    critiques.append(critique)

# --- Summary ---
wins = sum(1 for c in critiques if c["outcome"] == "win")
losses = sum(1 for c in critiques if c["outcome"] == "loss")
total_pnl = sum(c["pnl"] for c in critiques)
win_rate = wins / len(critiques) * 100 if critiques else 0

print(f"\n=== SUMMARY ===")
print(f"Total positions: {len(critiques)}")
print(f"Wins: {wins}, Losses: {losses}")
print(f"Win rate: {win_rate:.1f}%")
print(f"Total PnL: ${total_pnl:.2f}")

# Output JSON for the main agent to process
print("\n=== CRITIQUES_JSON ===")
print(json.dumps(critiques, indent=2, default=str))

mt5.shutdown()
