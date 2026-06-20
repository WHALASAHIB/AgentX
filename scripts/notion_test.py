import urllib.request, json, os

token = os.environ.get("NOTION_TOKEN", "")

# Test basic connection
req = urllib.request.Request(
    'https://api.notion.com/v1/users/me',
    headers={'Authorization': f'Bearer {token}', 'Notion-Version': '2022-06-28'}
)
try:
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    print(f"✅ Bot: {resp.get('name', '?')}")
except Exception as e:
    print(f"❌ Auth error: {e}")

# Try database with UUID format (with dashes)
db_id = '383c5525-4d39-4809-9093-efc530a37913'
req2 = urllib.request.Request(
    f'https://api.notion.com/v1/databases/{db_id}',
    headers={'Authorization': f'Bearer {token}', 'Notion-Version': '2022-06-28'}
)
try:
    resp2 = json.loads(urllib.request.urlopen(req2, timeout=10).read())
    print(f"✅ Database: {resp2.get('title',[{}])[0].get('plain_text','?')}")
    print(f"Properties: {list(resp2.get('properties',{}).keys())}")
except Exception as e:
    print(f"❌ Database error: {e}")

# Try without dashes
db_id2 = '383c5525d394809093efc530a3791394'
req3 = urllib.request.Request(
    f'https://api.notion.com/v1/databases/{db_id2}',
    headers={'Authorization': f'Bearer {token}', 'Notion-Version': '2022-06-28'}
)
try:
    resp3 = json.loads(urllib.request.urlopen(req3, timeout=10).read())
    print(f"✅ DB (no dashes): {resp3.get('title',[{}])[0].get('plain_text','?')}")
except Exception as e:
    print(f"❌ DB (no dashes) error: {e}")
