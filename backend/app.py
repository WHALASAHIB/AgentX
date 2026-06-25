from __future__ import annotations

# ═══════════════════════════════════════════════════════════════════════════
# 🔒 AGENTX BACKEND — INFRASTRUCTURE BASELINE
# ═══════════════════════════════════════════════════════════════════════════
# This file is the IMMUTABLE FOUNDATION of the entire platform.
# DO NOT CHANGE:
#   - Ports (8005 HTTP / 8443 HTTPS)
#   - Route structure (/api/*, /_next/*, /* catch-all)
#   - CORS configuration
#   - serve_frontend() routing logic (path→.html→index.html fallback)
#   - WebSocket proxy (/api/ws/*)
#   - Scanner blocker middleware
#   - Auth endpoint signatures (/api/auth/me, signin, signup)
# Without explicit Commander approval.
#
# 🏛️ Reference: /c/Trading/BASELINE.md — the single source of truth.
# ═══════════════════════════════════════════════════════════════════════════

import asyncio
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
PydanticBaseModel = BaseModel

from backend.models import HealthResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import __version__
from backend.auth import (
    require_auth, optional_auth, is_google_configured,
    get_google_auth_url, exchange_code, OWNER_EMAIL,
    SESSION_COOKIE,
    list_access_codes, generate_access_codes,
    validate_access_code, claim_access_code,
)
from backend.bridge_client import get_bridge
from backend.db.pool import get_db
from backend.redis_client import get_redis

logger = logging.getLogger(__name__)
_start_time = time.time()

# ── User Store (password-based auth for dev/signup) ─────────────────────────
_USERS: dict[str, dict] = {}  # email -> {"password_hash": str}


def _hash_password(password: str) -> str:
    """Simple SHA-256 hash for dev-mode password storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    return _hash_password(password) == password_hash


def _seed_users():
    """Seed known users on startup."""
    _USERS["whalasahibtrading@gmail.com"] = {
        "password_hash": _hash_password("Trading123!"),
        "name": "whalasahibtrading",
        "role": "admin",
    }
    logger.info("Seeded %d user(s) in user store", len(_USERS))


def _get_user(email: str) -> dict | None:
    return _USERS.get(email.strip().lower())


# ── Fire-and-forget helper ─────────────────────────────────────────────────
async def _publish_async(channel: str, message: dict):
    """Publish to Redis without blocking the caller."""
    try:
        from backend.redis_client import get_redis
        redis = get_redis()
        await redis.publish(channel, message)
    except Exception:
        pass  # Redis unavailable, silently ignore

# ── Request / Response Models ─────────────────────────────────────────────────

class AddAccountRequest(BaseModel):
    id: str
    name: str = ""
    login: int
    password: str = ""
    server: str = ""
    terminal_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    symbols: list[str] = Field(default_factory=lambda: ["XAUUSD", "EURUSD"])
    enabled: bool = True

class StartBotRequest(BaseModel):
    account_id: Optional[str] = None
    params: dict = Field(default_factory=dict)

# ── Bot Manager ───────────────────────────────────────────────────────────────

_BOTS_DIR = Path(__file__).resolve().parent.parent / "bots"
_ACTIVE_BOTS_DIR = _BOTS_DIR / "active_bots"

# Legacy hardcoded bot scripts (backward compatibility)
_LEGACY_BOT_SCRIPTS: dict[str, Path] = {
    "gold_bot": _BOTS_DIR / "gold_bot_v3.py",
    "scalping_bot": _BOTS_DIR / "scalping_youtube_goldstrategy.py",
    "streaming_bot": _BOTS_DIR / "streaming_bot_v3.py",
    "gold_phoenix": _BOTS_DIR / "gold_phoenix_bot.py",
    "scalping_hybrid": _BOTS_DIR / "scalping_phoenix_hybrid.py",
}

# Map strategy names (as used in run_<strategy>.py filenames) to display names
_STRATEGY_DISPLAY_MAP: dict[str, str] = {
    "macd": "MACD",
    "goldphoenix": "GoldPhoenix",
    "bollinger": "Bollinger",
    "sma": "SMA",
    "volatility_breakout": "VolatilityBreakout",
}


def _strategy_display_name(raw: str) -> str:
    """Return the display name for a strategy key (e.g. 'macd' -> 'MACD')."""
    return _STRATEGY_DISPLAY_MAP.get(raw, raw.capitalize())


def _discover_bots() -> dict[str, Path]:
    """Discover all available bot scripts (legacy + multi-pair).

    Scans:
      1. Legacy scripts in bots/ directory (if they exist on disk).
      2. Multi-pair run scripts in bots/active_bots/<PAIR>/run_<strategy>.py
         named ``{StrategyDisplay}_{PAIR}`` (e.g. ``MACD_EURUSD``).
    """
    bots: dict[str, Path] = {}

    # 1. Legacy bots — include only if the script file actually exists
    for name, script_path in _LEGACY_BOT_SCRIPTS.items():
        if script_path.exists():
            bots[name] = script_path.resolve()
        else:
            logger.debug("Legacy bot script not found, skipping: %s", script_path)

    # 2. Multi-pair bots — discover all run_*.py under active_bots/
    if _ACTIVE_BOTS_DIR.is_dir():
        pair_dirs: list[Path] = sorted(
            d for d in _ACTIVE_BOTS_DIR.iterdir() if d.is_dir()
        )
        for pair_dir in pair_dirs:
            pair = pair_dir.name.upper()
            run_files: list[Path] = sorted(pair_dir.glob("run_*.py"))
            for run_file in run_files:
                strategy_raw = run_file.stem[len("run_"):]
                strategy_display = _strategy_display_name(strategy_raw)
                bot_name = f"{strategy_display}_{pair}"
                bots[bot_name] = run_file.resolve()

    logger.info("Discovered %d bot scripts", len(bots))
    return bots


# Module-level dict — refreshed on startup and on-demand
BOT_SCRIPTS: dict[str, Path] = _discover_bots()
_bot_processes: dict[str, subprocess.Popen] = {}


def _refresh_bot_scripts():
    """Re-discover bot scripts and update the module-level ``BOT_SCRIPTS`` dict."""
    global BOT_SCRIPTS
    BOT_SCRIPTS = _discover_bots()


def _scan_running_bots():
    """Scan for existing pythonw processes running our bot scripts using psutil."""
    _refresh_bot_scripts()
    import psutil as _psutil
    for name, script_path in BOT_SCRIPTS.items():
        try:
            if not script_path or not script_path.exists():
                continue
            target_name = script_path.name.lower()
            for proc in _psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and 'python' not in proc.info['name'].lower():
                        continue
                    cmdline = proc.info.get('cmdline') or []
                    cmd_str = ' '.join(cmdline).lower()
                    if target_name in cmd_str:
                        process_pid = proc.info['pid']
                        logger.info("Found running bot '%s' (PID %d)", name, process_pid)
                        _bot_processes[name] = _make_running_proc(process_pid)
                        break
                except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.debug("Could not scan bot '%s': %s", name, e)


def _make_running_proc(process_pid: int):
    """Create a process-like wrapper for an already-running bot."""
    import psutil as _psutil
    import asyncio

    class _RunningProc:
        _pid = process_pid

        def poll(self):
            return None

        @property
        def pid(self):
            return self._pid

        def terminate(self):
            try:
                _psutil.Process(self._pid).terminate()
            except Exception:
                pass

        def kill(self):
            try:
                _psutil.Process(self._pid).kill()
            except Exception:
                pass

        async def wait(self, timeout=None):
            import time
            _start = time.time()
            while timeout is None or time.time() - _start < timeout:
                try:
                    p = _psutil.Process(self._pid)
                    if not p.is_running():
                        return 0
                except _psutil.NoSuchProcess:
                    return 0
                await asyncio.sleep(0.5)
            return 0

    return _RunningProc()

def _get_bot_script(name: str) -> Path:
    script = BOT_SCRIPTS.get(name)
    if not script:
        raise HTTPException(status_code=404, detail=f"Unknown bot: {name}")
    if not script.exists():
        raise HTTPException(status_code=500, detail=f"Bot script not found: {script}")
    return script

def _log_bot_decision(agent_name: str, action: str, detail: str, outcome: str = "success"):
    """Log a bot action to the decision_log and agent_logs."""
    try:
        _dl_path = Path(__file__).resolve().parent.parent / "scripts"
        sys.path.insert(0, str(_dl_path))
        import importlib
        dl = importlib.import_module("decision_log")
        importlib.reload(dl)
        dl.log_decision(
            agent_id=agent_name,
            agent_name=agent_name.replace("_", " ").title(),
            action=action,
            detail=detail,
            outcome=outcome,
            metadata={"source": "bot_controller"},
        )
        # Also save agent log for orchestrator
        try:
            db = get_db()
            db.save_agent_log(
                agent_name=agent_name,
                task=action,
                decision=action,
                outcome=outcome,
                metadata={"detail": detail, "source": "bot_controller"},
            )
        except Exception:
            pass
    except Exception:
        pass


def _seed_decision_log():
    """Seed decision log with sample entries if empty."""
    try:
        _dl_path = Path(__file__).resolve().parent.parent / "scripts"
        sys.path.insert(0, str(_dl_path))
        import importlib
        dl = importlib.import_module("decision_log")
        importlib.reload(dl)
        entries = dl.get_decisions(days=365, limit=1)
        if entries:
            return  # already has entries
        # Seed with historical entries
        now = datetime.now(timezone.utc)
        samples = [
            ("gold_bot", "Bot Started", "Gold Bot v3 deployed on XAUUSD", "success"),
            ("scalping_bot", "Bot Started", "Scalping strategy deployed on EURUSD", "success"),
            ("gold_phoenix", "Bot Stopped", "Gold Phoenix bot completed daily cycle", "success"),
        ]
        for agent_name, action, detail, outcome in samples:
            try:
                dl.log_decision(
                    agent_id=agent_name,
                    agent_name=agent_name.replace("_", " ").title(),
                    action=action,
                    detail=detail,
                    outcome=outcome,
                    metadata={"source": "seed", "timestamp_hint": now.isoformat()},
                )
            except Exception:
                pass
        logger.info("Seeded %d decision log entries", len(samples))
    except Exception:
        pass


async def _start_bot_process(name: str, script: Path) -> dict:
    if name in _bot_processes:
        proc = _bot_processes[name]
        if hasattr(proc, 'poll') and proc.poll() is None:
            raise HTTPException(status_code=409, detail=f"Bot '{name}' is already running")

    try:
        import subprocess
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(script.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, 'DETACHED_PROCESS') else 0,
        )
        _bot_processes[name] = proc
        db = get_db()
        db.upsert_bot({
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "script_path": str(script),
            "status": "running",
            "pid": proc.pid,
            "last_started": datetime.now(timezone.utc).isoformat(),
        })
        asyncio.create_task(_publish_async(f"bots:{name}", {"type": "bot_status", "status": "running", "pid": proc.pid}))
        # Log decision
        _log_bot_decision(name, "Bot Started", f"Bot '{name}' started (PID {proc.pid})")
        return {"name": name, "status": "running", "pid": proc.pid}
    except Exception as e:
        _log_bot_decision(name, "Bot Start Failed", f"Failed to start bot '{name}': {e}", "error")
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {e}")

async def _stop_bot_process(name: str) -> dict:
    if name not in _bot_processes:
        raise HTTPException(status_code=404, detail=f"Bot '{name}' is not running")

    proc = _bot_processes[name]
    if proc.poll() is not None:
        del _bot_processes[name]
        raise HTTPException(status_code=404, detail=f"Bot '{name}' already exited")

    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        pid = proc.pid
        del _bot_processes[name]

        db = get_db()
        db.upsert_bot({
            "name": name,
            "status": "stopped",
            "pid": None,
            "last_stopped": datetime.now(timezone.utc).isoformat(),
        })
        asyncio.create_task(_publish_async(f"bots:{name}", {"type": "bot_status", "status": "stopped", "pid": pid}))
        # Log decision
        _log_bot_decision(name, "Bot Stopped", f"Bot '{name}' stopped (PID {pid})")
        return {"name": name, "status": "stopped", "pid": pid}
    except Exception as e:
        _log_bot_decision(name, "Bot Stop Failed", f"Failed to stop bot '{name}': {e}", "error")
        raise HTTPException(status_code=500, detail=f"Failed to stop bot: {e}")

def _get_bot_status(name: str) -> dict:
    proc = _bot_processes.get(name)
    running = proc is not None and hasattr(proc, 'poll') and proc.poll() is None
    pid = proc.pid if hasattr(proc, 'pid') and running else None
    return {
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "running": running,
        "pid": pid,
        "script": str(BOT_SCRIPTS.get(name, "")),
    }

# ── Lifespan ──────────────────────────────────────────────────────────────────

def _seed_accounts_from_store():
    """Ensure mt5-demo and ftmo-demo accounts exist in the DB store."""
    store_path = Path(__file__).resolve().parent / "db" / "agentx_store.json"
    if not store_path.exists():
        logger.warning("agentx_store.json not found at %s", store_path)
        return
    try:
        with open(store_path, "r") as f:
            data = json.load(f)
        accounts = data.get("accounts", [])
        db = get_db()
        existing = {a["id"] for a in db.get_accounts()}
        for acct in accounts:
            if acct["id"] not in existing:
                db.save_account(acct)
                logger.info("Seeded account '%s' (%s) from agentx_store.json", acct["id"], acct.get("name", ""))
        logger.info("Account seeding complete: %d in store, %d already in DB", len(accounts), len(existing))
    except Exception as e:
        logger.error("Failed to seed accounts from agentx_store.json: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AGENTX Backend starting (v%s)", __version__)
    _seed_users()
    _seed_accounts_from_store()
    _scan_running_bots()

    # Refresh bot scripts to catch any new multi-pair bots
    _refresh_bot_scripts()

    # Auto-start any bots not already running
    started_count = 0
    for name, script_path in list(BOT_SCRIPTS.items()):
        if name in _bot_processes and _bot_processes[name].poll() is None:
            logger.info("Bot '%s' already running (PID %d)", name, _bot_processes[name].pid)
            continue
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script_path)],
                cwd=str(script_path.parent.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _bot_processes[name] = proc
            started_count += 1
            logger.info("Auto-started bot '%s' (PID %d)", name, proc.pid)
        except Exception as e:
            logger.error("Failed to auto-start bot '%s': %s", name, e)

    logger.info("Auto-started %d/%d bots", started_count, len(BOT_SCRIPTS))

    # Seed decision log with entries if empty
    _seed_decision_log()

    yield
    for name, proc in list(_bot_processes.items()):
        if proc.poll() is None:
            proc.terminate()
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: proc.wait(timeout=3))
            except Exception:
                proc.kill()
    logger.info("AGENTX Backend stopped")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AGENTX API",
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

# ── Block scanner traffic (WordPress exploitation probes) ────────────────

@app.middleware("http")
async def block_scanners(request: Request, call_next):
    path = request.url.path
    if path.endswith(".php") or "/wp-" in path or "/xmlrpc" in path:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    response = await call_next(request)
    return response

# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.get("/api/auth/login")
async def auth_login():
    if is_google_configured():
        return RedirectResponse(url=get_google_auth_url())
    return JSONResponse({
        "oauth_configured": False,
        "dev_mode": True,
        "message": "Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
    })

@app.get("/api/auth/callback")
async def auth_callback(code: str = "", state: str = "", request: Request = None):
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")
    userinfo = await exchange_code(code)
    if not userinfo or "email" not in userinfo:
        raise HTTPException(status_code=401, detail="Authentication failed")
    email = userinfo["email"].strip().lower()
    expected = OWNER_EMAIL.strip().lower()
    if email != expected:
        raise HTTPException(status_code=403, detail=f"Access denied: {email} is not authorized")
    response = RedirectResponse(url="/")
    response.set_cookie(
        key=SESSION_COOKIE,
        value=email,
        max_age=86400 * 7,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https" if request else False,
    )
    return response

@app.post("/api/auth/dev-login")
async def dev_login(email: str = OWNER_EMAIL, request: Request = None):
    response = JSONResponse({"email": email, "status": "authenticated"})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=email,
        max_age=86400 * 7,
        httponly=True,
        samesite="lax",
    )
    return response

@app.post("/api/auth/logout")
async def auth_logout():
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(key=SESSION_COOKIE)
    return response

# ── Access Codes (5-Tester System) ──────────────────────────────────────────

@app.get("/api/auth/codes")
async def get_access_codes(auth=Depends(require_auth)):
    """List all access codes with their status (admin only)."""
    return {"codes": list_access_codes()}

@app.post("/api/auth/codes/generate")
async def create_access_codes(auth=Depends(require_auth)):
    """Generate 5 fresh access codes for testers."""
    codes = generate_access_codes(5)
    return {"status": "created", "count": len(codes), "codes": codes}

@app.post("/api/auth/redeem")
async def redeem_access_code(code: str = "", label: str = "", request: Request = None):
    """Redeem an access code and get a session cookie."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing access code")
    codes = list_access_codes()
    found = None
    for c in codes:
        if c["code"] == code:
            found = c
            break
    if not found:
        raise HTTPException(status_code=403, detail="Invalid access code")
    if found["claimed"]:
        raise HTTPException(status_code=403, detail="Access code already used")
    claimer = label or f"tester_{code[:6]}"
    claim_access_code(code, claimer)
    response = JSONResponse({"status": "authenticated", "label": claimer})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=claimer,
        max_age=None,  # Session cookie — lasts until browser closes
        httponly=True,
        samesite="lax",
    )
    return response

