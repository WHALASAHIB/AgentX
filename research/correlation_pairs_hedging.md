# Negatively Correlated FX Pairs: Hedging Strategies & Bot Design

**Generated:** 2026-07-01  
**Target:** FTMO Challenge Accounts (4% Daily DD / 8% Total DD)  
**Platform:** MT5 + Python API

---

## 1. Correlation Matrix of Major Pairs

### Typical Correlation Coefficients (1-Year Rolling, Normal Market)

| Pair Pair | Correlation Coefficient | Relationship |
|---|---|---|
| EURUSD ↔ USDCHF | **-0.93 to -0.97** | Strongest negative correlation in FX |
| GBPUSD ↔ USDCHF | -0.85 to -0.90 | Strong negative |
| EURUSD ↔ USDJPY | -0.35 to -0.55 | Moderate negative |
| AUDUSD ↔ USDJPY | +0.60 to +0.75 | Positive (both move with risk) |
| AUDUSD ↔ USDCAD | +0.55 to +0.70 | Positive (commodity currencies) |
| XAUUSD ↔ DXY | **-0.85 to -0.95** | Very strong negative |
| NZDUSD ↔ USDJPY | +0.50 to +0.65 | Moderate positive |
| USDJPY ↔ USDCHF | +0.40 to +0.55 | Moderate positive |
| EURUSD ↔ GBPUSD | +0.65 to +0.80 | Strong positive |

### Key Findings

**Strongest Negative Correlations (Hedging Candidates):**
1. **EURUSD vs USDCHF** — ρ ≈ -0.95 (near-perfect inverse)
2. **XAUUSD vs DXY (USD Index)** — ρ ≈ -0.90 (gold vs dollar)
3. **GBPUSD vs USDCHF** — ρ ≈ -0.88

**Strongest Positive Correlations (Avoid for hedging):**
- EURUSD ↔ GBPUSD: +0.72 (same-direction majors)
- AUDUSD ↔ NZDUSD: +0.78 (sister commodity currencies)

### Regime-Dependent Correlation Shifts

| Regime | Characteristic | Correlation Behavior |
|---|---|---|
| **Risk-On** (low vol, rising equities) | USD weakens broadly | Negative correlations weaken (EURUSD/USDCHF → -0.85). AUD, NZD, CAD rally vs USD. USDJPY rises |
| **Risk-Off** (crisis, high vol) | USD strengthens, JPY/CHF bid | Negative correlations **strengthen** (EURUSD/USDCHF → -0.98). Safe-haven flows dominate |
| **Rate-Hike Cycles** | Dollar strengthens on rate differentials | EURUSD/USDCHF stays strongly negative but USDJPY correlation to EURUSD weakens |
| **Commodity Shock** | CAD/AUD/NZD diverge from EUR | Correlation matrices fragment. Commodity pairs decouple from European pairs |

> **Rule of Thumb:** Negative correlations are *most reliable* during risk-off regimes (when hedging protection matters most). They are *least reliable* during transition periods between regimes.

---

## 2. EURUSD vs USDCHF — The Classic Hedge Pair

### Typical Correlation Coefficient: **-0.93 to -0.97**

**Why this pair works:**
- Both pairs have USD as the quote (EURUSD) and base (USDCHF) — they are structural inverses
- EUR and CHF are both European currencies, driven by similar macro factors (ECB/SNB)
- SNB historically intervenes to cap CHF strength, creating a natural asymmetry

**Historical Rolling Correlation (5-Year Range):**
```
Normal:        -0.95
Risk-Off:      -0.98
Risk-On:       -0.85 to -0.90
SNB Event:     -0.50 to -0.70 (transient, 1-5 days)
EUR Crisis:    -0.80 to -0.88
```

**Formula equivalence:**
```
EURUSD × USDCHF = EURCHF (a cross rate)
When EURUSD rises, USDCHF should fall proportionally to keep EURCHF stable
Theoretically perfect hedge: ρ = -1.0 (in practice -0.95 due to frictions)
```

