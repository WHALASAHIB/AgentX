# AGENTX Backend API Reference

> Base URL: `https://agentx.nousresearch.com` (production) | `http://localhost:9000` (dev)  
> Auth: Bearer token (JWT) obtained via Google OAuth or dev-login  
> Content-Type: `application/json`

---

## 1. Authentication

### POST /api/v1/auth/login
Initiate Google OAuth login flow. Redirects user to Google consent screen.

**Response:** `302` redirect to `https://accounts.google.com/o/oauth2/auth?...`

### POST /api/v1/auth/callback
OAuth callback endpoint. Google returns auth code here.

**Params (query):** `code`, `state`  
**Response:**
```json
{ "token": "eyJhbGci...", "user": { "email": "...", "name": "..." }, "expires_in": 86400 }
```

### POST /api/v1/auth/dev-login
Development-only: bypass OAuth with a preconfigured dev account.

**Body:**
```json
{ "email": "dev@agentx.local" }
```
**Response:** Same JWT payload as callback.

### POST /api/v1/auth/logout
Invalidate current session.

**Headers:** `Authorization: Bearer <token>`  
**Response:** `{ "message": "Logged out" }`

### POST /api/v1/auth/codes/generate
Generate an access code (for granting access to new users).

**Body:**
```json
{ "max_uses": 5, "expires_in_hours": 48 }
```
**Response:**
```json
{ "code": "AGX-XXXX-YYYY", "max_uses": 5, "expires_at": "2026-06-22T12:00:00Z" }
```
**Example:**
```bash
curl -X POST https://agentx.nousresearch.com/api/v1/auth/codes/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_uses": 3, "expires_in_hours": 24}'
```

### POST /api/v1/auth/codes/redeem
Redeem an access code to create an account.

**Body:**
```json
{ "code": "AGX-XXXX-YYYY", "email": "newuser@example.com" }
```
**Response:** JWT token + user object.

### GET /api/v1/auth/codes
List all generated access codes (admin only).
```bash
curl -H "Authorization: Bearer $TOKEN" https://agentx.nousresearch.com/api/v1/auth/codes
```

---

## 2. Health & Configuration

### GET /api/v1/health
System health check.

**Response:**
```json
{
  "status": "ok",
  "uptime": 123456,
  "version": "2.5.0",
  "services": {
    "postgres": "connected",
    "redis": "connected",
    "mt5_bridge": "connected",
    "ollama": "available"
  }
}
```
```bash
curl https://agentx.nousresearch.com/api/v1/health
```

### GET /api/v1/config/magic-numbers
List all registered Magic Numbers with their allocations.

**Response:**
```json
{
  "strategy_mapping": {
    "MACD": { "base": 1001, "range": [1001, 1050] },
    "GoldPhoenix": { "base": 2001, "range": [2001, 2050] },
    "Bollinger": { "base": 3001, "range": [3001, 3050] },
    "SMA": { "base": 4001, "range": [4001, 4050] }
  },
  "in_use": [1001, 1002, 2001, 3001, 3002]
}
```

### GET /api/v1/diagnostic
Full diagnostic report — system health, active bot count, resource usage, bridge status.
```bash
curl -H "Authorization: Bearer $TOKEN" https://agentx.nousresearch.com/api/v1/diagnostic
```

---

## 3. Accounts

### GET /api/v1/accounts
List all trading accounts.

**Response:**
```json
[
  {
    "id": "acc_01",
    "name": "FTMO-01",
    "broker": "FTMO",
    "platform": "mt5",
    "server": "FTMO-Demo",
    "account_type": "challenge",
    "balance": 100000,
    "currency": "USD",
    "leverage": 30,
    "status": "active"
  }
]
```

### GET /api/v1/accounts/active
Get currently active trading account.

### POST /api/v1/accounts/switch
Switch active trading context.

**Body:**
```json
{ "account_id": "acc_02" }
```

### GET /api/v1/accounts/{id}
Get detailed account info including open positions, daily P&L, drawdown.

### POST /api/v1/accounts
Add a new trading account.

**Body:**
```json
{
  "name": "FTMO-02",
  "broker": "FTMO",
  "server": "FTMO-Demo",
  "account_type": "challenge",
  "balance": 100000,
  "login": 12345678,
  "password": "encrypted_via_wcm",
  "leverage": 30
}
```

### DELETE /api/v1/accounts/{id}
Remove a trading account.

### GET /api/v1/accounts/{id}/test
Test connection to the account's broker server.

---

