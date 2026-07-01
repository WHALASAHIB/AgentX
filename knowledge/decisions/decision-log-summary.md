# Decision Log Summary — AgentX Trading System

> **Source**: data/decision_log.json (905 entries), strategy_council/mistakes_ledger.json

## Structure

Each decision log entry follows this schema:
```json
{
  "id": "dec_<timestamp>_<hash>",
  "timestamp": "ISO-8601 UTC",
  "agent_id": "Bot/system identifier",
  "agent_name": "Human-readable name",
  "action": "What happened",
  "detail": "Context and parameters",
  "outcome": "success | error | pending",
  "metadata": {}
}
```

## Key Events Log

### Bot Startups (2026-06-25, Initial Fleet Deployment)

All bots started on the $9,930 balance mt5-demo account. This was the initial launch of the multi-pair system.

| Time (UTC) | Bot | Action | Detail | Outcome |
|------------|-----|--------|--------|---------|
| 04:28:15 | Bollinger_AUDUSD | Bot Started | symbol=AUDUSD strategy=bollinger balance=9930.79 | success |
| 04:28:16 | MACD_AUDUSD | Bot Started | symbol=AUDUSD strategy=macd balance=9930.79 | success |
| 04:28:17 | MACD_GBPUSD | Bot Started | symbol=GBPUSD strategy=macd balance=9930.79 | success |
| 04:28:18 | Bollinger_NZDUSD | Bot Started | symbol=NZDUSD strategy=bollinger balance=9930.06 | success |
| 04:28:19 | MACD_NZDUSD | Bot Started | symbol=NZDUSD strategy=macd balance=9930.06 | success |
| 04:28:20 | MACD_USDCAD | Bot Started | symbol=USDCAD strategy=macd balance=9930.06 | success |
| 04:28:21 | Bollinger_USDCHF | Bot Started | symbol=USDCHF strategy=bollinger balance=9929.33 | success |
| 04:28:22 | MACD_USDCHF | Bot Started | symbol=USDCHF strategy=macd balance=9929.33 | success |
| 04:28:23 | MACD_USDJPY | Bot Started | symbol=USDJPY strategy=macd balance=9929.33 | success |
| 04:28:24 | SMA_USDJPY | Bot Started | symbol=USDJPY strategy=sma balance=9929.33 | success |

### Initial Trades (2026-06-25)

| Time (UTC) | Bot | Action | Detail | Outcome |
|------------|-----|--------|--------|---------|
| 04:28:17 | Bollinger_AUDUSD | SELL OPEN | 0.29 AUDUSD @ 0.69019 ticket=481417995 | success |
| 04:28:21 | Bollinger_NZDUSD | SELL OPEN | 0.29 NZDUSD @ 0.56461 ticket=481418027 | success |
| 04:28:25 | MACD_USDJPY | BUY OPEN | 0.69 USDJPY @ 161.71800 ticket=481418051 | success |
| 05:07:23 | Bollinger_USDCHF | SELL OPEN | 0.24 USDCHF @ 0.81110 ticket=481436111 | success |
| 05:13:21 | MACD_NZDUSD | BUY OPEN | 0.3 NZDUSD @ 0.56474 ticket=481438833 | success |
| 05:15:18 | MACD_AUDUSD | BUY OPEN | 0.3 AUDUSD @ 0.68997 ticket=481439428 | success |
| 07:04:19 | MACD_GBPUSD | SELL OPEN | 0.2 GBPUSD @ 1.31776 ticket=481503549 | success |

### Trade Failures (2026-06-25, 07:32-07:56 UTC)

A cascade of order failures occurred as the system repeatedly tried and failed to execute trades:

