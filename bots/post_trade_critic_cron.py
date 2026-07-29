#!/usr/bin/env python
"""
Post-Trade Critic — Propfirm Pass v8 (magic 780012, EURUSD)
Runs as cron, checks last 2h for closed trades.
[POST-TRADE-CRITIC-AGENT v1.19.0]
"""
import os, sys, json, time, datetime
from datetime import datetime as dt, timedelta, timezone

# ─── Config ──────────────────────────────────────────────────────────
MAGIC = 780012
SYMBOL = "EURUSD"
LOOKBACK_HOURS = 2
HERMESS_ROOT = r"C:\Hermess"
TRADING_ROOT = r"C:\Trading"
MISTAKES_LEDGER = os.path.join(TRADING_ROOT, "strategy_council", "mistakes_ledger.json")
CRITIQUE_DIR = os.path.join(TRADING_ROOT, "bots", "analytics")
BOT_CONFIG = os.path.join(HERMESS_ROOT, "mt5_config.json")

os.makedirs(CRITIQUE_DIR, exist_ok=True)

# ─── MT5 Connection ────────────────────────────────────────────────
# Load config for expected account
with open(BOT_CONFIG) as f:
    cfg = json.load(f)
EXPECTED_LOGIN = int(cfg.get("login", 0))
EXPECTED_SERVER = cfg.get("server", "")

def connect():
    """Connect to already-running MT5 terminal. Do NOT kill terminal64.exe (Rule 1)."""
    if mt5.initialize(timeout=5000):
        info = mt5.account_info()
        if info and info.login == EXPECTED_LOGIN and info.server == EXPECTED_SERVER:
            return True
    # Already initialized or on wrong account — shutdown and try credential
    mt5.shutdown()
    ok = mt5.initialize(login=EXPECTED_LOGIN, password=cfg.get("password",""),
                        server=EXPECTED_SERVER, timeout=5000)
    if ok:
        info = mt5.account_info()
        return info is not None
    return False

# ─── Query history deals ───────────────────────────────────────────
import MetaTrader5 as mt5

def query_trades():
    """Fetch closed deals for magic 780012 in last N hours."""
    local_now = dt.now()
    from_time = local_now - timedelta(hours=LOOKBACK_HOURS)
    
    deals = mt5.history_deals_get(from_time, local_now)
    if deals is None:
        err = mt5.last_error()
        # MT5 returns (1, 'Success') when no deals exist — not an error
        if err and err[0] == 1:
            return []
        # Real error
        print(f"ERROR: history_deals_get returned None: {err}")
        return None
    
    # Filter by magic and symbol
    my_deals = [d for d in deals if d.magic == MAGIC and d.symbol == SYMBOL]
    return my_deals

# ─── Deal pairing (entry/exit per position) ────────────────────────
from collections import defaultdict

def get_trade_direction(entry_deals, close_deals):
    """Determine trade direction from available deals for a position."""
    if entry_deals:
        return "BUY" if entry_deals[0].type == 0 else "SELL"
    elif close_deals:
        # Close-only deal: type is OPPOSITE of direction
        return "SELL" if close_deals[0].type == 0 else "BUY"
    return "UNKNOWN"

