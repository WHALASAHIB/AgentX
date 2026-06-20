# 🏆 AGENTX v3 — Vision Manifesto & Master Specification

> **The definitive document.** Every feature, every requirement, every expectation for the AGENTX algorithmic trading platform.
> Any AI agent, developer, or stakeholder reads this first. This is the single source of truth for WHAT we're building and WHY.

---

## 📍 THE MISSION

**$1M in 12 months** via algorithmic trading through prop firms (FTMO primary, others as authorized).

The website (`inventra.website`) is the **heart of the project** — the cockpit where everything is executed, monitored, analyzed, and controlled. Without the website, the system is just scripts on a VM. With it, it's a **trading empire**.

---

## 🔥 CORE PRINCIPLES (Non-Negotiable)

1. **The website is the heart** — Every feature must be controllable and observable from the web dashboard. No buried CLI-only features.
2. **Backtesting is the foundation** — No strategy runs live without being fully validated in the Backtesting Lab. Every insight must be available.
3. **Zero tolerance for disconnections** — Once an account is added, it stays connected. Accounts change frequently (prop firms), and the system must handle it seamlessly.
4. **Top-class UI/UX** — The visuals must be engaging, data-rich, readable. Charts, graphs, colors, animations — every detail matters. This is a professional trading terminal, not a spreadsheet.
5. **Self-improving infrastructure** — Docker, Kubernetes, CI/CD. The system upgrades itself. If a component fails, it self-heals.
6. **Security is absolute** — Secrets never committed. Accounts encrypted. Audit trails on everything.
7. **No tolerance for mistakes** — Especially in account control. A wrong account switch, a disconnected fund, a misrouted trade — these cost real money.
8. **Harness Engineering** — Every document, every feature spec, every session follows the framework. AGENTS.md as router, PROGRESS.md for state, verification gating.

---

# 🖥️ THE WEBSITE — inventra.website

## Overview

A fully-featured, production-grade algorithmic trading web platform served at `inventra.website` via Cloudflare tunnel to the backend at `localhost:8005`. Single-page application (SPA) with 12+ sections, real-time data streaming, and full bot/account/strategy lifecycle management.

**Tech Stack (Frontend):**
- Vanilla JS SPA served by FastAPI (no build step, no Node.js dependency)
- Chart.js for financial charts (candlestick, line, bar)
- Server-Sent Events (SSE) for real-time data
- CSS custom properties for theming (dark/light mode)
- Inter font + Fira Code for code editors

**Tech Stack (Backend):**
- FastAPI (Python 3.12) — REST + SSE endpoints
- PostgreSQL — persistent storage
- Redis — caching, pub/sub, state persistence
- MT5 Bridge — communication with MetaTrader 5

**Architecture:**
```
Browser → Cloudflare → FastAPI Backend (:8005) → MT5 Bridge (:5000) → MetaTrader 5
                                                    → PostgreSQL + Redis
                                                    → Hermes Agent (cron, SRE)
```

---

## 📐 UI/UX Design System

### Visual Identity

| Element | Specification |
|---------|--------------|
| **Primary Color** | `#00d4aa` (teal accent) |
| **Secondary** | `#06B6D4` (cyan) |
| **Profit** | `#22C55E` (green) with glow `rgba(34,197,94,0.25)` |
| **Loss** | `#EF4444` (red) with glow `rgba(239,68,68,0.25)` |
| **Warning** | `#F59E0B` (amber) |
| **Background** | `#000212` (near-black) — dark by default |
| **Card BG** | `#111633` with glass effect (backdrop-filter blur) |
| **Text** | `#F1F5F9` primary, `#94A3B8` secondary |
| **Border** | `#1E2940` with `rgba(255,255,255,0.07)` glass border |
| **Font** | Inter (UI), Fira Code (code/data) |

### Design Principles

1. **Glassmorphism** — Cards have translucent backgrounds, subtle borders, blur effects. Feels premium, modern, and data-focused.
2. **Dark-first** — Dark mode is default and primary. Light mode is available but secondary.
3. **Data density with readability** — Show maximum information without overwhelming. Every pixel must convey something useful.
4. **Consistent spacing** — 8px grid system. Card padding: 28px. Section spacing: 32px.
5. **Micro-interactions** — Hover states, smooth transitions (300ms cubic-bezier), active indicators on nav items, pulsing status dots.
6. **Color-coded status** — Green = running/connected/profit. Red = stopped/disconnected/loss. Amber = warning/circuit-breaker. Cyan = system/info.
7. **Animated backgrounds** — Subtle gradient particle canvas, radial gradient overlays, shimmer loading states.
8. **Responsive** — Sidebar collapses on mobile, cards reflow into single column, touch-friendly targets.

### Layout Structure