## 4. Stats, Positions & Bots

### GET /api/v1/stats
Overall trading statistics.

**Query params:** `from`, `to`, `account_id`

### GET /api/v1/positions
Open positions for active account.

**Query params:** `symbol`, `magic`

### GET /api/v1/bots
List all configured trading bots.

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" https://agentx.nousresearch.com/api/v1/bots
```

### POST /api/v1/bots
Create a new bot instance.

**Body:**
```json
{
  "strategy": "GoldPhoenix",
  "account_id": "acc_01",
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "risk_percent": 0.15,
  "magic_number": 2001,
  "params": { "fast_ema": 12, "slow_ema": 26, "signal_sma": 9 }
}
```

### GET /api/v1/bots/{id}
Get bot details, configuration, and current status.

### PUT /api/v1/bots/{id}
Update bot configuration.

### DELETE /api/v1/bots/{id}
Remove a bot.

### POST /api/v1/bots/{id}/start
Start the bot (attach to market).

### POST /api/v1/bots/{id}/stop
Stop the bot (detach, close positions if configured).

### GET /api/v1/bots/{id}/status
Real-time bot status: running, stopped, error, circuit_breaker_active.

---

## 5. Bridge Proxy (MT5)

### GET /api/v1/bridge/history
Trade history from MT5 bridge.

**Query params:** `from`, `to`, `symbol`, `magic`

### GET /api/v1/bridge/equity
Current equity curve data.

### GET /api/v1/bridge/positions
Positions as reported by MT5 bridge.

### GET /api/v1/bridge/stats
Bridge-level statistics (latency, uptime, requests served).

### GET /api/v1/bridge/tick?symbol=XAUUSD
Latest tick data for a symbol.

---

## 6. Trades

### GET /api/v1/trades
List trades with filtering.

**Query params:** `status` (open|closed), `symbol`, `strategy`, `from`, `to`, `tag`, `magic`

### PUT /api/v1/trades/{id}/tags
Add/remove tags on a trade.

**Body:**
```json
{ "add": ["FTMO-safe", "winning"], "remove": ["review"] }
```

### PUT /api/v1/trades/{id}/notes
Attach notes to a trade.

**Body:**
```json
{ "note": "Entry based on MACD divergence on M15. TP1 hit at +25 pips." }
```

### POST /api/v1/trades/filter
Advanced trade filter with pagination.

**Body:**
```json
{
  "strategies": ["MACD", "GoldPhoenix"],
  "date_range": { "from": "2026-06-01", "to": "2026-06-20" },
  "tags": ["FTMO-safe"],
  "sort": "profit_desc",
  "page": 1,
  "per_page": 50
}
```

---

## 7. Backtesting

### GET /api/v1/backtest/strategies
List available backtesting strategies.

### POST /api/v1/backtest/run
Run a standard backtest.

**Body:**
```json
{
  "strategy": "MACD",
  "symbol": "EURUSD",
  "timeframe": "H1",
  "from": "2025-01-01",
  "to": "2025-12-31",
  "params": { "fast_ema": 12, "slow_ema": 26 },
  "initial_balance": 10000,
  "risk_percent": 0.15
}
```
**Example:**
```bash
curl -X POST https://agentx.nousresearch.com/api/v1/backtest/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy":"MACD","symbol":"EURUSD","timeframe":"H1","from":"2025-01-01","to":"2025-12-31","params":{"fast_ema":12,"slow_ema":26},"initial_balance":10000,"risk_percent":0.15}'
```

### POST /api/v1/backtest/optimize
Run parameter optimization.

**Body:**
```json
{
  "strategy": "Bollinger",
  "symbol": "GBPUSD",
  "timeframe": "H1",
  "from": "2025-01-01",
  "to": "2025-12-31",
  "params_grid": {
    "period": [14, 20, 26],
    "std_dev": [1.5, 2.0, 2.5]
  },
  "optimization_metric": "sharpe_ratio"
}
```

### POST /api/v1/backtest/custom
Run custom strategy backtest with user-defined logic.

### POST /api/v1/backtest/compare
Compare multiple backtest results side-by-side.

**Body:**
```json
{
  "runs": ["bt_abc123", "bt_def456", "bt_ghi789"],
  "metrics": ["profit_factor", "sharpe_ratio", "max_drawdown", "win_rate", "total_trades"]
}
```

---

## 8. Editor (Strategy Code)

### GET /api/v1/editor/files
List strategy files available for editing.

### GET /api/v1/editor/read/{path}
Read a strategy file's contents.

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://agentx.nousresearch.com/api/v1/editor/read/strategies/macd.py
```

