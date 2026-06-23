#!/usr/bin/env python
"""Test full MCP flow: authenticate + backtest in one session."""
import asyncio
import json
import sys
sys.path.insert(0, r"C:\Trading\strategy-engine")
from trader_dev_mcp import TraderDevMCP, print_result


async def test():
    client = TraderDevMCP()
    await client.connect()

    # 1. Authenticate
    auth = await client.call_tool("authenticate", {"key": "pk_G0P628bcenPilOUGjIdJLV5OggU-RAYE"})
    print("AUTH OK", file=sys.stderr)

    # 2. Backtest
    with open(r"C:\Trading\strategy-engine\pines\iter_0_ema_cross.pine", "r") as f:
        pine = f.read()

    result = await client.call_tool("quick_backtest", {
        "symbol": "XAUUSD",
        "timeframe": "1h",
        "pineSource": pine,
        "initialCapital": 10000,
        "name": "iter_0_ema_cross"
    })
    
    print_result(result)

    await client.close()


asyncio.run(test())
