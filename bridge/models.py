from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Health ────────────────────────────────────────────────────────────────────

class AccountStatus(BaseModel):
    id: str
    name: str
    connected: bool
    last_error: Optional[str] = None
    stale: bool = False

class HealthResponse(BaseModel):
    status: str = "ok"
    connected: bool
    accounts: list[AccountStatus] = []
    uptime_seconds: float = 0.0
    last_data_timestamp: Optional[datetime] = None
    version: str = "1.0.0"


# ── Account Info ──────────────────────────────────────────────────────────────

class AccountInfo(BaseModel):
    login: int
    name: str
    server: str
    broker: str
    currency: str
    leverage: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    profit: float
    trade_allowed: bool
    connected: bool
    stale: bool = False
    last_updated: Optional[datetime] = None


# ── Position ──────────────────────────────────────────────────────────────────

class Position(BaseModel):
    ticket: int
    symbol: str
    type: Literal["BUY", "SELL"]
    volume: float
    open_price: float
    current_price: float
    sl: float
    tp: float
    swap: float = 0.0
    profit: float
    open_time: str
    duration: str
    magic: int
    comment: str = ""
    stale: bool = False


# ── Trade History ─────────────────────────────────────────────────────────────

class ClosedTrade(BaseModel):
    position_id: int
    symbol: str
    type: Literal["BUY", "SELL"]
    volume: float
    entry_price: float
    exit_price: Optional[float] = None
    open_time: str
    close_time: str
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    net_profit: float = 0.0
    duration: str = ""
    magic: int = 0
    comment: str = ""


# ── Equity Curve ──────────────────────────────────────────────────────────────

class EquityPoint(BaseModel):
    time: str
    equity: float
    is_trade: bool = False
    type: str = ""
    profit: Optional[float] = None


# ── Statistics ────────────────────────────────────────────────────────────────

class AccountStats(BaseModel):
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_profit: float = 0.0
    daily_pnl: float = 0.0


# ── Tick ──────────────────────────────────────────────────────────────────────

class Tick(BaseModel):
    bid: float
    ask: float
    spread: int = 0
    time: str


# ── WebSocket Messages ────────────────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str
    account_id: Optional[str] = None
    symbol: Optional[str] = None
    data: Any = None


class WSSubscribe(BaseModel):
    type: Literal["subscribe", "unsubscribe"]
    channels: list[str] = []