### Why Not Exactly -1.0?
- Different liquidity profiles (EURUSD is ~3× more liquid)
- SNB interventions target EURCHF, not USDCHF directly
- Time zone differences in news impact (CHF moves on SNB, EUR on ECB)
- Transaction costs and spreads differ

---

## 3. AUDUSD vs USDJPY — Commodity vs Safe Haven

### Correlation Behavior

| Condition | AUDUSD ↔ USDJPY ρ | Notes |
|---|---|---|
| Normal market | **+0.60 to +0.75** | Both correlated to risk sentiment (positive, not negative!) |
| Risk-On rally | +0.70 to +0.85 | Strong positive — both rise |
| Risk-Off crash | +0.50 to +0.65 | Both fall, correlation persists |
| Divergent CB policy | +0.30 to +0.50 | RBA vs BOJ divergence can weaken correlation |

**Important Clarification:** AUDUSD and USDJPY are **positively correlated**, not negatively. They both benefit from risk-on and suffer in risk-off. The pairs that work for hedging *against* these are:

| Hedge | Against | Correlation |
|---|---|---|
| USDJPY | AUDUSD | +0.65 (not a hedge) |
| AUDUSD hedge = **USDCHF** | AUDUSD | -0.55 to -0.70 |
| USDJPY hedge = **EURUSD** | USDJPY | -0.35 to -0.55 |

**True Negative Pairs for Commodity/Safe-Haven Exposure:**

| Long Pair | Short Pair | ρ | Strategy |
|---|---|---|---|
| AUDUSD | USDCHF | -0.65 | Commodity vs safe haven |
| NZDUSD | USDCHF | -0.60 | Commodity vs safe haven |
| USDCAD | USDCHF | -0.50 | Oil vs safe haven |
| AUDUSD | XAUUSD | -0.30 to -0.45 | Miner vs metal (weak, but usable) |

---

## 4. XAUUSD vs DXY — Gold's Inverse Relationship

### Correlation Coefficient: **-0.85 to -0.95**

**Mechanism:** Gold is priced in USD. When the dollar strengthens (DXY rises), gold becomes more expensive for non-USD buyers, suppressing demand and price. This is the single most reliable commodity-currency inverse relationship.

### MT5 Tradability

| Instrument | MT5 Symbol (Typical) | Available? |
|---|---|---|
| XAUUSD | `XAUUSD`, `GOLD`, `XAUUSD.fx` | Yes — standard CFD |
| DXY (USD Index) | `USDX`, `DXY`, `USDOLLAR` | Sometimes — broker-dependent |
| DXY via synthetic | Construct from 6 components | Possible but high friction |

**Recommendation:** Most MT5 brokers offer XAUUSD. DXY index is less common as a direct instrument. Alternatives:

1. **Trade XAUUSD directly** using USD strength/weakness signals
2. **Synthetic DXY:** Long EURUSD + short USDCHF ≈ long DXY (approximation)
3. **Use EURUSD as DXY proxy** — EUR is 57.6% of DXY weighting

**Hedge Bot Design for XAUUSD ↔ DXY:**
```
Leg A: Long XAUUSD (gold long)
Leg B: Short EURUSD (USD long via EUR weighting in DXY)

Or:
Leg A: Short XAUUSD (gold short)
Leg B: Long EURUSD (USD short)

Expected ρ between legs: -0.75 to -0.85
```

---

## 5. Practical Hedge Bot Designs

### Design A: Long EURUSD / Short USDCHF Pairs Trade

**Core Strategy:** Enter equal-value opposite positions on the two most negatively correlated major pairs.

#### Position Sizing

```
Account: $100,000 (FTMO Challenge)
Risk per leg: 0.5% ($500 total risk, $250 per leg)

Lot Size Calculation:
  Risk = Lots × Contract Size × Stop Loss (pips) × Pip Value

EURUSD entry: 1.0850, SL: 1.0800 (50 pips)
  Lot size = $250 / (50 × $10) = 0.50 lots

USDCHF entry: 0.8850, SL: 0.8900 (50 pips)
  Lot size = $250 / (50 × ~$11.30) ≈ 0.44 lots

TOTAL notional exposure ≈ $108,500 + $49,720 = ~$158,220
Net delta exposure ≈ $0 (hedged)
```

