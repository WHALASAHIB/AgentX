# AGENTX Bot Strategies — Complete Reference

> All strategies use dynamic position sizing at 0.15% risk per trade.  
> Circuit breaker halts trading after N consecutive losses (configurable, default 5).  
> Trailing stops activate at 20 pips profit, trail by 10 pips.  
> IPC recovery restores bot state after process restart.  
> FTMO protections enforce max daily loss (-5%), max drawdown (-10% for challenges, -5% funded).

---

## 1. Core Strategies

### MACD Strategy
**Signature:** `MACD(symbol, timeframe, fast_ema=12, slow_ema=26, signal_sma=9, overbought=200, oversold=-200)`

- **Logic:** Standard MACD crossover + histogram divergence.
- **Entry:** MACD line crosses signal line with histogram confirmation.
- **Exit:** Opposite crossover or trailing stop.
- **Timeframes:** M15, H1 (preferred), H4.
- **Pairs:** EURUSD, GBPUSD, USDJPY, AUDUSD (major forex only).
- **Risk profile:** Conservative — typical win rate 55-60%, avg RR 1:1.5.
- **Backtest benchmark (2025, EURUSD H1):** Profit factor 1.42, Sharpe 1.21, Max DD -8.3%, Win rate 57%.

### GoldPhoenix Strategy
**Signature:** `GoldPhoenix(symbol=XAUUSD, timeframe=M15, atr_period=14, ema_fast=9, ema_slow=21, rsi_period=14, rsi_overbought=70, rsi_oversold=30)`

- **Logic:** Multi-factor gold trading — EMA trend filter + RSI momentum + ATR volatility gates.
- **Entry conditions:**
  1. Price above EMA 21 (bullish) or below (bearish).
  2. RSI divergence or extreme zone entry.
  3. ATR confirms sufficient volatility (>20th percentile).
- **Exit:** Trailing stop based on 1.5× ATR, or RSI reversion.
- **Timeframes:** M5, M15 (primary), H1.
- **Pairs:** XAUUSD only (symbol-locked).
- **Risk profile:** Moderate-aggressive — win rate 50-55%, avg RR 1:2.0.
- **Backtest benchmark (2025, XAUUSD M15):** Profit factor 1.68, Sharpe 1.45, Max DD -12.1%, Win rate 52%.

### Bollinger Strategy
**Signature:** `Bollinger(symbol, timeframe=H1, period=20, std_dev=2.0, ema_trend=50)`

- **Logic:** Bollinger Band squeeze/expansion with EMA trend filter.
- **Entry:**
  - Long: price touches lower band, EMA 50 trending up, candle closes inside bands.
  - Short: price touches upper band, EMA 50 trending down, candle closes inside bands.
- **Exit:** Price hits opposite band, or EMA trend reversal.
- **Timeframes:** H1, H4 (primary).
- **Pairs:** EURUSD, GBPUSD, USDJPY, XAUUSD.
- **Risk profile:** Moderate — win rate 53-58%, avg RR 1:1.8.
- **Backtest benchmark (2025, GBPUSD H1):** Profit factor 1.55, Sharpe 1.33, Max DD -9.7%, Win rate 55%.

### SMA Strategy
**Signature:** `SMA(symbol, timeframe=H1, fast_sma=10, slow_sma=50, trend_sma=200, filter_atr=true)`

- **Logic:** Dual SMA crossover with 200-SMA macro trend filter + ATR volatility filter.
- **Entry:** Fast SMA crosses slow SMA in direction of 200-SMA trend.
- **Exit:** Opposite SMA crossover, or ATR-based trailing stop.
- **Timeframes:** H1, H4 (primary), D1.
- **Pairs:** All major forex + XAUUSD.
- **Risk profile:** Conservative — win rate 58-63%, avg RR 1:1.3.
- **Backtest benchmark (2025, EURUSD H1):** Profit factor 1.38, Sharpe 1.18, Max DD -7.2%, Win rate 60%.

---

## 2. Legacy Strategies

### Gold v3 MTF
**Signature:** `Gold_v3_MTF(symbol=XAUUSD, timeframes=[M5, M15, H1], atr_multiplier=1.5)`

- Multi-timeframe confirmation for gold entries.
- Entry requires alignment across M5, M15, and H1.
- Higher win rate but fewer trade opportunities.

### Scalp v3
**Signature:** `Scalp_v3(symbol, timeframe=M1, ema_fast=5, ema_slow=13, rsi_period=7)`

- Fast scalping on M1 with EMA crossover + RSI filter.
- Target 5-10 pips, hard stop 15 pips.
- High trade frequency, lower win rate (~45-50%).

### M1 Stream
**Signature:** `M1_Stream(symbol, timeframe=M1, order_flow=true, volume_profile=false)`

- Order-flow-based scalping on M1.
- Reads market microstructure for entries.
- Experimental — use with caution.

