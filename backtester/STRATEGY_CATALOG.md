# AGENTX Trading System — Strategy Catalog

> Generated: 2026-06-18
> Source: `C:\Trading\backtester\strategies\` and `C:\Trading\backtester\custom_strategies\`

---

## Table of Contents

1. [DefaultStrategy (Fallback)](#1-defaultstrategy-fallback)
2. [sma_crossover_strategy](#2-sma_crossover_strategy)
3. [macd_crossover_strategy](#3-macd_crossover_strategy)
4. [bollinger_bands_strategy](#4-bollinger_bands_strategy)
5. [EmaRsiCrossoverStrategy](#5-emarsicrossoverstrategy)
6. [GoldPhoenixStrategy](#6-goldphoenixstrategy)
7. [Test (Custom — Disabled)](#7-test-custom--disabled)

---

## 1. DefaultStrategy (Fallback)

**File:** `strategies/default.py`
**Class:** `DefaultStrategy`
**Loader status:** Fallback only — loaded if no built-in/custom strategies are found (not in `BUILTIN_MODULES` list).

### Description
Simple SMA crossover strategy — default fallback. Used as a safety net when no other strategy modules are available.

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `fast_period` | `9` | Fast SMA lookback period |
| `slow_period` | `21` | Slow SMA lookback period |

### Timeframes
Any timeframe (no session/time-specific logic).

### Indicators Used
- **SMA** (fast=9, slow=21) — simple moving averages of `close`

### Entry Logic
- **BUY** → Fast SMA crosses above Slow SMA (signal = 1)
- **SELL** → Fast SMA crosses below or equals Slow SMA (signal = -1)
- Always in a position (never flat by intent — 1 or -1 on every bar)

### Exit Logic
Signal reversal: when the signal flips from 1 to -1 (or -1 to 1), the engine closes the current position and opens a new one.

---

## 2. sma_crossover_strategy

**File:** `strategies/sma_crossover.py`
**Class:** `sma_crossover_strategy`
**Loader key:** `sma_crossover`

### Description
> **Note:** Despite its filename (`sma_crossover.py`) and class name, this strategy uses **EMA** (exponential moving average), not SMA. Docstring reads: *"EMA 9/21 crossover strategy for trend following."*

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `fast_period` | `9` | Fast EMA period |
| `slow_period` | `21` | Slow EMA period |

### Timeframes
Any timeframe.

### Indicators Used
- **EMA** (fast=9, slow=21) — exponential moving averages via `.ewm()`

### Entry Logic
- **BUY** → Fast EMA > Slow EMA (signal = 1)
- **SELL** → Fast EMA ≤ Slow EMA (signal = -1)
- Always in a position (never flat — 1 or -1 on every bar)

### Exit Logic
Signal reversal triggers exit via the engine. Identical structure to DefaultStrategy but uses EMA instead of SMA.

---

## 3. macd_crossover_strategy

**File:** `strategies/macd_crossover.py`
**Class:** `macd_crossover_strategy`
**Loader key:** `macd_crossover`

### Description
MACD crossover with histogram confirmation.

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `fast` | `12` | Fast EMA period for MACD line |
| `slow` | `26` | Slow EMA period for MACD line |
| `signal` | `9` | Signal line EMA period |

### Timeframes
Any timeframe.

### Indicators Used
- **MACD** (12, 26, 9) — MACD line, signal line, histogram

### Entry Logic
- **BUY** → MACD line crosses ABOVE the signal line (cross-up on current bar)
- **SELL** → MACD line crosses BELOW the signal line (cross-down on current bar)
- Signals are discrete (1, -1, or 0) — no forward-fill; only fires on actual crossover bars

### Exit Logic
Signal reversal: when the opposite crossover fires, the engine closes the current position and opens a new one.

---

## 4. bollinger_bands_strategy

**File:** `strategies/bollinger_bands.py`
**Class:** `bollinger_bands_strategy`
**Loader key:** `bollinger_bands`

### Description
Bollinger Bands mean reversion strategy. Uses BB touch + RSI confirmation for entries.

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `period` | `20` | BB middle line SMA period |
| `std_dev` | `2.0` | Number of standard deviations for bands |

### Timeframes
Any timeframe.

### Indicators Used
- **Bollinger Bands** (period=20, std_dev=2.0) — upper, middle, lower
- **RSI** (14) — simple SMA-smoothed RSI for confirmation

### Entry Logic
- **BUY** → Price touches/below lower band **AND** RSI > 30 (oversold but not extreme)
- **SELL** → Price touches/above upper band **AND** RSI < 70 (overbought but not extreme)
- Signals are discrete (1, -1, or 0) — fires only when conditions are met on a given bar

### Exit Logic
Signal reversal: when the opposite signal fires, the engine closes the current position.

---

## 5. EmaRsiCrossoverStrategy

**File:** `strategies/ema_rsi_crossover.py`
**Class:** `EmaRsiCrossoverStrategy`
**Loader key:** `ema_rsi_crossover`

### Description
EMA(9/21) + RSI(14) momentum crossover strategy. Gold-optimised for XAUUSD on 1h/4h timeframes. Uses ATR(14) for dynamic stop-loss and take-profit.

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `ema_fast` | `9` | Fast EMA period |
| `ema_slow` | `21` | Slow EMA period |
| `rsi_period` | `14` | RSI lookback period |
| `rsi_buy_min` | `50.0` | Minimum RSI for buy (momentum building) |
| `rsi_buy_max` | `70.0` | Maximum RSI for buy (avoid overbought) |
| `rsi_sell_min` | `30.0` | Minimum RSI for sell (avoid oversold) |
| `rsi_sell_max` | `50.0` | Maximum RSI for sell (momentum fading) |

### Timeframes
Optimised for **1h / 4h** (designed with Gold in mind).

### Indicators Used
- **EMA** (fast=9, slow=21) — exponential moving averages
- **RSI** (14) — Wilder's smoothed RSI
- **ATR** (14) — for SL/TP sizing (used by engine, not directly for signals)

### Entry Logic
- **BUY** → Fast EMA crosses ABOVE Slow EMA **AND** RSI between 50–70 (momentum building, not overbought)
- **SELL** → Fast EMA crosses BELOW Slow EMA **AND** RSI between 30–50 (momentum fading, not oversold)
- Signals are forward-filled: once in a position, stays until opposite crossover

### Exit Logic
- Signal reversal (opposite crossover) closes position
- Engine applies hard-coded SL=200 pips / TP=400 pips (1:2 R:R)
- Engine also uses ATR values computed by strategy for reference

---

## 6. GoldPhoenixStrategy

**File:** `strategies/gold_phoenix.py`
**Class:** `GoldPhoenixStrategy`
**Loader key:** `gold_phoenix`

### Description
Multi-signal Gold strategy optimised for **FTMO challenge passing** (Phase 1: 10% profit, 10% DD, 10 days; Phase 2: 5%, 5%, 10 days). Combines session-based breakout, volatility expansion, and momentum continuation specifically for XAUUSD on H1.

### Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_period` | `14` | ATR lookback for volatility |
| `adx_period` | `14` | ADX lookback for trend strength |
| `adx_threshold` | `26.0` | Minimum ADX for trend mode |
| `ema_fast` | `21` | Fast EMA for trend/pullback |
| `ema_slow` | `55` | Slow EMA for trend direction |
| `bb_period` | `20` | Bollinger Band period |
| `bb_std` | `2.0` | Bollinger Band std dev |
| `bb_squeeze_min` | `0.40` | Max BB width ratio for squeeze detection |
| `max_trades_day` | `2` | Max trades per day |
| `session_start_gmt` | `7` | Trade session start (GMT hour) |
| `session_end_gmt` | `17` | Trade session end (GMT hour) |
| `asian_range_bars` | `6` | Bars for Asian session range calculation |

