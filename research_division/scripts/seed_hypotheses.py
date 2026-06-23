import json
import datetime

ARCHIVE = 'C:/Trading/research_division/state/research_hypotheses.json'
a = json.load(open(ARCHIVE))

new_ideas = [
    {
        'name': 'ATR_Regime_Selector',
        'family': 'regime_filter',
        'instruments': ['XAUUSD'],
        'timeframes': ['H1', 'H4'],
        'description': 'Adaptive strategy that switches between momentum and mean-reversion modes based on trailing 20-bar ATR percentile relative to its 200-bar history. When ATR is above the 70th percentile (high-volatility regime), trade breakouts with wider stops. When ATR is below the 30th percentile (low-volatility regime), trade mean-reversion bounces off HVNs. When ATR is mid-range (30-70th percentile), use a neutral grid scalping approach. This prevents the strategy from fighting the current volatility environment and adapts position sizing dynamically.',
        'market_behaviour': 'Gold (XAUUSD) exhibits clear volatility regimes driven by macro event clusters (NFP, CPI, FOMC), geopolitical shocks, and quiet Asian-session consolidation. During high-volatility regimes, price trends strongly and breakouts follow through. During low-volatility regimes, price oscillates within established ranges and HTF HVNs hold as support/resistance. The transition between regimes (volatility expansion/collapse) often produces the highest-RR trades.',
        'entry_logic': '1. Calculate 20-period ATR and its percentile rank over last 200 periods. 2. If ATR > 70th %ile (high vol): wait for price to break above/below 20-period Donchian channel. Enter on close beyond channel. 3. If ATR < 30th %ile (low vol): identify nearest HTF HVN within 1 ATR of current price. Enter on touch of HVN with conservative H1 momentum confirmation. 4. If mid-range: enter on pullback to VWAP with 5-pip stop, target 10 pips scalping.',
        'exit_logic': 'High-vol regime: SL = 2.5 ATR, TP = 4 ATR. Trail at 1 ATR after 2 ATR profit. Low-vol regime: SL = 1 ATR, TP = 2 ATR. Mid-range: fixed SL 5 pips, TP 10 pips. All regimes: exit immediately if ATR percentile crosses a regime boundary (detects regime shift).',
        'failure_mode': 'Fails during gradual volatility transitions where ATR percentile oscillates around boundaries (70th and 30th), causing churn as the strategy flips between modes. Also fails when volatility is flat for extended periods (ATR stuck at 50th %ile) and the mid-range scalping gets hit by sudden spikes.',
        'diversification_value': 'Unlike fixed-style strategies that only work in their preferred environment, this strategy survives across market conditions by matching style to regime. Most existing bots pick ONE approach and pray for the right environment — this adapts proactively.',
        'self_grade': 'B+',
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    },
    {
        'name': 'DXY_Valence_Correlation',
        'family': 'cross_asset',
        'instruments': ['XAUUSD', 'DXY', 'US10Y'],
        'timeframes': ['H4', 'D1'],
        'description': 'Exploits the inverse correlation between XAUUSD and DXY (USD Index), but only when the correlation is stable. Computes a rolling 40-period Pearson correlation between daily XAUUSD returns and DXY returns. When |correlation| > 0.6, the relationship is reliable and trades are taken based on DXY technical levels. When correlation collapses (< 0.4), XAUUSD is decoupling and this strategy sits out. Also factors in US10Y real yield changes as a secondary confirmatory signal — rising real yields + strong DXY = strong short signal; falling real yields + weak DXY = strong long signal.',
        'market_behaviour': 'Gold trades as the anti-dollar in normal macro environments. During risk-off events, DXY and gold can both rise (flight to safety into both USD and gold) temporarily breaking the inverse correlation. During QE/unconventional policy, the relationship weakens. The most reliable trading periods are when macro drivers are clear (e.g., rate hike cycles vs. rate cut cycles) and the correlation is > 0.6 in magnitude.',
        'entry_logic': '1. Compute rolling 40-period Pearson correlation of XAUUSD and DXY daily returns. 2. IF |correlation| < 0.4: no trade (correlation decay). 3. IF correlation < -0.6 (strong inverse): look for DXY hitting a key support/resistance level on the D1. DXY bounce off resistance -> long XAUUSD. DXY bounce off support -> short XAUUSD. 4. IF correlation > 0.6 (positive anomaly, rare, usually risk-off): DXY breaking resistance -> short XAUUSD; DXY breaking support -> long XAUUSD. 5. Secondary filter: US10Y real yield change over past 5 days must align (rising yields -> bearish gold, falling yields -> bullish gold).',
        'exit_logic': 'TP = 2.5 ATR of XAUUSD on H4. SL = 1.5 ATR. Trailing stop at 1 ATR after 1.5 ATR profit. Hard stop-loss: exit immediately if |correlation| drops below 0.4 intraday (relationship broken, get out).',
        'failure_mode': 'Commodity supercycles where gold decouples from USD entirely (e.g., gold as reserve accumulation independent of dollar). Correlation breakdowns during black-swan risk-off events where both DXY and gold rally simultaneously. Also fails if DXY data feed lags or is misaligned.',
        'diversification_value': 'Virtually all gold strategies are price-only or volatility-only. This is fundamentally different — it trades gold through the lens of its primary macro driver (USD) and even its secondary driver (real yields). It can generate winning trades when gold is range-bound and no price-action signal is present, purely because DXY hit a level.',
        'self_grade': 'A-',
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    },
    {
        'name': 'Volatility_Contraction_Breakout',
        'family': 'volatility',
        'instruments': ['XAUUSD'],
        'timeframes': ['M15', 'H1'],
        'description': 'Bollinger Squeeze / volatility contraction pattern for gold. When Bollinger Bands (20,2) narrow to their tightest 10% range over the trailing 200 periods, it signals impending expansion (volatility breakout). The strategy waits for a confirmed close outside the bands with above-average volume/range to enter. The key innovation: it measures the squeeze using BandWidth = (BB_upper - BB_lower)/BB_middle as a percentage, entering on the first candle that closes outside after BandWidth reaches a local minimum. Works well on gold because gold has strong episodic volatility — quiet periods precede explosive moves (NFP, CPI, geopolitics).',
        'market_behaviour': 'Gold has a distinctive volatility pattern: prolonged compression periods (often during Asian session or pre-news consolidation) followed by violent expansion. The Bollinger Squeeze captures this cycle well. During contraction, both institutions and retail sit on hands awaiting a catalyst. Once triggered, the move is sharp with follow-through because latecomers pile in. The H1 timeframe catches major macro moves; M15 catches intraday news reactions.',
        'entry_logic': '1. Compute Bollinger Bands (20,2) and BandWidth = (Upper - Lower)/Middle * 100. 2. Track trailing 200-period min/max of BandWidth. 3. When BandWidth is within bottom 10% of its 200-period range (squeeze detected), start monitoring. 4. Wait for a candle to CLOSE fully outside either band (above upper or below lower). 5. Confirm with: the breakout candle must have range >= 1.5x the average range of the prior 5 candles. 6. Enter long if close above upper band with confirmation; short if close below lower band with confirmation.',
        'exit_logic': 'Initial TP = 2x the height of the squeeze (BandWidth value at entry * middle price * 2). Initial SL = widest point of the squeeze bands (opposite band). Trail at 1 ATR after initial TP is hit. Hard time-stop: exit if no further 0.5 ATR progress within 8 hours of entry.',
        'failure_mode': 'False breakouts — price squeezes, breaks out briefly, then reverses. These are common when the squeeze precedes low-impact news rather than major catalysts. Also fails in trending markets where bands stay wide and never squeeze, generating no signals.',
        'diversification_value': 'Pure volatility-cycle trading (buying quiet, selling loud) is orthogonal to direction-dependent strategies. It generates signals at entirely different times than trend-following or mean-reversion bots — specifically when everything else is inactive (squeeze) or just entering (the actual breakout). It adds a unique optionality component to the portfolio.',
        'self_grade': 'A-',
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
for f in a['coverage_map']:
    if a['coverage_map'][f]:
        print(f'  {f}: {a["coverage_map"][f]}')
