import json, datetime

ARCHIVE = 'C:/Trading/research_division/state/research_hypotheses.json'
a = json.load(open(ARCHIVE))

new_ideas = [
    {
        'name': 'Volatility_Parity_Scale',
        'family': 'risk_overlay',
        'instruments': ['XAUUSD'],
        'timeframes': ['H1', 'H4'],
        'description': 'Risk-parity position sizing overlay that dynamically adjusts lot size to keep $ risk-per-trade constant regardless of market volatility. Instead of trading a fixed lot size, this strategy computes trailing 20-period ATR in pips, multiplies by a target risk budget ($250/trade), and derives the exact lot size that caps loss at that budget. The overlay wraps any existing entry signal — the novelty is that risk exposure is inversely proportional to market volatility, preventing account blowup during high-vol events and maximizing capital utilization during quiet periods.',
        'market_behaviour': 'Gold experiences dramatic volatility shifts: NFP and FOMC days can see 5x normal ATR, while Asian-session consolidation can compress ATR to 30% of normal. Fixed-lot trading destroys accounts during spike events and underutilizes capital during quiet periods. The market behaves such that volatility clustering is persistent — a high-vol day is often followed by another high-vol day. This strategy rides the volatility-normalization cycle: when vol spikes, it shrinks exposure to survive; when vol settles, it expands exposure to capitalize on the mean-reverting nature of volatility.',
        'entry_logic': '1. Compute target risk per trade (e.g., $250 = 0.5% of $50K account). 2. Calculate ATR(20) in pips on entry timeframe. 3. Derive lot size = target_risk / (ATR_pips * pip_value). 4. Apply any primary entry signal (e.g., momentum, breakout, or mean-reversion trigger) — the overlay has no directional bias of its own. 5. If computed lot size < minimum lot (0.01), skip trade (volatility too high to risk safely). 6. If computed lot size > maximum lot (e.g., 2.0), cap at maximum and flag position for early partial exit to reduce exposure. 7. Recompute lot size every 4 hours while position is open, adjusting exposure dynamically.',
        'exit_logic': 'SL fixed at 1x ATR from entry (the ATR used for sizing). TP at 2x ATR (fixed risk:reward = 1:2). Trail remaining position at 0.5x ATR after 1x ATR profit. Positions automatically reduce lot size if volatility expands mid-trade (partial close). Hard exit if ATR doubles from entry level (volatility shock — market regime changed).',
        'failure_mode': 'Fails during volatility regime shifts that occur mid-trade — if vol drops sharply, the strategy increases lot size into a fading signal. Also fails if ATR is a poor volatility estimator for the instrument (e.g., gap-driven markets). The overlay cannot protect against fat-tail events exceeding 1 ATR (black swans).',
        'diversification_value': 'ALL existing bots use fixed or percentage-based position sizing. This is the first strategy that makes position sizing the central risk mechanism rather than an afterthought. It can be layered over ANY of the existing strategies without changing their entry logic, giving it unique portfolio value as a meta-overlay rather than a competing signal.',
        'self_grade': 'A-',
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    },
    {
        'name': 'Gold_Seasonal_Cycle',
        'family': 'seasonal',
        'instruments': ['XAUUSD'],
        'timeframes': ['D1', 'W1'],
        'description': 'Exploits well-documented seasonal patterns in gold prices driven by physical demand cycles: Indian wedding season (Oct-Dec, largest gold consumer globally), Chinese New Year (Jan-Feb, second-largest consumer), central bank accumulation patterns, and jewelry fabrication cycles. The strategy builds a 10-year rolling seasonal composite of daily gold returns, identifies weeks where the historical probability of positive returns exceeds 65%, and takes directional positions aligned with the seasonal tailwind. Enters 5 days before the high-probability window and holds through its duration.',
        'market_behaviour': 'Gold has strong, statistically significant seasonal patterns. Prices typically rally from late July through September (jewelry fabrication for Diwali/Christmas), dip in October (tactical buying opportunity), rally again November-December (Indian wedding season + Diwali + Christmas fabrication), and see a second rally in January-February (Chinese New Year). March-April is weak (post-holiday demand lull, spring cleaning). May-June is mixed with occasional dips as physical demand ebbs before the autumn pickup. These patterns are driven by real physical flows (jewelry, bars, coins, central bank reserves), not speculative positioning, giving them persistent structural validity.',
        'entry_logic': '1. Build 10-year rolling daily seasonal composite (average % return for each calendar day over past 10 years, excluding current year). 2. Compute weekly aggregated seasonal probability: % of past 10 years where the week had a positive return. 3. Filter to weeks with >=65% historical probability of positive return. 4. Entry: 5 days before the start of a high-probability week (to capture early positioning). 5. Direction can be long or short — identify weeks with >=65% probability of negative returns (historically Mar-Apr) for short-side trades. 6. Confirm with: current week must not have extreme positioning (CFTC COT report net speculative length within 1 standard deviation of 3-year mean) — prevents fading crowded trades. 7. Exit: at close of the target week (Friday close).',
        'exit_logic': 'Hold period = 2 weeks maximum (entry week + target week). SL at 2x ATR(14) on D1. TP defined by seasonal composite: exit when cumulative return reaches the 10-year median return for the target window. Time-stop: exit at Friday close of target week regardless of P&L. No re-entry for same seasonal window if already stopped out.',
        'failure_mode': 'Fails during structural regime changes that break seasonality — e.g., gold was repressed in 1999-2005 (central bank selling, strong USD), breaking all seasonal patterns. Also fails during black-swan crises where macro dominates physical flows (COVID March 2020, 2008 financial crisis). Needs at least 5 years of data to be meaningful. Less effective on synthetic products (gold ETFs vs. physical).',
        'diversification_value': 'Radically different from every existing strategy. All current bots use price action, volatility, or correlation signals on intraday-to-daily timeframes. This is the only strategy operating on weekly/monthly calendars with 10-year lookbacks. It generates signals that are COMPLETELY uncorrelated with technical approaches — a seasonal long signal in November has no relation to what ADX, ATR, or Bollinger Bands are saying. This is the highest-diversification-value addition to the archive.',
        'self_grade': 'B',
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    },
    {
        'name': 'OrderFlow_Imbalance_Scalper',
        'family': 'other',
        'instruments': ['XAUUSD'],
        'timeframes': ['M1', 'M5'],
        'description': 'Tick-volume order flow scalper that exploits short-term directional imbalance in gold futures (or spot tick data). Uses cumulative delta (buy volume minus sell volume at the ask/bid) and delta divergence against price to identify imminent micro-reversals and momentum surges. When price is making lower highs but cumulative delta is making higher highs (bullish divergence), the strategy enters long. When price is making higher highs but delta is declining (bearish divergence), it enters short. The core insight is that order flow reveals institutional aggression before price action does — delta diverges from price by 2-5 seconds on average, enough for a scalping edge.',
        'market_behaviour': 'Gold during high-volume sessions (London open, US open, NFP) exhibits tick-level micro-structure where institutional orders (500+ lot block trades) appear at the bid/ask before price moves. The cumulative delta (cumulative sum of (trades at ask - trades at bid) over a rolling window) reveals buying/selling pressure that is invisible on OHLC charts. During news events, delta spikes ahead of price by 1-3 seconds. During normal trading, delta divergence against price (price up, delta down = distribution) predicts reversals with 60-65% accuracy on M1. Gold is particularly well-suited because it has deep liquidity and clear institutional footprint compared to FX crosses.',
        'entry_logic': '1. Compute cumulative delta over rolling 5-minute window: delta = sum(trades at ask - trades at bid). 2. Compute 20-period SMA of delta and 20-period SMA of price (M1 close). 3. Bullish entry (long): price makes a lower low than 5 bars ago BUT delta SMA is making a higher low (delta divergence). Enter at market on next tick after confirmation. 4. Bearish entry (short): price makes a higher high than 5 bars ago BUT delta SMA is making a lower high (delta divergence). Enter at market. 5. Volume filter: entry only if tick volume in the current minute exceeds 1.5x the 20-minute average tick volume (high institutional activity). 6. Skip if less than 30 minutes until a major economic release (FOMC, NFP, CPI) — order flow becomes erratic.',
        'exit_logic': 'Fixed TP = 5 pips (tight target, high win rate). SL = 8 pips (wider than TP for unfavorable R:R, but win rate >=60% justifies it). Time-stop: exit after 3 minutes if TP not hit (order flow edge decays quickly). Re-entry allowed after 10-minute cooldown if divergence re-forms. Maximum 3 trades per hour to avoid over-trading.',
        'failure_mode': 'Requires tick-level data (bid/ask prices or market depth) which may not be available from all brokers. Most retail brokers provide synthetic ticks that lag or lack true order flow information. Spread costs eat heavily into 5-pip targets — needs low-spread conditions. Fails in low-volume Asian session when delta is unreliable due to thin liquidity.',
        'diversification_value': 'Completely unique in the archive — no other strategy uses tick-level data, order flow, or cumulative delta. Timeframe (M1/M5) is the fastest in the archive. The approach (price-action-agnostic, order-flow-centric) is orthogonal to all existing ideas. Provides ultra-short-term exposure that balances the portfolio\'s bias toward H1-D1 strategies. Highest failure risk but also highest uncorrelated-return potential.',
        'self_grade': 'B-',
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    }
]

for idea in new_ideas:
    if not any(i['name'] == idea['name'] for i in a['ideas']):
        a['ideas'].append(idea)
        a['coverage_map'].setdefault(idea['family'], []).append(idea['name'])
a['metadata']['total_ideas'] = len(a['ideas'])
a['metadata']['families_covered'] = sorted(set(f for f, v in a['coverage_map'].items() if v))
json.dump(a, open(ARCHIVE, 'w'), indent=2)
print(f'SAVED. Total ideas: {a["metadata"]["total_ideas"]}')
print(f'Families covered: {a["metadata"]["families_covered"]}')
for f, ideas in sorted(a['coverage_map'].items()):
    print(f'  {f}: {len(ideas)} ideas')
