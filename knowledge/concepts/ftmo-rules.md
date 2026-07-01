# FTMO Challenge Rules — AgentX Trading System

> **Source**: BASELINE.md, strategy_council/glm_review_prompt.md,
>   strategy_council/mistakes_ledger.json, bots/risk_sizing.py

## Connected FTMO Accounts

| ID | Login | Server | Balance (2026-07-01) |
|----|-------|--------|---------------------|
| `ftmo-10k` | 1513767391 | FTMO-Demo | $9,076.69 |
| `ftmo-100k` | 1513845007 | FTMO-Demo | $100,000.00 |

Both accounts are on **FTMO-Demo** server. The coordinator runs in **single-account mode** — only the active account is refreshed. Switch accounts via the website's Switch button.

## Default (Demo) Account

| ID | Login | Server | Balance |
|----|-------|--------|---------|
| `mt5-demo` | 5051185832 | MetaQuotes-Demo | ~$97,107.53 |

## FTMO Challenge Rules (1-Phase $10K)

From the Propfirm Pass v8 strategy review:

| Rule | Value |
|------|-------|
| Challenge type | 1-Phase |
| Account size | $10,000 |
| Profit target | 10% ($1,000) |
| Daily drawdown limit | 4% of equity at day start |
| Total drawdown limit | 8% of initial balance |
| Risk per trade (recommended) | 0.5% ($50) |
| Max trades per day | 2 |
| Stop after consecutive losses | 2 |

## FTMO Standard Rules (for $100K and general)

| Rule | Limit |
|------|-------|
| Daily loss limit | 5% of initial balance |
| Max drawdown | 10% of initial balance (static) |
| Leverage | Up to 1:30 (Forex) |
| Min trading days | 10 days (1-Phase) |

**Critical distinction**: FTMO uses **static drawdown** (relative to initial balance), NOT trailing drawdown. The risk supervisor must track both.

## Emergency Stop Rules (from mistakes ledger)

1. **Auto-pause ALL bots** when drawdown reaches 8% static DD
2. **Send emergency alert** at 9% static DD
3. FTMO risk desk actively intervenes (closes positions with `CLOSED_BY_FTMO` comment)
4. **FTMO liquidates at 10% static drawdown** — no exceptions

## Multi-Pair Bot Restrictions on FTMO

- Multi-pair MACD bots (magic 200100, 200200) are designed for **unlimited demo**, NOT FTMO challenges
- These bots have 0% win rate in FTMO testing (0-for-23 trades, -$356 combined)
- **Rule**: When risk state is REDUCE and drawdown > 8%, ALL bots on FTMO must be paused

## Drawdown Tracking Requirements

From incident analysis (mistakes_ledger.json):

1. Risk supervisor must track **BOTH trailing and static drawdown**
2. Emergency stop triggers at **8% STATIC DD**, not 8% trailing DD
3. The static DD must be computed relative to **initial FTMO balance**, not account equity

## Propfirm Pass Strategy (EURUSD)

| Parameter | Value |
|-----------|-------|
| Symbol | EURUSD |
| Entry TF | 1-minute |
| Rejection TF | 5-minute |
| Session | US Open 13:00-15:00 UTC, Mon-Fri |
| Strategy | VWAP mean reversion |
| SL | 12 pips (fixed) |
| TP | 24 pips (fixed, 1:2 RR) |
| Risk | 0.5% per trade |
| Max trades/day | 2 |
| Stop after | 2 consecutive losses |
| News blackout | 60 min before high-impact events |

### Entry Logic (Propfirm Pass v8)
1. Calculate 1-hour VWAP from M1 bars
2. Check if price deviated >= 10 pips from VWAP
3. Check last 5 completed 1M bars forming a 5-minute candle
4. Look for rejection candle (pin bar or doji)
5. Momentum filter: skip if candle body > 60% of range
6. Buy if price below VWAP + bullish rejection; Sell if above + bearish rejection

## FTMO Validation in Position Sizing

From `bots/risk_sizing.py` — the `validate_ftmo_limits()` function checks:

- Daily remaining loss budget >= proposed trade risk
- Total drawdown remaining budget >= proposed trade risk
- Default daily limit: 5% of account balance
- Default max drawdown: 10% of account balance

## Lesson Learned (from mistakes_ledger)

- **2026-06-25**: Multi-pair MACD bots accumulated -$356 losses on FTMO during REDUCE risk state
- **2026-06-25**: USDJPY positions closed by FTMO risk desk for -$436
- **2026-06-26**: 8.5 lots USDJPY closed by FTMO risk desk after 15-22 min, drawdown reached 9.23%
- **2026-06-23 to 2026-06-26**: 7-day review: 106 trades, -$860.11 PnL on FTMO. MACD bots 0% WR. Gold Phoenix: 2 trades, +$39.96, 100% WR
