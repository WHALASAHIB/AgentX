# 🏛️ AGENTX INFRASTRUCTURE BASELINE — IMMUTABLE

> **Last verified:** 2026-07-01 03:45 HKT
> **Status:** ✅ ALL SYSTEMS OPERATIONAL (3 accounts)
> **This document is the single source of truth for all infrastructure. Do NOT modify any setting below without explicit Commander approval.**

---

## 1. DOMAIN & NETWORKING

| Property | Value |
|----------|-------|
| **Domain** | `inventra.website` |
| **HTTP** | `http://inventra.website` |
| **HTTPS** | `https://inventra.website` |
| **SSL Mode** | Cloudflare Universal SSL — **Flexible** |
| **HTTPS Redirect** | Always Use HTTPS — **Enabled** |
| **CDN** | Cloudflare (proxied — orange cloud) |
| **Cloudflare Zone ID** | `7d776e863660c45279fdf615ab52a90e` |
| **Cloudflare Tunnel ID** | `da2cf48b-5b1f-4e28-9b7c-8d7bce6ec1a6` |
| **Tunnel Config** | `~/.cloudflared/config.yml` |
| **Tunnel Credentials** | `~/.cloudflared/credentials.json` |
| **Tunnel Token** | `[REDACTED — stored in ~/.cloudflared/credentials.json]` |
| **Tunnel Status** | ✅ **Running** (PID varies, check `tasklist | grep cloudflared`) |
| **Tunnel Routes** | `inventra.website` + `www.inventra.website` → `http://localhost:8005` |

---

## 2. BACKEND SERVERS

### Primary (HTTP)
| Property | Value |
|----------|-------|
| **Port** | `8005` |
| **Bind** | `0.0.0.0:8005` |
| **Command** | `cd /c/Trading && python -m uvicorn backend.app:app --host 0.0.0.0 --port 8005` |
| **Framework** | FastAPI + Uvicorn |
| **Python** | 3.12.10 |
| **Status** | ✅ **Running** (verify: `curl http://localhost:8005/api/health`) |

### Secure (HTTPS — Self-Signed)
| Property | Value |
|----------|-------|
| **Port** | `8443` |
| **Bind** | `0.0.0.0:8443` |
| **SSL Cert** | `/c/Trading/backend/ssl/cert.pem` |
| **SSL Key** | `/c/Trading/backend/ssl/key.pem` |
| **Command** | `cd /c/Trading && python -m uvicorn backend.app:app --host 0.0.0.0 --port 8443 --ssl-certfile backend/ssl/cert.pem --ssl-keyfile backend/ssl/key.pem` |
| **Status** | ✅ **Running** (verify: `curl -sk https://localhost:8443/api/health`) |

---

## 3. MT5 BRIDGE

| Property | Value |
|----------|-------|
| **URL** | `http://127.0.0.1:5000` |
| **Status** | ✅ **Connected** |
| **Health Endpoint** | `http://127.0.0.1:5000/health` |

### Connected Accounts

| ID | Login | Server | Balance | Connected |
|----|-------|--------|---------|-----------|
| `mt5-demo` | 5051185832 | MetaQuotes-Demo | ~$97,107.53 | ✅ Active |
| `ftmo-10k` | 1513767391 | FTMO-Demo | $9,076.69 | When switched |
| `ftmo-100k` | 1513845007 | FTMO-Demo | $100,000.00 | When switched |

**Note:** Coordinator runs in single-account mode. Only the active account is refreshed.
Switch accounts via the website's Switch button — terminal restarts with chosen account.

---

## 4. FRONTEND

| Property | Value |
|----------|-------|
| **Type** | Next.js SPA (pre-built, no source) |
| **Location** | `/c/Trading/frontend/public/` |
| **Entry Point** | `index.html` (served at `/`) |
| **Static Assets** | `_next/static/` mounted at `/_next` |
| **Page Files** | 12 pre-rendered `.html` files in `frontend/public/` |

### All Routes

| Route | File | Title | Size |
|-------|------|-------|------|
| `/` | `index.html` | Live Command Center | 7.4KB |
| `/portfolio` | `portfolio.html` | Portfolio Dashboard | 9.3KB |
| `/trades` | `trades.html` | Trade Journal | 8.7KB |
| `/backtesting` | `backtesting.html` | Backtesting Lab | 9.4KB |
| `/bots` | `bots.html` | Bot Control Room | 7.3KB |
| `/scripts` | `scripts.html` | Script Editor | 7.1KB |
| `/ai` | `ai.html` | AI Orchestrator | 7.7KB |
| `/accounts` | `accounts.html` | Account Manager | 7.2KB |
| `/analytics` | `analytics.html` | Analytics Suite | 7.4KB |
| `/settings` | `settings.html` | Settings | 8.4KB |
| `/signin` | `signin.html` | Sign In | 6.0KB |
| `/signup` | `signup.html` | Create Account | 6.1KB |

