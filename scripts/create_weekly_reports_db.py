import urllib.request, json, os, sys
from datetime import datetime, timezone, timedelta

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
        body = json.loads(e.read())
        print(f"  ERROR {method} {path}: {body.get('message','?')[:200]}")
        return None

# Find parent page
print("Finding parent page...")
search = api("POST", "/search", {
    "query": "AGENTX Trading System",
    "filter": {"value": "page", "property": "object"}
})
pid = None
for r in search.get("results", []):
    if r.get("object") == "page":
        pid = r["id"]
        print(f"  Found parent: {pid}")
        break

if not pid:
    print("  Creating parent page...")
    parent = api("POST", "/pages", {
        "parent": {"database_id": PARENT_DB},
        "properties": {"Name": {"title": [{"text": {"content": "AGENTX Trading System"}}]}},
        "icon": {"type": "emoji", "emoji": "🤖"}
    })
    if not parent:
        print("  FAILED to create parent page!")
        sys.exit(1)
    pid = parent["id"]
    print(f"  Created: {pid}")

# Create Weekly Reports database
print("\nCreating Weekly Reports database...")
db = api("POST", "/databases", {
    "parent": {"type": "page_id", "page_id": pid},
    "icon": {"type": "emoji", "emoji": "📊"},
    "title": [{"text": {"content": "📊 Weekly Reports"}}],
    "properties": {
        "Week": {"title": {}},
        "Date Range": {"date": {}},
        "Total Trades": {"number": {"format": "number"}},
        "Wins": {"number": {"format": "number"}},
        "Losses": {"number": {"format": "number"}},
        "Win Rate": {"number": {"format": "percent"}},
        "Net P&L": {"number": {"format": "dollar"}},
        "Gross Profit": {"number": {"format": "dollar"}},
        "Gross Loss": {"number": {"format": "dollar"}},
        "Profit Factor": {"number": {"format": "number"}},
        "Best Trade": {"number": {"format": "dollar"}},
        "Worst Trade": {"number": {"format": "dollar"}},
        "Account Balance": {"number": {"format": "dollar"}},
        "Top Strategy": {"rich_text": {}},
        "Bottom Strategy": {"rich_text": {}},
        "Performance by Strategy": {"rich_text": {}},
        "Best Pair": {"rich_text": {}},
        "Worst Pair": {"rich_text": {}},
        "Executive Summary": {"rich_text": {}},
        "Action Items": {"rich_text": {}},
        "Status": {"select": {"options": [
            {"name": "✅ Good", "color": "green"},
            {"name": "⚠️ Needs Attention", "color": "yellow"},
            {"name": "❌ Critical", "color": "red"},
        ]}},
    }
})

if db:
    print(f"  ✅ Weekly Reports created: {db['id']}")
    print(f"  https://www.notion.so/{db['id'].replace('-','')}")
else:
    print("  ❌ Failed!")