# ── Dev-mode Auth Endpoints (for frontend SPA compatibility) ─────────────

@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Return current user from session or dev default."""
    session = request.cookies.get(SESSION_COOKIE)
    if session:
        return {"email": session, "name": session, "sub": session}
    # Dev mode: return default owner
    return {"email": OWNER_EMAIL, "name": "Commander", "sub": "dev-user"}

@app.post("/api/auth/signin")
async def auth_signin(request: Request):
    """Dev-mode signin — verifies email/password against user store."""
    try:
        body = await request.json()
        email = body.get("email", "").strip().lower()
        password = body.get("password", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    user = _get_user(email)
    if not user or not _verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    response = JSONResponse({"email": email, "status": "authenticated", "name": email.split("@")[0]})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=email,
        max_age=86400 * 7,
        httponly=True,
        samesite="lax",
    )
    return response

@app.post("/api/auth/signup")
async def auth_signup(request: Request):
    """Dev-mode signup — stores user in the user store."""
    try:
        body = await request.json()
        email = body.get("email", "").strip().lower()
        password = body.get("password", "")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if _get_user(email):
        raise HTTPException(status_code=409, detail="User already exists")
    _USERS[email] = {
        "password_hash": _hash_password(password),
        "name": email.split("@")[0],
        "role": "user",
    }
    logger.info("User created: %s", email)
    response = JSONResponse({"email": email, "status": "created", "name": email.split("@")[0]})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=email,
        max_age=86400 * 7,
        httponly=True,
        samesite="lax",
    )
    return response

# ── WebSocket Proxy ──────────────────────────────────────────────────────────

@app.websocket("/api/ws/{path:path}")
async def ws_proxy(websocket: WebSocket, path: str):
    """Proxy WebSocket connections to the MT5 Bridge."""
    import asyncio
    import httpx
    import json as json_module

    await websocket.accept()
    bridge_ws_url = f"ws://127.0.0.1:5000/{path}"

    try:
        async with websockets.connect(bridge_ws_url) as bridge_ws:
            # Bidirectional relay
            async def relay_to_client():
                try:
                    async for message in bridge_ws:
                        await websocket.send_text(message)
                except Exception:
                    pass

            async def relay_to_bridge():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await bridge_ws.send(data)
                except Exception:
                    pass

            await asyncio.gather(
                relay_to_client(),
                relay_to_bridge(),
            )
    except websockets.exceptions.WebSocketException as e:
        # If bridge websocket fails, fall back to HTTP polling data
        try:
            # Send a one-time health/tick snapshot via JSON
            if path == "system":
                bridge = get_bridge()
                health = await bridge.health()
                await websocket.send_json({
                    "type": "health",
                    "data": health,
                    "fallback": True,
                    "message": "Bridge WebSocket unavailable, using polling"
                })
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Cannot connect to bridge WebSocket: {e}"
                })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    bridge = get_bridge()
    db = get_db()
    redis = get_redis()
    bridge_health = {"connected": False, "error": None}
    try:
        bridge_raw = await bridge.health()
        bridge_health = {"connected": True, "data": bridge_raw}
    except HTTPException as e:
        bridge_health = {"connected": False, "error": e.detail}
    except Exception as e:
        bridge_health = {"connected": False, "error": str(e)}

    # Test database by actually reading a record
    database_health = {"connected": False}
    try:
        accounts = db.get_accounts()
        trades = db.get_trades(limit=1)
        database_health = {
            "connected": True,
            "account_count": len(accounts),
            "trade_count": len(db.get_trades()),
        }
    except Exception as e:
        database_health = {"connected": False, "error": str(e)}

    return {
        "status": "ok",
        "version": __version__,
        "uptime_seconds": round(time.time() - _start_time, 2),
        "bridge": bridge_health,
        "database": database_health,
        "redis": {"connected": redis.connected},
        "time": datetime.now(timezone.utc).isoformat(),
    }

# ── Magic Numbers Configuration ───────────────────────────────────────────────

@app.get("/api/config/magic-numbers")
async def get_magic_numbers():
    return {
        "gold_bot": 777556,
        "scalping_bot": 999112,
        "streaming_bot": 666334,
        "gold_phoenix": 777888,
    }

# ── Consolidated Stats ────────────────────────────────────────────────────────

@app.get("/api/stats")
async def consolidated_stats():
    """Aggregate positions, trades, and bridge data for a quick trading overview."""
    bridge = get_bridge()
    db = get_db()
    
    # Use default account ID
    account_id = "default"
    
    stats = {
        "total_positions": 0,
        "open_positions": 0,
        "total_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "net_pnl": 0.0,
        "total_volume": 0.0,
        "balance": 0.0,
        "equity": 0.0,
        "max_drawdown": 0.0,
        "best_account": {"name": "", "balance": 0.0, "equity": 0.0},
        "equity_history": [],
        "bot_statuses": [],
    }

    # ── Positions ──────────────────────────────────────────────────────────
    try:
        positions = await bridge.get_positions()
        stats["total_positions"] = len(positions)
        stats["open_positions"] = sum(
            1 for p in positions if p.get("type") != "closed" and p.get("profit") is not None
        )
    except Exception:
        pass

    # ── Bridge stats (most reliable source for trade data) ──────────────────
    try:
        bstats = await bridge.get_stats(account_id, days=30)
        stats["total_trades"] = bstats.get("total_trades", 0)
        stats["win_rate"] = bstats.get("win_rate", 0.0)
        stats["profit_factor"] = bstats.get("profit_factor", 0.0)
        stats["net_pnl"] = bstats.get("net_profit", 0.0)
        stats["total_volume"] = bstats.get("total_volume", 0.0)
        stats["balance"] = bstats.get("balance", 0.0)
        stats["equity"] = bstats.get("equity", 0.0)
        stats["max_drawdown"] = bstats.get("max_drawdown", 0.0)
    except Exception:
        pass

    # ── Best Account ───────────────────────────────────────────────────────
    try:
        bridge_accounts = await bridge.list_accounts()
        best = {"name": "", "balance": 0.0, "equity": 0.0}
        for acct in bridge_accounts:
            acct_id = acct.get("id", "")
            if not acct_id:
                continue
            try:
                info = await bridge.get_account(acct_id)
                balance = float(info.get("balance", 0) or 0)
                equity = float(info.get("equity", 0) or 0)
                if balance > best["balance"]:
                    best = {
                        "name": info.get("name", acct.get("name", acct_id)),
                        "balance": balance,
                        "equity": equity,
                    }
                    # Also promote best balance/equity to top-level fields
                    stats["balance"] = balance
                    stats["equity"] = equity
            except Exception:
                continue
        stats["best_account"] = best
    except Exception:
        pass

    # ── Equity History ────────────────────────────────────────────────────
    try:
        equity_data = await bridge.get_equity(account_id, days=30)
        stats["equity_history"] = equity_data if isinstance(equity_data, list) else []
    except Exception:
        pass

    # ── Bot Statuses ───────────────────────────────────────────────────────
    try:
        _refresh_bot_scripts()
        bot_statuses = []
        for name in BOT_SCRIPTS:
            status = _get_bot_status(name)
            bot_statuses.append({
                "name": status["name"],
                "running": status["running"],
                "pid": status["pid"],
                "magic": None,
            })
        stats["bot_statuses"] = bot_statuses
    except Exception:
        pass

    return stats

# ── Account Endpoints ─────────────────────────────────────────────────────────

@app.get("/api/accounts")
async def list_accounts(auth=Depends(require_auth)):
    bridge = get_bridge()
    db = get_db()
    try:
        bridge_accounts = await bridge.list_accounts()
    except HTTPException:
        bridge_accounts = []
    db_accounts = db.get_accounts()
    merged = {a["id"]: a for a in bridge_accounts}
    for a in db_accounts:
        if a["id"] in merged:
            merged[a["id"]].update({"name": a["name"], "enabled": a.get("enabled", True)})
        else:
            merged[a["id"]] = {
                "id": a["id"],
                "name": a["name"],
                "login": a["login"],
                "server": a["server"],
                "connected": False,
                "stale": False,
                "last_error": "Not configured in bridge",
                "enabled": a.get("enabled", True),
            }
    # Enrich with balance/equity from bridge account details
    for acct in merged.values():
        if acct.get("connected"):
            try:
                info = await bridge.get_account(acct["id"])
                if isinstance(info, dict):
                    acct["balance"] = float(info.get("balance", 0) or 0)
                    acct["equity"] = float(info.get("equity", 0) or 0)
                    acct["profit"] = float(info.get("profit", 0) or 0)
            except Exception as exc:
                logger.warning("Failed to fetch account detail for %s: %s", acct["id"], exc)
    return list(merged.values())

@app.get("/api/accounts/active")
async def active_account_route(auth=Depends(require_auth)):
    db = get_db()
    active_id = db.get_active_account()
    if not active_id:
        return {"active_account_id": None, "account": None}
    bridge = get_bridge()
    try:
        info = await bridge.get_account(active_id)
    except HTTPException:
        db_acct = db.get_account(active_id)
        if not db_acct:
            db.set_active_account(None)
            return {"active_account_id": None, "account": None}
        info = {
            "login": db_acct["login"],
            "name": db_acct["name"],
            "server": db_acct["server"],
            "connected": False,
            "stale": True,
        }
    try:
        bridge_health = await bridge.health()
        is_connected = (
            bridge_health.get("connected", False)
            and any(a.get("id") == active_id and a.get("connected", False)
                    for a in bridge_health.get("accounts", []))
        )
        info["connected"] = is_connected
        info["stale"] = not is_connected
    except Exception:
        pass
    db_acct = db.get_account(active_id)
    if db_acct:
        info["id"] = db_acct["id"]
        info["enabled"] = db_acct.get("enabled", True)
    return {"active_account_id": active_id, "account": info}

@app.post("/api/accounts/{account_id}/switch")
async def switch_account(account_id: str, auth=Depends(require_auth)):
    bridge = get_bridge()
    db = get_db()
    try:
        info = await bridge.get_account(account_id)
    except HTTPException:
        db_acct = db.get_account(account_id)
        if not db_acct:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")
        info = {"login": db_acct["login"], "name": db_acct["name"], "server": db_acct["server"], "connected": False, "stale": True}
        info["id"] = db_acct["id"]
        info["enabled"] = db_acct.get("enabled", True)
        db.set_active_account(account_id)
        return {"status": "switched", "active_account_id": account_id, "account": info}
    try:
        bridge_health = await bridge.health()
        is_connected = (
            bridge_health.get("connected", False)
            and any(a.get("id") == account_id and a.get("connected", False)
                    for a in bridge_health.get("accounts", []))
        )
        info["connected"] = is_connected
        info["stale"] = not is_connected
    except Exception:
        pass
    db_acct = db.get_account(account_id)
    if db_acct:
        info["id"] = db_acct["id"]
        info["enabled"] = db_acct.get("enabled", True)
    db.set_active_account(account_id)
    return {"status": "switched", "active_account_id": account_id, "account": info}

@app.get("/api/accounts/{account_id}")
async def account_detail(account_id: str, auth=Depends(require_auth)):
    bridge = get_bridge()
    db = get_db()
    try:
        info = await bridge.get_account(account_id)
    except HTTPException as e:
        db_acct = db.get_account(account_id)
        if not db_acct:
            raise e
        info = {
            "login": db_acct["login"],
            "name": db_acct["name"],
            "server": db_acct["server"],
            "connected": False,
            "stale": True,
        }
    # Override connected flag with bridge health (account detail can be stale
    # while bridge is still streaming live ticks — trust health over detail)
    try:
        bridge_health = await bridge.health()
        is_connected = (
            bridge_health.get("connected", False)
            and any(a.get("id") == account_id and a.get("connected", False)
                    for a in bridge_health.get("accounts", []))
        )
        info["connected"] = is_connected
        info["stale"] = not is_connected
    except Exception:
        pass  # keep whatever the bridge returned
    db_acct = db.get_account(account_id)
    if db_acct:
        info["id"] = db_acct["id"]
        info["enabled"] = db_acct.get("enabled", True)
    return info

@app.post("/api/accounts")
async def add_account(req: AddAccountRequest, auth=Depends(require_auth)):
    db = get_db()
    from bridge.config import AccountConfig, encrypt_password
    encrypted = ""
    if req.password:
        encrypted = encrypt_password(req.password)
    acct = {
        "id": req.id,
        "name": req.name or req.id,
        "login": req.login,
        "password_encrypted": encrypted,
        "server": req.server,
        "terminal_path": req.terminal_path,
        "symbols": req.symbols,
        "enabled": req.enabled,
    }
    db.save_account(acct)
    logger.info("Account saved: id=%s login=%s", acct["id"], acct["login"])
    return {"status": "created", "account": acct}

@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: str, auth=Depends(require_auth)):
    db = get_db()
    removed = db.delete_account(account_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "deleted", "account_id": account_id}

class TestConnectionResponse(PydanticBaseModel):
    success: bool
    balance: float = 0
    server: str = ""
    error: str = ""

@app.post("/api/accounts/{account_id}/test")
async def test_account_connection(account_id: str, auth=Depends(require_auth)):
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from bridge.config import load_accounts
    from bridge.mt5_manager import MT5Manager, get_manager

    accounts = load_accounts()
    acct = next((a for a in accounts if a.id == account_id), None)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not configured")

    cfg = acct.to_mt5_config()
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
        init_kwargs = {"path": cfg.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe")}
        if cfg.get("login") and cfg.get("password") and cfg.get("server"):
            init_kwargs["login"] = int(cfg["login"])
            init_kwargs["password"] = str(cfg["password"])
            init_kwargs["server"] = str(cfg["server"])
        if not mt5.initialize(**init_kwargs):
            err = mt5.last_error()
            mt5.shutdown()
            return {"success": False, "balance": 0, "server": "", "error": str(err)}
        acc = mt5.account_info()
        if acc is None:
            err = mt5.last_error()
            mt5.shutdown()
            return {"success": False, "balance": 0, "server": "", "error": str(err)}
        result = {"success": True, "balance": round(acc.balance, 2), "server": acc.server, "error": ""}
        mt5.shutdown()
        return result
    except ImportError:
        return {"success": False, "balance": 0, "server": "", "error": "MetaTrader5 package not installed"}
    except Exception as e:
        return {"success": False, "balance": 0, "server": "", "error": str(e)}

# ── Positions Endpoints ───────────────────────────────────────────────────────

@app.get("/api/positions")
async def all_positions(auth=Depends(require_auth)):
    bridge = get_bridge()
    positions = await bridge.get_positions()
    # Normalize to ensure PnL (profit) is present per position
    normalized = []
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        profit = pos.get("profit") or pos.get("pnl") or pos.get("net_profit") or 0
        if profit is None:
            profit = 0
        pos["pnl"] = float(profit)
        pos["profit"] = float(profit)
        normalized.append(pos)
    return normalized

@app.get("/api/positions/{ticket}")
async def position_detail(ticket: int, auth=Depends(require_auth)):
    bridge = get_bridge()
    positions = await bridge.get_positions()
    for pos in positions:
        if pos.get("ticket") == ticket:
            return pos
    raise HTTPException(status_code=404, detail=f"Position ticket {ticket} not found")

# ── Test Bot Endpoints ──────────────────────────────────────────────────────────

_test_bot_proc: Optional[subprocess.Popen] = None

@app.post("/api/bots/test/start")
async def test_bot_start():
    """Start the test bot (opens 0.01 BUY XAUUSD, holds 20s, closes)."""
    global _test_bot_proc

    if _test_bot_proc is not None and _test_bot_proc.poll() is None:
        raise HTTPException(status_code=409, detail="Test bot is already running")

    script = _BOTS_DIR / "test_bot.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail=f"test_bot.py not found at {script}")

    try:
        # Use pythonw for headless execution on Windows
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # fall back to python if pythonw not found

        proc = subprocess.Popen(
            [pythonw, str(script)],
            cwd=str(_BOTS_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, 'DETACHED_PROCESS') else 0,
        )
        _test_bot_proc = proc
        logger.info("Test bot started (PID %d)", proc.pid)
        return {"name": "test_bot", "status": "running", "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start test bot: {e}")


@app.get("/api/bots/test/status")
async def test_bot_status():
    """Check if the test bot is currently running."""
    global _test_bot_proc

    if _test_bot_proc is None:
        return {"name": "test_bot", "running": False, "pid": None}

    poll = _test_bot_proc.poll()
    running = poll is None
    return {
        "name": "test_bot",
        "running": running,
        "pid": _test_bot_proc.pid if running else None,
        "exit_code": poll if not running else None,
    }


@app.post("/api/bots/test/stop")
async def test_bot_stop():
    """Stop the test bot."""
    global _test_bot_proc

    if _test_bot_proc is None or _test_bot_proc.poll() is not None:
        _test_bot_proc = None
        raise HTTPException(status_code=404, detail="Test bot is not running")

    try:
        _test_bot_proc.terminate()
        try:
            await asyncio.wait_for(_test_bot_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            _test_bot_proc.kill()
            await _test_bot_proc.wait()
        pid = _test_bot_proc.pid
        _test_bot_proc = None
        logger.info("Test bot stopped (PID %d)", pid)
        return {"name": "test_bot", "status": "stopped", "pid": pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop test bot: {e}")


# ── Bot Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/bots")
async def list_bots(auth=Depends(require_auth)):
    _scan_running_bots()  # Live re-scan every time (also refreshes BOT_SCRIPTS)
    bots = []
    for name in sorted(BOT_SCRIPTS.keys()):
        bots.append(_get_bot_status(name))
    db = get_db()
    db_bots = db.get_bots()
    db_map = {b["name"]: b for b in db_bots}
    for bot in bots:
        if bot["name"] in db_map:
            bot["config"] = db_map[bot["name"]].get("config", {})
    return bots


@app.get("/api/bots/config")
async def bot_config(auth=Depends(require_auth)):
    """Return per-pair bot assignments and metadata for the frontend."""
    _refresh_bot_scripts()
    config = {
        "legacy_bots": [],
        "multi_pair": {},
    }
    legacy_names = set(_LEGACY_BOT_SCRIPTS.keys())
    for name, script_path in BOT_SCRIPTS.items():
        entry = {
            "name": name,
            "script": str(script_path),
            "exists": script_path.exists(),
        }
        if name in legacy_names:
            config["legacy_bots"].append(entry)
        else:
            # Multi-pair bot: extract pair and strategy from name
            # Names are like "MACD_EURUSD" or "GoldPhoenix_XAUUSD"
            parts = name.split("_", 1)
            strategy_part = parts[0] if len(parts) == 2 else ""
            pair_part = parts[1] if len(parts) == 2 else ""
            config["multi_pair"][name] = {
                **entry,
                "pair": pair_part,
                "strategy": strategy_part,
            }
    return config


@app.post("/api/bots/{name}/start")
async def start_bot(name: str, req: StartBotRequest = None, auth=Depends(require_auth)):
    if name == "test":
        return await test_bot_start()
    script = _get_bot_script(name)
    result = await _start_bot_process(name, script)
    asyncio.create_task(_publish_async(f"bots:{name}", {"type": "bot_status", "status": "started"}))
    return result

@app.post("/api/bots/{name}/stop")
async def stop_bot(name: str, auth=Depends(require_auth)):
    if name == "test":
        return await test_bot_stop()
    result = await _stop_bot_process(name)
    asyncio.create_task(_publish_async(f"bots:{name}", {"type": "bot_status", "status": "stopped"}))
    return result

@app.get("/api/bots/{name}/status")
async def bot_status(name: str, auth=Depends(require_auth)):
    if name == "test":
        return await test_bot_status()
    if name not in BOT_SCRIPTS:
        raise HTTPException(status_code=404, detail=f"Unknown bot: {name}")
    return _get_bot_status(name)

@app.delete("/api/bots/{name}")
async def delete_bot(name: str, auth=Depends(require_auth)):
    if name not in BOT_SCRIPTS:
        raise HTTPException(status_code=404, detail=f"Unknown bot: {name}")
    if name in _bot_processes:
        proc = _bot_processes[name]
        if proc.poll() is None:
            await _stop_bot_process(name)
    db = get_db()
    existing = db.get_bot(name)
    if existing:
        db.delete_bot(name)
    return {"status": "deleted", "name": name}

# ── Bridge Proxy Endpoints ────────────────────────────────────────────────────

@app.get("/api/bridge/accounts/{account_id}/history")
async def proxy_history(account_id: str, days: int = 30, auth=Depends(require_auth)):
    bridge = get_bridge()
    trades = await bridge.get_trades(account_id, days)
    db = get_db()
    db.upsert_trades(account_id, trades)
    # Fire-and-forget redis publish (don't block response)
    asyncio.create_task(_publish_async(f"trades:{account_id}", {"type": "trades_synced", "count": len(trades)}))
    return trades

@app.get("/api/bridge/accounts/{account_id}/equity")
async def proxy_equity(account_id: str, days: int = 30, auth=Depends(require_auth)):
    bridge = get_bridge()
    return await bridge.get_equity(account_id, days)

@app.get("/api/bridge/accounts/{account_id}/positions")
async def proxy_positions(account_id: str, auth=Depends(require_auth)):
    bridge = get_bridge()
    return await bridge.get_positions(account_id)

@app.get("/api/bridge/accounts/{account_id}/stats")
async def proxy_stats(account_id: str, days: int = 30, auth=Depends(require_auth)):
    bridge = get_bridge()
    return await bridge.get_stats(account_id, days)

@app.get("/api/bridge/accounts/{account_id}/tick/{symbol}")
async def proxy_tick(account_id: str, symbol: str, auth=Depends(require_auth)):
    bridge = get_bridge()
    tick = await bridge.get_tick(account_id, symbol.upper())
    asyncio.create_task(_publish_async(f"tick:{symbol}:{account_id}", tick))
    return tick

# ── Diagnostics ───────────────────────────────────────────────────────────────

@app.get("/api/diagnostic")
async def api_diagnostic(auth=Depends(require_auth)):
    bridge = get_bridge()
    try:
        diag = await bridge._get("/diagnostic")
    except HTTPException:
        diag = {"error": "bridge_unreachable"}
    return {
        "backend_version": __version__,
        "backend_uptime": round(time.time() - _start_time, 2),
        "bridge": diag,
    }

# ── Trade Tags & Notes Endpoints ─────────────────────────────────────────

from pydantic import BaseModel as PydanticBaseModel

class UpdateTagsRequest(PydanticBaseModel):
    tags: list[str]

class UpdateNotesRequest(PydanticBaseModel):
    notes: str

@app.post("/api/trades/{ticket}/tags")
async def update_trade_tags(ticket: int, req: UpdateTagsRequest, auth=Depends(require_auth)):
    db = get_db()
    db.execute(
        "UPDATE trades SET tags = %s WHERE position_id = %s",
        (req.tags, ticket),
    )
    return {"status": "ok", "ticket": ticket, "tags": req.tags}

@app.post("/api/trades/{ticket}/notes")
async def update_trade_notes(ticket: int, req: UpdateNotesRequest, auth=Depends(require_auth)):
    db = get_db()
    db.execute(
        "UPDATE trades SET notes = %s WHERE position_id = %s",
        (req.notes, ticket),
    )
    return {"status": "ok", "ticket": ticket, "notes": req.notes}

@app.get("/api/trades/filter")
async def filter_trades(
    days: int = 30,
    magic: Optional[int] = None,
    symbol: Optional[str] = None,
    bot_magic: Optional[int] = None,
    outcome: Optional[str] = None,
    account_id: str = "default",
    auth=Depends(require_auth),
):
    bridge = get_bridge()
    raw_trades = await bridge.get_trades(account_id, days)

    # Merge magic and bot_magic params
    filter_magic = magic if magic is not None else bot_magic

    # Normalise every trade to a consistent schema
    def normalise(t: dict) -> dict:
        # Determine direction
        typ = t.get("type", "")
        direction = "buy"
        if isinstance(typ, str):
            dl = typ.lower()
            if dl in ("sell", "short", "close_sell"):
                direction = "sell"
        elif isinstance(typ, (int, float)):
            direction = "buy" if typ > 0 else "sell"

        profit = t.get("profit") or t.get("pnl") or t.get("net_profit") or 0
        if profit is None:
            profit = 0

        volume = t.get("volume") or t.get("lots") or t.get("size") or 0

        return {
            "pair": t.get("symbol") or t.get("pair", ""),
            "open_time": t.get("open_time") or t.get("entry_time") or t.get("time", ""),
            "close_time": t.get("close_time") or t.get("exit_time", ""),
            "profit": float(profit),
            "volume": float(volume),
            "direction": direction,
            "magic": t.get("magic", 0),
        }

    trades = [normalise(t) for t in raw_trades]

    # ── Apply filters ──────────────────────────────────────────────────
    if filter_magic is not None:
        trades = [t for t in trades if t["magic"] == filter_magic]

    if symbol:
        sym_upper = symbol.upper()
        trades = [t for t in trades if sym_upper in t["pair"].upper()]

    if outcome:
        ol = outcome.lower()
        if ol == "win":
            trades = [t for t in trades if t["profit"] > 0]
        elif ol == "loss":
            trades = [t for t in trades if t["profit"] <= 0]
        # "all" → no filtering

    # Sort newest first
    trades.sort(key=lambda t: t.get("close_time", "") or t.get("open_time", ""), reverse=True)
    return trades

# ── Pine Script strategies directory ─────────────────────────────────────
PINES_DIR = Path(__file__).resolve().parent.parent / "strategy-engine" / "pines"
if not PINES_DIR.is_dir():
    PINES_DIR = Path("C:\\Trading\\strategy-engine\\pines")

def _list_pine_strategies() -> list[dict]:
    """List all .pine files from the pines directory."""
    if not PINES_DIR.is_dir():
        logger.warning("Pine scripts directory not found: %s", PINES_DIR)
        return []
    try:
        result = []
        for f in sorted(PINES_DIR.iterdir()):
            if f.suffix.lower() == ".pine":
                result.append({
                    "name": f.stem,
                    "path": str(f.resolve()),
                })
        return result
    except Exception as e:
        logger.error("Failed to list pine strategies: %s", e)
        return []

# ── Backtesting Endpoints ────────────────────────────────────────────────

@app.get("/api/backtest/strategies")
async def list_backtest_strategies(auth=Depends(require_auth)):
    """List all available Pine Script strategies from strategy-engine/pines/."""
    return _list_pine_strategies()

class RunBacktestRequest(PydanticBaseModel):
    symbol: str
    timeframe: str = "H1"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    capital: float = 10000
    lot_size: float = 0.01
    strategy_key: str = ""
    strategy_name: str = ""
    strategy_params: dict = {}
    ftmo_mode: bool = True
    risk_per_trade: float = 0.01
    pine_script: Optional[str] = None

@app.post("/api/backtest/run")
async def run_backtest(req: RunBacktestRequest, auth=Depends(require_auth)):
    import sys as _sys
    from pathlib import Path as _Path
    bt_root = str(_Path(__file__).resolve().parent.parent / "backtester")
    _sys.path.insert(0, bt_root)
    import pandas as pd
    from data import INSTRUMENTS, fetch
    from engine import run as bt_run
    from loader import list_strategies, PineScriptStrategy

    instrument = INSTRUMENTS.get(req.symbol)
    if not instrument:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {req.symbol}")

    # Default date range: last 7 days if not provided
    if req.date_from is None:
        date_from = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        date_from = req.date_from
    if req.date_to is None:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    else:
        date_to = req.date_to
    timeframe = req.timeframe

    # ── If a raw pine_script is provided, write to temp file → parse locally ──
    if req.pine_script:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".pine", prefix="pine_script_", delete=False, encoding="utf-8"
        )
        tmp.write(req.pine_script)
        script_path = tmp.name
        tmp.close()
        try:
            # Parse the .pine file and run local backtest
            strategy = PineScriptStrategy.from_pine_file(script_path, None)
            # Need data — fetch it now
            data = fetch(instrument["ticker"], date_from, date_to, interval=timeframe)
            if data is None or len(data) < 20:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough data for {req.symbol} {timeframe} from {date_from} to {date_to}. "
                           f"Got {len(data) if data is not None else 0} bars.",
                )
            # Recreate strategy with actual data
            strategy_params = {
                "fast_ema": strategy.fast_ema,
                "slow_ema": strategy.slow_ema,
                "adx_len": strategy.adx_len,
                "adx_thresh": strategy.adx_thresh,
                "rsi_len": strategy.rsi_len,
                "rsi_min": strategy.rsi_min,
                "tp_ratio": strategy.tp_ratio,
                "sl_ratio": strategy.sl_ratio,
            }
            local_result = bt_run(
                strategy_class=PineScriptStrategy,
                data=data,
                initial_capital=req.capital,
                spread_pips=instrument.get("spread_pips", 1.0),
                pip_value=instrument.get("pip_value", 0.0001),
                contract_size=instrument.get("contract_size", 100),
                risk_per_trade=req.risk_per_trade,
                strategy_params=strategy_params,
                ftmo_mode=req.ftmo_mode,
                lot_size=req.lot_size,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Local Pine Script backtest failed: {e}",
            )
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass
        return local_result

    data = fetch(instrument["ticker"], date_from, date_to, interval=timeframe)
    if data is None or len(data) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough data for {req.symbol} {timeframe} from {date_from} to {date_to}. "
                   f"Try a shorter range (e.g. 1-3 months) or different symbol. "
                   f"Got {len(data) if data is not None else 0} bars."
        )

    strategies = list_strategies()

    # Resolve strategy: prefer strategy_key, fall back to strategy_name
    effective_key = req.strategy_key or req.strategy_name
    if not effective_key:
        raise HTTPException(status_code=400, detail="Either strategy_key or strategy_name is required")

    # ── Pine Script (iter_*) strategies → parse .pine file and use local backtester ──
    if effective_key.startswith("iter_"):
        pines_dir = _Path(__file__).resolve().parent.parent / "strategy-engine" / "pines"
        pine_path = pines_dir / f"{effective_key}.pine"
        if not pine_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Pine Script strategy file not found: {pine_path}. "
                       f"Expected {effective_key}.pine in {pines_dir}",
            )
        try:
            # Parse the .pine file to extract parameters
            strategy = PineScriptStrategy.from_pine_file(str(pine_path), data)
            strategy_params = {
                "fast_ema": strategy.fast_ema,
                "slow_ema": strategy.slow_ema,
                "adx_len": strategy.adx_len,
                "adx_thresh": strategy.adx_thresh,
                "rsi_len": strategy.rsi_len,
                "rsi_min": strategy.rsi_min,
                "tp_ratio": strategy.tp_ratio,
                "sl_ratio": strategy.sl_ratio,
            }
            result = bt_run(
                strategy_class=PineScriptStrategy,
                data=data,
                initial_capital=req.capital,
                spread_pips=instrument.get("spread_pips", 1.0),
                pip_value=instrument.get("pip_value", 0.0001),
                contract_size=instrument.get("contract_size", 100),
                risk_per_trade=req.risk_per_trade,
                strategy_params=strategy_params,
                ftmo_mode=req.ftmo_mode,
                lot_size=req.lot_size,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Local Pine Script backtest failed for {effective_key}: {e}",
            )

        # ── Normalise equity_curve: always list of {time, equity}, never empty ──
        raw_eq = result.get("equity_curve", [])
        if isinstance(raw_eq, list) and len(raw_eq) > 0:
            eq_data = []
            for point in raw_eq:
                if isinstance(point, dict):
                    d = point.get("time", "")
                    eq_data.append({
                        "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:19],
                        "equity": float(point.get("equity", 0)),
                    })
        elif isinstance(raw_eq, pd.DataFrame):
            eq_df = raw_eq
            eq_data = []
            time_col = "time" if "time" in eq_df.columns else ("date" if "date" in eq_df.columns else None)
            if time_col:
                for _, row in eq_df.iterrows():
                    d = row[time_col]
                    eq_data.append({
                        "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:16],
                        "equity": float(row.get("equity", 0)),
                    })
            else:
                eq_data = [{"time": str(i), "equity": float(row.get("equity", 0))} for i, (_, row) in enumerate(eq_df.iterrows())]
        else:
            eq_data = []

        if not eq_data:
            start_eq = float(req.capital)
            end_eq = float(result.get("final_equity", start_eq))
            eq_data = [
                {"time": date_from[:10] + " 00:00", "equity": start_eq},
                {"time": date_to[:10] + " 00:00", "equity": end_eq},
            ]

        trades_list = []
        for t in result.get("trades", []):
            if not isinstance(t, dict):
                continue
            trades_list.append({
                "entry_time": str(t.get("entry_time", "")),
                "exit_time": str(t.get("exit_time", "")),
                "symbol": req.symbol,
                "side": t.get("side", ""),
                "entry_price": float(t.get("entry_price", 0)),
                "exit_price": float(t.get("exit_price", 0)),
                "pnl": float(t.get("pnl", 0)),
                "pnl_pips": float(t.get("pnl_pips", 0)),
                "pnl_pct": float(t.get("pnl_pct", 0)),
                "exit_reason": t.get("exit_reason", ""),
            })

        import numpy as np
        return {
            "metrics": {k: float(v) if isinstance(v, (np.floating,)) else int(v) if isinstance(v, (np.integer,)) else bool(v) if isinstance(v, np.bool_) else v for k, v in result["metrics"].items()},
            "equity_curve": eq_data,
            "trades": trades_list,
            "ftmo": result.get("ftmo"),
            "ftmo_phase2": result.get("ftmo_phase2"),
            "final_equity": float(result["final_equity"]),
        }

    # ── Local backtester for built-in strategies ────────────────────────
    if effective_key not in strategies:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {effective_key}")

    strategy_cls = strategies[effective_key]
    result = bt_run(
        strategy_class=strategy_cls,
        data=data,
        initial_capital=req.capital,
        spread_pips=instrument.get("spread_pips", 1.0),
        pip_value=instrument.get("pip_value", 0.0001),
        contract_size=instrument.get("contract_size", 100),
        risk_per_trade=req.risk_per_trade,
        strategy_params=req.strategy_params,
        ftmo_mode=req.ftmo_mode,
        lot_size=req.lot_size,
    )

    # ── Normalise equity_curve: always list of {time, equity}, never empty ──
    raw_eq = result.get("equity_curve", [])
    if isinstance(raw_eq, list) and len(raw_eq) > 0:
        eq_data = []
        for point in raw_eq:
            if isinstance(point, dict):
                d = point.get("time", "")
                eq_data.append({
                    "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:19],
                    "equity": float(point.get("equity", 0)),
                })
    elif isinstance(raw_eq, pd.DataFrame):
        eq_df = raw_eq
        eq_data = []
        time_col = "time" if "time" in eq_df.columns else ("date" if "date" in eq_df.columns else None)
        if time_col:
            for _, row in eq_df.iterrows():
                d = row[time_col]
                eq_data.append({
                    "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:16],
                    "equity": float(row.get("equity", 0)),
                })
        else:
            eq_data = [{"time": str(i), "equity": float(row.get("equity", 0))} for i, (_, row) in enumerate(eq_df.iterrows())]
    else:
        eq_data = []

    # Synthetic curve if still empty
    if not eq_data:
        start_eq = float(req.capital)
        end_eq = float(result.get("final_equity", start_eq))
        eq_data = [
            {"time": date_from[:10] + " 00:00", "equity": start_eq},
            {"time": date_to[:10] + " 00:00", "equity": end_eq},
        ]

    # ── Normalise trades: always list of trade objects ──────────────────
    trades_list = []
    for t in result.get("trades", []):
        if not isinstance(t, dict):
            continue
        trades_list.append({
            "entry_time": str(t.get("entry_time", "")),
            "exit_time": str(t.get("exit_time", "")),
            "symbol": req.symbol,
            "side": t.get("side", ""),
            "entry_price": float(t.get("entry_price", 0)),
            "exit_price": float(t.get("exit_price", 0)),
            "pnl": float(t.get("pnl", 0)),
            "pnl_pips": float(t.get("pnl_pips", 0)),
            "pnl_pct": float(t.get("pnl_pct", 0)),
            "exit_reason": t.get("exit_reason", ""),
        })

    import numpy as np
    return {
        "metrics": {k: float(v) if isinstance(v, (np.floating,)) else int(v) if isinstance(v, (np.integer,)) else bool(v) if isinstance(v, np.bool_) else v for k, v in result["metrics"].items()},
        "equity_curve": eq_data,
        "trades": trades_list,
        "ftmo": result.get("ftmo"),
        "ftmo_phase2": result.get("ftmo_phase2"),
        "final_equity": float(result["final_equity"]),
    }

class OptimizeRequest(PydanticBaseModel):
    symbol: str
    timeframe: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    capital: float = 10000
    strategy_key: str
    param_ranges: dict = {}

@app.post("/api/backtest/optimize")
async def optimize_backtest(req: OptimizeRequest, auth=Depends(require_auth)):
    import sys as _sys
    from pathlib import Path as _Path
    bt_root = str(_Path(__file__).resolve().parent.parent / "backtester")
    _sys.path.insert(0, bt_root)
    import numpy as np
    from data import INSTRUMENTS, fetch
    from engine import run as bt_run
    from loader import list_strategies

    instrument = INSTRUMENTS.get(req.symbol)
    if not instrument:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {req.symbol}")

    strategies = list_strategies()
    if req.strategy_key not in strategies:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {req.strategy_key}")

    strategy_cls = strategies[req.strategy_key]
    data = fetch(instrument["ticker"], req.date_from, req.date_to, interval=req.timeframe)
    if data is None or len(data) < 20:
        raise HTTPException(status_code=400, detail="Not enough data")

    results = []
    param_names = list(req.param_ranges.keys())
    if not param_names:
        raise HTTPException(status_code=400, detail="No param_ranges specified")

    def _run_one(params):
        return bt_run(
            strategy_class=strategy_cls, data=data, initial_capital=req.capital,
            spread_pips=instrument.get("spread_pips", 1.0),
            pip_value=instrument.get("pip_value", 0.0001),
            contract_size=instrument.get("contract_size", 100),
            risk_per_trade=0.01, strategy_params=params, ftmo_mode=False,
        )

    base = _run_one({})
    results.append({"params": {}, "sharpe": base["metrics"].get("sharpe", 0), "total_return": base["metrics"].get("total_return", 0)})

    ranges = req.param_ranges.get(param_names[0], [])
    if len(ranges) >= 3:
        for val in np.arange(float(ranges[0]), float(ranges[1]) + float(ranges[2]) / 2, float(ranges[2])):
            params = {param_names[0]: round(float(val), 4)}
            r = _run_one(params)
            results.append({
                "params": params,
                "sharpe": round(r["metrics"].get("sharpe", 0), 3),
                "total_return": round(r["metrics"].get("total_return", 0), 3),
            })

    return {"results": sorted(results, key=lambda x: x["sharpe"], reverse=True)}

class CustomBacktestRequest(PydanticBaseModel):
    code: str
    symbol: str
    timeframe: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    capital: float = 10000
    ftmo_mode: bool = True

class CompareBacktestRequest(PydanticBaseModel):
    strategy_keys: list[str]
    symbol: str
    timeframe: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    capital: float = 10000

class SaveStrategyRequest(PydanticBaseModel):
    name: str
    code: str

@app.post("/api/backtest/custom")
async def run_custom_backtest(req: CustomBacktestRequest, auth=Depends(require_auth)):
    import sys as _sys
    from pathlib import Path as _Path
    bt_root = str(_Path(__file__).resolve().parent.parent / "backtester")
    custom_dir = _Path(bt_root) / "custom_strategies"
    custom_dir.mkdir(parents=True, exist_ok=True)
    _sys.path.insert(0, bt_root)
    _sys.path.insert(0, str(custom_dir))
    import importlib.util
    import hashlib
    import pandas as pd
    from data import INSTRUMENTS, fetch
    from engine import run as bt_run

    instrument = INSTRUMENTS.get(req.symbol)
    if not instrument:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {req.symbol}")

    data = fetch(instrument["ticker"], req.date_from, req.date_to, interval=req.timeframe)
    if data is None or len(data) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough data for {req.symbol} {req.timeframe} from {req.date_from} to {req.date_to}. "
                   f"Try a shorter range (e.g. 1-3 months) or different symbol. "
                   f"Got {len(data) if data is not None else 0} bars."
        )

    code_hash = hashlib.md5(req.code.encode()).hexdigest()[:8]
    tmp_file = custom_dir / f"_custom_{code_hash}.py"
    tmp_file.write_text(req.code, encoding="utf-8")

    spec = importlib.util.spec_from_file_location(f"_custom_{code_hash}", str(tmp_file))
    if not spec or not spec.loader:
        raise HTTPException(status_code=400, detail="Failed to load custom strategy module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    strategy_cls = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and attr_name.lower().endswith("strategy"):
            strategy_cls = attr
            break
    if not strategy_cls:
        raise HTTPException(status_code=400, detail="No strategy class found in custom code")

    result = bt_run(
        strategy_class=strategy_cls,
        data=data,
        initial_capital=req.capital,
        spread_pips=instrument.get("spread_pips", 1.0),
        pip_value=instrument.get("pip_value", 0.0001),
        contract_size=instrument.get("contract_size", 100),
        risk_per_trade=0.01,
        strategy_params={},
        ftmo_mode=req.ftmo_mode,
    )

    try:
        tmp_file.unlink()
    except Exception:
        pass

    eq_df = result["equity_curve"] if isinstance(result["equity_curve"], pd.DataFrame) else pd.DataFrame(result["equity_curve"])
    eq_data = []
    if "time" in eq_df.columns:
        for _, row in eq_df.iterrows():
            d = row["time"]
            eq_data.append({
                "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:16],
                "equity": float(row["equity"]),
            })
    elif "date" in eq_df.columns:
        for _, row in eq_df.iterrows():
            d = row["date"]
            eq_data.append({
                "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:16],
                "equity": float(row["equity"]),
            })
    else:
        eq_data = [{"time": str(i), "equity": float(eq_df["equity"].iloc[i])} for i in range(len(eq_df))]

    trades_list = []
    for t in result["trades"]:
        trades_list.append({
            "entry_time": str(t.get("entry_time", "")),
            "exit_time": str(t.get("exit_time", "")),
            "symbol": req.symbol,
            "side": t.get("side", ""),
            "entry_price": float(t.get("entry_price", 0)),
            "exit_price": float(t.get("exit_price", 0)),
            "pnl": float(t.get("pnl", 0)),
            "pnl_pips": float(t.get("pnl_pips", 0)),
            "pnl_pct": float(t.get("pnl_pct", 0)),
            "exit_reason": t.get("exit_reason", ""),
        })

    import numpy as np
    return {
        "metrics": {k: float(v) if isinstance(v, (np.floating,)) else int(v) if isinstance(v, (np.integer,)) else bool(v) if isinstance(v, np.bool_) else v for k, v in result["metrics"].items()},
        "equity_curve": eq_data,
        "trades": trades_list,
        "ftmo": result.get("ftmo"),
        "ftmo_phase2": result.get("ftmo_phase2"),
        "final_equity": float(result["final_equity"]),
    }

@app.post("/api/backtest/compare")
async def compare_backtest(req: CompareBacktestRequest, auth=Depends(require_auth)):
    import sys as _sys
    from pathlib import Path as _Path
    bt_root = str(_Path(__file__).resolve().parent.parent / "backtester")
    _sys.path.insert(0, bt_root)
    import pandas as pd
    from data import INSTRUMENTS, fetch
    from engine import run as bt_run
    from loader import list_strategies

    if len(req.strategy_keys) > 3:
        raise HTTPException(status_code=400, detail="Maximum 3 strategies for comparison")

    instrument = INSTRUMENTS.get(req.symbol)
    if not instrument:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {req.symbol}")

    data = fetch(instrument["ticker"], req.date_from, req.date_to, interval=req.timeframe)
    if data is None or len(data) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough data for {req.symbol} {req.timeframe} from {req.date_from} to {req.date_to}. "
                   f"Try a shorter range (e.g. 1-3 months) or different symbol. "
                   f"Got {len(data) if data is not None else 0} bars."
        )

    strategies = list_strategies()
    results = []
    for key in req.strategy_keys:
        if key not in strategies:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {key}")
        strategy_cls = strategies[key]
        result = bt_run(
            strategy_class=strategy_cls,
            data=data,
            initial_capital=req.capital,
            spread_pips=instrument.get("spread_pips", 1.0),
            pip_value=instrument.get("pip_value", 0.0001),
            contract_size=instrument.get("contract_size", 100),
            risk_per_trade=0.01,
            strategy_params={},
            ftmo_mode=False,
        )
        eq_df = result["equity_curve"] if isinstance(result["equity_curve"], pd.DataFrame) else pd.DataFrame(result["equity_curve"])
        eq_data = []
        if "time" in eq_df.columns:
            for _, row in eq_df.iterrows():
                d = row["time"]
                eq_data.append({
                    "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:16],
                    "equity": float(row["equity"]),
                })
        elif "date" in eq_df.columns:
            for _, row in eq_df.iterrows():
                d = row["date"]
                eq_data.append({
                    "time": d.strftime("%Y-%m-%d %H:%M") if hasattr(d, "strftime") else str(d)[:16],
                    "equity": float(row["equity"]),
                })
        else:
            eq_data = [{"time": str(i), "equity": float(eq_df["equity"].iloc[i])} for i in range(len(eq_df))]
        import numpy as np
        results.append({
            "name": key,
            "metrics": {k: float(v) if isinstance(v, (np.floating,)) else int(v) if isinstance(v, (np.integer,)) else bool(v) if isinstance(v, np.bool_) else v for k, v in result["metrics"].items()},
            "equity_curve": eq_data,
            "final_equity": float(result["final_equity"]),
        })
    return {"results": results}

@app.post("/api/backtest/strategies")
async def save_custom_strategy(req: SaveStrategyRequest, auth=Depends(require_auth)):
    from pathlib import Path as _Path
    bt_root = _Path(__file__).resolve().parent.parent / "backtester"
    custom_dir = bt_root / "custom_strategies"
    custom_dir.mkdir(parents=True, exist_ok=True)
    file_path = custom_dir / f"{req.name}.py"
    if file_path.exists():
        raise HTTPException(status_code=409, detail=f"Strategy '{req.name}' already exists")
    file_path.write_text(req.code, encoding="utf-8")
    return {"status": "created", "name": req.name, "path": str(file_path)}

@app.delete("/api/backtest/strategies/{name}")
async def delete_custom_strategy(name: str, auth=Depends(require_auth)):
    from pathlib import Path as _Path
    bt_root = _Path(__file__).resolve().parent.parent / "backtester"
    file_path = bt_root / "custom_strategies" / f"{name}.py"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    file_path.unlink()
    return {"status": "deleted", "name": name}

# ── Editor Endpoints ────────────────────────────────────────────────────

@app.get("/api/editor/files")
async def editor_list_files(auth=Depends(require_auth)):
    import subprocess
    bots_dir = Path(__file__).resolve().parent.parent / "bots"
    if not bots_dir.exists():
        return {"files": []}
    result = subprocess.run(
        ["git", "-C", str(bots_dir.parent), "status", "--porcelain", "bots/"],
        capture_output=True, text=True, timeout=10,
    )
    git_status_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    git_map = {}
    for line in git_status_lines:
        if len(line) < 4: continue
        status = line[:2].strip()
        relative_path = line[3:]
        relative_path = relative_path.replace("\\", "/")
        git_map[relative_path] = status

    def build_tree(dir_path: Path, prefix: str = "bots"):
        items = []
        for entry in sorted(dir_path.iterdir(), key=lambda x: (x.is_file(), x.name)):
            rel = f"{prefix}/{entry.name}"
            if entry.is_dir():
                children = build_tree(entry, rel)
                items.append({"name": entry.name, "path": rel, "type": "folder", "children": children})
            elif entry.suffix == ".py":
                gs = git_map.get(rel, "")
                status = "clean"
                if gs == "M" or gs == " M": status = "modified"
                elif gs == "A" or gs == "??": status = "untracked"
                items.append({"name": entry.name, "path": rel, "type": "file", "git_status": status})
        return items

    return {"files": build_tree(bots_dir)}

@app.get("/api/editor/files/{path:path}")
async def editor_read_file(path: str, auth=Depends(require_auth)):
    """Read a bot script file content. Resolves relative to project root or bots/ dir."""
    project_root = Path(__file__).resolve().parent.parent  # C:\Trading
    bots_dir = project_root / "bots"

    # Try direct path first, then under bots/
    candidates = [
        project_root / path,
        bots_dir / path,
    ]
    # Also try stripping 'bots/' prefix if it's already included
    if path.startswith("bots/"):
        candidates.insert(0, project_root / path[len("bots/"):])

    full_path = None
    for candidate in candidates:
        resolved = candidate.resolve()
        # Security: ensure the resolved path is under project_root
        try:
            resolved.relative_to(project_root.resolve())
        except ValueError:
            continue
        if resolved.exists() and resolved.is_file():
            full_path = resolved
            break

    if full_path is None:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    try:
        content = full_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
    return {"path": str(full_path.relative_to(project_root)), "content": content}

class SaveFileRequest(PydanticBaseModel):
    content: str

@app.put("/api/editor/files/{path:path}")
async def editor_save_file(path: str, req: SaveFileRequest, auth=Depends(require_auth)):
    project_root = Path(__file__).resolve().parent.parent
    bots_dir = project_root / "bots"
    candidates = [project_root / path, bots_dir / path]
    if path.startswith("bots/"):
        candidates.insert(0, project_root / path[len("bots/"):])
    full_path = None
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            full_path = candidate
            break
    if full_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    full_path.write_text(req.content, encoding="utf-8")
    return {"status": "saved", "path": str(full_path.relative_to(project_root))}

@app.post("/api/editor/deploy/{path:path}")
async def editor_deploy(path: str, auth=Depends(require_auth)):
    from bots.streaming_bot import restart_bot
    try:
        result = restart_bot()
        return {"status": "deployed", "path": path, "bot_restarted": True, "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deploy failed: {e}")

@app.get("/api/editor/history/{path:path}")
async def editor_file_history(path: str, auth=Depends(require_auth)):
    import subprocess
    repo_root = Path(__file__).resolve().parent.parent
    rel = path.replace("\\", "/")
    result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "--oneline", "--follow", "--", rel],
        capture_output=True, text=True, timeout=10,
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip(): continue
        parts = line.strip().split(" ", 1)
        commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})
    return {"commits": commits[:30]}

# ── Research & Innovation Endpoints ────────────────────────────────────

@app.get("/api/research/division-status")
async def research_division_status(auth=Depends(require_auth)):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from research.division7 import get_division_status, get_innovation_pipeline
        result = {
            "division": get_division_status(),
            "pipeline": get_innovation_pipeline(),
        }

        # Also include Research & Invocation Division status if available
        try:
            rd_path = str(Path(__file__).resolve().parent.parent / "research_division")
            if rd_path not in sys.path:
                sys.path.insert(0, rd_path)
            from run import status_snapshot
            rd_status = status_snapshot()
            result["research_division"] = {
                "version": rd_status.get("division_version"),
                "sprint_number": rd_status.get("sprint", {}).get("sprint_number", 0),
                "backlog_items": len(rd_status.get("sprint", {}).get("backlog", [])),
                "items_in_progress": len(rd_status.get("sprint", {}).get("items", [])),
                "deployments_total": rd_status.get("deployment_stats", {}).get("total", 0),
                "deployments_success_rate": rd_status.get("deployment_stats", {}).get("success_rate", 0),
                "last_report_time": rd_status.get("latest_report", {}).get("generated_at", ""),
            }
        except Exception as rd_err:
            result["research_division"] = {"status": "unavailable", "error": str(rd_err)}

        return result
    except Exception as e:
        return {"division": None, "pipeline": [], "error": str(e)}

@app.get("/api/research/sprint")
async def research_sprint(auth=Depends(require_auth)):
    """Get the current Research Division sprint state and blockers."""
    try:
        rd_path = str(Path(__file__).resolve().parent.parent / "research_division")
        if rd_path not in sys.path:
            sys.path.insert(0, rd_path)
        from sprint_manager import load_sprint, detect_blockers
        from data_collector import fetch_open_positions
        from analytics_engine import load_analytics_history

        sprint = load_sprint()
        history = load_analytics_history()
        positions = fetch_open_positions()
        reports = history[-1].get("reports", {}) if history else {}

        blockers = detect_blockers(reports, positions) if reports else []

        return {
            "status": "ok",
            "sprint": sprint,
            "blockers": blockers,
            "analytics_history_points": len(history),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/research/insights")
async def research_insights(auth=Depends(require_auth)):
    """Get latest performance insights per pair and strategy."""
    try:
        rd_path = str(Path(__file__).resolve().parent.parent / "research_division")
        if rd_path not in sys.path:
            sys.path.insert(0, rd_path)
        from analytics_engine import load_analytics_history

        history = load_analytics_history()
        if not history:
            return {"status": "ok", "insights": [], "message": "No analytics data yet"}

        latest = history[-1].get("reports", {})

        # Build per-pair insights
        insights = []
        for pair, report in latest.items():
            if pair == "overall":
                continue
            kpis = report.get("kpis", {})
            insights.append({
                "pair": pair,
                "trades": kpis.get("total_trades", 0) or 0,
                "win_rate": round(kpis.get("win_rate", 0) or 0, 1),
                "profit_factor": round(kpis.get("profit_factor", 0) or 0, 2),
                "net_profit": round(kpis.get("net_profit", 0) or 0, 2),
                "max_dd": round(kpis.get("max_drawdown_pct", 0) or 0, 1),
                "avg_win": round(kpis.get("avg_win", 0) or 0, 2),
                "avg_loss": round(kpis.get("avg_loss", 0) or 0, 2),
                "expectancy_ratio": round(kpis.get("expectancy_ratio", 0) or 0, 2),
                "consecutive_losses": kpis.get("max_consecutive_losses", 0) or 0,
                "best_session": max(
                    kpis.get("win_rate_by_session", {"asian": 0, "london": 0, "us": 0}),
                    key=lambda s: (kpis.get("win_rate_by_session", {}).get(s) or 0) if not isinstance(kpis.get("win_rate_by_session", {}).get(s), dict) else (kpis.get("win_rate_by_session", {}).get(s, {}).get("win_rate", 0) or 0),
                    default="N/A"
                ),
            })

        # Overall market health
        overall = latest.get("overall", {}).get("kpis", {})
        market_health = {
            "total_trades": overall.get("total_trades", 0),
            "overall_win_rate": round(overall.get("win_rate", 0) or 0, 1),
            "profit_factor": round(overall.get("profit_factor", 0) or 0, 2),
            "net_pnl": round(overall.get("net_profit", 0) or 0, 2),
            "max_drawdown": round(overall.get("max_drawdown_pct", 0) or 0, 1),
            "best_pair": max(insights, key=lambda i: i["win_rate"], default={}).get("pair", "N/A") if insights else "N/A",
            "worst_pair": min(insights, key=lambda i: i["win_rate"], default={}).get("pair", "N/A") if insights else "N/A",
        }

        return {
            "status": "ok",
            "generated_at": history[-1].get("timestamp", ""),
            "market_health": market_health,
            "insights": insights,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/research/report")
async def research_report(auth=Depends(require_auth)):
    """Get the latest Research Division full report."""
    try:
        report_path = Path(__file__).resolve().parent.parent / "research_division" / "reports" / "latest.json"
        if report_path.exists():
            import json
            report = json.loads(report_path.read_text())
            return {"status": "ok", "report": report}
        return {"status": "ok", "report": None, "message": "No report generated yet"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/research/run-now")
async def research_run_now(auth=Depends(require_auth)):
    """Trigger the Research Division to run its full cycle now."""
    try:
        import subprocess
        import json

        rd_path = Path(__file__).resolve().parent.parent / "research_division"
        result = subprocess.run(
            [sys.executable, "run.py", "--once"],
            cwd=str(rd_path),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return {"status": "ok", "result": data}
            except json.JSONDecodeError:
                return {"status": "ok", "raw_output": result.stdout[:2000]}
        return {
            "status": "error",
            "returncode": result.returncode,
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Division cycle timed out (>10 min)"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/research/convert-document")
async def research_convert_document(req: dict, auth=Depends(require_auth)):
    file_path = req.get("file_path", "")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path required")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from research.markitdown_bridge import convert_to_markdown
        result = convert_to_markdown(file_path)
        if result is None:
            raise HTTPException(status_code=400, detail="Failed to convert document")
        return {"markdown": result, "file": file_path, "length": len(result)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Orchestrator Endpoints ─────────────────────────────────────────────

ORCHESTRATOR_AGENTS = [
    {
        "id": "research",
        "name": "Research & Innovation",
        "avatar": "📡",
        "role": "Market Research, Tool Discovery, Document Analysis",
        "status": "idle",
    },
    {
        "id": "clawjatt",
        "name": "Clawjatt",
        "avatar": "🐆",
        "role": "Technical Analysis & Signals",
        "status": "idle",
    },
    {
        "id": "alphaguru",
        "name": "AlphaGuru",
        "avatar": "🐅",
        "role": "Portfolio Allocation & Strategy",
        "status": "idle",
    },
    {
        "id": "hermesjatti",
        "name": "Hermes Jatti",
        "avatar": "🕊️",
        "role": "Execution & Risk Management",
        "status": "idle",
    },
]

ORCHESTRATOR_COMMANDS = [
    {"command": "Start gold bot", "agent": "clawjatt", "response": "Clawjatt is deploying the gold trading bot on XAUUSD. ATR multiplier 1.5, risk per trade 1%. Bot started successfully."},
    {"command": "Show PnL today", "agent": "hermesjatti", "response": "Today's PnL: +$42.30 across 3 trades. Win rate 66.7%. Profit factor 1.8. Best trade: +$35.00 on XAUUSD breakout."},
    {"command": "Backtest breakout strategy", "agent": "alphaguru", "response": "AlphaGuru ran backtest on SessionRangeBreakout. Results: Total return +12.4%, Sharpe 1.87, Max DD -4.2%. 47 trades over 90 days. FTMO compliant."},
    {"command": "Check system health", "agent": "clawjatt", "response": "System health check: Bridge connected. Database online. Redis pub/sub active. 1 account connected. 2 bots running. Memory usage 42%. CPU 8%."},
    {"command": "Analyze XAUUSD", "agent": "clawjatt", "response": "XAUUSD technical analysis: RSI 58 (neutral), MACD bullish crossover, 50 EMA above 200 EMA (golden cross). Support at 2295, resistance at 2330. Volume increasing."},
    {"command": "Review risk limits", "agent": "hermesjatti", "response": "Risk review: Daily loss at $18.50 (18.5% of $100 limit). Total drawdown $42.00 (4.2% of $10k account). Position size within limits. Margin level 285%. No violations."},
]

@app.get("/api/orchestrator/agents")
async def orchestrator_agents(auth=Depends(require_auth)):
    db = get_db()
    agents = []
    now = datetime.now(timezone.utc)

    # Fetch bot statuses — these ARE the real agents
    bots = db.get_bots()

    # Fetch decision logs for real last_active timestamps and actions
    decisions = db.get_agent_logs(limit=100) if hasattr(db, 'get_agent_logs') else []

    # Build per-bot last_active and last_action from decisions
    bot_activity: dict[str, dict] = {}
    for dec in decisions:
        name = dec.get("agent_name", "")
        if not name:
            continue
        if name not in bot_activity:
            bot_activity[name] = {"last_active": dec.get("created_at", ""), "last_action": dec.get("action", "")}
        # Prefer newer
        ts = dec.get("created_at", "")
        if ts and ts > bot_activity[name]["last_active"]:
            bot_activity[name] = {"last_active": ts, "last_action": dec.get("action", "")}

    # Create agent entries from real bots
    for bot in bots:
        name = bot.get("name", "")
        status = bot.get("status", "stopped")
        script = bot.get("script_path", "")
        # Extract strategy from script name or bot name
        parts = name.split("_")
        strategy = parts[0] if len(parts) > 1 else "custom"
        symbol = parts[1] if len(parts) > 1 else ""

        activity = bot_activity.get(name, {})
        agents.append({
            "id": name,
            "name": name.replace("_", " ").title(),
            "avatar": "🤖",
            "role": f"{strategy.capitalize()} Strategy on {symbol}" if symbol else f"{strategy.capitalize()} Strategy",
            "status": "running" if status == "running" else "idle",
            "last_active": activity.get("last_active") or bot.get("last_started", ""),
            "last_action": activity.get("last_action", f"Monitoring {symbol or strategy}"),
        })

    # Sort: running first, then idle
    agents.sort(key=lambda a: (0 if a["status"] == "running" else 1, a["name"]))

    return {"agents": agents}

class OrchestratorCommandRequest(PydanticBaseModel):
    command: str

@app.post("/api/orchestrator/command")
async def orchestrator_command(req: OrchestratorCommandRequest, auth=Depends(require_auth)):
    cmd_lower = req.command.lower()
    best = None
    best_score = 0
    for entry in ORCHESTRATOR_COMMANDS:
        score = sum(1 for w in entry["command"].lower().split() if w in cmd_lower)
        if score > best_score:
            best_score = score
            best = entry
    if best and best_score >= 2:
        agent = next((a for a in ORCHESTRATOR_AGENTS if a["id"] == best["agent"]), ORCHESTRATOR_AGENTS[0])
        return {
            "response": best["response"],
            "agent_id": best["agent"],
            "agent_name": agent["name"],
            "agent_avatar": agent["avatar"],
        }
    return {
        "response": f"I understand you want to: '{req.command}'. I'm routing this to the appropriate agent for analysis. Will report back shortly.",
        "agent_id": "hermesjatti",
        "agent_name": "Hermes Jatti",
        "agent_avatar": "🕊️",
    }

@app.get("/api/orchestrator/timeline")
async def orchestrator_timeline(auth=Depends(require_auth)):
    import random as _r
    events = []
    agents = {a["id"]: a for a in ORCHESTRATOR_AGENTS}
    for i in range(10):
        agent_id = _r.choice(list(agents.keys()))
        agent = agents[agent_id]
        actions = [
            "Analyzed market conditions",
            "Checked portfolio allocation",
            "Verified risk limits",
            "Executed trade signal",
            "Monitored open positions",
            "Evaluated macroeconomic data",
            "Adjusted stop-loss levels",
            "Reviewed bot performance",
        ]
        outcomes = ["success", "success", "success", "success", "warning", "success"]
        events.append({
            "time": f"{(10 - i) * 3}m ago",
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "agent_avatar": agent["avatar"],
            "action": _r.choice(actions),
            "outcome": _r.choice(outcomes),
            "detail": f"Completed in {_r.randint(50, 500)}ms",
        })
    return {"events": events}

# ── File Conversion Endpoint ──────────────────────────────────────────

from backend.file_converter import convert_bytes_to_markdown

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/api/convert/file")
async def convert_file(file: UploadFile = File(...)):
    """Accepts a file upload, converts to markdown, returns text + metadata."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = convert_bytes_to_markdown(contents, file.filename)
        return {
            "filename": result["filename"],
            "content_type": result["content_type"],
            "markdown": result["text"],
            "size": result["size"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")


# ── Settings Endpoints ─────────────────────────────────────────────────

@app.get("/api/settings/api-keys")
async def settings_api_keys(auth=Depends(require_auth)):
    # Full key values (stored here for demo; in production load from DB/vault)
    _full_keys = {
        "main": "agx_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p",
        "readonly": "agx_r5t6y7u8i9o0p1q2r3s4t5u6v7w8x9y0",
    }
    raw = [
        {"id": "main", "label": "Primary API Key", "key": _full_keys["main"], "created": "2026-01-15", "last_used": "2026-06-10 14:32:01"},
        {"id": "readonly", "label": "Read-only Key", "key": _full_keys["readonly"], "created": "2026-03-22", "last_used": "2026-06-09 09:12:45"},
    ]
    masked = []
    for k in raw:
        key_val = k.get("key", "")
        if len(key_val) > 12:
            masked_key = key_val[:8] + "..." + key_val[-4:]
        else:
            masked_key = key_val
        entry = {kk: vv for kk, vv in k.items() if kk != "key"}
        entry["key"] = masked_key
        masked.append(entry)
    return {"keys": masked}

@app.post("/api/settings/api-keys/regenerate")
async def settings_regenerate_key(auth=Depends(require_auth)):
    import secrets
    new_key = "agx_" + secrets.token_hex(16)
    return {"status": "regenerated", "key": new_key}

@app.get("/api/settings/sessions")
async def settings_sessions(auth=Depends(require_auth)):
    return {
        "sessions": [
            {"id": "s1", "ip": "192.168.1.42", "device": "Chrome / Windows", "last_active": "Active now", "current": True},
            {"id": "s2", "ip": "46.137.203.22", "device": "Firefox / Linux", "last_active": "2 hours ago", "current": False},
            {"id": "s3", "ip": "10.0.0.5", "device": "Safari / macOS", "last_active": "3 days ago", "current": False},
        ]
    }

@app.post("/api/settings/sessions/{session_id}/revoke")
async def settings_revoke_session(session_id: str, auth=Depends(require_auth)):
    return {"status": "revoked", "session_id": session_id}

@app.get("/api/settings/notifications")
async def settings_notifications(auth=Depends(require_auth)):
    return {
        "notifications": {
            "margin_call": True,
            "stop_out": True,
            "bot_error": True,
            "daily_summary": False,
        },
        "webhook_url": "",
    }

@app.post("/api/settings/notifications")
async def settings_update_notifications(req: dict, auth=Depends(require_auth)):
    return {"status": "saved", "settings": req}

@app.get("/api/settings/system")
async def settings_system(auth=Depends(require_auth)):
    import psutil
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
    except ImportError:
        cpu = 12; ram = 45; disk = 32
    return {
        "cpu": cpu, "ram": ram, "disk": disk,
        "services": {
            "bridge": True, "backend": True, "mt5": True,
            "postgresql": True, "redis": True,
        },
    }


# ── FTMO Challenge Manager ─────────────────────────────────────────

@app.get("/api/ftmo/challenges")
async def ftmo_list_challenges(auth=Depends(require_auth)):
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from ftmo_manager import list_challenges, get_summary
    return {"challenges": list_challenges(), "summary": get_summary()}

@app.get("/api/ftmo/challenges/{challenge_id}")
async def ftmo_get_challenge(challenge_id: str, auth=Depends(require_auth)):
    import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from ftmo_manager import get_challenge, check_phase_status
    challenge = get_challenge(challenge_id)
    if not challenge:
        raise HTTPException(404, "Challenge not found")
    status = check_phase_status(challenge)
    return {"challenge": challenge, "status": status}

@app.post("/api/ftmo/challenges")
async def ftmo_create_challenge(req: dict, auth=Depends(require_auth)):
    from ftmo_manager import create_challenge
    account_size = req.get("account_size", "10k")
    bot_name = req.get("bot_name", "gold_bot")
    notes = req.get("notes", "")
    challenge = create_challenge(account_size, bot_name, notes)
    return {"challenge": challenge, "message": f"FTMO {account_size} challenge created!"}

@app.post("/api/ftmo/challenges/{challenge_id}/trade")
async def ftmo_record_trade(challenge_id: str, req: dict, auth=Depends(require_auth)):
    from ftmo_manager import record_trade, check_phase_status
    pnl = req.get("pnl", 0)
    pnl_pips = req.get("pnl_pips", 0)
    challenge = record_trade(challenge_id, pnl, pnl_pips)
    if not challenge:
        raise HTTPException(404, "Challenge not found")
    status = check_phase_status(challenge)
    return {"challenge": challenge, "status": status}

@app.post("/api/ftmo/challenges/{challenge_id}/advance")
async def ftmo_advance_phase(challenge_id: str, auth=Depends(require_auth)):
    from ftmo_manager import advance_phase, check_phase_status
    challenge = advance_phase(challenge_id)
    if not challenge:
        raise HTTPException(404, "Challenge not found")
    status = check_phase_status(challenge)
    return {"challenge": challenge, "status": status, "message": challenge.get("_message", "Phase advanced")}

@app.get("/api/ftmo/summary")
async def ftmo_summary(auth=Depends(require_auth)):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ftmo_manager import get_summary
    return get_summary()

@app.get("/api/ftmo/profiles")
async def ftmo_profiles(auth=Depends(require_auth)):
    import json, os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "ftmo_profiles.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"error": "FTMO profiles not found"}


# ── AI Decision Log ──────────────────────────────────────────────────────────

_DECISION_LOG_PATH = Path(__file__).resolve().parent.parent / "scripts" / "decision_log.py"

def _load_decision_log():
    sys.path.insert(0, str(_DECISION_LOG_PATH.parent))
    import importlib
    dl = importlib.import_module("decision_log")
    importlib.reload(dl)
    return dl

class LogDecisionRequest(PydanticBaseModel):
    agent_id: str
    agent_name: str
    action: str
    detail: str = ""
    outcome: str = "pending"
    metadata: dict = {}

@app.get("/api/decisions")
async def get_decisions(days: int = 7, limit: int = 100, agent_id: str = None):
    dl = _load_decision_log()
    entries = dl.get_decisions(days=days, limit=limit, agent_id=agent_id)
    return {"decisions": entries, "count": len(entries)}

@app.post("/api/decisions")
async def log_decision(req: LogDecisionRequest):
    dl = _load_decision_log()
    entry = dl.log_decision(
        agent_id=req.agent_id,
        agent_name=req.agent_name,
        action=req.action,
        detail=req.detail,
        outcome=req.outcome,
        metadata=req.metadata,
    )
    return {"status": "logged", "entry": entry}

@app.get("/api/decisions/summary")
async def decisions_summary(days: int = 7):
    dl = _load_decision_log()
    summary = dl.get_summary(days=days)
    return summary


# ── Sentiment API ───────────────────────────────────────────────────────────

@app.get("/api/sentiment/score")
async def get_sentiment_score():
    """Return the current gold market sentiment score from real bot data."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research_division"))
    from sentiment_engine import get_sentiment
    score = await get_sentiment()
    return {
        "score": score.score,
        "bias": score.bias,
        "news": {"bullish": score.bullish_news, "bearish": score.bearish_news, "total": score.news_count},
        "geopolitical_risk": round(score.polymarket_risk, 2),
        "gold_trend": score.gold_trend,
        "drivers": score.drivers,
        "generated_at": score.generated_at,
        "real_data": {
            "total_pnl": score.total_pnl,
            "win_rate": round(score.win_rate * 100, 1),
            "open_positions": score.open_positions,
            "running_bots": score.running_bots,
            "total_bots": score.total_bots,
            "running_ratio": score.running_ratio,
        },
    }

@app.post("/api/sentiment/refresh")
async def refresh_sentiment():
    """Force-refresh sentiment data from all real sources."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research_division"))
    from sentiment_engine import get_sentiment
    score = await get_sentiment(force_refresh=True)
    return {
        "score": score.score,
        "bias": score.bias,
        "generated_at": score.generated_at,
        "real_data": {
            "total_pnl": score.total_pnl,
            "win_rate": round(score.win_rate * 100, 1),
            "open_positions": score.open_positions,
            "running_bots": score.running_bots,
            "total_bots": score.total_bots,
            "running_ratio": score.running_ratio,
        },
    }


