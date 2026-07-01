# Bot Deployment Runbook — AgentX Trading System

> **Source**: backend/app.py (lines 471-500, lifespan hook; lines 141-173, _discover_bots;
>   lines 330-386, _start_bot_process)

## Overview

Bots are deployed automatically via the **backend's lifespan hook**. When the FastAPI server starts, it:
1. Discovers all available bot scripts
2. Scans for already-running bot processes (via psutil)
3. Auto-starts any discovered bots that aren't already running

## Discovery Mechanism

The `_discover_bots()` function in `backend/app.py` finds bots from two locations:

### 1. Legacy Bots (hardcoded)
Located in `C:\Trading\bots\` — only included if the script file exists on disk:
- `gold_bot` -> gold_bot_v3.py
- `scalping_bot` -> scalping_youtube_goldstrategy.py
- `streaming_bot` -> streaming_bot_v3.py
- `gold_phoenix` -> gold_phoenix_bot.py
- `scalping_hybrid` -> scalping_phoenix_hybrid.py

### 2. Multi-Pair Bots (dynamic discovery)
Scans `bots/active_bots/<PAIR>/run_<strategy>.py`:
- Each pair directory is scanned for `run_*.py` files
- Bot name is generated as `{StrategyDisplay}_{PAIR}` (e.g., `MACD_EURUSD`)
- Strategy name mapping: macd->MACD, goldphoenix->GoldPhoenix, bollinger->Bollinger, sma->SMA, volatility_breakout->VolatilityBreakout

## Auto-Start Lifecycle

```
Server startup
      │
      ▼
_seed_users()           # Create initial user store
      │
      ▼
_seed_accounts()        # Load accounts from agentx_store.json
      │
      ▼
_scan_running_bots()    # Use psutil to find already-running bot processes
      │
      ▼
_refresh_bot_scripts()  # Re-discover bots (catch newly added ones)
      │
      ▼
Auto-start loop          # For each discovered bot:
      │                    - Skip if already running
      │                    - Launch as subprocess.Popen
      │                    - Register in _bot_processes dict
      │
      ▼
Server ready
```

## Auto-Start Code (from app.py lifespan)

```python
for name, script_path in list(BOT_SCRIPTS.items()):
    if name in _bot_processes and _bot_processes[name].poll() is None:
        continue  # Already running
    try:
        proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(script_path.parent.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _bot_processes[name] = proc
        logger.info("Auto-started bot '%s' (PID %d)", name, proc.pid)
    except Exception as e:
        logger.error("Failed to auto-start bot '%s': %s", name, e)
```

**Note**: The lifespan auto-start uses `DEVNULL` for stderr (silent). The API-based start (`_start_bot_process`) uses a dedicated error log file per bot.

## Manual Start/Stop via API

### Start a Bot
```python
POST /api/bots/{name}/start
```
- Verifies bot is not already running
- Sets up PYTHONPATH with Hermess paths
- Creates log file at bots/logs/{name}_error.log
- Launches as DETACHED_PROCESS (continues running even if parent exits)
- Writes status to JSON store (db.upsert_bot)
- Publishes SSE event for real-time UI update
- Logs decision to decision_log

### Stop a Bot
```python
POST /api/bots/{name}/stop
```
- Terminates the process (graceful: SIGTERM, then SIGKILL after 5s timeout)
- Removes from _bot_processes dict
- Updates JSON store
- Publishes SSE event
- Logs decision

## Bot Script Anatomy (multi_symbol_bot.py)

Each run script in `active_bots/<PAIR>/run_<strategy>.py` follows this pattern:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from multi_symbol_bot import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--symbol", "AUDUSD", "--strategy", "bollinger"]
    main()
```

The `multi_symbol_bot.main()` function:
1. Connects to MT5 (via utils/mt5_connect.py)
2. Loads strategy class from backtester/active_strategies/<SYMBOL>/<strategy_file>.py
3. Applies guardrails: trade_guardrail, circuit_breaker (5-loss stop + FTMO drawdown), session_filters (regime mode)
4. Runs main loop: checks for signals -> validates -> executes trades via MT5
5. Logs to bots/logs/<symbol>_<strategy>.log

## Alternative: Unified Bot Runner

An alternative deployment approach exists at `bots/unified_bot_runner.py`:
- Runs ALL active bots in a single process with ONE MT5 connection
- Eliminates the "Terminal disconnected" loop caused by 11 processes fighting over MT5
- Uses a hardcoded BOT_ROSTER with 11 entries
- Not auto-started by the backend — must be launched manually

```bash
python unified_bot_runner.py           # runs all active pairs
python unified_bot_runner.py --dry     # dry-run: import checks only
python unified_bot_runner.py --interval 60  # custom check interval
```

## Production Commands

| Service | Command |
|---------|---------|
| Backend (HTTP) | `python -m backend --host 0.0.0.0 --port 8005` |
| Backend (HTTPS) | `python -m backend --host 0.0.0.0 --port 8443 --ssl-certfile backend/ssl/cert.pem --ssl-keyfile backend/ssl/key.pem` |
| Tunnel | `./cloudflared.exe tunnel run da2cf48b` |
| Watchdog | Cron job checks bridge/backend/tunnel every 1h — silent unless broken |
| Auto-Sync | GitHub auto-sync every hour via cron (HH:00 UTC) |

## Verification

After deployment, verify with:
```bash
curl http://localhost:8005/api/health          # Backend alive
curl http://127.0.0.1:5000/health              # Bridge alive
curl http://localhost:8005/api/bots             # List all bots + status
```
