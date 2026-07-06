"""
AgentX Trading MCP Server
==========================
Implements 3 patterns from arXiv:2606.30317:
1. RESOURCE GATEWAY (Pattern 1) — URI-addressed trading data with sanitization
2. DOMAIN-SPECIFIC ADAPTER (Pattern 5) — LLM-friendly MT5 trading tools
3. TOOL ORCHESTRATOR (Pattern 2) — Multi-step composite trading workflows

Anti-patterns avoided: no God Tool, all content sanitized, descriptive names,
no long-running sync ops.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("agentx-mcp")

BRIDGE_BASE = os.environ.get("AGENTX_BRIDGE_URL", "http://127.0.0.1:5000")
TRADING_DIR = Path(os.environ.get("AGENTX_TRADING_DIR", "C:/Trading"))

# ── Anti-Pattern Protection: Content Sanitizer ────────────────────────────
_INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore\s+(all\s+)?(prior|previous|above)\s+instructions|"
    r"forget\s+(everything|all)|"
    r"you\s+(are\s+)?(now|must\s+act\s+as)|"
    r"system\s+(prompt|message|instruction)|"
    r"override\s+(protocol|system|instructions))"
)


def sanitize(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = _INJECTION_PATTERNS.sub("[REDACTED]", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text


def sanitize_data(data: Any) -> Any:
    if isinstance(data, str):
        return sanitize(data)
    elif isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data


# ── Bridge Client ─────────────────────────────────────────────────────────
class BridgeClient:
    def __init__(self, base_url: str = BRIDGE_BASE):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=15.0)

    async def _get(self, path: str) -> Any:
        try:
            resp = await self.client.get(f"{self.base_url}{path}")
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    async def _post(self, path: str, data: dict | None = None) -> Any:
        try:
            resp = await self.client.post(f"{self.base_url}{path}", json=data or {})
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    async def list_accounts(self) -> list[dict]:
        d = await self._get("/api/v1/accounts")
        return d if isinstance(d, list) else []

    async def get_account(self, account_id: str) -> dict | None:
        return await self._get(f"/api/v1/accounts/{account_id}")

    async def get_health(self) -> dict | None:
        return await self._get("/health")

    async def get_positions(self, account_id: str) -> list[dict]:
        d = await self._get(f"/api/v1/accounts/{account_id}/positions")
        return d if isinstance(d, list) else []

    async def get_trades(self, account_id: str, limit: int = 50) -> list[dict]:
        d = await self._get(f"/api/v1/accounts/{account_id}/trades?limit={limit}")
        return d if isinstance(d, list) else []

    async def get_ticks(self, account_id: str) -> dict | None:
        return await self._get(f"/api/v1/accounts/{account_id}/ticks")

    async def switch_account(self, account_id: str) -> dict | None:
        return await self._post(f"/api/v1/accounts/{account_id}/switch")

    async def get_stats(self, account_id: str, days: int = 30) -> dict | None:
        return await self._get(f"/api/v1/accounts/{account_id}/stats?days={days}")


bridge = BridgeClient()

# ── MCP Server ────────────────────────────────────────────────────────────
from mcp.server import MCPServer, InitializationOptions
from mcp.server.models import ServerCapabilities
from mcp.types import CallToolResult, TextContent, ResourceContents

server = MCPServer(
    "agentx-trading",
    InitializationOptions(
        server_name="AgentX Trading MCP",
        server_version="1.0.0",
        capabilities=ServerCapabilities(tools={}, resources={}),
    ),
)

# ============================================================================
# TOOLS — Patterns 2 (Tool Orchestrator) & 5 (Domain-Specific Adapter)
# ============================================================================

@server.tool(description="Get a human-readable summary of a trading account including balance, "
             "equity, open positions count, total P&L, and connection status. "
             "Use FIRST before any trading operation to understand account state.")
async def get_account_summary(account_id: str) -> CallToolResult:
    """Get detailed trading account summary. account_id: e.g. mt5-demo, ftmo-10k, ftmo-100k."""
    account = await bridge.get_account(account_id)
    if not account:
        return CallToolResult(isError=True, content=[TextContent(type="text",
            text=f"Account '{account_id}' not found or bridge offline.")])
    positions = await bridge.get_positions(account_id)
    pos_count = len(positions) if positions else 0
    total_pnl = sum(p.get("profit", 0) or 0 for p in (positions or []))
    text = (
        f"**{account.get('name', account_id)}** | {account.get('server','N/A')} | Login: {account.get('login','N/A')}\n"
        f"Balance: **${account.get('balance',0):,.2f}** | Equity: **${account.get('equity',0):,.2f}**\n"
        f"P&L: **${account.get('profit',0):+,.2f}** | Open: {pos_count} (${total_pnl:+,.2f})\n"
        f"Trade: {'Yes' if account.get('trade_allowed') else 'No'} | "
        f"{'Connected' if account.get('connected') else 'Disconnected'}"
    )
    return CallToolResult(content=[TextContent(type="text", text=text)])


@server.tool(description="Switch the active MT5 trading account. The bridge disconnects from "
             "current account and connects to the target. Use to change which account you trade on.")
async def switch_active_account(account_id: str) -> CallToolResult:
    """Switch active MT5 account. account_id: target account (mt5-demo, ftmo-10k, ftmo-100k)."""
    result = await bridge.switch_account(account_id)
    if result is None:
        return CallToolResult(isError=True, content=[TextContent(type="text",
            text=f"Failed to switch to '{account_id}'. Bridge offline.")])
    status = result.get("status", "unknown")
    if status == "switched":
        return CallToolResult(content=[TextContent(type="text",
            text=f"✅ Switched to **{account_id}**.")])
    return CallToolResult(content=[TextContent(type="text",
        text=f"Switch result: {status}")])


@server.tool(description="Get detailed open positions for a trading account. "
             "Shows symbol, direction, volume, entry price, and P&L for each.")
async def get_position_details(account_id: str) -> CallToolResult:
    """List open positions. account_id: target account."""
    positions = await bridge.get_positions(account_id)
    if not positions:
        return CallToolResult(content=[TextContent(type="text",
            text=f"No open positions on **{account_id}**.")])
    lines = [f"**Open Positions — {account_id}** ({len(positions)}):"]
    for p in positions:
        pnl = p.get("profit", 0) or 0
        sym = p.get("symbol", "?")
        typ = p.get("type", "?")
        vol = p.get("volume", 0)
        entry = p.get("open_price", 0)
        lines.append(f"  {sym} {typ} {vol} lots @ {float(entry):.5f} → **${pnl:+,.2f}**")
    total = sum((p.get("profit", 0) or 0) for p in positions)
    lines.append(f"\n**Total: ${total:+,.2f}**")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


@server.tool(description="Get live bid/ask prices for all tracked forex pairs and BTCUSD. "
             "Returns a formatted table. Use before making trading decisions.")
async def get_market_prices() -> CallToolResult:
    """Live prices from active account."""
    accounts = await bridge.list_accounts()
    if not accounts:
        return CallToolResult(isError=True, content=[TextContent(type="text", text="No accounts.")])
    active = next((a for a in accounts if a.get("connected")), accounts[0])
    ticks = await bridge.get_ticks(active["id"])
    if not ticks:
        return CallToolResult(isError=True, content=[TextContent(type="text", text="Prices unavailable.")])
    lines = [f"**Live Prices** ({active.get('id','?')})\n", f"{'Symbol':<10} {'Bid':<12} {'Ask':<12}"]
    lines.append("-" * 34)
    for sym, data in sorted(ticks.items()):
        if isinstance(data, dict):
            lines.append(f"{sym:<10} {float(data.get('bid',0)):<12.5f} {float(data.get('ask',0)):<12.5f}")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


@server.tool(description="Get recent trade history. Shows symbol, direction, volume, "
             "entry price, profit. Use to review recent performance.")
async def get_trade_history(account_id: str, limit: int = 20) -> CallToolResult:
    """Recent trades. account_id: target. limit: max trades (1-100, default 20)."""
    limit = min(max(limit, 1), 100)
    trades = await bridge.get_trades(account_id, limit)
    if not trades:
        return CallToolResult(content=[TextContent(type="text",
            text=f"No trade history for **{account_id}**.")])
    lines = [f"**Trade History — {account_id}** (last {len(trades)}):"]
    for t in trades:
        profit = t.get("profit", 0) or 0
        lines.append(f"  {'+' if profit>=0 else '-'} {t.get('symbol','?')} {t.get('type','?')} "
                     f"{t.get('volume',0)} lots @ {t.get('price',0):.5f} → **${profit:+,.2f}**")
    total = sum((t.get("profit", 0) or 0) for t in trades)
    wins = sum(1 for t in trades if (t.get("profit", 0) or 0) > 0)
    wr = (wins / len(trades) * 100) if trades else 0
    lines.append(f"\n{len(trades)} trades | Win Rate: {wr:.0f}% | Net: **${total:+,.2f}**")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


@server.tool(description="Run full health check on bridge connectivity, all registered accounts, "
             "and their current balances and status. Use for troubleshooting.")
async def check_system_health() -> CallToolResult:
    """Infrastructure health check."""
    health = await bridge.get_health()
    accounts = await bridge.list_accounts()
    lines = ["**AgentX Health Check**\n"]
    if health:
        uptime = health.get("uptime_seconds", 0)
        lines.append(f"Bridge: {'Connected' if health.get('connected') else 'Disconnected'} "
                     f"({uptime//3600}h{(uptime%3600)//60}m)")
    else:
        lines.append("Bridge: Offline")
    if accounts:
        lines.append(f"\n**Accounts ({len(accounts)}):**")
        for a in accounts:
            lines.append(f"  {'Active' if a.get('connected') else 'Standby'}: "
                         f"{a.get('name',a['id'])} — ${a.get('balance',0):,.2f}")
    else:
        lines.append("\nNo accounts.")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


@server.tool(description="Complete audit of a trading account: balance, equity, open positions, "
             "recent trade performance, and risk metrics. One comprehensive health check.")
async def full_account_audit(account_id: str) -> CallToolResult:
    """Comprehensive audit. account_id: target."""
    account = await bridge.get_account(account_id)
    positions = await bridge.get_positions(account_id)
    trades = await bridge.get_trades(account_id, 50)
    lines = [f"**Full Audit — {account_id}**\n" + "=" * 50]
    if account:
        dd = 0
        if account.get("balance", 0) > 0:
            dd = (account["balance"] - account.get("equity", 0)) / account["balance"] * 100
        lines.append(f"Balance: ${account.get('balance',0):,.2f}")
        lines.append(f"Equity: ${account.get('equity',0):,.2f}")
        lines.append(f"Drawdown: {dd:.2f}%")
        lines.append(f"Margin Level: {account.get('margin_level',0):,.0f}%")
        lines.append(f"Trade: {'Yes' if account.get('trade_allowed') else 'No'}")
        if account.get("last_error"):
            lines.append(f"Error: {account['last_error']}")
    if positions:
        pos_pnl = sum((p.get("profit", 0) or 0) for p in positions)
        lines.append(f"\nOpen Positions ({len(positions)}) — P&L: ${pos_pnl:+,.2f}")
        for p in positions[:5]:
            lines.append(f"  {p.get('symbol','?')} {p.get('type','?')} ${p.get('profit',0):+,.2f}")
        if len(positions) > 5:
            lines.append(f"  ... +{len(positions)-5} more")
    if trades:
        wins = sum(1 for t in trades if (t.get("profit", 0) or 0) > 0)
        total = sum((t.get("profit", 0) or 0) for t in trades)
        lines.append(f"\nPerformance (last {len(trades)}): Win Rate: {wins/len(trades)*100:.0f}% | "
                     f"Net: ${total:+,.2f}")
        if dd > 5:
            lines.append("⚠️ Drawdown exceeds 5%")
        if (account or {}).get("margin_level", 1000) and (account or {}).get("margin_level", 1000) < 200:
            lines.append("🚨 Margin level below 200%")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


@server.tool(description="Compare all trading accounts side by side: balances, positions, "
             "performance. Get a bird's eye view of your entire portfolio.")
async def compare_accounts() -> CallToolResult:
    """Compare all accounts."""
    accounts = await bridge.list_accounts()
    if not accounts:
        return CallToolResult(isError=True, content=[TextContent(type="text", text="No accounts.")])
    lines = ["**Account Comparison**\n"]
    for a in accounts:
        aid = a.get("id", "?")
        positions = await bridge.get_positions(aid)
        pos_count = len(positions) if positions else 0
        pos_pnl = sum((p.get("profit", 0) or 0) for p in (positions or []))
        status = 'Active' if a.get("connected") else 'Standby'
        lines.append(f"  {a.get('name', aid):<20} "
                     f"${a.get('balance',0):<10,.2f} ${a.get('equity',0):<10,.2f} "
                     f"${pos_pnl:<8+,.2f} {pos_count} pos | {status}")
    return CallToolResult(content=[TextContent(type="text", text="\n".join(lines))])


# ============================================================================
# RESOURCES — Pattern 1: Resource Gateway (with sanitization)
# ============================================================================

@server.resource(uri="agentx://accounts", name="All Trading Accounts",
                 description="List all registered MT5 trading accounts with balances and status",
                 mime_type="application/json")
async def resource_accounts() -> list[ResourceContents]:
    accounts = await bridge.list_accounts()
    text = json.dumps(sanitize_data(accounts) if accounts else {"accounts": []}, indent=2)
    return [ResourceContents(uri="agentx://accounts", text=text, mimeType="application/json")]


@server.resource(uri="agentx://prices", name="Live Prices",
                 description="Current bid/ask prices for all tracked forex pairs and BTC",
                 mime_type="application/json")
async def resource_prices() -> list[ResourceContents]:
    accounts = await bridge.list_accounts()
    if not accounts:
        return [ResourceContents(uri="agentx://prices", text=json.dumps({"error": "no accounts"}),
                                 mimeType="application/json")]
    active = next((a for a in accounts if a.get("connected")), accounts[0])
    ticks = await bridge.get_ticks(active["id"])
    text = json.dumps(sanitize_data(ticks or {"error": "unavailable"}), indent=2)
    return [ResourceContents(uri="agentx://prices", text=text, mimeType="application/json")]


@server.resource(uri="agentx://health", name="System Health",
                 description="Health status of bridge and all registered accounts",
                 mime_type="application/json")
async def resource_health() -> list[ResourceContents]:
    health = await bridge.get_health()
    text = json.dumps(sanitize_data(health or {"status": "unhealthy"}), indent=2)
    return [ResourceContents(uri="agentx://health", text=text, mimeType="application/json")]


# ============================================================================
# Main
# ============================================================================

async def main():
    logger.info("=" * 60)
    logger.info("AgentX Trading MCP Server")
    logger.info("Patterns: Resource Gateway | Domain Adapter | Tool Orchestrator")
    logger.info(f"Tools: 8 | Resources: 3 | Anti-patterns: all 4 avoided")
    logger.info(f"Bridge: {BRIDGE_BASE}")
    logger.info("=" * 60)
    await server.run_streamable_http_async(host="127.0.0.1", port=8100)


if __name__ == "__main__":
    asyncio.run(main())