### Serving Logic (in `backend/app.py` → `serve_frontend()`)
1. Block `api/` and `_next/` paths (handled by other routes)
2. Try exact file match (`FRONTEND_DIR / path`)
3. Try with `.html` extension (`FRONTEND_DIR / path + ".html"`)
4. Try without trailing slash + `.html`
5. Fallback to `index.html` (SPA catch-all)

---

## 5. API ENDPOINTS (All Working)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | System health + bridge status |
| `/api/auth/me` | GET | Current user (dev mode: returns Commander) |
| `/api/auth/signin` | POST | Dev-mode signin (accepts any credentials) |
| `/api/auth/signup` | POST | Dev-mode signup |
| `/api/auth/logout` | POST | Logout |
| `/api/auth/login` | GET | Google OAuth login |
| `/api/auth/dev-login` | POST | Dev login bypass |
| `/api/accounts` | GET | List accounts |
| `/api/stats` | GET | Trading statistics |
| `/api/positions` | GET | Open positions |
| `/api/bots` | GET | Registered bots |
| `/api/bridge/accounts/{id}/history` | GET | Trade history |
| `/api/bridge/accounts/{id}/equity` | GET | Equity curve |
| `/api/bridge/accounts/{id}/stats` | GET | Account stats |
| `/api/bridge/accounts/{id}/tick/{symbol}` | GET | Live tick |
| `/api/bots/{name}/start` | POST | Start bot |
| `/api/bots/{name}/stop` | POST | Stop bot |
| `/api/editor/files` | GET | Script files |
| `/api/orchestrator/agents` | GET | AI agent status |
| `/api/ws/{path}` | WS | WebSocket proxy → bridge |
| `/api/settings/system` | GET | System info |
| `/api/events` | GET | SSE event stream |

---

## 6. PATCHES APPLIED (Critical Changes)

| # | Patch | File | Date |
|---|-------|------|------|
| 1 | API URL: `http://localhost:8000` → relative `/api/` | All 13 JS chunks | 2026-06-23 |
| 2 | WebSocket URL: `ws://localhost:5000` → `/api/ws` | All 13 JS chunks | 2026-06-23 |
| 3 | WebSocket proxy: added `/api/ws/{path}` endpoint | `backend/app.py` | 2026-06-23 |
| 4 | Auth endpoints: added `/api/auth/me`, `/signin`, `/signup` | `backend/app.py` | 2026-06-23 |
| 5 | Scanner blocker: .php/wp-/xmlrpc → 404 | `backend/app.py` | 2026-06-23 |
| 6 | Page routing: serve `{path}.html` before `index.html` fallback | `backend/app.py` | 2026-06-23 |
| 7 | Cloudflare SSL: toggled Universal SSL off→on to force issue | Cloudflare Dashboard | 2026-06-23 |
| 8 | Coordinator: single-account mode (no auto-cycling) | `bridge/subprocess_coordinator.py` | 2026-06-30 |
| 9 | Set-active API endpoint on bridge | `bridge/server.py` | 2026-06-30 |
| 10 | Switch-terminal updates coordinator active account | `bridge/server.py` | 2026-06-30 |
| 11 | Coordinator created synchronously (race fix) | `bridge/mt5_manager.py` | 2026-06-30 |
| 12 | Lifespan sets initial active to mt5-demo | `bridge/server.py` | 2026-06-30 |

---

## 7. KNOWN ISSUES (Non-Blocking)

| # | Issue | Severity | ETA |
|---|-------|----------|-----|
| 1 | No process supervision (backend not auto-restarted on crash) | 🟡 Medium | TBD |
| 2 | Redis disconnected (sessions/caching not available) | 🟡 Medium | TBD |
| 3 | JSON file store (62MB, not ACID) instead of SQLite | 🟡 Medium | TBD |
| 4 | Backend bound to `0.0.0.0` (public, not localhost-only) | 🟡 Medium | TBD |
| 5 | CORS `allow_origins=["*"]` — should be restricted | 🟢 Low | TBD |
| 6 | No mobile responsive CSS | 🟢 Low | TBD |

---

## 8. HARD RULES

1. **NEVER change `backend/app.py` port, bind, or route structure** without Commander approval
2. **NEVER modify tunnel config** (`~/.cloudflared/config.yml`) without Commander approval
3. **NEVER delete pre-rendered `.html` files** from `frontend/public/`
4. **ALWAYS restart both backends after `app.py` changes** (HTTP + HTTPS)
5. **ALWAYS verify via `curl` after restart** before declaring done
6. **NEVER push credentials** to GitHub (`.env.*` is gitignored)

---

*This baseline was established on 2026-06-23. All settings above are verified working.*