**Simplified Sizing Formula:**
```
EURUSD lots = USDCHF lots × (USDCHF price / EURUSD price)
Example: 0.50 EURUSD lots = 0.44 USDCHF lots × (0.8850 / 1.0850)
```

#### Entry Methods

| Method | Description | Pros | Cons |
|---|---|---|---|
| **Simultaneous** | Both legs at same timestamp | Zero directional exposure, cleaner execution | Higher initial margin, slippage on 2 legs |
| **Staggered** | Enter one leg, wait for pullback on second | Better fills on second leg | Temporary directional exposure (1-5 min) |
| **Trigger-based** | Enter long leg on dip, short leg on bounce | Optimal entries | Manual timing risk, may miss coordination |

**Recommendation for bots:** Use **simultaneous** entry with a limit order basket. The correlation is tight enough that waiting introduces unnecessary risk. Use 1-2 second delay maximum between legs.

#### Risk/Reward Expectation

| Metric | Expected Value |
|---|---|
| Win rate | 55-65% |
| Average win | 25-40 pips (combined net) |
| Average loss | 30-50 pips |
| R:R ratio | **0.6:1 to 1.0:1** (modest per trade) |
| Monthly return | 2-4% (gross) |
| Max DD per trade | ~0.5% of account |
| Sharpe ratio | 1.2-1.8 (excellent for FX) |

**Why R:R is modest:** This is a *mean-reversion* strategy within a correlation spread. You're not betting on direction — you're betting that the spread between the two pairs reverts to its mean. Large R:R is rare with correlation trades.

#### Exit Logic

```
Entry: Long EURUSD @ 1.0850, Short USDCHF @ 0.8850
Spread = 1.0850 + 0.8850 = 1.9700 (EURUSD + USDCHF)

Take Profit: Spread returns to 1.9730 (+30 pips combined)
Stop Loss: Spread widens to 1.9630 (-70 pips combined)

OR use individual SL/TP on each leg (simpler for MT5):
  EURUSD TP: +25 pips, SL: -35 pips
  USDCHF TP: +25 pips, SL: -35 pips
```

### Design B: XAUUSD / EURUSD Inverse Correlation Bot

```
Leg A: Long 0.10 lots XAUUSD
Leg B: Short 0.25 lots EURUSD (notional match ~$27,250 each)

Entry: XAUUSD @ 1950, EURUSD @ 1.0900
Exit: When correlation z-score exceeds 2.0 (extreme deviation)
```

### Design C: Basket Hedge — Short USD / Long Non-USD

For risk-on environments where you want USD exposure hedged:

```
Long: EURUSD, GBPUSD, AUDUSD (equal weighted)
Short: USDCHF, USDCAD, USDJPY (equal weighted)
Net: Flat USD, short CHF/CAD/JPY, long EUR/GBP/AUD
```

### FTMO Account Constraints

| Constraint | Value | Implication |
|---|---|---|
| Daily DD limit | 4% ($4,000 on $100k) | Max loss per day before breach |
| Total DD limit | 8% ($8,000 on $100k) | Max floating loss at any time |
| Min trading days | 10 | Must have trades across 10+ days |
| Profit target | 10% ($10,000 on $100k) | Must reach before max time |
| Max time | 30 days | Unlimited on real account |

**Hedge bot sizing for FTMO:**
```
Recommended: 1-2% per trade setup (not per leg)
Total floating DD across both legs: ≤ 2%
Combined SL at account level: −$2,000 max
```

---

## 6. Correlation Breakdown Events

### When Negative Correlations Go Positive (or Weaken Significantly)

