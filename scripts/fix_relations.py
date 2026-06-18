import urllib.request, json

TOKEN = "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"
D1 = "383c5525-d394-81c4-bd63-dce9890e18e5"
D2 = "383c5525-d394-8122-94f9-df8d64bb80ff"
D3 = "383c5525-d394-819b-a7d4-cbe5e95d02e2"
D4 = "383c5525-d394-810f-bfc3-e49ff8218606"

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
        return json.loads(e.read())

# Add relations
r1 = api("PATCH", f"/databases/{D2}", {"properties": {
    "Month": {"relation": {"database_id": D1, "type": "single_property", "single_property": {}}}
}})
print("DB2->DB1:", r1.get("object", "error"))

r2 = api("PATCH", f"/databases/{D1}", {"properties": {
    "Trades": {"relation": {"database_id": D2, "type": "single_property", "single_property": {}}}
}})
print("DB1->DB2:", r2.get("object", "error"))

r3 = api("PATCH", f"/databases/{D4}", {"properties": {
    "Related Strategy": {"relation": {"database_id": D3, "type": "single_property", "single_property": {}}}
}})
print("DB4->DB3:", r3.get("object", "error"))
print("Done!")
