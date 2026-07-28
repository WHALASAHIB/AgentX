#!/usr/bin/env python3
"""
Edge Council — multi-perspective critical evaluation of discovered edges.

5 council members score each edge on 0-100 scale.
Only edges meeting ALL minimum thresholds survive.
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from math import sqrt, log
from typing import Optional

import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE_DIR = os.path.join(BASE_DIR, "state")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

logger = logging.getLogger("edge_council")

# ============================================================================
# Minimum thresholds
# ============================================================================

MIN_SCORES = {
    "quant": 30,
    "microstructure": 40,  # Auto-reject if < 40 — MUST have "who loses?"
    "behavioral": 30,
    "risk": 30,
    "strategy": 30,
}

FINAL_MIN_SCORE = 60  # Overall minimum to be actionable


# ============================================================================
# Council Members
# ============================================================================

class CouncilMember:
    """Base class for council members."""
    name: str
    weight: float

    def score(self, edge: dict) -> tuple[float, str]:
        """Return (score 0-100, reason_text)."""
        raise NotImplementedError


class QuantAuditor(CouncilMember):
    """🧮 Statistical rigor — p-values, overfitting, sample size."""
    name = "quant"
    weight = 0.25

    def score(self, edge: dict) -> tuple[float, str]:
        reasons = []
        deductions = 0.0

        wr = edge.get("win_rate", 0)
        pf = edge.get("profit_factor", 0)
        sharpe = edge.get("sharpe", 0)
        trades = edge.get("trades", 0)
        p_val = edge.get("p_value", 1.0)
        max_dd = edge.get("max_drawdown_pct", 100)
        oos_wr = edge.get("oos_win_rate", 0)
        oos_pf = edge.get("oos_profit_factor", 0)

        # Sample size adequacy
        if trades < 30:
            deductions += 25
            reasons.append(f"Low sample size ({trades} trades, need ≥30)")
        elif trades < 50:
            deductions += 10
            reasons.append(f"Moderate sample ({trades} trades)")
        elif trades >= 100:
            reasons.append(f"Strong sample ({trades} trades)")

        # Statistical significance
        if p_val > 0.05:
            deductions += 30
            reasons.append(f"Not significant at α=0.05 (p={p_val:.4f})")
        elif p_val > 0.01:
            deductions += 10
            reasons.append(f"Significant at α=0.05 (p={p_val:.4f})")
        else:
            reasons.append(f"Strongly significant (p={p_val:.4f})")

        # Sharpe ratio
        if sharpe < 0.5:
            deductions += 15
            reasons.append(f"Low risk-adjusted returns (Sharpe={sharpe:.2f})")
        elif sharpe >= 1.0:
            reasons.append(f"Good risk-adjusted returns (Sharpe={sharpe:.2f})")

        # OOS consistency
        wr_drop = (wr - oos_wr) * 100
        if wr_drop > 10:
            deductions += 25
            reasons.append(f"OOS WR drops {wr_drop:.1f}pp — possible overfitting")
        elif wr_drop > 5:
            deductions += 10
            reasons.append(f"OOS WR drops {wr_drop:.1f}pp")
        else:
            reasons.append(f"OOS consistent (drop={wr_drop:.1f}pp)")

        if oos_pf < 1.0:
            deductions += 20
            reasons.append(f"OOS PF below breakeven ({oos_pf:.2f})")

        # Max drawdown
        if max_dd > 15:
            deductions += 15
            reasons.append(f"High max drawdown ({max_dd:.1f}%)")
        elif max_dd > 10:
            deductions += 5

        # Base score
        score = max(0, 70 - deductions)
        # Clamp and add bonus for exceptional stats
        if pf > 2.0 and sharpe > 1.5 and trades > 100:
            score = min(100, score + 15)

        score = max(0, min(100, score))
        reason_text = "; ".join(reasons) if reasons else "No statistical issues"
        return score, reason_text


class MicrostructureAnalyst(CouncilMember):
    """🏛️ Market microstructure — who is on the other side?

    This is the most important council member. An edge without a
    plausible microstructure explanation is likely noise or overfitting.
    """
    name = "microstructure"
    weight = 0.25

    def score(self, edge: dict) -> tuple[float, str]:
        """
        Evaluate whether there's a plausible market microstructure explanation.
        Higher score = more plausible that a real market participant
        is systematically providing the losing side.
        """
        indicator = edge.get("indicator", "")
        pair = edge.get("pair", "")
        timeframe = edge.get("timeframe", "")
        params = edge.get("parameters", {})
        wr = edge.get("win_rate", 0)
        pf = edge.get("profit_factor", 0)

        reasons = []
        score = 50  # Start at neutral

        # --- Trend-following edges (MA crosses, MACD, ADX) ---
        trend_followers = ["SMA_Cross", "EMA_Cross", "WMA_Cross", "HMA_Cross",
                           "MACD", "ADX_DMI", "Aroon"]

        if indicator in trend_followers:
            # Trend following works because:
            # - Retail traders fade trends (buying dips in downtrends)
            # - Institutions build positions gradually → trends persist
            # - Stop-loss clustering at support/resistance gets swept
            reasons.append("Institutions accumulate positions over days/weeks; "
                           "retail fades the move thinking it's 'overextended'")
            reasons.append("Trend persistence is structural: order flow imbalance "
                           "from institutional execution algorithms")
            score += 20

            if timeframe in ("H1", "H4", "D1"):
                score += 10  # Higher timeframes = more structural
                reasons.append(f"Higher timeframe ({timeframe}) = institutional flow, not retail noise")

            # Fast MAs on low TF = likely noise
            if timeframe == "M5":
                score -= 10
                reasons.append("M5 trend signals likely noise — microstructure edge less plausible")

        # --- Mean reversion edges (RSI, BB, CCI, Williams %R) ---
        mean_reversion = ["RSI", "Bollinger_Bands", "Stochastic", "CCI",
                          "Williams_R", "Price_vs_MA", "Keltner"]

        if indicator in mean_reversion:
            # Mean reversion works because:
            # - Retail overreaction to news/moves → price extremes
            # - Market maker hedging at extreme levels
            # - Algorithmic arbitrage restoring equilibrium
            reasons.append("Retail overreaction to news/momentum creates temporary "
                           "price extremes; algorithms and market makers fade these")
            reasons.append("Statistical arbitrage: extreme deviations attract "
                           "mean-reverting flow from prop desks and HFTs")

            # RSI 14 on H1/H4 is a classic mean reversion signal
            if indicator == "RSI" and params.get("period") == 14:
                score += 10
                reasons.append("RSI(14) is the industry standard — many market "
                               "participants trade it, creating self-fulfilling behavior")

            # Very tight thresholds = likely noise
            oversold = params.get("oversold", 0)
            if oversold > 35:
                score -= 10
                reasons.append(f"Very tight threshold (os={oversold}) — likely noise, not microstructure")

            score += 15

        # --- Volatility edges (ATR Breakout, etc.) ---
        volatility_edges = ["ATR_Breakout", "Bollinger_Bands", "Keltner"]
        if indicator in volatility_edges:
            # Volatility expansion edges:
            # - Stop-loss clusters trigger cascading liquidations
            # - Volatility clustering is a well-documented statistical fact
            reasons.append("Volatility clustering (Mandelbrot): large moves beget "
                           "large moves — statistical fact of financial time series")
            reasons.append("Stop-loss cascades: leveraged retail positions get "
                           "liquidated, accelerating the move")
            score += 15

        # --- Pattern-based edges ---
        pattern_edges = ["Candle_Engulfing", "Candle_Hammer", "Candle_PinBar",
                         "Candle_Star", "Candle_Harami", "Candle_Doji",
                         "Breakout", "InsideBar_Breakout"]
        if indicator in pattern_edges:
            # Patterns work because:
            # - They capture institutional order flow (smart money footprint)
            # - Self-fulfilling: many traders recognize and trade them
            reasons.append("Candle patterns reflect order flow imbalances — "
                           "institutional footprint visible on price chart")
            reasons.append("Self-fulfilling: retail and institutional traders "
                           "recognize these patterns and trade accordingly")

            if indicator in ("Candle_Engulfing", "Candle_PinBar"):
                score += 15
                reasons.append("Engulfing/Pin Bar are the strongest reversal "
                               "patterns — institutional absorption/rejection")
            elif indicator == "Candle_Doji":
                score -= 5
                reasons.append("Doji = indecision, not directional — weak edge alone")

        # --- Pair-specific microstructure ---
        if pair == "EURUSD":
            reasons.append("EURUSD is the most liquid pair — institutional flow "
                           "dominates, retail is noise")
            score += 5
        elif pair == "XAUUSD":
            reasons.append("Gold is sentiment/hedging driven — crowd psychology "
                           "at extremes (fear/greed) creates reversals")
            score += 5
        elif pair in ("GBPUSD", "USDJPY"):
            score += 3
            reasons.append(f"{pair} has strong institutional participation")

        # Win rate vs microstructure plausibility
        if wr > 0.70:
            score -= 15
            reasons.append(f"WR={wr*100:.0f}% suspiciously high — likely overfitted, "
                           "not microstructure")
        if wr < 0.53:
            score -= 10
            reasons.append(f"Low WR ({wr*100:.0f}%) — edge too weak for reliable exploitation")

        # Profit factor sanity
        if pf > 3.0:
            score -= 10
            reasons.append(f"PF={pf:.2f} abnormally high — likely data-mining bias")

        score = max(0, min(100, score))
        reason_text = "; ".join(reasons) if reasons else "No plausible microstructure explanation"
        return score, reason_text


class BehavioralAnalyst(CouncilMember):
    """🧠 Behavioral bias exploitation — which psychological bias creates the edge."""
    name = "behavioral"
    weight = 0.20

    def score(self, edge: dict) -> tuple[float, str]:
        indicator = edge.get("indicator", "")
        timeframe = edge.get("timeframe", "")
        reasons = []
        score = 40

        bias_map = {
            # Trend edges exploit:
            "SMA_Cross": ("Anchoring bias — traders anchor to recent prices and "
                          "can't accept the new trend direction"),
            "EMA_Cross": ("Disposition effect — traders close winners too early, "
                          "let losers run, exacerbating trends"),
            "WMA_Cross": ("Confirmation bias — traders seek info confirming old view, "
                          "miss trend change signals"),
            "HMA_Cross": ("Recency bias — slow to update beliefs, trends persist "
                          "while traders catch up"),
            "MACD": ("Gambler's fallacy — after a long trend, traders bet on reversal "
                     "prematurely; trend continues"),
            "ADX_DMI": ("Conservatism bias — traders under-react to new information, "
                        "trend develops slowly"),
            "Aroon": ("Status quo bias — reluctance to change position, even as "
                      "trend reverses"),
            # Mean reversion edges exploit:
            "RSI": ("Fear/greed cycle — retail overreaction to price moves creates "
                    "temporary extremes"),
            "Bollinger_Bands": ("Recency + representativeness — 'this time is different' "
                                "thinking at extremes, usually wrong"),
            "Stochastic": ("Hot hand fallacy — recent winners feel invincible, buy tops; "
                           "recent losers panic-sell bottoms"),
            "CCI": ("Herding behavior — crowd pushes prices too far, creating "
                    "reversion opportunity"),
            "Williams_R": ("Overconfidence bias — traders convinced of continuation "
                           "at extremes, providing liquidity"),
            "Price_vs_MA": ("Regression bias — traders treat distance from MA as "
                            "'cheap' or 'expensive' emotionally"),
            # Volatility edges exploit:
            "ATR_Breakout": ("Ostrich effect — traders ignore stop-losses during "
                             "volatility, get liquidated"),
            "Keltner": ("Myopic loss aversion — traders with tight stops get "
                        "stopped out by volatility, then move reverses"),
        }

        pattern_bias = {
            "Candle_Engulfing": "Narrative bias — once a pattern is labeled, traders "
                                "see what they expect; creates self-fulfillment",
            "Candle_Hammer": "Pattern-seeking — human brain finds patterns in noise; "
                             "self-fulfilling when enough traders act on it",
            "Candle_PinBar": "Availability heuristic — memorable patterns are "
                             "over-weighted in decision making",
            "Candle_Star": "Gambler's fallacy — after 2 bars, traders expect reversal; "
                           "star pattern materializes",
            "Candle_Harami": "Ambiguity aversion — uncertainty after a strong move "
                             "causes traders to exit, creating the reversal",
            "Candle_Doji": "Ambiguity aversion — indecision makes traders exit, "
                           "creating the very reversal they fear",
            "Breakout": "Fear of missing out (FOMO) — traders chase breakouts, "
                        "creating momentum that becomes self-fulfilling",
            "InsideBar_Breakout": "Status quo bias — traders wait for confirmation, "
                                  "the breakout triggers FOMO entry",
        }

        if indicator in bias_map:
            reasons.append(bias_map[indicator])
            score += 25
        elif indicator in pattern_bias:
            reasons.append(pattern_bias[indicator])
            score += 20
        else:
            reasons.append("No clear behavioral bias identified for this indicator")
            score -= 10

        # Timeframe adjustment
        if timeframe in ("M5", "M15"):
            score -= 5
            reasons.append(f"Lower timeframe ({timeframe}) — behavioral biases "
                           "are weaker, noise dominates")
        elif timeframe in ("H4", "D1"):
            score += 10
            reasons.append(f"Higher timeframe ({timeframe}) — behavioral biases "
                           "are stronger, decisions are more considered")

        score = max(0, min(100, score))
        reason_text = "; ".join(reasons) if reasons else "No behavioral analysis"
        return score, reason_text


class RiskAnalyst(CouncilMember):
    """⚠️ Edge survival — what regimes kill this edge?"""
    name = "risk"
    weight = 0.15

    def score(self, edge: dict) -> tuple[float, str]:
        indicator = edge.get("indicator", "")
        timeframe = edge.get("timeframe", "")
        max_dd = edge.get("max_drawdown_pct", 0)
        max_cons = edge.get("max_cons_losses", 0)
        reasons = []
        score = 60  # Start higher

        # Drawdown penalty
        if max_dd > 20:
            deductions = 30
            reasons.append(f"Max drawdown {max_dd:.1f}% is severe — edge can destroy "
                           "account before recovering")
        elif max_dd > 10:
            deductions = 10
            reasons.append(f"Max drawdown {max_dd:.1f}% is significant")
        elif max_dd < 5:
            score += 10
            reasons.append(f"Low max drawdown ({max_dd:.1f}%)")
            deductions = 0
        else:
            deductions = 0

        # Consecutive losses
        if max_cons >= 8:
            deductions += 20
            reasons.append(f"{max_cons} consecutive losses — psychological breaking point")
        elif max_cons >= 5:
            deductions += 10
            reasons.append(f"{max_cons} consecutive losses — requires discipline")

        # Regime vulnerability
        if indicator in ("SMA_Cross", "EMA_Cross", "WMA_Cross", "HMA_Cross",
                         "MACD", "ADX_DMI", "Aroon"):
            reasons.append("Vulnerable to: sideways/ranging markets (whipsaws)")
            reasons.append("Vulnerable to: sharp reversals (lagging nature)")
            score -= 5
            if max_cons > 5:
                score -= 10  # Trend strategies do poorly in range = big strings

        if indicator in ("RSI", "Bollinger_Bands", "Stochastic", "CCI",
                         "Williams_R", "Price_vs_MA"):
            reasons.append("Vulnerable to: strong trending markets (can't catch falling knife)")
            reasons.append("Vulnerable to: volatility regime shifts (bands expand/contract)")
            score -= 5

        if indicator in ("ATR_Breakout", "Keltner"):
            reasons.append("Vulnerable to: low volatility regimes (no breakouts occur)")
            score -= 5

        # Timeframe = edge survival
        if timeframe in ("M5", "M15"):
            score -= 10
            reasons.append("Lower TF edges decay faster — microstructure changes quickly")
        elif timeframe in ("H4", "D1"):
            score += 10
            reasons.append("Higher TF edges survive longer — institutional flow is stable")

        score = max(0, score - deductions)
        score = min(100, score)
        reason_text = "; ".join(reasons) if reasons else "No significant risk factors identified"
        return score, reason_text


class StrategyAnalyst(CouncilMember):
    """⚙️ Implementation feasibility — can we trade this edge in MT5?"""
    name = "strategy"
    weight = 0.15

    def score(self, edge: dict) -> tuple[float, str]:
        indicator = edge.get("indicator", "")
        timeframe = edge.get("timeframe", "")
        wr = edge.get("win_rate", 0)
        pf = edge.get("profit_factor", 0)

        reasons = []
        score = 60

        # MT5 feasibility
        impossible_for_mt5 = []
        if indicator in ("Candle_Star", "Candle_Harami"):
            # Multi-bar patterns need complex state tracking — doable but tricky
            score -= 5
            reasons.append("Multi-bar pattern — needs state tracking in MT5 EA, doable")
        if indicator in ("Candle_Doji", "Candle_Hammer", "Candle_PinBar",
                         "Candle_Engulfing"):
            reasons.append("Single-bar pattern — easy to code in MT5 EA")
            score += 5

        # Most indicators are trivial in MT5
        reasons.append("Standard indicator — straightforward MT5 implementation")

        # Timeframe alignment
        if timeframe in ("M5", "M15"):
            score += 5
            reasons.append(f"Low TF ({timeframe}) — more signals, faster compounding")
        elif timeframe in ("H1",):
            score += 10
            reasons.append(f"H1 aligns with existing Propfirm Pass bot — can piggyback")
        elif timeframe == "H4":
            score += 5
            reasons.append("H4 — good balance of signal frequency and reliability")

        # Win rate × PF interaction
        if wr > 0.50 and pf > 1.5:
            score += 10
            reasons.append("High WR × PF combination — excellent for position sizing")
        elif wr > 0.60 and pf < 1.2:
            score -= 5
            reasons.append("High WR but low PF — many small wins, one big loss")

        # Risk-adjusted feasibility
        expected_value = (wr * edge.get("avg_win", 0) -
                          (1 - wr) * edge.get("avg_loss", 0))
        if expected_value > 0:
            score += 5
            reasons.append(f"Positive expected value per trade (${expected_value:.2f})")

        # Slippage sensitivity (higher on M5)
        if timeframe == "M5":
            score -= 5
            reasons.append("M5 sensitive to slippage/spread — test with realistic costs")

        score = max(0, min(100, score))
        reason_text = "; ".join(reasons) if reasons else "Feasible to implement"
        return score, reason_text


# ============================================================================
# Council
# ============================================================================

class Council:
    """The Edge Council — convenes to judge candidates."""

    def __init__(self):
        self.members = [
            QuantAuditor(),
            MicrostructureAnalyst(),
            BehavioralAnalyst(),
            RiskAnalyst(),
            StrategyAnalyst(),
        ]

    def judge(self, edge: dict) -> dict:
        """
        Judge one edge candidate. Returns edge dict with council scores added.
        """
        scores = {}
        reasons = {}
        pass_all = True

        for member in self.members:
            score, reason = member.score(edge)
            scores[member.name] = score
            reasons[member.name] = reason

            if score < MIN_SCORES.get(member.name, 0):
                pass_all = False

        # Final weighted score
        final_score = sum(
            scores[m.name] * m.weight for m in self.members
        )

        # Reject overall if below minimum
        if final_score < FINAL_MIN_SCORE:
            pass_all = False

        decision = "ACCEPT" if pass_all else "REJECT"

        return {
            **edge,
            "council_quant": scores["quant"],
            "council_microstructure": scores["microstructure"],
            "council_behavioral": scores["behavioral"],
            "council_risk": scores["risk"],
            "council_strategy": scores["strategy"],
            "council_final": round(final_score, 1),
            "council_decision": decision,
            "council_reasons": reasons,
            "who_loses": reasons.get("microstructure", ""),
            "economic_rationale": "; ".join([
                r for r in [
                    reasons.get("microstructure", ""),
                    reasons.get("behavioral", ""),
                ] if r
            ]),
        }


def run_council(input_file: str = None) -> list[dict]:
    """Run council review on candidates from a scan output file."""
    if input_file and os.path.exists(input_file):
        with open(input_file, "r") as f:
            report = json.load(f)
    else:
        # Default: load edge_state.json
        state_file = os.path.join(STATE_DIR, "edge_state.json")
        if not os.path.exists(state_file):
            logger.error("No edge_state.json found — run edge_scanner first")
            return []
        with open(state_file, "r") as f:
            report = json.load(f)

    candidates = report.get("edges", [])
    if not candidates:
        logger.info("No candidates to review")
        return []

    logger.info("Council reviewing %d edge candidates...", len(candidates))

    council = Council()
    reviewed = []

    for edge in candidates:
        result = council.judge(edge)
        reviewed.append(result)
        logger.info("  %s | %s %s | Final=%.1f | %s",
                    result["pair"], result["timeframe"], result["indicator"],
                    result["council_final"], result["council_decision"])

    # Sort by final score descending
    reviewed.sort(key=lambda e: e.get("council_final", 0), reverse=True)

    # Save council verdict
    output = {
        "run_timestamp": time.time(),
        "datetime_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "pair": report.get("pair", ""),
        "candidates_reviewed": len(reviewed),
        "accepted": sum(1 for r in reviewed if r["council_decision"] == "ACCEPT"),
        "rejected": sum(1 for r in reviewed if r["council_decision"] == "REJECT"),
        "edges": reviewed,
    }

    verdict_file = os.path.join(STATE_DIR, "council_verdict.json")
    with open(verdict_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    # Archive
    archive_file = os.path.join(
        ARCHIVE_DIR,
        f"council_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info("Council verdict saved: %s", verdict_file)
    logger.info("Accepted: %d | Rejected: %d", output["accepted"], output["rejected"])

    return reviewed


def print_council_report(verdicts: list[dict]) -> None:
    """Print a readable council report."""
    if not verdicts:
        print("\n  ⚠️  No edges survived council review.\n")
        print("  Every candidate failed at least one council member's minimum threshold.\n")
        return

    print(f"\n{'='*70}")
    print("  🏛️  EDGE COUNCIL VERDICT")
    print(f"{'='*70}\n")

    accepted = [v for v in verdicts if v["council_decision"] == "ACCEPT"]
    rejected = [v for v in verdicts if v["council_decision"] == "REJECT"]

    print(f"  Total reviewed: {len(verdicts)}")
    print(f"  ✅ Accepted: {len(accepted)}")
    print(f"  ❌ Rejected: {len(rejected)}\n")

    if accepted:
        print(f"{'─'*70}")
        for i, e in enumerate(accepted[:3]):  # Show top 3
            print(f"  [{i+1}] 🏆 {e['pair']} | {e['timeframe']} | {e['indicator']}")
            print(f"      WR={e['win_rate']*100:.1f}%  PF={e['profit_factor']:.2f}  "
                  f"Trades={e['trades']}")
            print(f"      Council Score: {e['council_final']:.1f}/100")
            print(f"      🧮 Quant: {e['council_quant']:.0f}  "
                  f"🏛️ Micro: {e['council_microstructure']:.0f}  "
                  f"🧠 Behav: {e['council_behavioral']:.0f}")
            print(f"      ⚠️ Risk: {e['council_risk']:.0f}  "
                  f"⚙️ Strat: {e['council_strategy']:.0f}")
            print(f"      💡 Who loses: {e.get('who_loses', '')[:120]}...")
            print()

    if rejected:
        print(f"  {'─'*40}")
        print(f"  ❌ Rejected ({len(rejected)}):")
        for e in rejected[:5]:
            print(f"     - {e['pair']} {e['timeframe']} {e['indicator']} "
                  f"(score={e['council_final']:.0f})")

    print(f"{'='*70}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Edge Discovery Council")
    parser.add_argument("--input", type=str, default=None,
                        help="Input edge_state.json path (default: auto)")
    parser.add_argument("--file-only", action="store_true",
                        help="Only write JSON")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress output")
    args = parser.parse_args()

    log_level = logging.WARNING if (args.quiet or args.file_only) else logging.INFO
    logging.basicConfig(level=log_level,
                        format="%(asctime)s | %(levelname)s | %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

    log_path = os.path.join(LOGS_DIR, "council.log")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logging.getLogger().addHandler(fh)

    verdicts = run_council(args.input)

    if not args.file_only and not args.quiet:
        print_council_report(verdicts)

    accepted = sum(1 for v in verdicts if v["council_decision"] == "ACCEPT")
    rejected = sum(1 for v in verdicts if v["council_decision"] == "REJECT")
    print(f"edge_council | {len(verdicts)} reviewed | {accepted} accepted | {rejected} rejected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