# ── Server-Sent Events (SSE) ────────────────────────────────────────────────

@app.get("/api/events")
async def sse_events():
    """SSE endpoint that streams bridge health and bot status every 5 seconds."""
    async def event_generator():
        last_bridge = {}
        last_bots = {}
        while True:
            try:
                bridge = get_bridge()
                # Get bridge health
                try:
                    health = await bridge.health()
                except HTTPException:
                    health = {"connected": False, "error": "bridge_unreachable"}
                except Exception:
                    health = {"connected": False, "error": "unknown"}

                # Get bot statuses
                bot_statuses = {}
                for name in BOT_SCRIPTS:
                    bot_statuses[name] = _get_bot_status(name)

                now = datetime.now(timezone.utc).isoformat()

                # Always send the ping event with full state
                data = json.dumps({
                    "type": "ping",
                    "timestamp": now,
                    "bridge": health,
                    "bot_statuses": bot_statuses,
                })
                yield f"data: {data}\n\n"

                # Send bridge_status event if bridge health changed
                bridge_snapshot = json.dumps(health, sort_keys=True)
                last_bridge_snapshot = json.dumps(last_bridge, sort_keys=True)
                if bridge_snapshot != last_bridge_snapshot:
                    data = json.dumps({
                        "type": "bridge_status",
                        "timestamp": now,
                        "bridge": health,
                    })
                    yield f"event: bridge_status\ndata: {data}\n\n"
                    last_bridge = health

                # Send bot_status event if any bot status changed
                if bot_statuses != last_bots:
                    data = json.dumps({
                        "type": "bot_status",
                        "timestamp": now,
                        "bot_statuses": bot_statuses,
                    })
                    yield f"event: bot_status\ndata: {data}\n\n"
                    last_bots = bot_statuses

                await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception:
                # On unexpected error, sleep briefly then retry
                await asyncio.sleep(5)
                continue

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Prices Endpoint ───────────────────────────────────────────────────────────

