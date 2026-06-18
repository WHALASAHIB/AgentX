#!/usr/bin/env python3
"""
Automated Health Check Test Suite for Trading Backend API.
Tests all major API endpoints respond with correct HTTP status codes and JSON schemas.
Hits the live server at http://localhost:8000.
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"
TIMEOUT = 10

tests_passed = 0
tests_failed = 0
failures = []


def request(endpoint):
    """HTTP GET to endpoint, returns (status_code, parsed_json_or_none)."""
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = urllib.request.urlopen(url, timeout=TIMEOUT)
        status = resp.status
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        return status, data
    except urllib.error.HTTPError as e:
        return e.code, None
    except json.JSONDecodeError as e:
        return 200, f"INVALID_JSON: {e}"
    except Exception as e:
        return 0, f"ERROR: {e}"


def request_post(endpoint, body=None):
    """HTTP POST to endpoint, returns (status_code, parsed_json_or_none)."""
    url = f"{BASE_URL}{endpoint}"
    data_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    req = urllib.request.Request(
        url, data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        status = resp.status
        body_resp = resp.read().decode("utf-8")
        data = json.loads(body_resp)
        return status, data
    except urllib.error.HTTPError as e:
        return e.code, None
    except json.JSONDecodeError as e:
        return 200, f"INVALID_JSON: {e}"
    except Exception as e:
        return 0, f"ERROR: {e}"


def check(name, condition, detail=""):
    global tests_passed, tests_failed
    if condition:
        tests_passed += 1
        print(f"  PASS  {name}")
    else:
        tests_failed += 1
        msg = f"  FAIL  {name}  --  {detail}" if detail else f"  FAIL  {name}"
        print(msg)
        failures.append(msg)


# ---------------------------------------------------------------------------
# 1. /api/health
# ---------------------------------------------------------------------------
def test_health():
    print("\n=== /api/health ===")
    status, data = request("/api/health")
    check("HTTP 200", status == 200, f"got {status}")
    check("JSON object (not array)", isinstance(data, dict), f"type={type(data).__name__}")
    check("Has 'status' key", "status" in data if isinstance(data, dict) else False)
    if isinstance(data, dict):
        check("status == 'ok'", data.get("status") == "ok", f"got {data.get('status')!r}")
        check("Has 'version' key", "version" in data)
        check("Has 'uptime_seconds' key", "uptime_seconds" in data)
        check("Has 'bridge' object", isinstance(data.get("bridge"), dict))
        check("Has 'database' object", isinstance(data.get("database"), dict))


# ---------------------------------------------------------------------------
# 2. /api/accounts
# ---------------------------------------------------------------------------
def test_accounts():
    print("\n=== /api/accounts ===")
    status, data = request("/api/accounts")
    check("HTTP 200", status == 200, f"got {status}")
    check("Response is a JSON array", isinstance(data, list), f"type={type(data).__name__}")
    if isinstance(data, list):
        check("Array is not None", data is not None)
        if data:
            acct = data[0]
            check("Account has 'id'", isinstance(acct, dict) and "id" in acct)
            check("Account has 'name'", isinstance(acct, dict) and "name" in acct)
            check("Account has 'login'", isinstance(acct, dict) and "login" in acct)
            check("Account has 'server'", isinstance(acct, dict) and "server" in acct)
            check("Account has 'connected'", isinstance(acct, dict) and "connected" in acct)


# ---------------------------------------------------------------------------
# 3. /api/bots
# ---------------------------------------------------------------------------
def test_bots():
    print("\n=== /api/bots ===")
    status, data = request("/api/bots")
    check("HTTP 200", status == 200, f"got {status}")
    check("Response is a JSON array", isinstance(data, list), f"type={type(data).__name__}")
    if isinstance(data, list):
        check("Array is not None", data is not None)
        if data:
            bot = data[0]
            check("Bot has 'name'", isinstance(bot, dict) and "name" in bot)
            check("Bot has 'display_name'", isinstance(bot, dict) and "display_name" in bot)
            check("Bot has 'running'", isinstance(bot, dict) and "running" in bot)
            check("Bot has 'script'", isinstance(bot, dict) and "script" in bot)
            check("Bot has 'config'", isinstance(bot, dict) and "config" in bot)


# ---------------------------------------------------------------------------
# 4. /api/stats
# ---------------------------------------------------------------------------
def test_stats():
    print("\n=== /api/stats ===")
    status, data = request("/api/stats")
    check("HTTP 200", status == 200, f"got {status}")
    check("JSON object (not array)", isinstance(data, dict), f"type={type(data).__name__}")
    if isinstance(data, dict):
        for key in ("total_positions", "open_positions", "total_trades",
                    "win_rate", "profit_factor", "net_pnl", "total_volume"):
            check(f"Has '{key}' key", key in data)
        check("Has 'best_account' object", isinstance(data.get("best_account"), dict))
        check("Has 'bot_statuses' array", isinstance(data.get("bot_statuses"), list))


# ---------------------------------------------------------------------------
# 5. /api/config/magic-numbers
# ---------------------------------------------------------------------------
def test_magic_numbers():
    print("\n=== /api/config/magic-numbers ===")
    status, data = request("/api/config/magic-numbers")
    check("HTTP 200", status == 200, f"got {status}")
    check("JSON object (not array)", isinstance(data, dict), f"type={type(data).__name__}")
    if isinstance(data, dict):
        check("Has 'gold_bot' key", "gold_bot" in data)
        check("Has 'scalping_bot' key", "scalping_bot" in data)
        check("Has 'streaming_bot' key", "streaming_bot" in data)
        check("Has 'gold_phoenix' key", "gold_phoenix" in data)
        # Magic numbers should be integers
        if "gold_bot" in data:
            check("gold_bot is int", isinstance(data["gold_bot"], int), f"type={type(data['gold_bot']).__name__}")


# ---------------------------------------------------------------------------
# 6. /api/backtest/strategies (GET)
# ---------------------------------------------------------------------------
def test_backtest_strategies():
    print("\n=== /api/backtest/strategies ===")
    status, data = request("/api/backtest/strategies")
    # This endpoint requires auth - expect 401 or 200
    check("Response received", status in (200, 401), f"got {status}")
    if status == 200:
        check("Response is a JSON array", isinstance(data, list), f"type={type(data).__name__}")
        if isinstance(data, list) and data:
            strat = data[0]
            check("Strategy has 'key'", isinstance(strat, dict) and "key" in strat)
            check("Strategy has 'name'", isinstance(strat, dict) and "name" in strat)
            check("Strategy has 'params'", isinstance(strat, dict) and "params" in strat)
    elif status == 401:
        check("Auth required (expected)", True)


# ---------------------------------------------------------------------------
# 7. /api/backtest/run (POST)
# ---------------------------------------------------------------------------
def test_backtest_run():
    print("\n=== /api/backtest/run ===")
    # First get strategies to find a valid key
    status, strats = request("/api/backtest/strategies")
    strategy_key = ""
    if status == 200 and isinstance(strats, list) and strats:
        strategy_key = strats[0].get("key", "")

    payload = {
        "symbol": "XAUUSD",
        "timeframe": "1h",
        "date_from": "2024-01-01",
        "date_to": "2024-02-01",
        "capital": 10000,
        "lot_size": 0.01,
        "strategy_key": strategy_key or "gold_bot",
        "strategy_params": {},
        "ftmo_mode": True,
    }
    status, data = request_post("/api/backtest/run", payload)
    # Expect 401 (no auth), 400 (bad data), or 200 (success)
    check("Response received", status in (200, 400, 401), f"got {status}")
    if status == 200:
        check("Response is a JSON object", isinstance(data, dict), f"type={type(data).__name__}")
        if isinstance(data, dict):
            check("Has 'metrics' key", "metrics" in data)
            check("Has 'equity_curve' key", "equity_curve" in data)
            check("Has 'trades' key", "trades" in data)
            check("Has 'final_equity' key", "final_equity" in data)
            check("equity_curve is a list", isinstance(data.get("equity_curve"), list))
            check("trades is a list", isinstance(data.get("trades"), list))
            check("final_equity is numeric", isinstance(data.get("final_equity"), (int, float)))
    elif status == 401:
        check("Auth required (expected)", True)


# ---------------------------------------------------------------------------
# 8. /api/backtest/custom (POST)
# ---------------------------------------------------------------------------
def test_backtest_custom():
    print("\n=== /api/backtest/custom ===")
    # Minimal custom strategy code
    code = '''import pandas as pd
import numpy as np

class MyTestStrategy:
    def __init__(self, data, **kwargs):
        self.data = data
    def next(self, i):
        return {}
    @property
    def name(self):
        return "MyTestStrategy"
'''
    payload = {
        "code": code,
        "symbol": "XAUUSD",
        "timeframe": "1h",
        "date_from": "2024-01-01",
        "date_to": "2024-02-01",
        "capital": 10000,
        "ftmo_mode": True,
    }
    status, data = request_post("/api/backtest/custom", payload)
    check("Response received", status in (200, 400, 401), f"got {status}")
    if status == 200:
        check("Response is a JSON object", isinstance(data, dict), f"type={type(data).__name__}")
        if isinstance(data, dict):
            check("Has 'metrics' key", "metrics" in data)
            check("Has 'equity_curve' key", "equity_curve" in data)
            check("Has 'trades' key", "trades" in data)
            check("Has 'final_equity' key", "final_equity" in data)
    elif status == 401:
        check("Auth required (expected)", True)
    # 400 is also valid — e.g. if data fetch fails for that range


# ---------------------------------------------------------------------------
# 9. /api/backtest/compare (POST)
# ---------------------------------------------------------------------------
def test_backtest_compare():
    print("\n=== /api/backtest/compare ===")
    payload = {
        "strategy_keys": ["gold_bot", "scalping_bot"],
        "symbol": "XAUUSD",
        "timeframe": "1h",
        "date_from": "2024-01-01",
        "date_to": "2024-02-01",
        "capital": 10000,
    }
    status, data = request_post("/api/backtest/compare", payload)
    check("Response received", status in (200, 400, 401), f"got {status}")
    if status == 200:
        check("Response is a JSON object", isinstance(data, dict), f"type={type(data).__name__}")
        if isinstance(data, dict):
            check("Has 'results' key", "results" in data)
            check("results is a list", isinstance(data.get("results"), list))
            if data["results"]:
                r = data["results"][0]
                check("Result has 'name'", "name" in r)
                check("Result has 'metrics'", "metrics" in r)
                check("Result has 'equity_curve'", "equity_curve" in r)
                check("Result has 'final_equity'", "final_equity" in r)
    elif status == 401:
        check("Auth required (expected)", True)


# ---------------------------------------------------------------------------
# 10. /api/ftmo/challenges (GET)
# ---------------------------------------------------------------------------
def test_ftmo_challenges():
    print("\n=== /api/ftmo/challenges ===")
    status, data = request("/api/ftmo/challenges")
    check("Response received", status in (200, 401), f"got {status}")
    if status == 200:
        check("Response is a JSON object", isinstance(data, dict), f"type={type(data).__name__}")
        if isinstance(data, dict):
            check("Has 'challenges' key", "challenges" in data)
            check("Has 'summary' key", "summary" in data)
            check("challenges is a list", isinstance(data.get("challenges"), list))
            check("summary is a dict", isinstance(data.get("summary"), dict))
    elif status == 401:
        check("Auth required (expected)", True)


# ---------------------------------------------------------------------------
# 11. /api/ftmo/summary (GET)
# ---------------------------------------------------------------------------
def test_ftmo_summary():
    print("\n=== /api/ftmo/summary ===")
    status, data = request("/api/ftmo/summary")
    check("Response received", status in (200, 401), f"got {status}")
    if status == 200:
        check("Response is a JSON object", isinstance(data, dict), f"type={type(data).__name__}")
    elif status == 401:
        check("Auth required (expected)", True)


# ---------------------------------------------------------------------------
# 12. /api/sentiment/score (GET)
# ---------------------------------------------------------------------------
def test_sentiment_score():
    print("\n=== /api/sentiment/score ===")
    status, data = request("/api/sentiment/score")
    # This endpoint does NOT require auth
    check("HTTP 200", status == 200, f"got {status}")
    check("Response is a JSON object", isinstance(data, dict), f"type={type(data).__name__}")
    if isinstance(data, dict):
        check("Has 'score' key", "score" in data)
        check("Has 'bias' key", "bias" in data)
        check("Has 'news' key", "news" in data)
        check("Has 'geopolitical_risk' key", "geopolitical_risk" in data)
        check("Has 'gold_trend' key", "gold_trend" in data)
        check("Has 'drivers' key", "drivers" in data)
        check("Has 'generated_at' key", "generated_at" in data)
        if isinstance(data.get("news"), dict):
            check("news has 'bullish'", "bullish" in data["news"])
            check("news has 'bearish'", "bearish" in data["news"])
            check("news has 'total'", "total" in data["news"])


# ---------------------------------------------------------------------------
# 13. /api/events (GET) — SSE endpoint (check it returns 200 + text/event-stream)
# ---------------------------------------------------------------------------
def test_events_sse():
    print("\n=== /api/events ===")
    url = f"{BASE_URL}/api/events"
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        status = resp.status
        content_type = resp.headers.get("Content-Type", "")
        # Read first chunk to verify SSE format
        chunk = resp.read(500).decode("utf-8", errors="replace")
        resp.close()
        check("HTTP 200", status == 200, f"got {status}")
        check("Content-Type is text/event-stream",
              "text/event-stream" in content_type,
              f"got {content_type!r}")
        check("Body starts with 'data:'", chunk.strip().startswith("data:"),
              f"first bytes: {chunk[:80]!r}")
        # Try to parse first SSE event as JSON
        if chunk.strip().startswith("data:"):
            json_str = chunk.strip()[5:].strip()
            try:
                event_data = json.loads(json_str)
                check("Parsed SSE event JSON", isinstance(event_data, dict))
                if isinstance(event_data, dict):
                    check("SSE event has 'type'", "type" in event_data)
                    check("SSE event has 'timestamp'", "timestamp" in event_data)
                    check("SSE event has 'bridge'", "bridge" in event_data)
                    check("SSE event has 'bot_statuses'", "bot_statuses" in event_data)
            except json.JSONDecodeError:
                check("SSE event is valid JSON", False, f"parse error on: {json_str[:100]}")
    except urllib.error.HTTPError as e:
        check("HTTP response", e.code in (200, 401), f"got {e.code}")
    except Exception as e:
        check("SSE request", False, f"ERROR: {e}")


# ---------------------------------------------------------------------------
# 14. /api/bots (GET)
# ---------------------------------------------------------------------------
def test_bots_expanded():
    print("\n=== /api/bots (expanded) ===")
    # Re-use the existing /api/bots GET but add more schema checks
    status, data = request("/api/bots")
    check("HTTP 200", status == 200, f"got {status}")
    check("Response is a JSON array", isinstance(data, list), f"type={type(data).__name__}")
    if isinstance(data, list):
        check("Array is not None", data is not None)
        if data:
            bot = data[0]
            check("Bot has 'name'", isinstance(bot, dict) and "name" in bot)
            check("Bot has 'display_name'", isinstance(bot, dict) and "display_name" in bot)
            check("Bot has 'running'", isinstance(bot, dict) and "running" in bot)
            check("'running' is bool", isinstance(bot.get("running"), bool),
                  f"type={type(bot.get('running')).__name__}")
            check("Bot has 'script'", isinstance(bot, dict) and "script" in bot)
            check("Bot has 'pid'", isinstance(bot, dict) and "pid" in bot)
            check("Bot has 'config'", isinstance(bot, dict) and "config" in bot)


# ---------------------------------------------------------------------------
# 15. /api/bots/{name}/start (POST) + /api/bots/{name}/stop (POST)
# ---------------------------------------------------------------------------
def test_bots_start_stop():
    print("\n=== /api/bots/{name}/start + stop ===")
    # Get a valid bot name from the list
    status, bots = request("/api/bots")
    bot_name = ""
    if status == 200 and isinstance(bots, list) and bots:
        bot_name = bots[0].get("name", "")

    if not bot_name:
        check("Bot name available", False, "no bots in list — can't test start/stop")
        return

    # Try starting the bot
    status, data = request_post(f"/api/bots/{bot_name}/start")
    check("Start response received", status in (200, 400, 401), f"got {status}")
    if status == 200:
        check("Start returned JSON object", isinstance(data, dict), f"type={type(data).__name__}")
        if isinstance(data, dict):
            check("Has 'status' or 'message' in start response",
                  "status" in data or "message" in data)
            # Check bot is now running
            _, bots_after = request("/api/bots")
            if isinstance(bots_after, list):
                for b in bots_after:
                    if b.get("name") == bot_name:
                        # It may not actually start if script not found, but structure should be there
                        check(f"Bot '{bot_name}' has running field", "running" in b)
                        break
    elif status == 401:
        check("Auth required (expected)", True)

    # Try stopping the bot (cleanup)
    status, data = request_post(f"/api/bots/{bot_name}/stop")
    check("Stop response received", status in (200, 400, 401), f"got {status}")
    if status == 200:
        check("Stop returned JSON object", isinstance(data, dict), f"type={type(data).__name__}")
        if isinstance(data, dict):
            check("Has 'status' or 'message' in stop response",
                  "status" in data or "message" in data)
    elif status == 401:
        check("Auth required (expected)", True)
if __name__ == "__main__":
    print("=" * 60)
    print(" TRADING BACKEND - HEALTH CHECK TEST SUITE")
    print(f" Target: {BASE_URL}")
    print("=" * 60)

    test_health()
    test_accounts()
    test_bots()
    test_stats()
    test_magic_numbers()
    test_backtest_strategies()
    test_backtest_run()
    test_backtest_custom()
    test_backtest_compare()
    test_ftmo_challenges()
    test_ftmo_summary()
    test_sentiment_score()
    test_events_sse()
    test_bots_expanded()
    test_bots_start_stop()

    print("\n" + "=" * 60)
    print(f" RESULTS:  {tests_passed} passed  /  {tests_failed} failed  /  {tests_passed + tests_failed} total")
    print("=" * 60)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f)

    sys.exit(0 if tests_failed == 0 else 1)
