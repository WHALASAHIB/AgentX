# AGENTX DevOps Pipeline — Complete Reference

> Stack: Python 3.12+ | FastAPI | PostgreSQL 16 | Redis 7 | MetaTrader 5  
> CI/CD: Git-based, triggered by `make deploy` or git push  
> Monitoring: SRE Engine, AIOps, AgentOps, DevSecOps

---

## 1. SRE Engine

Framework for site reliability — runs every 2 minutes via cron.

### Resource Governance
| Check              | Threshold              | Action                               |
|--------------------|------------------------|--------------------------------------|
| Active bot count   | > 8                    | Prevent new bot starts, alert        |
| Available RAM      | < 500 MB               | Halt trading, GC trigger, alert      |
| MT5 connections    | > 5                    | Reject new connections, alert        |
| Redis memory       | > 80% of maxmemory     | Evict non-critical keys, alert       |
| Disk space         | < 10% free             | Rotate logs, archive, alert          |

### Health Checks
- **PostgreSQL:** Connection pool health, query latency > 1s alert.
- **Redis:** Ping latency, memory usage, key count.
- **MT5 Bridge:** Port 5000 reachable, tick latency < 500ms.
- **Ollama (optional):** Model loaded, inference latency.
- **Notion API:** Push queue depth, last successful push.
- **Sentiment Cache:** TTL check, stale entries.

### Circuit Breaker
- System-level breaker: if 3+ health checks fail consecutively, enter safe mode.
- Safe mode: all bots stop, only manual restart allowed.
- Auto-recovery: re-check every 2 min, exit safe mode after all checks pass 2 consecutive cycles.

### Log Rotation
| Pattern          | Retention | Compression |
|-----------------|-----------|-------------|
| `logs/*.log`    | 7 days    | gzip        |
| `logs/*.json`   | 30 days   | gzip        |
| `cron/*.log`    | 14 days   | gzip        |
| `debug/*.log`   | 3 days    | none        |

---

## 2. CI/CD Pipeline

### Flow: `git pull → validate → backup → deploy → verify → rollback`

#### Step 1: git pull
```bash
git pull origin main
```
Auto-stash local changes if conflicts.

#### Step 2: validate
```bash
make validate
# Runs: syntax check, import check, config validation, DB migration check
```

#### Step 3: backup
```bash
make backup
# Creates: timestamped backup of current code + DB dump + bot state
# Location: backups/{timestamp}/
```

#### Step 4: deploy
```bash
make deploy
# Stops affected bots, installs deps, restarts service, restarts bots
```

#### Step 5: verify
```bash
make verify
# Health check, bot status check, trade execution smoke test
```

#### Step 6: rollback (on failure)
```bash
make rollback
# Restores from latest backup, reverts code, restarts service
```

### Rollback triggers:
- Verify step returns non-zero exit code.
- SRE Engine detects degradation within 5 minutes of deploy.
- Manual intervention (`make rollback`).

---

## 3. DevSecOps

### Credential Migration
Raw passwords/API keys in config files → Windows Credential Manager (WinCM).

**Migration process:**
1. `make migrate-creds` — scans all config files for credential patterns.
2. Extracts credentials, stores in WinCM under `AGENTX/{service}/{key}` namespace.
3. Replaces raw values with `credential://AGENTX/{service}/{key}` references.
4. Original config files backed up to `backups/pre-migration/`.

### Windows Credential Manager (WinCM) Integration
| Credential           | WinCM Target Name                          |
|----------------------|--------------------------------------------|
| PostgreSQL password  | `AGENTX/postgres/password`                 |
| Redis password       | `AGENTX/redis/password`                    |
| JWT secret           | `AGENTX/auth/jwt_secret`                   |
| Google OAuth client  | `AGENTX/google/oauth_client_secret`        |
| Notion API token     | `AGENTX/notion/api_token`                  |
| MT5 account password | `AGENTX/mt5/{account_id}/password`         |
| Telegram bot token   | `AGENTX/telegram/bot_token`                |
| Polymarket API key   | `AGENTX/polymarket/api_key`                |

### Audit Logging
All sensitive operations logged to `audit.jsonl`:

```json
{"timestamp":"2026-06-20T10:00:00Z","action":"credential_access","user":"admin","resource":"AGENTX/postgres/password","result":"success"}
{"timestamp":"2026-06-20T10:01:00Z","action":"deploy","user":"admin","commit":"abc123","result":"success"}
{"timestamp":"2026-06-20T10:02:00Z","action":"config_change","user":"admin","config":"settings.yaml","diff":"+risk_percent: 0.20"}
```

**Audited actions:**
- Deployments and rollbacks
- Credential access and migration
- Config changes
- User login/logout
- Bot create/delete/start/stop
- Circuit breaker triggers
- Research Division actions

---

## 4. AgentOps

Decision, failure, and metrics logging for all agent actions.

