import urllib.request, json, re, os

SCRIPTS_DIR = 'C:/Trading/scripts'
with open(os.path.join(SCRIPTS_DIR, 'create_notion.py')) as f:
    src = f.read()

m = re.search(r'TOKEN\s*=\s*"([^"]+)"', src)
TOKEN_v=m.group(1)

headers = {"Authorization": "Bearer " + TOKEN_v, "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

# Query Trade Log
req = urllib.request.Request(
    "https://api.notion.com/v1/databases/383c5525-d394-8122-94f9-df8d64bb80ff/query",
    data=b'{}', method="POST", headers=headers)
r = json.loads(urllib.request.urlopen(req, timeout=10).read())
pages = r.get("results", [])
print(f"Trade Log: {len(pages)} entries\n")

for p in list(reversed(pages))[:8]:
    props = p.get("properties", {})
    name = ""
    pnl = 0
    result = ""
    for k, v in props.items():
        if v.get("type") == "title":
            parts = v.get("title", [])
            name = "".join(pt.get("plain_text", "") for pt in parts)
        if k == "P&L":
            pnl = v.get("number", 0) or 0
        if k == "Result":
            rs = v.get("select")
            if rs:
                result = rs.get("name", "")
    print(f"  {name[:55]:55s} ${pnl:>+8.2f} {result}")

print(f"\nTotal: {len(pages)} entries")
