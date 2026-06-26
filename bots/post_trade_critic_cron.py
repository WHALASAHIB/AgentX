#!/usr/bin/env python3
"""
Post-Trade Critic Agent — Cron Run for Propfirm Pass Strategy v8 (magic 780012).
Connects to MT5, fetches closed trades in last 2h for EURUSD, analyzes them,
produces critique report and updates mistakes_ledger if losing trades found.
"""
import json
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

import MetaTrader5 as mt5

# ── Config ──────────────────────────────────────────────────────────────────
MAGIC = 780012
SYMBOL = "EURUSD"
LOOKBACK_HOURS = 2

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
CONFIG_PATH = os.path.join(PROJECT_DIR, "mt5_config.json")
LEDGER_PATH = os.path.join(PROJECT_DIR, "strategy_council", "mistakes_ledger.json")
CRITIQUE_DIR = os.path.join(SCRIPT_DIR, "analytics")

os.makedirs(CRITIQUE_DIR, exist_ok=True)

with open(CONFIG_PATH) as f:
    config = json.load(f)

account = config["accounts"][0]  # ftmo-demo
login = account["login"]
password = account["password"]
server = account["server"]


def evaluate_trade(trade):
    """Score a closed trade 1-10 and return critique + recommendations."""
    score = 5  # start neutral
    positives = []
    negatives = []
    root_cause = None
    fix = None
    prevention_rule = None

    pnl = trade["pnl"]
    net_pnl = pnl

    price_entry = trade["price_open"]
    price_close = trade["price_close"]
    volume = trade["volume"]
    direction = trade["direction"]

    time_open = trade["time_open"]
    time_close = trade["time_close"]
    holding_seconds = (time_close - time_open).total_seconds()
    holding_hours = holding_seconds / 3600

    sl = trade.get("sl", 0)
    tp = trade.get("tp", 0)

    # ── P&L score ──
    if net_pnl > 0:
        positives.append(f"Winning trade: +${net_pnl:.2f}")
        score += 2
        if net_pnl > 15:
            score += 1
    else:
        negatives.append(f"Losing trade: ${net_pnl:.2f}")
        score -= 2
        if net_pnl < -15:
            score -= 1

    # ── Holding time ──
    if holding_hours < 1:
        positives.append(f"Quick trade ({holding_hours:.1f}h)")
        score += 1
    elif holding_hours > 6:
        negatives.append(f"Extended holding ({holding_hours:.1f}h)")
        score -= 1

    # ── Volume analysis ──
    if volume > 0.3:
        negatives.append(f"Large volume ({volume} lots)")
        score -= 1
    elif volume <= 0.1 and volume > 0:
        positives.append(f"Conservative sizing ({volume} lots)")
        score += 1

    # ── R:R estimate ──
    if sl and tp and price_entry:
        if direction == "BUY":
            risk = price_entry - sl
            reward = tp - price_entry
        else:
            risk = sl - price_entry
            reward = price_entry - tp
        if risk > 0 and reward > 0:
            rr = reward / risk
            if rr >= 1.5:
                positives.append(f"Good R:R ({rr:.2f})")
                score += 1
            elif rr < 1.0:
                negatives.append(f"Poor R:R ({rr:.2f})")
                score -= 1

    # ── Determine outcome type ──
    if net_pnl > 0:
        outcome = "win"
    else:
        outcome = "loss"
        if holding_hours < 1:
            root_cause = "Early stop-out — price reversed sharply after entry"
            fix = "Widen SL or check for news catalyst before entry"
            prevention_rule = "Check high-impact news calendar before every US session trade"
        elif holding_hours > 4:
            root_cause = "Extended drawdown — trade held too long against position"
            fix = "Set tighter time-based exit (max 4h hold or trailing SL)"
            prevention_rule = "Maximum 4-hour holding time for EURUSD US session trades"
        else:
            root_cause = "Trend reversal during trade — VWAP deviation signal faded"
            fix = "Require stronger confirmation: 2nd rejection candle or higher timeframe trend alignment"
            prevention_rule = "Only enter when H1 trend matches VWAP deviation direction"

    # Clamp score
    score = max(1, min(10, score))

    if score >= 8:
        quality = "good"
    elif score >= 5:
        quality = "acceptable"
    elif score >= 3:
        quality = "poor"
    else:
        quality = "error"

    return {
        "ticket": trade["ticket"],
        "symbol": SYMBOL,
        "direction": direction,
        "entry_price": round(price_entry, 5),
        "exit_price": round(price_close, 5),
        "volume": volume,
        "pnl": round(net_pnl, 2),
        "open_time": time_open.isoformat(),
        "close_time": time_close.isoformat(),
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
    """Detect patterns across all trades in the window."""
    patterns = []
    total = len(critiques)
    if total == 0:
        return patterns, 0, 0

    wins = [c for c in critiques if c["outcome"] == "win"]
    losses = [c for c in critiques if c["outcome"] == "loss"]
    win_rate = (len(wins) / total) * 100 if total > 0 else 0

    if win_rate < 40:
        patterns.append({
            "pattern": "Low win rate",
            "severity": "CRITICAL",
            "detail": f"{win_rate:.1f}% win rate across {total} trades"
        })
    elif win_rate < 50:
        patterns.append({
            "pattern": "Below average win rate",
            "severity": "WARNING",
            "detail": f"{win_rate:.1f}% win rate across {total} trades"
        })

    cons_losses = 0
    max_cons_losses = 0
    for c in critiques:
        if c["outcome"] == "loss":
            cons_losses += 1
            max_cons_losses = max(max_cons_losses, cons_losses)
        else:
            cons_losses = 0
    if max_cons_losses >= 3:
        patterns.append({
            "pattern": "Consecutive losses",
            "severity": "CRITICAL",
            "detail": f"{max_cons_losses} losses in a row"
        })

    avg_score = sum(c["score"] for c in critiques) / total if total > 0 else 0
    return patterns, win_rate, avg_score


def log_mistake(critique):
    """Append a losing trade to the mistakes ledger."""
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
        ledger = json.load(f)
        ledger["mistakes"].append(entry)
        f.seek(0)
        json.dump(ledger, f, indent=2)
        f.truncate()
    return entry


def main():
    print(f"=== Post-Trade Critic — Propfirm Pass v8 (Magic {MAGIC}, {SYMBOL}) ===")
    now_local = datetime.now()
    print(f"Time: {now_local.isoformat()}")
    print(f"Lookback: {LOOKBACK_HOURS}h\n")

    # ── Connect to MT5 ──────────────────────────────────────────────────
    print("[1/4] Connecting to MT5...")
    if not mt5.initialize(login=login, password=password, server=server):
        print(f"ERROR: MT5 initialize failed: {mt5.last_error()}")
        sys.exit(1)
    print(f"  Connected: MT5 version {mt5.version()}")

    # ── Fetch closed trades ─────────────────────────────────────────────
    print(f"\n[2/4] Fetching closed trades for {SYMBOL} (magic={MAGIC})...")
    now = datetime.now()
    from_time = now - timedelta(hours=LOOKBACK_HOURS)

    # Get history deals by time range
    deals = mt5.history_deals_get(from_time, now)
    if deals is None:
        print(f"  No deals found: {mt5.last_error()}")
        mt5.shutdown()
        print("\nNo trades — staying silent.")
        return

    # Filter by symbol and magic
    relevant = []
    for d in deals:
        d_dict = d._asdict()
        if d_dict.get("symbol") == SYMBOL and d_dict.get("magic") == MAGIC:
            relevant.append(d_dict)

    print(f"  Found {len(relevant)} deals matching {SYMBOL}/magic {MAGIC}")

    if not relevant:
        mt5.shutdown()
        print("\nNo trades — staying silent.")
        return

    # Group by position_id to get full trades (entry + exit)
    position_deals = defaultdict(list)
    for d in relevant:
        pid = d.get("position_id", 0)
        if pid == 0:
            pid = d.get("order", 0)
        position_deals[pid].append(d)

    combined_trades = []
    for pid, pdeals in position_deals.items():
        # Sort by time
        pdeals.sort(key=lambda x: x.get("time", 0))

        # Determine direction from first deal
        entry_deal = pdeals[0]
        exit_deal = pdeals[-1]
        entry_type = entry_deal.get("type", 0)
        # MT5 deal types: 0=BUY, 1=SELL
        direction = "BUY" if entry_type in (0,) else "SELL"

        entry_price = entry_deal.get("price", 0)
        # For exit, find the opposite direction deal
        exit_price = exit_deal.get("price", entry_price)

        volume = entry_deal.get("volume", 0)
        total_profit = sum(d.get("profit", 0) for d in pdeals)
        total_commission = sum(d.get("commission", 0) for d in pdeals)
        total_swap = sum(d.get("swap", 0) for d in pdeals)

        time_open = datetime.fromtimestamp(entry_deal.get("time", 0))
        time_close = datetime.fromtimestamp(exit_deal.get("time", 0))

        # Get order info for SL/TP if available
        order = mt5.history_orders_get(ticket=pid)
        sl_price = 0
        tp_price = 0
        if order:
            o = order[0]
            sl_price = o.sl if o.sl else 0
            tp_price = o.tp if o.tp else 0

        trade = {
            "ticket": pid,
            "direction": direction,
            "price_open": entry_price,
            "price_close": exit_price,
            "volume": volume,
            "pnl": total_profit + total_commission + total_swap,
            "sl": sl_price,
            "tp": tp_price,
            "time_open": time_open,
            "time_close": time_close,
        }
        combined_trades.append(trade)

    total_pnl = sum(t["pnl"] for t in combined_trades)
    print(f"  Total P&L: ${total_pnl:.2f}")
    print(f"  Unique trades (position-based): {len(combined_trades)}")

    # ── Analyze each trade ─────────────────────────────────────────────
    print(f"\n[3/4] Analyzing {len(combined_trades)} trades...")
    critiques = []
    wins = []
    losses = []

    for trade in combined_trades:
        critique = evaluate_trade(trade)
        critiques.append(critique)

        emoji = "✅" if critique["outcome"] == "win" else "❌"
        print(f"  Ticket #{critique['ticket']} | {critique['direction']} | "
              f"P&L: ${critique['pnl']:.2f} | Score: {critique['score']}/10 ({critique['quality']}) | {emoji}")
        for p in critique["positives"]:
            print(f"    + {p}")
        for n in critique["negatives"]:
            print(f"    - {n}")

        if critique["outcome"] == "win":
            wins.append(critique)
        else:
            losses.append(critique)

    # ── Pattern detection ──────────────────────────────────────────────
    patterns, win_rate, avg_score = detect_patterns(critiques)
    print(f"\n[4/5] Pattern detection:")
    print(f"  Win rate: {win_rate:.1f}% ({len(wins)}W / {len(losses)}L)")
    print(f"  Avg score: {avg_score:.1f}/10")
    if patterns:
        for p in patterns:
            print(f"  [{p['severity']}] {p['pattern']}: {p['detail']}")
    else:
        print("  No concerning patterns detected.")

    # ── Handle losses: log to ledger ───────────────────────────────────
    if losses:
        print(f"\n[5/5] Logging {len(losses)} loss(es) to mistakes_ledger.json...")
        for loss in losses:
            entry = log_mistake(loss)
            print(f"  → {loss['direction']} @ {loss['entry_price']} | "
                  f"P&L: ${loss['pnl']:.2f} | Root: {loss['root_cause'][:60]}...")
            print(f"    Fix: {loss['fix']}")
            print(f"    Prevention: {loss['prevention_rule']}")

    # ── Handle wins: log what went right ───────────────────────────────
    if wins:
        print(f"\n  {len(wins)} winning trade(s):")
        for w in wins:
            print(f"  ✅ {w['direction']} @ {w['entry_price']} | "
                  f"P&L: ${w['pnl']:.2f} | Score: {w['score']}/10")
            for p in w["positives"]:
                print(f"    ✓ {p}")

    # ── Build daily critique report ────────────────────────────────────
    report_date = now_local.strftime("%Y-%m-%d")
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
        "recommendations": [],
    }

    if patterns:
        for p in patterns:
            if p["severity"] == "CRITICAL":
                report["recommendations"].append(f"ADDRESS: {p['pattern']} — {p['detail']}")
    if losses:
        report["recommendations"].append(
            "Check high-impact news calendar before entering US session EURUSD trades."
        )
        if any(l.get("root_cause") and "stop-out" in (l["root_cause"] or "").lower() for l in losses):
            report["recommendations"].append(
                "Consider widening SL by 2-3 pips or adding ATR-based dynamic SL."
            )

    report_path = os.path.join(CRITIQUE_DIR, f"daily_critique_{report_date}.json")
    with open(report_path, "w") as f:
        # Convert datetime objects to strings
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return super().default(obj)
        json.dump(report, f, indent=2, cls=DateTimeEncoder)
    print(f"\n  Report saved: {report_path}")

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"CRITIQUE SUMMARY — {report_date}")
    print(f"{'='*60}")
    print(f"  Trades:     {len(critiques)} ({'✅' if win_rate >= 50 else '⚠️'} {win_rate:.1f}% WR)")
    print(f"  P&L:        ${total_pnl:.2f}")
    print(f"  Avg Score:  {avg_score:.1f}/10")
    print(f"  Patterns:   {len(patterns)}")
    print(f"  Losses:     {len(losses)}")
    if report["recommendations"]:
        print(f"\n  RECOMMENDATIONS:")
        for i, r in enumerate(report["recommendations"], 1):
            print(f"    {i}. {r}")
    print(f"{'='*60}")

    mt5.shutdown()
    print("\n=== Critique complete ===")


if __name__ == "__main__":
    main()