```
┌─────────────────────────────────────────────────┐
│ SIDEBAR (220px) │ TOOBAR (64px)                  │
│                 ├─────────────────────────────────┤
│ LOGO            │ Title │ Ticker │ Bridge │Theme │
├─────────────────┤─────────────────────────────────┤
│ 📊 Cmd Center   │                                 │
│ 💼 Portfolio    │     CONTENT AREA                │
│ 📓 Trade Journal│     (one section at a time)     │
│ 🧪 Backtest Lab │                                 │
│ 🤖 Bot Control  │     Cards │ Charts │ Tables     │
│ 📝 Script Editor│     Data │ Controls             │
│ 🧠 Orchestrator │                                 │
│ 🏦 Accounts     │                                 │
│ 🏆 FTMO         │                                 │
│ 📈 Analytics    │                                 │
│ ⚙️ Settings     │                                 │
│ 📄 File Conv    │                                 │
├─────────────────┤                                 │
│ v3.0.0          │                                 │
└─────────────────┴─────────────────────────────────┘
```

---

## 📊 SECTION 1: COMMAND CENTER

**The real-time trading dashboard overview.** This is the first thing you see — the cockpit.

### Features
- **4 KPI cards** at top row: Balance, Equity, Daily P&L (color-coded), Open Positions count
- **Mini ticker bar** at top of content: XAUUSD, EURUSD, GBPUSD, USDJPY prices with direction indicators
- **Equity curve chart** — last 7 days, gradient fill, interactive tooltip
- **Open positions table** — symbol, type, volume, entry price, current price, P&L, SL, TP
- **Recent trades feed** — last 10 closed trades with profit/loss indicators
- **Bot running summary** — X/Y bots running, last health check timestamp
- **Quick actions** — Pause all, Resume all, Refresh data buttons
- **Performance today** — Win rate %, P&L, best/worst trade
- **MT5 Bridge status indicator** — connected/disconnected with latency

### Data Sources
- `/api/health` — backend + bridge status
- `/api/stats` — account statistics
- `/api/positions` — open positions
- `/api/trades` — recent trades (limit=10)
- `/api/bots` — bot status list
- SSE `/api/events` — real-time updates on positions, P&L, ticks

---

## 💼 SECTION 2: PORTFOLIO

**Account positions and performance across all strategies.**

### Features
- **Portfolio equity curve** — longer timeframe (30 days, 90 days toggle)
- **Strategy allocation pie chart** — percentage of capital per strategy
- **Position distribution** — bar chart: lots per symbol
- **Daily P&L heatmap** — grid of days × profit/loss intensity (last 30 days)
- **Asset allocation table** — symbol, strategy, lots, value, unrealized P&L, realized P&L
- **Risk metrics panel** — Sharpe ratio, Sortino, Max DD, Win Rate, Profit Factor
- **Export portfolio snapshot** — CSV/PDF download

### Backend Endpoints
- `/api/portfolio/summary` — aggregated portfolio data
- `/api/portfolio/equity?days=30` — equity curve data
- `/api/portfolio/allocation` — strategy/symbol allocation breakdown
- `/api/portfolio/risk-metrics` — Sharpe, Sortino, max DD, etc.

---

## 📓 SECTION 3: TRADE JOURNAL

**Complete trade history with smart filters.** Every trade recorded, analyzable, and pushable to Notion.

### Features
- **Advanced filtering** — by date range, symbol, strategy, direction, outcome (win/loss/breakeven), tags
- **Sortable columns** — Date, Symbol, Strategy, Direction, Volume, Entry, Exit, P&L (pips + currency), Duration, Tags
- **Pagination** — 50 trades per page, total count displayed
- **Bulk actions** — select trades → tag, add notes, export
- **P&L distribution chart** — histogram of trade outcomes
- **Win rate by strategy** — donut/bar chart per strategy
- **P&L by symbol** — horizontal bar chart
- **Trade detail modal** — click any trade → full detail: chart screenshot if available, notes, tags, FTMO compliance flags
- **Notion push status** — column showing whether trade was pushed to Notion
- **Tag management** — add/remove tags inline, tag cloud
- **Export** — CSV, JSON, PDF formats
- **Equity curve with trade markers** — scatter points on equity curve showing entry/exit of each trade

### Backend Endpoints
- `/api/trades?status=closed&symbol=X&strategy=Y&from=Z&to=W&page=1&per_page=50`
- `/api/trades/{id}/tags` — PUT: add/remove tags
- `/api/trades/{id}/notes` — PUT: add notes
- `/api/trades/filter` — POST: advanced filter with pagination
- `/api/trades/export?format=csv` — GET: export filtered trades

---

## 🧪 SECTION 4: BACKTESTING LAB 🏆

**THE CROWN JEWEL.** This must be the best backtesting terminal on any trading platform. Every possible insight about a strategy must be available.

### Input Panel

| Parameter | Options |
|-----------|---------|
| **Strategy** | MACD, GoldPhoenix, Bollinger, SMA, Custom (paste code) |
| **Symbol** | XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD, USDCHF, BTCUSD, EURJPY, GBPJPY |
| **Timeframe** | M1, M5, M15, M30, H1, H4, D1, W1 |
| **Date Range** | 1 month, 3 months, 6 months, 1 year, 3 years, 5 years, 10 years, Custom |
| **Initial Balance** | Text input (default: $10,000) |
| **Risk %** | Text input (default: 0.15%) |
| **Account Type** | FTMO P1, FTMO P2, Personal (applies different rule sets) |
| **Custom Parameters** | Dynamic form fields per strategy (EMA periods, ATR multiplier, RSI thresholds, etc.) |
| **Optimization Mode** | Toggle: single run vs grid optimization |

