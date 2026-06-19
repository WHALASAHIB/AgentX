# Dashboard Reference

## Overview

The trading dashboard is a single-page web application served by the FastAPI
backend. It is implemented as a single HTML file (`frontend/public/index.html`,
~2750 lines) with inline CSS and vanilla JavaScript. It provides a comprehensive
interface for monitoring and controlling the entire trading system.

## Frontend Architecture

- **File:** `frontend/public/index.html` (~2750 lines)
- **Dependencies:** Chart.js (loaded from CDN, no local fallback)
- **API Base:** Empty string (`API_BASE = ''`) — all calls relative to port 8005
- **Styling:** Inline CSS, no external stylesheets
- **JavaScript:** Vanilla JS, no frameworks (React, Vue, etc.)
- **Charts:** Chart.js via CDN for equity curves and analytics visualizations

## Sections

The dashboard has 12 sections accessible via sidebar/top navigation:

### 1. CommandCenter
System-wide controls: overall health, bridge status, bot count (online vs total),
emergency stop/kill switches, quick action buttons.

### 2. Portfolio
Account-level info: balance, equity, margin, free margin, open positions across
all bots, daily/weekly/monthly P&L, equity curve chart (Chart.js).

### 3. TradeJournal
Historical trade log with filters (bot, pair, date range, win/loss), paginated
trade list with entry/exit prices, pips, profit, export functionality.

### 4. Backtest
Strategy backtesting: select strategy/pair/date range/parameters, run via
backend, view profit curve, win rate, drawdown, compare runs.

### 5. Bots
All 23 bots with online/offline/error status, per-bot details (PID, strategy,
pairs, uptime, last trade), start/stop/restart controls, config viewer.
Health check timeout: 10s (increased from 3s to avoid false offline).

### 6. Scripts
Available trading/utility scripts, run on demand, view output/logs, schedule.

### 7. Orchestrator
Coordinated multi-bot operations: group actions, coordinated execution, risk
management rules, scheduled operations.

### 8. Accounts
Configured trading accounts with broker/server/login details, add/edit/remove,
dashboard account switching.

### 9. FTMO
Prop firm challenge tracking: profit targets, trading days, risk limits,
compliance checking, phase tracking (Phase 1, Phase 2, Funded).

### 10. Analytics
Research Division dashboards: win rate charts, profit factor trends, drawdown
analysis, session performance comparison, research report viewer.

### 11. Settings
Google OAuth config, access codes, API keys, Notion integration, theme, logging.

### 12. FileConverter
Trade history format conversion: CSV/JSON/XLSX import/export, MT4-to-MT5
conversion, batch processing.

## API Endpoints the Frontend Calls

The dashboard makes relative API calls (API_BASE = '') for all sections:

| Endpoint                       | Method | Sections            |
|--------------------------------|--------|---------------------|
| `/api/health`                  | GET    | CommandCenter       |
| `/api/portfolio`               | GET    | Portfolio           |
| `/api/trades`                  | GET    | TradeJournal        |
| `/api/trades/recent`           | GET    | TradeJournal        |
| `/api/backtest/run`            | POST   | Backtest            |
| `/api/backtest/results`        | GET    | Backtest            |
| `/api/bots/status`             | GET    | Bots                |
| `/api/bots/start`              | POST   | Bots                |
| `/api/bots/stop`               | POST   | Bots                |
| `/api/bots/restart`            | POST   | Bots                |
| `/api/scripts/list`            | GET    | Scripts             |
| `/api/scripts/run`             | POST   | Scripts             |
| `/api/orchestrator/status`     | GET    | Orchestrator        |
| `/api/orchestrator/action`     | POST   | Orchestrator        |
| `/api/accounts`                | GET    | Accounts            |
| `/api/ftmo/status`             | GET    | FTMO                |
| `/api/ftmo/update`             | POST   | FTMO                |
| `/api/analytics/summary`       | GET    | Analytics           |
| `/api/research/division-status`| GET    | Analytics           |
| `/api/research/report`         | GET    | Analytics           |
| `/api/research/insights`       | GET    | Analytics           |
| `/api/settings`                | GET    | Settings            |
| `/api/settings/update`         | POST   | Settings            |
| `/api/fileconverter/convert`   | POST   | FileConverter       |
| `/api/fileconverter/export`    | GET    | FileConverter       |

The candles endpoint (`/api/candles`) was removed in a previous fix.

## Health/Offline Detection System

The dashboard periodically calls `/api/health`. On failure, it marks the backend
as offline and shows warnings. Each section has independent loading/error states.

**Configuration:** Timeout is 10 seconds (increased from 3s), retry every 5-10s.
Auto-refresh guards prevent overlapping requests.

**Fixes Applied:**
- Health check timeout 3s → 10s (reduced false offline detections)
- Offline detection: proper distinction between "not responding" and "slow"
- Auto-refresh guards prevent race conditions
- Button events decoupled from health check status

## CDN Dependency

Chart.js is loaded from CDN with NO local fallback. If CDN is unreachable,
all chart-dependent sections (Portfolio equity curve, Analytics charts) show
empty containers. Workaround: download Chart.js locally and update the script
tag in index.html.

## Common Fixes Applied

| Fix                          | Description                                    |
|------------------------------|------------------------------------------------|
| Health check timeout 3s→10s  | Reduced false offline detections               |
| Offline detection fixed      | Better down vs slow distinction                |
| Candles endpoint removed     | Unused endpoint cleanup                        |
| Auto-refresh guards          | Prevented race conditions                      |
| Button decoupling            | Buttons work independently of health check     |

## How to Modify the Dashboard

1. Edit `frontend/public/index.html`
2. Add a section: create a `<div>` with ID, add nav entry, wire JS
3. Add an API call: use `fetch('/api/new-endpoint')`
4. Add a chart: include `<canvas>`, initialize Chart.js in JS
5. Refresh page — no build step needed (vanilla HTML/JS)
6. Test: verify all sections, health check, offline detection, charts

## Browser Compatibility

Tested with Google Chrome (recommended), Firefox, Edge, Opera. IE not supported.