### Timeframes
Designed for **H1** (1-hour). The Asian session range logic and session hours are hard-tuned for hourly bars.

### Indicators Used
- **ATR** (14) — true range average for volatility context
- **EMA** (21, 55, 200) — short/medium/long-term trend
- **ADX** (14) — trend strength with +DI/-DI direction
- **Bollinger Bands** (20, 2.0) — squeeze detection
- **RSI** (14) — Wilder's smoothed for reversal signals

### Entry Logic
**Four signal types** (any can fire on a given bar, evaluated in priority order):

1. **ASIAN_BREAK** (London open, 7–10 GMT) — breakout above Asian session high (long) or below Asian session low (short). Requires meaningful Asian range (>0.3×ATR). Triggers in trend or no-trend.
2. **SQUEEZE** (any session hour) — when BB width is at an extreme contraction (squeeze_ratio ≤ bb_squeeze_min), breakout above upper band (long) or below lower band (short).
3. **PULLBACK** (strong trend, ADX ≥ threshold+5) — price pulls back within 0.5×ATR of fast EMA after having been on the other side in the last 5 bars. Requires RSI ≥ 40 (long) or ≤ 60 (short).
4. **REVERSAL** (no trend, ADX < threshold) — RSI extreme (<25 or >75) near slow EMA (±1.5×ATR). Requires two consecutive bars at extreme.

**Capped** at `max_trades_day` per day (excess signals are zeroed).

### Exit Logic
- Engine applies hard SL=200 pips / TP=400 pips (1:2 R:R)
- Signal reversal triggers exit
- Margin-call at equity ≤ 0
- End-of-data forced close

---

## 7. Test (Custom — Disabled)

**File:** `custom_strategies/_custom_33926009.py`
**Class:** `Test`
**Loader status:** ⚠️ **NOT LOADED** — The filename starts with underscore (`_custom_33926009.py`), and the loader explicitly skips files whose name starts with `_`.

### Description
Minimal stub strategy — always generates a flat signal (no trades).

### Parameters
None.

### Timeframes
Any.

### Indicators Used
None.

### Entry Logic
Never enters a position — `df['signal'] = 0` unconditionally.

### Exit Logic
N/A — no positions to exit.

---

## Summary Table

| # | Strategy | File | Type | Indicators | Timeframes | Trades |
|---|----------|------|------|-----------|------------|--------|
| 1 | DefaultStrategy | `default.py` | Fallback | SMA (9,21) | Any | Always in |
| 2 | sma_crossover | `sma_crossover.py` | Built-in | EMA (9,21) | Any | Always in |
| 3 | macd_crossover | `macd_crossover.py` | Built-in | MACD (12,26,9) | Any | Discrete |
| 4 | bollinger_bands | `bollinger_bands.py` | Built-in | BB (20,2), RSI (14) | Any | Discrete |
| 5 | ema_rsi_crossover | `ema_rsi_crossover.py` | Built-in | EMA (9,21), RSI (14), ATR (14) | 1h/4h optimised | Forward-filled |
| 6 | gold_phoenix | `gold_phoenix.py` | Built-in | ATR, EMA, ADX, BB, RSI | H1 specific | Capped/day |
| 7 | Test (stub) | `_custom_...py` | Custom | None | Any | Never |