def pair_trades(deals):
    """Group deals by position_id and return complete trades."""
    if not deals:
        return []
    
    # Group by position_id
    by_pos = defaultdict(list)
    for d in deals:
        by_pos[d.position_id].append(d)
    
    trades = []
    for pos_id, pos_deals in by_pos.items():
        entry_deals = [d for d in pos_deals if d.entry == 0]  # DEAL_ENTRY_IN
        close_deals = [d for d in pos_deals if d.entry == 1]  # DEAL_ENTRY_OUT
        
        if not close_deals:
            continue  # position still open
        
        # Compute PnL from all deals
        total_pnl = sum(d.profit for d in pos_deals)
        if total_pnl == 0:
            continue  # no completed trade
        
        direction = get_trade_direction(entry_deals, close_deals)
        
        entry_price = entry_deals[0].price if entry_deals else close_deals[0].price
        exit_price = close_deals[0].price if close_deals else entry_deals[0].price
        entry_time = dt.fromtimestamp(entry_deals[0].time) if entry_deals else None
        exit_time = dt.fromtimestamp(close_deals[0].time) if close_deals else None
        volume = sum(abs(d.volume) for d in entry_deals) if entry_deals else abs(close_deals[0].volume)
        
        # Determine exit reason from comment
        exit_reason = "close"
        for d in close_deals:
            if "[sl" in d.comment.lower():
                exit_reason = "SL"
            elif "[tp" in d.comment.lower():
                exit_reason = "TP"
        
        # Compute R:R if we have entry and exit prices
        rr = None
        if entry_price and exit_price and entry_price != 0:
            if direction == "BUY":
                rr = (exit_price - entry_price) / (entry_price - exit_price) if exit_price < entry_price else None
            else:  # SELL
                rr = (entry_price - exit_price) / (exit_price - entry_price) if exit_price > entry_price else None
        
        holding_minutes = None
        if entry_time and exit_time:
            holding_minutes = (exit_time - entry_time).total_seconds() / 60
        
        # Score
        score = score_trade(total_pnl, rr, holding_minutes, volume)
        
        quality = "good" if score >= 8 else ("acceptable" if score >= 5 else ("poor" if score >= 3 else "error"))
        
        trade = {
            "position_id": pos_id,
            "symbol": SYMBOL,
            "direction": direction,
            "entry_price": round(entry_price, 5),
            "exit_price": round(exit_price, 5),
            "volume": volume,
            "pnl": round(total_pnl, 2),
            "score": score,
            "quality": quality,
            "outcome": "win" if total_pnl > 0 else "loss",
            "exit_reason": exit_reason,
            "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S") if entry_time else "unknown",
            "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S") if exit_time else "unknown",
            "holding_minutes": round(holding_minutes, 1) if holding_minutes else None,
            "comment": close_deals[0].comment if close_deals else ""
        }
        trades.append(trade)
    
    return trades

def score_trade(pnl, rr, holding_minutes, volume):
    """Score a trade 1-10."""
    s = 5  # base
    
    # P&L outcome
    if pnl > 0:
        s += 2
        if pnl > 50:
            s += 1
    else:
        s -= 1
        if pnl < -50:
            s -= 1
    
    # R:R quality (only if available)
    if rr is not None:
        if rr >= 2:
            s += 2
        elif rr >= 1:
            s += 1
        elif rr < 0.5:
            s -= 1
    
    # Holding time
    if holding_minutes is not None:
        if 10 <= holding_minutes <= 180:
            s += 1  # reasonable hold
        elif holding_minutes > 360:
            s -= 1  # held too long
        elif holding_minutes < 5:
            s -= 1  # quick scalp
    
    # Volume (appropriate)
    if volume == 0.1:
        s += 1
    elif volume > 0.5:
        s -= 1
    
    return max(1, min(10, s))

# ─── Mistakes Ledger ───────────────────────────────────────────────
def load_ledger():
    if not os.path.exists(MISTAKES_LEDGER):
        default = {"strategy": "Propfirm Pass v8", "mistakes": [], "lessons_learned": []}
        with open(MISTAKES_LEDGER, "w") as f:
            json.dump(default, f, indent=2)
        return default
    with open(MISTAKES_LEDGER) as f:
        content = f.read().strip()
        if not content:
            return {"strategy": "Propfirm Pass v8", "mistakes": [], "lessons_learned": []}
        return json.loads(content)

def append_mistake(trade):
    """Append a losing trade to the mistakes ledger with dedup."""
    ledger = load_ledger()
    
    # Dedup key
    dup_key = f"{dt.now().strftime('%Y-%m-%d')}_{trade['direction']}_{trade['pnl']}"
    existing = set()
    for m in ledger.get("mistakes", []):
        existing.add(f"{m.get('date','')}_{m.get('direction','')}_{m.get('pnl',0)}")
    
    if dup_key in existing:
        print(f"SKIP: Duplicate mistake entry {dup_key}")
        return False
    
    # Get entry/exit prices from the trade
    entry = trade["entry_price"]
    exit_p = trade["exit_price"]
    direction = trade["direction"]
    pnl = trade["pnl"]
    exit_reason = trade.get("exit_reason", "close")
    
    # Determine root cause
    if exit_reason == "SL":
        root_cause = f"Stop-loss hit at {exit_p} — price reversed {abs(exit_p - entry):.5f} pips against entry"
        fix = "Check VWAP deviation before entry — ensure trend is established, not fading"
        prevention_rule = "Verify price is beyond 2σ VWAP band AND has rejection candle before entry"
    elif trade["holding_minutes"] and trade["holding_minutes"] < 5:
        root_cause = f"Quick exit at {exit_p} — entered but price immediately reversed"
        fix = "Wait for candle close confirmation before entry"
        prevention_rule = "Do not enter on live candle — wait for close to confirm rejection"
    else:
        root_cause = f"Price moved from {entry} to {exit_p} — trend continued against entry direction"
        fix = "Check higher timeframe trend before entry"
        prevention_rule = "Align entries with 15-min EMA trend direction"
    
    mistake = {
        "date": dt.now().strftime("%Y-%m-%d"),
        "direction": direction,
        "entry": entry,
        "exit": exit_p,
        "pnl": round(pnl, 2),
        "root_cause": root_cause,
        "fix": fix,
        "prevention_rule": prevention_rule
    }
    
    ledger["mistakes"].append(mistake)
    
    with open(MISTAKES_LEDGER, "w") as f:
        json.dump(ledger, f, indent=2)
    
    print(f"✓ Appended mistake to ledger: {direction} {SYMBOL} PnL={pnl:.2f}")
    return True

