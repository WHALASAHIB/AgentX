# AGENTX Cron Automation — Complete Reference

> All scheduled jobs managed by the Hermes cron daemon.  
> Timezone: HKT (UTC+8) unless otherwise noted.  
> Logs: stored in `cron/` directory, rotated by SRE Engine.

---

## 1. SRE Engine

**Schedule:** Every 2 minutes (`*/2 * * * *`)  
**Script:** `cron/sre_engine.py`  
**Priority:** 🔴 Critical

### Tasks
1. **Resource Governance**
   - Count active bots (alert if > 8).
   - Check available RAM (alert if < 500 MB).
   - Check MT5 connection count (alert if > 5).
   - Check Redis memory usage (alert if > 80%).
   - Check disk free space (alert if < 10%).

2. **Health Checks**
   - PostgreSQL: Ping test, connection pool health.
   - Redis: Ping test, memory usage, eviction rate.
   - MT5 Bridge: Port 5000 connectivity, tick stream latency.
   - Ollama (optional): Model loaded, inference speed.

3. **Circuit Breaker Management**
   - If 3+ consecutive failures: enter **Safe Mode** (halt all bots).
   - If all checks pass 2 consecutive cycles: exit Safe Mode.
   - Log all transitions to `audit.jsonl`.

4. **Log Rotation**
   - Rotate logs > size threshold (100MB per file).
   - Compress and archive logs > 24h.
   - Delete logs > retention period.

5. **System Alerts**
   - Send critical alerts to Telegram immediately.
   - Send warning alerts grouped (max 1 per 5 min per component).

### Log Format
```
2026-06-20 10:30:00 | SRE | HEALTH | OK | pg=ok redis=ok bridge=ok ram=2048MB bots=4
2026-06-20 10:32:00 | SRE | RESOURCE | OK | bots=4/8 ram=2048MB connections=2/5
2026-06-20 10:34:00 | SRE | CIRCUIT_BREAKER | SAFE_MODE_ENTER | reason: 3 consecutive health failures
```

---

## 2. Research Full Cycle

**Schedule:** Every 4 hours (`0 */4 * * *`) — runs at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 HKT  
**Script:** `cron/research_full_cycle.py`  
**Priority:** 🟡 High

### Pipeline (5 Agents)

#### Agent 1: Collector
- Fetch latest news from Google News RSS (20 articles per symbol query).
- Query Polymarket sentiment data.
- Aggregate any available market commentary.
- Store raw articles in `research.raw_articles` table.

#### Agent 2: Analyst
- Score article sentiment (positive/negative/neutral).
- Generate composite sentiment per symbol.
- Identify emerging themes and market narratives.
- Create insights stored in `research.insights` table.

#### Agent 3: Sprint Master
- Review current sprint backlog from `research.sprints` table.
- Assign tasks to Research Division agents.
- Track progress against sprint goals.
- Generate sprint status summary.

#### Agent 4: Innovator
- Review strategy performance metrics.
- Identify optimization opportunities.
- Generate strategy improvement proposals.
- Run backtest simulations for proposed changes.

#### Agent 5: Deployer
- Review and prioritize improvement proposals.
- Apply approved strategy parameter changes.
- Run verification tests.
- Log deployment outcome.

### Output
- Insights stored in `research.insights`.
- Sprint records in `research.sprints`.
- Strategy proposals stored as actionable items.
- All cycle steps logged to `cron/research_cycle.log`.

---

## 3. Sprint Planning

**Schedule:** Daily at 08:00 HKT (`0 8 * * *`)  
**Script:** `cron/sprint_planning.py`  
**Priority:** 🟡 High

### Tasks
1. **Backlog Selection**
   - Review open insights from Research Division.
   - Prioritize by urgency score (market impact × confidence).
   - Select top 3-5 items for today's sprint.

2. **Daily Standup**
   - Report yesterday's results (trades, P&L, errors).
   - State today's goals (selected backlog items).
   - Flag blockers (MT5 issues, resource constraints, market conditions).

3. **Bot Assignment**
   - Assign backlog items to specific bots/strategies where applicable.
   - Set sprint duration (default 4 hours, can extend to next planning cycle).

### Output
- Sprint record created in `research.sprints` with `phase: planning`.
- Tasks assigned to agents with `status: pending`.
- Notification sent via Telegram if configured.

---

## 4. Sprint Review

**Schedule:** Daily at 20:00 HKT (`0 20 * * *`)  
**Script:** `cron/sprint_review.py`  
**Priority:** 🟡 High

### Tasks
1. **Progress Assessment**
   - Review completed vs pending sprint tasks.
   - Calculate completion rate (percentage).
   - Evaluate sprint artifacts (backtest results, strategy changes).

2. **Performance Review**
   - Compare sprint performance to previous sprints.
   - Identify strategies that exceeded or underperformed expectations.
   - Note any anomalies detected by AIOps during sprint.

3. **Lessons Learned**
   - Document what worked well.
   - Document what didn't work.
   - Suggest process improvements for next sprint.

4. **Sprint Close**
   - Mark current sprint as `completed` in `research.sprints`.
   - Archive sprint artifacts.
   - Prepare summary for Daily Brief report.

### Output
- Sprint marked `completed` with score.
- Lessons learned stored in `research.lessons` table.
- Report generated at `cron/reports/sprint_review_{date}.md`.

