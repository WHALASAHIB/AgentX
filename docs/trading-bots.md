# Trading Bots Reference

## Overview

The trading system runs 23 trading bots across multiple strategies and currency
pairs. Bots are managed as background processes on the Windows host machine
(10.10.10.1). Each bot connects to MetaTrader 5 via the bridge client to receive
market data and execute trades.

## Bot Architecture

Each bot follows a common pattern:
1. **Initialization** — Load config for assigned pair(s), connect to MT5 bridge,
   initialize strategy indicators.
2. **Market Loop** — Continuously poll for new market data, apply strategy logic,
   generate signals (buy/sell/hold).
3. **Execution** — Submit the trade to MT5 via bridge client, log the result.
4. **Reporting** — Periodically report status, open positions, and P&L to backend.

## Bot Directory Structure

```
bots/
├── active_bots/              # Per-pair strategy scripts
│   ├── AUDUSD/   (macd, bollinger)
│   ├── BTCUSD/   (macd, goldphoenix, sma)
│   ├── EURUSD/   (macd, goldphoenix)
│   ├── GBPUSD/   (macd, goldphoenix)
│   ├── NZDUSD/   (macd, bollinger)
│   ├── USDCAD/   (macd, goldphoenix)
│   ├── USDCHF/   (macd, bollinger)
│   ├── USDJPY/   (macd, sma)
│   └── XAUUSD/   (macd, goldphoenix)
├── logs/                     # All bot log output
├── multi_symbol_bot.py       # Main multi-pair bot
├── gold_bot_v3.py            # Legacy: gold bot (PID 1724)
├── gold_phoenix_bot.py       # Legacy: gold phoenix (PID 10672)
├── scalping_youtube_goldstrategy.py  # Legacy: scalping (PID 1916)
└── streaming_bot_v3.py       # Legacy: streaming bot (PID 12800)
```

## Complete Bot Inventory (23 Bots)

| # | Strategy    | Pairs                                    | PID   | Type       |
|---|-------------|------------------------------------------|-------|------------|
| 1 | GoldBot     | XAUUSD (legacy)                          | 1724  | Legacy     |
| 2 | GoldPhoenix | XAUUSD (legacy)                          | 10672 | Legacy     |
| 3 | Scalping    | XAUUSD (legacy)                          | 1916  | Legacy     |
| 4 | Streaming   | Multi-pair (legacy)                      | 12800 | Legacy     |
| 5-13 | MACD     | AUDUSD, BTCUSD, EURUSD, GBPUSD, NZDUSD, | 2456  | Multi-pair |
|   |             | USDCAD, USDCHF, USDJPY, XAUUSD (9 pairs)|       |            |
|14-18 | GoldPhoenix| BTCUSD, EURUSD, GBPUSD, USDCAD, XAUUSD   | 2348  | Multi-pair |
|19-21 | Bollinger  | AUDUSD, NZDUSD, USDCHF (3 pairs)         | 7888  | Multi-pair |
|22-23 | SMA        | BTCUSD, USDJPY (2 pairs)                 | 7524  | Multi-pair |

Multi-pair bots share one PID per strategy: MACD (2456) manages 9 pairs,
GoldPhoenix (2348) manages 5, Bollinger (7888) manages 3, SMA (7524) manages 2.

## Legacy Bots

### Gold Bot (gold_bot_v3.py, PID 1724)
Legacy XAUUSD bot. Older strategy superseded by multi-pair implementations but
still running for comparative performance tracking.

### Gold Phoenix (gold_phoenix_bot.py, PID 10672)
Legacy GoldPhoenix on XAUUSD only. Newer version runs 5 pairs under PID 2348.

### Scalping Bot (scalping_youtube_goldstrategy.py, PID 1916)
XAUUSD scalping strategy inspired by a public YouTube gold trading strategy.
Uses short timeframes and quick exits.

### Streaming Bot (streaming_bot_v3.py, PID 12800)
Multi-pair streaming bot processing real-time market data. Third version.

## Multi-Pair Bot System

Bots under `bots/active_bots/` are organized by currency pair, each containing
`run_{strategy}.py` scripts loaded by the main multi-symbol bot or run standalone.

### Strategy Scripts
- **MACD** (`run_macd.py`): Moving Average Convergence Divergence. 9 pairs,
  PID 2456. Most widely deployed strategy.
- **GoldPhoenix** (`run_goldphoenix.py`): Proprietary strategy. 5 pairs, PID 2348.
- **Bollinger** (`run_bollinger.py`): Bollinger Bands-based. 3 pairs, PID 7888.
- **SMA** (`run_sma.py`): Simple Moving Average crossover. 2 pairs, PID 7524.

### Per-Pair Configuration
Each pair directory may include:
- `config.json` — Lot size, stop loss, take profit
- `indicators.json` — Indicator parameters per pair
- `session.json` — Allowed trading session hours

## How to Add a New Bot/Strategy

1. Create strategy script in `bots/` (e.g., `bots/new_strategy.py`)
2. For multi-pair, create `bots/active_bots/{PAIR}/run_new_strategy.py` per pair
3. Add config files (config.json, indicators.json) in pair directories
4. Start: `python bots/new_strategy.py` (test foreground) then background
5. Verify on dashboard Bots section
6. Update PIDs in bot tracking

## How to Restart a Bot

### Individual Bot
```bash
kill <PID>
python bots/<bot_script>.py &
```
Verify with `tasklist | grep python` or dashboard Bots section.

### Multi-Pair Bot (e.g., MACD PID 2456)
```bash
kill 2456
python bots/active_bots/run_macd_all.py &
```
Verify all pairs appear active on the dashboard.

## Bot Log Locations

All logs written to `bots/logs/`:
```
bots/logs/
├── gold_bot.log      ├── gold_phoenix.log
├── scalping_bot.log  ├── streaming_bot.log
├── macd.log          ├── goldphoenix.log
├── bollinger.log     ├── sma.log
└── multi_symbol.log
```
Each contains timestamped entries for trades, errors, connection status, and
indicator signals. Logs rotate automatically (size-based or daily).

## Common Issues and Fixes

### Bot Not Responding
**Symptom:** Bot shows offline on dashboard.
**Fix:** Check `tasklist | grep python`. Restart if dead.

### Bridge Connection Lost
**Symptom:** All bots show connection errors.
**Fix:** Restart bridge: `python backend/bridge_client.py`

### Stale Process (Phantom PID)
**Symptom:** Dashboard shows running but bot isn't trading.
**Fix:** Kill old PID and restart. PID may be stale from a previous session.

### High CPU Usage
**Symptom:** System sluggish, bots lagging.
**Fix:** Check for runaway processes. Multi-pair bots (especially MACD with
9 pairs) can consume significant CPU. Restart if needed.

## Monitoring Bots

- **Dashboard:** Bots section shows status, PID, uptime, last trade
- **Task Manager:** `tasklist | grep python` on Windows host
- **Log Files:** Check `bots/logs/` for errors
- **Backend API:** `/api/bots/status` returns all bot states
