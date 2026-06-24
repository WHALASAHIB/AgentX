"""
Test Bot — XAUUSD BUY 0.01 lot, hold 20s, close, exit.
Opens a single 0.01-lot BUY position on XAUUSD via MetaTrader 5,
waits 20 seconds, then closes the trade and exits cleanly.
Handles MT5 connection failure gracefully.
"""

import sys
import time
import traceback

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed. Install with: pip install MetaTrader5")
    sys.exit(1)


def main():
    print("[TEST_BOT] Starting XAUUSD BUY test (0.01 lot)")

    # ── 1. Initialize MT5 ────────────────────────────────────────────────
    if not mt5.initialize():
        err = mt5.last_error()
        print(f"[TEST_BOT] MT5 initialization FAILED: {err}")
        mt5.shutdown()
        sys.exit(1)

    print("[TEST_BOT] MT5 initialized successfully")
    account = mt5.account_info()
    if account is None:
        print(f"[TEST_BOT] No MT5 account connected: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)
    print(f"[TEST_BOT] Account: {account.login} @ {account.server} | Balance: {account.balance:.2f}")

    # ── 2. Open BUY 0.01 lot XAUUSD ──────────────────────────────────────
    symbol = "XAUUSD"
    lot = 0.01
    deviation = 20

    # Ensure symbol is available/market watch
    if not mt5.symbol_select(symbol, True):
        print(f"[TEST_BOT] Failed to select symbol {symbol}")
        mt5.shutdown()
        sys.exit(1)

    # Get current price
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[TEST_BOT] Failed to get tick for {symbol}")
        mt5.shutdown()
        sys.exit(1)

    price = tick.ask
    print(f"[TEST_BOT] XAUUSD ask price: {price}")

    # Prepare order request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": 0.0,
        "tp": 0.0,
        "deviation": deviation,
        "magic": 999001,
        "comment": "TEST_BOT",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err_msg = f"Order send failed: retcode={result.retcode if result else 'None'}"
        print(f"[TEST_BOT] {err_msg}")
        mt5.shutdown()
        sys.exit(1)

    ticket = result.order
    print(f"[TEST_BOT] BUY order placed — Ticket: {ticket}")

    # ── 3. Wait 20 seconds ────────────────────────────────────────────────
    print("[TEST_BOT] Waiting 20 seconds before closing...")
    time.sleep(20)

    # ── 4. Close the trade ────────────────────────────────────────────────
    # Get current position info (refresh price for closing)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print("[TEST_BOT] Cannot get current price to close — shutting down")
        mt5.shutdown()
        sys.exit(1)

    # Get open positions to find our ticket
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        print(f"[TEST_BOT] Position {ticket} already closed or not found")
        mt5.shutdown()
        sys.exit(0)

    pos = positions[0]
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_SELL,  # Close BUY with SELL
        "position": ticket,
        "price": tick.bid,
        "deviation": deviation,
        "magic": 999001,
        "comment": "TEST_BOT_CLOSE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    close_result = mt5.order_send(close_request)
    if close_result is None or close_result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[TEST_BOT] Close FAILED: retcode={close_result.retcode if close_result else 'None'}")
    else:
        print(f"[TEST_BOT] Position {ticket} CLOSED successfully")

    # ── 5. Shutdown and exit cleanly ──────────────────────────────────────
    mt5.shutdown()
    print("[TEST_BOT] Test complete — exiting cleanly")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[TEST_BOT] Unhandled exception: {e}")
        traceback.print_exc()
        try:
            mt5.shutdown()
        except Exception:
            pass
        sys.exit(1)
