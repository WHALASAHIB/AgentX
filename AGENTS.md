# AGENTX v3 — AI-Powered Trading System

**Entry point for AI agents, automated workflows, and human operators.**

AGENTX v3 is a production trading system running on Windows 11 that manages automated forex/commodity bots across 9 currency pairs via MetaTrader 5. It features a FastAPI backend, real-time bridge to MT5, a 5-phase Research & Innovation Division, a single-page dashboard frontend, and a full DevOps/SRE pipeline.

## DevOps / MLOps Pipeline

| Component | Location | Purpose |
|-----------|----------|---------|
| SRE Engine | `devops/sre.py` | Self-healing: resource limits, health checks, process governance |
| Deploy Pipeline | `devops/deploy.py` | CI/CD: git pull → validate → backup → deploy → verify |
| CI Workflow | `.github/workflows/ci.yml` | GitHub Actions: validates all .py on push |
| Rules Config | `devops/rules.yaml` | Resource caps (8 max bots, 500MB min free RAM) |
| Makefile Targets | `Makefile` | `make sre`, `make deploy`, `make validate`, `make rollback` |

### Resource Governance
- **MAX 8 bot processes** — prevents memory exhaustion
- **Staggered launches** — 3s gap prevents MT5 IPC congestion  
- **IPC recovery** — auto restart MT5 session on `symbol_select` failure
- **Circuit breaker** — auto-pause after 3 consecutive losses

### Cron Jobs (Consolidated — was 29, now 17)
| Schedule | Job | Purpose |
|----------|-----|---------|
| `*/3 min` | SRE Engine | System health + resource governance |
| `*/5 min` | Notion Auto-Push | Trade journal |
| `30 min` | HermesMemorySync | Cloud backup |
| `Hourly` | SentimentRefresh | Update sentiment cache |
| `Hourly` | GitHub Auto-Sync | Version control |
| `4 hours` | Research Division | Analytics cycle |
| `6:00` | Gold Phoenix Report | Strategy iteration |
| `7:05` | SentimentPipeline | Social sentiment |
| `7:00` | Daily Algo Intelligence | CEO morning briefing |
| `Monday 9:00` | Weekly CEO Report | Weekly summary |

## DevSecOps — Credential Security
- **Manager:** `devops/credentials.py` — Windows Credential Manager + encrypted file
- **Audit:** Every credential access is logged to `bots/logs/credential_audit.log`
- **SRE integration:** SRE engine checks for plaintext .env files every cycle
- **GitGuard:** All `.env.*`, `*.key`, `*_token.txt` now gitignored
- **Usage:** `make sec-check | sec-migrate | sec-audit | sec-list`

## AgentOps — Agent Observability
- **Logger:** `devops/agentops.py` — structured JSONL logging for all agent decisions
- **Decisions:** `bots/logs/agent_decisions.jsonl` — WHY each decision was made
- **Failures:** `bots/logs/agent_failures.jsonl` — categorized with stack traces
- **Costs:** `bots/logs/agent_metrics.jsonl` — LLM token cost tracking
- **Usage:** `make agent-decisions | agent-failures | agent-costs`

## AIOps — Anomaly Detection
- **Scanner:** `devops/aiops.py` — detects P&L velocity anomalies, bot silence, stale logs
- **Patterns:** z-score analysis of P&L, silence detection (>6h), error count monitoring
- **Usage:** `make aiops-scan`

## Rejected Paradigms (Honest Assessment)
| Paradigm | Verdict | Why |
|----------|---------|-----|
| **MLOps** | ❌ SKIP | We don't train ML models. Strategies are deterministic rules. A model registry/feature store would be useless overhead. |
| **Full AIOps** | ❌ SKIP | Datadog/Splunk is enterprise overkill. Our light anomaly detection in `aiops.py` is sufficient. |
| **LLMOps platform** | ✅ LITE | Cost tracking is in `agentops.py`. A full prompt management platform would cost more in maintenance than we spend on tokens (~$5/week). |

## Tech Stack

| Layer        | Technology                                                |
|--------------|-----------------------------------------------------------|
| Language     | Python 3.12.10                                            |
| Backend      | FastAPI (port 8005) + Uvicorn                             |
| MT5 Bridge   | Separate service on `10.10.10.1:5000` (host machine)      |
| Account      | Demo, account `5051185832` (~$92,700 balance)             |
| Database     | PostgreSQL (via psycopg2-binary) + Redis caching          |
| Frontend     | Vanilla JS + Chart.js CDN (SPA, ~2750 lines)              |
| Auth         | Google OAuth + access codes                               |
| Orchestrator | Hermes Agent cron (every 4h)                              |
| Notion       | Auto-push trade journal every 5 minutes                   |
| Domain       | `inventra.website` (Cloudflare tunnel, DNS propagating) |

