#!/usr/bin/env python3
"""
Post-Trade Critic — Cron Run (self-contained)
Analyzes closed MT5 trades for Propfirm Pass v8 (magic 780012, EURUSD, last 2h)
"""
import json
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict
import MetaTrader5 as mt5

# ── Paths ──────────────────────────────────────────────────────────────────
CONFIG_PATH = r"C:\Trading\mt5_config.json"
LEDGER_PATH = r"C:\Trading\strategy_council\mistakes_ledger.json"
CRITIQUE_DIR = r"C:\Trading\bots\analytics"
os.makedirs(CRITIQUE_DIR, exist_ok=True)

MAGIC = 780012
SYMBOL = "EURUSD"
LOOKBACK_HOURS = 2

def load_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    # Try accounts array first, then top-level fields
    if "accounts" in cfg and len(cfg["accounts"]) > 0:
        account = cfg["accounts"][0]
        return account["login"], account["password"], account["server"]
    else:
        return cfg.get("login"), cfg.get("password"), cfg.get("server")

def evaluate_trade(trade):
    """Score a closed trade 1-10. Returns critique dict."""
    score = 5
    positives, negatives = [], []
    pnl = trade["pnl"]
    price_entry = trade["price_open"]
    price_close = trade["price_close"]
    volume = trade["volume"]
    direction = trade["direction"]
    holding_hours = (trade["time_close"] - trade["time_open"]).total_seconds() / 3600

    # P&L
    if pnl > 0:
        positives.append(f"Winning trade: +${pnl:.2f}")
        score += 2 + (1 if pnl > 15 else 0)
    else:
        negatives.append(f"Losing trade: ${pnl:.2f}")
        score -= 2 + (1 if pnl < -15 else 0)

    # Holding time
    if holding_hours < 1:
        positives.append(f"Quick trade ({holding_hours:.1f}h)")
        score += 1
    elif holding_hours > 6:
        negatives.append(f"Extended holding ({holding_hours:.1f}h)")
        score -= 1

    # Volume
    if volume > 0.3:
        negatives.append(f"Large volume ({volume} lots)")
        score -= 1
    elif volume <= 0.1:
        positives.append(f"Conservative sizing ({volume} lots)")
        score += 1

    # R:R (if SL/TP available)
    sl, tp = trade.get("sl", 0), trade.get("tp", 0)
    if sl and tp and price_entry:
        risk = (price_entry - sl) if direction == "BUY" else (sl - price_entry)
        reward = (tp - price_entry) if direction == "BUY" else (price_entry - tp)
        if risk > 0 and reward > 0:
            rr = reward / risk
            if rr >= 1.5:
                positives.append(f"Good R:R ({rr:.2f})")
                score += 1
            elif rr < 1.0:
                negatives.append(f"Poor R:R ({rr:.2f})")
                score -= 1

    outcome = "win" if pnl > 0 else "loss"
    root_cause, fix, prevention_rule = None, None, None
    if outcome == "loss":
        if holding_hours < 0.5:
            root_cause = "Early stop-out — price rejected entry signal within minutes"
            fix = "Widen SL buffer or wait for stronger candle confirmation before entry"
            prevention_rule = "Do NOT enter on first rejection candle alone — confirm with momentum or higher TF alignment"
        elif holding_hours < 1:
            root_cause = "Premature exit — price stopped out before intraday recovery"
            fix = "Add ATR-based SL buffer (1.5x ATR) instead of fixed pip SL"
            prevention_rule = "Set SL at 1.5x ATR below entry, not fixed pip distance"
        elif holding_hours > 4:
            root_cause = "Extended drawdown — trade held too long against position"
            fix = "Set tighter time-based exit (max 4h hold with trailing SL at breakeven after 1h)"
            prevention_rule = "Maximum 4-hour holding time for EURUSD session trades, trail SL to breakeven after 1h"
        else:
            root_cause = "Trend reversal during trade — signal faded by broader market move"
            fix = "Require H1 trend filter aligning with entry direction before taking signal"
            prevention_rule = "Only enter EURUSD when H1 20-EMA trend direction matches signal direction"

    score = max(1, min(10, score))
    quality_map = [(8, "good"), (5, "acceptable"), (3, "poor")]
    quality = "error"
    for threshold, label in sorted(quality_map, reverse=True):
        if score >= threshold:
            quality = label
            break

    return {
        "ticket": trade["ticket"],
        "symbol": SYMBOL,
        "direction": direction,
        "entry_price": round(price_entry, 5),
        "exit_price": round(price_close, 5),
        "volume": volume,
        "pnl": round(pnl, 2),
        "open_time": trade["time_open"].isoformat(),
        "close_time": trade["time_close"].isoformat(),
        "holding_hours": round(holding_hours, 2),
        "score": score,
        "quality": quality,
        "outcome": outcome,
        "positives": positives,
        "negatives": negatives,
        "root_cause": root_cause,
        "fix": fix,
        "prevention_rule": prevention_rule,
    }


