# Research Division

## Overview

The Research Division is the analytical backbone of the trading system. Located
at `research_division/`, it performs automated analysis of trading performance,
generates strategy innovations, runs backtests on MT5, deploys improvements, and
produces detailed reports. The full cycle runs every 4 hours via Hermes cron.

## Purpose

- Analyze trading bot performance across all 23 bots and 9 currency pairs
- Identify underperforming strategies and suggest improvements
- Backtest proposed strategy changes on MT5 before live deployment
- Track research sprints with specific items and milestones
- Generate performance KPIs for the dashboard and Notion reports
- Maintain a historical record of strategy evolution

## Directory Structure

```
research_division/
├── run.py                  # Full cycle runner
├── analytics_engine.py     # Performance analytics computation
├── deployment_engine.py    # MT5 backtesting + deployment with rollback
├── sprint_manager.py       # Sprint planning and tracking
├── strategy_innovation.py  # Strategy variant generation
├── reports/                # JSON report output directory
│   ├── latest.json         # Most recent full report
│   ├── analytics.json      # Analytics-only report
│   └── historical/         # Archived reports
└── templates/              # Report templates (optional)
```

## File Descriptions

### run.py — Full Cycle Runner
The main entry point that orchestrates the complete research cycle. It calls
each module in sequence:
1. `data_collect()` — Gathers recent trade data from the SQLite database
2. `analytics()` — Runs analytics_engine to compute all KPIs
3. `innovate()` — Runs strategy_innovation to generate new variants
4. `deploy()` — Runs deployment_engine to backtest and deploy improvements
5. `report()` — Writes the final report JSON to `reports/`

### analytics_engine.py — Analytics Computation
Performs comprehensive performance analysis on all bot data:
- Win rate per bot and per pair
- Profit factor (gross profit / gross loss)
- Sharpe ratio (risk-adjusted return)
- Maximum drawdown (peak-to-trough decline)
- Session analysis (performance by trading session: Asian, European, US)
- Per-pair KPIs (average trade duration, average pips per trade, etc.)
- Account-level aggregate metrics
- Time-series performance trends

### deployment_engine.py — Backtesting and Deployment
Manages the lifecycle of strategy improvements:
1. **Backtest on MT5** — Sends proposed strategy changes to MT5 for historical
   backtesting
2. **Evaluate** — Compares backtest results against current live performance
3. **Deploy** — If backtest shows improvement, deploys the change to live bots
4. **Rollback** — If deployed change causes degradation, automatically rolls back
   to the previous version
5. **Logging** — All deployments and rollbacks are logged for audit

### sprint_manager.py — Sprint Tracking
Manages development sprints for the research division:
- Create sprints with start/end dates
- Add sprint items (research tasks, strategy changes, bug fixes)
- Track item status (planned, in progress, completed, blocked)
- Generate sprint summary reports
- Historical sprint data for process improvement

### strategy_innovation.py — Strategy Variant Generation
Generates new strategy variants by:
- Parameter mutation (adjusting indicator periods, thresholds, lot sizes)
- Combining existing strategies
- Adding new indicator signals
- Session-based modifications
- Risk parameter adjustments
Each variant is scored and the top candidates are sent to the deployment engine
for backtesting.

## Cron Schedule

- **Frequency:** Every 4 hours
- **Hermes Job ID:** 37931b893b53
- **Typical Schedule:** Runs at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
  (system local time)
- **Duration:** Usually completes within 5-15 minutes depending on data volume
  and backtest complexity
- **Status Monitoring:** The Hermes cron system tracks execution status. Failed
  runs are logged and can be retried manually.

## How to Run Manually

```bash
# Navigate to project root (where research_division/ lives)
cd /path/to/project

# Run the full cycle
python research_division/run.py

# Run individual modules for debugging
python research_division/analytics_engine.py
python research_division/strategy_innovation.py
python research_division/deployment_engine.py
python research_division/sprint_manager.py
```

After manual run, check `research_division/reports/latest.json` for output.

## Analytics KPIs Computed

### Per-Bot Metrics
| KPI              | Description                                      |
|------------------|--------------------------------------------------|
| Win Rate         | Percentage of profitable trades                   |
| Profit Factor    | Gross profit divided by gross loss                |
| Sharpe Ratio     | Risk-adjusted return measure                      |
| Max Drawdown     | Largest peak-to-trough decline (%)                |
| Avg Trade Duration| Average length of open trades                    |
| Total Trades     | Count of all trades in period                     |
| Net Profit       | Total P&L in account currency                     |
| Avg Pips/Trade   | Average pip gain/loss per trade                   |

### Session Analysis
- **Asian Session:** Performance during Tokyo hours
- **European Session:** Performance during London hours
- **US Session:** Performance during New York hours
- **Session Overlap:** Performance during overlapping sessions (e.g., London-NY)

### Per-Pair Analysis
- Performance broken down by each of the 9 traded pairs
- Correlation analysis between pairs
- Volatility measures per pair
- Best/worst performing pairs by strategy

## API Endpoints

The backend exposes three endpoints for accessing research data:

| Endpoint                          | Method | Description                      |
|-----------------------------------|--------|----------------------------------|
| `/api/research/division-status`   | GET    | Current research division status |
| `/api/research/report`            | GET    | Latest full research report      |
| `/api/research/insights`          | GET    | Key insights from analysis       |

These are consumed by the dashboard Analytics section and by Notion for
published reports.

## Known Fixed Bugs History

### Bug 1: Drawdown at 5412% (Fixed)
- **Issue:** The analytics engine was computing drawdown based on cumulative
  profit rather than equity curve, resulting in an absurd 5412% drawdown figure.
- **Fix:** Rewrote drawdown calculation to use peak-to-trough equity curve with
  proper reset logic at account reset boundaries.

### Bug 2: Duration Parsing Broken (Fixed)
- **Issue:** Trade duration parsing failed when trades spanned midnight UTC,
  producing negative or NaN duration values that corrupted all analytics.
- **Fix:** Implemented proper datetime handling with timezone-aware arithmetic
  and midnight-crossing logic.

### Bug 3: Deployment Key Mismatch (Fixed)
- **Issue:** The deployment engine had a key mismatch between the strategy
  variant identifiers used by strategy_innovation.py and those expected by
  deployment_engine.py. This caused deployment failures and phantom rollbacks.
- **Fix:** Unified the key naming convention across both modules with a shared
  constants file. Added validation checks before deployment.

## Reports

Reports are stored as JSON files in `research_division/reports/`:
- **latest.json:** Always contains the most recent full cycle report
- **analytics.json:** Analytics-only output (no innovation/deployment data)
- **historical/:** Archived reports with timestamps for trend analysis

Report JSON structure includes:
- `timestamp`: When the report was generated
- `cycle_duration`: How long the cycle took
- `analytics`: All computed KPIs broken down by bot, pair, and session
- `innovations`: Strategy variants generated (if any)
- `deployments`: Deployments attempted and their outcomes
- `sprint_updates`: Current sprint status
- `issues`: Any warnings or errors encountered
