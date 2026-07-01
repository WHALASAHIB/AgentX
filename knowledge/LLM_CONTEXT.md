# LLM Context — AgentX Trading System Knowledge Bundle

You are an AI assistant specialized in the **AgentX Algorithmic Trading Platform**. This knowledge bundle provides the complete context for understanding, operating, and extending the system.

## What Is AgentX?

AgentX is a full-stack algorithmic trading web platform — a web cockpit for monitoring, controlling, and analyzing live trading bots in real-time across multiple MT5 accounts. It runs on a Windows VM and serves via Cloudflare Tunnel at **https://inventra.website**.

## Architecture at a Glance

```
Browser ──► Cloudflare (CDN/SSL) ──► Cloudflare Tunnel ──► FastAPI Backend (:8005)
                                                              │
                                                       ┌──────┴──────┐
                                                       │             │
                                                     SQLite      JSON Store
                                                       │
                                                  MT5 Bridge (:5000)
                                                       │
                                                  MetaTrader 5
                                                       │
                                        mt5-demo | ftmo-10k | ftmo-100k
```

## Key Facts

| Property | Value |
|----------|-------|
| Domain | inventra.website |
| Backend (HTTP) | 0.0.0.0:8005 — FastAPI + Uvicorn |
| Backend (HTTPS) | 0.0.0.0:8443 — Self-signed SSL |
| MT5 Bridge | 127.0.0.1:5000 |
| Tunnel ID | da2cf48b |
| Cloudflare Zone ID | 7d776e863660c45279fdf615ab52a90e |
| Active Accounts | mt5-demo ($97K), ftmo-10k ($9K), ftmo-100k ($100K) |
| Python | 3.12.10 |
| Bridge Mode | Single-account (no auto-cycling) |

## Active Bot Fleet (11 entries, ~15 individual bots)

### Bollinger (mean reversion)
- AUDUSD magic=780007
- NZDUSD magic=780008
- USDCHF magic=780005

### MACD (crossover)
- AUDUSD magic=888223
- GBPUSD magic=780003
- NZDUSD magic=780008
- USDCAD magic=780006
- USDCHF magic=780005
- USDJPY magic=780004

### SMA (crossover)
- USDJPY magic=780004

### Volatility Breakout
- XAUUSD magic=200500

### Propfirm Pass
- EURUSD (VWAP mean reversion, US Open 13:00-15:00 UTC)

### DISABLED
- BTCUSD MACD (not available on MetaQuotes-Demo)
- BTCUSD SMA (not available on MetaQuotes-Demo)

## FTMO Challenge Rules
- FTMO 1-Phase $10K: 10% profit target ($1,000), 4% daily DD, 8% total DD
- FTMO 100K: standard FTMO rules
- **Daily loss limit**: 5% of initial balance
- **Max drawdown**: 10% of initial balance (static, NOT trailing)
- Risk supervisor tracks BOTH trailing and static DD
- Emergency stop at 8% static DD

## Key Architecture Decisions
1. **Single-account bridge mode** — coordinator refreshes only the active account to avoid MT5 hangs
2. **Unified Bot Runner** — all strategies in ONE process with ONE MT5 connection (eliminates terminal contention)
3. **Cloudflare Tunnel** — no open inbound ports; tunnel routes inventra.website → localhost:8005
4. **Scanner blocker** — .php, /wp-, /xmlrpc requests return 404
5. **Frontend SPA** — 12 pre-rendered HTML pages served by FastAPI catch-all routing

## Knowledge Files
- `concepts/infrastructure.md` — Full system architecture details
- `concepts/ftmo-rules.md` — FTMO challenge rules and strategy
- `strategies/active-bots-overview.md` — All bot configurations
- `bots/deployment-runbook.md` — How bots are deployed
- `decisions/decision-log-summary.md` — Historical decisions and incidents
- `api/backend-endpoints.md` — Complete API reference
- `README.md` — Human-readable overview

## Hard Rules (from BASELINE.md)
1. NEVER change backend port, bind, or route structure without Commander approval
2. NEVER modify tunnel config without Commander approval
3. NEVER delete pre-rendered .html files from frontend/public/
4. ALWAYS restart both backends after app.py changes
5. ALWAYS verify via curl after restart
6. NEVER push credentials to GitHub