## Directory Structure

```
C:\Trading\
├── backend/              FastAPI app (~2170 lines, port 8005)
│   ├── app.py           Main server, all API routes
│   ├── auth.py          Google OAuth + access code auth
│   ├── bridge_client.py MT5 Bridge HTTP client
│   ├── models.py        Pydantic models
│   ├── redis_client.py  Redis pub/sub client
│   └── db/              Database layer (pool, store, queries)
├── bots/                23 bot scripts + active_bots/
│   ├── logs/            Per-bot logs + state JSON files
│   ├── active_bots/     Multi-pair run scripts (per-pair dirs)
│   └── multi_symbol_bot.py  Template runner for multi-pair bots
├── frontend/public/     SPA dashboard (index.html, ~2750 lines)
├── research_division/   5-phase Research & Innovation engine
│   ├── run.py           Orchestrator entry point (--full cycle)
│   ├── analytics_engine.py  960-line KPI computation engine
│   ├── deployment_engine.py 1221-line deploy/rollback system
│   ├── sprint_manager.py    1334-line Scrum/agile PM engine
│   ├── reports/         JSON report outputs per cycle
│   └── state/           Sprint state, trade cache, analytics history
├── scripts/             Utility scripts (Notion push, fix tools, etc.)
├── graphify-out/        Code graph visualization output
├── AGENTS.md            ← YOU ARE HERE
├── PROGRESS.md          Live state tracking
├── Makefile             Task automation
├── .python-version      Python version pin
└── requirements.txt     Python dependencies
```

## Quick Start

```bash
cd /c/Trading

# Setup environment
make setup

# Check system health
make check

# Run backend (port 8005)
uvicorn backend.app:app --host 0.0.0.0 --port 8005 --reload

# Run research division full cycle
make research
```

## Command Reference

| Command | Action |
|---------|--------|
| `make check` | Run health check + report status |
| `make health` | Curl backend `/api/health` |
| `make status` | Show status of all 23 bots |
| `make setup` | Install Python deps, create required dirs |
| `make research` | Run research division full cycle |
| `make clean` | Remove `__pycache__`, logs, temp files |
| `python backend/app.py` | Start backend server (port 8005) |
| `curl http://localhost:8005/api/health` | Health check |
| `curl http://localhost:8005/api/bots` | List all bots |
| `curl http://localhost:8005/api/stats` | Consolidated trading stats |
| `python research_division/run.py --full` | Full research cycle |

## 🚨 HARD CONSTRAINTS

These rules are absolute. Violating them causes data loss or trading errors.

1. **NEVER delete trade data.** No `DROP TABLE`, `DELETE FROM trades`, or truncating position/trade history. Data is the system's permanent record.

2. **ALWAYS verify before deploy.** Run health checks and test any parameter change in research/backtesting before deploying to live bots. The deployment engine has canary+rollback — use it.

3. **NEVER stop all bots simultaneously.** Stop bots one at a time. Stopping all bots at once leaves open positions unmanaged, risking drawdown.

4. **NEVER modify running bot scripts directly.** Always stop a bot first, modify its script, then restart. Hot-patching can corrupt state files.

5. **ALWAYS keep the MT5 Bridge running.** The bridge (`10.10.10.1:5000`) is the single point of connection to MetaTrader 5. If it's down, no trading occurs. Restart it before the backend.

6. **NEVER commit secrets.** `.env.keys`, `.env.cloudflare`, `.bridge_key`, `.cf_token`, and `tunnel_token.txt` are all in `.gitignore`. Never add them to version control.

7. **ALWAYS check the system is healty before assuming it's broken.** Run `make check` first. The backend, bridge, database, and Redis all have health endpoints. Verify each layer before debugging.

## Related Documentation

- `docs/architecture.md` — System architecture, component relationships, data flow
- `docs/trading-bots.md` — Bot types, strategies, pairs, and lifecycle management
- `docs/research-division.md` — 5-phase research cycle, sprint management, deployment
- `docs/dashboard.md` — Frontend routes, API endpoints, real-time updates
- `docs/operations.md` — MT5 Bridge setup, Notion integration, Cloudflare tunnel

## Before Asking for Help

1. Run `make check` and verify all services respond
2. Check `PROGRESS.md` to see if your issue is a known blocker
3. Check the bot's log in `bots/logs/<PAIR>_<STRATEGY>.log`
4. Verify the MT5 Bridge is running (`curl http://10.10.10.1:5000/health`)
5. Verify Redis and PostgreSQL are reachable
6. Check the backend is running on port 8005
7. If it's a research issue, check `research_division/division.log`
8. If you changed code, check `graphify-out/GRAPH_REPORT.md` for structural issues

---

*AGENTX v3 — Last updated 2026-06-19*
