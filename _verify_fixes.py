"""Test bot control fixes — uses cookie-based auth"""
import sys, json, subprocess, time, os, http.cookiejar, urllib.request

# Set up cookie handling
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

# Sign in
req = urllib.request.Request(
    "http://127.0.0.1:8008/api/auth/signin",
    data=json.dumps({"email":"whalasahibtrading@gmail.com","password":"Trading123!"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)
with opener.open(req) as resp:
    auth_data = json.loads(resp.read())
    print(f"Auth: {auth_data['status']}")

def api_get(path):
    req = urllib.request.Request(f"http://127.0.0.1:8008{path}")
    return json.loads(opener.open(req).read())

def api_post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8008{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    return json.loads(opener.open(req).read())

# Test 1: Start a stopped bot
print("=" * 60)
print("Test 1: Start Bollinger_NZDUSD")
try:
    r = api_post("/api/bots/Bollinger_NZDUSD/start")
    print(f"  Response: {json.dumps(r, indent=2)}")
except urllib.error.HTTPError as e:
    print(f"  Error: {e.code} {e.read().decode()}")

time.sleep(3)

# Test 2: Check bot status
print("\nTest 2: Check bot status")
r = api_get("/api/bots/Bollinger_NZDUSD")
print(f"  running={r['running']}, pid={r.get('pid')}, last_error={r.get('last_error')}")

# Test 3: Check error log
print("\nTest 3: Error log")
log_path = r"C:\Trading\bots\logs\Bollinger_NZDUSD_error.log"
if os.path.exists(log_path):
    with open(log_path) as f:
        content = f.read()
    if content.strip():
        print(f"  Log tail: {content[-300:]}")
    else:
        print("  Log is empty")
else:
    print("  No error log yet")

# Test 4: Backtest with data_source
print("\n" + "=" * 60)
print("Test 4: Backtest data_source")
r = api_post("/api/backtest/run", {
    "strategy_name": "sma_crossover", "symbol": "XAUUSD",
    "timeframe": "1h", "date_from": "2025-06-20",
    "date_to": "2025-06-25", "capital": 10000
})
print(f"  data_source: {r.get('data_source')}")
print(f"  bars_fetched: {r.get('bars_fetched')}")
print(f"  trades: {r.get('metrics',{}).get('total_trades',0)}")
print(f"  equity_points: {len(r.get('equity_curve',[]))}")

# Test 5: MACD with few/0 trades
print("\n" + "=" * 60)
print("Test 5: MACD crossover")
r = api_post("/api/backtest/run", {
    "strategy_name": "macd_crossover", "symbol": "XAUUSD",
    "timeframe": "1h", "date_from": "2025-06-20",
    "date_to": "2025-06-25", "capital": 10000
})
print(f"  trades: {r.get('metrics',{}).get('total_trades',0)}")
print(f"  data_source: {r.get('data_source')}")

# Test 6: Test bot status
print("\n" + "=" * 60)
print("Test 6: Test bot status")
r = api_get("/api/bots/test/status")
print(f"  running={r.get('running')}, last_error={r.get('last_error')}")

# Test 7: List all bots with error info
print("\n" + "=" * 60)
print("Test 7: Bot list sample")
r = api_get("/api/bots")
print(f"  Total bots: {len(r)}")
for b in r[:3]:
    print(f"  {b['name']}: running={b['running']}, last_error={b.get('last_error')}")

print("\n✅ All tests complete!")
