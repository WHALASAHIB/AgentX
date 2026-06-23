#!/usr/bin/env python
"""
Direct MCP client for Trader Dev — bypasses the buggy anyio/SSE client.
Uses httpx + httpx-sse directly with proper event loop management for Python 3.12.
"""
import asyncio
import json
import sys
import uuid
from urllib.parse import urljoin

import httpx
from httpx_sse import aconnect_sse


class TraderDevMCP:
    """Direct MCP client for trader.dev using native SSE transport."""

    def __init__(self, server_url="https://mcp.trader.dev/sse"):
        self.server_url = server_url
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0))
        self._endpoint_url = None
        self._pending = {}
        self._reader_task = None
        self._connected = False
        self._connected_event = asyncio.Event()

    async def _read_loop(self):
        """Read all SSE events. Dispatch 'endpoint' to set the URL,
        'message' to resolve pending request futures."""
        async with aconnect_sse(self.http, "GET", self.server_url) as event_source:
            event_source.response.raise_for_status()
            async for sse in event_source.aiter_sse():
                if sse.event == "endpoint":
                    self._endpoint_url = urljoin(self.server_url, sse.data)
                    print(f"Connected: {self._endpoint_url}", file=sys.stderr)
                    self._connected_event.set()
                elif sse.event == "message" and sse.data.strip():
                    try:
                        msg = json.loads(sse.data)
                        msg_id = msg.get("id")
                        if msg_id is not None:
                            sid = str(msg_id)
                            fut = self._pending.pop(sid, None)
                            if fut and not fut.done():
                                fut.set_result(msg)
                    except json.JSONDecodeError:
                        pass

    async def connect(self):
        """Start the SSE reader and wait for the endpoint URL."""
        self._reader_task = asyncio.create_task(self._read_loop())
        await asyncio.wait_for(self._connected_event.wait(), timeout=30.0)
        self._connected = True
        return self._endpoint_url

    async def send_request(self, method: str, params: dict = None, timeout: float = 120.0):
        """Send JSON-RPC request via HTTP POST, wait for response via SSE."""
        req_id = str(uuid.uuid4())[:8]
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}

        future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future

        try:
            resp = await self.http.post(
                self._endpoint_url,
                json=payload,
                timeout=httpx.Timeout(timeout)
            )
            resp.raise_for_status()

            result = await asyncio.wait_for(future, timeout=timeout)

            if "error" in result:
                raise RuntimeError(f"MCP error: {json.dumps(result['error'])}")
            return result.get("result")
        except asyncio.TimeoutError:
            raise RuntimeError(f"Request {method} timed out after {timeout}s")
        finally:
            self._pending.pop(req_id, None)

    async def list_tools(self):
        return (await self.send_request("tools/list")).get("tools", [])

    async def call_tool(self, name, args=None):
        return await self.send_request("tools/call", {"name": name, "arguments": args or {}})

    async def close(self):
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        await self.http.aclose()
        self._connected = False


def print_result(data):
    """Print result as structured text."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    parsed = json.loads(item["text"])
                    print(json.dumps(parsed, indent=2, default=str))
                except (json.JSONDecodeError, KeyError):
                    print(item.get("text", str(item)))
            else:
                print(json.dumps(item, indent=2, default=str))
    elif isinstance(data, dict):
        if "content" in data:
            for item in data["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    try:
                        parsed = json.loads(item["text"])
                        print(json.dumps(parsed, indent=2, default=str))
                    except (json.JSONDecodeError, KeyError):
                        print(item["text"])
                else:
                    print(json.dumps(item, indent=2, default=str))
        else:
            print(json.dumps(data, indent=2, default=str))
    else:
        print(str(data))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Trader Dev MCP Client (direct)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-tools", help="List available tools")

    a = sub.add_parser("authenticate", help="Authenticate with API key")
    a.add_argument("--key", required=True)

    b = sub.add_parser("quick-backtest", help="Run synchronous backtest")
    b.add_argument("--symbol", required=True)
    b.add_argument("--timeframe", required=True)
    b.add_argument("--pine-source")
    b.add_argument("--pine-source-file")
    b.add_argument("--initial-capital", type=float, default=10000)
    b.add_argument("--name")

    s = sub.add_parser("search-strategies", help="Search strategies")
    s.add_argument("--symbol")
    s.add_argument("--timeframe")

    c = sub.add_parser("call", help="Call any tool directly")
    c.add_argument("tool_name")
    c.add_argument("tool_args", nargs="*")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    async def run():
        client = TraderDevMCP()
        try:
            await client.connect()

            if args.command == "list-tools":
                tools = await client.list_tools()
                print(f"Available tools ({len(tools)}):")
                for t in tools:
                    name = t.get("name", "?")
                    desc = t.get("description", "")
                    props = (t.get("inputSchema") or {}).get("properties", {})
                    print(f"\n  {name}: {desc[:200]}")
                    for pn, pi in props.items():
                        req = "required" if pn in (t.get("inputSchema") or {}).get("required", []) else "optional"
                        print(f"    {pn} ({pi.get('type', 'str')}, {req}): {pi.get('description', '')[:120]}")

            elif args.command == "authenticate":
                result = await client.call_tool("authenticate", {"key": args.key})
                print("Authenticated." if result else f"Result: {result}")
                print_result(result)

            elif args.command == "quick-backtest":
                params = {"symbol": args.symbol, "timeframe": args.timeframe, "initialCapital": int(args.initial_capital)}
                if args.pine_source:
                    params["pineSource"] = args.pine_source
                if args.pine_source_file:
                    with open(args.pine_source_file, "r") as f:
                        params["pineSource"] = f.read()
                if args.name:
                    params["name"] = args.name
                result = await client.call_tool("quick_backtest", params)
                print_result(result)

            elif args.command == "search-strategies":
                filters = {}
                if args.symbol: filters["symbol"] = args.symbol
                if args.timeframe: filters["timeframe"] = args.timeframe
                result = await client.call_tool("search_strategies", filters)
                print_result(result)

            elif args.command == "call":
                call_args = {}
                for a in args.tool_args:
                    if "=" in a:
                        k, v = a.split("=", 1)
                        call_args[k] = v
                result = await client.call_tool(args.tool_name, call_args)
                print_result(result)
        finally:
            await client.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
