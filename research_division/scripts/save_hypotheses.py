import json, datetime

ARCHIVE = 'C:/Trading/research_division/state/research_hypotheses.json'
a = json.load(open(ARCHIVE))

new_ideas = [
    {
        'name': 'Session_Decay_Exposure_Controller',
        'family': 'risk_overlay',
        'instruments': ['XAUUSD', 'NAS100'],
        'timeframes': ['H1'],
        'description': 'Time-based position sizing overlay that reduces exposure during low-liquidity sessions (Asian, Friday close-to-open) and allows full size during high-liquidity overlap (London-NY). Predictably reduces drawdown during session transitions where slippage is highest.',
        'entry_logic': 'Not a standalone entry — applies as a multiplier on any base strategy position sizing. 1) At each H1 bar, determine current session: Asian (00:00-08:00 UTC) = 0.5x multiplier, London open (08:00-12:00 UTC) = 0.7x, London-NY overlap (12:00-16:00 UTC) = 1.0x, NY alone (16:00-21:00 UTC) = 0.7x, Pacific (21:00-00:00 UTC) = 0.4x. 2) Special rules: Friday 20:00 UTC through Sunday 23:00 UTC = 0.2x (weekend gap risk). 3) On NFP/FOMC/CPI days, reduce to 0.3x for 2 hours before and 1 hour after the event. 4) Multiply the base strategy lot size by the session multiplier. 5) Re-evaluate every bar.',
        'exit_logic': 'Overlay self-reverts at each session boundary — no independent SL/TP. If base strategy exits normally, overlay multiplier is 0 (no additional effect). Maximum drawdown protection is implicit: less capital at risk during dangerous hours.',
        'failure_mode': '1) Misses Asian-session breakouts that run 15-30 pips before London open (e.g., RBA rate decisions, Chinese PMI surprises). 2) Friday afternoons sometimes see sharp directional moves that are front-loaded — reduced exposure misses these entirely. 3) During 24h trending days, the overlay forces reduced size during the trend most profitable continuation phase if it overlaps with lower-liquidity hours.',
        'diversification_value': 'Completely orthogonal to all 11 existing risk_overlay ideas — none address time/session-based exposure. Complements Slippage_Regime_Sizer (which handles micro liquidity) and Volatility_Parity_Scale (which handles vol-based sizing) by covering the macro-liquidity time dimension. Adds diversification through a non-statistical, calendar-driven risk rule.',
        'self_grade': 'B+'
    },
    {
        'name': 'Entropy_Regime_Contingency_Sizer',
        'family': 'risk_overlay',
        'instruments': ['XAUUSD', 'EURUSD'],
        'timeframes': ['H1'],
        'description': 'Measures market entropy (randomness of price directional changes) over 20 periods and reduces position size in high-entropy (choppy, directionless) regimes while allowing full size in low-entropy (strong trending) regimes. Prevents equity curves from suffering during range-bound whipsaw markets.',
        'entry_logic': 'Overlay applied on top of any base strategy. 1) Encode each H1 bar direction as: +1 (close > open with range > 10% of ATR), -1 (close < open with range > 10% of ATR), 0 (doji / inside bar / low-range). 2) Compute Shannon entropy over the 20-bar sequence: H = -sum(p(x) * log2(p(x))) where p(x) is frequency of each state. 3) Normalize: if H > 0.75 (high randomness -> ranging/choppy) -> multiplier = 0.5x. If 0.4 < H < 0.75 -> multiplier = 0.75x. If H < 0.4 (low randomness -> strong trend) -> multiplier = 1.0x. 4) Apply multiplier to base strategy position size. 5) Re-evaluate every 5 bars to avoid noise.',
        'exit_logic': 'No independent SL/TP. Overlay self-updates every 5 bars. If entropy drops mid-trade, sizing increases — effectively adding to winning positions during trend confirmation. If entropy spikes, sizing decreases — reducing exposure during uncertainty without closing the trade outright.',
        'failure_mode': '1) Shannon entropy is a lagging measure — the regime may have already broken before entropy catches up, causing delayed size adjustments. 2) High-volatility trending markets (e.g., news-driven breaks) produce high entropy in the first 5-10 bars and get penalized despite being strong directional moves. 3) Short lookbacks (20) make entropy noisy; long lookbacks (50+) make it too slow. The 20-bar balance is a compromise that may not suit all instruments.',
        'diversification_value': 'Novel measurement approach — none of the 11 existing risk_overlay ideas use entropy or randomness measurement. Completely orthogonal to VaR-based (VaR_Trailing_Stop_Overlay), volatility-based (Volatility_Parity_Scale, Multi_TF_Vol_Convexity_Sizer), and drawdown-based (Max_Drawdown_Lock_Protector) methods. The entropy signal captures a fundamentally different dimension of market risk — structural randomness rather than magnitude of movement.',
        'self_grade': 'B+'
    },
    {
        'name': 'Skew_Asymmetry_Insurer',
        'family': 'risk_overlay',
        'instruments': ['XAUUSD'],
        'timeframes': ['H4'],
        'description': 'Adjusts position size based on the asymmetry (skewness) of recent returns. When skew is heavily negative (left-tail heavy), downside risk exceeds upside potential — reduces long positions. When skew is heavily positive (right-tail heavy), reduces short positions. Standard deviation-based methods miss this asymmetry entirely.',
        'entry_logic': 'Overlay applied on any base strategy. 1) Compute daily return skewness over 30 periods using Fisher-Pearson standardized moment coefficient. 2) Classify regime: Highly negative skew (< -0.5) = left-tail risk elevated; Neutral skew (-0.5 to +0.5) = symmetric risk; Highly positive skew (> +0.5) = right-tail risk elevated. 3) For long-only base strategies: if skew < -0.5 -> 0.5x multiplier (downside risk), if skew > +0.5 -> 1.0x multiplier (upside bias). 4) For short-only base strategies: if skew > +0.5 -> 0.5x multiplier, if skew < -0.5 -> 1.0x multiplier. 5) For directional strategies: 0.75x multiplier for either high-skew regime, 1.0x for neutral. 6) Re-evaluate daily.',
        'exit_logic': 'No independent SL/TP. Updates daily at H4 close. Skewness changes slowly (30-period window), so the overlay provides stable, non-chattering adjustments. If a sudden skew event occurs (e.g., flash crash), the 30-period window ensures the adjustment persists for several days — preventing re-entry into a still-dangerous regime.',
        'failure_mode': '1) Skewness requires 30+ data points to be statistically meaningful — cannot adapt quickly to sudden regime changes. 2) During low-volatility periods, skewness estimates become noisy and unreliable (tiny returns produce division-by-near-zero issues). 3) XAUUSD skew is often near-zero due to its symmetric nature — the overlay may rarely trigger, making it low-utility on gold compared to equity indices. 4) Rolling skewness produces autocorrelated signals that can lead to persistent over- or under-sizing during multi-day trending regimes that happen to have asymmetric volatility.',
        'diversification_value': 'Addresses a blind spot — no existing risk_overlay idea considers return skew asymmetry. All existing methods (VaR, ATR, drawdown-based) treat upside and downside risk symmetrically. This is the first idea to explicitly differentiate directional risk premium. Works best in combination with Volatility_Parity_Scale and Multi_TF_Vol_Convexity_Sizer to cover both magnitude and asymmetry of risk.',
        'self_grade': 'B'
    }
]

for idea in new_ideas:
    if not any(i['name'] == idea['name'] for i in a['ideas']):
        a['ideas'].append(idea)
        a['coverage_map'].setdefault(idea['family'], []).append(idea['name'])

a['metadata']['total_ideas'] = len(a['ideas'])
a['metadata']['families_covered'] = sorted(set(f for f,v in a['coverage_map'].items() if v))

json.dump(a, open(ARCHIVE, 'w'), indent=2)
print(f'SAVED. Total ideas: {a["metadata"]["total_ideas"]}')
print(f'risk_overlay count: {len(a["coverage_map"]["risk_overlay"])}')
print(f'New ideas added: {[idea["name"] for idea in new_ideas]}')
