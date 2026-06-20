# AGENTX v3 — AI-Powered Trading System

**Entry point for AI agents, automated workflows, and human operators.**

AGENTX v3 is a production trading system on Windows 11 that manages automated forex/commodity bots via MetaTrader 5. Features a FastAPI backend, MT5 bridge, Research Division, Notion journaling, and a full DevOps/SRE pipeline.

> 📖 **FRESH SESSION PROTOCOL — Read this before modifying anything.**
> This file is a **router**, not an encyclopedia. Topic docs in `docs/` have full detail.

---

## 🚨 HARD CONSTRAINTS (Absolute Rules)

1. **NEVER delete trade data.** No `DROP TABLE`, `DELETE FROM trades`, or truncating position/trade history.
2. **ALWAYS verify before deploy.** Run `make check` then `make e2e` before declaring any task done.
3. **NEVER start with modifications.** Run `make init` first — read AGENTS.md, PROGRESS.md, and docs/ before touching code.
4. **NEVER stop all bots simultaneously.** Stop bots one at a time. Unmanaged open positions cause drawdown.
5. **NEVER modify running bot scripts.** Stop the bot, modify, then restart. Hot-patching corrupts state files.
6. **ALWAYS keep MT5 Bridge running.** Bridge (`10.10.10.1:5000`) is the single point of connection to MT5. Restart it before the backend.
7. **NEVER commit secrets.** `.env.*`, `*.key`, `tunnel_token.txt` are gitignored. Use `make sec-migrate` for proper storage.
8. **NEVER modify these files without authorization:** `devops/rules.yaml`, `devops/credentials.py`, `.env.secure`.

---

## 🔧 INITIALIZATION PHASE (Must Do Before Any Work)

Before making ANY changes, run this sequence:

```
make init      # Reads harness files, checks env, reports state
```

`make init` does: reads AGENTS.md → reads PROGRESS.md → checks env readiness → reads relevant `docs/*.md` → creates a plan → outputs plan to session. Do NOT skip this step.

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12.10 |
| Backend | FastAPI (port 8005) + Uvicorn |
| MT5 Bridge | Service on `10.10.10.1:5000` |
| Account | Demo `5051185832` (~$96,685.85 balance) |
| Database | PostgreSQL + Redis caching |
| Frontend | Vanilla JS + Chart.js (SPA dashboard) |
| Orchestrator | Hermes Agent cron |
| Domain | `inventra.website` (Cloudflare tunnel) |

---

## 📂 Directory Structure

```
C:\Trading\
├── AGENTS.md           ← YOU ARE HERE (router file)
├── ARCHITECTURE.md     ← System architecture (must read before architecture work)
├── PROGRESS.md         ← Live state tracking
├── Makefile            ← Task automation
├── backend/            FastAPI app (port 8005)
├── bots/               Trading bot scripts + logs/
├── devops/             SRE Engine, CI/CD, security, observability
├── docs/               Topic documentation
├── frontend/           SPA dashboard
├── research_division/  5-phase Research & Innovation engine
├── scripts/            Utility scripts
└── graphify-out/       Code graph visualization
```

---

## ⚡ Quick Start

```bash
cd /c/Trading
make init          # Read harness, check env, create plan
make setup         # Install deps
make check         # System health
make e2e           # Full verification suite
```

---

## 📖 Documentation (Read on Demand)

| File | Read When... |
|------|-------------|
| `docs/architecture.md` | Understanding system architecture, data flow, port mapping |
| `docs/trading-bots.md` | Working with bot strategies, pairs, lifecycle |
| `docs/research-division.md` | Using the 5-phase research cycle |
| `docs/dashboard.md` | Frontend routes, API endpoints |
| `docs/operations.md` | MT5 Bridge, Notion, Cloudflare tunnel setup |
| `FEATURES_TEMPLATE.md` | Creating structured feature specs for any task |
| `devops/rules.yaml` | Resource governance caps (MAX 8 bots, 500MB min free RAM) |

---

## 🎯 Scope Boundaries

**DO NOT TOUCH without explicit authorization:**
- `devops/rules.yaml` — resource caps (changing this affects SRE governance)
- `devops/credentials.py` — credential management system
- `.env.secure` — encrypted credentials
- Any `.env.*` or `*_token.txt` file — secrets
- Running bot PIDs — stop properly via backend API

**WHAT TO TOUCH (in scope):**
- Bot strategy parameters in `bots/active_bots/`
- `backend/` — API routes, models, bridge client
- `research_division/` — analytics, sprint, deployment engines
- `docs/` — documentation (always keep in sync)

---

## ✅ VERIFICATION GATING

**You are NOT done until ALL checks pass:**

```bash
make check        # System health (backend, bridge, bots)
make validate     # Python syntax validation
make e2e          # Full verification suite
```

The agent's opinion on whether a task is done is worthless. **Only passing verification matters.**

---

## 🧹 CLEAN STATE PROTOCOL (End of Session)

Before finishing ANY session, run:

1. **Commit** all intentional changes with descriptive messages
2. **Revert/stash** any unintentional changes
3. **Kill** any processes started during the session
4. **Clean** temporary files (`make clean`)
5. **Check** system still works (`make check`)
6. **Update** PROGRESS.md with session summary
7. **Verify** git status is clean (`git status`)
8. **Document** any known issues or manual steps needed

> ⚠️ A session that doesn't leave a clean state is stealing context from the next session.

---

## 🔍 Before Asking for Help

1. Run `make check` — verify all services respond
2. Check `PROGRESS.md` — is your issue a known blocker?
3. Check bot logs in `bots/logs/<PAIR>_<STRATEGY>.log`
4. Verify MT5 Bridge: `curl http://10.10.10.1:5000/health`
5. Verify backend: `curl http://localhost:8005/api/health`

---

*AGENTX v3 — Harness Engineering Course Applied. Last updated 2026-06-20.*
