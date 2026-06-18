from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge import __version__
from bridge.config import load_accounts
from bridge.mt5_manager import get_manager, MT5Manager
from bridge.models import (
    AccountInfo, AccountStats, AccountStatus, ClosedTrade,
    EquityPoint, HealthResponse, Position, Tick, WSMessage,
)

logger = logging.getLogger(__name__)
_start_time = time.time()


# ── WebSocket Connection Manager ─────────────────────────────────────────────

class WSConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, message: dict):
        async with self._lock:
            dead = []
            for ws in self._connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.remove(ws)

    async def broadcast_to_subscribers(self, account_id: str, message: dict):
        msg = WSMessage(
            type=message.get("type", "event"),
            account_id=account_id,
            data=message.get("data"),
        )
        await self.broadcast(msg.model_dump(exclude_none=True))


ws_manager = WSConnectionManager()


# ── MT5 Event → WS Bridge ────────────────────────────────────────────────────

def _mt5_event_callback(account_id: str, message: dict):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(ws_manager.broadcast_to_subscribers(account_id, message))
    except RuntimeError:
        pass


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    accounts = load_accounts()
    manager = get_manager()
    manager.start_all(accounts)

    for conn in manager.get_all_connections():
        conn.register_ws_callback(_mt5_event_callback)

    logger.info("Bridge started with %d account(s)", len(accounts))
    yield

    manager.stop_all()


# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="AGENTX MT5 Bridge",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_conn(account_id: str):
    manager = get_manager()
    conn = manager.get_connection(account_id)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")
    return conn


def _ensure_not_stale(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("stale", False) and result.get("data") is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "MT5 offline and no cached data available",
                "connected": False,
                "stale": True,
            },
        )
    return result


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    manager = get_manager()
    acc_statuses = [
        AccountStatus(
            id=a["id"],
            name=a["name"],
            connected=a["connected"],
            last_error=a["last_error"],
            stale=a["stale"],
        )
        for a in manager.list_accounts()
    ]
    last_ts = None
    for conn_id in [a["id"] for a in manager.list_accounts()]:
        conn = manager.get_connection(conn_id)
        if conn and conn.last_data_time:
            dt = datetime.fromtimestamp(conn.last_data_time, tz=timezone.utc)
            if last_ts is None or dt > last_ts:
                last_ts = dt

    return HealthResponse(
        status="ok" if manager.any_connected else "degraded",
        connected=manager.any_connected,
        accounts=acc_statuses,
        uptime_seconds=round(time.time() - _start_time, 2),
        last_data_timestamp=last_ts,
        version=__version__,
    )


@app.get("/api/v1/accounts")
async def list_accounts():
    manager = get_manager()
    return manager.list_accounts()


@app.get("/api/v1/accounts/{account_id}", response_model=AccountInfo)
async def account_info(account_id: str):
    conn = _get_conn(account_id)
    result = conn.get_account_info()
    _ensure_not_stale(result)
    data = result["data"]
    return AccountInfo(
        login=data["login"],
        name=data.get("name", ""),
        server=data.get("server", ""),
        broker=data.get("broker", ""),
        currency=data.get("currency", ""),
        leverage=data.get("leverage", 0),
        balance=data.get("balance", 0.0),
        equity=data.get("equity", 0.0),
        margin=data.get("margin", 0.0),
        free_margin=data.get("free_margin", 0.0),
        margin_level=data.get("margin_level", 0.0),
        profit=data.get("profit", 0.0),
        trade_allowed=data.get("trade_allowed", False),
        connected=data.get("connected", False),
        stale=data.get("stale", True),
        last_updated=result.get("last_updated"),
    )


@app.get("/api/v1/accounts/{account_id}/positions", response_model=list[Position])
async def open_positions(account_id: str):
    conn = _get_conn(account_id)
    result = conn.get_positions()
    _ensure_not_stale(result)
    return [Position(**p) for p in result["data"]]


@app.get("/api/v1/accounts/{account_id}/history", response_model=list[ClosedTrade])
async def trade_history(account_id: str, days: int = Query(30, ge=1, le=365)):
    conn = _get_conn(account_id)
    result = conn.get_closed_trades()
    _ensure_not_stale(result)
    return [ClosedTrade(**t) for t in result["data"]]


@app.get("/api/v1/accounts/{account_id}/equity", response_model=list[EquityPoint])
async def equity_curve(account_id: str, days: int = Query(30, ge=1, le=365)):
    conn = _get_conn(account_id)
    result = conn.get_equity_curve()
    _ensure_not_stale(result)
    return [EquityPoint(**e) for e in result["data"]]


@app.get("/api/v1/accounts/{account_id}/stats", response_model=AccountStats)
async def account_stats(account_id: str, days: int = Query(30, ge=1, le=365)):
    conn = _get_conn(account_id)
    result = conn.get_stats()
    _ensure_not_stale(result)
    return AccountStats(**result["data"])


@app.get("/api/v1/accounts/{account_id}/tick/{symbol}", response_model=Tick)
async def live_tick(account_id: str, symbol: str):
    conn = _get_conn(account_id)
    data = conn.get_tick(symbol.upper())
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=f"No tick data for {symbol.upper()} (account {account_id})",
        )
    return Tick(**data)


@app.get("/diagnostic")
async def diagnostic():
    import importlib
    mt5_available = False
    try:
        import MetaTrader5
        mt5_available = True
    except ImportError:
        pass

    import platform
    import os as _os
    os_name = platform.system()
    if _os.name == "nt":
        os_name = "Windows"

    manager = get_manager()
    return {
        "os": os_name,
        "service_uptime_seconds": round(time.time() - _start_time, 2),
        "mt5_package_installed": mt5_available,
        "accounts_configured": len(manager.list_accounts()),
        "any_connected": manager.any_connected,
        "accounts": manager.list_accounts(),
    }


# ── WebSocket Endpoints ───────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS events error: %s", e)
    finally:
        await ws_manager.disconnect(websocket)


@app.websocket("/ws/ticks/{account_id}/{symbol}")
async def ws_ticks(websocket: WebSocket, account_id: str, symbol: str):
    await websocket.accept()
    symbol = symbol.upper()
    conn = _get_conn(account_id)
    try:
        while True:
            data = conn.get_tick(symbol)
            if data:
                await websocket.send_json({
                    "type": "tick",
                    "account_id": account_id,
                    "symbol": symbol,
                    "data": data,
                })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS tick error: %s", e)


@app.websocket("/ws/positions/{account_id}")
async def ws_positions(websocket: WebSocket, account_id: str):
    await websocket.accept()
    conn = _get_conn(account_id)
    last_tickets: set[int] = set()
    try:
        while True:
            result = conn.get_positions()
            if result["data"] is not None:
                current_tickets = {p["ticket"] for p in result["data"]}
                if current_tickets != last_tickets:
                    changed = result["data"]
                    last_tickets = current_tickets
                    await websocket.send_json({
                        "type": "position_update",
                        "account_id": account_id,
                        "data": changed,
                        "stale": not conn.connected,
                    })
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS position error: %s", e)