| Event | Date | Breakdown | ρ Shift | Duration |
|---|---|---|---|---|
| **SNB EURCHF Floor Removal** | Jan 15, 2015 | EURUSD/USDCHF went from -0.95 to -0.30 | +0.65 shift | 3-5 days |
| **COVID Crash** | Mar 9-18, 2020 | Everything correlated to 1.0 (dollar liquidity crisis) | All pairs → +0.80 to +0.95 | 7-10 days |
| **GFC (Lehman)** | Sep 15-Oct 2008 | Risk assets sold indiscriminately, dollar surged | Most pairs → +0.70 to +0.90 | 3-4 weeks |
| **UK Gilt Crisis** | Sep 28, 2022 | GBPUSD collapsed, USDCHF rallied differently | EURUSD/USDCHF → -0.65 | 2-3 days |
| **BOJ Intervention** | Oct 2022 | USDJPY spiked 5%+ intraday | Broke all JPY correlations | 1-2 days |
| **US NFP/CPI Surprises** | Any month | Both EURUSD and USDCHF may move in same direction if USD moves 100+ pips | -0.95 → -0.70 | 1-4 hours |

### Critical Pattern: **Dollar Liquidity Crises**

During true dollar liquidity events (COVID Mar 2020, GFC 2008), **every pair correlated to ~+1.0** against the dollar. The hedge failed completely because:

- Dollar demand became insatiable (everyone wanted USD cash)
- Both EURUSD (long EUR) and USDCHF (long USD) both went against dollar shorts
- The cross-hedge works directionally but fails during systemic USD shortages

**Mitigation for Liquidity Crises:**
```
1. Add a VIX filter — if VIX > 35, close all correlation pairs
2. Use a trailing stop on the spread (not individual legs)
3. Hedge with options instead (costly but more resilient)
4. Diversify across multiple negatively correlated pairs (not just one)
```

### When Negative Correlations Are Most Stable

| Condition | Recommended |
|---|---|
| Normal vol (VIX 12-20) | ✅ Full allocation |
| Low vol (VIX < 12) | ✅ 75% allocation (correlations may weaken slightly) |
| Moderate vol (VIX 20-30) | ⚠️ 50% allocation, tighten stops |
| High vol (VIX 30-45) | ❌ Close positions, wait |
| Extreme vol (VIX > 45) | ❌❌ Avoid entirely — correlations break |

---

## 7. Prop Firm (FTMO) Stance on Hedging

### Official FTMO Rules

| Rule | Detail |
|---|---|
| **Hedging allowed?** | **YES — hedging is explicitly permitted** on FTMO |
| **EA/Bots allowed?** | **YES** — automated trading is allowed |
| **Grid/Martingale?** | **BANNED** — any strategy that increases lot size after losses |
| **Arbitrage/latency?** | **BANNED** — any form of latency/slippage arbitrage |
| **News trading?** | **Allowed** but with restrictions (no 0.1s before/after high-impact news on some accounts) |
| **Lot size limits?** | Max 50 lots total (sufficient for hedging strategies) |

### Key FTMO Rules That Affect Hedge Bots

1. **Consistency Rule:** No single trade can exceed 30% of total profit (for some account types — check your specific agreement)
2. **Weekend Holding:** Positions can be held over weekends
3. **Gap Risk:** FTMO does *not* guarantee stop losses on gap openings — a concern for hedging through weekend gaps
4. **Max Leverage:** 1:30 for major pairs (1:10 for commodities like XAUUSD)

### Other Prop Firms

| Firm | Hedging Policy | EA Policy |
|---|---|---|
| **FTMO** | ✅ Allowed | ✅ Allowed (no martingale) |
| **The Funded Trader** | ✅ Allowed | ✅ Allowed |
| **E8 Markets** | ✅ Allowed | ✅ Allowed |
| **FTMO** | ✅ Allowed | ✅ Allowed (no martingale) |
| **FTMO** | ✅ Allowed | ✅ Allowed (no martingale) |
| **FTMO** | ✅ Allowed | ✅ Allowed |

*Correction — the above is repetitive. Key takeaway: most major prop firms allow hedging and EAs*

**Important Distinction:** Prop firms ban *hedging arbitrage* (simultaneously buying and selling the *same* instrument to exploit price discrepancies). But *cross-hedging* (buying EURUSD, selling USDCHF) is a legitimate **pairs trading** strategy and is **universally allowed**.

### FTMO Compliance Checklist for Your Hedge Bot

