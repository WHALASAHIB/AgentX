# AGENTX — Strategy Assignments

> Generated from comprehensive backtesting (45 combos on 9 pairs)
> Date: 2025-06-18

---

## Overview

**MACD Crossover** is the dominant strategy — STRONG YES on ALL 9 pairs.
**Gold Phoenix** is strong on 5 pairs (XAUUSD, EURUSD, GBPUSD, USDCAD, BTCUSD).
For pairs where Gold Phoenix is weak or uncertain, Bollinger Bands or SMA Crossover are used as secondary strategies.

---

## Pair Assignments

### 1. XAUUSD — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780001 | 1.0% |
| Bot 2 | Gold Phoenix | 780001 | 1.0% |

**Why:** MACD Crossover tested STRONG YES. Gold Phoenix was designed specifically for XAUUSD (FTMO-optimised). Both complement each other — MACD for trend following, Gold Phoenix for multi-signal (Asian break, squeeze, pullback, reversal).

**Expected performance:** High win rate on both strategies. Gold has strong trending properties suited to both approaches.

---

### 2. EURUSD — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780002 | 1.0% |
| Bot 2 | Gold Phoenix | 780002 | 1.0% |

**Why:** MACD Crossover STRONG YES. Gold Phoenix also strong on EURUSD — benefits from session-based breakout logic that captures London/US momentum.

**Expected performance:** Solid, predictable. EURUSD has good liquidity and respects technical levels.

---

### 3. GBPUSD — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780003 | 1.0% |
| Bot 2 | Gold Phoenix | 780003 | 1.0% |

**Why:** MACD Crossover STRONG YES. Gold Phoenix strong on GBPUSD — cable moves well during overlapping London/US sessions.

**Expected performance:** Good, though expect wider spreads during volatile news events.

---

### 4. USDJPY — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780004 | 0.8% |
| Bot 2 | SMA Crossover | 780004 | 0.8% |

**Why:** MACD Crossover STRONG YES. **Gold Phoenix FAILED on USDJPY** — the Asian session breakout logic doesn't translate well to JPY pairs. Replaced with SMA Crossover (EMA 9/21 trend following).

**Risk note:** Max drawdown 21.9% — **use smaller lot sizes** (0.8% risk vs 1.0% default). Monitor closely.

---

### 5. USDCHF — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780005 | 1.0% |
| Bot 2 | Bollinger Bands | 780005 | 1.0% |

**Why:** MACD Crossover STRONG YES. Gold Phoenix only **CAUTIOUS** on USDCHF — replaced with Bollinger Bands mean reversion as secondary.

**Expected performance:** Moderate. USDCHF is often correlated inversely with EURUSD. Bollinger Bands works when the pair is range-bound.

---

### 6. USDCAD — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780006 | 1.0% |
| Bot 2 | Gold Phoenix | 780006 | 1.0% |

**Why:** MACD Crossover STRONG YES. Gold Phoenix strong on USDCAD — captures oil-linked CAD movements during US session.

**Expected performance:** Solid. USDCAD trends well and respects technicals.

---

### 7. AUDUSD — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780007 | 1.0% |
| Bot 2 | Bollinger Bands | 780007 | 1.0% |

**Why:** MACD Crossover STRONG YES. Gold Phoenix only **UNCERTAIN** on AUDUSD — replaced with Bollinger Bands mean reversion.

**Expected performance:** Moderate. AUDUSD can be range-bound for extended periods. Bollinger Bands catches mean reversions; MACD catches breakouts.

---

### 8. NZDUSD — 2 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780008 | 1.0% |
| Bot 2 | Bollinger Bands | 780008 | 1.0% |

**Why:** MACD Crossover STRONG YES. Gold Phoenix NOT recommended for NZDUSD. Bollinger Bands mean reversion is the secondary choice.

**Expected performance:** Moderate. NZDUSD is lower volatility, appreciates Bollinger Bands range trading.

---

### 9. BTCUSD — 3 Bots
| Bot | Strategy | Magic | Risk |
|-----|----------|-------|------|
| Bot 1 | MACD Crossover | 780009 | 1.0% |
| Bot 2 | Gold Phoenix | 780009 | 1.0% |
| Bot 3 | SMA Crossover | 780009 | 1.0% |

**Why:** MACD Crossover STRONG YES. Gold Phoenix strong on BTCUSD (works well on volatile move-heavy assets). SMA Crossover also effective on BTCUSD — crypto trends are persistent and SMA/EMA crossovers capture them well.

**Expected performance:** Best opportunity set of all pairs. Crypto has strong trending properties. SMA Crossover (weak on forex) shines here.

---

## Risk Summary

| Pair | Max DD Warning | Risk Adj. | Notes |
|------|---------------|-----------|-------|
| USDJPY | 21.9% | 0.8% risk | Reduce lot size, active monitoring |
| All others | N/A | 1.0% risk | Standard risk profile |

## Bot Architecture

- **Template:** `C:\Trading\bots\multi_symbol_bot.py`
- **Per-pair runners:** `C:\Trading\bots\active_bots\<PAIR>\run_<strategy>.py`
- **Strategy files:** `C:\Trading\backtester\active_strategies\<PAIR>\<strategy>.py`
- **Logs:** `C:\Trading\bots\logs\<symbol>_<strategy>.log`
- **Archived strategies:** `C:\Trading\backtester\old_strategies\`

### Running a bot

Direct:
```
python C:\Trading\bots\multi_symbol_bot.py --symbol XAUUSD --strategy macd
```

Via per-pair wrapper:
```
python C:\Trading\bots\active_bots\XAUUSD\run_macd.py
```
