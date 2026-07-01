# AgentX Trading Knowledge Base

> **Open Knowledge Format (OKF) bundle** for the AgentX algorithmic trading system.
> Bundle config: `okf.yaml`

## What's Here

```
knowledge/
├── okf.yaml                        # OKF bundle manifest
├── LLM_CONTEXT.md                  # AI assistant context (quick-start)
├── README.md                       # This file — human overview
├── concepts/
│   ├── infrastructure.md           # System architecture, networking, ports
│   └── ftmo-rules.md               # FTMO challenge rules & compliance
├── strategies/
│   └── active-bots-overview.md     # All 15 bots: pairs, strategies, status
├── bots/
│   └── deployment-runbook.md       # How bots are deployed (auto-start lifecycle)
├── decisions/
│   └── decision-log-summary.md     # Key decisions from structured log
└── api/
    └── backend-endpoints.md        # Complete REST API reference
```

## Quick Links

| What | Link |
|------|------|
| Live dashboard | https://inventra.website |
| Backend health | http://localhost:8005/api/health |
| Bridge status | http://127.0.0.1:5000/health |
| Infrastructure baseline | C:\Trading\BASELINE.md |
| Main README | C:\Trading\README.md |

## System Overview

- **Backend**: FastAPI + Uvicorn on 0.0.0.0:8005
- **HTTPS (self-signed)**: 0.0.0.0:8443
- **MT5 Bridge**: 127.0.0.1:5000
- **Domain**: inventra.website -> Cloudflare Tunnel -> localhost:8005
- **Tunnel ID**: da2cf48b
- **Cloudflare Zone ID**: 7d776e863660c45279fdf615ab52a90e

## Bot Fleet

**15 active bot entries** across 8 symbols, using 4 strategies (Bollinger, MACD, SMA, Volatility Breakout) + 1 Propfirm Pass bot. Two BTCUSD bots are disabled (crypto not available on MetaQuotes-Demo).

## Prop Firm Challenge

- **FTMO 1-Phase $10K**: Login 1513767391, server FTMO-Demo, $9,076.69 balance
- **FTMO $100K**: Login 1513845007, server FTMO-Demo, $100,000 balance
- Drawdown limits: 5% daily, 10% total (static)
- Emergency stop at 8% static DD

## Deployment

Bots auto-start via the backend's `lifespan` hook. The backend scans `bots/active_bots/<PAIR>/run_<strategy>.py` on startup and launches each as a subprocess. The `Unified Bot Runner` alternative runs all in one process with one MT5 connection.

## Known Issues

| Severity | Issue |
|----------|-------|
| Medium | No process supervision (backend not auto-restarted on crash) |
| Medium | Redis disconnected (sessions/caching not available) |
| Medium | JSON file store (62MB, not ACID) instead of SQLite |
| Medium | Backend bound to 0.0.0.0 (public, not localhost-only) |
| Low | CORS allow_origins=["*"] — should be restricted |

*Part of Project PropMillion: $1M in 12 months via algorithmic trading.*
