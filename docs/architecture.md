# System Architecture

## High-Level Overview

The trading system is an algorithmic trading platform running on a Windows 11 host with
a VirtualBox VM (10.10.10.100) hosting the backend services, while the host machine
(10.10.10.1) runs MetaTrader 5 (MT5) and the 23 trading bots. The backend is a FastAPI
Python application serving a single-page dashboard via HTTP on port 8005.

## ASCII Architecture Diagram

```
                          +-----------------------+
                          |    User / Browser      |
                          | (Dashboard HTML/JS)   |
                          +----------+------------+
                                     | HTTP :8005
                                     v
                +--------------------+--------------------+
                |         FastAPI Backend (Python)        |
                |  backend/app.py (~2025 lines)           |
                |  Port 8005 / CORS enabled               |
                |  Auth: Google OAuth + Access Codes      |
                |  DB: SQLite (backend/db/pool.py)        |
                |  Cache: Optional Redis                  |
                +---+----------------+-------------------+
                    |                |
                    | REST           | REST
                    v                v
       +------------+----+   +------+-------------+
       | Research     |   | MT5 Bridge           |
       | Division     |   | bridge_client.py     |
       | /research_   |   | Port 5000            |
       | division/    |   | Connects to MT5 on   |
       | (4 modules)  |   | host 10.10.10.1      |
       +------+-------+   +----------+-----------+
              |                       |
              |               +-------v--------+
              |               |  MetaTrader 5   |
              |               |  (Host Machine) |
              |               +-------+--------+
              |                       |
              |              +--------v--------+
              |              |  23 Trading Bots |
              |              |  - 4 Legacy Bots |
              |              |  - MACD (9 pairs)|
              |              |  - GoldPhoenix   |
              |              |  - Bollinger     |
              |              |  - SMA           |
              |              |  - Multi-symbol  |
              |              +-----------------+
              |
       +------v--------+
       |  Notion API    |
       |  (Dashboards/  |
       |   Reports)     |
       +---------------+
```

## Component Descriptions

### 1. Backend (FastAPI)
- **File:** `backend/app.py` (~2025 lines)
- **Port:** 8005
- **Database:** SQLite via `backend/db/pool.py`
- **Auth:** Google OAuth + access codes via `backend/auth.py`
- **CORS:** Enabled for cross-origin dashboard access
- **Redis:** Optional, used for caching if configured
- **Endpoints:** Serves the dashboard HTML, REST API for bot control, trade journal,
  portfolio, backtesting, accounts, FTMO, analytics, settings, file converter, and
  research division data.

### 2. Dashboard (Frontend)
- **File:** `frontend/public/index.html` (~2750 lines)
- **Architecture:** Single HTML file with inline CSS and vanilla JavaScript
- **Charts:** Chart.js loaded from CDN (no local fallback)
- **API Base:** Empty string (relative API calls to same origin)
- **Sections:** CommandCenter, Portfolio, TradeJournal, Backtest, Bots, Scripts,
  Orchestrator, Accounts, FTMO, Analytics, Settings, FileConverter

### 3. MT5 Bridge
- **File:** `backend/bridge_client.py`
- **Port:** 5000
- **Purpose:** Connects the Python backend to MetaTrader 5 running on the host
- **Connection:** Host machine at 10.10.10.1 communicates with VM at 10.10.10.100
- **Data Flow:** Market data from MT5 is relayed through the bridge to the bots and
  backend for analysis and trade execution.

### 4. Trading Bots (23 Total)
- **4 Legacy Bots:** gold_bot (PID 1724), gold_phoenix (PID 10672),
  scalping_bot (PID 1916), streaming_bot (PID 12800)
- **Multi-Pair Bots:** Organized under `bots/active_bots/{PAIR}/run_{strategy}.py`
  - MACD: 9 pairs (PID 2456)
  - GoldPhoenix: 5 pairs (PID 2348)
  - Bollinger: 3 pairs (PID 7888)
  - SMA: 2 pairs (PID 7524)
- **Main Bot:** `bots/multi_symbol_bot.py`

### 5. Research Division
- **Location:** `research_division/`
- **Modules:**
  - `analytics_engine.py` — Full analytics computation (win rate, profit factor,
    drawdown, session analysis, per-pair KPIs)
  - `run.py` — Full cycle runner (data_collect → analytics → innovate → deploy → report)
  - `deployment_engine.py` — Backtest on MT5, deploy improvements with rollback
  - `sprint_manager.py` — Sprint tracking with items
  - `strategy_innovation.py` — Strategy variant generation
- **Schedule:** Runs every 4 hours via Hermes cron (job_id: 37931b893b53)
- **Reports:** JSON output to `research_division/reports/`

### 6. Notion Integration
- The backend communicates with Notion for dashboard and report publishing.
- Credentials stored in `.env.keys` and `.env.cloudflare`.

## Data Flow

```
Market Data Feeds
       |
       v
 MetaTrader 5 (Host: 10.10.10.1)
       |
       v
 MT5 Bridge (bridge_client.py, Port 5000)
       |
       v
 Trading Bots (23 instances on Host)
       |
       +--> Trade Execution (MT5)
       |
       v
 FastAPI Backend (Port 8005, VM: 10.10.10.100)
       |
       +--> SQLite Database (trade records, portfolio state)
       +--> Redis Cache (optional)
       |
       v
 Research Division (every 4 hours)
       |
       +--> Analytics Reports (JSON)
       +--> Strategy Improvements
       |
       v
 Dashboard (HTTP served to browser)
       |
       v
 Notion (published dashboards/reports)
```

## Port Mapping

| Service          | Port | Location        |
|------------------|------|-----------------|
| FastAPI Backend  | 8005 | VM 10.10.10.100 |
| MT5 Bridge       | 5000 | Host 10.10.10.1 |

## Network Layout

- **VM Address:** 10.10.10.100 — runs the FastAPI backend, research division (cron),
  and serves the dashboard
- **Host Address:** 10.10.10.1 — runs MetaTrader 5, all 23 trading bots, and the
  MT5 bridge client
- The network bridge between host and VM allows the backend to query the bridge
  for market data and trade status.

## Security

- **Google OAuth:** Users authenticate via Google OAuth for dashboard access.
- **Access Codes:** Secondary authentication mechanism for bot/API access.
- **Environment Files:**
  - `.env.keys` — API keys, secrets, OAuth credentials
  - `.env.cloudflare` — Cloudflare tunnel/access configuration
- **No hardcoded secrets:** All credentials are loaded from environment files at
  runtime by the backend.

## Technology Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Backend       | Python 3.12, FastAPI, Uvicorn       |
| Database      | SQLite (via pool.py connection pool)|
| Cache         | Redis (optional)                    |
| Frontend      | Vanilla JS, HTML5, CSS3             |
| Charts        | Chart.js (CDN)                      |
| Auth          | Google OAuth 2.0                    |
| Trading       | MetaTrader 5, MQL5                  |
| Bridge        | Python socket/HTTP bridge client    |
| Automation    | Hermes cron (research cycle)        |
| Reporting     | JSON files to research_division/    |
