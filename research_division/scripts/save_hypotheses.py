import json, datetime

ARCHIVE = 'C:/Trading/research_division/state/research_hypotheses.json'
a = json.load(open(ARCHIVE))

new_ideas = [
    {
        "name": "Momentum_Carry_Volatility_Filter",
        "family": "momentum",
        "instruments": ["XAUUSD"],
        "timeframes": ["H1", "H4"],
        "description": "Combines trend-momentum entry with a positive carry filter (contango/backwardation in gold futures basis) and uses ATR-normalized volatility gating to prevent entry during choppy or overextended conditions. The idea: strong trends that also have favourable carry (futures curve in backwardation) and moderate volatility (not too low = no trend, not too high = blow-off top) are the highest-probability momentum trades.",
        "entry_logic": "Step 1: Calculate 50-period and 200-period EMA slope on XAUUSD H1/H4. A bullish slope requires EMA50 > EMA200 and both sloping up. Step 2: Compute gold futures basis (front-month futures price / spot price). Require basis > 1.001 (backwardation, positive carry) for longs or basis < 0.999 (contango, negative carry) for shorts. Step 3: Compute 14-period ATR as % of price. Gate: only trade if ATR% is between its 20-period 30th and 70th percentile — kills zero-volatility flat markets and blow-off top volatility spikes. Step 4: On aligned H1 trend, wait for a pullback to 20 EMA with a bullish engulfing or hammer candle. Entry on close of confirmation candle.",
        "exit_logic": "Stop loss: 1.5x ATR(14) below entry. Take profit: 3:1 risk-reward, or trail stop at 1x ATR once price moves 2x ATR in profit. Time stop: close after 48 bars if neither hit. Additional exit: if basis flips (carry changes sign) with price still in trade, reduce to half position.",
        "failure_mode": "Can whipsaw during contango/backwardation regime shifts when central bank policy changes rapidly (e.g. surprise rate cuts/hikes). The volatility percentile gate may also miss the first powerful leg of a new trend until the next pullback.",
        "diversification_value": "Uniquely adds positive carry as a momentum confirmatory filter — no existing momentum bot in the archive uses the gold futures basis curve. Also uses volatility percentile gating rather than raw ATR thresholds, preventing overfitted parameter drift.",
        "self_grade": "B+",
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    },
    {
        "name": "Mean_Reversion_OrderFlow_Exhaustion",
        "family": "mean_reversion",
        "instruments": ["XAUUSD"],
        "timeframes": ["M15", "M5"],
        "description": "Identifies short-term exhaustion points in gold by combining tick-volume delta divergence with cluster-wide wick structure. When aggressive buying (delta divergence — price makes higher high but cumulative delta makes lower high) coincides with an identifiable liquidity sweep wick through a recent swing high, the market has exhausted the marginal buyer and is primed for a mean-reversion snap back toward the value area (VWAP or 20 EMA on M15).",
        "entry_logic": "Step 1: On M15, compute cumulative delta divergence — price makes a swing high above the prior 20-bar high while cumulative delta (aggressive buys - aggressive sells over 5 bars) fails to confirm, printing a lower high. Step 2: Confirm the high candle has a wick at least 2x the body length and the wick extended at least 0.5 ATR beyond the prior 20-bar high (liquidity sweep pattern). Step 3: Volume on the exhaustion bar must be in the top 30% of 50-bar volume (shows real participation, not noise). Step 4: Enter short on close of the exhaustion bar. For long entries, reverse: price makes lower low with delta making higher low, wick sweeps below prior 20-bar low, high volume.",
        "exit_logic": "Stop loss: 0.5 ATR beyond the swept liquidity level (above the wick high). Take profit: 1:1.5 risk-reward or VWAP whichever comes first. If price re-enters the wick zone (invalidates the sweep), exit immediately at market. Hard time stop: 24 bars.",
        "failure_mode": "Fails in strong trending one-directional markets where delta divergence can persist for many bars (trend exhaustion not the same as mean-reversion exhaustion). Entries against a strong trend get crushed. Needs a regime filter (e.g. ADX < 30) as a prerequisite.",
        "diversification_value": "Introduces cumulative delta divergence as a formal entry mechanism — no existing mean-reversion idea uses order-flow delta data. Also uniquely requires wick-to-body ratio (liquidity sweep) as a confirmation condition, bridging order-flow analysis with price structure.",
        "self_grade": "B",
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    },
    {
        "name": "Cross_Asset_Basis_Divergence",
        "family": "cross_asset",
        "instruments": ["XAUUSD", "XAGUSD", "DX-Y.NYB"],
        "timeframes": ["H4", "D1"],
        "description": "Exploits divergence between gold-silver ratio momentum and the US Dollar Index movement. The logic: when XAU/XAG ratio is rising (gold outperforming silver — typically risk-off behaviour) but DXY is falling (bearish dollar — typically risk-on behaviour), there is an inter-asset inconsistency that historically resolves with gold catching down or silver catching up. This cross-asset basis divergence acts as an early warning that the current gold move is fragile and likely to mean-revert or stall.",
        "entry_logic": "Step 1: Compute the 21-period rate of change of the XAU/XAG ratio (gold price / silver price) on H4. Step 2: Compute the 21-period rate of change of DXY on H4. Step 3: Divergence signal occurs when ROC_XAUXAG > +5% (gold strongly outperforming silver) AND ROC_DXY < -2% (dollar weakening). This is the inconsistency — risk-off in metals (gold beating silver) while risk-on in FX (bearish USD). Step 4: (a) If gold is above its 50 EMA on D1, favour short gold (risk-off priced into gold, USD weakness should pull commodities up but silver is already being bought — gold is the laggard). (b) If gold is below 50 EMA on D1, go long silver (silver will catch up when risk-on returns). Entry on close of the bar where divergence exceeds both thresholds.",
        "exit_logic": "Stop loss: 1% below entry for gold shorts, 1.5% below entry for silver longs. Take profit: when either ROC_XAUXAG drops below +2% or ROC_DXY rises above 0% — the divergence has resolved. Hard stop at 20 bars. Scale out 50% at 1:1 risk-reward, trail the rest at 1 ATR.",
        "failure_mode": "Central bank interventions (e.g. BOJ/Fed coordinated dollar operations) can distort DXY beyond normal correlation regimes. Also, the XAU/XAG ratio can diverge from the dollar for extended periods during sustained gold bull runs driven by physical demand (central bank buying, not speculative). Works best in normal speculative environments.",
        "diversification_value": "Uniquely exploits the XAU/XAG ratio in tandem with DXY in an inconsistency-detection framework. No existing cross_asset idea uses this specific three-asset divergence (gold vs silver vs dollar) as a signal. Also proposes asset-direction switching (short gold vs long silver) based on trend context — adaptive cross-asset hedging.",
        "self_grade": "B+",
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }
]

for idea in new_ideas:
    if not any(i["name"] == idea["name"] for i in a["ideas"]):
        a["ideas"].append(idea)
        a["coverage_map"].setdefault(idea["family"], []).append(idea["name"])

a["metadata"]["total_ideas"] = len(a["ideas"])
a["metadata"]["families_covered"] = sorted(set(f for f,v in a["coverage_map"].items() if v))

json.dump(a, open(ARCHIVE, "w"), indent=2)
print(f"SAVED. Total ideas: {a['metadata']['total_ideas']}")
print(f"Added: {[i['name'] for i in new_ideas]}")
print(f"Families updated: {[i['family'] for i in new_ideas]}")
