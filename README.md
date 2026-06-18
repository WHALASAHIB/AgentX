# AGENTX — AI-Powered Algorithmic Trading System 🚀

> **Enterprise-Grade Trading Automation** | MetaTrader 5 | Cloudflare Tunnel | 4 Trading Bots | AI Orchestration

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Components](#-components)
- [Trading Bots](#-trading-bots)
- [Backtesting Engine](#-backtesting-engine)
- [Frontend Dashboard](#-frontend-dashboard)
- [API Reference](#-api-reference)
- [Deployment](#-deployment)
- [Cron Jobs & Automation](#-cron-jobs--automation)
- [Research & Innovation](#-research--innovation)
- [Setup Guide](#-setup-guide)
- [Future Roadmap](#-future-roadmap)

---

## 🎯 Overview

**AGENTX** is a fully automated algorithmic trading platform designed to pass **FTMO prop firm challenges** and scale to **$1M in 12 months**. It runs 4 concurrent trading bots on MetaTrader 5, with a real-time dashboard, backtesting engine, sentiment analysis, and AI orchestration — all deployed on a Windows Hyper-V VM behind Cloudflare Tunnel.

### Key Metrics
| Metric | Value |
|---|---|
| **Running Bots** | 4 concurrent |
| **Trading Instrument** | XAUUSD (Gold) |
| **Account Balance** | $91,881.97 (Demo) |
| **Historic Trades** | 754 |
| **Backend Uptime** | Auto-start on boot |
| **Domain** | inventra.website (Cloudflare) |

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Hyper-V VM (10.10.10.100)                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────────┐   │
│  │  MT5      │◄───│  Bridge  │◄───│  FastAPI Backend :8003   │   │
│  │  Terminal │    │  :5000   │    │  (Bot Manager + Auth)    │   │
│  └──────────┘    └──────────┘    └──────────┬───────────────┘   │
│        ▲                                     │                   │
│        │                    ┌─────────────────┼──────────────┐  │
│        │                    │  ┌──────────┐  ┌──────────┐   │  │
│        │                    │  │Gold      │  │Gold Bot  │   │  │
│        │                    │  │Phoenix   │  │V3        │   │  │
│        │                    │  └──────────┘  └──────────┘   │  │
│        │                    │  ┌──────────┐  ┌──────────┐   │  │
│        │                    │  │Scalping  │  │Streaming │   │  │
│        │                    │  │Bot       │  │Bot V3    │   │  │
│        │                    │  └──────────┘  └──────────┘   │  │
│        │                    └───────────────────────────────┘  │
│        │                                │                      │
│        │                    ┌───────────▼──────────────┐       │
│        │                    │  Sentiment Engine :8001  │       │
│        │                    │  (News + Polymarket +    │       │
│        │                    │   MT5 Trend Analysis)    │       │
│        │                    └──────────────────────────┘       │
│        │                                │                      │
│        │                    ┌───────────▼──────────────┐       │
│        │                    │  AI Orchestrator          │       │
│        │                    │  (7 HermesJatti Divisions)│       │
│        │                    └──────────────────────────┘       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Cloudflare Tunnel   │
                    │  (Named: da2cf48b…) │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  inventra.website    │
                    │  (Proxied via        │
                    │   Cloudflare)        │
                    └─────────────────────┘
```

### Data Flow
1. **Bridge** connects to MT5 Terminal → fetches real-time prices, account info, open positions
2. **Bots** read market data via Bridge → apply strategies → send trade signals back through Bridge
3. **Backend** orchestrates everything: manages bot lifecycle, serves dashboard API, stores trade history
4. **Frontend** (SPA) displays everything: portfolio, open trades, equity curve, analytics
5. **Cloudflare Tunnel** exposes the backend securely to the internet without port forwarding
6. **Sentiment Engine** analyzes news, prediction markets, and market structure for trade filtering

---

## 🔧 Components

### 1. MT5 Bridge (`bridge/`)
- **Port:** 5000
- **Stack:** Python, FastAPI, MetaTrader5 library
- **Endpoints:** `/health`, `/api/v1/accounts`, `/api/v1/accounts/{id}/positions`, `/api/v1/accounts/{id}/history`, `/api/v1/accounts/{id}/stats`, `/api/v1/accounts/{id}/equity`, `/api/v1/accounts/{id}/tick/{symbol}`
- **Features:** Multiple account support, stale data detection, equity curve tracking

### 2. Backend Server (`backend/`)
- **Port:** 8003
- **Stack:** FastAPI, SQLite, Redis (optional)
- **Role:** Bot manager, API gateway, auth provider, backtesting API
- **Auth:** Access code system (5 testers) + Google OAuth + dev login
- **Bot scripts map:** `backend/app.py` → `BOT_SCRIPTS` dict defines all managed bots

### 3. Frontend (`frontend/public/`)
- **Type:** Single-page application (vanilla JS + Chart.js)
- **Features:** 
  - Command Center (live trading dashboard)
  - Portfolio view + equity chart
  - Trade journal with filtering
  - Analytics (win rate, profit factor, drawdown)
  - FTMO Challenge Manager
  - AI Orchestrator panel
  - Script editor + file converter
  - Dark/Light theme
  - Auto-refresh (15s intervals)

### 4. Cloudflare Tunnel
- **Type:** Named tunnel (persistent ID)
- **Tunnel ID:** `da2cf48b-5b1f-4e28-9b7c-8d7bce6ec1a6`
- **Domain:** `inventra.website` → CNAME → tunnel
- **Config:** `~/.cloudflared/config.yml`
- **Auto-start:** Windows Startup (AGENTX_Startup.bat)

### 5. Sentiment Engine (`research/sentiment_engine.py`)
- **Sources:** Google News RSS, Polymarket API, MT5 trend analysis
- **Output:** Score -10 to +10
- **Integration:** Imported by bots at runtime; filters trade signals

### 6. AI Orchestrator (`agents/orchestrator.py`)
- **Divisions:** Software Engineering, Data Science, AI & Automation, Trading, Business Intelligence, QA, R&I
- **Schedule:** Board meetings at 7AM/8AM/9AM HKT daily
- **Output:** Daily reports, trade recommendations, research briefs

---

## 🤖 Trading Bots

All bots trade **XAUUSD (Gold)** on MetaTrader 5 Demo.

| Bot | File | PID | Type | Description |
|---|---|---|---|---|
| **Gold Phoenix** | `gold_phoenix_bot.py` | 13664 | Trend Following | ADX + Squeeze strategy; 75% win rate in backtests |
| **Gold Bot V3** | `gold_bot_v3.py` | 15128 | Multi-Timeframe | MTF analysis with volume confirmation |
| **Scalping Bot** | `scalping_youtube_goldstrategy.py` | 7716 | Scalping | 1-min scalping, high frequency, YouTube-based strategy |
| **Streaming Bot V3** | `streaming_bot_v3.py` | 2272 | Market Making | Tick-by-tick streaming, small consistent profits |

### Bot Lifecycle
- **Auto-spawn:** Backend spawns all bots as subprocesses on startup
- **Live re-scan:** `/api/bots` endpoint checks process health on every request
- **Restart:** POST `/api/bots/{name}/stop` + `/api/bots/{name}/start`
- **Persistence:** Bots restart automatically if backend restarts

---

## 📊 Backtesting Engine (`backtester/`)

A production-grade backtesting framework with FTMO challenge simulation.

### Features
- **28 metrics:** Total Return, Win Rate, Profit Factor, Sharpe Ratio, Max DD, Recovery Factor, Expectancy, Avg Trade, Pips, etc.
- **FTMO Simulation:** Phase 1 (10% profit, 10% DD), Phase 2 (5% profit, 5% DD), Funded (80% split)
- **Commission:** Realistic per-symbol spreads + commissions
- **Margin calls:** Auto-stops at $0 equity
- **Symbol support:** XAUUSD, EURUSD, BTCUSD, and more
- **Export:** CSV and JSON download from dashboard

### Strategies
- Gold Phoenix Strategy (custom)
- Multiple built-in strategies in `strategies/` and `custom_strategies/`
- Load custom strategies dynamically via `loader.py`

---

## 🌐 Frontend Dashboard

The dashboard is a **162KB single HTML file** with embedded CSS/JS (no build step needed).

### Sections
1. **Command Center** — Live market data, XAUUSD ticker, equity chart, trade buttons
2. **Portfolio** — Positions, balance, equity, margin, open P&L
3. **Trade Journal** — Full trade history with filters (by magic number, date range)
4. **Analytics** — 12-card metrics grid (trades, win rate, gross P&L, drawdown, etc.)
5. **Settings** — CPU/RAM/Disk usage + service status indicators
6. **FTMO Manager** — Create/manage challenges, track progress against rules
7. **Script Editor** — Browse, edit, and deploy bot scripts from the browser
8. **AI Orchestrator** — View agent status + timeline + send commands to AI agents
9. **File Converter** — Drag-and-drop file conversion to Markdown

---

## 📡 API Reference

### Public Endpoints
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/bots` | List all bots + status |
| POST | `/api/bots/{name}/start` | Start a bot |
| POST | `/api/bots/{name}/stop` | Stop a bot |
| GET | `/api/bots/{name}/status` | Single bot status |
| GET | `/api/stats` | Aggregate statistics |
| GET | `/api/accounts` | List trading accounts |
| GET | `/api/positions` | Open positions |
| GET | `/api/backtest/strategies` | List available strategies |
| POST | `/api/backtest/run` | Run a backtest |
| GET | `/api/ftmo/challenges` | FTMO challenges |
| POST | `/api/ftmo/challenges` | Create challenge |
| GET | `/api/settings/system` | System resources |
| GET | `/api/orchestrator/agents` | AI agent status |
| POST | `/api/auth/dev-login` | Dev authentication |

### Bridge Endpoints (port 5000)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Bridge health |
| GET | `/api/v1/accounts` | All accounts |
| GET | `/api/v1/accounts/{id}` | Account info (balance, equity) |
| GET | `/api/v1/accounts/{id}/positions` | Open positions |
| GET | `/api/v1/accounts/{id}/history` | Closed trades |
| GET | `/api/v1/accounts/{id}/equity` | Equity curve |
| GET | `/api/v1/accounts/{id}/stats` | Account statistics |
| GET | `/api/v1/accounts/{id}/tick/{symbol}` | Real-time tick |

---

## 🚀 Deployment

### System Requirements
- **OS:** Windows 11 (runs on Hyper-V VM)
- **Python:** 3.12+
- **MetaTrader 5:** Installed with demo account
- **Cloudflare:** Domain + API token (Zone:DNS:Edit)

### Auto-Start on Boot
The system auto-starts via `AGENTX_Startup.bat` in Windows Startup folder:
1. MT5 Bridge (port 5000)
2. Backend + Bots (port 8003)
3. Cloudflare Tunnel (named tunnel)

### Startup Script (`start_agentx.bat`)
```batch
@echo off
cd /d C:\Trading
timeout /t 15 /nobreak >nul

REM Step 1: MT5 Bridge
start "MT5-Bridge" /MIN python.exe -m bridge --host 0.0.0.0 --port 5000

REM Step 2: Backend (auto-spawns bots)
start "AGENTX-Backend" /MIN python.exe -m uvicorn backend.app:app --host 0.0.0.0 --port 8003

REM Step 3: Cloudflare Tunnel
start "Cloudflare-Tunnel" /MIN cloudflared.exe tunnel run <TUNNEL_ID> --no-autoupdate
```

### Cloudflare Setup
- **Domain:** inventra.website
- **Nameservers:** `augustus.ns.cloudflare.com`, `sydney.ns.cloudflare.com`
- **DNS:** CNAME `@` + `www` → `tunnel-id.cfargotunnel.com` (proxied)
- **Tunnel:** Named tunnel via `cloudflared.exe`

---

## ⏰ Cron Jobs & Automation

All times in **HKT (UTC+8)**.

| Time | Job | Description |
|---|---|---|
| 07:00 AM | R&I Board Meeting | Research & Innovation daily meeting |
| 07:05 AM | SentimentPipeline | Collect sentiment data |
| 07:15 AM | Social Sentiment Scanner | Scan social media for market sentiment |
| 07:30 AM | Qwen Pre-Market Brief | Pre-market analysis and briefing |
| 08:00 AM | Division Reports | 7-division HermesJatti reports |
| 09:00 AM | CEO Daily Summary | Executive summary & approvals |
| 06:00 AM | Gold Phoenix Daily Report | Strategy iteration report |
| 06:00 AM | Resource Discovery | Research new tools/resources |
| 17:30 PM | Qwen Strategy Deep Dive | Post-close strategy analysis |
| Every 1m | Trade Watchdog | Monitor bot trades |
| Every 2m | AGENTX Watchdog | System health check |
| Every 15m | Bot Anomaly Scanner | Detect bot anomalies |
| Every 30m | Memory Sync | Backup to OneDrive |
| Every hour | GitHub Auto-Sync | Push changes to GitHub |
| Every hour | Sentiment Refresh | Refresh sentiment data |

---

## 🔬 Research & Innovation

### Sentiment Pipeline (`research/sentiment_engine.py`)
- **3 Data Sources:**
  1. Google News RSS (XAUUSD headlines)
  2. Polymarket API (prediction markets)
  3. MT5 Trend Analysis (price action structure)
- **Output:** Composite score (-10 to +10)
- **Integration:** Imported by Gold Phoenix Bot for signal validation

### AI Agents (`agents/`)
- **Orchestrator:** Coordinates 7 divisions
- **MarketSentimentAgent:** Analyzes news sentiment
- **Division Agents:** One per HermesJatti department

### Research Outputs (`research/`)
- Daily board meeting minutes
- Sentiment briefs
- Division reports
- Social sentiment analysis
- Strategy deep dives

---

## 🛠 Setup Guide

### Prerequisites
```bash
# Install Python 3.12+
# Install MetaTrader 5
# Install cloudflared
pip install -r requirements.txt
```

### Local Development
```bash
# Start the bridge
python -m bridge --host 0.0.0.0 --port 5000

# Start the backend
uvicorn backend.app:app --host 0.0.0.0 --port 8003

# Access the dashboard
open http://localhost:8003
```

### Cloudflare Tunnel (Production)
```bash
# Login to Cloudflare
cloudflared tunnel login

# Create a named tunnel
cloudflared tunnel create <name>

# Configure DNS
cloudflared tunnel route dns <tunnel-id> <domain>

# Run the tunnel
cloudflared tunnel run <tunnel-id>
```

### Authentication
- **Dev Login:** POST `/api/auth/dev-login` (email-based, bypass)
- **Access Codes:** Generate 5 testers via `/api/auth/codes/generate`
- **Google OAuth:** Configure via environment variables

---

## 🗺 Future Roadmap

### 🔜 Short-term
- [ ] **Knowledge Graph** — Map relationships between market events, strategies, and outcomes
- [ ] **Firecrawl Integration** — Deep website crawling for alternative data sources
- [ ] **NotebookLM Connection** — AI-powered research notebooks for strategy development
- [ ] **Multi-MT5 Launcher** — Deploy same strategy across multiple FTMO accounts simultaneously

### 📅 Medium-term
- [ ] **Secondary Gmail Integration** — Email-to-trade signals, automated report delivery
- [ ] **Moodle Connection** — Sync learning materials, trading courses
- [ ] **Notion API** — Bi-directional sync for knowledge base, meeting notes, strategy docs
- [ ] **Real-time Trade Export** — CSV/JSON/API for external analytics
- [ ] **Risk Engine** — Dynamic position sizing based on account equity and volatility
- [ ] **Prop Firm Dashboard** — Track all challenges across FTMO, MFF, The Funded Trader

### 🏆 Long-term (12-month goal: $1M)
- [ ] **Phase 1:** Pass FTMO $100k Challenge
- [ ] **Phase 2:** Scale to multiple funded accounts ($200k+ each)
- [ ] **Phase 3:** Compound profits across accounts
- [ ] **Phase 4:** Institutional-grade risk management
- [ ] **Phase 5:** Automated challenge entry + progression

---

## 📁 Project Structure

```
C:\Trading\
├── agents/              # AI Orchestrator & Agents
│   ├── orchestrator.py
│   └── sentiment_agent.py
├── backend/             # FastAPI Backend Server
│   ├── app.py           # Main application (routes, bot manager)
│   ├── auth.py          # Authentication system
│   ├── bridge_client.py # MT5 Bridge client
│   └── ftmo_manager.py  # FTMO challenge tracking
├── backtester/          # Backtesting Engine
│   ├── engine.py        # Core backtesting logic
│   ├── data.py          # Data fetching & symbol config
│   ├── loader.py        # Dynamic strategy loader
│   ├── strategies/      # Built-in strategies
│   └── custom_strategies/ # Custom user strategies
├── bots/                # Trading Bots (4 agents)
│   ├── gold_phoenix_bot.py
│   ├── gold_bot_v3.py
│   ├── scalping_youtube_goldstrategy.py
│   ├── streaming_bot_v3.py
│   └── session_filters.py
├── bridge/              # MT5 Bridge Server
│   ├── server.py        # FastAPI server for MT5
│   ├── mt5_manager.py   # MT5 connection manager
│   └── config.py        # Bridge configuration
├── frontend/            # SPA Dashboard
│   └── public/
│       └── index.html   # Single-file dashboard (162KB)
├── research/            # R&I Outputs & Tools
│   ├── sentiment_engine.py
│   ├── sentiment_pipeline.py
│   └── markitdown_bridge.py
├── scripts/             # Utility scripts
├── logs/                # Application logs
├── config/              # Configuration files
├── utils/               # Helper utilities
├── start_agentx.bat     # Startup script (C:\Trading\)
├── AGENTX_Startup.bat   # Startup shortcut (Windows Startup)
└── requirements.txt     # Python dependencies
```

---

## 🔐 Security

- **Authentication:** Session-cookie based with configurable expiry
- **Access Control:** 5-tester access code system with one-time claims
- **Google OAuth:** Optional for admin access
- **HTTPS:** Cloudflare proxied (once DNS fully propagates)
- **Network:** Isolated on Hyper-V internal network, exposed only via Cloudflare Tunnel

---

## 📞 Support & Deployment

| Contact | Details |
|---|---|
| **Developer** | Whala Sahib Singh |
| **Domain** | inventra.website |
| **GitHub** | [WHALASAHIB/AgentX](https://github.com/WHALASAHIB/AgentX) |
| **Dashboard** | https://inventra.website |
| **Local** | http://10.10.10.100:8003 |

---

## 📜 License

Proprietary — Internal trading system. Not for redistribution.

---

*"Automated trading, powered by AI. Scaling to $1M, one FTMO challenge at a time."*
