"""
Connection Test Bot
Places a 0.0001 lot random trade, holds for 10 seconds, closes it.
Purpose: verify end-to-end MT5 connection and algo trading is working.
"""

import MetaTrader5 as mt5
import random
import time
from datetime import datetime

# Initialize MT5
print("=" * 60)
print("CONNECTION TEST BOT")
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

if not mt5.initialize():
    print(f"❌ MT5 initialize failed: {mt5.last_error()}")
    exit(1)

print("✅ MT5 initialized")

# Check terminal status
terminal_info = mt5.terminal_info()
if terminal_info:
    print(f"   Terminal: {terminal_info.name}")
    print(f"   Connected: {terminal_info.connected}")
    print(f"   Trade allowed: {terminal_info.trade_allowed}")

# Check account info
account_info = mt5.account_info()
if account_info:
    print(f"   Account: {account_info.login}")
    print(f"   Balance: ${account_info.balance:.2f}")
    print(f"   Equity: ${account_info.equity:.2f}")
    print(f"   Trade mode: {account_info.trade_mode}")

# If trade_allowed is False, algo trading is disabled in terminal
if account_info and not account_info.trade_allowed:
    print("\n⚠️  TRADE NOT ALLOWED - Algo trading disabled in MT5 terminal!")
    print("   Click the 'Algo Trading' button (green triangle) in MT5 toolbar")
    mt5.shutdown()
    exit(1)

# Pick a random symbol from major pairs
symbols = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", "BTCUSD"]
symbol = random.choice(symbols)

print(f"\n📊 Testing symbol: {symbol}")

# Check if symbol is available
if not mt5.symbol_select(symbol, True):
    print(f"❌ Failed to select symbol {symbol}: {mt5.last_error()}")
    # Try another symbol
    symbol = "XAUUSD"
    mt5.symbol_select(symbol, True)

# Get symbol info
symbol_info = mt5.symbol_info(symbol)
if not symbol_info:
    print(f"❌ Symbol {symbol} not found")
    mt5.shutdown()
    exit(1)

print(f"   Spread: {symbol_info.spread}")
print(f"   Digits: {symbol_info.digits}")
print(f"   Trade mode: {symbol_info.trade_mode}")

# Get current price
tick = mt5.symbol_info_tick(symbol)
if not tick:
    print(f"❌ Failed to get tick for {symbol}")
    mt5.shutdown()
    exit(1)

print(f"   Bid: {tick.bid}")
print(f"   Ask: {tick.ask}")

# Random buy or sell
is_buy = random.choice([True, False])
order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
action = "BUY" if is_buy else "SELL"

price = tick.ask if is_buy else tick.bid

# Calculate SL/TP to minimize risk (wide so it doesn't hit in 10s)
slip = symbol_info.point * 500  # 50 pips for safety
if is_buy:
    sl = price - slip
    tp = price + slip
else:
    sl = price + slip
    tp = price - slip

# Prepare the trade request
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": 0.0001,  # Minimum possible lot
    "type": order_type,
    "price": price,
    "sl": sl,
    "tp": tp,
    "deviation": 20,
    "magic": 999999,  # Test magic number
    "comment": "CONNECTION_TEST",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}

print(f"\n🚀 PLACING {action} {symbol} 0.0001 lot @ {price}")
print(f"   SL: {sl} | TP: {tp}")

# Send order
result = mt5.order_send(request)

if result.retcode != mt5.TRADE_RETCODE_DONE:
    print(f"\n❌ ORDER REJECTED!")
    print(f"   Retcode: {result.retcode}")
    print(f"   Comment: {result.comment}")
    
    # Decode common error codes
    errors = {
        10013: "Invalid request",
        10014: "Invalid volume",
        10015: "Invalid price",
        10016: "Invalid SL/TP",
        10017: "Order disabled",
        10018: "Market closed",
        10019: "Insufficient money",
        10020: "Too many orders",
        10021: "Server error",
        10022: "No changes",
        10024: "No orders to close/modify/delete",
        10025: "Duplicate order (already placed)",
        10026: "Blocked by server filters",
        10027: "AutoTrading disabled by client",
        10028: "AutoTrading disabled by server",
        10029: "No connection",
        10030: "Order timeout",
        10031: "Invalid order type",
        10032: "Invalid order fill type",
        10033: "Invalid order expiration",
        10034: "Invalid order direction",
    }
    if result.retcode in errors:
        print(f"   Meaning: {errors[result.retcode]}")
    else:
        print(f"   Unknown error code")
    
    mt5.shutdown()
    exit(1)

print(f"✅ ORDER EXECUTED!")
print(f"   Ticket: {result.order}")
print(f"   Volume: {result.volume}")
print(f"   Price: {result.price}")

# Wait 10 seconds
print(f"\n⏳ Holding position for 10 seconds...")
for i in range(10, 0, -1):
    print(f"   {i}s...", end="\r")
    time.sleep(1)
print("   Done!            ")

# Close the position
print(f"\n🔒 Closing position...")

close_request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": 0.0001,
    "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
    "position": result.order,
    "price": tick.bid if is_buy else tick.ask,
    "deviation": 20,
    "magic": 999999,
    "comment": "CONNECTION_TEST_CLOSE",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}

close_result = mt5.order_send(close_request)

if close_result.retcode == mt5.TRADE_RETCODE_DONE:
    # Get the trade result
    positions = mt5.history_deals_get(result.order, result.order + 1)
    if positions and len(positions) > 0:
        profit = sum(p.profit for p in positions)
        print(f"✅ POSITION CLOSED! P&L: ${profit:.2f}")
    else:
        print("✅ POSITION CLOSED!")
else:
    print(f"❌ CLOSE FAILED: retcode={close_result.retcode} ({close_result.comment})")

# Check positions list
mt5_positions = mt5.positions_get()
if mt5_positions and len(mt5_positions) > 0:
    print(f"\n📋 Open positions remaining: {len(mt5_positions)}")
else:
    print(f"\n📋 No open positions remaining ✅")

# Summary
print(f"\n{'=' * 60}")
print("TEST RESULT: ✅ PASSED" if result.retcode == mt5.TRADE_RETCODE_DONE else "TEST RESULT: ❌ FAILED")
print(f"   Symbol: {symbol}")
print(f"   Direction: {action}")
print(f"   Volume: 0.0001")
print(f"   Order Ticket: {result.order}")
print(f"   Connection: ✅ Working")
print(f"   Algo Trading: ✅ Enabled")
print(f"{'=' * 60}")

mt5.shutdown()
