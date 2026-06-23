import json, datetime

ARCHIVE = 'C:/Trading/research_division/state/research_hypotheses.json'
a = json.load(open(ARCHIVE))
now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

new_ideas = [
    {
        'name': 'MultiTimeframe_Liquidity_Stacked_Breakout',
        'family': 'breakout',
        'instruments': ['XAUUSD'],
        'timeframes': ['M15', 'H1', 'H4'],
        'description': 'Identifies liquidity clusters stacked across H4, H1, and M15 order blocks at converging price levels. When price breaks through all stacked levels with a cascade of increasing volume (volume expansion >1.5x the 20-period average on each successive level break), it confirms genuine institutional absorption rather than retail liquidity grabs. The strategy measures the depth of liquidity at each level using volume profile and enters only when at least two consecutive timeframe levels break with volume confirmation.',
        'market_behaviour': 'Gold exhibits multi-tiered liquidity structures where institutions place clusters of orders at key levels across timeframes. During accumulation, price repeatedly touches and rejects a level with decreasing volume (absorption). When the breakout finally occurs, volume cascades - each broken level releases the next tranche of stop-losses and adds momentum. Retail traders get caught guessing whether the first level break is real, while institutions use multi-level stacking to trap both sides. The Asian-to-London transition is the highest-probability window for this behavior.',
        'entry_logic': '1. Identify order blocks on H4, H1, M15 using standard ICT displacement + FVG methodology. 2. Check if any 2+ timeframes have order blocks overlapping within 0.3 ATR of each other (stacked liquidity zone). 3. Mark the outer boundary of the stacked zone as the trigger line. 4. Wait for price to break the trigger line with the first candle closing beyond it. 5. Confirm volume: the breakout candle range must be >= 1.5x the 20-period average candle range AND the tick volume (or delta) must show net directional dominance (>60% of volume in breakout direction). 6. Enter on the next candle open after confirmation. 7. If only one timeframe level breaks without volume confirmation, skip - treat as a false break.',
        'exit_logic': 'SL = 1.5x ATR(14) on H1 measured from entry. TP1 = 2x ATR on H1 (50% position), TP2 = 4x ATR on H1 (remaining 50%). Trail TP2 at 1x ATR after TP1 is hit. Hard time-stop: exit if no new 0.5 ATR extension within 24 hours. If volume drops below average on any continuation candle after entry, tighten to a breakeven stop.',
        'failure_mode': 'Fails in news-driven spike-and-retrace markets where volume spikes are from retail panic rather than institutional accumulation. Also fails during algorithmic chop where no clean multi-level structure exists - the strategy simply stays flat, which means long periods of inactivity. The multi-TF stacking requirement is a high bar and may miss genuine breakouts that only have one clean level.',
        'diversification_value': 'Unlike single-level breakout strategies or retest-based breakouts, this requires explicit multi-timeframe liquidity stacking with volume cascade confirmation - a fundamentally different trigger condition. It operates in an entirely different signal space than momentum or mean-reversion bots and generates far fewer but higher-conviction signals. Complements existing Volume_Profile_Acceptance_Breakout by adding a stacked liquidity dimension.',
        'self_grade': 'A-',
        'generated_at': now
    },
    {
        'name': 'Gold_USD_Cross_Rate_Carry_Trade_Proxy',
        'family': 'cross_asset',
        'instruments': ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY'],
        'timeframes': ['H4', 'D1'],
        'description': 'Decomposes XAUUSD movements into two components: broad USD directional bias and gold-specific factors. By comparing gold price action against a USD index proxy constructed from the weighted average of EURUSD, GBPUSD, and USDJPY movements, the strategy isolates gold-specific strength/weakness. When gold and the USD proxy move in the same direction (gold rising while USD proxy also rising = gold outperforming USD weakness with additional gold-specific demand), conviction is high. When they diverge (gold rising while USD proxy falling = the move is just USD weakness), position sizing is halved and stops are tighter. This identifies pure alpha in gold rather than just beta from broad dollar moves.',
        'market_behaviour': "Gold's price is composed of roughly 60% USD directional component, 20% real-yield/inflation component, 10% geopolitical risk premium, and 10% residual (COMEX positioning, EM central bank accumulation, etc.). Most traders fail to distinguish between these drivers, taking gold trades that are really just USD trades. By decomposing the move, the strategy can size up when gold has genuine idiosyncratic demand (e.g., central bank buying, geopolitical panic) versus when it is just riding the dollar wave. The highest-RR setups occur when gold is rallying AGAINST a strengthening USD or falling against a weakening USD - these divergence signals precede regime changes in the gold-USD relationship.",
        'entry_logic': "1. Construct a synthetic USD index: USD_proxy = (0.576 * EURUSD + 0.136 * GBPUSD + 0.136 * USDJPY) using D1 returns, re-weighted to replicate DXY correlation. 2. Compute 20-period rolling correlation between XAUUSD D1 returns and USD_proxy returns. 3. ALSO compute 20-period rolling beta: gold_return = alpha + beta * USD_proxy_return + epsilon. 4. If correlation < -0.7 (standard inverse relationship) and beta magnitude > 1.2 (gold amplifies USD moves): standard sizing at 1x, SL = 1.5 ATR. 5. If correlation < -0.7 but beta < 1.0 (gold is muted vs USD moves): the gold-specific component is acting as a drag - HALVE position size. 6. If correlation is WEAK (> -0.5 or positive, meaning gold is moving independently): FULL size allowed because gold has genuine idiosyncratic demand - SL = tighter at 1.0 ATR. 7. Entry direction determined by which way gold breaks its H4 20-EMA after the correlation/beta analysis is complete.",
        'exit_logic': 'Standard regime (step 4): TP = 2.5 ATR, SL = 1.5 ATR on H4. Muted regime (step 5): TP = 1.5 ATR, SL = 1.0 ATR (reduced tolerance). Independent regime (step 6): TP = 3.5 ATR, SL = 1.0 ATR (tight stop, wide target - capture the idiosyncratic move). All regimes: re-evaluate correlation/beta every 5 bars and exit if the regime classification changes (e.g., independent moves back to standard inverse - the idiosyncratic edge is gone).',
        'failure_mode': 'In regime of perfectly predictable inverse correlation (beta ~-1, correlation ~-0.9), this strategy adds no edge over a simple DXY trend-following gold strategy - the decomposition has no divergence to exploit. The independent-move regime also can produce rare false signals (gold rallies on COMEX option expiration flows that reverse the next day). Requires reliable data for all 3 USD crosses which multiplies data feed failure risk.',
        'diversification_value': "Unlike DXY_Valence_Correlation which uses DXY level itself as a trigger, this strategy decomposes the gold-USD relationship into components (USD beta vs gold-specific alpha) and sizes based on which component is driving price. This is a higher-dimensional approach to gold trading that the existing cross_asset family lacks - it does not just use a correlation filter, it extracts and isolates the alpha component of gold moves.",
        'self_grade': 'A-',
        'generated_at': now
    },
    {
        'name': 'Diwali_Chinese_New_Year_Physical_Demand_Frontrun',
        'family': 'seasonal',
        'instruments': ['XAUUSD'],
        'timeframes': ['D1'],
        'description': 'Front-runs the two largest global physical gold buying events: Diwali (Oct-Nov, India accounts for ~25% of global demand) and Chinese New Year (Jan-Feb, China accounts for ~30%). Three weeks before each event, historically gold enters a seasonal accumulation phase driven by wholesale/jewelry sector restocking. After the event, there is a predictable sell-off as physical premiums normalize and speculative longs unwind. The entry window is defined by calendar date with a confirmation filter requiring the 14-period RSI to be below 60 (not already overbought/pre-priced in). Takes profit in two tranches: half before the event, half after the post-event decline materializes.',
        'market_behaviour': "Physical gold demand follows a pronounced seasonal pattern driven by cultural festivals and wedding seasons. India's Diwali (festival of lights) is the single largest gold-buying period globally - households buy gold as auspicious investment and gifts. Chinese New Year drives similar buying for gifting and wealth storage. Wholesalers and jewelers typically begin stockpiling 2-3 weeks before each event, creating sustained upward pressure on spot gold. After the event, demand collapses and speculative longs (who front-ran the event) unwind, creating a 1-2 week retracement. This pattern has been consistent for 20+ years but is often overlooked by algorithmic traders who focus on technical or macro signals.",
        'entry_logic': '1. Calculate Diwali date (variable Oct/Nov based on Hindu lunisolar calendar) and Chinese New Year date (variable Jan/Feb based on Chinese lunisolar calendar). Hard-code the 3-week pre-event windows. 2. 21 calendar days before event (T-21): open entry monitoring. 3. Confirm RSI(14) on D1 is below 60 (not overbought - rally has not been front-run already). 4. Also check that the 20-day ATR is not at its 100-day minimum (avoid entering during extreme volatility compression where gold might be artificially suppressed). 5. Enter long on the first day T-21 to T-7 where D1 closes above the 5-EMA. 6. If RSI > 60 at T-21, wait for a pullback to the 20-EMA before entering - do not chase. 7. If no entry triggered by T-7 before event, skip that event cycle.',
        'exit_logic': 'TP1: Close 50% of position on the D1 candle before the event date (capture pre-event accumulation). TP2: Hold remaining 50% until 7 calendar days after the event date, or until RSI crosses above 75 (extreme overbought = post-event blowoff top), or until D1 closes below the 20-EMA, whichever comes first. SL: 1.5x ATR(14) on D1 from entry - typically 20-30 USD on gold. Hard rule: exit all positions by T+10 (10 days after event) regardless of price - the seasonal edge decays rapidly after that.',
        'failure_mode': 'Fails in years when gold is in a sustained downtrend driven by macro factors (e.g., 2013 taper tantrum where seasonal patterns were overwhelmed by Fed tightening fears). The RSI < 60 filter helps but does not fully protect against macro override. Also fails if central bank gold sales coincide with the seasonal window (though rare since 2022 when central banks switched to net buying). Calendar-based entry means the trade may be well-known and already priced in by sophisticated funds - edge decay is a long-term risk.',
        'diversification_value': 'Completely uncorrelated with technical or volatility-based strategies - this is pure seasonality-driven alpha. Unlike Gold_Seasonal_Cycle (which trades generic monthly patterns) and Monsoon_India_Demand_Frontrun (which ties to monsoon-driven rural income), this targets specific calendar-locked mega-events with defined pre/post windows. It generates only 2-4 trades per year with high win-rate potential, providing stable PnL smoothing that offsets choppy periods from other strategies.',
        'self_grade': 'B+',
        'generated_at': now
    }
]

for idea in new_ideas:
    if not any(i['name'] == idea['name'] for i in a['ideas']):
        a['ideas'].append(idea)
        a['coverage_map'].setdefault(idea['family'], []).append(idea['name'])
    else:
        print(f'WARNING: Duplicate name {idea["name"]} - skipping')

a['metadata']['total_ideas'] = len(a['ideas'])
a['metadata']['families_covered'] = sorted(set(f for f,v in a['coverage_map'].items() if v))
a['metadata']['last_updated'] = now
json.dump(a, open(ARCHIVE, 'w'), indent=2)
print(f'SAVED. Total ideas: {a["metadata"]["total_ideas"]}')
print(f'Families covered: {a["metadata"]["families_covered"]}')
print()
print('Coverage counts:')
for f in sorted(a['coverage_map']):
    print(f'  {f}: {len(a["coverage_map"][f])}')
print()
print('New ideas added:')
for idea in new_ideas:
    print(f'  - {idea["name"]} ({idea["family"]})')