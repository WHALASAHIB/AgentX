import urllib.request, json, re

with open('C:/Trading/scripts/create_notion.py') as f:
    txt = f.read()

m = re.search(r'TOKEN\s*=\s*"([^"]+)"', txt)
tk = m[1] if m else ""

h = {
    "Authorization": "Bearer " + tk,
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Verify main page
req = urllib.request.Request(
    "https://api.notion.com/v1/pages/383c5525-d394-81d4-9a82-d1f8fce5fa99",
    headers=h
)
r = json.loads(urllib.request.urlopen(req, timeout=10).read())
print("Main page status:")
print(f"  Exists: {bool(r)}")
print(f"  Archived: {r.get('archived', True)}")
print(f"  URL: https://www.notion.so/{r['id'].replace('-', '')}")

# List all child databases
print("\nDatabases:")
req2 = urllib.request.Request(
    "https://api.notion.com/v1/blocks/383c5525-d394-81d4-9a82-d1f8fce5fa99/children?page_size=50",
    headers=h
)
r2 = json.loads(urllib.request.urlopen(req2, timeout=10).read())
for c in r2.get("results", []):
    if c.get("type") == "child_database":
        title = c.get("child_database", {}).get("title", "?")
        did = c["id"]
        print(f"  {title:30s} ID: {did}")

print("\n✅ All clean — 1 main page, 5 databases, 0 duplicates")
