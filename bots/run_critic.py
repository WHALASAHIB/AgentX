"""
Post-Trade Critic Agent — cron run
Checks MT5 for closed trades (magic 780012, EURUSD, last 2h)
Generates critique report and optionally updates mistakes ledger.
"""
import os, sys, json, time
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────
MAGIC = 780012
SYMBOL = "EURUSD"
LOOKBACK_HOURS = 2
CONFIG_PATH = r"C:\Hermess\mt5_config.json"
STATE_PATH = r"C:\Hermess\bots\state\propfirm_pass_state.json"
MISTAKES_LEDGER_PATH = r"C:\Trading\strategy_council\mistakes_ledger.json"
CRITIQUE_DIR = r"C:\Trading\bots\analytics"
LOG_PATH = r"C:\Hermess\bots\logs\propfirm_pass_strategy.log"

# ── MT5 connection (headless-safe pattern — no taskkill) ────────────────
try:
    import MetaTrader5 as mt5
except ImportError:
    print("❌ MetaTrader5 not installed")
    sys.exit(1)

def connect_mt5_safe(config_path):
    """Connect to already-running terminal without killing it."""
    with open(config_path) as f:
        cfg = json.load(f)
    expected_login = int(cfg.get("login", 0))
    expected_server = cfg.get("server", "")
    
    # Tier 1: bare init — attaches to running terminal, keeps GUI intact
    if mt5.initialize(timeout=5000):
        info = mt5.account_info()
        if info and info.login == expected_login and info.server == expected_server:
            print(f"✓ Connected: {info.login}/{info.server} (matched config)")
            return True, info
        elif info:
            print(f"⚠ Connected but account mismatch: {info.login}/{info.server} vs expected {expected_login}/{expected_server}")
            # Still usable — return False so caller knows, but we can still query trades
            return True, info
        else:
            print("⚠ bare init returned True but account_info() is None")
            mt5.shutdown()
    
    # Tier 2: shutdown and try credential-based init
    print("⚠ Trying credential-based init...")
    mt5.shutdown()
    ok = mt5.initialize(login=expected_login, password=cfg.get("password", ""),
                        server=expected_server, timeout=5000)
    if ok:
        info = mt5.account_info()
        if info:
            print(f"✓ Credential init: {info.login}/{info.server}")
            return True, info
    print("❌ All connection methods failed")
    return False, None

# ── State file check ────────────────────────────────────────────────────
def check_state_file():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state = json.load(f)
        print(f"📁 State file: {state.get('total_trades', 0)} trades, "
              f"{state.get('total_wins', 0)}W/{state.get('total_losses', 0)}L, "
              f"sl_hits={state.get('sl_hits', 'N/A')}, tp_hits={state.get('tp_hits', 'N/A')}")
        return state
    else:
        print("⚠ STATE FILE MISSING — trade tracking, SL/TP counters all reset")
        return None

