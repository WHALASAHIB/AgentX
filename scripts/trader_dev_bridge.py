#!/usr/bin/env python
"""
trader_dev_bridge.py — Bridge between backend app.py and Trader Dev MCP
=======================================================================
Connects to trader.dev MCP SSE server, authenticates, and runs Pine Script
backtests. Used by the /api/backtest/run endpoint when strategy_name starts
with 'iter_' (Pine Script strategies).
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Trader.dev API key ──────────────────────────────────────────────────────
# Load from environment or fall back to the known key from test_flow.py
TRADER_DEV_API_KEY = os.environ.get(
    "TRADER_DEV_API_KEY",
    "pk_G0P628bcenPilOUGjIdJLV5OggU-RAYE"
)

# MCP server URL
MCP_SERVER_URL = os.environ.get(
    "TRADER_DEV_MCP_URL",
    "https://mcp.trader.dev/sse"
)

# Path to Pine Script strategies
PINES_DIR = Path(__file__).resolve().parent.parent / "strategy-engine" / "pines"
if not PINES_DIR.is_dir():
    PINES_DIR = Path("C:\\Trading\\strategy-engine\\pines")


class TraderDevBridge:
    """Manages a single MCP connection for Pine Script backtesting."""

    def __init__(self):
        self._client = None
        self._connected = False

    async def _ensure_client(self):
        """Lazy-init and connect the MCP client."""
        if self._connected and self._client is not None:
            return self._client

        # Import here to avoid circular imports and allow graceful fallback
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "strategy-engine"))
        from trader_dev_mcp import TraderDevMCP

        self._client = TraderDevMCP(server_url=MCP_SERVER_URL)
        try:
            await self._client.connect()
            # Authenticate
            auth_result = await self._client.call_tool(
                "authenticate", {"key": TRADER_DEV_API_KEY}
            )
            logger.info("Trader.dev MCP authenticated successfully")
            self._connected = True
            return self._client
        except Exception as e:
            self._connected = False
            self._client = None
            raise RuntimeError(f"Failed to connect to trader.dev MCP: {e}")

    async def run_backtest(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        capital: float = 10000,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        """
        Run a Pine Script backtest via trader.dev MCP.

        Args:
            strategy_name: Name of the strategy (e.g. 'iter_34_macd8_ichimoku_cloud_rsi')
            symbol: Trading symbol (e.g. 'XAUUSD')
            timeframe: Timeframe string (e.g. '1h', 'H1', '30m')
            capital: Initial capital
            date_from: Start date (YYYY-MM-DD) - optional
            date_to: End date (YYYY-MM-DD) - optional

        Returns:
            Dict with standardized backtest results (metrics, equity_curve, trades, etc.)

        Raises:
            RuntimeError: If MCP is unreachable or the backtest fails
            FileNotFoundError: If the .pine file doesn't exist
        """
        # Resolve the .pine file
        pine_path = PINES_DIR / f"{strategy_name}.pine"
        if not pine_path.exists():
            # Try alternate path
            alt_pine_path = Path(strategy_name)
            if alt_pine_path.suffix == ".pine" and alt_pine_path.exists():
                pine_path = alt_pine_path
            elif Path(strategy_name).exists():
                pine_path = Path(strategy_name)
            else:
                raise FileNotFoundError(
                    f"Pine Script file not found for strategy '{strategy_name}': {pine_path}"
                )

        pine_source = pine_path.read_text(encoding="utf-8")

        # Map timeframe format: H1 -> 1h, M15 -> 15m, etc.
        tf_map = {
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "1h", "H2": "2h", "H4": "4h",
            "D1": "1d", "W1": "1w",
        }
        mcp_tf = tf_map.get(timeframe.upper(), timeframe.lower())

        # Get the MCP client
        client = await self._ensure_client()

        # Build params for quick_backtest
        params = {
            "symbol": symbol,
            "timeframe": mcp_tf,
            "pineSource": pine_source,
            "initialCapital": int(capital),
            "name": strategy_name,
        }

        # Add date range if provided
        if date_from and date_to:
            params["from"] = date_from
            params["to"] = date_to

        logger.info(
            "Running MCP backtest: strategy=%s symbol=%s tf=%s capital=%s",
            strategy_name, symbol, mcp_tf, capital
        )

        try:
            result = await client.call_tool("quick_backtest", params)
        except Exception as e:
            raise RuntimeError(f"Trader.dev MCP backtest failed: {e}")

        # Parse the result — MCP returns content list with text items
        return self._parse_result(result, strategy_name)

    def _parse_result(self, raw_result, strategy_name: str) -> dict:
        """Convert MCP quick_backtest result to standardized format.

        MCP returns a list of content items. One of them contains a JSON
        string with the actual backtest result (resultId, result, etc.).
        We parse the JSON text item that has the most complete data.
        """
        # ── Collect all text content items ──────────────────────────────
        text_contents = []
        if isinstance(raw_result, dict):
            content = raw_result.get("content", [])
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_contents.append(item["text"])
        elif isinstance(raw_result, list):
            for item in raw_result:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_contents.append(item["text"])

        # ── Try to parse each text as JSON, pick the richest one ────────
        parsed = {}
        for tc in text_contents:
            try:
                obj = json.loads(tc)
                # Check if this has backtest result data
                if isinstance(obj, dict):
                    # Prefer the result that has a "result" key with backtest data
                    if "result" in obj and isinstance(obj["result"], dict):
                        parsed = obj["result"]
                        break
                    # Or has resultId + finalEquity (top-level result shape)
                    if "resultId" in obj and "finalEquity" in obj:
                        parsed = obj
                        break
                    # Otherwise use the largest dict
                    if len(str(obj)) > len(str(parsed)):
                        parsed = obj
            except (json.JSONDecodeError, TypeError):
                continue

        # If we still don't have meaningful data, extract from raw_result
        if not parsed or not isinstance(parsed, dict):
            parsed = raw_result if isinstance(raw_result, dict) else {}

        # ── Extract metrics ─────────────────────────────────────────────
        metrics = {}
        field_map = {
            "total_return_pct": ["netProfitPct", "netProfitPct", "totalReturn", "return"],
            "net_profit": ["netProfit", "netProfit", "net_profit"],
            "total_trades": ["totalTrades", "totalTrades", "trades"],
            "win_rate": ["winRatePct", "winRatePct", "winRate", "win_rate"],
            "profit_factor": ["profitFactor", "profitFactor", "profit_factor"],
            "max_drawdown": ["maxDrawdown", "maxDrawdown", "max_drawdown"],
            "max_drawdown_pct": ["maxDrawdownPct", "maxDrawdownPct", "maxDrawdown"],
            "sharpe_ratio": ["sharpeRatio", "sharpe", "sharpe_ratio"],
            "gross_profit": ["grossProfit", "grossProfit"],
            "gross_loss": ["grossLoss", "grossLoss"],
            "avg_trade": ["avgTrade", "avgTrade"],
            "avg_winning_trade": ["avgWinningTrade", "avgWinningTrade"],
            "avg_losing_trade": ["avgLosingTrade", "avgLosingTrade"],
            "largest_win": ["largestWin", "largestWin"],
            "largest_loss": ["largestLoss", "largestLoss"],
            "winning_trades": ["winningTrades", "winningTrades"],
            "losing_trades": ["losingTrades", "losingTrades"],
            "bars_evaluated": ["barsEvaluated", "barsEvaluated"],
        }

        for std_key, possible_keys in field_map.items():
            for pk in possible_keys:
                val = parsed.get(pk)
                if val is not None:
                    try:
                        metrics[std_key] = float(val)
                    except (ValueError, TypeError):
                        metrics[std_key] = 0.0
                    break
                # Check nested result.result
                if "result" in parsed and isinstance(parsed["result"], dict):
                    val = parsed["result"].get(pk)
                    if val is not None:
                        try:
                            metrics[std_key] = float(val)
                        except (ValueError, TypeError):
                            metrics[std_key] = 0.0
                        break

        # Ensure all metrics we care about have some value
        defaults = {
            "total_return_pct": 0.0, "net_profit": 0.0,
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0,
        }
        for k, v in defaults.items():
            metrics.setdefault(k, v)

        # ── Extract trades ──────────────────────────────────────────────
        trades_raw = parsed.get("trades", [])
        if not trades_raw and "result" in parsed and isinstance(parsed["result"], dict):
            trades_raw = parsed["result"].get("trades", [])

        trades_list = []
        if isinstance(trades_raw, list):
            for t in trades_raw:
                trades_list.append({
                    "entry_time": str(t.get("entryTime", t.get("entry_time", ""))),
                    "exit_time": str(t.get("exitTime", t.get("exit_time", ""))),
                    "side": str(t.get("side", t.get("direction", ""))),
                    "entry_price": float(t.get("entryPrice", t.get("entry_price", 0))),
                    "exit_price": float(t.get("exitPrice", t.get("exit_price", 0))),
                    "pnl": float(t.get("pnl", t.get("profit", 0))),
                    "pnl_pct": float(t.get("pnlPct", t.get("pnl_pct", 0))),
                    "exit_reason": str(t.get("exitReason", t.get("exit_reason", ""))),
                })

        # ── Extract equity curve ────────────────────────────────────────
        eq_curve = parsed.get("equityCurve", parsed.get("equity_curve", []))
        if not eq_curve and "result" in parsed and isinstance(parsed["result"], dict):
            eq_curve = parsed["result"].get("equityCurve", [])

        eq_data = []
        if isinstance(eq_curve, list):
            for point in eq_curve:
                if isinstance(point, dict):
                    eq_data.append({
                        "time": str(point.get("time", point.get("date", ""))),
                        "equity": float(point.get("equity", point.get("value", 0))),
                    })

        # ── Final equity ────────────────────────────────────────────────
        final_equity = parsed.get("finalEquity", parsed.get("final_equity"))
        if final_equity is None and "result" in parsed and isinstance(parsed["result"], dict):
            final_equity = parsed["result"].get("finalEquity")
        if final_equity is None:
            final_equity = parsed.get("initialCapital", 10000)

        return {
            "metrics": metrics,
            "equity_curve": eq_data,
            "trades": trades_list,
            "final_equity": float(final_equity),
            "strategy_name": strategy_name,
            "source": "trader_dev_mcp",
        }

    async def close(self):
        """Close the MCP connection."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
            self._connected = False


# ── Module-level singleton ──────────────────────────────────────────────────
_bridge_instance: Optional[TraderDevBridge] = None


def get_bridge() -> TraderDevBridge:
    """Get or create the shared TraderDevBridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = TraderDevBridge()
    return _bridge_instance


async def run_pine_backtest(
    strategy_name: str,
    symbol: str,
    timeframe: str = "1h",
    capital: float = 10000,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """Convenience function: run a Pine Script backtest via trader.dev MCP."""
    bridge = get_bridge()
    try:
        return await bridge.run_backtest(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            capital=capital,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception:
        # On failure, reset the bridge so next call tries fresh
        global _bridge_instance
        _bridge_instance = None
        raise


async def check_mcp_available() -> bool:
    """Check if trader.dev MCP is reachable. Returns True/False."""
    try:
        bridge = TraderDevBridge()
        client = await bridge._ensure_client()
        await bridge.close()
        return True
    except Exception as e:
        logger.warning("Trader.dev MCP not available: %s", e)
        return False
