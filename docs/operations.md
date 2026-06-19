# Operations & Troubleshooting

## Overview

This document covers day-to-day operations for the algorithmic trading system:
starting and stopping services, monitoring bot health, running research cycles,
and troubleshooting common issues.

## How to Start/Stop the Backend

The backend runs on the VM (10.10.10.100) using FastAPI via uvicorn on port 8005.

### Starting
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8005 --reload
# Or as daemon:
nohup uvicorn backend.app:app --host 0.0.0.0 --port 8005 > backend.log 2>&1 &
```

### Stopping
```bash
ps aux | grep uvicorn   # find PID
kill <PID>              # graceful
kill -9 <PID>           # force if needed
```

### Verifying
```bash
curl http://localhost:8005/api/health
```

## How to Check All 23 Bots Are Running

### Via Terminal (Windows Host)
```bash
tasklist | grep python
# Expected: 8+ processes for gold_bot (1724), gold_phoenix (10672),
# scalping (1916), streaming (12800), MACD (2456),
# GoldPhoenix multi (2348), Bollinger (7888), SMA (7524)
```

### Via Dashboard
Open the **Bots** section. Verify all 23 bots show green "online" status.

## How to Restart Individual Bots

### Via Dashboard (Recommended)
Open Bots section, find the bot, click "Restart".

### Via Terminal
```bash
kill <PID>
cd /path/to/bots && python <bot_script>.py &
tasklist | grep python   # verify
```

### Multi-Pair Bot Restart
```bash
kill 2456                # Kill MACD (all 9 pairs)
python bots/active_bots/run_macd_all.py &
```

## How to Check Bridge Connection

The bridge (`backend/bridge_client.py`) connects the backend to MT5 on port 5000.

```bash
tasklist | grep bridge               # process running?
netstat -an | grep 5000              # port listening?
curl http://localhost:8005/api/health # includes bridge status
```

### Bridge Fixes
1. Ensure MT5 is open and logged in on the host
2. Restart bridge: `python backend/bridge_client.py`
3. Verify network: `ping 10.10.10.1` (VM→host), `ping 10.10.10.100` (host→VM)
4. Check Windows Firewall for port 5000

## How to Run the Research Division

### Manual Run
```bash
cd /path/to/project && python research_division/run.py
```

### Verify Results
```bash
cat research_division/reports/latest.json
curl http://localhost:8005/api/research/report   # via API
```

The research cycle runs every 4 hours via Hermes cron (job_id: 37931b893b53).
Typical completion time: 5-15 minutes.

## How to Check Recent Trades

### Via Dashboard
Open **TradeJournal**, filter by bot/pair/date.

### Via API
```bash
curl http://localhost:8005/api/trades/recent
```

### Via Database
```bash
sqlite3 backend/db/trading.db "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 20;"
```

## Troubleshooting

### Empty Dashboard Boxes
**Symptom:** Sections load but show empty content areas, charts don't render.

**Causes:** Chart.js CDN unreachable (no internet on VM), no data in DB (bridge down),
API returning empty responses.

**Checks:**
```bash
curl -I https://cdn.jsdelivr.net/npm/chart.js
sqlite3 backend/db/trading.db "SELECT COUNT(*) FROM trades;"
curl http://localhost:8005/api/health
```

**Fixes:** Download Chart.js locally and update index.html. Restart bridge if DB empty.

### Bridge Not Connecting
**Symptom:** "Bridge Disconnected" on dashboard, all bots showing errors.

**Checks:** Is MT5 running? Is bridge_client.py running? Port 5000 open?
Can VM reach host (ping 10.10.10.1)?

**Fixes:** Open MT5 and log in. Restart bridge_client.py. Check Windows Firewall.
Restart VM network adapter if needed.

### Backend Won't Restart (Phantom PID)
**Symptom:** "Address already in use" on port 8005. Stale PID.

**Fix:**
```bash
netstat -ano | findstr :8005   # find the real PID
taskkill /PID <PID> /F         # force kill
# Wait 5-10 seconds, then restart
```

### Bot Shows Online But Not Trading
**Symptom:** Green status, no recent trades.

**Checks:** Examine bot log (`bots/logs/<bot>.log`), verify bridge connection,
check MT5 for alerts, restart the individual bot.

## Emergency Procedures

### Emergency Stop (All Trading)
Use when system is behaving erratically or risk limits are breached.
1. Dashboard: Click "Emergency Stop" in CommandCenter
2. API: `curl -X POST http://localhost:8005/api/bots/stop-all`
3. Kill all processes: `taskkill /IM python.exe /F`
4. Close MT5 positions manually if needed

### System Recovery After Crash
1. Start MT5 on host and log in
2. Start bridge: `python backend/bridge_client.py &`
3. Start backend: `uvicorn backend.app:app --host 0.0.0.0 --port 8005`
4. Start bots via dashboard or API
5. Verify all 23 bots are online
6. Check recent trades for anomalies

## Log Files

| Service          | Log Path                                      |
|------------------|-----------------------------------------------|
| Backend          | backend/logs/ or console output               |
| Bots             | bots/logs/*.log                               |
| Bridge           | backend/bridge_client.log                     |
| Research Reports | research_division/reports/latest.json         |
| Dashboard        | Browser console (client-side)                 |

## Quick Reference

```bash
curl http://localhost:8005/api/health               # backend status
tasklist | grep python                               # bot processes
netstat -an | grep 5000                              # bridge port
netstat -an | grep 8005                              # backend port
python research_division/run.py                      # run research
cat research_division/reports/latest.json            # research report
curl http://localhost:8005/api/trades/recent         # recent trades
taskkill /IM python.exe /F                           # emergency kill
```
