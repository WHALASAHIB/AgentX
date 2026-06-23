import asyncio, json, sys
sys.path.insert(0, r"C:\Trading\strategy-engine")
sys.path.insert(0, r"C:\Users\nryur\AppData\Local\hermes\scripts")
from trader_dev_mcp import TraderDevMCP

async def run():
    client = TraderDevMCP()
    await client.connect()
    # Authenticate
    await client.call_tool("authenticate", {"key": "pk_G0P628bcenPilOUGjIdJLV5OggU-RAYE"})
    # Read Pine source
    with open(r"C:/Trading/strategy-engine/pines/iter_26_macd_rsi_tp1.5_24h.pine", "r") as f:
        pine = f.read()
    # Backtest
    result = await client.call_tool("quick_backtest", {
        "symbol": "XAUUSD", "timeframe": "1h",
        "pineSource": pine, "initialCapital": 10000,
        "name": "iter_26_macd_rsi_tp1.5_24h"
    })
    print(json.dumps(result, default=str))
    await client.close()

asyncio.run(run())
