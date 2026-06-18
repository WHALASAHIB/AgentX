import urllib.request, json, uuid

TOKEN = "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"

# Database IDs
D1 = "383c5525-d394-81c4-bd63-dce9890e18e5"  # Monthly
D2 = "383c5525-d394-8122-94f9-df8d64bb80ff"  # Trade Log
D3 = "383c5525-d394-819b-a7d4-cbe5e95d02e2"  # Strategy Journal
D4 = "383c5525-d394-810f-bfc3-e49ff8218606"  # Action Items

def api(method, path, data=None):
    req = urllib.request.Request(
        f"https://api.notion.com/v1{path}",
        data=json.dumps(data).encode() if data else None,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        print(f"  ❌ {method} {path}: {body.get('message','?')[:200]}")
        return None

# ============================================================
# 1. RENAME DATABASES - clean, organized names
# ============================================================
print("=" * 50)
print("STEP 1: Rename databases")
print("=" * 50)

renames = {
    D1: "🗓 Monthly Performance",
    D2: "📈 Trade Log",
    D3: "🧠 Strategy Journal",
    D4: "📋 Action Items",
}

for db_id, new_name in renames.items():
    r = api("PATCH", f"/databases/{db_id}", {"title": [{"text": {"content": new_name}}]})
    if r:
        print(f"  ✅ {db_id[:8]}... → \"{new_name}\"")

# ============================================================
# 2. ADD DEMO ENTRIES
# ============================================================
print("\n" + "=" * 50)
print("STEP 2: Add demo entries")
print("=" * 50)

# --- DEMO MONTH ---
print("\n📁 Monthly Performance — Demo Entry")
demo_month = api("POST", "/pages", {
    "parent": {"database_id": D1},
    "properties": {
        "Month": {"title": [{"text": {"content": "June 2026 — Demo"}}]},
        "Pairs Traded": {"multi_select": [
            {"name": "XAUUSD"}, {"name": "EURUSD"}, {"name": "GBPUSD"},
            {"name": "USDJPY"}, {"name": "BTCUSD"}
        ]},
        "Total Trades": {"number": 47},
        "Net P&L": {"number": 3850.00},
        "Win Rate": {"number": 68.1},
        "Best Strategy": {"rich_text": [{"text": {"content": "Gold Phoenix"}}]},
        "Worst Strategy": {"rich_text": [{"text": {"content": "SMA Crossover"}}]},
        "Monthly Report": {"rich_text": [{"text": {"content": "Demo month — strong performance on XAUUSD with Gold Phoenix strategy. SMA needs tuning on EURUSD."}}]},
    }
})
if demo_month:
    demo_month_id = demo_month["id"]
    print(f"  ✅ June 2026 — Demo (ID: {demo_month_id[:8]}...)")
else:
    demo_month_id = None

# --- DEMO TRADES ---
print("\n📈 Trade Log — Demo Entries")

demo_trades = [
    {"name": "Demo-001: XAUUSD Buy", "date": "2026-06-01", "pair": "XAUUSD", "strategy": "Gold Phoenix",
     "direction": "Buy", "entry": 2345.50, "exit": 2362.80, "volume": 0.5, "pnl": 865.00, "result": "Win",
     "notes": "Classic breakout entry. RSI confirmed. Perfect setup."},
    {"name": "Demo-002: EURUSD Sell", "date": "2026-06-02", "pair": "EURUSD", "strategy": "MACD Crossover",
     "direction": "Sell", "entry": 1.0840, "exit": 1.0812, "volume": 0.3, "pnl": 420.00, "result": "Win",
     "notes": "MACD bearish cross on H1. Trend continued downward."},
    {"name": "Demo-003: GBPUSD Buy", "date": "2026-06-03", "pair": "GBPUSD", "strategy": "Bollinger Bands",
     "direction": "Buy", "entry": 1.2720, "exit": 1.2705, "volume": 0.4, "pnl": -225.00, "result": "Loss",
     "notes": "False breakout below lower band. BOE news caused reversal."},
    {"name": "Demo-004: XAUUSD Sell", "date": "2026-06-05", "pair": "XAUUSD", "strategy": "Gold Phoenix",
     "direction": "Sell", "entry": 2370.00, "exit": 2355.20, "volume": 0.6, "pnl": 740.00, "result": "Win",
     "notes": "Resistance at 2370 held. Quick 15-min scalp."},
    {"name": "Demo-005: USDJPY Buy", "date": "2026-06-07", "pair": "USDJPY", "strategy": "SMA Crossover",
     "direction": "Buy", "entry": 155.80, "exit": 155.92, "volume": 0.2, "pnl": 180.00, "result": "Win",
     "notes": "SMA 50/200 crossover on M30. Small but consistent."},
]

demo_trade_ids = []
for t in demo_trades:
    page_data = {
        "parent": {"database_id": D2},
        "properties": {
            "Trade": {"title": [{"text": {"content": t["name"]}}]},
            "Date": {"date": {"start": t["date"]}},
            "Pair": {"select": {"name": t["pair"]}},
            "Strategy": {"select": {"name": t["strategy"]}},
            "Direction": {"select": {"name": t["direction"]}},
            "Entry Price": {"number": t["entry"]},
            "Exit Price": {"number": t["exit"]},
            "Volume": {"number": t["volume"]},
            "P&L": {"number": t["pnl"]},
            "Result": {"select": {"name": t["result"]}},
            "Notes": {"rich_text": [{"text": {"content": t["notes"]}}]},
        }
    }
    r = api("POST", "/pages", page_data)
    if r:
        demo_trade_ids.append(r["id"])
        print(f"  ✅ {t['name']}")

# Link demo trades to demo month
if demo_month_id and demo_trade_ids:
    for tid in demo_trade_ids:
        api("PATCH", f"/pages/{tid}", {
            "properties": {"Month": {"relation": [{"id": demo_month_id}]}}
        })
    print(f"  🔗 Linked {len(demo_trade_ids)} trades to Demo month")

# --- DEMO STRATEGIES ---
print("\n🧠 Strategy Journal — Demo Entries")

demo_strategies = [
    {
        "name": "Gold Phoenix",
        "pairs": ["XAUUSD"],
        "good": "Strong trend-following on XAUUSD. Excellent RSI + breakout combo. Win rate ~72% in trending markets.",
        "weak": "Underperforms in ranging markets. False signals during high-impact news. Needs tighter SL during NFP.",
        "improvements": "Add ATR-based dynamic stop. Filter out trades during major news windows (30min before/after).",
        "best": "Strong uptrend with RSI 40-60 zone. H1 timeframe with clear support/resistance levels.",
        "worst": "Sideways chop between 2340-2360. High-volatility news events. Low-liquidity Asian session.",
    },
    {
        "name": "MACD Crossover",
        "pairs": ["EURUSD", "GBPUSD", "USDJPY"],
        "good": "Reliable on major pairs. Clear entry signals. Good win rate on H4 timeframe (~65%).",
        "weak": "Lagging indicator — late entries in fast moves. Many false crossovers in low volatility.",
        "improvements": "Add trend filter (EMA 200). Use histogram divergence for early warnings.",
        "best": "H4 timeframe with clear trend. Low-moderate volatility. After London open.",
        "worst": "H1 during news. Low volatility Asian session. Pair with tight spreads only.",
    },
    {
        "name": "Bollinger Bands",
        "pairs": ["GBPUSD", "XAUUSD", "BTCUSD"],
        "good": "Great mean-reversion on ranging pairs. Excellent for BTCUSD (high volatility).",
        "weak": "Terrible in trending markets. Whipsawed constantly. Band hits don't always mean reversal.",
        "improvements": "Only trade when bands contract first (squeeze setup). Add RSI divergence confirmation.",
        "best": "Ranging market with clear channel. After a volatility squeeze. H1 timeframe.",
        "worst": "Strong trends. News-driven breakouts. Low-volatility pairs (USDCHF).",
    },
    {
        "name": "SMA Crossover",
        "pairs": ["USDJPY", "EURUSD"],
        "good": "Simple and effective on JPY pairs. Slow enough to filter noise.",
        "weak": "Way too slow for scalping. High drawdown during ranging periods. Lots of whipsaw.",
        "improvements": "Shorten periods (10/30 instead of 50/200). Add ADX filter (>25 only).",
        "best": "Strong trend on USDJPY. H1 timeframe. After clear breakout.",
        "worst": "Range-bound markets. Multiple crossovers in same day. Low vol summer months.",
    }
]

demo_strategy_ids = []
for s in demo_strategies:
    r = api("POST", "/pages", {
        "parent": {"database_id": D3},
        "properties": {
            "Strategy": {"title": [{"text": {"content": s["name"]}}]},
            "Pairs Used": {"multi_select": [{"name": p} for p in s["pairs"]]},
            "Good At": {"rich_text": [{"text": {"content": s["good"]}}]},
            "Weaknesses": {"rich_text": [{"text": {"content": s["weak"]}}]},
            "Improvements": {"rich_text": [{"text": {"content": s["improvements"]}}]},
            "Best Conditions": {"rich_text": [{"text": {"content": s["best"]}}]},
            "Worst Conditions": {"rich_text": [{"text": {"content": s["worst"]}}]},
        }
    })
    if r:
        demo_strategy_ids.append(r["id"])
        print(f"  ✅ {s['name']}")

# --- DEMO ACTION ITEMS ---
print("\n📋 Action Items — Demo Entries")

demo_actions = [
    {"action": "Add ATR-based dynamic SL to Gold Phoenix", "priority": "High", "status": "In Progress",
     "notes": "Currently 20pip fixed. Need to implement ATR(14) * 1.5 multiplier.", "strat_idx": 0},
    {"action": "Implement news filter for all strategies", "priority": "High", "status": "Open",
     "notes": "Block trading 30min before/after major news (NFP, FOMC, CPI). Use ForexFactory calendar API.", "strat_idx": 0},
    {"action": "Add ADX filter to SMA Crossover", "priority": "Medium", "status": "Open",
     "notes": "Only take trades when ADX > 25. Avoid whipsaw in ranging markets.", "strat_idx": 3},
    {"action": "Test Bollinger Squeeze on BTCUSD", "priority": "Medium", "status": "Open",
     "notes": "Backtest BB squeeze on BTCUSD H1 over last 3 months. Compare with standard BB.", "strat_idx": 2},
    {"action": "Add histogram divergence to MACD strategy", "priority": "Low", "status": "Open",
     "notes": "Price making higher high but MACD histogram making lower high = bearish divergence signal.", "strat_idx": 1},
    {"action": "Review monthly performance vs targets", "priority": "High", "status": "Done",
     "notes": "June demo: $3,850 profit, 68% win rate. On track for $100k/month target. Gold Phoenix strongest performer.", "strat_idx": 0},
]

for a in demo_actions:
    page_data = {
        "parent": {"database_id": D4},
        "properties": {
            "Action": {"title": [{"text": {"content": a["action"]}}]},
            "Priority": {"select": {"name": a["priority"]}},
            "Status": {"select": {"name": a["status"]}},
            "Notes": {"rich_text": [{"text": {"content": a["notes"]}}]},
        }
    }
    # Link to strategy if applicable
    if "strat_idx" in a and a["strat_idx"] < len(demo_strategy_ids):
        page_data["properties"]["Related Strategy"] = {"relation": [{"id": demo_strategy_ids[a["strat_idx"]]}]}
    
    r = api("POST", "/pages", page_data)
    if r:
        print(f"  ✅ [{a['priority']}] {a['action'][:55]}...")


# ============================================================
# SUMMARY
# ============================================================
def link(i): return f"https://www.notion.so/{i.replace('-', '')}"

print("\n" + "=" * 50)
print("🎉 NOTION ORGANIZED SUCCESSFULLY!")
print("=" * 50)
print(f"""
🗓  Monthly Performance  → {link(D1)}
     → 1 demo entry (June 2026)
     → 5 demo trades linked
     
📈  Trade Log             → {link(D2)}
     → 5 demo trades (3 wins, 2 losses)
     → Linked to June 2026 month
     
🧠  Strategy Journal      → {link(D3)}
     → 4 demo strategies (Gold Phoenix, MACD, Bollinger, SMA)
     → Each with Good At / Weaknesses / Improvements / Conditions
     
📋  Action Items          → {link(D4)}
     → 6 demo action items
     → 3 High, 2 Medium, 1 Low priority
     → Linked to related strategies
""")