---

## 5. Notion Auto-Push

**Schedule:** Every 10 minutes (`*/10 * * * *`)  
**Script:** `cron/notion_auto_push.py`  
**Priority:** 🟢 Normal

### Tasks
1. **Query Closed Trades**
   - Query `trades` table WHERE `status = 'closed'` AND `notion_pushed = false`.
   - Collect trades closed since last push cycle.

2. **Format for Notion**
   - Map trade fields to Notion database properties.
   - Include: timestamp, symbol, strategy, direction, volume, entry/exit prices, P&L, tags, notes.

3. **Push to Notion**
   - POST to Notion API `/v1/pages` (parent database: Trade Log).
   - Handle rate limits (3 req/s max, auto-backoff).
   - Retry up to 3 times on failure.

4. **Mark as Pushed**
   - Update `trades.notion_pushed = true` on success.
   - Log push status (success/failure + reason).

5. **Monthly Performance Update (if applicable)**
   - If date crosses month boundary, push aggregate monthly stats to Monthly Performance database.

### Queue
- If Notion API is down, items queue in Redis `notion:push_queue`.
- Queue processed next cycle (low-priority, no alert on delay).

---

## 6. Sentiment Cache TTL

**Schedule:** Every 30 minutes (`*/30 * * * *`)  
**Script:** `cron/sentiment_refresh.py`  
**Priority:** 🟢 Normal

### Tasks
1. **Check Cache Freshness**
   - Scan Redis `sentiment:{symbol}` keys.
   - Check `updated_at` timestamp.
   - Flag entries older than 30 minutes as stale.

2. **Refresh Stale Entries**
   - For each stale symbol:
     - Fetch news sentiment via RSS (brief, 5 articles).
     - Query Polymarket current probabilities.
     - Compute composite score (60% news, 20% Polymarket, 20% recent P&L context).
   - Update Redis with new score and TTL reset.

3. **Symbols Monitored**
   - XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD, EURJPY, GBPJPY

4. **Logging**
   - Log refresh success/failure per symbol.
   - Track cache hit rate metric.

---

## 7. AIOps Watch

**Schedule:** Every 5 minutes (`*/5 * * * *`)  
**Script:** `cron/aiops_watch.py`  
**Priority:** 🟡 High

### Tasks
1. **Run All 6 Detectors**
   - Detector 1: P&L Velocity — check rolling stats.
   - Detector 2: Win Rate Collapse — per strategy rolling window.
   - Detector 3: Consecutive Losses — per bot streak counter.
   - Detector 4: Silence — check last signal timestamp.
   - Detector 5: Frequency Spike — check trades/hour rate.
   - Detector 6: Risk Drift — check position size distribution.

2. **Additional Checks**
   - Stale Log Detection: last log entry per component > 10 min?
   - Excess Error Detection: error rate > 10% in last 5 min?

3. **Alerting**
   - Any detector trigger → log to `audit.jsonl`.
   - Critical anomalies → immediate Telegram alert.
   - Warning anomalies → aggregate, send max 1 per 5 min.

4. **Action on Trigger**
   - Anomaly documented in `metrics.aiops_alerts` table.
   - If pattern matches known recovery procedure, auto-execute.
   - Otherwise, flag for next Sprint Planning cycle.

### Alert Severity
| Severity | Detectors                        | Action                     |
|----------|----------------------------------|----------------------------|
| Critical | P&L Velocity, Consecutive Losses | Halt bot, alert Telegram   |
| Warning  | Win Rate, Silence, Frequency     | Investigate, flag for review |
| Info     | Risk Drift, Stale Log, Excess Err| Log, review if persistent |

---

## 8. Hermes Cron Jobs Reference

All cron entries registered in `~/.hermes/cron.yaml`:

```yaml
cron:
  - name: sre_engine
    schedule: "*/2 * * * *"
    command: "python cron/sre_engine.py"
    enabled: true
    timeout: 120

  - name: research_full_cycle
    schedule: "0 */4 * * *"
    command: "python cron/research_full_cycle.py"
    enabled: true
    timeout: 600

  - name: sprint_planning
    schedule: "0 8 * * *"
    command: "python cron/sprint_planning.py"
    enabled: true
    timeout: 300

  - name: sprint_review
    schedule: "0 20 * * *"
    command: "python cron/sprint_review.py"
    enabled: true
    timeout: 300

  - name: notion_auto_push
    schedule: "*/10 * * * *"
    command: "python cron/notion_auto_push.py"
    enabled: true
    timeout: 120

  - name: sentiment_refresh
    schedule: "*/30 * * * *"
    command: "python cron/sentiment_refresh.py"
    enabled: true
    timeout: 60

  - name: aiops_watch
    schedule: "*/5 * * * *"
    command: "python cron/aiops_watch.py"
    enabled: true
    timeout: 60
```

### Hermes Cron Commands

| Command                           | Description                        |
|----------------------------------|------------------------------------|
| `hermes cron list`               | List all registered cron jobs      |
| `hermes cron enable <name>`      | Enable a cron job                 |
| `hermes cron disable <name>`     | Disable a cron job                |
| `hermes cron run <name>`         | Manually trigger a cron job now   |
| `hermes cron log <name>`         | View last 50 lines of cron log    |
| `hermes cron status`             | Show running/stopped status       |
