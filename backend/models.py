"""Pydantic response models for AGENTX API endpoints.

Provides a base ResponseModel and typed models for the main endpoint groups.
Used as response_model=... annotations in FastAPI routes for OpenAPI docs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Base Model ─────────────────────────────────────────────────────────────────

class ResponseModel(BaseModel):
    """Base response model with common fields.

    All specific response models should inherit from this to ensure a
    consistent API surface. Subclasses may add endpoint-specific fields.
    """
    pass


# ── Health ─────────────────────────────────────────────────────────────────────

class BridgeHealthInfo(BaseModel):
    """Sub-object returned inside HealthResponse indicating bridge connectivity."""
    connected: bool = Field(
        default=False,
        description="Whether the MT5 bridge is currently connected",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the bridge is unreachable or failed",
    )


class DatabaseHealthInfo(BaseModel):
    """Sub-object for database connection status inside HealthResponse."""
    connected: bool = Field(
        default=False,
        description="Whether the database connection is alive",
    )


class RedisHealthInfo(BaseModel):
    """Sub-object for Redis connection status inside HealthResponse."""
    connected: bool = Field(
        default=False,
        description="Whether the Redis connection is alive",
    )


class HealthResponse(ResponseModel):
    """Response returned by ``GET /api/health``.

    Contains overall API status, version, uptime, and sub-service health.
    """
    status: str = Field(
        default="ok",
        description="Overall API status (e.g. 'ok')",
    )
    version: str = Field(
        default="",
        description="Backend version string from ``backend.__version__``",
    )
    uptime_seconds: float = Field(
        default=0.0,
        description="Seconds elapsed since the backend process started",
        ge=0,
    )
    bridge: BridgeHealthInfo = Field(
        default_factory=BridgeHealthInfo,
        description="MT5 bridge health information",
    )
    database: DatabaseHealthInfo = Field(
        default_factory=DatabaseHealthInfo,
        description="Database connection status",
    )
    redis: RedisHealthInfo = Field(
        default_factory=RedisHealthInfo,
        description="Redis connection status",
    )
    time: str = Field(
        default="",
        description="ISO-8601 timestamp of when the response was generated",
    )


# ── Bridge Status ──────────────────────────────────────────────────────────────

class BridgeStatus(ResponseModel):
    """Status information for the MT5 bridge, returned by diagnostic endpoints."""
    connected: bool = Field(
        default=False,
        description="Whether the bridge is connected",
    )
    accounts: list[dict] = Field(
        default_factory=list,
        description="List of account status dicts from the bridge",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the bridge is unreachable",
    )


# ── Account Info ───────────────────────────────────────────────────────────────

class AccountInfo(ResponseModel):
    """Detailed information about a single trading account."""
    id: Optional[str] = Field(
        default=None,
        description="Unique account identifier",
    )
    login: Optional[int] = Field(
        default=None,
        description="MT5 login number",
    )
    name: Optional[str] = Field(
        default=None,
        description="Human-readable account name",
    )
    server: Optional[str] = Field(
        default=None,
        description="MT5 server name",
    )
    connected: bool = Field(
        default=False,
        description="Whether the account is currently connected via the bridge",
    )
    stale: Optional[bool] = Field(
        default=None,
        description="Whether the account data may be stale (not actively streaming)",
    )
    enabled: Optional[bool] = Field(
        default=None,
        description="Whether the account is enabled in the system",
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message if the account failed to connect",
    )


# ── Bot Info ───────────────────────────────────────────────────────────────────

class BotInfo(ResponseModel):
    """Status and metadata for a single trading bot instance."""
    name: str = Field(
        default="",
        description="Bot script key name",
    )
    display_name: str = Field(
        default="",
        description="Human-readable display name",
    )
    running: bool = Field(
        default=False,
        description="Whether the bot process is currently active",
    )
    pid: Optional[int] = Field(
        default=None,
        description="Process ID of the running bot, or None if stopped",
    )
    script: str = Field(
        default="",
        description="Filesystem path to the bot script",
    )
    config: Optional[dict] = Field(
        default=None,
        description="Bot configuration dictionary from the database",
    )


# ── Position Info ──────────────────────────────────────────────────────────────

class PositionInfo(ResponseModel):
    """Information about an open trading position."""
    ticket: Optional[int] = Field(
        default=None,
        description="Position ticket number",
    )
    symbol: Optional[str] = Field(
        default=None,
        description="Traded symbol (e.g. 'XAUUSD')",
    )
    side: Optional[str] = Field(
        default=None,
        description="Trade direction: 'buy' or 'sell'",
    )
    volume: Optional[float] = Field(
        default=None,
        description="Trade volume in lots",
    )
    open_price: Optional[float] = Field(
        default=None,
        description="Price at which the position was opened",
    )
    current_price: Optional[float] = Field(
        default=None,
        description="Current market price for the symbol",
    )
    profit: Optional[float] = Field(
        default=None,
        description="Current profit/loss in account currency",
    )
    swap: Optional[float] = Field(
        default=None,
        description="Accumulated swap/rollover",
    )
    open_time: Optional[str] = Field(
        default=None,
        description="ISO-8601 timestamp of when the position was opened",
    )
    account_id: Optional[str] = Field(
        default=None,
        description="ID of the account holding this position",
    )


# ── Stats Response ─────────────────────────────────────────────────────────────

class StatsResponse(ResponseModel):
    """Trading statistics for an account over a given period."""
    total_trades: Optional[int] = Field(
        default=None,
        description="Total number of trades in the period",
    )
    winning_trades: Optional[int] = Field(
        default=None,
        description="Number of profitable trades",
    )
    losing_trades: Optional[int] = Field(
        default=None,
        description="Number of unprofitable trades",
    )
    win_rate: Optional[float] = Field(
        default=None,
        description="Win rate as a decimal (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    total_profit: Optional[float] = Field(
        default=None,
        description="Sum of all profitable trade PnL",
    )
    total_loss: Optional[float] = Field(
        default=None,
        description="Sum of all losing trade PnL",
    )
    net_profit: Optional[float] = Field(
        default=None,
        description="Net profit = total_profit + total_loss",
    )
    profit_factor: Optional[float] = Field(
        default=None,
        description="Ratio of gross profit to gross loss",
        ge=0.0,
    )
    sharpe_ratio: Optional[float] = Field(
        default=None,
        description="Sharpe ratio of the trading period",
    )
    max_drawdown: Optional[float] = Field(
        default=None,
        description="Maximum drawdown as a percentage (0–100)",
        ge=0.0,
        le=100.0,
    )
    avg_trade: Optional[float] = Field(
        default=None,
        description="Average profit/loss per trade",
    )
    avg_win: Optional[float] = Field(
        default=None,
        description="Average profit per winning trade",
    )
    avg_loss: Optional[float] = Field(
        default=None,
        description="Average loss per losing trade",
    )


# ── Backtest Result ────────────────────────────────────────────────────────────

class BacktestTrade(BaseModel):
    """A single trade generated during a backtest simulation."""
    entry_time: str = Field(
        default="",
        description="Timestamp of trade entry",
    )
    exit_time: str = Field(
        default="",
        description="Timestamp of trade exit",
    )
    symbol: str = Field(
        default="",
        description="Traded symbol",
    )
    side: str = Field(
        default="",
        description="Trade direction: 'buy' or 'sell'",
    )
    entry_price: float = Field(
        default=0.0,
        description="Price at entry",
    )
    exit_price: float = Field(
        default=0.0,
        description="Price at exit",
    )
    pnl: float = Field(
        default=0.0,
        description="Profit/loss in account currency",
    )
    pnl_pct: float = Field(
        default=0.0,
        description="Profit/loss as a percentage of capital",
    )


class EquityPoint(BaseModel):
    """A single data point on the equity curve."""
    time: str = Field(
        default="",
        description="Timestamp of this equity point",
    )
    equity: float = Field(
        default=0.0,
        description="Account equity at this point in time",
    )


class BacktestMetrics(BaseModel):
    """Aggregate metrics computed from a backtest run."""
    total_return: Optional[float] = Field(
        default=None,
        description="Total return as a decimal (e.g. 0.15 = 15%)",
    )
    sharpe: Optional[float] = Field(
        default=None,
        description="Sharpe ratio of the strategy",
    )
    max_drawdown: Optional[float] = Field(
        default=None,
        description="Maximum drawdown as a decimal",
    )
    win_rate: Optional[float] = Field(
        default=None,
        description="Win rate as a decimal (0.0–1.0)",
    )
    profit_factor: Optional[float] = Field(
        default=None,
        description="Ratio of gross profit to gross loss",
    )
    total_trades: Optional[int] = Field(
        default=None,
        description="Total number of trades executed",
    )
    avg_trade: Optional[float] = Field(
        default=None,
        description="Average PnL per trade",
    )


class FTMOPhase(BaseModel):
    """FTMO challenge phase evaluation results."""
    passed: Optional[bool] = Field(
        default=None,
        description="Whether the FTMO phase was passed",
    )
    profit: Optional[float] = Field(
        default=None,
        description="Profit percentage achieved",
    )
    max_drawdown: Optional[float] = Field(
        default=None,
        description="Maximum drawdown during the phase",
    )
    days_traded: Optional[int] = Field(
        default=None,
        description="Number of days traded in the phase",
    )


class BacktestResult(ResponseModel):
    """Complete result of a backtest simulation run."""
    metrics: BacktestMetrics = Field(
        default_factory=BacktestMetrics,
        description="Aggregate performance metrics",
    )
    equity_curve: list[EquityPoint] = Field(
        default_factory=list,
        description="Equity curve data points over time",
    )
    trades: list[BacktestTrade] = Field(
        default_factory=list,
        description="Individual trade records from the simulation",
    )
    final_equity: float = Field(
        default=0.0,
        description="Ending account equity after all trades",
    )
    ftmo: Optional[FTMOPhase] = Field(
        default=None,
        description="FTMO phase 1 evaluation results, if applicable",
    )
    ftmo_phase2: Optional[FTMOPhase] = Field(
        default=None,
        description="FTMO phase 2 evaluation results, if applicable",
    )


# ── Generic / Convenience ──────────────────────────────────────────────────────

class StatusResponse(ResponseModel):
    """Simple status response used by create/delete/switch endpoints."""
    status: str = Field(
        default="ok",
        description="Operation result status (e.g. 'ok', 'created', 'deleted', 'switched')",
    )


__all__ = [
    "ResponseModel",
    "HealthResponse",
    "BridgeHealthInfo",
    "DatabaseHealthInfo",
    "RedisHealthInfo",
    "BridgeStatus",
    "AccountInfo",
    "BotInfo",
    "PositionInfo",
    "StatsResponse",
    "BacktestResult",
    "BacktestMetrics",
    "BacktestTrade",
    "EquityPoint",
    "FTMOPhase",
    "StatusResponse",
]