### Results Dashboard (After Backtest Runs)

#### 1. Performance Summary Cards
| Metric | Description |
|--------|-------------|
| **Net Profit** | Total P&L in currency and % |
| **Total Trades** | Number of trades executed |
| **Win Rate** | % of winning trades |
| **Profit Factor** | Gross Profit / Gross Loss |
| **Sharpe Ratio** | Risk-adjusted return |
| **Max Drawdown** | Largest peak-to-trough decline (%) |
| **Average RR** | Average risk-to-reward ratio |
| **Expectancy** | Average profit per trade |
| **SQN** | System Quality Number |
| **Recovery Factor** | Net Profit / Max DD |

#### 2. Equity Curve
- Interactive Chart.js candlestick/line chart
- Annotations for drawdown periods (red shading)
- Trade markers (green dots for wins, red for losses)
- Zoom, pan, hover tooltips
- Compare mode: overlay multiple backtest equity curves

#### 3. Trade Distribution Analysis
- **P&L Histogram** — Distribution of trade outcomes (bucketed)
- **Win/Loss by Month** — Heatmap: green/red intensity by month
- **Win/Loss by Day of Week** — Bar chart showing performance by weekday
- **Win/Loss by Hour** — Bar chart showing performance by trading hour (HKT)
- **Consecutive Wins/Losses** — Streak chart (longest win/loss streaks)
- **Trade Duration Distribution** — Histogram of trade holding times
- **Position Size vs P&L** — Scatter plot

#### 4. Strategy-Specific Metrics
| Strategy | Metrics |
|----------|---------|
| **MACD** | Signal line cross count, Histogram divergence frequency, EMA alignment % |
| **GoldPhoenix** | EMA trend filter accuracy, RSI zone entries, ATR volatility gate trigger rate |
| **Bollinger** | Squeeze count, Band touch frequency, Band walk detection |
| **SMA** | Crossover accuracy, 200-SMA filter effectiveness, Whipsaw count |

#### 5. FTMO Compliance Check
- **FTMO P1 Simulation** — Can it pass Phase 1? Profit target %, DD %, Min days met?
- **FTMO P2 Simulation** — Can it pass Phase 2? More conservative targets
- **Daily Loss Limit Breaches** — How many times would daily -5% be hit?
- **Max Drawdown Breaches** — How many times would -10% (P1) or -5% (P2) be hit?
- **Consistency Rule Check** — No single trade > 20% of total profit target
- **Verdict** — ✅ PASS / ❌ FAIL with explanation

#### 6. Comparison Mode
- Side-by-side comparison of up to 4 backtest runs
- Radar chart comparing: Win Rate, Profit Factor, Sharpe, Max DD, Avg RR
- Table with all metrics side-by-side
- Equity curve overlay

#### 7. Parameter Optimization Results
- Heatmap of parameter combinations × profit factor
- Best parameters highlighted
- Sensitivity analysis — how each parameter affects results
- Parallel coordinates chart for multivariate optimization

#### 8. Monte Carlo Simulation
- Run 1000+ shuffled trade sequences
- Distribution of possible outcomes
- Confidence intervals (95%, 99%)
- Worst case, median, best case equity curves
- Probability of passing FTMO challenge

#### 9. Walk-Forward Analysis
- Train period vs test period performance
- Robustness score
- Out-of-sample performance vs in-sample

#### 10. Export & Share
- Export full report as PDF (with all charts)
- Export trade list as CSV
- Shareable link to backtest configuration
- Save to Favorites for later comparison

### Backend Endpoints
- `/api/backtest/run` — POST: run single backtest
- `/api/backtest/optimize` — POST: parameter grid optimization
- `/api/backtest/custom` — POST: custom strategy code backtest
- `/api/backtest/compare` — POST: compare multiple runs
- `/api/backtest/monte-carlo/{run_id}` — GET: Monte Carlo simulation
- `/api/backtest/walk-forward/{run_id}` — GET: walk-forward analysis
- `/api/backtest/favorites` — GET/POST/DELETE: saved backtest configs
- `/api/backtest/report/{run_id}/pdf` — GET: export PDF report

---

## 🤖 SECTION 5: BOT CONTROL

**Manage live trading bots — start, stop, delete, monitor, inspect, modify.**

### Features

#### Bot Overview Panel
- **Bot cards** — each bot displayed as a card with:
  - Name, Strategy, Symbol, Timeframe, Magic Number
  - Status badge: 🟢 Running, 🔴 Stopped, 🟡 Error, ⚠️ Circuit Breaker
  - Last signal time, last trade time
  - Current position (if any): direction, volume, P&L
  - Today's P&L
- **Sort/filter** — by strategy, symbol, status, profitability
- **Search** — search by bot name, magic number, symbol

