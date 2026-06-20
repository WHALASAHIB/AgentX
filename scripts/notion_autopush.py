#!/usr/bin/env python3
"""
AGENTX — Notion Auto-Push Script
Polls MT5 bridge for new closed trades and pushes them to Notion Trade Log.
Links trades to the appropriate Monthly Performance entry.
Runs every 10 minutes via cron.
"""

import urllib.request, json, os, sys, time
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
MT5_BRIDGE = "http://localhost:5000"
ACCOUNT_ID = "default"

# Notion DBs
TRADE_LOG_DB = "383c5525-d394-8122-94f9-df8d64bb80ff"
MONTHLY_DB = "383c5525-d394-81c4-bd63-dce9890e18e5"

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "notion_push_state.json")

# ── Strategy Mapping ──────────────────────────────────────────────────────────
def resolve_strategy(trade):
    """Extract strategy name from trade comment/magic."""
    comment = (trade.get("comment") or "").strip().upper()
    magic = trade.get("magic", 0)
    
    # Direct comment-based mapping
    comment_map = {
        "MSB_MACD": "MACD Crossover",
        "MSB_SMA": "SMA Crossover",
        "MSB_GOLDPHOENIX": "Gold Phoenix",
        "MSB_BB": "Bollinger Bands",
        "GOLDV3_MTF": "Gold v3 MTF",
        "SRBV2_XAU": "SRB v2 XAU",
        "SRB_XAU": "SRB XAU",
        "SCALPV3_YTB": "Scalp v3",
        "STREAM_M1": "M1 Stream",
        "AGENTX": "AgentX Core",
    }
    if comment in comment_map:
        return comment_map[comment]
    
    # Magic-based mapping (fallback)
    if 780001 <= magic <= 780008:
        return "MACD Crossover"
    elif magic == 777555:
        return "SRB v2 XAU"
    elif magic == 777556:
        return "Gold v3 MTF"
    elif magic == 888222:
        return "M1 Stream"
    elif magic == 999111:
        return "Scalp v3"
    elif magic == 123456:
        return "AgentX Core"
    
    return "Unknown"

def resolve_direction(trade):
    t = (trade.get("type") or "").upper()
    if "BUY" in t:
        return "Buy"
    if "SELL" in t:
        return "Sell"
    return "Buy"  # default

def resolve_result(trade):
    profit = trade.get("net_profit", trade.get("profit", 0))
    if profit > 0:
        return "Win"
    return "Loss"

def is_valid_trade(trade):
    """Filter out deposits/withdrawals and invalid entries."""
    pos_id = trade.get("position_id", 0)
    volume = trade.get("volume", 0)
    symbol = trade.get("symbol", "")
    
    # Skip deposits/withdrawals (position_id=0, volume=0, no symbol)
    if pos_id == 0 and volume == 0 and not symbol:
        return False
    return True

# ── API Helpers ───────────────────────────────────────────────────────────────
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
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        print(f"  NOTION ERROR {method} {path}: {body.get('message','?')[:200]}")
        return None
    except Exception as e:
        print(f"  NOTION EXCEPTION {method} {path}: {e}")
        return None

def mt5_api(path):
    """Call MT5 Bridge API — always use /api/v1/ prefix."""
    # Ensure path has /api/v1/ prefix
    if not path.startswith("/api/v1/"):
        if path.startswith("/"):
            path = "/api/v1" + path
        else:
            path = "/api/v1/" + path
    req = urllib.request.Request(f"{MT5_BRIDGE}{path}")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  MT5 ERROR {path}: {e}")
        return None

# ── State Management ──────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"last_position_id": 0, "pushed_ids": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ── Month Management ──────────────────────────────────────────────────────────
def get_or_create_month(date_str):
    """Find or create a Monthly Performance entry for the given date."""
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.split("T")[0])
        else:
            dt = datetime.strptime(date_str.split(" ")[0], "%Y-%m-%d")
    except:
        dt = datetime.now()
    
    month_key = dt.strftime("%Y-%m")
    month_label = dt.strftime("%B %Y")
    
    # Search existing months
    query = notion_api("POST", f"/databases/{MONTHLY_DB}/query", {
        "filter": {
            "property": "Month",
            "title": {"contains": month_label}
        }
    })
    
    if query and query.get("results"):
        return query["results"][0]["id"]
    
    # Create new month entry
    new_month = notion_api("POST", "/pages", {
        "parent": {"database_id": MONTHLY_DB},
        "properties": {
            "Month": {"title": [{"text": {"content": f"{month_label} (Auto)"}}]},
            "Total Trades": {"number": 0},
            "Net P&L": {"number": 0},
            "Win Rate": {"number": 0},
        }
    })
    
    if new_month:
        print(f"  📁 Created month: {month_label}")
        return new_month["id"]
    return None

