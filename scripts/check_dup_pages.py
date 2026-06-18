import urllib.request, json, re

with open('C:/Trading/scripts/create_notion.py') as f:
    txt = f.read()

m = re.search(r'TOKEN\s*=\s*"([^"]+)"', txt)
if m:
    tk = m[1]
else:
    tk = ""

h = {
    "Authorization": "Bearer " + tk,
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

b = json.dumps({
    "query": "AGENTX Trading System",
    "filter": {"value": "page", "property": "object"}
}).encode()

req = urllib.request.Request(
    "https://api.notion.com/v1/search",
    data=b, method="POST", headers=h
)
r = json.loads(urllib.request.urlopen(req, timeout=10).read())
pages = r.get("results", [])

print(f"Found {len(pages)} AGENTX page(s):\n")

for page in pages:
    pid = page["id"]
    created = page.get("created_time", "?")[:10]
    icon = page.get("icon", {})
    icon_str = icon.get("emoji", "?") if icon else "?"
    
    cr2 = json.loads(urllib.request.urlopen(
        urllib.request.Request(
            "https://api.notion.com/v1/blocks/" + pid + "/children?page_size=50",
            headers=h
        ), timeout=10
    ).read())
    
    child_count = len(cr2.get("results", []))
    db_count = sum(1 for b in cr2.get("results", []) if b.get("type") == "child_database")
    
    print(f"ID: {pid}")
    print(f"  Icon: {icon_str}  Children: {child_count}  DBs: {db_count}  Created: {created}")
    print(f"  URL: https://www.notion.so/{pid.replace('-', '')}")
    
    # Skip the main page (has 5 databases)
    if db_count >= 4:
        print(f"  ✅ MAIN PAGE — keeping this one")
        continue
    
    # Delete empty duplicate pages
    print(f"  🗑️ Deleting duplicate page...")
    del_req = urllib.request.Request(
        "https://api.notion.com/v1/pages/" + pid,
        data=json.dumps({"archived": True}).encode(),
        method="PATCH", headers=h
    )
    del_resp = json.loads(urllib.request.urlopen(del_req, timeout=10).read())
    if del_resp.get("archived"):
        print(f"  ✅ Archived successfully")
    else:
        print(f"  ❌ Failed to archive")
    print()
