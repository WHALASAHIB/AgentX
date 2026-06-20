# AGENTX Integrations — Complete Reference

> Every external service AGENTX connects to, with configuration details, authentication methods, and data flow.

---

## 1. MetaTrader 5 (Bridge)

| Property          | Value                      |
|------------------|----------------------------|
| Protocol         | TCP (custom binary)        |
| Port             | 5000                       |
| Authentication   | API key (HMAC-SHA256)      |
| Max connections  | 5 (hard limit)             |
| Tick latency     | < 500ms (alert if exceeded)|
| Data flow        | Bidirectional              |

**Bridge operations:**
- Account login/logout
- Symbol tick subscription
- Order placement/modification/deletion
- Position and history retrieval
- Account info (balance, equity, margin)
- Server time and market status

**Configuration (`config.yaml`):**
```yaml
mt5:
  bridge_host: "127.0.0.1"
  bridge_port: 5000
  connection_timeout: 10
  heartbeat_interval: 5
  reconnect_delay: 2
  max_retries: 3
```

---

## 2. PostgreSQL

| Property       | Value                        |
|---------------|------------------------------|
| Version       | 16+                          |
| Host          | localhost (default)          |
| Port          | 5432                         |
| Database      | agentx                       |
| Auth          | Windows Credential Manager   |
| Pool size     | 20                           |

**Schemas:**
| Schema     | Tables                                    |
|------------|-------------------------------------------|
| `public`   | accounts, bots, trades, positions, settings |
| `research` | insights, reports, sprints, agents        |
| `audit`    | audit_log, credential_log, deploy_log     |
| `metrics`  | agent_metrics, decision_log, failure_log  |

**Key tables:**
- `accounts` — Trading accounts (FTMO, personal), credentials reference.
- `bots` — Bot instances, strategy config, magic number mapping.
- `trades` — All trades with tags, notes, strategy_id, FTMO flags.
- `positions` — Current open positions (synced with MT5 bridge).
- `insights` — Research Division generated insights.
- `sprints` — Sprint records, phase tracking, task assignments.
- `audit_log` — Timestamped audit trail of all sensitive operations.

**Connection string pattern:**
```
postgresql://agentx@localhost:5432/agentx?sslmode=require
```
Password retrieved from WinCM key `AGENTX/postgres/password`.

---

## 3. Redis

| Property       | Value                        |
|---------------|------------------------------|
| Version       | 7+                           |
| Host          | localhost (default)          |
| Port          | 6379                         |
| Auth          | Windows Credential Manager   |
| Max memory    | 512MB                        |
| Eviction      | allkeys-lru                  |

**Use cases:**
- **Cache:** Sentiment scores (TTL 30 min), backtest results (TTL 1h), account info.
- **Pub/Sub:** Real-time tick data from MT5 bridge, SSE events to web clients.
- **State persistence:** Bot state for IPC recovery (`bot:{id}:state`), circuit breaker counters.
- **Session store:** JWT session cache, rate limiting counters.
- **Queue:** Notion push queue, sentiment refresh queue, deployment queue.

**Key namespaces:**
| Key Pattern                     | Purpose                         | TTL      |
|--------------------------------|---------------------------------|----------|
| `bot:{id}:state`               | Bot state (strategy, positions) | None     |
| `bot:{id}:circuit_breaker`     | CB counter, timestamps          | 1h       |
| `sentiment:{symbol}`           | Sentiment score                 | 30 min   |
| `backtest:{id}:result`         | Backtest result cache           | 1h       |
| `sse:events`                   | SSE event bus                   | Pub/Sub  |
| `session:{token}`              | JWT session                     | 24h      |
| `notion:push_queue`            | Trades pending Notion push      | Queue    |
| `rate_limit:{endpoint}:{user}` | Rate limit counters             | 1 min    |

---

## 4. Google OAuth

| Property        | Value                             |
|----------------|-----------------------------------|
| Auth type      | OAuth 2.0 (Authorization Code)    |
| Client ID      | Stored in `config.yaml` (env ref) |
| Client Secret  | WinCM: `AGENTX/google/oauth_client_secret` |
| Scopes         | `openid`, `email`, `profile`      |
| Redirect URI   | `https://agentx.nousresearch.com/api/v1/auth/callback` |

**Flow:**
1. User clicks "Login with Google".
2. Redirected to Google consent screen.
3. Google redirects to callback with auth code.
4. Server exchanges auth code for tokens.
5. JWT issued to user (24h expiry).
6. Refresh token stored for session extension.

**Access codes bypass OAuth:** Pre-generated codes (AGX-XXXX-YYYY) allow account creation without Google login — used for granting access to new users.

---

## 5. Notion

| Property        | Value                               |
|----------------|-------------------------------------|
| API Version    | 2022-06-28                          |
| Auth           | Internal Integration Token (WinCM)  |
| Token Key      | `AGENTX/notion/api_token`           |
| Push interval  | Every 10 minutes (Auto-Push cron)   |

**Databases:**
| Database              | Purpose                                      |
|-----------------------|----------------------------------------------|
| Trade Log             | Closed trades with all fields, tags, notes    |
| Monthly Performance   | Aggregated monthly metrics per strategy       |
| Sprint Board          | Sprint tasks, backlog items, in-progress work |
| Research Insights     | Generated insights from Research Division     |

**Trade Log properties pushed:**
- Date/Time
- Symbol
- Strategy
- Direction (Long/Short)
- Volume
- Entry Price
- Exit Price
- P&L (pips and currency)
- Tags (FTMO-safe, winning, reviewed)
- Notes
- Screenshot URL (if applicable)