def _fetch_daily_opens(symbols: list[str]) -> dict[str, float]:
    """Fetch daily OHLC open prices for the given symbols via MetaTrader5.

    Returns a dict mapping symbol -> today's open price (or 0 if unavailable).
    """
    daily_open: dict[str, float] = {}
    if not symbols:
        return daily_open

    config_path = Path(__file__).resolve().parent.parent / "mt5_config.json"
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    terminal_path = cfg.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    login = cfg.get("login")
    password = cfg.get("password")
    server = cfg.get("server")

    import MetaTrader5 as _mt5
    # Initialize once for the batch
    _mt5.shutdown()
    init_kw: dict = {"path": terminal_path}
    if login and password and server:
        init_kw["login"] = int(login)
        init_kw["password"] = str(password)
        init_kw["server"] = str(server)

    if not _mt5.initialize(**init_kw):
        logger.warning("MT5 init failed for daily OHLC: %s", _mt5.last_error())
        _mt5.shutdown()
        return daily_open

    # Ensure all symbols are selected
    for sym in symbols:
        _mt5.symbol_select(sym, True)

    for sym in symbols:
        try:
            rates = _mt5.copy_rates_from_pos(sym, _mt5.TIMEFRAME_D1, 0, 1)
            if rates is not None and len(rates) > 0:
                daily_open[sym] = float(rates[0]["open"])
            else:
                logger.debug("No daily rates for %s", sym)
        except Exception as e:
            logger.debug("Failed to fetch daily open for %s: %s", sym, e)

    _mt5.shutdown()
    return daily_open