#### Bot Control Actions
| Action | Description |
|--------|-------------|
| **Start** | Start a stopped bot |
| **Stop** | Gracefully stop a running bot |
| **Restart** | Stop + Start (with config reload) |
| **Delete** | Remove bot from system (confirmation dialog required) |
| **Pause** | Temporary pause (bot stays loaded but doesn't trade) |
| **Resume** | Resume paused bot |

#### Bot Detail View (Click on Bot Card)
- **Full Configuration** — all parameters, read-only view with "Edit" button
- **Live Log** — tail last 50 lines of bot log, auto-refresh every 3 seconds
- **Performance Stats** — Total trades, Win Rate, P&L, Profit Factor, Avg RR for this bot
- **Open Position Detail** — if position open: entry, SL, TP, current, P&L, duration
- **Recent Trades** — last 20 trades from this bot
- **Equity Curve** — this bot's contribution to overall equity
- **Actions Panel** — Start/Stop/Restart/Delete buttons
- **Script Link** — "View Script" button opens the bot's script in Script Editor (Section 6)

#### Batch Operations
- Select multiple bots → Start All, Stop All, Restart All, Delete Selected
- Filter by strategy → apply action to all matching bots
- **CAUTION:** Stop all bots must be explicitly confirmed (2-step confirmation)

#### Status Monitoring
- Auto-refresh bot status every 5 seconds
- Push notifications (via toast) when bot state changes (started, stopped, error, circuit breaker)
- Error count badge on sidebar

### Backend Endpoints
- `/api/bots` — GET: list all bots, POST: create new bot
- `/api/bots/{id}` — GET: detail, PUT: update config, DELETE: remove
- `/api/bots/{id}/start` — POST
- `/api/bots/{id}/stop` — POST
- `/api/bots/{id}/restart` — POST
- `/api/bots/{id}/status` — GET: real-time status
- `/api/bots/{id}/log?lines=50` — GET: tail bot log
- `/api/bots/{id}/performance` — GET: performance stats for this bot
- `/api/bots/batch` — POST: batch operations (start/stop/restart/delete)

---

## 📝 SECTION 6: SCRIPT EDITOR

**Edit, save, and deploy bot scripts directly from the browser.**

### Features

#### File Browser
- **File tree** — expandable directory structure of bot scripts
  - `bots/` — all bot scripts
  - `bots/active_bots/` — actively deployed bots
  - `strategies/` — strategy core logic
  - Backend files (read-only mode)
- Search files by name
- Recent files list

#### Code Editor
- Monaco Editor (VS Code in browser) or CodeMirror
- **Syntax highlighting** — Python syntax coloring
- **Line numbers** + gutter
- **Minimap** — code overview on right side
- **Search/replace** within file
- **Auto-indent**, bracket matching
- **Multiple tabs** — edit multiple files simultaneously
- **Unsaved changes indicator** — dot on tab
- **Git diff view** — see changes vs last committed version

#### Editor Actions
| Action | Description |
|--------|-------------|
| **Save** | Save changes to disk |
| **Deploy** | Save + deploy to production (stops bot, updates file, restarts bot) |
| **Validate** | Python syntax check before saving |
| **Format** | Auto-format Python code (Black or autopep8) |
| **Diff** | Show diff against last commit |
| **History** | Version history of file edits |
| **Revert** | Revert to last saved/committed version |

#### File Operations
- **Create new file** — template selector (bot script, strategy, config)
- **Rename file**
- **Delete file** (with confirmation)
- **Upload file** — upload from local machine

#### Deployment Flow
1. Edit file in editor
2. Click "Validate" → syntax check runs on backend
3. Click "Deploy" → backend stops relevant bot(s), saves file, restarts bot(s)
4. Deployment status shown in notification
5. Rollback button available for 60 seconds after deploy

### Backend Endpoints
- `/api/editor/files` — GET: list files
- `/api/editor/read/{path}` — GET: read file content
- `/api/editor/save` — POST: save file
- `/api/editor/deploy` — POST: deploy edited script
- `/api/editor/validate` — POST: syntax check
- `/api/editor/history/{path}` — GET: version history
- `/api/editor/create` — POST: create new file

---

## 🧠 SECTION 7: AI ORCHESTRATOR

**Multi-agent trading intelligence system — the brain of AGENTX.**

### Features

#### Agent Status Dashboard
- **Agent cards** — one per agent with status (idle/running/error), last run time, tasks completed
  - 📡 Collector — Market data collection agent
  - 📊 Analyst — Sentiment analysis and insight generation
  - 🎯 Sprint Master — Sprint planning and backlog management
  - 💡 Innovator — Strategy improvement proposals
  - 🚀 Deployer — Strategy deployment and verification
  - 🛡️ SRE — System reliability monitoring
  - 🔍 AIOps — Anomaly detection
  - 📋 AgentOps — Decision and failure logging

#### Agent Details
- **Task history** — timeline of tasks executed by each agent
- **Decision log** — what each agent decided and why
- **Output preview** — last output from each agent (insights, proposals, reports)
- **Manual trigger** — button to force-run any agent immediately

#### Agent Commands
- "Run Research Cycle" — trigger full 5-agent research pipeline
- "Generate Insights" — force analyst to generate fresh insights
- "Run Sprint" — trigger sprint planning
- "Deploy Top Strategy" — deploy the highest-priority strategy proposal

### Backend Endpoints
- `/api/orchestrator/agents` — GET: list agents and status
- `/api/orchestrator/command` — POST: send command to agent
- `/api/orchestrator/timeline` — GET: agent event timeline

---

## 🏦 SECTION 8: ACCOUNT MANAGER ❗

**CRITICAL — ZERO TOLERANCE FOR MISTAKES.** Manage multiple prop firm accounts. Once an account is added, it stays connected. No disconnections allowed.

### Features

#### Account Overview
- **Account cards** — each account displayed as a card:
  - Account name, Broker, Server, Login, Account type (Challenge P1/P2, Funded, Personal)
  - Balance, Equity, Margin, Free Margin
  - Daily P&L, Total P&L
  - Status badge: 🟢 Active, 🟡 Warning, 🔴 Disconnected, ⏳ Pending
  - Current drawdown % (with color: green < 3%, amber < 5%, red > 5%)
  - Active bot count on this account
  - Last connection time
- **Auto-refresh** every 10 seconds
- **Sort/filter** — by broker, account type, status, balance

#### Add Account
- **Form fields:**
  - Account Name (user-friendly label)
  - Broker (e.g., FTMO, MFF, personal)
  - Server (e.g., FTMO-Demo, FTMO-Real)
  - Account Type: Challenge P1, Challenge P2, Funded, Personal
  - Login (MT5 login ID)
  - Password (encrypted via WinCM, not stored in plaintext)
  - Leverage (dropdown: 1:10, 1:30, 1:50, 1:100, 1:200, 1:500)
  - Starting Balance (for tracking)
  - Notes (optional)
- **Connection test** before saving — "Test Connection" button pings the broker
- **Auto-connect** toggle — once saved, system maintains persistent connection

#### Account Detail View (Click on Account Card)
- **Connection Status** — live connection indicator, latency, last ping
- **Account Metrics** — Balance, Equity, P&L, Drawdown, Margin Level, Leverage
- **Daily P&L Chart** — last 30 days
- **Active Bots** — list of bots assigned to this account
- **Open Positions** — symbol, direction, volume, entry, current, P&L
- **Trade History** — trades from this account only
- **FTMO Progress** (if challenge account) — profit target progress %, days remaining, max DD remaining
- **Performance Summary** — Total trades, Win Rate, P&L, Profit Factor (account-level)
- **Risk Limits** — configurable per-account risk overrides (max daily loss %, max DD %, max lot size)

#### Account Management Actions
| Action | Description |
|--------|-------------|
| **Edit** | Update account configuration |
| **Delete** | Remove account (confirmation required) |
| **Test Connection** | Ping broker server |
| **Reconnect** | Force re-establish connection |
| **Switch Active** | Set this account as the active trading account |
| **Disable Bots** | Stop all bots on this account |
| **Enable Bots** | Resume all bots on this account |

#### Multi-Account Features
- **Account switching** — dropdown in top bar to switch active account (affects entire dashboard)
- **Consolidated view** — see combined P&L across all accounts
- **Per-account risk** — each account has independent risk settings
- **Auto-failover** — if one MT5 connection drops, others remain unaffected
- **Account groups** — group accounts by firm (FTMO group, personal group)
- **Bulk account import** — CSV upload for adding multiple accounts at once

#### Connection Persistence
- **Continuous heartbeat** — every 5 seconds ping each connected account
- **Auto-reconnect** — on disconnect, retry with exponential backoff (1s, 2s, 4s, 8s, 16s, 30s max)
- **Reconnection log** — every reconnection attempt logged with timestamp and result
- **Alert on persistent disconnect** — Telegram notification if account disconnected for > 60 seconds
- **Graceful degradation** — one account going down never affects others

### Backend Endpoints
- `/api/accounts` — GET: list accounts, POST: add account
- `/api/accounts/{id}` — GET: detail, PUT: update, DELETE: remove
- `/api/accounts/{id}/test` — GET: test connection
- `/api/accounts/{id}/reconnect` — POST: force reconnect
- `/api/accounts/active` — GET: get active account, PUT: set active account
- `/api/accounts/{id}/risk-limits` — GET/PUT: per-account risk settings
- `/api/accounts/consolidated` — GET: consolidated metrics across all accounts
- `/api/accounts/import` — POST: bulk CSV import

---

## 🏆 SECTION 9: FTMO CHALLENGE MANAGER

**Track every FTMO challenge from purchase to funded payout.**

### Features

#### Challenge Overview
- **Challenge cards** — each challenge displayed:
  - Challenge name, Phase (P1/P2/Funded)
  - Account size (e.g., $10k, $100k, $200k)
  - Profit target %, current progress %
  - Max DD %, current DD %
  - Days remaining
  - Status: 🔴 In Progress, 🟢 Completed, ✅ Funded, ❌ Failed
  - Balance, Equity, Daily P&L

#### Add Challenge
- Form: Firm, Account Size, Phase, Start Date, Fee Paid
- Auto-links to an Account Manager account

#### Challenge Detail
- **Progress Bar** — visual progress toward profit target
- **DD Gauge** — current drawdown vs max allowed
- **Daily P&L Table** — each day's performance during challenge
- **Compliance Alerts** — any FTMO rule violations flagged
- **Trade Log** — challenge-specific trades
- **Projection** — expected completion date at current pace
- **Verification Calendar** — shows trading days counted toward minimum

### Backend Endpoints
- `/api/ftmo/challenges` — GET/POST
- `/api/ftmo/challenges/{id}` — GET/PUT
- `/api/ftmo/profiles` — GET: FTMO rule profiles
- `/api/ftmo/summary` — GET: consolidated FTMO performance

---

## 📈 SECTION 10: ANALYTICS

**Advanced metrics and deep insights into every aspect of the trading system.**

### Features

#### Performance Analytics
- **Overall P&L Chart** — customizable date range, with comparison periods
- **Win Rate Trend** — rolling 50-trade win rate over time
- **Profit Factor Trend** — rolling period profit factor
- **Sharpe Ratio Trend** — rolling 30-day Sharpe
- **Drawdown Chart** — equity peaks and valleys
- **Recovery Time** — average time to recover from drawdown

#### Strategy Analytics
- **Strategy Comparison** — side-by-side metrics for all strategies
- **Best/Worst Performer** — top and bottom strategies by P&L
- **Strategy P&L Contribution** — percentage of total P&L per strategy
- **Performance by Market Condition** — trending, ranging, volatile
- **Session Analysis** — performance by Asian/London/US/Overlap sessions

#### Symbol Analytics
- **Symbol P&L Breakdown** — P&L per symbol
- **Symbol Win Rates** — win rate per symbol
- **Symbol Volatility Impact** — correlation between volatility and bot performance

#### Risk Analytics
- **Value at Risk (VaR)** — 95% and 99% daily VaR
- **Position Concentration** — percentage of capital in each position
- **Correlation Matrix** — correlation between strategy returns
- **Stress Test** — simulated performance during past crash events

#### Time-Based Analytics
- **Hourly Performance** — P&L by hour of day
- **Daily Performance** — P&L by day of week
- **Monthly Performance** — P&L by month
- **Calendar View** — color-coded daily P&L calendar

#### Export & Reports
- **PDF Report Generator** — comprehensive analytics report
- **Scheduled Reports** — daily/weekly/monthly auto-generated reports
- **Data Export** — any view exportable as CSV/JSON

### Backend Endpoints
- `/api/analytics/overview?from=X&to=Y` — GET: comprehensive analytics
- `/api/analytics/strategies` — GET: strategy comparison
- `/api/analytics/symbols` — GET: symbol breakdown
- `/api/analytics/risk` — GET: risk metrics
- `/api/analytics/time-based` — GET: hourly/daily/monthly breakdown
- `/api/analytics/export?format=pdf` — GET: export report

---

## ⚙️ SECTION 11: SETTINGS

**System configuration, user preferences, and integrations management.**

### Features

#### General Settings
- **Appearance** — Dark/Light mode toggle, accent color picker
- **Language** — (future: multi-language support)
- **Time Zone** — display time in HKT/UTC/local
- **Number Format** — decimal places, currency symbol

#### Trading Settings
- **Global Risk %** — default risk per trade (0.15%)
- **Max Positions** — global max open positions
- **Circuit Breaker** — consecutive loss threshold (default 5)
- **Slippage** — max slippage in pips
- **Trading Hours** — session filter configuration
- **News Filter** — pause before/after economic releases (minutes configurable)
- **Position Sizing** — fixed lot vs percentage toggle

#### Notification Settings
- **Telegram Alerts** — enable/disable per alert type
  - Trade executed
  - Bot started/stopped
  - Circuit breaker triggered
  - Account disconnected
  - Anomaly detected
  - Daily summary
- **Email Alerts** — configure email recipients
- **Web Push** — browser notifications

#### Integration Settings
- **Notion** — API token, database IDs, push interval, fields to push
- **Cloudflare** — tunnel configuration, domain settings
- **Telegram** — bot token, chat ID
- **GitHub** — remote URL, branch, auto-push toggle

#### Security Settings
- **API Keys** — view/manage API keys for external access
- **Access Codes** — generate/manage access codes for users
- **OAuth** — Google OAuth configuration
- **Audit Log** — view security audit log
- **Session Management** — active sessions, revoke sessions

#### System Settings
- **Backend** — port, host, debug mode
- **Database** — connection string, pool size
- **Redis** — host, port, max memory
- **Hermes Agent** — cron job status, enable/disable individual jobs
- **Logging** — log level, retention period, log rotation settings

### Backend Endpoints
- `/api/settings` — GET/PUT: all settings
- `/api/settings/{category}` — GET/PUT: settings by category
- `/api/settings/notifications/test` — POST: test notification
- `/api/settings/export` — GET: export all settings as JSON
- `/api/settings/import` — POST: import settings from JSON

---

## 📄 SECTION 12: FILE CONVERTER

**Convert trading-related documents (PDF, DOCX, XLSX) to Markdown for AI processing.**

### Features
- Drag-and-drop file upload
- Convert to Markdown with original formatting preserved
- Download converted file
- Preview before download
- Batch conversion (up to 5 files)

### Backend Endpoints
- `/api/convert/upload` — POST: upload and convert file
- `/api/convert/preview/{id}` — GET: preview converted content
- `/api/convert/download/{id}` — GET: download converted file

---

# 🛡️ INFRASTRUCTURE & DEVOPS

> **Senior Software Engineer level.** Docker, Kubernetes, CI/CD, self-healing, self-improving, production-grade everything.

## Deployment Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    PRODUCTION CLUSTER                       │
│                       (Kubernetes)                          │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Frontend    │  │   Backend    │  │  Redis       │      │
│  │  (nginx)     │  │  (FastAPI)   │  │  (Cache)     │      │
│  │  :80/:443    │  │  :8005       │  │  :6379       │      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘      │
│         │                 │                                  │
│         ▼                 ▼                                  │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │  Cloudflare  │  │  PostgreSQL  │                         │
│  │  Tunnel      │  │  (Primary)   │                         │
│  │  (ingress)   │  │  :5432       │                         │
│  └──────────────┘  └──────────────┘                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │  MT5 Bridge  │  │  Hermes      │                         │
│  │  (sidecar)   │  │  Agent       │                         │
│  │  :5000       │  │  (cron)      │                         │
│  └──────────────┘  └──────────────┘                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │  Prometheus  │  │  Grafana     │                         │
│  │  (metrics)   │  │  (monitor)   │                         │
│  └──────────────┘  └──────────────┘                         │
└────────────────────────────────────────────────────────────┘
```

## Docker Containers

| Container | Image | Replicas | Resources |
|-----------|-------|----------|-----------|
| `agentx-frontend` | nginx:alpine | 2 | 0.25 CPU, 256MB RAM |
| `agentx-backend` | python:3.12-slim | 3 | 1 CPU, 1GB RAM |
| `agentx-bridge` | python:3.12-slim | 1 (per MT5 instance) | 0.5 CPU, 512MB RAM |
| `agentx-redis` | redis:7-alpine | 1 | 0.5 CPU, 512MB RAM |
| `agentx-postgres` | postgres:16-alpine | 1 | 1 CPU, 2GB RAM |
| `agentx-cron` | python:3.12-slim | 1 | 0.25 CPU, 256MB RAM |
| `prometheus` | prom/prometheus | 1 | 0.5 CPU, 1GB RAM |
| `grafana` | grafana/grafana | 1 | 0.5 CPU, 512MB RAM |

## Kubernetes Configuration

### Services
- `agentx-backend-svc` — ClusterIP, port 8005
- `agentx-frontend-svc` — ClusterIP, port 80
- `agentx-redis-svc` — ClusterIP, port 6379
- `agentx-postgres-svc` — ClusterIP, port 5432
- `agentx-bridge-svc` — ClusterIP, port 5000

### Deployments
- Rolling update strategy (maxSurge: 25%, maxUnavailable: 0)
- Health checks: liveness + readiness probes
- Resource limits and requests
- PodAntiAffinity for cross-node spread

### ConfigMaps & Secrets
- `agentx-config` — ConfigMap: non-sensitive config
- `agentx-secrets` — Secret: credentials (encrypted via SealedSecrets or External Secrets Operator)

### Ingress
- Cloudflare Tunnel → nginx ingress controller
- TLS termination at Cloudflare

## CI/CD Pipeline (GitHub Actions)

Every push to `main` branch:

```
1. Code checkout
2. Python syntax validation (py_compile all .py files)
3. Unit tests (pytest)
4. Build Docker images
5. Push to container registry (Docker Hub / GHCR)
6. Deploy to staging (K8s namespace: agentx-staging)
7. Smoke tests (health check + API test + bot status check)
8. Deploy to production (K8s namespace: agentx-prod)
9. Health verification
10. Telegram notification: success/failure
```

### Rollback
- One-click rollback via GitHub Actions — redeploys previous stable image
- `make rollback` — reverts code and rebuilds
- Canary deployments: 1 replica runs new version for 5 minutes before full rollout

## Monitoring & Observability

### Prometheus Metrics
| Metric | Type | Labels |
|--------|------|--------|
| `agentx_bots_active` | Gauge | strategy, symbol |
| `agentx_trades_total` | Counter | strategy, symbol, outcome |
| `agentx_trade_duration_seconds` | Histogram | strategy |
| `agentx_pnl_daily` | Gauge | account |
| `agentx_drawdown_current` | Gauge | account |
| `agentx_bridge_latency_ms` | Histogram | |
| `agentx_http_requests_total` | Counter | method, path, status |
| `agentx_http_request_duration_ms` | Histogram | method, path |
| `agentx_db_query_duration_ms` | Histogram | query_type |
| `agentx_redis_hit_ratio` | Gauge | |

### Grafana Dashboards
1. **Trading Overview** — P&L, bots, trades, win rate (real-time)
2. **System Health** — CPU, RAM, disk, network, service status
3. **API Performance** — request rates, latencies, error rates
4. **Account Overview** — all accounts, balances, equity curves
5. **FTMO Dashboard** — challenge progress, drawdown, days remaining

### Alerts (Prometheus AlertManager)
| Alert | Condition | Severity |
|-------|-----------|----------|
| BackendDown | `up{job="agentx-backend"} == 0` | Critical |
| HighLatency | `agentx_bridge_latency_ms > 500` | Warning |
| HighErrorRate | `rate(agentx_http_requests_total{status=~"5.."}[5m]) > 0.05` | Critical |
| DrawdownWarning | `agentx_drawdown_current > 8` | Warning |
| DrawdownCritical | `agentx_drawdown_current > 10` | Critical |
| BotStopped | `agentx_bots_active < expected_count` | Warning |
| AccountDisconnected | `agentx_account_connected == 0` | Critical |
| DiskSpaceLow | `node_filesystem_free_bytes < 0.1` | Warning |

## Self-Healing (SRE Engine)

Runs every 5 minutes via Hermes cron. Orchestrated across all containers.

| Check | Action |
|-------|--------|
| Backend not responding | Restart backend container |
| Bridge disconnected | Restart bridge container + reconnect MT5 |
| Bot count < expected | Restart stopped bots with staggered delay |
| Memory < 500MB free | Kill non-essential processes, GC trigger |
| Disk < 10% free | Rotate logs, compress archives |
| Redis memory > 80% | Evict non-critical keys |
| PostgreSQL pool exhausted | Increase pool size, alert |
| SSL certificate expiring < 7 days | Auto-renew via certbot/Cloudflare API |

## Backup & Recovery

### Automated Backups
| Backup | Frequency | Retention | Location |
|--------|-----------|-----------|----------|
| PostgreSQL dump | Every 6 hours | 14 days | `backups/db/` |
| Bot state (Redis) | Every 6 hours | 7 days | `backups/redis/` |
| Configuration | Every deploy | 30 versions | `backups/config/` |
| Full system | Daily at 02:00 HKT | 30 days | `backups/full/` |

### Disaster Recovery
- **Cold start** — `make setup && make deploy && make check`
- **DB restore** — `make db-restore <backup_file>`
- **Full restore** — `make restore <date>` — restores DB + config + bot state
- **RTO** (Recovery Time Objective): < 30 minutes
- **RPO** (Recovery Point Objective): < 6 hours (max data loss)

---

# 📋 APPENDIX: SYSTEM INTEGRATION

## Current System State (as of June 2026)

| Component | Status | Details |
|-----------|--------|---------|
| **Backend** | ✅ Running | FastAPI on VM (10.10.10.100:8005) |
| **MT5 Bridge** | ✅ Running | Host (10.10.10.1:5000), account 5051185832 |
| **Bots** | ✅ 19 active | 4 disabled by council |
| **Balance** | Demo | ~$96,685.85 |
| **Frontend** | ✅ 12 sections | SPA served by backend |
| **Research Cyc** | ✅ Every 4h HKT | 5-agent pipeline |
| **Notion Push** | ✅ Every 5 min | Trade journal auto-push |
| **SRE Watchdog** | ✅ Every 5 min | Self-healing + health checks |
| **TryCloudflare** | ✅ Active | `leader-sega-mit-ottawa.trycloudflare.com` |
| **Domain** | ⏳ DNS prop | `inventra.website` via Cloudflare |
| **GitHub** | ✅ Synced | `WHALASAHIB/AgentX.git` |
| **CI Pipeline** | ✅ Passing | `py_compile` validation |

## Existing Harness Files (Harness/ folder)

| File | Content |
|------|---------|
| `README.md` | Feature index, quick access, hard constraints |
| `AGENTS.md` | Router file, 8 hard constraints, init phase, verification gating |
| `ARCHITECTURE.md` | System architecture, component diagram, data flow |
| `PROGRESS.md` | Live state tracking, completed items, blocked items |
| `bot-strategies.md` | 10 strategies, per-pair assignments, FTMO protections |
| `backend-api.md` | 75+ API endpoints with curl examples |
| `integrations.md` | 13 external integrations |
| `devops-pipeline.md` | SRE + CI/CD + DevSecOps + AgentOps + AIOps |
| `security-observability.md` | OAuth, credentials, anomaly detection |
| `cron-automation.md` | 7 cron jobs with schedules |
| `FEATURES_TEMPLATE.md` | Feature spec template |
| `clean-state-protocol.md` | 8-step end-of-session protocol |
| `current-tunnel-url.txt` | Temporary Cloudflare tunnel |
| `Makefile` | All automation targets |
| `VISION-MANIFESTO.md` | THIS FILE — master vision & specification |

---

# ✅ VERIFICATION CHECKLIST

Before any feature is considered "done":

- [ ] **Website reflects it** — Can I see/control it from `inventra.website`?
- [ ] **API exists** — Backend endpoints documented in `backend-api.md`
- [ ] **Backend endpoints work** — `make e2e` passes, health checks pass
- [ ] **UI renders correctly** — No layout breaks, responsive, data shows
- [ ] **Error handling** — Graceful error messages, not raw stack traces
- [ ] **No secrets exposed** — No credentials in code, gitignored
- [ ] **Performance acceptable** — Page loads < 2s, API responses < 500ms
- [ ] **Documented in Harness** — Feature spec filed in `Harness/features/`

---

*AGENTX v3 — Vision Manifesto. Last updated 2026-06-20.*
*This document represents the complete vision and specification for the AGENTX algorithmic trading platform.*
*Any AI agent, developer, or stakeholder should read this FIRST before making any changes.*
