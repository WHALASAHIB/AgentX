# Hermes Trading System — Architecture & Deployment Guide

Welcome to the automated algorithmic trading platform. This README documents the critical architectural constraints every developer and operator must understand before working with this system.

---

## Table of Contents

1. [Bridge Architecture (CRITICAL: Read-Only)](#1-bridge-architecture-critical-read-only)
2. [Bot Deployment Protocol](#2-bot-deployment-protocol)
3. [Session Filter Import Pattern](#3-session-filter-import-pattern)
4. [Magic Number Configuration](#4-magic-number-configuration)
5. [No-New-Services-Without-Proven-ROI Principle](#5-no-new-services-without-proven-roi-principle)
6. [Task Queue System](#6-task-queue-system)
7. [Seven-Division HermesJatti Framework](#7-seven-division-hermesjatti-framework)

---

## 1. Bridge Architecture (CRITICAL: Read-Only)

**The MT5 Bridge (port 5000) is READ-ONLY.** It has NO trade endpoint.

This is the single most important architectural constraint. The bridge serves only as a data relay:
- Relays market data (ticks, rates) from MT5 on the host machine to the backend
- Provides account information (balance, equity, positions)
- Communicates with the VM-based FastAPI backend

**What this means for development:**
- You **cannot** place orders through the bridge
- You **cannot** manage trades through the bridge
- All trading must happen via **standalone Python bots** that import `MetaTrader5` directly

**Architecture diagram:**
```
┌─────────────────────┐         ┌──────────────────────┐
│   MT5 (Host)        │ <────── │  Standalone Bots     │
│  10.10.10.1         │ import  │  (import MetaTrader5) │
└────────┬────────────┘ MetaTr  └──────────────────────┘
         │          ader5
         │ bridge data (read-only)
         v
┌─────────────────────┐
│  MT5 Bridge         │
│  port 5000          │
│  (READ-ONLY)        │
└────────┬────────────┘
         │
         v
┌─────────────────────┐
│  FastAPI Backend    │
│  port 8005 (VM)     │
│  10.10.10.100       │
└─────────────────────┘
```

---

## 2. Bot Deployment Protocol

All trading bots are **standalone Python scripts** running on the host machine (Windows 11).

### Bot Architecture
```python
#!/usr/bin/env python3
import MetaTrader5 as mt5

# Configuration
MAGIC = 999112           # Unique bot identifier
SYMBOL = "XAUUSD"        # Trading symbol
ORDER_COMMENT = "BOT_V4" # Order comment for identification

# Connection (use utils/mt5_connect.py helpers)
from utils.mt5_connect import connect_mt5, load_config

config = load_config()
connect_mt5(config)

# Trading logic...
# mt5.order_send() for trade execution
```

### Key Rules
1. **Direct MT5 connection** — bots connect to MT5 locally via `import MetaTrader5`, never through the bridge
2. **No bridge dependency for execution** — bridge is for data/telemetry only
3. **Each bot has a unique MAGIC number** — registered in the config system (see §4)
4. **Bots run as persistent background processes** — managed via the backend API or Windows Task Scheduler
5. **Logging goes to `bots/logs/{bot_name}.log`** — JSON state files for dashboard consumption
6. **Use `utils/mt5_connect.py`** — for standardized MT5 connection handling (retry, trade_allowed checks)

### Current Bot Fleet (23 processes)
- **4 Legacy Bots:** gold_bot, gold_phoenix, scalping_bot, streaming_bot
- **Multi-Pair Bots:** MACD (9 pairs), GoldPhoenix (5 pairs), Bollinger (3 pairs), SMA (2 pairs)
- **Scalping:** scalping_youtube_goldstrategy.py (magic 999112, v4)

---

## 3. Session Filter Import Pattern

Session filters must be imported using the **bare module name**, not the `bots.` prefix.

### Correct Import
```python
from session_filters import should_trade
```

### Incorrect Import (Will Fail)
```python
from bots.session_filters import should_trade  # DO NOT DO THIS
```

### Why?
The backend `app.py` and the bots themselves both need access to `session_filters`. Using a bare import ensures:
- The module works whether launched from the `bots/` directory or the project root
- The backend API can import it without path conflicts
- Consistent behavior across all 23+ bot processes

The `session_filters` module is located at `C:\Trading\bots\session_filters.py` but must always be imported by bare name.

---

## 4. Magic Number Configuration

Every bot has a unique **magic number** that identifies its trades in MT5 history. These are managed centrally.

### Endpoint
```
GET /api/config/magic-numbers
```

### Purpose
- Prevents magic number conflicts between bots
- Provides a single source of truth for the frontend dashboard
- Enables per-bot trade analysis in the analytics engine

### Active Magic Numbers
| Bot | Magic | Status |
|-----|-------|--------|
| Gold V3 | 777556 | Active |
| SCALPv4 (current) | 999112 | Active |
| Streaming V3 | 666334 | Active |
| Gold Phoenix | custom | Active |
| SCALPv3_YTB | ~~999111~~ | **KILLED** (Jun 17) |

**Note:** Never hardcode magic numbers in the frontend. Always fetch from `/api/config/magic-numbers`.

---

## 5. No-New-Services-Without-Proven-ROI Principle

**No new services, daemons, or long-running processes shall be added to this system without first demonstrating a proven return on investment.**

### Rationale
- The system already runs **23 bot processes** plus the backend, bridge, and cron jobs
- Each new service adds attack surface, maintenance burden, and resource consumption
- The SCALPv3_YTB debacle (20 trades lost -$7,766, 95.6% of all losses) demonstrates the cost of unvalidated trading logic

### Guidelines
1. **Prove it in backtest first** — run through the Research Division's backtesting pipeline
2. **Paper trade for minimum 2 weeks** — use MT5 demo or minimum lot sizes
3. **ROI threshold** — must show positive expectancy with at least 100 simulated trades
4. **Bottle-neck check** — does this duplicate existing functionality? If so, improve existing code instead
5. **Approval required** — changes to bot fleet or new services require Scrum Master sign-off

### Exceptions
- Bug fixes and security patches (immediate)
- Data pipeline improvements (no trade execution path)
- Dashboard/UI improvements (no runtime impact)

---

## 6. Task Queue System

The Division Queue Processor manages tasks via the Hermes orchestration system.

### Queue File
```
C:\Trading\orchestrator\queue.json
```

### Task Structure
```json
{
    "id": "TASK-000041",
    "division": "Research & Innovation",
    "title": "Run social sentiment scan for Jun 20",
    "priority": "normal",
    "priority_level": 3,
    "status": "pending|in_progress|completed",
    "assigned_to": "",
    "source": "R&I Board Meeting YYYY-MM-DD",
    "created_at": "ISO timestamp",
    "updated_at": "ISO timestamp",
    "claimed_at": null,
    "claimed_by": null,
    "completed_at": null,
    "result": null,
    "reviewed_by": null,
    "review_verdict": null,
    "review_notes": null,
    "error": null
}
```

### Processing Flow
1. Division Queue Processor claims available tasks (status: `pending`)
2. Sets status to `in_progress` with `claimed_at` and `claimed_by`
3. Executes the task using available tools (Hermes agents, API calls, file operations)
4. On completion: saves `result`, sets `completed_at`, marks status `completed`
5. Tasks with review requirements wait for Scrum Master approval

---

## 7. Seven-Division HermesJatti Framework

The system operates under a 7-division structure inspired by the HermesJatti framework. Each division has a Scrum Master and a Queue Processor sub-agent.

| # | Division | Focus Area |
|---|----------|------------|
| 1 | **Software Engineering** | Backend (FastAPI), Frontend (Dashboard), Infrastructure |
| 2 | **AI & Automation** | ML models, cron jobs, watchdog, sentiment pipeline |
| 3 | **Data Science** | Analytics engine, pattern analysis, performance KPIs |
| 4 | **Trading & Financial** | Bot strategies, risk management, position sizing |
| 5 | **Research & Innovation** | Market research, tool discovery, sentiment analysis |
| 6 | **Business Intelligence** | Dashboard widgets, reporting, Notion integration |
| 7 | **QA & Compliance** | Testing, API audits, security, code review |

### Scrum Process
- **Daily Stand-ups:** Board meetings at ~19:00 UTC produce new tasks
- **Task Queue:** 40+ tasks tracked in `orchestrator/queue.json`
- **Priority Levels:** 1=Critical, 2=High, 3=Normal, 4=Low
- **Review Cycle:** Tasks marked `completed` await Scrum Master review with `review_verdict` and `review_notes`

---

## Quick Reference

### Directory Layout
```
C:\Trading\
├── backend/          # FastAPI application (VM: 10.10.10.100)
│   ├── app.py        # Main application (~2025 lines)
│   ├── bridge_client.py  # MT5 bridge (port 5000)
│   ├── db/           # SQLite database layer
│   └── tests/        # Pytest test suite
├── bots/             # Trading bot scripts (Host: 10.10.10.1)
│   ├── logs/         # Per-bot execution logs + state JSON
│   ├── scalping_youtube_goldstrategy.py  # Scalping v4
│   ├── multi_symbol_bot.py               # Multi-pair framework
│   └── session_filters.py                # Liquidity session filter
├── research/         # Research outputs, sentiment scans
├── research_division/  # Analytics engine, sprint management
├── docs/             # Architecture documentation
├── utils/            # Shared utilities (mt5_connect, etc.)
├── orchestrator/     # Task queue management
├── frontend/         # Dashboard source (served by backend)
├── backtester/       # Backtesting engine + strategies
├── README.md         # This file
└── .env.keys         # Credentials (not committed)
```

### Key Ports
| Service | Port | Location |
|---------|------|----------|
| FastAPI Backend | 8005 | VM 10.10.10.100 |
| MT5 Bridge | 5000 | Host 10.10.10.1 |
| Sentiment API | 8000 | (via main backend) |

### Important Files
- `backend/app.py` — Main API server
- `research_division/analytics_engine.py` — Performance analytics
- `orchestrator/queue.json` — Task queue
- `bots/session_filters.py` — Liquidity session rules
- `utils/mt5_connect.py` — Standardized MT5 connection

---

*Document generated: 2026-06-20 00:19 UTC*
*Part of the Hermes Trading System — HermesJatti 7-Division Framework*