@app.get("/api/prices")
async def get_prices():
    """Return current bid/ask prices for all tracked symbols with % change.

    Reads tracked_symbols from mt5_config.json, queries the bridge for each,
    and returns a JSON dict keyed by symbol. Each entry includes a 'change_pct'
    field computed from today's daily open (via MT5) vs current bid price.
    Bridge errors for individual symbols are reported as null instead of
    failing the whole request.
    Falls back to the last known trade price from history when live tick
    data is unavailable.
    """
    config_path = Path(__file__).resolve().parent.parent / "mt5_config.json"
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        symbols = config.get("tracked_symbols") or config.get("symbols", [])
    except Exception as e:
        logger.warning("Could not read mt5_config.json: %s", e)
        symbols = []

    bridge = get_bridge()
    prices: dict[str, Any] = {}

    # Fetch daily OHLC open prices for all symbols
    daily_opens = _fetch_daily_opens(symbols)

    # Pre-fetch history to build a fallback price lookup per symbol
    last_trade_price: dict[str, float] = {}
    try:
        trades = await bridge.get_trades("default", days=30)
        # Sort by close_time descending so the first entry per symbol is the most recent
        trades_sorted = sorted(trades, key=lambda t: t.get("close_time", ""), reverse=True)
        for t in trades_sorted:
            sym = t.get("symbol", "")
            if sym and sym not in last_trade_price:
                exit_price = t.get("exit_price")
                if exit_price is not None:
                    last_trade_price[sym] = float(exit_price)
    except Exception as e:
        logger.warning("Could not fetch trade history for fallback: %s", e)

    async def fetch_one(symbol: str) -> None:
        bid = None
        ask = None
        timestamp = None
        error = None
        try:
            tick = await bridge.get_tick("default", symbol)
            bid = tick.get("bid")
            ask = tick.get("ask")
            timestamp = tick.get("time") or tick.get("timestamp")
        except HTTPException as e:
            error = e.detail
        except Exception as e:
            error = str(e)

        # Fallback: if bid/ask are both null, use last known trade price
        if bid is None and ask is None and symbol in last_trade_price:
            last_price = last_trade_price[symbol]
            bid = last_price
            ask = last_price
            logger.info("Fallback price for %s: using history price %s", symbol, last_price)

        # Calculate change_pct from today's daily open vs current bid
        change_pct = None
        daily_open = daily_opens.get(symbol)
        if bid is not None and daily_open is not None and daily_open != 0:
            change_pct = round(((bid - daily_open) / daily_open) * 100, 4)

        prices[symbol] = {
            "bid": bid,
            "ask": ask,
            "change_pct": change_pct,
            "daily_open": daily_open,
            "timestamp": timestamp,
        }
        if error:
            prices[symbol]["error"] = error

    await asyncio.gather(*(fetch_one(sym) for sym in symbols))
    return prices


