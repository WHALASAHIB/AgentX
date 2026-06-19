# AGENTX v3 — Progress & System State

> **Live state tracking file. Update this file when milestones complete, blockers clear, or issues surface.**

---

## Current Status

| Field | Value |
|-------|-------|
| **Sprint** | Sprint 3 — Platform Hardening & Stability |
| **Phase** | Post-audit remediation / infrastructure hardening |
| **Backend** | Running (port 8005) — v1.0.0 |
| **MT5 Bridge** | Running (10.10.10.1:5000) — Account 5051185832 |
| **Bots** | 23 total (4 legacy + 19 multi-pair) |
| **Balance** | ~$92,700 (demo) |
| **Research Division** | Cron: every 4h HKT (00,04,08,12,16,20) |
| **Notion Push** | Every 5 minutes (auto) |
| **Domain** | `inventra.website` — DNS propagating |
| **Last Updated** | 2026-06-19 |

---

## ✅ Completed Items

### CEO Audit Fixes — Dashboard (4 Critical)
- [x] Dashboard no longer shows empty tables for ongoing trades
- [x] Positions table renders correctly with proper column alignment
- [x] Equity chart displays historical data properly instead of blank canvas
- [x] Bot status panel shows accurate running/stopped states

### CEO Audit Fixes — Research Division (6 Critical)
- [x] analytics_engine.py: Fixed pair-level KPI computation (win_rate, profit_factor, net_profit)
- [x] analytics_engine.py: Fixed session analysis (Asian/London/US session breakdowns)
- [x] sprint_manager.py: Fixed backlog prioritization scoring (urgency multipliers applied correctly)
- [x] sprint_manager.py: Fixed blocker detection logic (no false positives on normal market conditions)
- [x] deployment_engine.py: Fixed safe_deploy canary/rollback flow (was skipping validation)
- [x] deployment_engine.py: Fixed bot restart after deployment (was not killing old process)

### New API Endpoints
- [x] `/api/research/report` — Returns latest research division report
- [x] `/api/research/insights` — Extracts actionable trading insights from reports
- [x] `/api/diagnostic` — Comprehensive bridge + backend diagnostics

### Infrastructure
- [x] Graphify code graph generated (2808 nodes, 5516 edges, 186 communities)
- [x] Makefile created with check/health/status/setup/research/clean targets
- [x] .python-version created (3.12.10)
- [x] requirements.txt updated with all critical dependencies
- [x] AGENTS.md entry point created for AI agents

---

## 🔄 In Progress

- [ ] DNS propagation for `inventra.website` (pointed to Cloudflare, tunnel ID `da2cf48b-5b1f-4e28-9b7c-8d7bce6ec1a6`)
- [ ] Creating `docs/` directory with architecture, trading-bots, research-division, dashboard, and operations documentation
- [ ] Audit active_bots/ directory to verify all 19 multi-pair run scripts exist
- [ ] Verify notion_autopush.py runs correctly (check notion_push_state.json)
- [ ] Create `.env.keys` and `.env.cloudflare` templates if missing

---

## 🚫 Blocked Items

| Issue | Impact | Workaround |
|-------|--------|------------|
| **DNS propagation** — `inventra.website` not yet resolving universally | External access via domain name not available | Use localhost:8005 or Cloudflare tunnel URL internally |
| **Phantom PID 1836** — `kill -9 1836` returns "No such process" but process list still shows it | Minor; no functional impact | Ignore; part of process scanning edge case. PID table stale after bot restart |
| **Old backend process can't restart** — `uvicorn` on port 8005 sometimes refuses restart after kill | Backend needs manual restart | Kill with `taskkill /PID <PID> /F` via Windows cmd, then restart from bash |

---

## 🐛 Known Issues

1. **Chart.js CDN dependency** — Frontend loads Chart.js from CDN. If the internet is down, the dashboard charts fail silently. Should bundle Chart.js locally.
2. **Old backend process can't restart** — After force-killing `uvicorn`, port 8005 remains claimed by a ghost process. Requires Windows `taskkill /F` on the actual PID.
3. **Phantom PID 1836** — Bot process scanner picks up a PID that `kill` can't reach. This is a race condition in `psutil` process enumeration on Windows. Non-critical.
4. **Gitignore excludes `research/`** — The directory `research/` (with scrum JSOns and daily reports) is gitignored. Missing from version control; backups needed.
5. **No docs/ directory yet** — Topic docs referenced in AGENTS.md don't exist. These need to be created.
6. **Graphify graph may be stale** — Last built from commit `2786c533`. Run `graphify update .` after significant code changes.
7. **Notion weekly report scripts** — Multiple fix scripts exist (`fix_weekly.py` through `fix_weekly_v5.py`) indicating fragility in the Notion weekly report pipeline.

---

## Bot Inventory (23 Total)

### Legacy Bots (4)
- `gold_bot` — Gold bot v3
- `gold_phoenix` — Gold Phoenix strategy
- `scalping_bot` — Scalping on gold/youtube strategy
- `streaming_bot` — Streaming bot v3

### Multi-Pair Bots (19)

**MACD Strategy** — 9 pairs
`MACD_AUDUSD`, `MACD_BTCUSD`, `MACD_EURUSD`, `MACD_GBPUSD`, `MACD_NZDUSD`, `MACD_USDCAD`, `MACD_USDCHF`, `MACD_USDJPY`, `MACD_XAUUSD`

**GoldPhoenix Strategy** — 5 pairs
`GoldPhoenix_BTCUSD`, `GoldPhoenix_EURUSD`, `GoldPhoenix_GBPUSD`, `GoldPhoenix_USDCAD`, `GoldPhoenix_XAUUSD`

**Bollinger Strategy** — 3 pairs
`Bollinger_AUDUSD`, `Bollinger_NZDUSD`, `Bollinger_USDCHF`

**SMA Strategy** — 2 pairs
`SMA_BTCUSD`, `SMA_USDJPY`

---

*Update this file as milestones complete or new issues surface.*