### Decision Logging
```json
{
  "agent": "GoldPhoenix",
  "action": "open_long",
  "symbol": "XAUUSD",
  "timestamp": "2026-06-20T10:30:00Z",
  "decision_factors": {
    "ema_aligned": true,
    "rsi_value": 32.5,
    "atr_value": 18.2,
    "sentiment_score": 62.4,
    "ftmo_compliant": true
  }
}
```

### Failure Logging
```json
{
  "agent": "MACD",
  "failure": "order_rejected",
  "reason": "insufficient_margin",
  "symbol": "EURUSD",
  "timestamp": "2026-06-20T10:31:00Z",
  "recovery_action": "reduce_position_size"
}
```

### Metrics Logging
| Metric              | Source          | Aggregation |
|--------------------|----------------|-------------|
| trades_per_hour    | Per strategy   | Sum         |
| win_rate           | Per strategy   | Rolling 50  |
| profit_factor      | Per bot        | Window      |
| avg_trade_duration | Per strategy   | Mean        |
| latency_ms         | Bridge → Trade | P50/P95     |
| error_rate         | Per component  | Rate/min    |

---

## 5. AIOps — Anomaly Detection

Six anomaly detectors run every 5 minutes. Each generates an alert when triggered.

### Detector 1: P&L Velocity
- **Signal:** Rate of P&L change per minute.
- **Threshold:** >2σ from 24-hour rolling mean.
- **Trigger:** Sharp P&L drop.
- **Action:** Halt affected bots, send alert.

### Detector 2: Win Rate Collapse
- **Signal:** Rolling 20-trade win rate.
- **Threshold:** < 30% (or < 50% of strategy baseline).
- **Trigger:** Win rate collapse on any strategy.
- **Action:** Investigate strategy, circuit breaker on affected bot(s).

### Detector 3: Consecutive Losses
- **Signal:** Consecutive losing trades.
- **Threshold:** > 5 (or > 30% of historical max).
- **Trigger:** Losing streak exceeds threshold.
- **Action:** Circuit breaker, strategy review.

### Detector 4: Silence
- **Signal:** Time since last trade signal.
- **Threshold:** > 4 hours (configurable per strategy).
- **Trigger:** Strategy stopped producing signals.
- **Action:** Check MT5 connection, bot status, market conditions.

### Detector 5: Frequency Spike
- **Signal:** Trade frequency per hour.
- **Threshold:** > 4σ from 7-day rolling mean.
- **Trigger:** Abnormal increase in trading activity.
- **Action:** Check for signal logic bug, halt if confirmed.

### Detector 6: Risk Drift
- **Signal:** Position size vs historical distribution.
- **Threshold:** Position > 3× median position size.
- **Trigger:** Bot attempted outsized trade.
- **Action:** Log violation, review params, circuit breaker.

### Additional Detectors
- **Stale Log Detection:** Check last log entry timestamp > 10 minutes.
- **Excess Error Detection:** Error rate > 10% of total operations in 5-minute window.

---

## 6. Resource Rules (Hard Limits)

| Resource           | Limit | Enforcement            |
|--------------------|-------|------------------------|
| Max active bots    | 8     | SRE Engine blocks >8   |
| Min free RAM       | 500MB | SRE Engine halts       |
| Max MT5 connections| 5     | Bridge rejects         |
| Max PostgreSQL conns | 20  | Connection pool capped |
| Max Redis memory   | 512MB | Maxmemory-policy allkeys-lru |
| Max backtest runs  | 5 concurrent | Queue beyond 5 |
| Max trades/day (FTMO)| See bot-strategies.md | Per account type |

---

## 7. Makefile Targets Reference

| Target            | Description                                    |
|-------------------|------------------------------------------------|
| `help`           | List all targets with descriptions             |
| `install`        | Install Python dependencies (pip -r)            |
| `validate`       | Syntax + import + config + migration check      |
| `backup`         | Full backup (code + DB + state)                 |
| `deploy`         | Full deploy cycle (stop → install → start)      |
| `verify`         | Post-deploy verification suite                  |
| `rollback`       | Restore previous deployment                     |
| `start`          | Start the AGENTX service                        |
| `stop`           | Stop the AGENTX service                         |
| `restart`        | Stop + start                                    |
| `test`           | Run test suite (pytest)                         |
| `lint`           | Run linters (ruff, mypy)                        |
| `clean`          | Clean cache, logs, temp files                   |
| `migrate-creds`  | Migrate credentials to WinCM                   |
| `logs`           | Tail all logs                                  |
| `status`         | Service status overview                         |
| `psql`           | Open PostgreSQL console                         |
| `redis-cli`      | Open Redis console                              |
| `shell`          | Open Python shell with AGENTX context           |
| `db-upgrade`     | Run Alembic DB migrations                       |
| `db-downgrade`   | Rollback last DB migration                      |
