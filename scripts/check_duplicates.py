import urllib.request, json, re

SCRIPTS_DIR = 'C:/Trading/scripts'
with open(SCRIPTS_DIR + '/create_notion.py') as f:
    for raw_line in f:
        if 'TOKEN' in raw_line and 'ntn_' in raw_line:
            a = raw_line.index('"') + 1
            b = raw_line.rindex('"')
            TK=raw_li...k

headers = {"Authorization": "Bearer " + TK, "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

body = json.dumps({
    "query": "AGENTX Trading System",
    "filter": {"value": "page", "property": "object"}
}).encode()
req = urllib.request.Request("https://api.notion.com/v1/search", data=body, method="POST", headers=headers)
r = json.loads(urllib.request.urlopen(req, timeout=10).read())

pages = r.get("results", [])
print(f"Found {len(pages)} AGENTX Trading System page(s):\n")

for page in pages:
    pid = page["id"]
    created = page.get("created_time", "?")[:10]
    icon = page.get("icon", {})
    icon_str = icon.get("emoji", "?") if icon else "?"
    
    child_req = urllib.request.Request(
        "https://api.notion.com/v1/blocks/" + pid + "/children?page_size=50",
        headers=headers)
    children = json.loads(urllib.request.urlopen(child_req, timeout=10).read())
    child_count = len(children.get("results", []))
    db_count = sum(1 for b in children.get("results", []) if b.get("type") == "child_database")
    
    print(f"ID: {pid}")
    print(f"  Icon: {icon_str}  Children: {child_count}  DBs: {db_count}  Created: {created}")
    print(f"  URL: https://www.notion.so/{pid.replace(chr(45), '')}")
    
    for b in children.get("results", []):
        if b.get("type") == "child_database":
            cd = b.get("child_database", {})
            print(f"    Database: {cd.get('title', '?')}")
    print()