| Time (UTC) | Bot | Action | Detail | Outcome |
|------------|-----|--------|--------|---------|
| 07:32:25 | MACD_NZDUSD | SELL FAILED | 0.29 NZDUSD | error |
| 07:32:28 | Bollinger_USDCHF | SELL FAILED | 0.01 USDCHF | error |
| 07:33:21 | Bollinger_AUDUSD | BUY FAILED | 0.01 AUDUSD | error |
| 07:33:27 | MACD_NZDUSD | SELL FAILED | 0.01 NZDUSD | error |
| 07:33:30 | Bollinger_USDCHF | SELL FAILED | 0.01 USDCHF | error |

**... continuing for ~24 minutes of repeated failures** (7:34-7:56 UTC, ~50 total failures)

These failures represent the system repeatedly retrying trades that MT5 was rejecting. The fix was the **Unified Bot Runner** (single MT5 connection) which eliminated the process contention causing these failures.

### Bot Restarts (2026-06-28)

| Time (UTC) | Bot | Action | Detail | Outcome |
|------------|-----|--------|--------|---------|
| 00:21:17 | Bollinger_AUDUSD | Bot Started | Bot 'Bollinger_AUDUSD' started (PID 7128) | success |
| 00:33:15 | Bollinger_NZDUSD | Bot Started | Bot 'Bollinger_NZDUSD' started (PID 11848) | success |
| 16:59:49 | Bollinger_NZDUSD | Bot Started | Bot 'Bollinger_NZDUSD' started (PID 14592) | success |
| 16:59:51 | MACD_AUDUSD | Bot Started | Bot 'MACD_AUDUSD' started (PID 3216) | success |
| 17:01:45 | Bollinger_AUDUSD | Bot Stopped | Bot 'Bollinger_AUDUSD' stopped (PID 14592) | success |
| 17:01:46 | Bollinger_AUDUSD | Bot Started | Bot 'Bollinger_AUDUSD' started (PID 12324) | success |

### Propfirm Pass Deployment (2026-07-01)

| Time (UTC) | Bot | Action | Detail | Outcome |
|------------|-----|--------|--------|---------|
| 01:01:25 | Propfirm_pass_EURUSD | Bot Started | Bot 'Propfirm_pass_EURUSD' started (PID 2060) | success |

## Major Incidents (from mistakes_ledger.json)

### Incident 1: Multi-Pair MACD on FTMO (2026-06-25)
- **PnL**: -$793.03
- **Root cause**: Multi-pair MACD bots continued trading on FTMO account during REDUCE risk state, accumulating -$356 combined losses. USDJPY positions closed by FTMO risk desk for additional -$436.
- **Fix**: Kill multi-pair bots on FTMO account when risk state is REDUCE
- **Prevention rule**: When risk state is REDUCE and drawdown > 8%, ALL bots on FTMO must be paused

### Incident 2: Stale PID Lock (2026-06-27)
- **Root cause**: Propfirm Pass bot ran on Saturday, detected weekend, created stale PID lock (16408) that would have expired ~Jun 29, but process exited without placing trades
- **Fix**: Clean stale PID locks on startup
- **Prevention rule**: Bot launch script must check and clean stale PID locks before acquiring new lock

### Incident 3: FTMO Risk Desk Intervention (2026-06-26)
- **PnL**: -$455.00
- **Root cause**: 8.5 lots USDJPY (5.0+2.5+1.0 at magic 0) opened at 19:10-19:17 UTC, closed by FTMO risk desk at 19:32 UTC (15-22 min hold). Drawdown reached 9.23%.
- **Fix**: Emergency stop must trigger at 8% static DD, not 8% trailing DD
- **Prevention rule**: Risk supervisor must track BOTH trailing and static drawdown

### Incident 4: 7-Day FTMO Review (2026-06-23 to 2026-06-26)
- **PnL**: -$860.11
- **Details**: 106 trades total. MACD multi-pair bots went 0-for-23 (0% WR, -$356). Propfirm pass variants: 36 trades, -$100.76, 15.3% WR. Only positive contributor: Gold Phoenix (2 trades, +$39.96, 100% WR).