def detect_patterns(critiques):
    patterns = []
    total = len(critiques)
    if total == 0:
        return patterns, 0, 0
    wins = [c for c in critiques if c["outcome"] == "win"]
    losses = [c for c in critiques if c["outcome"] == "loss"]
    win_rate = len(wins) / total * 100

    if win_rate < 40:
        patterns.append({"pattern": "Low win rate", "severity": "CRITICAL",
                         "detail": f"{win_rate:.1f}% win rate across {total} trades"})
    elif win_rate < 50:
        patterns.append({"pattern": "Below average win rate", "severity": "WARNING",
                         "detail": f"{win_rate:.1f}% win rate across {total} trades"})

    cons, max_cons = 0, 0
    for c in critiques:
        cons = (cons + 1) if c["outcome"] == "loss" else 0
        max_cons = max(max_cons, cons)
    if max_cons >= 3:
        patterns.append({"pattern": "Consecutive losses", "severity": "CRITICAL",
                         "detail": f"{max_cons} losses in a row"})

    avg_score = sum(c["score"] for c in critiques) / total if total > 0 else 0
    return patterns, win_rate, avg_score


def log_mistake(critique):
    """Append losing trade to mistakes_ledger.json. Returns the entry."""
    entry = {
        "date": critique["close_time"][:10],
        "direction": critique["direction"],
        "entry": critique["entry_price"],
        "exit": critique["exit_price"],
        "pnl": critique["pnl"],
        "root_cause": critique["root_cause"],
        "fix": critique["fix"],
        "prevention_rule": critique["prevention_rule"],
    }
    with open(LEDGER_PATH, "r+") as f:
        try:
            ledger = json.load(f)
        except json.JSONDecodeError:
            ledger = {"strategy": "Propfirm Pass v8", "mistakes": [], "lessons_learned": []}
        ledger["mistakes"].append(entry)
        f.seek(0)
        json.dump(ledger, f, indent=2)
        f.truncate()
    return entry