# ── Push Trade to Notion ──────────────────────────────────────────────────────
def push_trade(trade, month_id):
    """Push a single trade to Notion Trade Log."""
    pos_id = trade.get("position_id", 0)
    symbol = trade.get("symbol", "?")
    direction = resolve_direction(trade)
    strategy = resolve_strategy(trade)
    result = resolve_result(trade)
    
    close_time_raw = trade.get("close_time", "")
    try:
        close_dt = datetime.strptime(close_time_raw, "%Y-%m-%d %H:%M")
        close_date = close_dt.strftime("%Y-%m-%d")
    except:
        close_date = datetime.now().strftime("%Y-%m-%d")
    
    entry_price = trade.get("entry_price", 0)
    exit_price = trade.get("exit_price", 0)
    volume = trade.get("volume", 0)
    net_profit = trade.get("net_profit", trade.get("profit", 0))
    
    trade_name = f"#{pos_id}: {symbol} {direction} ({strategy})"
    
    page = notion_api("POST", "/pages", {
        "parent": {"database_id": TRADE_LOG_DB},
        "properties": {
            "Trade": {"title": [{"text": {"content": trade_name[:200]}}]},
            "Date": {"date": {"start": close_date}},
            "Pair": {"select": {"name": symbol}},
            "Strategy": {"select": {"name": strategy}},
            "Direction": {"select": {"name": direction}},
            "Entry Price": {"number": entry_price},
            "Exit Price": {"number": exit_price},
            "Volume": {"number": volume},
            "P&L": {"number": round(net_profit, 2)},
            "Result": {"select": {"name": result}},
            "Notes": {"rich_text": [{"text": {"content": f"Auto-pushed from MT5. Magic: {trade.get('magic',0)} Comment: {trade.get('comment','')}"}}]},
            "Month": {"relation": [{"id": month_id}]},
        }
    })
    
    if page:
        print(f"  ✅ #{pos_id}: {symbol} {direction} ${net_profit:+,.2f} ({strategy})")
        return True
    return False

# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    import sys
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Notion Auto-Push starting...", flush=True)
    
    state = load_state()
    last_id = state.get("last_position_id", 0)
    pushed_ids = set(state.get("pushed_ids", []))
    
    # Fetch trade history (last 7 days to be safe)
    print(f"  Fetching trades from MT5 bridge (last_id={last_id})...", flush=True)
    trades = mt5_api(f"/api/v1/accounts/{ACCOUNT_ID}/history?days=7")
    if not trades:
        print("  ❌ Could not fetch trades from MT5 bridge", flush=True)
        return
    print(f"  ✅ Got {len(trades)} trades from bridge", flush=True)
    
    # Filter valid trades (skip deposits/withdrawals)
    valid_trades = [t for t in trades if is_valid_trade(t)]
    
    # Get max position_id
    max_pos_id = max((t.get("position_id", 0) for t in valid_trades), default=0)
    
    # Fresh start: skip all historical trades, just set baseline
    if last_id == 0 and not pushed_ids:
        state["last_position_id"] = max_pos_id
        state["pushed_ids"] = [max_pos_id] if max_pos_id > 0 else []
        save_state(state)
        print(f"  📋 First run — set baseline position_id to {max_pos_id}. No trades pushed.", flush=True)
        return
    
    # If last_id is 0 but we have a pushed list from partial state
    if last_id == 0 and pushed_ids:
        last_id = max_pos_id
    
    # Find new trades (position_id > last_id)
    new_trades = [t for t in valid_trades if t.get("position_id", 0) > last_id and t.get("position_id") not in pushed_ids]
    
    if not new_trades:
        # Silent exit — no new trades, nothing to report
        return
    
    # Sort by position_id ascending
    new_trades.sort(key=lambda t: t.get("position_id", 0))
    
    print(f"  📊 Found {len(new_trades)} new trade(s) to push")
    
    pushed_count = 0
    max_id = last_id
    
    for trade in new_trades:
        pos_id = trade.get("position_id", 0)
        close_time = trade.get("close_time", "")
        
        # Get or create month page
        month_id = get_or_create_month(close_time)
        if not month_id:
            print(f"  ⚠️  Could not get/create month for trade #{pos_id}, skipping")
            continue
        
        # Push to Notion
        if push_trade(trade, month_id):
            pushed_ids.add(pos_id)
            pushed_count += 1
            if pos_id > max_id:
                max_id = pos_id
    
    # Update state
    state["last_position_id"] = max_id
    state["pushed_ids"] = list(pushed_ids)
    if len(state["pushed_ids"]) > 1000:
        state["pushed_ids"] = state["pushed_ids"][-1000:]
    save_state(state)
    
    print(f"  ✅ Pushed {pushed_count} trade(s). Last position ID: {max_id}")

if __name__ == "__main__":
    main()
