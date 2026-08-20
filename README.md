<div align="center">

# 📊 AgentX — Algorithmic Trading OS

**Full-stack algorithmic trading platform: research → strategy → backtest → live execution → monitoring.**

[![License](https://img.shields.io/badge/License-Proprietary-red.svg?style=flat-square)](#license)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?style=flat-square)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Uvicorn-009688.svg?style=flat-square)](https://fastapi.tiangolo.com)
[![MT5](https://img.shields.io/badge/MetaTrader%205-Connected-green.svg?style=flat-square)](#connected-accounts)
[![Status](https://img.shields.io/badge/Status-Live-brightgreen.svg?style=flat-square)](https://inventra.website)
[![Platform](https://img.shields.io/badge/Platform-Windows%20VM-0078D6.svg?style=flat-square)](#deployment)

**🟢 Live:** [`inventra.website`](https://inventra.website) · **🔌 Local:** `http://localhost:8005` · **⚙️ Bridge:** `127.0.0.1:5000`

*Part of Project PropMillion — $1M in 12 months via algorithmic trading.*

</div>

---

## 🎯 What Is AgentX?

AgentX is the **command center** for a professional algorithmic trading operation. It connects a live MetaTrader 5 fleet, an AI research division, a backtesting lab, and a real-time web dashboard into one closed loop:

```
AI Research → Strategy Code → Backtest → Paper/Live Execution → Monitoring → (loop)
```

**This repo contains the full stack**: FastAPI backend + SPA dashboard, MT5 bridge integration, multi-account management, FTMO challenge tracking, and the AI orchestrator surface.

---

## ✨ Feature Highlights

| # | Feature | What It Does |
|:-:|---------|--------------|
| 1 | 📊 **Command Center** | Real-time trading overview, KPI cards, equity chart, daily change % |
| 2 | 💼 **Portfolio** | Account positions, strategy allocation, risk metrics |
| 3 | 📓 **Trade Journal** | Full trade history with smart filters + export |
| 4 | 🧪 **Backtesting Lab** | Strategy validation, Monte Carlo, Walk-Forward analysis |
| 5 | 🤖 **Bot Control** | Start / stop / monitor / edit trading bots |
| 6 | 📝 **Script Editor** | Monaco editor with one-click deploy flow |
| 7 | 🧠 **AI Orchestrator** | Multi-agent status and command surface |
| 8 | 🏦 **Account Manager** | Multi-account switching (`mt5-demo`, `ftmo-10k`, `ftmo-100k`) |
| 9 | 🏆 **FTMO Challenge** | Challenge progress, drawdown tracking, compliance |
| 10 | 📈 **Analytics** | Strategy comparison, deep risk analysis |
| 11 | ⚙️ **Settings** | Configuration, integrations, security |
| 12 | 📄 **File Converter** | PDF/DOCX/XLSX → Markdown |

Each page dynamically resolves the active account — switching accounts updates **all** pages automatically.

---

## 🏗️ Architecture

```
Browser ──► Cloudflare ──► Tunnel ──► FastAPI (:8005)
                                          │
                                    ┌─────┴─────┐
                                  SQLite      JSON Store
                                    │
                              MT5 Bridge (:5000)
                                    │
                              MetaTrader 5
                                    │
                          mt5-demo | ftmo-10k | ftmo-100k
```

| Component | Port | Tech | Status |
|-----------|------|------|--------|
| **Backend** | `0.0.0.0:8005` | FastAPI + Uvicorn | ✅ Active |
| **HTTPS (self-signed)** | `0.0.0.0:8443` | FastAPI + SSL | ✅ Active |
| **MT5 Bridge** | `127.0.0.1:5000` | FastAPI subprocess | ✅ Connected |
| **Cloudflare Tunnel** | → `localhost:8005` | cloudflared | ✅ Running |
| **Domain** | `inventra.website` | Cloudflare proxied + Flexible SSL | ✅ Online |

### Connected Accounts

| ID | Login | Server | Balance |
|----|-------|--------|---------|
| `mt5-demo` | 5051185832 | MetaQuotes-Demo | ~$97K |
| `ftmo-10k` | 1513767391 | FTMO-Demo | $9,076 |
| `ftmo-100k` | 1513845007 | FTMO-Demo | $100,000 |

> Bridge runs in **single-account mode** — only refreshes the active account to avoid hangs. Switch via the website's account switcher (restarts the MT5 terminal with chosen credentials).

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- MT5 Bridge running on port 5000
- Cloudflared tunnel (for public access)

### Local Dev
```bash
git clone git@github.com:WHALASAHIB/AgentX.git
cd AgentX
pip install -r requirements.txt
python -m backend --host 0.0.0.0 --port 8005
# Open → http://localhost:8005
```

### Production (via Cloudflare Tunnel)
```bash
# Backend
python -m backend --host 0.0.0.0 --port 8005

# Tunnel (separate terminal)
cloudflared.exe tunnel run da2cf48b
```

---

## 🛡️ API (75+ REST endpoints + SSE + WebSocket)

| Category | Base Path | Key Endpoints |
|----------|-----------|---------------|
| **Health** | `/api/health` | System health + bridge status |
| **Auth** | `/api/auth/*` | signin, signup, logout, OAuth me |
| **Accounts** | `/api/accounts` | Multi-account list, active account |
| **Stats** | `/api/stats` | Trading statistics |
| **Positions** | `/api/positions` | Open positions |
| **Trades** | `/api/trades` | Trade history, filtering, tagging |
| **Bots** | `/api/bots` | Bot CRUD, start/stop |
| **Backtest** | `/api/backtest/*` | Run, optimize, compare, Monte Carlo |
| **FTMO** | `/api/ftmo/*` | Challenge tracking, compliance |
| **Analytics** | `/api/analytics/*` | Strategy comparison, risk metrics |
| **Editor** | `/api/editor/*` | Script editing, deploy |
| **Settings** | `/api/settings` | System configuration |
| **Events (SSE)** | `/api/events` | Real-time streaming |
| **WebSocket** | `/api/ws/{path}` | Proxy → MT5 Bridge |

---

## 🔒 Security

- **Google OAuth 2.0** — primary auth
- **Access Codes** — secondary auth
- **JWT sessions** with Redis support
- **Dev-mode bypass** — auto sign-in as Commander (dev only)
- **Scanner blocker** — `.php`, `/wp-`, `/xmlrpc` requests → 404
- **No secrets in code** — all in `.env.*` (gitignored)

---

## 📂 Project Structure

```
AgentX/
├── backend/            # FastAPI app: app.py, auth.py, models.py, bridge_client.py
│   ├── db/             # SQLite databases
│   ├── ssl/            # Self-signed SSL certs
│   └── tests/          # Test suite
├── frontend/           # 12 pre-rendered SPA pages
├── bots/               # Bot strategy configs
├── backtester/         # Backtest engine + strategy library
├── edge_discovery/     # Edge-finding research pipeline
├── research_division/  # AI research agents
├── strategy_council/   # Strategy vetting/approval
├── knowledge/          # RAG knowledge base
├── devops/             # DevOps/SRE configs
├── agent-x-landing/    # Marketing/landing page
├── mcp_server.py       # MCP server for AI tool access
└── BASELINE.md         # Infrastructure immutable baseline
```

---

## 🔧 Deployment & Operations

| Service | Command |
|---------|---------|
| **Backend** | `python -m backend --host 0.0.0.0 --port 8005` |
| **HTTPS** | `python -m backend --host 0.0.0.0 --port 8443 --ssl-*` |
| **Tunnel** | `./cloudflared.exe tunnel run da2cf48b` |
| **Watchdog** | Cron checks bridge/backend/tunnel every 1h — silent unless broken |

### Auto-Sync
GitHub auto-sync runs via cron (every 2h) — local changes are committed and pushed automatically.

---

## 🗺️ Roadmap

- [x] MT5 multi-account bridge
- [x] FTMO challenge tracking
- [x] Backtesting lab (Monte Carlo, Walk-Forward)
- [x] AI orchestrator + MCP server
- [ ] Low-latency C++ execution engine
- [ ] Strategy factory v2 (defeated-Sharpe OOS validation)
- [ ] Portfolio risk aggregation across accounts

---

## 📚 Related

| Repo / System | What It Has |
|---------------|-------------|
| **Hermess (bridge)** | MT5 Bridge — single-account subprocess coordinator |
| **Backtester** | Strategy validation engine (Monte Carlo, Walk-Forward) |
| **Research Division** | AI research agents for edge discovery |

---

## ⚠️ Disclaimer

**Trading involves substantial risk.** This software is provided for educational and research purposes. Past performance does not guarantee future results. Use at your own risk — never trade with money you cannot afford to lose.

---

*AgentX — Algorithmic Trading Dashboard. Built for Project PropMillion.*

---

<!-- last-refreshed: 2026-08-20 -->

## 📡 Live Status

| Metric | Value |
|--------|-------|
| Stars | 0 |
| Forks | 0 |
| Commits | 330 |
| Last commit | `d30a67a docs: overhaul README — hero, badges, feature grid, architecture, roadmap` |
| Refreshed | 2026-08-20 (auto) |