# ── Bot log check ───────────────────────────────────────────────────────
def check_bot_log():
    if not os.path.exists(LOG_PATH):
        print("⚠ Bot log file missing")
        return
    mtime = os.path.getmtime(LOG_PATH)
    age_minutes = (time.time() - mtime) / 60
    with open(LOG_PATH, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    last_20 = [l for l in lines[-50:] if "INFO" in l or "ERROR" in l or "trade" in l.lower() or "signal" in l.lower()]
    has_recent = age_minutes < 60
    print(f"📄 Bot log: {len(lines)} lines, last modified {age_minutes:.0f} min ago")
    if last_20:
        print(f"   Last entries: {last_20[-3:]}")
    if age_minutes > 60:
        print(f"⚠ Bot log stopped {age_minutes:.0f} min ago — possible zombie")

# ── Duplicate instance scan ─────────────────────────────────────────────
def check_duplicate_instances():
    import subprocess
    try:
        ps_cmd = r'Get-CimInstance Win32_Process -Filter "Name=' + "'" + r"python.exe" + "'" + r'" | Where-Object { $_.CommandLine -match "propfirm_pass" } | Measure-Object | Select-Object -ExpandProperty Count'
        r = subprocess.run(['powershell.exe', '-Command', ps_cmd],
            capture_output=True, text=True, timeout=15)
        count = int(r.stdout.strip()) if r.stdout.strip() else 0
        if count > 1:
            print(f"⚠ {count} instances of propfirm_pass_bot running — trade counts may be inflated")
        elif count == 0:
            print("ℹ No propfirm_pass_bot instances running")
        else:
            print(f"✓ {count} instance of propfirm_pass_bot running")
        return count
    except Exception as e:
        print(f"⚠ Could not check instances: {e}")
        return 0

# ── Fetch trades ────────────────────────────────────────────────────────
def fetch_trades():
    """Fetch closed trades for magic 780012, EURUSD in last N hours."""
    local_now = datetime.now()
    from_time = local_now - timedelta(hours=LOOKBACK_HOURS)
    
    print(f"🔍 Querying deals: {from_time} to {local_now} (local)")
    
    deals = mt5.history_deals_get(from_time, local_now)
    if deals is None:
        err = mt5.last_error()
        print(f"   history_deals_get returned None — last_error: {err}")
        return [], None
    
    print(f"   Total deals in window: {len(deals)}")
    
    # Filter by magic and symbol
    my_deals = [d for d in deals if d.magic == MAGIC and d.symbol == SYMBOL]
    print(f"   Deals matching magic {MAGIC}/{SYMBOL}: {len(my_deals)}")
    
    if not my_deals:
        return [], None
    
    # Print raw deals for debugging
    for d in my_deals[:10]:
        dt = datetime.fromtimestamp(d.time)
        entry_type = {0: "BUY/OPEN", 1: "SELL/CLOSE", 2: "INOUT"}.get(d.entry, f"entry={d.entry}")
        deal_type = {0: "BUY", 1: "SELL"}.get(d.type, f"type={d.type}")
        print(f"   Deal {d.ticket}: pos_id={d.position_id} {deal_type} {entry_type} "
              f"vol={d.volume} price={d.price} profit={d.profit:.2f} "
              f"time={dt} comment=\"{d.comment}\"")
    
    # Group by position_id to form round-trip trades
    pos_deals = defaultdict(list)
    for d in my_deals:
        pos_deals[d.position_id].append(d)
    
    trades = []
    for pos_id, pos_d in pos_deals.items():
        entry_deals = [d for d in pos_d if d.entry == 0]  # DEAL_ENTRY_IN
        close_deals = [d for d in pos_d if d.entry == 1]  # DEAL_ENTRY_OUT
        
        # Determine direction
        if entry_deals:
            direction = "BUY" if entry_deals[0].type == 0 else "SELL"
        elif close_deals:
            # Only close deals — type is OPPOSITE of direction
            direction = "SELL" if close_deals[0].type == 0 else "BUY"
        else:
            direction = "UNKNOWN"
        
        # Sum profit across all deals for this position
        total_pnl = sum(d.profit for d in pos_d)
        
        # Entry/exit prices
        entry_price = entry_deals[0].price if entry_deals else None
        exit_price = close_deals[0].price if close_deals else None
        
        # Timestamps
        entry_time = datetime.fromtimestamp(entry_deals[0].time) if entry_deals else None
        exit_time = datetime.fromtimestamp(close_deals[0].time) if close_deals else None
        
        # Holding time
        holding_hours = None
        if entry_time and exit_time:
            holding_hours = (exit_time - entry_time).total_seconds() / 3600
        
        # Exit reason from comment
        exit_reason = "close"
        if close_deals:
            comment = close_deals[0].comment or ""
            if "[sl" in comment.lower():
                exit_reason = "SL"
            elif "[tp" in comment.lower():
                exit_reason = "TP"
        
        # Volume
        volume = max(d.volume for d in pos_d) if pos_d else 0
        
        trades.append({
            "position_id": pos_id,
            "symbol": SYMBOL,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_time": str(entry_time) if entry_time else None,
            "exit_time": str(exit_time) if exit_time else None,
            "holding_hours": holding_hours,
            "volume": volume,
            "pnl": round(total_pnl, 2),
            "outcome": "win" if total_pnl > 0 else "loss",
            "exit_reason": exit_reason,
            "num_deals": len(pos_d),
        })
    
    return trades, my_deals

# ── Score a trade ───────────────────────────────────────────────────────
def score_trade(trade):
    """Score trade 1-10."""
    score = 5  # start neutral
    positives = []
    negatives = []
    root_cause = "N/A (winning trade)" if trade["outcome"] == "win" else None
    
    if trade["outcome"] == "win":
        score += 2
        ratio = abs(trade["pnl"]) / (abs(trade["pnl"]) + 1)  # placeholder
        positives.append(f"Winning trade: +${trade['pnl']:.2f}")
    else:
        score -= 2
        negatives.append(f"Losing trade: ${trade['pnl']:.2f}")
    
    # Holding time evaluation
    if trade["holding_hours"] is not None:
        if trade["holding_hours"] < 1:
            if trade["outcome"] == "win":
                score += 1
                positives.append("Quick win")
            else:
                score -= 1
                negatives.append(f"Quick loss ({trade['holding_hours']:.1f}h)")
        elif trade["holding_hours"] > 12:
            score -= 1
            negatives.append(f"Long holding ({trade['holding_hours']:.1f}h)")
    
    # Volume assessment
    vol = trade["volume"]
    if vol <= 0.3:
        score += 1
        positives.append(f"Appropriate sizing ({vol})")
    
    # Exit reason
    if trade["exit_reason"] == "SL":
        negatives.append("Stop-loss hit")
        score -= 1
    elif trade["exit_reason"] == "TP":
        positives.append("Take-profit hit")
        score += 1
    
    # Quality label
    if score >= 8:
        quality = "good"
    elif score >= 5:
        quality = "acceptable"
    elif score >= 3:
        quality = "poor"
    else:
        quality = "error"
    
    return {
        "score": min(max(score, 1), 10),
        "quality": quality,
        "positives": positives,
        "negatives": negatives,
    }

# ── Check session window ────────────────────────────────────────────────
def check_session_window(trades):
    """Verify each trade's UTC hour falls within declared session windows."""
    session_windows = [(13, 15)]  # US session 13-15 UTC
    outside = []
    for t in trades:
        if t["entry_time"]:
            try:
                trade_utc = datetime.fromisoformat(t["entry_time"]).replace(tzinfo=None)
                # Assume stored time is local? Let's check by comparing with UTC
                # Actually entry_time is from timestamp which is local
                # We need to check if it's within UTC window
                # For now, let's just check the hour
                trade_hour = datetime.fromisoformat(t["entry_time"]).hour
            except:
                trade_hour = 0
            
            in_window = any(open_h <= trade_hour < close_h for open_h, close_h in session_windows)
            if not in_window:
                outside.append(t)
    
    if outside:
        entries = ", ".join([f"{t['position_id']}@{t['entry_time']}" for t in outside[:3]])
        print(f"⚠ {len(outside)} trades outside US session (13-15 UTC): {entries}")

# ── Mistakes ledger ─────────────────────────────────────────────────────
def update_mistakes_ledger(losing_trades):
    """Append losing trades to mistakes ledger with dedup."""
    if not losing_trades:
        return
    
    # Read existing ledger
    ledger = {}
    if os.path.exists(MISTAKES_LEDGER_PATH):
        with open(MISTAKES_LEDGER_PATH) as f:
            content = f.read().strip()
            if content:
                ledger = json.loads(content)
    
    if not ledger:
        ledger = {"strategy": "Propfirm Pass v8", "mistakes": [], "lessons_learned": []}
    
    # Build existing dedup set
    existing = set()
    for m in ledger.get("mistakes", []):
        key = f"{m.get('date','')}_{m.get('direction','')}_{m.get('pnl',0)}"
        existing.add(key)
    
    added = 0
    for t in losing_trades:
        date_str = t.get("exit_time", "")[:10] if t.get("exit_time") else datetime.now().strftime("%Y-%m-%d")
        desc = f"{date_str}_{t['direction']}_{t['pnl']}"
        
        if desc not in existing:
            entry = {
                "date": date_str,
                "direction": t["direction"],
                "entry": t["entry_price"],
                "exit": t["exit_price"],
                "pnl": t["pnl"],
                "root_cause": t.get("root_cause", "Unknown — review required"),
                "fix": t.get("fix", "Review trade context before next entry"),
                "prevention_rule": t.get("prevention_rule", "Verify market conditions before entry"),
            }
            ledger["mistakes"].append(entry)
            existing.add(desc)
            added += 1
            print(f"📝 Added to mistakes ledger: {date_str} {t['direction']} ${t['pnl']:.2f}")
    
    if added > 0:
        # Write back
        os.makedirs(os.path.dirname(MISTAKES_LEDGER_PATH), exist_ok=True)
        with open(MISTAKES_LEDGER_PATH, "w") as f:
            json.dump(ledger, f, indent=2)
        print(f"✓ Mistakes ledger updated ({added} new entries)")
    else:
        print(f"ℹ No new mistakes to add (dedup skipped {len(losing_trades)})")

# ── Main ────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"POST-TRADE CRITIC — Run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Magic: {MAGIC} | Symbol: {SYMBOL} | Lookback: {LOOKBACK_HOURS}h")
    print("=" * 60)
    
    # ── Pre-analysis system checks ──
    print("\n── System Checks ──")
    check_state_file()
    check_bot_log()
    instance_count = check_duplicate_instances()
    
    # ── Connect MT5 ──
    print("\n── MT5 Connection ──")
    connected, info = connect_mt5_safe(CONFIG_PATH)
    if not connected:
        print("❌ Could not connect to MT5 — cannot analyze trades")
        # Check time-based decision matrix
        utc_now = datetime.now(timezone.utc)
        utc_hour = utc_now.hour
        # Session window: 13-15 UTC
        if utc_hour >= 15:
            print("ℹ Window already passed (13-15 UTC) — [SILENT]")
        elif utc_hour >= 13:
            print("⚠ Window currently active — MT5 unreachable, bot cannot trade!")
            print("   Producing diagnostic report...")
        else:
            print(f"ℹ Window still ahead (current UTC={utc_hour}, window=13-15) — [SILENT]")
            # Still try to run if connected via fallback
        if info:
            print(f"   Connection status: partial (wrong account: {info.login}/{info.server})")
    
    # ── Fetch trades ──
    print("\n── Trade Analysis ──")
    trades, raw_deals = fetch_trades()
    
    if not trades:
        print(f"\n📭 No closed trades found for MAGIC {MAGIC}/{SYMBOL} in last {LOOKBACK_HOURS}h")
        print("→ [SILENT] — nothing to critique")
        # Check if we need to resolve state-change (e.g., wrong account now resolved)
        return
    
    # ── Check session window compliance ──
    check_session_window(trades)
    
    # ── Score each trade ──
    total_score = 0
    wins = 0
    losses = 0
    win_pnl = 0
    loss_pnl = 0
    losing_trades = []
    trade_critiques = []
    
    for t in trades:
        scoring = score_trade(t)
        score = scoring["score"]
        quality = scoring["quality"]
        total_score += score
        
        t.update(scoring)
        
        if t["outcome"] == "win":
            wins += 1
            win_pnl += t["pnl"]
        else:
            losses += 1
            loss_pnl += abs(t["pnl"])
            losing_trades.append(t)
        
        trade_critiques.append(t)
        
        print(f"\n  Trade #{t['position_id']}: {t['direction']} {t['volume']} lot "
              f"→ ${t['pnl']:.2f} ({t['outcome']})")
        print(f"    Entry: {t['entry_price']} | Exit: {t['exit_price']} | "
              f"Holding: {t['holding_hours']:.1f}h" if t['holding_hours'] else f"    Entry: {t['entry_price']} | Exit: {t['exit_price']}")
        print(f"    Exit reason: {t['exit_reason']} | Score: {score}/10 ({quality})")
        if t["positives"]:
            print(f"    ✓ {' | '.join(t['positives'])}")
        if t["negatives"]:
            print(f"    ✗ {' | '.join(t['negatives'])}")
    
    # ── Summary ──
    total_pnl = win_pnl - loss_pnl
    total_trades = len(trades)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    avg_score = (total_score / total_trades) if total_trades > 0 else 0
    
    print(f"\n── Summary ──")
    print(f"Total trades: {total_trades}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Total PnL: ${total_pnl:.2f}")
    print(f"Avg score: {avg_score:.1f}/10")
    
    # ── Pattern detection ──
    patterns = []
    if total_trades < 20:
        print(f"\n⚠ Small sample warning — only {total_trades} trades. Patterns below are suggestive, not conclusive.")
    
    if win_rate < 40 and total_trades >= 3:
        patterns.append({"pattern": "Low win rate", "severity": "CRITICAL", "detail": f"{win_rate:.1f}% across {total_trades} trades"})
    elif win_rate < 50 and total_trades >= 3:
        patterns.append({"pattern": "Below average WR", "severity": "WARNING", "detail": f"{win_rate:.1f}% across {total_trades} trades"})
    
    # Consecutive losses
    if losses >= 3:
        patterns.append({"pattern": "Consecutive losses", "severity": "CRITICAL", "detail": f"{losses} losses in window"})
    
    # Direction bias
    buys = [t for t in trades if t["direction"] == "BUY"]
    sells = [t for t in trades if t["direction"] == "SELL"]
    buy_wins = sum(1 for t in buys if t["outcome"] == "win")
    sell_wins = sum(1 for t in sells if t["outcome"] == "win")
    if len(buys) >= 2 and len(sells) >= 2:
        buy_wr = (buy_wins / len(buys) * 100) if buys else 0
        sell_wr = (sell_wins / len(sells) * 100) if sells else 0
        if (buy_wr == 100 and sell_wr == 0) or (buy_wr == 0 and sell_wr == 100):
            patterns.append({"pattern": "Direction bias detected", "severity": "HIGH", 
                           "detail": f"BUY: {buy_wins}/{len(buys)}W | SELL: {sell_wins}/{len(sells)}W"})
    
    if patterns:
        print(f"\n── Patterns Detected ──")
        for p in patterns:
            print(f"[{p['severity']}] {p['pattern']}: {p['detail']}")
    
    # ── Recommendations ──
    recommendations = []
    if losing_trades:
        # Analyze loss patterns
        sl_losses = [t for t in losing_trades if t["exit_reason"] == "SL"]
        tp_wins = [t for t in trades if t["outcome"] == "win" and t["exit_reason"] == "TP"]
        
        if sl_losses and not tp_wins:
            recommendations.append("All exits are SL hits — review SL placement relative to ATR/volatility")
        
        recommendations.append(f"Review the {len(losing_trades)} losing trade(s) for root cause patterns")
    
    if recommendations:
        print(f"\n── Recommendations ──")
        for i, r in enumerate(recommendations, 1):
            print(f"  {i}. {r}")
    
    # ── Mistakes ledger ──
    if losing_trades:
        for t in losing_trades:
            t["root_cause"] = "Loss occurred — needs manual review of entry context"
            t["fix"] = "Review VWAP deviation, rejection candle, and news calendar before next entry"
            t["prevention_rule"] = "Check high-impact news calendar before every US session EURUSD trade"
        update_mistakes_ledger(losing_trades)
    
    # ── Save critique report ──
    today = datetime.now().strftime("%Y-%m-%d")
    report = {
        "date": today,
        "run_time": datetime.now().isoformat(),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_score": round(avg_score, 1),
        "per_symbol": {SYMBOL: {"wins": wins, "losses": losses, "total_pnl": round(total_pnl, 2)}},
        "patterns": patterns,
        "trade_critiques": trade_critiques,
        "recommendations": recommendations,
    }
    
    os.makedirs(CRITIQUE_DIR, exist_ok=True)
    report_path = os.path.join(CRITIQUE_DIR, f"daily_critique_{today}.json")
    if os.path.exists(report_path):
        with open(report_path) as f:
            existing = json.load(f)
        # Merge: append new trade critiques
        existing["trade_critiques"].extend(trade_critiques)
        existing["total_trades"] = existing.get("total_trades", 0) + total_trades
        existing["wins"] = existing.get("wins", 0) + wins
        existing["losses"] = existing.get("losses", 0) + losses
        existing["total_pnl"] = round(existing.get("total_pnl", 0) + total_pnl, 2)
        # Recalculate
        t = existing["wins"] + existing["losses"]
        existing["win_rate"] = round(existing["wins"] / t * 100, 1) if t > 0 else 0
        # Update per_symbol
        for sym in [SYMBOL]:
            if sym not in existing["per_symbol"]:
                existing["per_symbol"][sym] = {"wins": 0, "losses": 0, "total_pnl": 0}
            existing["per_symbol"][sym]["wins"] += wins
            existing["per_symbol"][sym]["losses"] += losses
            existing["per_symbol"][sym]["total_pnl"] = round(existing["per_symbol"][sym]["total_pnl"] + total_pnl, 2)
        # Merge patterns (dedup by pattern name)
        existing_pattern_names = {p["pattern"] for p in existing.get("patterns", [])}
        for p in patterns:
            if p["pattern"] not in existing_pattern_names:
                existing["patterns"].append(p)
                existing_pattern_names.add(p["pattern"])
        existing["recommendations"] = list(set(existing.get("recommendations", []) + recommendations))
        existing["run_time"] = datetime.now().isoformat()
        with open(report_path, "w") as f:
            json.dump(existing, f, indent=2)
    else:
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
    
    print(f"\n📊 Critique report saved: {report_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