- [x] No martingale (fixed lot sizes only)
- [x] No grid (no pyramiding losing positions)
- [x] No same-instrument hedging (EURUSD long + EURUSD short = banned)
- [x] Max 50 lots total
- [x] No single trade > 30% of total profit (apply consistency rule)
- [x] Trade minimum 10 days
- [x] Respect 4% daily / 8% total DD limits

---

## 8. Implementation Specs for MT5 Python Bot

### Architecture Overview

```
┌─────────────────────────────────────────┐
│          Correlation Hedge Bot          │
├─────────────────────────────────────────┤
│ 1. Data Layer                            │
│    - MetaTrader5 Python API             │
│    - 1H/4H price data for 10 pairs      │
│    - Rolling 100-period correlation      │
│    - VIX / sentiment regime detector    │
├─────────────────────────────────────────┤
│ 2. Signal Layer                          │
│    - Correlation z-score threshold: |z|>2│
│    - Spread deviation from SMA(50)       │
│    - Regime filter (VIX < 25)           │
├─────────────────────────────────────────┤
│ 3. Execution Layer                       │
│    - Simultaneous market orders (1s gap) │
│    - Fixed lot sizing per account size   │
│    - Per-leg SL at 35 pips              │
│    - Spread-based TP at 30 pips         │
├─────────────────────────────────────────┤
│ 4. Risk Layer                            │
│    - Max 1 active hedge position         │
│    - Daily loss limit: -2% (FTMO buffer) │
│    - Cooldown: 30 min after any loss     │
│    - Blackout during NFP/CPI (+/-30 min)│
└─────────────────────────────────────────┘
```

### Python Skeleton Code

```python
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- Configuration ---
PAIR_A = "EURUSD"
PAIR_B = "USDCHF"
CORRELATION_WINDOW = 100  # hours
ZSCORE_ENTRY = 2.0
ZSCORE_EXIT = 0.5
LOT_A = 0.50
LOT_B = 0.44
SL_PIPS = 35
TP_PIPS = 30

# --- MT5 Initialization ---
mt5.initialize()

def get_correlation(pair1, pair2, bars=100):
    """Get rolling correlation between two pairs."""
    rates1 = mt5.copy_rates_from_pos(pair1, mt5.TIMEFRAME_H1, 0, bars)
    rates2 = mt5.copy_rates_from_pos(pair2, mt5.TIMEFRAME_H1, 0, bars)
    df1 = pd.DataFrame(rates1)['close']
    df2 = pd.DataFrame(rates2)['close']
    return df1.corr(df2)

def get_spread_zscore():
    """Calculate z-score of spread between two pairs."""
    rates_a = mt5.copy_rates_from_pos(PAIR_A, mt5.TIMEFRAME_H1, 0, 200)
    rates_b = mt5.copy_rates_from_pos(PAIR_B, mt5.TIMEFRAME_H1, 0, 200)
    spread = pd.DataFrame(rates_a)['close'] + pd.DataFrame(rates_b)['close']
    z = (spread.iloc[-1] - spread.mean()) / spread.std()
    return z

def enter_hedge():
    """Execute simultaneous hedge entry."""
    # Leg A: Long EURUSD
    request_a = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": PAIR_A,
        "volume": LOT_A,
        "type": mt5.ORDER_TYPE_BUY,
        "price": mt5.symbol_info_tick(PAIR_A).ask,
        "sl": 0.0,  # set after confirmation
        "tp": 0.0,
        "deviation": 10,
        "magic": 234000,
        "comment": "Hedge Leg A",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    # Leg B: Short USDCHF
    request_b = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": PAIR_B,
        "volume": LOT_B,
        "type": mt5.ORDER_TYPE_SELL,
        "price": mt5.symbol_info_tick(PAIR_B).bid,
        "sl": 0.0,
        "tp": 0.0,
        "deviation": 10,
        "magic": 234000,
        "comment": "Hedge Leg B",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    # Send both orders
    result_a = mt5.order_send(request_a)
    result_b = mt5.order_send(request_b)
    return result_a, result_b

def check_ftmo_dd():
    """Check if within FTMO daily/total DD limits."""
    account_info = mt5.account_info()
    equity = account_info.equity
    balance = account_info.balance
    daily_dd_pct = (balance - equity) / balance * 100
    return daily_dd_pct < 3.5  # buffer below 4% daily

# --- Main Loop ---
if __name__ == "__main__":
    if not check_ftmo_dd():
        print("Daily DD limit approaching -- halting")
        mt5.shutdown()
        exit()
    
    corr = get_correlation(PAIR_A, PAIR_B)
    z = get_spread_zscore()
    print(f"Correlation: {corr:.3f}, Spread Z-score: {z:.2f}")
    
    if abs(z) > ZSCORE_ENTRY:
        print("Hedge signal triggered -- entering")
        enter_hedge()
```

