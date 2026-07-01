import asyncio, json, sys
sys.path.insert(0, r"C:\Trading\strategy-engine")
sys.path.insert(0, r"C:\Users\nryur\AppData\Local\hermes\scripts")
from trader_dev_mcp import TraderDevMCP

async def run():
    client = TraderDevMCP()
    await client.connect()
    await client.call_tool("authenticate", {"key": "pk_G0P628bcenPilOUGjIdJLV5OggU-RAYE"})
    with open(r"C:/Trading/strategy-engine/pines/iter_317_ema3_10_rsi50_adx18_session.pine", "r") as f:
        pine = f.read()
    result = await client.call_tool("quick_backtest", {
        "symbol": "XAUUSD", "timeframe": "1h",
        "pineSource": pine, "initialCapital": 10000,
        "name": "iter_317_ema3_10_rsi50_adx18_session"
    })
    print(json.dumps(result, default=str))
    await client.close()

asyncio.run(run())