# ─── Pattern Detection ─────────────────────────────────────────────
def detect_patterns(trades):
    patterns = []
    if not trades:
        return patterns
    
    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    total = len(trades)
    wr = (len(wins) / total * 100) if total > 0 else 0
    
    # Low win rate
    if wr < 40 and total >= 3:
        patterns.append({"pattern": "Low win rate", "severity": "CRITICAL",
                         "detail": f"{wr:.1f}% across {total} trades"})
    elif wr < 50 and total >= 3:
        patterns.append({"pattern": "Below average WR", "severity": "WARNING",
                         "detail": f"{wr:.1f}% across {total} trades"})
    
    # Consecutive losses
    if len(losses) >= 3:
        patterns.append({"pattern": "Consecutive losses", "severity": "CRITICAL",
                         "detail": f"{len(losses)} losses in a row"})
    
    # Exit reason patterns
    sl_count = sum(1 for t in trades if t.get("exit_reason") == "SL")
    tp_count = sum(1 for t in trades if t.get("exit_reason") == "TP")
    if sl_count > tp_count * 2 and total >= 3:
        patterns.append({"pattern": "SL/TP imbalance", "severity": "HIGH",
                         "detail": f"{sl_count} SL hits vs {tp_count} TP hits"})
    
    return patterns

# ─── Recommendations ──────────────────────────────────────────────
def generate_recommendations(trades, patterns, losses):
    recs = []
    
    for p in patterns:
        if p["pattern"] == "Low win rate":
            recs.append(f"Review entry criteria — WR {p['detail']}. Consider tightening VWAP deviation filter or adding trend confirmation.")
        elif p["pattern"] == "Consecutive losses":
            recs.append(f"Consecutive losses detected ({p['detail']}). Implement cooldown timer or daily loss limit.")
        elif p["pattern"] == "SL/TP imbalance":
            recs.append(f"SL/TP imbalance: {p['detail']}. Consider widening stops or tightening targets.")
    
    if losses:
        recs.append("Review each losing trade's root cause in mistakes_ledger.json and verify prevention rules are actionable.")
    
    return recs

