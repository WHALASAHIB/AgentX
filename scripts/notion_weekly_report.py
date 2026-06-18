#!/usr/bin/env python3
"""
AGENTX — Weekly CEO Report Generator
Queries all Notion databases + MT5 bridge and creates a comprehensive weekly report.
Runs every Monday at 9am HKT via cron.
Creates a new page in the Weekly Reports database.
"""

import urllib.request, json, os, sys
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
NOTION_TOKEN="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"
MT5_BRIDGE = "http://localhost:5000"
ACCOUNT_ID = "default"

# Notion DBs
WEEKLY_REPORTS_DB = "383c5525-d394-81be-b265-d330ad85d9c3"
TRADE_LOG_DB = "383c5525-d394-8122-94f9-df8d64bb80ff"
MONTHLY_DB = "383c5525-d394-81c4-bd63-dce9890e18e5"
STRATEGY_DB = "383c5525-d394-819b-a7d4-cbe5e95d02e2"
ACTION_DB = "383c5525-d394-810f-bfc3-e49ff8218606"

# ── Helpers ───────────────────────────────────────────────────────────────────
def notion_api(method, path, data=None):
    req = urllib.request.Request(
        f"https://api.notion.com/v1{path}",
        data=json.dumps(data).encode() if data else None,
        method=method,
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as e:
        print(f"NOTION ERROR: {e}")
        return None

def mt5_api(path):
    req = urllib.request.Request(f"{MT5_BRIDGE}{path}")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception as e:
        print(f"MT5 ERROR: {e}")
        return None

def query_database(db_id, filter_dict=None):
    results = []
    body = {}
    if filter_dict:
        body["filter"] = filter_dict
    body["page_size"] = 100
    
    start_cursor = None
    while True:
        if start_cursor:
            body["start_cursor"] = start_cursor
        r = notion_api("POST", f"/databases/{db_id}/query", body)
        if not r:
            break
        results.extend(r.get("results", []))
        if r.get("has_more"):
            start_cursor = r.get("next_cursor")
        else:
            break
    return results

def get_text(prop):
    if not prop: return ""
    t = prop.get("type")
    if t == "title":
        return "".join(p.get("plain_text","") for p in prop.get("title",[]))
    if t == "rich_text":
        return "".join(p.get("plain_text","") for p in prop.get("rich_text",[]))
    return ""

def get_number(prop):
    if not prop: return 0
    return prop.get("number", 0) or 0

def get_select_name(prop):
    if not prop: return ""
    s = prop.get("select")
    return s.get("name","") if s else ""

def is_valid_trade(t):
    """Filter out deposits/withdrawals."""
    if t.get("position_id", 0) == 0 and t.get("volume", 0) == 0 and not t.get("symbol", ""):
        return False
    return True

def resolve_strategy(trade):
    """Strategy mapping from comment/magic."""
    comment = (trade.get("comment") or "").strip().upper()
    magic = trade.get("magic", 0)
    
    cmap = {
        "MSB_MACD": "MACD Crossover", "MSB_SMA": "SMA Crossover",
        "MSB_GOLDPHOENIX": "Gold Phoenix", "MSB_BB": "Bollinger Bands",
        "GOLDV3_MTF": "Gold v3 MTF", "SRBV2_XAU": "SRB v2 XAU",
        "SRB_XAU": "SRB XAU", "SCALPV3_YTB": "Scalp v3",
        "STREAM_M1": "M1 Stream", "AGENTX": "AgentX Core",
    }
    if comment in cmap:
        return cmap[comment]
    if 780001 <= magic <= 780008: return "MACD Crossover"
    if magic == 777555: return "SRB v2 XAU"
    if magic == 777556: return "Gold v3 MTF"
    if magic == 888222: return "M1 Stream"
    if magic == 999111: return "Scalp v3"
    if magic == 123456: return "AgentX Core"
    return "Unknown"

# ── Main Report Generator ─────────────────────────────────────────────────────
def generate_report():
    print(f"📊 AGENTX — Weekly CEO Report Generator")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S HKT')}\n")
    
    # ── 1. Determine current week (HKT) ──
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=6, hours=23, minutes=59)
    week_label = f"Week {monday.isocalendar()[1]}, {monday.strftime('%b %d')} - {sunday.strftime('%b %d, %Y')}"
    print(f"   Period: {week_label}")
    
    # ── 2. Fetch MT5 data ──
    print("\n📡 Fetching MT5 data...")
    account = mt5_api(f"/api/v1/accounts/{ACCOUNT_ID}")
    balance = float(account.get("balance", 0)) if account else 0
    equity = float(account.get("equity", 0)) if account else 0
    prev_balance = float(account.get("balance", 0)) if account else 0  # Will compute from history
    print(f"   Balance: ${balance:,.2f} | Equity: ${equity:,.2f}")
    
    # All trades from last 7 days
    weekly_trades_raw = mt5_api(f"/api/v1/accounts/{ACCOUNT_ID}/history?days=7") or []
    
    # Filter valid trades only
    all_weekly = [t for t in weekly_trades_raw if is_valid_trade(t)]
    
    # Also filter by date range (Monday to Sunday HKT)
    def parse_close_time(t):
        try:
            return datetime.strptime(t.get("close_time",""), "%Y-%m-%d %H:%M")
        except:
            return None
    
    weekly_trades = [t for t in all_weekly if (dt:=parse_close_time(t)) and monday.replace(tzinfo=None) <= dt <= sunday.replace(tzinfo=None)]
    
    print(f"   Valid trades this week: {len(weekly_trades)}")
    
    # ── 3. Calculate metrics ──
    total_trades = len(weekly_trades)
    wins = [t for t in weekly_trades if t.get("net_profit", t.get("profit", 0)) > 0]
    losses = [t for t in weekly_trades if t.get("net_profit", t.get("profit", 0)) <= 0]
    num_wins = len(wins); num_losses = len(losses)
    win_rate = round(num_wins / total_trades * 100, 1) if total_trades > 0 else 0
    
    gross_profit = sum(t.get("net_profit", t.get("profit", 0)) for t in wins)
    gross_loss = abs(sum(t.get("net_profit", t.get("profit", 0)) for t in losses))
    net_pnl = round(gross_profit - gross_loss, 2)
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.99 if gross_profit > 0 else 0)
    
    best_trade = max(weekly_trades, key=lambda t: t.get("net_profit", t.get("profit", 0))) if weekly_trades else None
    worst_trade = min(weekly_trades, key=lambda t: t.get("net_profit", t.get("profit", 0))) if weekly_trades else None
    best_pnl = best_trade.get("net_profit", 0) if best_trade else 0
    worst_pnl = worst_trade.get("net_profit", 0) if worst_trade else 0
    
    # ── 4. Performance by strategy ──
    strat_data = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
    for t in weekly_trades:
        s = resolve_strategy(t)
        pnl = t.get("net_profit", t.get("profit", 0))
        strat_data[s]["trades"] += 1
        strat_data[s]["pnl"] += pnl
        if pnl > 0: strat_data[s]["wins"] += 1
        else: strat_data[s]["losses"] += 1
    
    sorted_strats = sorted(strat_data.items(), key=lambda x: x[1]["pnl"], reverse=True)
    top_strategy = sorted_strats[0][0] if sorted_strats else "N/A"
    bottom_strategy = sorted_strats[-1][0] if len(sorted_strats) > 1 else top_strategy
    
    strat_lines = []
    for name, sd in sorted_strats:
        sr = round(sd["wins"] / sd["trades"] * 100, 1) if sd["trades"] > 0 else 0
        strat_lines.append(f"  • {name}: {sd['trades']} trades | {sd['wins']}W/{sd['losses']}L | {sr}% WR | ${sd['pnl']:+,.2f}")
    strat_perf = "\n".join(strat_lines)
    
    # ── 5. Performance by pair ──
    pair_data = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    for t in weekly_trades:
        p = t.get("symbol", "?")
        pnl = t.get("net_profit", t.get("profit", 0))
        pair_data[p]["trades"] += 1
        pair_data[p]["pnl"] += pnl
        if pnl > 0: pair_data[p]["wins"] += 1
    
    sorted_pairs = sorted(pair_data.items(), key=lambda x: x[1]["pnl"], reverse=True)
    best_pair = sorted_pairs[0][0] if sorted_pairs else "N/A"
    worst_pair = sorted_pairs[-1][0] if len(sorted_pairs) > 1 else best_pair
    
    # ── 6. Fetch action items ──
    print("\n📋 Fetching action items from Notion...")
    actions = query_database(ACTION_DB)
    open_actions = [a for a in actions if get_select_name(a.get("properties",{}).get("Status")) in ("Open", "In Progress")]
    high_priority = [a for a in open_actions if get_select_name(a.get("properties",{}).get("Priority")) == "High"]
    completed_actions = [a for a in actions if get_select_name(a.get("properties",{}).get("Status")) == "Done"]
    
    # ── 7. Fetch strategy insights ──
    print("🧠 Fetching strategy insights...")
    strategies = query_database(STRATEGY_DB)
    
    # ── 8. Determine status ──
    if net_pnl > 0 and win_rate >= 50: status = "✅ Good"
    elif net_pnl > 0: status = "⚠️ Needs Attention"
    else: status = "❌ Critical"
    
    # ── 9. Build executive summary ──
    exec_lines = [
        f"📊 WEEK {monday.isocalendar()[1]} PERFORMANCE SNAPSHOT",
        f"",
        f"Period: {week_label}",
        f"Account Balance: ${balance:,.2f} | Net P&L: ${net_pnl:+,.2f}",
        f"",
    ]
    if net_pnl > 0:
        exec_lines.append(f"✅ POSITIVE WEEK — Generated ${net_pnl:+,.2f} profit across {total_trades} trades.")
    else:
        exec_lines.append(f"⚠️ LOSS WEEK — Lost ${abs(net_pnl):+,.2f} across {total_trades} trades.")
    exec_lines.append(f"Win rate of {win_rate}% with a profit factor of {profit_factor}.")
    
    exec_lines.append(f"")
    exec_lines.append(f"🏆 Top Performer: {top_strategy} (${strat_data[top_strategy]['pnl']:+,.2f})")
    exec_lines.append(f"📉 Worst Performer: {bottom_strategy} (${strat_data[bottom_strategy]['pnl']:+,.2f})")
    exec_lines.append(f"🎯 Best Pair: {best_pair} | ⚠️ Worst Pair: {worst_pair}")
    
    if best_trade:
        exec_lines.append(f"⭐ Best Trade: {best_trade.get('symbol','?')} ${best_pnl:+,.2f}")
    if worst_trade:
        exec_lines.append(f"💀 Worst Trade: {worst_trade.get('symbol','?')} ${worst_pnl:+,.2f}")
    
    exec_lines.append(f"")
    exec_lines.append(f"📈 Total Volume: {total_trades} trades this week")
    
    exec_summary = "\n".join(exec_lines)
    
    # ── 10. Build action items text ──
    action_lines = []
    if high_priority:
        action_lines.append("🔴 HIGH PRIORITY:")
        for a in high_priority:
            action_lines.append(f"  • {get_text(a.get('properties',{}).get('Action'))}")
    med = [a for a in open_actions if get_select_name(a.get('properties',{}).get('Priority')) == 'Medium']
    if med:
        action_lines.append("🟡 MEDIUM PRIORITY:")
        for a in med:
            action_lines.append(f"  • {get_text(a.get('properties',{}).get('Action'))}")
    if not open_actions:
        action_lines.append("  ✅ All action items completed!")
    action_items_text = "\n".join(action_lines) if action_lines else "No pending action items."
    
    # ── 11. Create report page in Notion ──
    print("\n📝 Creating Weekly Report page in Notion...")
    def trunc(t, n=2000): return t[:n] if len(t) > n else t
    
    report = notion_api("POST", "/pages", {
        "parent": {"database_id": WEEKLY_REPORTS_DB},
        "properties": {
            "Week": {"title": [{"text": {"content": week_label}}]},
            "Date Range": {"date": {"start": monday.strftime("%Y-%m-%d"), "end": sunday.strftime("%Y-%m-%d")}},
            "Total Trades": {"number": total_trades},
            "Wins": {"number": num_wins},
            "Losses": {"number": num_losses},
            "Win Rate": {"number": win_rate},
            "Net P&L": {"number": net_pnl},
            "Gross Profit": {"number": round(gross_profit, 2)},
            "Gross Loss": {"number": round(gross_loss, 2)},
            "Profit Factor": {"number": profit_factor},
            "Best Trade": {"number": round(best_pnl, 2)},
            "Worst Trade": {"number": round(worst_pnl, 2)},
            "Account Balance": {"number": round(balance, 2)},
            "Top Strategy": {"rich_text": [{"text": {"content": trunc(top_strategy)}}]},
            "Bottom Strategy": {"rich_text": [{"text": {"content": trunc(bottom_strategy)}}]},
            "Best Pair": {"rich_text": [{"text": {"content": trunc(best_pair)}}]},
            "Worst Pair": {"rich_text": [{"text": {"content": trunc(worst_pair)}}]},
            "Performance by Strategy": {"rich_text": [{"text": {"content": trunc(strat_perf)}}]},
            "Executive Summary": {"rich_text": [{"text": {"content": trunc(exec_summary)}}]},
            "Action Items": {"rich_text": [{"text": {"content": trunc(action_items_text)}}]},
            "Status": {"select": {"name": status}},
        }
    })
    
    report_url = ""
    if report:
        report_url = f"https://www.notion.so/{report['id'].replace('-','')}"
        print(f"  ✅ Report created: {report_url}")
    else:
        print("  ❌ Failed to create report!")
    
    # ── 12. CLI Summary ──
    print(f"""
{'='*60}
📊 AGENTX WEEKLY REPORT — {week_label}
{'='*60}
Status: {status} | Balance: ${balance:,.2f} | Net P&L: ${net_pnl:+,.2f}

📈 PERFORMANCE
  Trades: {total_trades} | Wins: {num_wins} | Losses: {num_losses}
  Win Rate: {win_rate}% | Profit Factor: {profit_factor}
  Best: ${best_pnl:+,.2f} | Worst: ${worst_pnl:+,.2f}

🏆 Top: {top_strategy} | 📉 Bottom: {bottom_strategy}
🎯 Best Pair: {best_pair} | 💀 Worst: {worst_pair}

📌 OPEN ACTIONS: {len(open_actions)} ({len(high_priority)} high priority)
🔗 Full report: {report_url}
{'='*60}
— AGENTX Command Reports
""")
    
    return report_url

if __name__ == "__main__":
    generate_report()