def main():
    print(f"=== Post-Trade Critic — Magic {MAGIC}, {SYMBOL}, last {LOOKBACK_HOURS}h ===")
    print(f"Run time: {datetime.now().isoformat()}")

    login, password, server = load_config()

    # ── Connect ────────────────────────────────────────────────────────
    print("\n[1] Connecting to MT5...")
    if not mt5.initialize(login=login, password=password, server=server):
        err = mt5.last_error()
        print(f"ERROR: initialize failed — {err}")
        # Try bare init then login
        print("  Trying bare initialize() + login()...")
        if not mt5.initialize():
            err2 = mt5.last_error()
            print(f"ERROR: bare initialize failed — {err2}")
            mt5.shutdown()
            sys.exit(1)
        if not mt5.login(login=login, password=password, server=server):
            err3 = mt5.last_error()
            print(f"ERROR: login failed — {err3}")
            mt5.shutdown()
            sys.exit(1)
        print(f"  Connected (fallback method): version {mt5.version()}")
    else:
        print(f"  Connected: version {mt5.version()}")

    # ── Check account info ────────────────────────────────────────────
    info = mt5.account_info()
    if info:
        print(f"  Account: {info.login}@{info.server} | Balance: ${info.balance:.2f}")
        # Verify against config
        cfg_login = int(login) if isinstance(login, str) else login
        cfg_server = str(server)
        if info.login != cfg_login or info.server != cfg_server:
            print(f"  ⚠️ WARNING: Connected to {info.login}/{info.server}, expected {cfg_login}/{cfg_server}")
    else:
        print(f"  No account info available")

    # ── Fetch deals ────────────────────────────────────────────────────
    print(f"\n[2] Fetching closed trades (lookback: {LOOKBACK_HOURS}h)...")
    now = datetime.now()  # timezone-naive — MT5 requirement
    from_time = now - timedelta(hours=LOOKBACK_HOURS)
    print(f"  Timerange: {from_time.isoformat()} → {now.isoformat()}")

    deals = mt5.history_deals_get(from_time, now)

    if deals is None:
        err = mt5.last_error()
        if err[0] == 1:  # Success = no deals
            deals = []
            print(f"  No deals in timerange (last_error={err})")
        else:
            print(f"ERROR: history_deals_get returned None, last_error={err}")
            mt5.shutdown()
            sys.exit(1)

    # Filter to our magic + symbol
    relevant = []
    for d in deals:
        d = d._asdict()
        if d.get("symbol") == SYMBOL and d.get("magic") == MAGIC:
            relevant.append(d)

    print(f"  Total deals: {len(deals)} | Matching {SYMBOL}/M{MAGIC}: {len(relevant)}")

    if not relevant:
        mt5.shutdown()
        print("\nNo trades found in window. Staying silent.")
        print("[SILENT]")
        return

    # ── Group by position_id into trades ───────────────────────────────
    pos_deals = defaultdict(list)
    for d in relevant:
        pid = d.get("position_id", d.get("order", 0))
        pos_deals[pid].append(d)

    trades = []
    for pid, pdeals in pos_deals.items():
        pdeals.sort(key=lambda x: x.get("time", 0))
        entry_d, exit_d = pdeals[0], pdeals[-1]

        # Determine direction from deal type (0=BUY, 1=SELL)
        entry_type = entry_d.get("entry", 0)
        deal_type = entry_d.get("type", 0)
        if deal_type == 0:
            direction = "BUY"
        elif deal_type == 1:
            direction = "SELL"
        else:
            direction = "BUY" if entry_type == 0 else "SELL"

        # Try to get order for SL/TP info
        sl = tp = 0
        try:
            order_info = mt5.history_orders_get(position=pid)
            if order_info and len(order_info) > 0:
                sl = order_info[0].sl or 0
                tp = order_info[0].tp or 0
        except Exception as e:
            print(f"  Warning: could not fetch order for position {pid}: {e}")

        # Compute P&L
        total_pnl = sum(
            d.get("profit", 0) + d.get("commission", 0) + d.get("swap", 0)
            for d in pdeals
        )

        trade = {
            "ticket": pid,
            "direction": direction,
            "price_open": entry_d.get("price", 0),
            "price_close": exit_d.get("price", 0),
            "volume": entry_d.get("volume", 0),
            "sl": sl,
            "tp": tp,
            "pnl": total_pnl,
            "time_open": datetime.fromtimestamp(entry_d.get("time", 0)),
            "time_close": datetime.fromtimestamp(exit_d.get("time", 0)),
        }
        trades.append(trade)

    total_pnl = sum(t["pnl"] for t in trades)
    print(f"  Positions reconstructed: {len(trades)}, Total P&L: ${total_pnl:.2f}")

    # ── Analyze ────────────────────────────────────────────────────────
    print(f"\n[3] Analyzing {len(trades)} trades...")
    critiques = [evaluate_trade(t) for t in trades]
    wins = [c for c in critiques if c["outcome"] == "win"]
    losses = [c for c in critiques if c["outcome"] == "loss"]

    for c in critiques:
        emoji = "✅" if c["outcome"] == "win" else "❌"
        print(f"  #{c['ticket']} {c['direction']} @ {c['entry_price']} → {c['exit_price']} "
              f"P&L:${c['pnl']:.2f} Score:{c['score']}/10 {emoji}")
        for p in c["positives"]:
            print(f"    + {p}")
        for n in c["negatives"]:
            print(f"    - {n}")
        if c["root_cause"]:
            print(f"    → Root cause: {c['root_cause']}")
        if c["fix"]:
            print(f"    → Fix: {c['fix']}")
        if c["prevention_rule"]:
            print(f"    → Prevention: {c['prevention_rule']}")

    # ── Pattern detection ──────────────────────────────────────────────
    patterns, win_rate, avg_score = detect_patterns(critiques)
    print(f"\n[4] Patterns: {len(patterns)} detected | WR: {win_rate:.1f}% | Avg Score: {avg_score:.1f}/10")
    for p in patterns:
        print(f"  [{p['severity']}] {p['pattern']}: {p['detail']}")

    # ── Log losses to mistakes ledger ─────────────────────────────────
    if losses:
        print(f"\n[5] Logging {len(losses)} loss(es) to mistakes ledger...")
        for l in losses:
            entry = log_mistake(l)
            print(f"  → {entry['direction']} @ {entry['entry']} | ${entry['pnl']:.2f} | {entry['root_cause'][:60]}")

    if wins:
        print(f"\n  {len(wins)} win(s) documented:")
        for w in wins:
            print(f"  ✅ {w['direction']} @ {w['entry_price']} | ${w['pnl']:.2f} | Score: {w['score']}/10")
            print(f"     Positives: {'; '.join(w['positives'])}")

    # ── Save daily critique report ─────────────────────────────────────
    report_date = now.strftime("%Y-%m-%d")
    recommendations = []
    if patterns:
        for p in patterns:
            if p["severity"] == "CRITICAL":
                recommendations.append(f"ADDRESS: {p['pattern']} — {p['detail']}")

    report = {
        "date": report_date,
        "run_time": datetime.now().isoformat(),
        "total_trades": len(critiques),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_score": round(avg_score, 1),
        "per_symbol": {
            SYMBOL: {
                "wins": len(wins),
                "losses": len(losses),
                "total_pnl": round(total_pnl, 2),
            }
        },
        "patterns": patterns,
        "trade_critiques": critiques,
        "recommendations": recommendations,
    }

    report_path = os.path.join(CRITIQUE_DIR, f"daily_critique_{report_date}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[6] Report saved: {report_path}")

    # ── Terminal summary ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"SUMMARY — {report_date} | Propfirm Pass v8 (M{MAGIC}) | {SYMBOL}")
    print(f"{'='*60}")
    print(f"  Trades:   {len(critiques)}")
    print(f"  Wins:     {len(wins)}")
    print(f"  Losses:   {len(losses)}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Total P&L: ${total_pnl:.2f}")
    print(f"  Avg Score: {avg_score:.1f}/10")
    if recommendations:
        print(f"  Recommendations:")
        for i, r in enumerate(recommendations, 1):
            print(f"    {i}. {r}")
    print(f"{'='*60}")

    mt5.shutdown()
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
