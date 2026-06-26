"""
Test Bot — XAUUSD BUY 0.01 lot, hold 20s, close, exit.
Uses the MT5 Bridge HTTP API instead of direct MT5 calls.
Accepts --account-id for targeted account execution.

Usage:
    python test_bot.py --account-id <account_id>
"""

import argparse
import sys
import time
import traceback

try:
    import requests
except ImportError:
    print("ERROR: requests package not installed. Install with: pip install requests")
    sys.exit(1)

BRIDGE_URL = "http://127.0.0.1:5000"
SYMBOL = "XAUUSD"
LOT = 0.01
DEVIATION = 20
MAGIC = 999001


def bridge_get(path: str) -> dict:
    """GET request to bridge API, returns parsed JSON."""
    url = f"{BRIDGE_URL}{path}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def bridge_trade(request: dict) -> dict:
    """POST a trade request to the bridge API, returns parsed JSON."""
    url = f"{BRIDGE_URL}/api/v1/trade"
    resp = requests.post(url, json=request, timeout=15)
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Test Bot — XAUUSD BUY test")
    parser.add_argument("--account-id", required=True, help="MT5 account ID to trade on")
    args = parser.parse_args()
    account_id = args.account_id

    print(f"[TEST_BOT] Starting XAUUSD BUY test (0.01 lot) on account: {account_id}")

    # ── 1. Get account info ────────────────────────────────────────────────
    try:
        account_info = bridge_get(f"/api/v1/accounts/{account_id}")
        print(f"[TEST_BOT] Account: {account_info.get('login')} @ {account_info.get('server')} "
              f"| Balance: {account_info.get('balance', 0):.2f}")
    except Exception as e:
        print(f"[TEST_BOT] Failed to get account info: {e}")
        sys.exit(1)

    # ── 2. Get current tick for XAUUSD ──────────────────────────────────────
    try:
        tick = bridge_get(f"/api/v1/accounts/{account_id}/tick/{SYMBOL}")
        ask = float(tick.get("ask", 0))
        bid = float(tick.get("bid", 0))
        if ask <= 0 or bid <= 0:
            print(f"[TEST_BOT] Invalid tick data: {tick}")
            sys.exit(1)
        print(f"[TEST_BOT] {SYMBOL} ask={ask} bid={bid}")
    except Exception as e:
        print(f"[TEST_BOT] Failed to get tick for {SYMBOL}: {e}")
        sys.exit(1)

    # ── 3. Open BUY 0.01 lot XAUUSD via bridge ──────────────────────────────
    open_request = {
        "account_id": account_id,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": "BUY",
        "price": ask,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "TEST_BOT",
    }
    print(f"[TEST_BOT] Sending BUY order...")
    result = bridge_trade(open_request)
    retcode = result.get("retcode", -1)
    if retcode != 10009:  # TRADE_RETCODE_DONE
        err_msg = result.get("error", result)
        print(f"[TEST_BOT] BUY order FAILED: retcode={retcode} error={err_msg}")
        sys.exit(1)

    ticket = result.get("order", 0)
    print(f"[TEST_BOT] BUY order placed — Ticket: {ticket}")

    # ── 4. Wait 20 seconds ────────────────────────────────────────────────
    print("[TEST_BOT] Waiting 20 seconds before closing...")
    time.sleep(20)

    # ── 5. Close the trade via bridge ──────────────────────────────────────
    # Get fresh tick for close price
    try:
        tick = bridge_get(f"/api/v1/accounts/{account_id}/tick/{SYMBOL}")
        bid = float(tick.get("bid", 0))
    except Exception as e:
        print(f"[TEST_BOT] Cannot get current price to close: {e}")
        sys.exit(1)

    close_request = {
        "account_id": account_id,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": "SELL",
        "position": ticket,
        "price": bid,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "TEST_BOT_CLOSE",
    }
    print(f"[TEST_BOT] Sending CLOSE order for ticket {ticket}...")
    close_result = bridge_trade(close_request)
    close_retcode = close_result.get("retcode", -1)
    if close_retcode != 10009:
        print(f"[TEST_BOT] Close FAILED: retcode={close_retcode} error={close_result.get('error', close_result)}")
    else:
        print(f"[TEST_BOT] Position {ticket} CLOSED successfully")

    # ── 6. Exit cleanly ────────────────────────────────────────────────────
    print("[TEST_BOT] Test complete — exiting cleanly")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[TEST_BOT] Unhandled exception: {e}")
        traceback.print_exc()
        sys.exit(1)
