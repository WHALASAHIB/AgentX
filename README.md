# 📊 AgentX — Algorithmic Trading Dashboard

> **Full-stack algorithmic trading web platform** — monitor, control, and analyze live trading bots in real-time across multiple MT5 accounts.
>
> 🟢 **Live:** [`inventra.website`](https://inventra.website) — powered by FastAPI + SPA frontend + Cloudflare Tunnel
> 🔌 **Local:** `http://localhost:8005`
> ⚙️ **Bridge:** `http://127.0.0.1:5000` (Hermess)

---

## 🎯 What This Is

AgentX is the **web cockpit** for a professional algorithmic trading system. This repo contains the FastAPI backend (serving a pre-rendered SPA dashboard) plus infrastructure config.

**The trading intelligence — bots, research, DevOps, AI agents — lives in the [Hermess](https://github.com/WHALASAHIB/Hermess.git) repo.**

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- MT5 Bridge running on port 5000 (see [Hermess](https://github.com/WHALASAHIB/Hermess.git))
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

## 🏗️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, Uvicorn |
| **Frontend** | Vanilla JS SPA, Chart.js, CSS3 |
| **Database** | JSON file store + SQLite |
| **Auth** | Google OAuth 2.0 + Dev-mode bypass + Access Codes |
| **Infrastructure** | Cloudflare Tunnel (da2cf48b), Cloudflare SSL (Flexible) |
| **Bridge** | MT5 Bridge (Hermess) — single-account subprocess coordinator |

---

## 📐 Dashboard — 12 Sections

| # | Section | Purpose |
|:-:|---------|---------|
| 1 | 📊 **Command Center** | Real-time trading overview, KPI cards, equity chart, daily change % |
| 2 | 💼 **Portfolio** | Account positions, strategy allocation, risk metrics |
| 3 | 📓 **Trade Journal** | Complete trade history with smart filters, export |
| 4 | 🧪 **Backtesting Lab** | Strategy validation, Monte Carlo, Walk-Forward |
| 5 | 🤖 **Bot Control** | Start/stop/monitor/edit trading bots |
| 6 | 📝 **Script Editor** | Monaco editor with deploy flow |
| 7 | 🧠 **AI Orchestrator** | Multi-agent status and commands |
| 8 | 🏦 **Account Manager** | Multi-account switching (mt5-demo, ftmo-10k, ftmo-100k) |
| 9 | 🏆 **FTMO Challenge** | Challenge progress, DD tracking, compliance |
| 10 | 📈 **Analytics** | Deep metrics, strategy comparison, risk analysis |
| 11 | ⚙️ **Settings** | Configuration, integrations, security |
| 12 | 📄 **File Converter** | PDF/DOCX/XLSX → Markdown |

Each page dynamically resolves the active account — switching accounts updates **all** pages automatically.

---

## 🌐 Infrastructure

```
Browser ──► Cloudflare ──► Tunnel ──► FastAPI (:8005)
                                          │
                                    ┌─────┴─────┐
                                    │           │
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
| **MT5 Bridge** | `127.0.0.1:5000` | FastAPI Subprocess | ✅ Connected |
| **Cloudflare Tunnel** | → `localhost:8005` | cloudflared da2cf48b | ✅ Running |
| **Domain** | `inventra.website` | Cloudflare proxied + Flexible SSL | ✅ Online |

### Connected Accounts

| ID | Login | Server | Balance |
|----|-------|--------|---------|
| `mt5-demo` | 5051185832 | MetaQuotes-Demo | ~$97,107 |
| `ftmo-10k` | 1513767391 | FTMO-Demo | $9,076 |
| `ftmo-100k` | 1513845007 | FTMO-Demo | $100,000 |

Bridge runs in **single-account mode** — only refreshes the active account to avoid hangs. Switch via the website's Switch button (restarts MT5 terminal with chosen credentials).

---

## 🛡️ API Endpoints

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

**75+ REST endpoints** + SSE real-time streaming + WebSocket proxy.

---

## 🔒 Security

- **Google OAuth 2.0** (primary auth)
- **Access Codes** (secondary auth)
- **JWT sessions** with Redis support
- **Dev-mode bypass** (auto signin as Commander)
- **Scanner blocker** — blocks `.php`, `/wp-`, `/xmlrpc` requests with 404
- **No secrets in code** — all in `.env.*` (gitignored)
- **CORS** — open for dev (`allow_origins=["*"]`), restrict for production

---

## 📂 Project Structure

```
AgentX/
├── backend/
│   ├── app.py            # Main FastAPI application (141KB)
│   ├── auth.py           # Auth handlers (OAuth, dev-mode)
│   ├── models.py         # Pydantic models
│   ├── bridge_client.py  # Bridge API client
│   ├── ftmo_manager.py   # FTMO challenge logic
│   ├── redis_client.py   # Redis caching layer
│   ├── db/               # SQLite databases
│   ├── ssl/              # Self-signed SSL certs
│   └── tests/            # Test suite
├── frontend/
│   └── public/           # 12 pre-rendered SPA pages
├── bots/                 # Bot strategy configs
├── devops/               # DevOps/SRE configs
├── strategy-engine/      # Pine Script strategy engine
└── BASELINE.md           # Infrastructure immutable baseline
```

---

## 🔧 Deployment

### Current Setup (Windows VM)
| Service | Command |
|---------|---------|
| **Backend** | `python -m backend --host 0.0.0.0 --port 8005` |
| **HTTPS** | `python -m backend --host 0.0.0.0 --port 8443` (with --ssl-*) |
| **Tunnel** | `./cloudflared.exe tunnel run da2cf48b` |
| **Watchdog** | Cron job checks bridge/backend/tunnel every 1h — silent unless broken |

### Auto-Sync
GitHub auto-sync runs every hour via cron (`auto-sync: HH:00 UTC`).

---

## 📚 Related

| Repo | What It Has |
|------|-------------|
| **[Hermess](https://github.com/WHALASAHIB/Hermess.git)** | Bot strategies, AI agents, research pipeline, DevOps/SRE, RAG knowledge base, MT5 Bridge, config |

---

*AgentX v3 — Trading Dashboard. Part of Project PropMillion: $1M in 12 months via algorithmic trading.*
