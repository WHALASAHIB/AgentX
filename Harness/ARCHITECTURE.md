# AGENTX Trading System — Architecture Overview

## Component Diagram (ASCII)

```
                          +-----------------------+
                          |    Browser Dashboard   |
                          |  (HTML/JS/CSS, 2750ln) |
                          +----------+------------+
                                     | HTTP :8005
                                     v
     +--------------------+--------------------+---------+
     |          FastAPI Backend (Python 3.12)            |
     |  backend/app.py  (~2025 lines, Port 8005)         |
     |  CORS enabled · Google OAuth + Access Codes       |
     |  SQLite (backend/db/pool.py) · Redis (optional)   |
     +---+-------------+------------------+-------------+
         |             |                  |
    HTTP |        HTTP |             HTTP |
         v             v                  v
  +------+------+ +---+------+   +-------+--------+
  | MT5 Bridge  | | Research |   | Notion API     |
  | Port 5000   | | Division |   | Reports/Dash   |
  | Host→VM msg | | 4 modules|   +----------------+
  +------+------+ +----------+
         |
         v
  +------+----------+
  | MetaTrader 5     |
  | (Host 10.10.10.1)|
  +------+----------+
         |
         v
  +------+-------------------------------------------+
  |  23 Trading Bots (all on Host 10.10.10.1)        |
  |  4 Legacy · MACD(9) · GoldPhoenix(5)             |
  |  Bollinger(3) · SMA(2) · Multi-Symbol            |
  +--------------------------------------------------+
```

## Data Flow

```
Agent/AI (Hermes)
    |
    | (prompt / instruction)
    v
FastAPI Backend (VM 10.10.10.100:8005)
    |
    | (REST / JSON)
    v
MT5 Bridge (Host 10.10.10.1:5000)
    |
    v
MetaTrader 5 (Host)
    |
    +--> 23 Trading Bots (read market data, signal generation)
    |
    +--> Trade Execution (MT5 terminal)
    |
    v
Backend (receives execution feedback, stores in SQLite)
    |
    v
Research Division (every 4h via Hermes cron)
    |  analytics_engine.py → strategy_innovation.py
    |  deployment_engine.py → sprint_manager.py
    v
Reports → JSON files (research_division/reports/)
    |
    v
Notion Dashboards + Browser Dashboard
```

### Detailed Pipeline

1. **Agent/AI Layer** — Hermes agents orchestrate trading decisions, research cycles, and system maintenance via cron jobs and API calls to the backend.
2. **Backend Layer** — FastAPI on VM (10.10.10.100:8005) serves the dashboard, manages bot lifecycle, records trades, and coordinates research.
3. **Bridge Layer** — `bridge_client.py` on Host (10.10.10.1:5000) is the sole communication channel between the VM backend and the MT5 terminal.
4. **Execution Layer** — MT5 on the Host machine runs 23 trading bots that generate signals and execute trades on forex pairs.

## Port Mapping

| Service          | Port | Host              | Protocol | Purpose                      |
|------------------|------|-------------------|----------|------------------------------|
| FastAPI Backend  | 8005 | 10.10.10.100 (VM) | HTTP     | Dashboard + REST API         |
| MT5 Bridge       | 5000 | 10.10.10.1 (Host) | HTTP     | VM↔MT5 communication        |
| Hermes Cron      | N/A  | 10.10.10.100 (VM) | Internal | Research cycle scheduling    |
| SQLite           | N/A  | 10.10.10.100 (VM) | File     | Persistent trade/state store |

## Deployment Model

```
+---------------------------------------------------+
|  HOST MACHINE (10.10.10.1) — Windows 11           |
|  +---------------------------------------------+  |
|  | MetaTrader 5 Terminal                        |  |
|  | 23 Trading Bots (Python/MQL5)               |  |
|  | MT5 Bridge Client (bridge_client.py:5000)    |  |
|  +---------------------------------------------+  |
|                                                    |
|  VirtualBox Bridge Network                         |
|                                                    |
|  +---------------------------------------------+  |
|  | VM (10.10.10.100) — Linux                   |  |
|  | FastAPI Backend (uvicorn :8005)              |  |
|  | SQLite Database                              |  |
|  | Research Division (Hermes cron / 4h)         |  |
|  | Hermes Agent (Nous Research)                 |  |
|  +---------------------------------------------+  |
+---------------------------------------------------+
```

## Key Architectural Principles

- **Separation of Concerns** — VM runs stateless backend logic; Host runs stateful trading terminal. No direct MT5 access from VM.
- **Single Bridge Pattern** — All VM→MT5 communication goes through `bridge_client.py:5000`. No backdoors.
- **Agent-First Automation** — Hermes schedules the research cycle; the backend serves results; the bridge executes.
- **Immutable Infrastructure Intent** — Features are gated by Clean State Protocol; dirty state is detected and rejected before deployment.
- **Observability** — Dashboard (single HTML file) is served by the backend; research outputs go to JSON on disk and Notion.

## Technology Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Backend       | Python 3.12, FastAPI, Uvicorn       |
| Database      | SQLite (pool.py connection pool)    |
| Cache         | Redis (optional)                    |
| Frontend      | Vanilla JS, HTML5, CSS3             |
| Charts        | Chart.js (CDN)                      |
| Auth          | Google OAuth 2.0                    |
| Trading       | MetaTrader 5, MQL5                  |
| Bridge        | Python HTTP bridge client           |
| Automation    | Hermes Agent / cron                 |
| Reporting     | JSON → Notion API                   |
| Secrets       | `.env.keys`, `.env.cloudflare`      |

## Security Boundaries

- **No hardcoded secrets** — credentials loaded at runtime from `.env.keys` and `.env.cloudflare`
- **Google OAuth** — dashboard access authentication
- **Access Codes** — secondary auth for API/bot control
- **Network Segmentation** — bridge port (5000) is host-only; backend port (8005) is VM-only plus dashboard