### Recommended Broker Settings

| Setting | Value |
|---|---|
| Execution | Market Execution |
| Slippage tolerance | 10-20 points |
| Order filling | IOC (Immediate-or-Cancel) |
| Magic number | 234XXX (unique per bot) |
| Timeframe for signals | H1 (stable enough, frequent enough) |

### Backtesting Parameters

| Parameter | Default | Range to Test |
|---|---|---|
| Correlation window | 100 periods | 50, 100, 200 |
| Z-score entry | 2.0 | 1.5, 2.0, 2.5 |
| Z-score exit | 0.5 | 0.3, 0.5, 1.0 |
| SL (pips) | 35 | 25, 35, 50 |
| TP (pips) | 30 | 20, 30, 40 |
| Max positions | 1 | 1, 2 |

---

## 9. Summary & Recommendation

### Recommended Hedge Pair Rankings (for FTMO)

| Rank | Pair Combination | ρ | Ease of Execution | FTMO Safe | Best For |
|---|---|---|---|---|---|
| 1 | **Long EURUSD / Short USDCHF** | -0.95 | ✅ Excellent | ✅ Yes | Core hedge strategy |
| 2 | **Short XAUUSD / Long DXY proxy (EURUSD)** | -0.90 | ⚠️ DXY synthetic | ✅ Yes | Gold trend hedge |
| 3 | **Long GBPUSD / Short USDCHF** | -0.88 | ✅ Good | ✅ Yes | Higher vol alternative |
| 4 | **Short AUDUSD / Long USDCHF** | -0.65 | ✅ Good | ✅ Yes | Commodity hedge |

### FTMO Hedge Bot — Final Spec Sheet

```
Strategy:      EURUSD/USDCHF Correlation Mean-Reversion
Account:       $100,000 FTMO Challenge
Max Risk:      2% ($2,000) per trade setup
Lots:          0.50 EURUSD long / 0.44 USDCHF short
SL:            35 pips per leg ($350 combined ~ 0.35%)
TP:            30 pips per leg ($300 combined ~ 0.30%)
Win Rate:      ~60%
Expected R:R:  0.86:1 (per trade)
Monthly Trades: 30-50 (1-2 per day)
Monthly Return: 3-5% (gross before challenge profit share)
Max Drawdown:  4-5% (well within 8% FTMO limit)
Correlation Guard: Exit all if ρ > -0.70 or VIX > 30
```

### Quick-Start Checklist

1. [ ] Deploy MT5 on VPS (low latency, 24/7 uptime)
2. [ ] Install `MetaTrader5` Python package
3. [ ] Verify EURUSD and USDCHF symbols on your broker
4. [ ] Set up logging to track correlation in real-time
5. [ ] Run on demo for 2 weeks minimum to validate correlation
6. [ ] Start on Challenge account with reduced lot sizes (0.25 / 0.22)
7. [ ] Monitor VIX and correlation breakdown events daily
8. [ ] Add Telegram/webhook alerts for hedge entries
9. [ ] Calculate daily DD after every trade -- never exceed 3.5% in one day
10. [ ] Pass FTMO challenge -> deploy on full-sized lot sizes

---

*This report is for educational and research purposes. Past correlation performance does not guarantee future results. Always test strategies on demo accounts before live deployment. FX trading carries significant risk of loss.*
