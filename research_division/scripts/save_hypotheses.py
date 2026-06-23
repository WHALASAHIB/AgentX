import json, datetime

ARCHIVE = 'C:/Trading/research_division/state/research_hypotheses.json'
a = json.load(open(ARCHIVE))

new_ideas = [
    {
        'name': 'Markov_Switching_Momentum_Regime',
        'family': 'regime_filter',
        'instruments': ['XAUUSD'],
        'timeframes': ['H1', 'H4'],
        'description': 'Two-state Hidden Markov Model classifies gold as trending (regime 1) or ranging/mean-reverting (regime 2) using daily returns and realized volatility. Momentum entries enabled only in regime 1. Completely absent from existing archive — all 12 regime_filter ideas use ATR, ADX, liquidity, yield curve, or macro proxies, not statistical HMM.',
        'entry_logic': '1. Fit a 2-state Gaussian HMM on 60-day rolling window of (daily log returns, 14-day realized vol). 2. Use Viterbi to decode current state. 3. IF regime=1 (trending): compute 20-period ROC (rate of change) on H1, enter long if ROC > 0.5% and price > 50-EMA, short if ROC < -0.5% and price < 50-EMA. 4. IF regime=2 (mean-reverting): skip all momentum entries. 5. Confirm with ADF test p-value < 0.05 on 50-bar returns (stationarity check for regime 2 exclusion).',
        'exit_logic': 'Stop loss: 1.5x ATR(14) from entry. Take profit: 3.0x ATR for momentum trades. Trailing stop: 1x ATR chandelier after price moves 2x ATR in profit. Regime switch exit: if Viterbi decodes regime change back to mean-reverting while in a momentum trade, flatten 50% of position immediately.',
        'failure_mode': 'HMM can overfit regime boundaries on noisy gold data. Regime persistence bias — once in trending state, slow to switch, causing drawdowns at trend exhaustion. The 60-day rolling window creates lag in regime detection during rapid macro shifts (e.g., surprise rate decisions).',
        'diversification_value': 'Only HMM-based regime filter in the archive. Completely decorrelated from all existing ADX/ATR/macro regime approaches — captures statistical regime structure rather than deterministic threshold-based regimes. Would have near-zero correlation with any existing bot.',
        'self_grade': 'B+',
        'generated_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    },
    {
        'name': 'Gold_Bitcoin_Divergence_Rotator',
        'family': 'cross_asset',
        'instruments': ['XAUUSD', 'BTCUSD'],
        'timeframes': ['H4', 'D1'],
        'description': 'Gold and Bitcoin increasingly compete as store-of-value / safe-haven assets, but trade on different liquidity channels (gold: institutional, CB reserves; BTC: retail/ETF flows, digital-native). When rolling 30-day correlation exceeds +0.65 (regime of convergence) or drops below -0.20 (divergence), fade the move back toward the 90-day mean correlation of ~0.25. No existing cross_asset idea uses BTC correlation at all.',
        'entry_logic': '1. Compute 30-day Pearson correlation of daily returns (XAUUSD vs BTCUSD). 2. Compute 90-day rolling mean and std of that correlation. 3. IF z-score of current 30-day correlation > 2.0 (unusually high convergence) — expect mean reversion in correlation. Short the stronger asset, long the weaker. 4. IF z-score < -1.5 (unusual divergence) — expect convergence. Long the lagging asset, short the leading. 5. Entry only when both assets have >$50 daily range (avoid low-vol noise). 6. Check DXY direction: if DXY > 20-day EMA, prefer short gold side. 7. Position size: equal notional, 0.5% risk per leg.',
        'exit_logic': 'Stop loss: 1.5x ATR(14) on each leg, or correlation z-score moves another 1.0 in same direction (stop out if divergence continues). Take profit: correlation z-score returns to 0 (neutral). Time stop: exit after 10 bars if not triggered, as correlation regimes have limited persistence. Rebalance daily.',
        'failure_mode': 'Structural breakdown: if gold and BTC permanently decouple (e.g., CBDCs displace BTC as digital gold), the historical correlation anchor drifts. BTC can gap 10%+ on crypto-native events (exchange hacks, regulatory bans) that leave gold unchanged — the pair correlation becomes meaningless noise during crypto-specific shocks.',
        'diversification_value': 'Only strategy in the archive using BTC correlation with gold. Cross-asset ideas currently cover DXY, US10Y, TIPS, SPX, XAGUSD, USOIL, GDX, CRB indexes — but zero crypto exposure. This adds a completely orthogonal asset class dimension. Also distinct from pair-trade mean reversion (which is intra-asset-class); this is inter-asset-class correlation rotator.',
        'self_grade': 'B',
        'generated_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    },
    {
        'name': 'Kalman_Filter_Dynamic_Mean_Reversion',
        'family': 'mean_reversion',
        'instruments': ['XAUUSD'],
        'timeframes': ['M15', 'H1'],
        'description': 'Uses a Kalman filter to estimate the dynamic, time-varying mean of gold prices — rather than a fixed moving average or fixed Bollinger band center. When price deviates >1.5x the Kalman prediction error (innovation) on M15, fade aggressively. The Kalman filter adapts to changing volatility and trend components automatically, unlike static Bollinger/MA mean reversion. No existing mean_reversion idea uses Kalman filtering.',
        'entry_logic': '1. State vector: [price_level, trend_slope]. Observation: H1 close. Process noise covariance Q and observation noise R estimated via 5-day rolling MLE. 2. Kalman predict-update cycle yields: predicted price (k_t|t-1), innovation (residual between actual and predicted), and innovation variance S_t. 3. ENTRY CONDITION: |innovation| > 1.5 * sqrt(S_t) AND the innovation is in the opposite direction of the last 3 consecutive 15-min candle direction (divergence confirmation). 4. For long: price significantly below Kalman estimate AND last 3 M15 candles are bearish (exhaustion). 5. For short: symmetric. 6. Filter out entries when Kalman trend_slope > 0.3 ATR/day (too strong trend, don\'t fade). 7. Enter at market, 0.75% risk.',
        'exit_logic': 'Stop loss: 0.8x ATR(14) from entry (tight — Kalman reversion tends to be sharp). Take profit 1: 50% at innovation returns to 0 (price re-meets Kalman estimate). Take profit 2: 50% at 1.0x innovation in opposite direction (overshoot the other side). Fail-safe: if Kalman re-estimates such that current price becomes the new mean (innovation shrinks below 0.5x S_t while still in loss), exit at breakeven or -0.3 ATR max loss — the filter is saying the mean has moved.',
        'failure_mode': 'Kalman filter can take time to converge after structural breaks (gap openings, NFP spikes). During high-vol news events, the innovation threshold is too tight — gets stopped out repeatedly. Process noise parameters chosen by rolling MLE can produce unstable estimates during low-liquidity Asian session. Most dangerous failure: Kalman diverges (filter becomes overconfident in wrong state) during sustained trending moves, causing repeated fade losses.',
        'diversification_value': 'First Kalman filter-based strategy in the archive. Completely different mathematical foundation from existing mean reversion ideas (which use: z-score of EMA, Bollinger distance, VWAP entropy, FVG fills, order flow exhaustion, COT extremes). Kalman provides a dynamic state-space approach that adapts faster than fixed-period oscillators and handles non-stationary price processes naturally. Should show very low correlation with all 13 existing mean reversion strategies.',
        'self_grade': 'A-',
        'generated_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
]

for idea in new_ideas:
    if not any(i['name'] == idea['name'] for i in a['ideas']):
        a['ideas'].append(idea)
        a['coverage_map'].setdefault(idea['family'], []).append(idea['name'])
        print(f'Added: {idea["name"]} ({idea["family"]})')
    else:
        print(f'SKIPPED (duplicate): {idea["name"]}')

a['metadata']['total_ideas'] = len(a['ideas'])
a['metadata']['families_covered'] = sorted(set(f for f,v in a['coverage_map'].items() if v))
json.dump(a, open(ARCHIVE, 'w'), indent=2)
print(f'SAVED. Total ideas: {a["metadata"]["total_ideas"]}')
print(f'Families: {a["metadata"]["families_covered"]}')
