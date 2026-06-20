# 🏗️ AGENTX v3 — Complete System Reference

**Harness Engineering Framework Applied** — All features documented here.
Live tunnel: `https://leader-sega-mit-ottawa.trycloudflare.com`
Domain: `inventra.website` (DNS propagating at Namecheap)

---

## 📋 Complete Feature Index

| # | Feature | File | Status |
|---|---------|------|--------|
| 1 | **Backend API** (75+ endpoints) | `backend/app.py` | ✅ Live port 8005 |
| 2 | **Frontend Dashboard** (SPA) | `frontend/public/index.html` | ✅ Live |
| 3 | **Multi-Pair Trading Bots** (4 strategies × 9 pairs) | `bots/multi_symbol_bot.py` | ✅ 19 bots running |
| 4 | **AI Agent Orchestrator** (6 agents) | `agents/orchestrator.py` | ✅ Active |
| 5 | **Research Division** (5-phase cycle) | `research_division/run.py` | ✅ Cron every 4h |
| 6 | **Analytics Engine** (KPIs per pair) | `research_division/analytics_engine.py` | ✅ |
| 7 | **Sprint Manager** (Agile PM) | `research_division/sprint_manager.py` | ✅ |
| 8 | **Deployment Engine** (canary + rollback) | `research_division/deployment_engine.py` | ✅ |
| 9 | **SRE Engine** (self-healing) | `devops/sre.py` | ✅ Cron every 2min |
| 10 | **DevSecOps** (credential security) | `devops/credentials.py` | ✅ |
| 11 | **AgentOps** (decision/failure logging) | `devops/agentops.py` | ✅ |
| 12 | **AIOps** (anomaly detection) | `devops/aiops.py` | ✅ |
| 13 | **CI/CD Pipeline** (deploy/rollback) | `devops/deploy.py` | ✅ |
| 14 | **Notion Auto-Push** (trade journal) | `scripts/notion_autopush.py` | ✅ Every 5min |
| 15 | **Sentiment Engine** (Google News + Polymarket) | `research/sentiment_engine.py` | ✅ |
| 16 | **FTMO Challenge Manager** | `backend/app.py` (routes) | ✅ |
| 17 | **File Converter** (PDF/DOCX/XLSX → MD) | `backend/app.py` | ✅ |
| 18 | **Google OAuth** + Access Codes | `backend/auth.py` | ✅ |
| 19 | **SSE Real-time Streaming** | `backend/app.py` (`/api/events`) | ✅ |
| 20 | **Editor** (live file edit + deploy) | `backend/editor` | ✅ |
| 21 | **Backtesting Engine** (4 strategies) | `backend/backtest` | ✅ |
| 22 | **MT5 Bridge** (MetaTrader 5) | Bridge service port 5000 | ✅ Live |
| 23 | **Cloudflare Tunnel** (named) | `da2cf48b-5b1f-4e28-9b7c-8d7bce6ec1a6` | ✅ Running |
| 24 | **TryCloudflare Tunnel** (temporary) | `leader-sega-mit-ottawa.trycloudflare.com` | ✅ Active |
| 25 | **Telegram Alerts** | Hermes cron | ✅ |
| 26 | **Web Dashboard** (Hermes) | `hermes dashboard` (port 9119) | ✅ |

---

## 🚀 Quick Access

### Temporary Tunnel (Working Now)
```
https://leader-sega-mit-ottawa.trycloudflare.com
```

### Local
```
http://localhost:8005          # Backend + Dashboard
http://localhost:5000/health   # MT5 Bridge
http://127.0.0.1:9119          # Hermes Dashboard
```

### VM
```
http://10.10.10.100:8005       # Backend on VM
```

### Domain (DNS Propagating)
```
https://inventra.website        # ⏳ Nameserver propagation at Namecheap
```

---

## 🚨 8 Hard Constraints

1. **NEVER delete trade data** — No DROP TABLE, DELETE FROM trades, or truncating history
2. **ALWAYS verify before deploy** — Run `make check` then `make e2e` before declaring done
3. **NEVER start with modifications** — Run `make init` first
4. **NEVER stop all bots simultaneously** — Stop one at a time
5. **NEVER modify running bot scripts** — Stop first, modify, then restart
6. **ALWAYS keep MT5 Bridge running** — Restart bridge before backend
7. **NEVER commit secrets** — `.env.*`, `*.key`, `tunnel_token.txt` are gitignored
8. **NEVER modify without authorization:** `devops/rules.yaml`, `devops/credentials.py`