---

## 6. Google News RSS

| Property        | Value                                   |
|----------------|-----------------------------------------|
| Source         | `https://news.google.com/rss/search`    |
| Frequency      | Every 4 hours (Research Collector cron) |
| Query params   | `q=XAUUSD+trading&hl=en-US&gl=US`      |
| Max articles   | 20 per query                            |

**Symbol-to-query mapping:**
| Symbol  | RSS Query                          |
|---------|-----------------------------------|
| XAUUSD  | `gold+price+trading`              |
| EURUSD  | `EURUSD+forex+analysis`           |
| GBPUSD  | `GBPUSD+sterling+forex`           |
| USDJPY  | `USDJPY+yen+forex`                |
| General | `forex+market+trading+strategy`   |

Articles are parsed, scored for sentiment, and fed to the Research Division Analyst for insight generation.

---

## 7. Polymarket API

| Property        | Value                                   |
|----------------|-----------------------------------------|
| Endpoint       | `https://clob.polymarket.com`           |
| Auth           | API key + signature (WinCM stored)      |
| Use            | Prediction market sentiment for symbols |

**Example query:**
```bash
curl "https://clob.polymarket.com/markets?tag=gold&limit=5"
```

Polymarket probabilities (e.g., "Will gold reach $2500 by July?") feed into the composite sentiment score.

---

## 8. Cloudflare

| Property        | Value                                     |
|----------------|-------------------------------------------|
| Tunnel type    | Named tunnel (cloudflared)                 |
| Tunnel name    | `agentx-prod`                              |
| Origin         | `localhost:9000`                           |
| Public URL     | `https://agentx.nousresearch.com`          |
| DNS            | Cloudflare DNS managed                     |

**Configuration (`~/.cloudflared/config.yaml`):**
```yaml
tunnel: agentx-prod
credentials-file: ~/.cloudflared/agentx-prod.json
ingress:
  - hostname: agentx.nousresearch.com
    service: http://localhost:9000
  - service: http_status:404
```

---

## 9. GitHub

| Property        | Value                                      |
|----------------|--------------------------------------------|
| Remote          | `origin` → GitHub                          |
| Branch          | `main` (production)                        |
| CI/CD           | GitHub Actions (optional, local Makefile primary) |
| GitGuard        | Secret scanning enabled                    |
| Webhook         | POST to `/api/v1/github-webhook` (optional) |

**Sync flow:**
1. Development on feature branches.
2. Merge to `main` via PR.
3. Local deployment: `git pull && make deploy`.
4. GitHub secret scanning catches any committed credentials.

---

## 10. Telegram

| Property        | Value                                     |
|----------------|-------------------------------------------|
| Bot Token      | WinCM: `AGENTX/telegram/bot_token`         |
| Chat ID        | Configured in `settings.yaml`             |
| Purposes       | SRE alerts, anomaly notifications, daily reports |

**Alert types:**
- 🚨 **Critical:** Circuit breaker triggered, system down, drawdown limit hit.
- ⚠️ **Warning:** Resource threshold approaching, anomaly detected, bridge latency high.
- ✅ **Info:** Bot started/stopped, deployment succeeded, daily P&L summary.

**Example alert format:**
```
🚨 AGENTX ALERT: Circuit Breaker Triggered
Bot: GoldPhoenix (XAUUSD)
Reason: 5 consecutive losses
Time: 2026-06-20 10:30:00 UTC
Action: Trading paused on bot_001
```

---

## 11. Ollama (Qwen2.5:14b)

| Property        | Value                        |
|----------------|-----------------------------|
| Model          | `qwen2.5:14b-instruct-q4_K_M` |
| Host           | `localhost:11434`            |
| Auth           | None (local)                 |
| Status         | Optional — graceful degraded |
| Purpose        | LLM analysis of research insights |

**Usage:**
- Research Division: Strategy improvement proposals.
- Sentiment analysis: Supplementary news interpretation.
- Insight generation: Natural language summaries of market conditions.

**Dependency:** If Ollama is unavailable, Research Division operates in data-only mode without LLM analysis.

---

## 12. Windows Credential Manager

| Property        | Value                                       |
|----------------|---------------------------------------------|
| Namespace      | `AGENTX/{service}/{key}`                    |
| Tool           | `credentialmanager` Python library           |
| Fallback       | AES-GCM encrypted `credentials.enc` file     |

**All stored credentials:**
| WinCM Key                              | Environment Equivalent  |
|----------------------------------------|------------------------|
| `AGENTX/postgres/password`            | `AGENTX_PG_PASSWORD`  |
| `AGENTX/redis/password`               | `AGENTX_REDIS_PASSWORD`|
| `AGENTX/auth/jwt_secret`              | `AGENTX_JWT_SECRET`   |
| `AGENTX/google/oauth_client_secret`   | —                     |
| `AGENTX/notion/api_token`             | —                     |
| `AGENTX/mt5/{account_id}/password`    | —                     |
| `AGENTX/telegram/bot_token`           | —                     |
| `AGENTX/polymarket/api_key`           | —                     |

---

## 13. YouTube

| Property        | Value                                      |
|----------------|--------------------------------------------|
| Source type    | Manual strategy reference                   |
| Purpose        | Reference for strategy development          |
| Channels       | Various forex/gold trading channels         |
| Integration    | Manual — strategies coded based on concepts |

YouTube is not an API integration — strategy source concepts from educational trading content are codified into the Python strategy files.
