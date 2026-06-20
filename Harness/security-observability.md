# AGENTX Security & Observability — Complete Reference

> Defense-in-depth: Google OAuth, credential isolation, audit trails, AIOps anomaly detection, SRE health monitoring, and Research Division reporting.

---

## 1. Security Architecture

### Authentication Layers
| Layer           | Mechanism                  | Purpose                          |
|----------------|----------------------------|----------------------------------|
| User Auth      | Google OAuth 2.0           | Primary user login               |
| Code Access    | AGX-XXXX-YYYY codes        | Invite-only account creation      |
| Dev Access     | Dev-login endpoint         | Development/testing bypass        |
| API Auth       | JWT (Bearer token)         | All authenticated requests        |
| Service-to-service | HMAC-SHA256 API key   | MT5 Bridge ↔ AGENTX core          |

### Google OAuth 2.0 Flow
```
User → Click "Login" → Google Consent → Auth Code → /api/v1/auth/callback → JWT
```
- JWT issued: 24-hour expiry.
- Refresh: Auto-refresh on expiry (refresh token stored server-side).
- Scopes: `openid email profile` — minimal access principle.

### Access Codes
- Format: `AGX-XXXX-YYYY` (16-char alphanumeric, 2 groups).
- Configurable max uses (default 5) and expiry (default 48h).
- One-time use per code instance.
- Stored hashed (bcrypt) in database — plaintext never persisted after generation.
- Admin-only generation endpoint.

### Session Management
| Property        | Value                    |
|----------------|--------------------------|
| Storage        | Redis `session:{token}`  |
| TTL            | 24 hours                 |
| Invalidation   | Logout → Redis delete    |
| Max sessions/user | 5 (configurable)      |
| Rate limiting  | 100 req/min per session  |

**Dev-login restrictions:**
- Only available in `AGENTX_ENV=development`.
- Uses pre-configured dev credentials (no Google redirect).
- Logs all dev-login events to audit log.
- Not accessible from production Cloudflare tunnel.

---

## 2. Credential Storage

### Primary: Windows Credential Manager (WinCM)
- Credentials stored under `AGENTX/{service}/{key}` namespace.
- Accessed via `credentialmanager` Python library (Windows API).
- All credential reads logged to `audit.jsonl`.
- Migration from config files → WinCM via `make migrate-creds`.

### Fallback: AES-GCM Encrypted File
- Used when WinCM is unavailable (non-Windows test environments).
- File: `credentials.enc` (AES-256-GCM encrypted).
- Encryption key from `AGENTX_ENCRYPTION_KEY` environment variable.
- Auto-decrypt on service startup, memory-only during runtime.

**What is stored?**
| Category         | Credentials                              |
|-----------------|------------------------------------------|
| Database        | PostgreSQL password, Redis password      |
| External APIs   | Google OAuth secret, Notion token, Telegram token, Polymarket key |
| Trading         | MT5 account passwords (per account ID)   |
| JWT             | JWT signing secret (256-bit)             |

---

## 3. Audit Logging

All sensitive operations are logged to `audit.jsonl` (structured JSONL format).

### Audited Event Categories
| Category              | Events                                                     |
|-----------------------|------------------------------------------------------------|
| Authentication        | login, logout, dev-login, code-redeem, code-generate       |
| Credential Access     | credential-read, credential-write, credential-migrate      |
| Deployments           | deploy, rollback, verify-pass, verify-fail                 |
| Configuration Changes | settings-update, bot-create, bot-update, bot-delete        |
| Trading Operations    | bot-start, bot-stop, circuit-breaker-trigger, trade-reject |
| Research Division     | sprint-start, sprint-complete, insight-generated           |
| Security Events       | failed-login, rate-limit-hit, invalid-token, anomaly-detected |

### Audit Log Format
```json
{
  "timestamp": "2026-06-20T10:30:00.000Z",
  "action": "credential_read",
  "user": "admin",
  "resource": "AGENTX/postgres/password",
  "result": "success",
  "source_ip": "192.168.1.100",
  "session_id": "sess_abc123",
  "details": {}
}
```

### Audit Log Management
- Location: `logs/audit.jsonl`
- Rotation: Daily, compressed (gzip), retained 90 days.
- Search: `grep '"action":"deploy"' logs/audit.jsonl`
- Integrity: SHA-256 hash of each day's log file stored in PostgreSQL audit schema.

---

## 4. GitGuard & GitHub Secret Scanning