# ─── Main ──────────────────────────────────────────────────────────
def main():
    run_time = dt.now().strftime("%Y-%m-%dT%H:%M:%S")
    today = dt.now().strftime("%Y-%m-%d")
    
    print(f"=== Post-Trade Critic | {run_time} UTC | Magic={MAGIC} {SYMBOL} ===\n")
    
    # Step 0: Connect to MT5
    if not connect():
        print("ERROR: Failed to connect to MT5")
        # Check if terminal is running
        import subprocess
        r = subprocess.run(['tasklist'], capture_output=True, text=True, timeout=10)
        if 'terminal64' in r.stdout:
            print("  MT5 terminal is running but connection failed — possible IPC handshake issue")
        else:
            print("  MT5 terminal is NOT running")
        return 1
    
    # Step 1: Verify MT5 account
    info = mt5.account_info()
    if not info:
        print("ERROR: Cannot get account info")
        return 1
    
    actual_login = info.login
    actual_server = info.server
    print(f"Connected: login={actual_login}, server={actual_server}")
    
    if actual_login != EXPECTED_LOGIN or actual_server != EXPECTED_SERVER:
        print(f"WARNING: Connected to {actual_login}/{actual_server}, expected {EXPECTED_LOGIN}/{EXPECTED_SERVER}")
    
    # Step 2: Query trades
    local_now = dt.now()
    from_time = local_now - timedelta(hours=LOOKBACK_HOURS)
    print(f"Query range: {from_time} → {local_now} (local, {LOOKBACK_HOURS}h)")
    
    raw_deals = query_trades()
    if raw_deals is None:
        print("ERROR: Failed to query MT5 history")
        return 1
    
    print(f"Raw deals: {len(raw_deals)}")
    
    trades = pair_trades(raw_deals)
    print(f"Paired trades: {len(trades)}")
    
    if not trades:
        print("No completed trades found in last 2 hours.")
        return 0  # [SILENT]
    
    # Step 3: Analyze each trade
    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    total_pnl = sum(t["pnl"] for t in trades)
    avg_score = sum(t["score"] for t in trades) / len(trades) if trades else 0
    wr = (len(wins) / len(trades) * 100) if trades else 0
    
    print(f"\nResults: {len(wins)}W / {len(losses)}L | Win rate: {wr:.1f}% | PnL: ${total_pnl:.2f}")
    
    for t in trades:
        print(f"\n  [{t['outcome'].upper()}] {t['direction']} {t['symbol']} | "
              f"Entry: {t['entry_price']} → Exit: {t['exit_price']} | "
              f"PnL: ${t['pnl']:.2f} | Score: {t['score']}/10 ({t['quality']}) | "
              f"Exit: {t['exit_reason']} | Hold: {t['holding_minutes']}min")
        
        if t["outcome"] == "win":
            print(f"  ✓ Positives: Winning trade (+${t['pnl']:.2f})")
            if t["exit_reason"] == "TP":
                print(f"  ✓ Take-profit hit — strategy executed as expected")
        else:
            print(f"  ✗ Root cause: {t.get('exit_reason', 'close')} exit at {t['exit_price']}")
            if t["holding_minutes"] and t["holding_minutes"] < 5:
                print(f"  ✗ Quick exit — possible premature entry or fakeout")
    
    # Step 4: Append losing trades to mistakes ledger
    for t in losses:
        append_mistake(t)
    
    # Step 5: Pattern detection
    patterns = detect_patterns(trades)
    recs = generate_recommendations(trades, patterns, losses)
    
    # Step 6: Build report
    per_symbol = {SYMBOL: {"wins": len(wins), "losses": len(losses),
                           "total_pnl": round(total_pnl, 2)}}
    
    trade_critiques = []
    for t in trades:
        positives = []
        negatives = []
        if t["outcome"] == "win":
            positives.append(f"Winning trade: +${t['pnl']:.2f}")
            if t["exit_reason"] == "TP":
                positives.append("Take-profit hit — strategy executed correctly")
        else:
            negatives.append(f"Losing trade: ${t['pnl']:.2f}")
            if t["exit_reason"] == "SL":
                negatives.append("Stop-loss hit")
        
        trade_critiques.append({
            "ticket": t["position_id"],
            "symbol": t["symbol"],
            "direction": t["direction"],
            "entry_price": t["entry_price"],
            "exit_price": t["exit_price"],
            "volume": t["volume"],
            "pnl": t["pnl"],
            "score": t["score"],
            "quality": t["quality"],
            "outcome": t["outcome"],
            "positives": positives,
            "negatives": negatives,
            "root_cause": "N/A (winning trade)" if t["outcome"] == "win" else f"SL hit at {t['exit_price']}",
            "holding_minutes": t["holding_minutes"],
            "exit_reason": t["exit_reason"]
        })
    
    report = {
        "date": today,
        "run_time": run_time,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(wr, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_score": round(avg_score, 1),
        "per_symbol": per_symbol,
        "patterns": patterns,
        "trade_critiques": trade_critiques,
        "recommendations": recs
    }
    
    # Save report
    report_path = os.path.join(CRITIQUE_DIR, f"daily_critique_{today}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved: {report_path}")
    
    # Print patterns
    if patterns:
        print(f"\nPatterns detected:")
        for p in patterns:
            print(f"  [{p['severity']}] {p['pattern']}: {p['detail']}")
    
    if recs:
        print(f"\nRecommendations:")
        for r in recs:
            print(f"  → {r}")
    
    # Verify mistakes ledger was modified
    if losses:
        mtime = os.path.getmtime(MISTAKES_LEDGER)
        print(f"\nMistakes ledger mtime: {dt.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
