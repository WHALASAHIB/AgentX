# Active Bots Overview — AgentX Trading System

> **Source**: bots/unified_bot_runner.py (BOT_ROSTER), bots/active_bots/ discovery,
>   bots/multi_symbol_bot.py, backend/app.py (_discover_bots)

## Fleet Summary

**15 active bot entries** across **8 symbols**, using **5 strategy types**.
All bots connect via MetaTrader 5 on the active account (mt5-demo, ftmo-10k, or ftmo-100k).

## Unified Bot Runner (Single Process)

The `bots/unified_bot_runner.py` manages **11 bot pairs** in ONE process with ONE MT5 connection:

| # | Symbol | Strategy | Magic | Max Entries/Day | Status |
|---|--------|----------|-------|-----------------|--------|
| 1 | AUDUSD | bollinger | 780007 | 2 | Active |
| 2 | NZDUSD | bollinger | 780008 | 2 | Active |
| 3 | USDCHF | bollinger | 780005 | 2 | Active |
| 4 | AUDUSD | macd | 888223 | 2 | Active |
| 5 | GBPUSD | macd | 780003 | 2 | Active |
| 6 | NZDUSD | macd | 780008 | 2 | Active |
| 7 | USDCAD | macd | 780006 | 2 | Active |
| 8 | USDCHF | macd | 780005 | 2 | Active |
| 9 | USDJPY | macd | 780004 | 2 | Active |
| 10 | XAUUSD | volatilitybreakout | 200500 | 2 | Active |
| 11 | USDJPY | sma | 780004 | 2 | Active |

## Individual Active Bot Scripts (Backend Discovery)

The backend discovers **15 run scripts** via `bots/active_bots/<PAIR>/run_<strategy>.py`:

| # | Bot Name | File | Pair | Strategy | Status |
|---|----------|------|------|----------|--------|
| 1 | Bollinger_AUDUSD | active_bots/AUDUSD/run_bollinger.py | AUDUSD | Bollinger Bands | Active |
| 2 | MACD_AUDUSD | active_bots/AUDUSD/run_macd.py | AUDUSD | MACD Crossover | Active |
| 3 | MACD_GBPUSD | active_bots/GBPUSD/run_macd.py | GBPUSD | MACD Crossover | Active |
| 4 | Bollinger_NZDUSD | active_bots/NZDUSD/run_bollinger.py | NZDUSD | Bollinger Bands | Active |
| 5 | MACD_NZDUSD | active_bots/NZDUSD/run_macd.py | NZDUSD | MACD Crossover | Active |
| 6 | MACD_USDCAD | active_bots/USDCAD/run_macd.py | USDCAD | MACD Crossover | Active |
| 7 | Bollinger_USDCHF | active_bots/USDCHF/run_bollinger.py | USDCHF | Bollinger Bands | Active |
| 8 | MACD_USDCHF | active_bots/USDCHF/run_macd.py | USDCHF | MACD Crossover | Active |
| 9 | MACD_USDJPY | active_bots/USDJPY/run_macd.py | USDJPY | MACD Crossover | Active |
| 10 | SMA_USDJPY | active_bots/USDJPY/run_sma.py | USDJPY | SMA Crossover | Active |
| 11 | MACD_XAUUSD | active_bots/XAUUSD/run_macd.py | XAUUSD | MACD Crossover | Active |
| 12 | VolatilityBreakout_XAUUSD | active_bots/XAUUSD/run_volatility_breakout.py | XAUUSD | Volatility Breakout | Active |
| 13 | PropfirmPass_EURUSD | active_bots/EURUSD/run_propfirm_pass.py | EURUSD | VWAP Mean Reversion | Active |
| 14 | MACD_BTCUSD | active_bots/BTCUSD/run_macd.py | BTCUSD | MACD Crossover | **DISABLED** |
| 15 | SMA_BTCUSD | active_bots/BTCUSD/run_sma.py | BTCUSD | SMA Crossover | **DISABLED** |

**Note**: BTCUSD bots are disabled because MetaQuotes-Demo server does not serve crypto symbols (symbol_select fails with IPC error).

## Strategy Details

### Bollinger Bands (Mean Reversion)
- **Symbols**: AUDUSD, NZDUSD, USDCHF
- **Pattern**: Mean reversion — buys near lower band, sells near upper band
- **Magic numbers**: 780005, 780007, 780008
- **Source strategy files**: backtester/active_strategies/<SYMBOL>/bollinger_bands.py

### MACD Crossover (Trend Following)
- **Symbols**: AUDUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY, XAUUSD
- **Pattern**: MACD line crosses signal line for entry direction
- **Magic numbers**: 780003-780008, 888223
- **Source strategy files**: backtester/active_strategies/<SYMBOL>/macd_crossover.py

### SMA Crossover
- **Symbols**: USDJPY
- **Pattern**: Simple Moving Average crossover
- **Magic number**: 780004
- **Source strategy files**: backtester/active_strategies/<SYMBOL>/sma_crossover.py

### Volatility Breakout
- **Symbols**: XAUUSD
- **Pattern**: Bollinger Squeeze / volatility contraction — waits for low-volatility squeeze, then trades the breakout direction
- **Magic number**: 200500
- **Source**: bots/volatility_breakout_bot.py (standalone, not multi_symbol_bot)
- **Check interval**: 10 seconds

### Propfirm Pass (VWAP Mean Reversion)
- **Symbols**: EURUSD
- **Pattern**: VWAP deviation + rejection candle at US Open (13:00-15:00 UTC)
- **Timeframe**: 1-minute entry, 5-minute rejection candle
- **SL/TP**: 12 pips / 24 pips (1:2 RR)
- **Risk**: 0.5% per trade, max 2 trades/day
- **Source**: bots/active_bots/EURUSD/run_propfirm_pass.py -> propfirm_pass_bot.py

## Bot Execution Architecture

Each run script is a thin wrapper that calls either:
- `multi_symbol_bot.py` main() (for MACD, Bollinger, SMA) — passes --symbol and --strategy args
- Strategy-specific main() (for VolatilityBreakout, PropfirmPass — standalone bots)

The backend auto-starts all discovered scripts on boot via the lifespan hook.

## Performance Snapshot (from research division report)

From latest report (2026-07-01):
- **Total trades**: 65
- **Overall win rate**: 40%
- **Profit factor**: 9.01
- **Net profit**: $9,076.69
- **Max drawdown**: 1.0%

Per-pair (partial data):
- **AUDUSD**: 9 trades, 10% WR, -$199.05, 6 consecutive losses
- **GBPUSD**: 6 trades, 50% WR, -$26.31
- **NZDUSD**: 9 trades (win rate not shown)
