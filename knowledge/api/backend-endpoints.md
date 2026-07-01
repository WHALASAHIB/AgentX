# Backend API Reference — AgentX Trading System

> **Source**: backend/app.py, BASELINE.md, README.md
> **Base URL**: http://localhost:8005 (HTTP) / https://inventra.website (Production)
> **Auth**: Session cookie (dev-mode bypass for Commander), Google OAuth 2.0, Access Codes

## System Health

### `GET /api/health`
System health + bridge status.

**Response**: `{"status": "ok", "bridge": "connected", "version": "...", "uptime": ...}`

## Authentication

### `GET /api/auth/login`
Redirects to Google OAuth login. Returns dev-mode info if OAuth not configured.

### `GET /api/auth/me`
Returns current user from session cookie or dev default ("Commander").

### `POST /api/auth/signin`
Dev-mode signin (accepts any credentials).
- **Body**: `{"email": "...", "password": "..."}`

### `POST /api/auth/signup`
Dev-mode signup.
- **Body**: `{"email": "...", "password": "..."}`

### `POST /api/auth/logout`
Clears session cookie.

### `GET /api/auth/login`
Google OAuth login redirect.

### `POST /api/auth/dev-login`
Dev login bypass.
- **Body**: `{"email": "..."}`
- **Default email**: whalasahibtrading@gmail.com

### `GET /api/auth/callback`
Google OAuth callback handler.

### `GET /api/auth/codes`
List all access codes with their status (admin only).
- **Auth**: Required

### `POST /api/auth/codes/generate`
Generate 5 fresh access codes for testers.
- **Auth**: Required
- **Response**: `{"status": "created", "count": 5, "codes": [...]}`

### `POST /api/auth/redeem`
Redeem an access code and get a session cookie.
- **Body**: `{"code": "...", "label": "..."}`

## Accounts

### `GET /api/accounts`
List all connected MT5 accounts.
- **Response**: Array of account objects with id, name, login, server, balance, status

## Trading Statistics

### `GET /api/stats`
Trading statistics aggregated across active account.

### `GET /api/positions`
Open positions on the active account.

## Bots

### `GET /api/bots`
List all registered bots with status.
- **Response**: Array of `{name, display_name, status, pid, script, last_error}`

### `POST /api/bots/{name}/start`
Start a bot by name.
- **Response**: `{"name": "...", "status": "running", "pid": ...}`

### `POST /api/bots/{name}/stop`
Stop a running bot.
- **Response**: `{"name": "...", "status": "stopped", "pid": ...}`

## Bridge (MT5)

### `GET /api/bridge/accounts/{id}/history`
Trade history for a specific account.
- **Path**: `{id}` = account identifier (e.g., mt5-demo, ftmo-10k)

### `GET /api/bridge/accounts/{id}/equity`
Equity curve data.

### `GET /api/bridge/accounts/{id}/stats`
Account statistics (PnL, win rate, drawdown, etc.).

### `GET /api/bridge/accounts/{id}/tick/{symbol}`
Live tick data for a symbol.

## Backtesting

### `GET/POST /api/backtest/*`
Backtesting endpoints (run, optimize, compare, Monte Carlo).

## FTMO

### `GET/POST /api/ftmo/*`
FTMO challenge tracking and compliance endpoints.

## Analytics

### `GET /api/analytics/*`
Strategy comparison, risk metrics, deep analytics.

## Script Editor

### `GET /api/editor/files`
List available script files in the editor.

## Settings

### `GET /api/settings/system`
System information (version, uptime, accounts).

## Real-Time Events

### `GET /api/events`
Server-Sent Events (SSE) stream for real-time updates.
- Connected accounts, trades, bot status changes

### `WS /api/ws/{path}`
WebSocket proxy -> MT5 Bridge.
- Proxies all WebSocket traffic to bridge at `ws://127.0.0.1:5000/{path}`

## Misc

### `POST /api/accounts/add`
Add a new MT5 account.
- **Body**: `{"id": "...", "name": "...", "login": 123, "password": "...", "server": "...", "terminal_path": "...", "symbols": [...], "enabled": true}`

## Complete Endpoint Summary

| Method | Endpoint | Category | Purpose |
|--------|----------|----------|---------|
| GET | /api/health | Health | System health + bridge status |
| GET | /api/auth/me | Auth | Current user (dev: Commander) |
| POST | /api/auth/signin | Auth | Dev-mode signin |
| POST | /api/auth/signup | Auth | Dev-mode signup |
| POST | /api/auth/logout | Auth | Logout |
| GET | /api/auth/login | Auth | Google OAuth login |
| POST | /api/auth/dev-login | Auth | Dev login bypass |
| GET | /api/auth/callback | Auth | OAuth callback |
| GET | /api/auth/codes | Auth | List access codes |
| POST | /api/auth/codes/generate | Auth | Generate access codes |
| POST | /api/auth/redeem | Auth | Redeem access code |
| GET | /api/accounts | Accounts | List accounts |
| POST | /api/accounts/add | Accounts | Add account |
| GET | /api/stats | Stats | Trading statistics |
| GET | /api/positions | Positions | Open positions |
| GET | /api/bots | Bots | Registered bots |
| POST | /api/bots/{name}/start | Bots | Start bot |
| POST | /api/bots/{name}/stop | Bots | Stop bot |
| GET | /api/bridge/accounts/{id}/history | Bridge | Trade history |
| GET | /api/bridge/accounts/{id}/equity | Bridge | Equity curve |
| GET | /api/bridge/accounts/{id}/stats | Bridge | Account stats |
| GET | /api/bridge/accounts/{id}/tick/{symbol} | Bridge | Live tick |
| GET/POST | /api/backtest/* | Backtest | Backtesting suite |
| GET/POST | /api/ftmo/* | FTMO | FTMO challenge tracking |
| GET | /api/analytics/* | Analytics | Deep analytics |
| GET | /api/editor/files | Editor | Script files |
| GET | /api/settings/system | Settings | System info |
| GET | /api/events | Events | SSE event stream |
| WS | /api/ws/{path} | WebSocket | Proxy to bridge |

**75+ REST endpoints** total, including sub-resources under backtest, ftmo, analytics, and editor categories.

## Frontend Routes

| Route | Page | Description |
|-------|------|-------------|
| / | Command Center | Real-time trading overview, KPI cards, equity chart |
| /portfolio | Portfolio Dashboard | Account positions, strategy allocation, risk metrics |
| /trades | Trade Journal | Complete trade history with smart filters |
| /backtesting | Backtesting Lab | Strategy validation, Monte Carlo, Walk-Forward |
| /bots | Bot Control Room | Start/stop/monitor/edit trading bots |
| /scripts | Script Editor | Monaco editor with deploy flow |
| /ai | AI Orchestrator | Multi-agent status and commands |
| /accounts | Account Manager | Multi-account switching |
| /analytics | Analytics Suite | Deep metrics, strategy comparison, risk analysis |
| /settings | Settings | Configuration, integrations, security |
| /signin | Sign In | Login page |
| /signup | Sign Up | Registration page |

## Security

- **Google OAuth 2.0** (primary auth)
- **Access Codes** (secondary auth, 5-tester system)
- **JWT sessions** with Redis support (Redis currently disconnected)
- **Dev-mode bypass** — auto signin as Commander with cookie
- **Scanner blocker** — `.php`, `/wp-`, `/xmlrpc` requests return 404
- **No secrets in code** — all in `.env.*` (gitignored)
- **CORS** — open for dev (`allow_origins=["*"]`), restrict for production