### GitGuard (Pre-Commit)
- Scans staged files for credential patterns before `git commit`.
- Patterns detected:
  - API keys (`sk-...`, `api_key`, `apikey`)
  - Passwords (`password:`, `passwd:`, `pwd=`)
  - Tokens (`token:`, `bearer:`, `secret:`)
  - Private keys (`-----BEGIN.*PRIVATE KEY-----`)
  - Connection strings (`postgresql://`, `redis://`)
- **Action:** Blocks commit if secrets detected, displays warning with file/lint.
- **Bypass:** `git commit --no-verify` (logged for audit).

### GitHub Secret Scanning
- Enabled on repository via GitHub Security tab.
- Scans entire commit history for known credential patterns.
- Alerts sent to repository admin on detection.
- Auto-revoke partner patterns (AWS, GitHub tokens) when feasible.

---

## 5. AgentOps Observability

Logging framework for all agent actions — decisions, failures, and metrics.

### Decision Logging
Every bot trade signal is logged with full context:
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
  },
  "session": "overlap",
  "bot_id": "bot_001"
}
```

### Failure Logging
All errors, rejections, and exceptions:
```json
{
  "agent": "MACD",
  "failure": "order_rejected",
  "reason": "insufficient_margin",
  "symbol": "EURUSD",
  "timestamp": "2026-06-20T10:31:00Z",
  "recovery_action": "reduce_position_size",
  "stack_trace": "..."
}
```

### Metrics Logging
Continuous metrics streamed to `metrics` schema in PostgreSQL:
| Metric              | Type    | Collection Interval |
|--------------------|---------|-------------------|
| trades_per_hour    | Counter | Per trade          |
| win_rate           | Gauge   | Rolling 50 trades  |
| profit_factor      | Gauge   | Daily window       |
| avg_trade_duration | Gauge   | Per trade closed   |
| latency_ms         | Histogram| Per bridge call   |
| error_rate         | Gauge   | Per 5 min window   |

---

## 6. AIOps Anomaly Detection

Six detectors run every 5 minutes. All alerts sent to Telegram + audit log.

### Detector 1: P&L Velocity
Monitors rate of P&L change. Triggers on >2σ deviation from 24h rolling mean.

### Detector 2: Win Rate Collapse
Monitors rolling 20-trade win rate per strategy. Triggers on <30% or <50% of strategy baseline.

### Detector 3: Consecutive Losses
Monitors losing streaks. Triggers on >5 consecutive losses or >30% of historical max.

### Detector 4: Silence
Monitors time since last trade signal. Triggers on >4h without signal (configurable per strategy).

### Detector 5: Frequency Spike
Monitors trade frequency. Triggers on >4σ from 7-day rolling mean.

### Detector 6: Risk Drift
Monitors position size distribution. Triggers on position >3× median size.

### Stale Log Detection
Alert if no new log entries in any monitored component for >10 minutes.

### Excess Error Detection
Alert if error rate exceeds 10% of total operations in any 5-minute window.

---

## 7. SRE Health Monitoring

Framework runs every 2 minutes checking:

| Component     | Check                          | Alert Threshold         |
|--------------|--------------------------------|------------------------|
| PostgreSQL   | Connection pool, query latency | Latency > 1s           |
| Redis        | Ping, memory, key count        | Memory > 80%           |
| MT5 Bridge   | Port reachable, tick latency   | Latency > 500ms        |
| Disk         | Free space                     | < 10% free             |
| RAM          | Available memory               | < 500 MB               |
| Bots         | Active count, error state      | > 8 bots, any error    |
| Ollama       | Model loaded, inference time   | Optional — warn only   |
| Sentiment    | Cache TTL, freshness           | Stale entries > 30 min |

**Circuit Breaker:** 3 consecutive health failures → safe mode → all bots stop.

---

## 8. Research Division Reporting

| Report            | Frequency       | Recipients         | Content                                    |
|-------------------|-----------------|--------------------|--------------------------------------------|
| Daily Brief       | Every sprint (4h) | Dashboard         | Market conditions, bot performance, insights |
| Sprint Summary    | 08:00, 20:00 HKT | User              | Sprint plan + review                        |
| Anomaly Report    | On detection    | Telegram           | Detected anomaly + recommended action       |
| Weekly Performance| Every Monday    | User               | Strategy P&L, win rates, drawdowns          |
| Audit Summary     | Daily           | Admin only         | All security-relevant events from past 24h  |

All reports generated by Research Division agents, stored in `research.reports` table.
