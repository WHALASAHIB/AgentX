# Product Requirements Document — Edge Discovery Loop

## 1. Purpose
A systematic, recurring (every 6h) brute-force scan across all technical indicators × parameters × 8 instruments × 5 timeframes to discover **genuine, explainable statistical edges** — not overfitted backtest porn.

## 2. Core Philosophy
> **"How would I make money from someone losing it?"**

Every edge must answer:
- Who is on the other side of this trade?
- Why are they taking the losing side?
- What market microstructure or behavioral bias creates this asymmetry?
- Is this edge structural (will persist) or ephemeral (will decay)?

## 3. Scope

### Instruments (8) — ONE PER RUN (rotating)
EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD, XAUUSD

Each 6h run focuses on ONE pair in rotation. Full cycle completes in ~2 days.

### Timeframes (5) — All from M1 resample
M5, M15, H1, H4, D1

### Data Source
MT5 `copy_rates_from_pos()` with 99,999 bar limit.
Cache refreshed every run.

**Actual depth achieved:**
| TF | Bars | Span |
|----|------|------|
| M5 | 99,999 | ~1.3 years |
| M15 | 99,999 | ~4.0 years ✅ |
| H1 | 99,999 | ~16 years ✅ |
| H4 | ~41,000 | ~26 years ✅ |
| D1 | ~6,800 | ~26 years ✅ |

M15+ meets the 3-year minimum. M5 is shorter but still meaningful (~1.3 years).

### Run Schedule
Every 6h during session hours (07:00, 13:00, 19:00, 01:00 HKT)
One pair per run. Rotation: EURUSD → GBPUSD → USDJPY → USDCHF → USDCAD → AUDUSD → NZDUSD → XAUUSD → repeat.

### Performance Metrics
- Win Rate, Profit Factor, Sharpe Ratio, Avg Win/Loss
- Max Consecutive Losses, Max Drawdown
- Statistical significance (z-score, t-test p-value)
- Walk-forward consistency (split data into 3 periods)

## 4. Out of Scope (v1.0)
- Machine learning / deep learning models
- Order flow / tick-level data
- Fundamental / macroeconomic factors
- Sentiment analysis from news/social media

## 5. Success Criteria
- One scan completes in < 15 min
- Top 3 edges are reproducible (hold in walk-forward)
- Each edge has a documented economic rationale
- Council consensus score ≥ 70/100 to be "actionable"
- Edge decay tracking — alert if edge degrades > 20% from discovery baseline