---

## 🔧 Using the System

### Bot Management
```bash
curl http://localhost:8005/api/bots                          # List all bots
curl http://localhost:8005/api/bots/GBPUSD_MACD/start        # Start a bot
curl http://localhost:8005/api/bots/GBPUSD_MACD/stop         # Stop a bot
curl http://localhost:8005/api/stats                          # Trading stats
```

### Trading Dashboard
Open `http://localhost:8005/` in a browser. Features:
- 📊 Real-time ticker (XAUUSD, EURUSD, GBPUSD, USDJPY)
- 📈 Equity curve chart
- 📋 Open positions table
- 🤖 Bot status panel
- 📉 Trade history

### Backtesting
```bash
curl http://localhost:8005/api/backtest/run -X POST \
  -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","strategy":"macd","days":90}'
```

### Research Division
```bash
make research         # Full 5-phase cycle
curl http://localhost:8005/api/research/report       # Latest report
curl http://localhost:8005/api/research/insights     # Per-pair insights
```

---

## 🤖 Bot Strategies (10 Total)

| Strategy | Pairs | Risk % | Type |
|----------|-------|--------|------|
| **MACD** | AUDUSD, GBPUSD, NZDUSD, USDCHF, USDCAD, USDJPY, BTCUSD | 0.15% | Core |
| **GoldPhoenix** | XAUUSD, BTCUSD, EURUSD, GBPUSD, USDCAD | 0.15% | Core |
| **Bollinger** | AUDUSD, NZDUSD, USDCHF | 0.15% | Core |
| **SMA** | USDJPY, BTCUSD | 0.15% | Core |
| Gold v3 MTF | XAUUSD | Legacy | Legacy |
| Scalp v3 | XAUUSD | Legacy | Legacy |
| M1 Stream | XAUUSD | Legacy | Legacy |
| SRB v2 XAU | XAUUSD | Legacy | Legacy |
| SRB XAU | XAUUSD | Legacy | Legacy |
| Scalping Hybrid | XAUUSD | Legacy | Legacy |

**19 bots active** (4 disabled by council: Streaming Bot, MACD EURUSD, MACD XAUUSD, GoldBot)

---

## 🔐 Security Layers

| Layer | Technology | Details |
|-------|-----------|---------|
| **Auth** | Google OAuth 2.0 | OpenID + email profile |
| **Sessions** | HTTP-only cookies | 7-day expiry, SameSite=lax |
| **Access Codes** | 16-char hex | Time-limited, 5 testers |
| **Credentials** | Windows Credential Manager | OS-level encryption |
| **Fallback** | AES-GCM encrypted file | Machine-derived key |
| **Audit** | Full access log | Every read/write timestamped |
| **CI Check** | GitHub secret scanning | Push protection |

---

## 📊 Observability

```bash
make agent-decisions     # Recent agent decisions
make agent-failures      # Failure statistics by category
make agent-costs         # LLM token costs
make aiops-scan          # Anomaly detection scan
make sec-check           # Security posture check
```

---

## 🐛 Known Issues

1. **SRE bot detection** — Grep pattern looks for "multi_symbol_bot" but actual processes use "run_macd", "run_goldphoenix" etc. False 0/8 count.
2. **No trades on weekends** — Bots are flat (normal, market closed)
3. **DNS not propagated** — Namecheap nameservers still resolving
4. **Notion autopush log missing** — Log file path mismatch

---

## 🔑 Makefile Reference

```bash
make init        # [HARNESS] Read harness, check env, create plan
make check       # System health (backend, bridge, bots)
make e2e         # [HARNESS] Full verification suite
make health      # Fast API ping
make status      # Bot status table
make setup       # Install deps + create dirs
make research    # Full research cycle
make validate    # Python syntax check
make sre         # SRE engine health
make deploy      # CI/CD deploy
make rollback    # Rollback last deploy
make sec-check   # Security scan
make aiops-scan  # Anomaly detection
make clean       # Remove temp files
```

---

*AGENTX v3 — Last updated 2026-06-20 | Sprint 4: Harness Engineering*