# ── Frontend (static files from AGENTX dashboard) ──────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "public")

# Mount _next static assets (must be before catch-all)
_next_dir = os.path.join(FRONTEND_DIR, "_next")
if os.path.isdir(_next_dir):
    app.mount("/_next", StaticFiles(directory=_next_dir), name="next_assets")

# Serve index.html at root
@app.get("/", response_class=HTMLResponse)
async def serve_frontend_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>AGENTX Backend Running</h1><p>Frontend not found. Run setup.</p>")

# Serve other static files (favicon, etc.)
@app.get("/{path:path}", response_class=HTMLResponse)
async def serve_frontend(path: str):
    # Don't intercept API routes
    if path.startswith("api/") or path.startswith("_next/"):
        raise HTTPException(status_code=404)
    
    # Try exact file match first (e.g., favicon.svg)
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    # Try with .html extension (pre-rendered pages like portfolio.html, trades.html)
    html_path = os.path.join(FRONTEND_DIR, path + ".html")
    if os.path.isfile(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    
    # Try without trailing slash
    if path.endswith("/"):
        no_slash_path = os.path.join(FRONTEND_DIR, path.rstrip("/") + ".html")
        if os.path.isfile(no_slash_path):
            with open(no_slash_path, "r", encoding="utf-8") as f:
                return f.read()
    
    # SPA fallback: serve index.html for client-side routes
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    raise HTTPException(status_code=404)
