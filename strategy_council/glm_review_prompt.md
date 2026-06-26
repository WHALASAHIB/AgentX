You are a hedge fund strategy analyst reviewing a prop firm passing strategy. Do NOT be nice — be critical. Find every weakness.

## Strategy: Propfirm Pass Strategy v8

SYMBOL: EURUSD
TIMEFRAME: 1-minute (entry), 5-minute (rejection candle)
SESSION: US Open 13:00-15:00 UTC, Monday-Friday

### Entry Logic
1. Calculate 1-hour VWAP from M1 bars
2. Check if price deviated >= 10 pips from VWAP
3. Check last 5 completed 1M bars forming a 5-minute candle
4. Look for rejection candle:
   - Pin bar: Wick > 1.5x body, body < 40% of range
   - Doji: Body < 10% of range
5. Momentum filter: Skip if candle body > 60% of range (trend candle)
6. Buy if price below VWAP + bullish rejection; Sell if price above VWAP + bearish rejection
7. Doji + direction from VWAP deviation

### Exit Logic
- SL: Fixed 12 pips
- TP: Fixed 24 pips (1:2 RR)
- No trailing stop, no breakeven

### Risk Management
- Risk: 0.5% per trade (or 1% — USER IS CONSIDERING)
- Max 2 trades/day total
- Stop after 2 consecutive losses
- News blackout: 60 min before high-impact events

### Target
- FTMO 1-Phase $10K
- 10% profit target ($1,000)
- 4% daily DD limit, 8% total DD limit

### Backtest Results (3 months of M1 data, Mar-Jun 2026)
- 5 trades, 60% WR, 3.00 PF, $201 PnL, 0.98% max DD
- All trades from US session
- Small sample — limited statistical confidence

### Risk/Reward Questions
USER IS CONSIDERING:
A) 1% risk instead of 0.5%
B) 1:3 or 1:4 RR instead of 1:2

### What I want from you:

1. **CRITIQUE THE STRATEGY** — What are the top 3 weaknesses? Be brutally honest.

2. **1% RISK ASSESSMENT** — At 1%:
   - Risk per trade: $100
   - Win per trade: $200 (1:2)
   - 2 consecutive losses = $200 (2% daily DD, still under 4%)
   - 4 consecutive losses = $400 (hits 4% daily LIMIT)
   - 8 consecutive losses = $800 (hits 8% total stop-out)
   - Max losing streak in backtest: 2
   - **Would you approve 1% risk?** Why or why not?

3. **RR RATIO ANALYSIS** — For this VWAP mean reversion strategy:
   - If we keep 12 pip SL but widen TP to 36 pips (1:3), the win rate will DROP because the market needs to move further past VWAP
   - Mean reversion typically snaps back ~8-15 pips then stalls
   - A 24-pip TP is already aggressive for mean reversion
   - **Would 1:3 or 1:4 work for this strategy?** Or is 1:2 optimal?

4. **FORWARD TEST DESIGN** — The user wants:
   - Fresh account (clean slate)
   - Only this one bot running
   - Start Monday
   - How many trades before we can evaluate if it works?
   - What metrics to track?

5. **FINAL VERDICT** — Would you deploy this on a real $10K FTMO account? Yes/no/conditional?
