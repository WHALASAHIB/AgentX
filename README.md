# 📊 AgentX — Algorithmic Trading Dashboard

> **Full-stack algorithmic trading web platform** — monitor, control, and analyze your trading bots in real-time.
> The website interface for the [Hermess](https://github.com/WHALASAHIB/Hermess.git) trading intelligence system.

---

## 🎯 What This Is

AgentX is the **web cockpit** for a professional algorithmic trading system. This repo contains ONLY the website — the FastAPI backend that serves the dashboard and the SPA frontend that renders it.

**Live at:** `inventra.website` (via Cloudflare tunnel)
**Temporary:** `https://leader-sega-mit-ottawa.trycloudflare.com`
**Local:** `http://localhost:8005`

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, Uvicorn |
| **Frontend** | Vanilla JS SPA, Chart.js, CSS3 |
| **Database** | SQLite (with connection pooling) |
| **Auth** | Google OAuth 2.0 + Access Codes |
| **Infrastructure** | Cloudflare Tunnel, Docker (optional) |

---

## 📐 Dashboard — 12 Sections

| # | Section | Purpose |
|:-:|---------|---------|
| 1 | 📊 **Command Center** | Real-time trading overview, KPI cards, equity chart |
| 2 | 💼 **Portfolio** | Account positions, strategy allocation, risk metrics |
| 3 | 📓 **Trade Journal** | Complete trade history with smart filters, export |
| 4 | 🧪 **Backtesting Lab** | Strategy validation, Monte Carlo, Walk-Forward |
| 5 | 🤖 **Bot Control** | Start/stop/monitor/edit trading bots |
| 6 | 📝 **Script Editor** | Monaco editor with deploy flow |
| 7 | 🧠 **AI Orchestrator** | Multi-agent status and commands |
| 8 | 🏦 **Account Manager** | Multi-account, zero tolerance for disconnections |
| 9 | 🏆 **FTMO Challenge** | Challenge progress, DD tracking, compliance |
| 10 | 📈 **Analytics** | Deep metrics, strategy comparison, risk analysis |
| 11 | ⚙️ **Settings** | Configuration, integrations, security |
| 12 | 📄 **File Converter** | PDF/DOCX/XLSX → Markdown |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- MT5 Bridge running on port 5000 (see Hermess repo)
- Redis (optional, for caching)

### Setup
```bash
# Clone
git clone git@github.com:WHALASAHIB/AgentX.git
cd AgentX

# Install dependencies
pip install -r requirements.txt

# Run backend
uvicorn backend.app:app --host 0.0.0.0 --port 8005

# Open in browser
open http://localhost:8005
```

### With Docker
```bash
docker build -t agentx-backend .
docker run -p 8005:8005 -v $(pwd)/backend/db:/app/backend/db agentx-backend
```

---

## 🛡️ API Endpoints

The backend serves 75+ REST endpoints plus SSE real-time streaming:

| Category | Base Path | Key Endpoints |
|----------|-----------|---------------|
| **Health** | `/api/health` | System health, bridge status |
| **Stats** | `/api/stats` | Trading statistics |
| **Positions** | `/api/positions` | Open positions |
| **Trades** | `/api/trades` | Trade history, filtering, tagging |
| **Bots** | `/api/bots` | Bot CRUD, start/stop |
| **Backtest** | `/api/backtest/*` | Run, optimize, compare, Monte Carlo |
| **Accounts** | `/api/accounts` | Multi-account management |
| **FTMO** | `/api/ftmo/*` | Challenge tracking, compliance |
| **Analytics** | `/api/analytics/*` | Strategy comparison, risk metrics |
| **Editor** | `/api/editor/*` | Script editing, deploy |
| **Settings** | `/api/settings` | System configuration |
| **Events (SSE)** | `/api/events` | Real-time streaming |

Full API docs: See `backend/app.py` or the Hermess docs.

---

## 🔗 Architecture

```
Browser ──► Cloudflare ──► FastAPI (:8005) ──► MT5 Bridge (:5000) ──► MetaTrader 5
                          │
                          ├── SQLite (trades, positions, accounts)
                          ├── Redis (cache, pub/sub)
                          └── Hermess (bots, research, SRE)
```

The website communicates with the trading system through the backend. All bot logic, research, and DevOps run in the [Hermess](https://github.com/WHALASAHIB/Hermess.git) repo.

---

## 🔧 Deployment

### Production (current)
- FastAPI backend runs on VM (`10.10.10.100:8005`)
- Cloudflare tunnel provides secure public access
- MT5 Bridge on host (`10.10.10.1:5000`)

### Docker Compose (recommended)
```yaml
services:
  backend:
    build: .
    ports: ["8005:8005"]
    volumes: ["./backend/db:/app/backend/db"]
    environment:
      - MT5_BRIDGE_URL=http://host.docker.internal:5000
```

### Kubernetes (future)
See `k8s/` directory for deployment manifests.

---

## 🔒 Security

- Google OAuth 2.0 (primary auth)
- Access Codes (secondary auth)
- JWT sessions with Redis
- No secrets in code (all in `.env.*` gitignored files)
- CORS restricted to known origins

---

## 📚 Related

| Repo | What It Has |
|------|-------------|
| **[Hermess](https://github.com/WHALASAHIB/Hermess.git)** | Bot strategies, research, DevOps, SRE, RAG pipeline, agents, config |

---

*AgentX v3 — Trading Dashboard. Part of Project PropMillion.*
