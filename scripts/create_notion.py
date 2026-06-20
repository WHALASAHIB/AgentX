import urllib.request, json, os

TOKEN = os.environ.get("NOTION_TOKEN", "")
PARENT_DB = "383c5525-d394-8090-93ef-c530a3791394"

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
        body = e.read().decode()
        print(f"  ERROR {method} {path}: {body[:300]}")
        return None

# 1. Create parent page
print("Creating parent page...")
parent = api("POST", "/pages", {
    "parent": {"database_id": PARENT_DB},
    "properties": {"Name": {"title": [{"text": {"content": "AGENTX Trading System"}}]}},
    "icon": {"type": "emoji", "emoji": "🤖"}
})
if not parent: exit(1)
pid = parent["id"]
print(f"  ✅ {pid}")

# 2. DB1 - Monthly (no relations yet)
print("\nCreating DB1 Monthly Performance...")
db1 = api("POST", "/databases", {
    "parent": {"type": "page_id", "page_id": pid},
    "icon": {"type": "emoji", "emoji": "📁"},
    "title": [{"text": {"content": "📁 Monthly Performance"}}],
    "properties": {
        "Month": {"title": {}},
        "Pairs Traded": {"multi_select": {}},
        "Total Trades": {"number": {"format": "number"}},
        "Net P&L": {"number": {"format": "dollar"}},
        "Win Rate": {"number": {"format": "percent"}},
        "Best Strategy": {"rich_text": {}},
        "Worst Strategy": {"rich_text": {}},
        "Monthly Report": {"rich_text": {}},
    }
})
if not db1: exit(1)
d1 = db1["id"]
print(f"  ✅ {d1}")

# 3. DB2 - Trade Log (no relations yet)
print("\nCreating DB2 Trade Log...")
db2 = api("POST", "/databases", {
    "parent": {"type": "page_id", "page_id": pid},
    "icon": {"type": "emoji", "emoji": "📊"},
    "title": [{"text": {"content": "📊 Trade Log"}}],
    "properties": {
        "Trade": {"title": {}},
        "Date": {"date": {}},
        "Pair": {"select": {"options": [
            {"name": "XAUUSD","color": "yellow"},{"name": "EURUSD","color": "blue"},
            {"name": "GBPUSD","color": "purple"},{"name": "USDJPY","color": "red"},
            {"name": "USDCHF","color": "green"},{"name": "USDCAD","color": "orange"},
            {"name":"AUDUSD","color":"pink"},{"name":"NZDUSD","color":"gray"},{"name":"BTCUSD","color":"brown"}
        ]}},
        "Strategy": {"select": {"options": [
            {"name":"MACD Crossover","color":"blue"},{"name":"Gold Phoenix","color":"yellow"},
            {"name":"SMA Crossover","color":"green"},{"name":"Bollinger Bands","color":"purple"}
        ]}},
        "Direction": {"select": {"options": [{"name":"Buy","color":"green"},{"name":"Sell","color":"red"}]}},
        "Entry Price": {"number": {"format": "number"}},
        "Exit Price": {"number": {"format": "number"}},
        "Volume": {"number": {"format": "number"}},
        "P&L": {"number": {"format": "dollar"}},
        "Result": {"select": {"options": [{"name":"Win","color":"green"},{"name":"Loss","color":"red"}]}},
        "Notes": {"rich_text": {}},
    }
})
if not db2: exit(1)
d2 = db2["id"]
print(f"  ✅ {d2}")

# 4. DB3 - Strategy Journal
print("\nCreating DB3 Strategy Journal...")
db3 = api("POST", "/databases", {
    "parent": {"type": "page_id", "page_id": pid},
    "icon": {"type": "emoji", "emoji": "🧠"},
    "title": [{"text": {"content": "🧠 Strategy Journal"}}],
    "properties": {
        "Strategy": {"title": {}},
        "Pairs Used": {"multi_select": {}},
        "Good At": {"rich_text": {}},
        "Weaknesses": {"rich_text": {}},
        "Improvements": {"rich_text": {}},
        "Best Conditions": {"rich_text": {}},
        "Worst Conditions": {"rich_text": {}},
    }
})
if not db3: exit(1)
d3 = db3["id"]
print(f"  ✅ {d3}")

# 5. DB4 - Action Items
print("\nCreating DB4 Action Items...")
db4 = api("POST", "/databases", {
    "parent": {"type": "page_id", "page_id": pid},
    "icon": {"type": "emoji", "emoji": "📌"},
    "title": [{"text": {"content": "📌 Action Items"}}],
    "properties": {
        "Action": {"title": {}},
        "Priority": {"select": {"options": [{"name":"High","color":"red"},{"name":"Medium","color":"yellow"},{"name":"Low","color":"green"}]}},
        "Status": {"select": {"options": [{"name":"Open","color":"gray"},{"name":"In Progress","color":"blue"},{"name":"Done","color":"green"}]}},
        "Notes": {"rich_text": {}},
    }
})
if not db4: exit(1)
d4 = db4["id"]
print(f"  ✅ {d4}")

# 6. Now add relations via PATCH
print("\nAdding relations...")

# DB1 <-> DB2 (Month <-> Trades)
api("PATCH", f"/databases/{d1}", {"properties": {
    "Trades": {"relation": {"database_id": d2}}
}})
print("  DB1 -> DB2 ✅")

api("PATCH", f"/databases/{d2}", {"properties": {
    "Month": {"relation": {"database_id": d1}}
}})
print("  DB2 -> DB1 ✅")

# DB3 -> DB4 (Strategy -> Actions)
api("PATCH", f"/databases/{d4}", {"properties": {
    "Related Strategy": {"relation": {"database_id": d3}}
}})
print("  DB4 -> DB3 ✅")

def link(i): return f"https://www.notion.so/{i.replace('-', '')}"

print(f"""
{'='*50}
🎉 ALL 4 DATABASES CREATED!
{'='*50}

📁 Monthly Performance → {link(d1)}
📊 Trade Log          → {link(d2)}  
🧠 Strategy Journal   → {link(d3)}
📌 Action Items       → {link(d4)}

Relations: DB1↔DB2 ✅ | DB3↔DB4 ✅
""")
