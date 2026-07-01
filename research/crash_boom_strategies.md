# Crash/Boom Trading Strategies — Actionable Research Report
## For MetaTrader 5 (FX & Gold) Implementation
### Risk Budget: 0.5–1% per trade | Max Daily DD: 4% (FTMO-compliant)

---

## Table of Contents
1. [Tail-Risk Hedging (Taleb/Universa Approach)](#1-tail-risk-hedging)
2. [Volatility Breakout & Expansion Strategies](#2-volatility-breakout--expansion-strategies)
3. [VWAP Deviation During High-Volatility Events](#3-vwap-deviation-during-high-volatility-events)
4. [Gold (XAUUSD) Crash/Boom Patterns](#4-gold-xauusd-crashboom-patterns)
5. [Price-Action Momentum Explosion Detection](#5-price-action-momentum-explosion-detection)
6. [MT5-Compatible Indicator Approaches](#6-mt5-compatible-indicator-approaches)
7. [Summary Matrix](#7-summary-matrix)

---

## 1. Tail-Risk Hedging (Taleb/Universa)

### Core Concept
The Universa approach: buy deep out-of-the-money (OTM) options that are cheap to hold but pay out massively during black-swan events (3-5 sigma moves). Taleb's strategy loses small amounts consistently (the "premium bleed") but captures 10-50x returns during crashes.

### Can This Be Done With FX?
**Partially — with important caveats:**
- FX options (OTC) are not traded on most MT5 retail platforms. However, you can **synthetically replicate** tail-risk hedges using:
  - **CFD positions** with very wide stops placed at extreme levels
  - **Position sizing as a hedge** — reducing size during calm, increasing during fear
  - **VIX or Volatility ETFs** — if your broker offers indices (not typical for FX-only brokers)
- **Realistic alternative for MT5 FX:** Use a **systematic stop-loss overlay** combined with **gamma-like scaling** — increase position size as volatility rises, decrease during calm.

### MT5-Implementable Strategy: "Premium Bleed" Hedge Overlay

**Concept:** Run a small, persistent short position on low-volatility pairs (EURCHF, USDCHF) with extremely wide stops — essentially paying a small daily cost as "premium" for crash protection. During crashes, CHF and JPY strengthen massively.

**Strategy Design:**

| Parameter | Value |
|-----------|-------|
| **Instruments** | EURCHF, USDCHF (safe-haven CHF pairs) |
| **Direction** | Long EURCHF (hedge against CHF strength during crashes) |
| **Position size** | 0.01-0.02 lots per $10k (very small — the "premium") |
| **Stop loss** | None or 500+ pips (allow the bleed) |
| **Take profit** | None (hold through crash) |
| **Monthly expected cost** | 0.2-0.5% of account (the bleed) |
| **Trigger to close** | When VIX-equivalent or ATR(14) on EURCHF exceeds 2x its 50-day average |

**Better Alternative — Dynamic Beta Weighting:**
- Track overall portfolio beta to a crash proxy (S&P 500, Gold)
- When beta > threshold, reduce all position sizes by 25-50%
- This is *de facto* tail hedging via exposure management

### Pitfalls
- **Premium bleed accumulates:** Over years, the cost can exceed crash payouts if crashes are infrequent
- **FX doesn't crash like equities:** FX crashes are 2-5% moves, not 20-30%. The payoff profile is less attractive
- **Broker restrictions:** Most MT5 brokers don't offer FX options natively
- **Time decay works against you** in options; in synthetic versions, you're fighting spread costs

---

## 2. Volatility Breakout / Expansion Strategies

### 2A. ATR Expansion Breakout

**Logic:** Sudden ATR expansion signals a volatility regime change — the market is entering a high-energy phase. Trade in the direction of the expansion.

**Entry Signal:**
- Calculate ATR(14) on H1
- If current candle's ATR > 1.5x (or 2x) the ATR(50) on the same timeframe
- **AND** the current candle has broken the previous candle's high (for longs) or low (for shorts)
- Enter immediately or at market

**Exit:**
- Trail stop at 1x ATR(14) (fixed trailing from highest high / lowest low)
- Or exit when ATR(14) drops back below 1.2x ATR(50) (volatility contraction)

**Money Management (0.5-1% risk):**

| Account Size | Risk % | Risk $ | Stop Distance (pips) | Position Size |
|-------------|--------|--------|---------------------|---------------|
| $10,000 | 0.5% | $50 | 30 pips (EURUSD) | 0.16 lots |
| $10,000 | 1.0% | $100 | 30 pips (EURUSD) | 0.33 lots |
| $50,000 | 0.5% | $250 | 30 pips (EURUSD) | 0.83 lots |
| $100,000 | 1.0% | $1,000 | 30 pips (EURUSD) | 3.3 lots |

**Formula:** Lots = (Account x Risk%) / (StopPips x PipValue)

**Best Instruments:** EURUSD, GBPUSD, XAUUSD (gold has highest ATR expansion sensitivity)

**Known Pitfalls:**
- False breakouts are common — use strict confirmation (e.g., close above breakout level, not just intra-day spike)
- ATR expansion can happen at the END of a move (blow-off top) — always check price structure
- On lower TFs (M5, M15), ATR is noisy — stick to H1+

### 2B. Bollinger Band Squeeze Breakout

**Logic:** When Bollinger Bands contract (squeeze), it signals low volatility. The breakout from the squeeze often produces explosive directional moves.

**Entry Signal (M15 or H1):**
1. Bollinger Bands (20, 2) — measure bandwidth: (Upper - Lower) / Middle
2. Bandwidth contracts below its 20-period low (squeeze detected)
3. Price breaks above upper band (long) or below lower band (short)
4. Volume/volatility confirmation: ATR(14) > 1.3x ATR(50) on the breakout candle

**Alternative — %B Squeeze:**
- Use %B indicator (price position within bands)
- Squeeze when %B stays between 0.2 and 0.8 for 10+ candles
- Enter when %B breaks above 0.8 (long) or below 0.2 (short)

**Exit:**
- Target 2x the pre-squeeze bandwidth (measured from entry)
- Or trail once 1x bandwidth profit is achieved

**Risk Sizing:** Same formula as above. Stop at opposite band (short stops above upper band + 5 pips).

**Best Pairs:** GBPUSD (most explosive squeeze breakouts), XAUUSD, USDJPY

**Pitfalls:**
- Squeeze can persist for 50+ bars — premature entry is costly
- False breakouts: price can breach a band and reverse within 1-2 candles
- On XAUUSD, bandwidth on lower TFs is tight — use H1 minimum

---

## 3. VWAP Deviation During High-Volatility Events

### Core Concept
During news events (NFP, FOMC, CPI), price often deviates significantly from VWAP. The strategy exploits the statistical tendency for price to revert toward VWAP after the initial spike, or to continue directionally if the deviation is supported by momentum.

### Entry Logic — "Event Mean Reversion" Variant

**Setup:**
- Identify upcoming high-impact events (NFP, FOMC, CPI, ADP, GDP)
- Calculate VWAP on H1 using: (H+L+C)/3 x Volume / Cumulative Volume
- On MT5: compute via custom Python indicator (MT5 API allows tick volume)

**Entry Rules:**
1. Wait 5-15 minutes after the news release (let initial spike settle)
2. If price is > 1.5x ATR(14) away from VWAP in either direction
3. **AND** the 1-minute candle shows a reversal pattern (doji, hammer, shooting star)
4. Enter in the direction TOWARD VWAP (mean reversion)

**Entry Logic — "Event Momentum" Variant**

**Setup:**
- Same event-based trigger
- Calculate VWAP and a "VWAP channel" (+/-1 ATR bands around VWAP)

**Entry Rules:**
1. If price breaks above VWAP + 1 ATR and stays there for 3 consecutive 1-min candles
2. Enter long with stop at VWAP - 0.5 ATR
3. Target VWAP + 2 ATR (extension)

### Exit Logic
- **Mean reversion variant:** Exit when price touches VWAP; or trail at 0.5x ATR(14)
- **Momentum variant:** Exit on close below VWAP + 0.5 ATR; or fixed 2:1 RR

**Risk Sizing (0.5-1%):**

| Account | Risk % | Stop | Notes |
|---------|--------|------|-------|
| $10k | 0.5% ($50) | NFP: 40 pip stop | Wider stops needed during news |
| $10k | 1.0% ($100) | NFP: 40 pip stop | |
| $100k | 0.5% ($500) | NFP: 40 pip stop | |

### Best Instruments for News Events
| Event | Best Pairs | Notes |
|-------|-----------|-------|
| NFP | EURUSD, GBPUSD, USDJPY | EURUSD most liquid |
| FOMC | USDJPY, XAUUSD | Gold sensitive to rate decisions |
| CPI | EURUSD, USDCAD | |
| GDP | USD pairs generally | |
| Retail Sales | GBPUSD, EURUSD | |

### Pitfalls
- **Slippage is extreme** during news — spreads can widen to 5-20 pips
- **Stop-loss hunting:** Brokers often spike through stops during news
- **Second leg:** The initial spike often reverses completely within 30 minutes — don't chase
- **VWAP recalculation:** VWAP resets daily; on MT5 custom implementation must handle session breaks
- **Not all events are equal:** NFP moves ~80-120 pips EURUSD; CPI ~60-100 pips; lesser events may not trigger

---

## 4. Gold (XAUUSD) Crash/Boom Patterns

### Gold's Unique Behavior
Gold is a **crisis barometer** — it spikes during:
- Geopolitical shocks (wars, sanctions, invasions)
- Banking/financial crises (2008, 2020, 2023 regional banks)
- Real rate collapses (Fed pivots, QE announcements)
- Sudden USD weakness

Gold's crash patterns (selling during liquidity crises — "sell everything" events):
- March 2020: Gold dropped ~12% in 2 weeks, then rallied 35% over 3 months
- 2013 Taper Tantrum: Gold crashed ~28% over 2 months

### Strategy 4A: Crisis Spike Scalp (Boom)

**Setup:** Monitor for breaking geopolitical/financial news

**Entry Signal:**
1. XAUUSD gains > 1.5% within 1 hour (abnormal move)
2. Volume (tick) surges to > 2x the 50-period tick volume average
3. Price breaks above the previous session's high
4. Enter long immediately on the breakout

**Exit:**
- Trail at 1.5x ATR(14) on M15
- Close 50% at +2 ATR, let rest run
- Hard close when volatility drops (ATR(14) on H1 falls 40% from peak)

**Risk Sizing:**
- XAUUSD pip value: $1 per 0.01 lot per $10 movement
- Stop: 150-200 pips (movement is volatile)
- For $10k account at 0.5% risk ($50): 0.02-0.03 lots (wide stop needed)

### Strategy 4B: Gold Crash Recovery (Buy-the-Dip)

**Concept:** Gold always recovers from crashes that are NOT structural USD-strengthening events. Buy the panic.

**Entry:**
1. Gold drops > 3% from recent 20-day high
2. VIX or equivalent fear index is elevated
3. Price forms a bullish engulfing or hammer on the DAILY chart
4. RSI(14) < 30 (oversold)
5. Enter 50% at signal, 50% if price drops another 1%

**Exit:**
- Target: previous resistance / 50% Fibonacci retracement of the crash
- Time stop: close after 5 trading days if no progress

### Strategy 4C: Gold Intraday Breakout (Boom)

**Entry:** H1 chart
1. Bollinger Bands (20,2) squeeze (bandwidth at 14-period low)
2. Price breaks above middle band + 1x ATR(14)
3. Tick volume > 1.5x average
4. Enter on H1 close above this level

**Exit:** Target 2x the ATR(14) from entry; stop at previous H1 low minus 1 ATR

### Best Conditions for Gold Strategies
| Condition | Boom Likely | Crash Likely |
|-----------|-------------|--------------|
| Fed cuts rates | HIGH | LOW |
| War/conflict starts | HIGH | MED (initial liquidation, then rally) |
| USD strengthens | LOW | HIGH |
| Real yields rise | LOW | HIGH |
| Banking crisis | HIGH | MED (initial, then recovery) |
| Liquidity crisis | LOW (initial crash) | HIGH (then buy dip) |

### Pitfalls
- **Gold spikes are extremely sharp but short-lived** — 70% of crisis spikes fade within 5 days
- **Stop distances must be wide** (200+ pips on H1) — tight stops get taken immediately
- **Gold has multiple personalities:** acts as risk-on (low rates) AND risk-off (crisis) asset
- **COMEX expiry / First Notice Day** can cause artificial volatility — avoid trading around these dates
- **Correlated to USD and yields** inversely — don't ignore macro context

---

## 5. Price-Action Momentum Explosion Detection

### Core Concept
Identify candles with **abnormal range relative to recent history** — these signal "momentum explosions" that often continue for 3-7 more candles.

### Strategy: "Range Ratio" Explosion System

**Entry Logic (any timeframe, recommended M15 or H1):**
1. Calculate the median candle range over the last 20 periods: `MedRange = median(High - Low for last 20 candles)`
2. Current candle's range: `CurrentRange = High - Low`
3. **Range Ratio** = `CurrentRange / MedRange`
4. Entry triggers when **Range Ratio > 2.5** (2.5x normal range)
5. Trade in the direction of the candle body — if bullish body, go long; if bearish body, go short
6. Confirmation filter: Range Ratio > 2.5 AND the candle closes in the top 30% (longs) or bottom 30% (shorts) of its range

**Exit Logic:**
- **Method A (Fixed):** Target = 1.5 x CurrentRange from entry
- **Method B (Trailing):** Trail stop at the 20-period median range; tighten to 1x median after 2x profit achieved
- **Method C (Regression):** Exit when a new candle's range is < 1.2x median range (volatility contraction exit)

**Risk Sizing:**

| Parameter | Value |
|-----------|-------|
| Stop distance | 0.5 x CurrentRange (half the explosion candle's range) |
| Risk per trade | 0.5-1% |
| Position size | Lots = (Account x Risk%) / (StopPips x PipValue) |
| RR expectation | 2:1 to 3:1 on valid signals |

### Python Implementation Snippet (for MT5 API)

```python
def detect_explosion(high, low, close, period=20, threshold=2.5):
    # Calculate median range
    ranges = [high[i] - low[i] for i in range(-period, 0)]
    med_range = sorted(ranges)[period // 2]

    # Current range
    curr_range = high[-1] - low[-1]
    ratio = curr_range / med_range if med_range > 0 else 0

    # Direction & body position
    body = close[-1] - open[-1]
    body_pct = (close[-1] - low[-1]) / curr_range if curr_range > 0 else 0.5

    if ratio >= threshold:
        if body > 0 and body_pct > 0.7:   # Bullish explosion
            return 'BUY', ratio
        elif body < 0 and body_pct < 0.3: # Bearish explosion
            return 'SELL', ratio
    return None, ratio
```

### Best Instruments
| Instrument | Explosion Frequency | Average Follow-Through | Best TF |
|------------|-------------------|----------------------|---------|
| XAUUSD | HIGH | 3-5 candles | M15, H1 |
| GBPUSD | HIGH | 3-4 candles | M15, H1 |
| EURUSD | MED | 2-3 candles | H1 |
| USDJPY | MED | 2-3 candles | H1 |
| USDCHF | LOW | 1-2 candles | H1 |
| NZDUSD | LOW | 2 candles | H1 |

### Pitfalls
- **Spike-and-reverse:** Some explosion candles are liquidity grabs that reverse completely — this is the #1 cause of losses. The candle close filter (top/bottom 30%) helps but doesn't eliminate it
- **Threshold tuning:** 2.5x works for H1. For M15, use 3.0x. For M5, 4.0x (noisier = higher threshold needed)
- **Market context matters:** An explosion candle during a news event is different from one during quiet trading. Filter for event periods
- **Gap risk:** On weekends/overnight, explosion signals may gap through your stop
- **Median vs mean:** Use median (not mean) for range — it's robust to the very outliers we're detecting

---

## 6. MT5-Compatible Indicator Approaches

### 6A. Custom Volatility Ratio Indicator

**What it does:** Displays current ATR divided by a longer-term ATR average.

**Parameters:**
- Fast ATR: 14
- Slow ATR: 50
- Threshold line: 1.5, 2.0, 2.5
- Calculation: `VolRatio = ATR(14) / ATR(50)`

**Signal:** When VolRatio crosses above 1.5 and price is above/below key moving average

**Implementation:** Can be coded as a custom MT5 indicator (mq5) or Python indicator via MT5 API

### 6B. Bollinger Band Squeeze

**What it does:** Plots Bollinger Band width as a histogram. Squeeze condition = BB width < Keltner Channel width.

**Parameters:**
- BB period: 20, BB dev: 2.0
- Keltner Channel period: 20, multiplier: 1.5

**MT5 Availability:** Built-in Bollinger Bands + manual Keltner overlay is sufficient.

### 6C. VWAP with Standard Deviation Bands

**Implementation for MT5 (Python via API):**
1. Calculate VWAP on H1: `VWAP = sum(TP[i] * Vol[i]) / sum(Vol[i])`
2. Deviation = `sqrt(sum(Vol[i] * (TP[i] - VWAP)^2) / sum(Vol[i]))`
3. Plot +1, +2, +3 SD bands

**Signals:**
- Level 1: Price at VWAP + 1 Dev = potential reversal zone
- Level 2: Price beyond VWAP + 2 Dev = overextended (mean reversion setup)
- Level 3: Price at VWAP + 3 Dev = extreme (rare, powerful)

### 6D. ATR Trailing Stop (Chandelier Exit)

**Parameters:** ATR(22), multiplier 3.0, lookback 22. Use as exit mechanism for all volatility strategies above.

### 6E. Volume-Weighted ATR (VWATR)

**Calculation:** `VWATR = EMA(ATR x TickVolume / AvgTickVolume, period)`

**Signal:** VWATR > 1.5x its own 50-period MA = confirmed elevated volatility.

### 6F. Intraday Momentum Index (IMI)

**Parameters:** Period 14, OB 80, OS 20. Uses open-to-close changes.

**Signal:** Cross above 80 during volatility expansion = strong momentum entry.

### Indicator Selection Matrix

| Strategy | Primary Indicators | Confirmation | Best TF |
|----------|-------------------|--------------|---------|
| ATR Expansion | ATR(14), ATR(50) | Price structure | H1 |
| BB Squeeze | BB(20,2), KC(20,1.5) | ATR ratio | H1 |
| VWAP News | VWAP +/- SD bands | ATR, reversal candle | M5-M15 |
| Gold Boom | ATR(14), BB(20,2) | Tick volume | H1 |
| Range Ratio | Custom: median range | Candle body % | M15-H1 |
| Momentum Explosion | Custom: VWATR | IMI(14) | M15 |

---

## 7. Summary Matrix

### Strategy Comparison

| # | Strategy | Best Pairs | Est. Win Rate | Avg RR | TF | Complexity |
|---|----------|-----------|--------------|--------|-----|-----------|
| 1 | Tail-Risk Hedge (Overlay) | EURCHF, USDCHF | N/A (hedge) | 1:5+ (rare) | Daily | Medium |
| 2A | ATR Expansion Breakout | GBPUSD, XAUUSD | 45-55% | 1:2 - 1:3 | H1 | Low |
| 2B | BB Squeeze Breakout | GBPUSD, XAUUSD | 40-50% | 1:2 - 1:4 | H1 | Low |
| 3 | VWAP News Event | EURUSD, GBPUSD, USDJPY | 55-65% | 1:1 - 1:2 | M5-M15 | Medium |
| 4A | Gold Crisis Spike | XAUUSD | 50-60% | 1:2 - 1:3 | M15-H1 | Medium |
| 4B | Gold Crash Recovery | XAUUSD | 65-75% | 1:2 - 1:5 | Daily | Low |
| 5 | Range Ratio Explosion | XAUUSD, GBPUSD | 50-55% | 1:2 - 1:3 | M15-H1 | Medium |

### Recommended Implementation Order

1. **ATR Expansion Breakout** (2A) — simplest, only needs built-in ATR
2. **BB Squeeze Breakout** (2B) — also built-in indicators
3. **VWAP News Event** (3) — needs custom VWAP calc, highest win rate
4. **Range Ratio Explosion** (5) — needs custom Python indicator
5. **Gold Crash Recovery** (4B) — needs daily monitoring
6. **Tail-Risk Hedge overlay** (1) — ongoing background

### Risk Budget Allocation

| Strategy | Allocation of Risk Budget |
|----------|--------------------------|
| Daily directional (ATR/BB/Range) | 40% (max 4 signals/week) |
| News event (VWAP) | 30% (max 2 events/day) |
| Gold specific | 20% (1-2 signals/week) |
| Tail-risk hedge overlay | 10% (always running) |

### Critical Risk Rules (FTMO-Compliant)

1. **Max 4% daily DD hard stop** — if P&L hits -4%, stop all trading for the day
2. **Correlated pair limits** — do not take EURUSD + GBPUSD simultaneously (0.7+ correlation); max 1 trade per correlated group
3. **News filter** — no new entries 30 min before major news (use ForexFactory calendar)
4. **Max concurrent trades:** 3 (uncorrelated pairs only)
5. **Weekly cool-off:** After 3 consecutive losses, stop for the day
6. **Monthly max drawdown:** 8% — if hit, shut down all strategies for the month

---

*Research compiled for MT5 / Python automated trading system. All strategies require backtesting and optimization on your specific broker's execution conditions before live deployment.*