### SRB v2 XAU
**Signature:** `SRB_v2_XAU(symbol=XAUUSD, timeframe=M15, support_res_bands=true, breakout_confirmation=2_candles)`

- Support/resistance band breakout on XAUUSD.
- Requires 2-candle close beyond band for confirmation.
- Good for trending gold days.

### SRB XAU (Legacy)
**Signature:** `SRB_XAU(symbol=XAUUSD, timeframe=M15)`

- Original support/resistance breakout (single-candle confirmation).
- Superseded by v2 for production use.

### Scalping Hybrid
**Signature:** `Scalping_Hybrid(symbol, timeframe=M5, macd_periods=[12,26,9], bollinger_period=20, rsi_period=7)`

- Combines MACD crossover + Bollinger squeeze + RSI momentum.
- Triple-confirmation entries.
- All pairs, M5 preferred.

---

## 3. Per-Pair Strategy Assignments

| Symbol   | Primary Strategy | Fallback Strategy | Timeframes          |
|----------|-----------------|-------------------|--------------------|
| XAUUSD   | GoldPhoenix     | SRB v2 XAU        | M5, M15, H1       |
| EURUSD   | MACD            | SMA               | M15, H1           |
| GBPUSD   | Bollinger       | MACD              | H1, H4            |
| USDJPY   | MACD            | SMA               | M15, H1           |
| AUDUSD   | SMA             | MACD              | H1                |
| USDCAD   | SMA             | Bollinger         | H1                |
| NZDUSD   | SMA             | MACD              | H1                |
| EURJPY   | Bollinger       | SMA               | H1, H4            |
| GBPJPY   | Bollinger       | MACD              | H1                |

---

## 4. Dynamic Position Sizing

All strategies share the same position sizing engine:

```
risk_amount = account_balance × risk_percent (default 0.15%)
position_size = risk_amount / stop_loss_pips
```

**Position limits by account type:**
| Account Type  | Max Position % | Max Lots | FTMO Rules Apply |
|---------------|---------------|---------|------------------|
| FTMO Challenge | 0.15%        | 1.0     | Yes              |
| FTMO Funded    | 0.10%        | 0.5     | Yes              |
| Personal       | 0.15%        | 2.0     | No               |

---

## 5. Circuit Breaker

**Trigger conditions (any):**
- 5 consecutive losing trades (configurable)
- Daily loss exceeds -5% of account
- Drawdown exceeds -10% (challenge) or -5% (funded)
- Strategy-specific error rate > 20% on last 20 signals

**Actions:**
1. Pause trading on affected bot(s)
2. Log breach to AgentOps
3. Send SRE alert via Telegram
4. Auto-resume after 60 minutes or manual override

**Override API:**
```bash
curl -X POST https://agentx.nousresearch.com/api/v1/bots/{id}/start \
  -H "Authorization: Bearer $TOKEN"
```

---

## 6. Trailing Stops

| Parameter           | Default | Strategy Override |
|--------------------|---------|------------------|
| Activation pips    | 20      | GoldPhoenix: 25  |
| Trail distance     | 10      | MACD: 8          |
| Minimum trail step | 1 pip   | —                |
| Lock minimum profit| 5 pips  | —                |

---

## 7. IPC Recovery

On bot restart (planned or crash):
1. Check Redis for persisted bot state (`bot:{id}:state`).
2. Reconnect to MT5 bridge.
3. Synchronize open positions with broker.
4. Resume trailing stops from last known price.
5. Resume circuit breaker counters (do not reset on restart).

---

## 8. FTMO Protections

Applied to all FTMO account types:
- **Daily loss limit:** Hard stop at -5% daily P&L (all bots halt).
- **Max drawdown:** -10% for challenge phase, -5% for funded phase.
- **Max lot size:** 1.0 lots (challenge), 0.5 lots (funded).
- **Max positions:** 3 simultaneous (challenge), 2 (funded).
- **Trading hours restriction:** No news trading 5 min before/after major economic releases.
- **Consistency rule:** No single trade > 20% of total profit target (challenge phase).

---

## 9. Trading Sessions (HKT — UTC+8)

| Session    | Forex Active       | Gold Active | Hours (HKT)      | Primary Strategies       |
|-----------|-------------------|-------------|------------------|-------------------------|
| Asian     | JPY, AUD, NZD     | Yes         | 06:00–15:00      | MACD, SMA               |
| London    | EUR, GBP, CHF     | Yes         | 15:00–00:00      | MACD, Bollinger, SMA    |
| US        | USD all pairs     | Yes         | 20:00–05:00      | Bollinger, GoldPhoenix  |
| Overlap   | EUR/USD, GBP/USD  | Peak        | 20:00–00:00      | All                     |

**Session-aware execution:**
- Bots automatically adjust pair activation by session.
- Gold (XAUUSD) trades across all sessions but reduced sizing in Asian session.
- News events automatically pause trading 5 min before/after high-impact releases.