### POST /api/v1/editor/save
Save modified strategy file.

**Body:**
```json
{
  "path": "strategies/macd.py",
  "content": "def calculate():\n    ...",
  "commit_message": "Optimized MACD entry logic"
}
```

### POST /api/v1/editor/deploy
Deploy edited strategy to production bots.

**Body:**
```json
{
  "path": "strategies/macd.py",
  "bot_ids": ["bot_001", "bot_002"],
  "hot_reload": true
}
```

### GET /api/v1/editor/history/{path}
View edit history for a strategy file.

---

## 9. Research Division

### GET /api/v1/research/division-status
Get status of all Research Division agents: Collector, Analyst, Sprint Master, Innovator, Deployer.

**Response:**
```json
{
  "collector": { "status": "idle", "last_run": "2026-06-20T08:00:00Z", "articles_processed": 142 },
  "analyst": { "status": "active", "last_run": "2026-06-20T08:05:00Z", "insights_generated": 7 },
  "sprint_master": { "status": "idle", "sprint_phase": "planning" },
  "innovator": { "status": "idle", "proposals_pending": 3 },
  "deployer": { "status": "completed", "last_deployment": "2026-06-20T08:30:00Z" }
}
```

### POST /api/v1/research/sprint
Trigger a sprint cycle manually.

### POST /api/v1/research/insights
Request fresh insights from the Analyst agent.

### GET /api/v1/research/report
Get latest research report.

### POST /api/v1/research/run-now
Force-run the full Research Division cycle.

---

## 10. Orchestrator

### GET /api/v1/orchestrator/agents
List orchestrator agents and their current tasks.

### POST /api/v1/orchestrator/command
Send a command to an orchestrator agent.

**Body:**
```json
{
  "agent": "sprint_master",
  "command": "start_sprint",
  "params": { "bots": ["bot_001", "bot_002"], "duration_hours": 4 }
}
```

### GET /api/v1/orchestrator/timeline
Get orchestrator event timeline.

---

## 11. FTMO

### GET /api/v1/ftmo/challenges
List FTMO challenges and their status.

### POST /api/v1/ftmo/trade
Execute a trade compliant with FTMO rules (max drawdown check, daily loss limit, position sizing).

**Body:**
```json
{
  "challenge_id": "ftmo_01",
  "symbol": "EURUSD",
  "volume": 0.1,
  "type": "buy",
  "sl_pips": 20,
  "tp_pips": 40,
  "ftmo_rules_compliant": true
}
```

### POST /api/v1/ftmo/advance
Advance challenge phase (Phase 1 → Phase 2 → Funded).

### GET /api/v1/ftmo/profiles
List FTMO compliance profiles.

### GET /api/v1/ftmo/summary
Overall FTMO performance summary across all challenges.

---

## 12. Sentiment

### GET /api/v1/sentiment/score?symbol=XAUUSD
Get current sentiment score for a symbol.

**Response:**
```json
{
  "symbol": "XAUUSD",
  "score": 62.4,
  "classification": "bullish",
  "sources": {
    "news": 68,
    "social": 55,
    "polymarket": 64
  },
  "updated_at": "2026-06-20T10:30:00Z"
}
```

### POST /api/v1/sentiment/refresh
Force-refresh sentiment cache.

---

## 13. SSE Events (Server-Sent Events)

### GET /api/v1/events
Stream real-time system events.

**Events:**
- `bot:started` / `bot:stopped` / `bot:error`
- `trade:opened` / `trade:closed`
- `sre:alert` — resource threshold breached
- `aiops:anomaly` — anomaly detected
- `research:insight` — new insight published
- `sprint:phase_change`

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  https://agentx.nousresearch.com/api/v1/events
```

---

## 14. Settings

### GET /api/v1/settings
Get system and user settings.

### PUT /api/v1/settings
Update settings.

**Body:**
```json
{
  "risk_percent_default": 0.15,
  "circuit_breaker_max_cons_loss": 5,
  "trailing_stop_activation": 20,
  "trailing_stop_distance": 10,
  "notion_auto_push": true,
  "max_active_bots": 8
}
```

---

## 15. File Conversion

### POST /api/v1/convert
Convert strategy files between formats (Python <-> MQL5).
```bash
curl -X POST https://agentx.nousresearch.com/api/v1/convert \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "strategies/macd.py", "target_format": "mql5"}'
```
