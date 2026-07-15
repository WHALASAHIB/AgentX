"""Strategy Engineer — Iteration 356: EMA3/8 + RSI + ADX>18 + 1:1.5 TP/SL on XAUUSD 1h"""
import asyncio, json, sys, os
sys.path.insert(0, r"C:\Trading\strategy-engine")
sys.path.insert(0, r"C:\Users\nryur\AppData\Local\hermes\scripts")
from trader_dev_mcp import TraderDevMCP

PINE_FILE = r"C:/Trading/strategy-engine/pines/iter_356_ema_cross_rsi_adx18_tp15.pine"
SYMBOL = "XAUUSD"
TIMEFRAME = "1h"
API_KEY = "pk_G0P628bcenPilOUGjIdJLV5OggU-RAYE"

async def run():
    client = TraderDevMCP()
    try:
        await client.connect()
        print("CONNECTED", flush=True)

        # Authenticate
        auth_result = await client.call_tool("authenticate", {"key": API_KEY})
        print(f"AUTH: {json.dumps(auth_result, default=str)}", flush=True)

        # Read Pine source
        with open(PINE_FILE, "r") as f:
            pine = f.read()

        # Backtest
        result = await client.call_tool("quick_backtest", {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "pineSource": pine,
            "initialCapital": 10000,
            "name": "iter_356_ema_cross_rsi_adx18_tp15"
        })
        print("RESULT:", json.dumps(result, default=str), flush=True)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)
    finally:
        await client.close()

asyncio.run(run())
