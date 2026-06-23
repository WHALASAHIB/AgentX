#!/usr/bin/env python3
"""
self_improving_research.py — Context gatherer for the self-improving strategy research loop.

Reads the research_hypotheses.json archive and outputs a structured summary
that the cron agent uses to generate NOVEL ideas (not repeats).

Outputs:
  - Total ideas generated so far
  - Coverage by strategy family (what's been done, what's missing)
  - Recent ideas (last 5)
  - Suggestions for which families to explore next
  - A uniqueness fingerprint for the agent to check against
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

ARCHIVE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "state", "research_hypotheses.json"
)

# — Strategy families that the research targets
STRATEGY_FAMILIES = {
    "momentum": "Trend-following, MACD cross, SMA cross, ADX trend strength",
    "mean_reversion": "RSI oversold/overbought, Bollinger squeeze, stochastic reversal",
    "breakout": "Channel breakouts, Asian range break, support/resistance breaks",
    "volatility": "ATR-based position sizing, volatility breakout, VWAP bands",
    "regime_filter": "Session-aware filters, volatility regime, trend vs ranging detection",
    "risk_overlay": "Trailing stops, pyramiding rules, correlation hedge, drawdown guards",
    "cross_asset": "Treasury yield correlation, DXY impact, crypto-equity beta rotation",
    "seasonal": "Time-of-day patterns, day-of-week effects, month-end flows",
    "other": "Anything that doesn't fit above",
}

# — Instruments available for strategy deployment
INSTRUMENTS = {
    "XAUUSD": "Gold — currently the primary focus, 4 legacy bots + multi bots",
    "EURUSD": "Euro — most liquid forex pair",
    "GBPUSD": "Cable — volatile, good for breakout",
    "USDJPY": "Yen — sensitive to interest rate differentials",
    "USDCHF": "Swissie — safe haven, correlated to XAU",
    "USDCAD": "Loonie — oil-correlated",
    "AUDUSD": "Aussie — commodities/China-correlated",
    "NZDUSD": "Kiwi — late session mover",
    "BTCUSD": "Bitcoin — crypto volatility, 24/7 market",
}


def load_archive() -> Dict[str, Any]:
    """Load the research hypotheses archive."""
    if not os.path.exists(ARCHIVE_PATH):
        return {
            "metadata": {"total_ideas": 0, "families_covered": []},
            "ideas": [],
            "coverage_map": {k: [] for k in STRATEGY_FAMILIES}
        }
    with open(ARCHIVE_PATH, "r") as f:
        return json.load(f)


def build_coverage_report(archive: Dict[str, Any]) -> str:
    """Build a human-readable coverage report from the archive."""
    ideas = archive.get("ideas", [])
    coverage = archive.get("coverage_map", {})
    meta = archive.get("metadata", {})

    lines = []
    lines.append("=" * 60)
    lines.append("📊 RESEARCH ARCHIVE COVERAGE REPORT")
    lines.append(f"   Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Total ideas archived: {meta.get('total_ideas', 0)}")

    if ideas:
        last_idea = ideas[-1]
        lines.append(f"Last idea added: {last_idea.get('name', 'unknown')} "
                     f"({last_idea.get('generated_at', 'unknown')})")
    lines.append("")

    # — Family coverage
    lines.append("📁 COVERAGE BY STRATEGY FAMILY:")
    lines.append("-" * 40)
    total_families = len(STRATEGY_FAMILIES)
    covered = sum(1 for f in STRATEGY_FAMILIES if coverage.get(f, []))
    lines.append(f"Families covered: {covered}/{total_families}")
    lines.append("")

    for family, description in STRATEGY_FAMILIES.items():
        family_ideas = coverage.get(family, [])
        bar = "█" * len(family_ideas) + "░" * max(0, 5 - len(family_ideas))
        lines.append(f"  {family:20s} [{bar}] {len(family_ideas)} ideas")
        if len(family_ideas) == 0:
            lines.append(f"  {' ' * 22}⚠️  GAP — No ideas in this family yet")
        lines.append(f"  {' ' * 22}└ {description}")
        if family_ideas:
            # Show last 2 idea names
            for n in family_ideas[-2:]:
                lines.append(f"  {' ' * 22}  • {n}")
        lines.append("")

    # — Gap analysis: which families to target next
    lines.append("🎯 RECOMMENDED FOCUS (gaps first):")
    lines.append("-" * 40)
    uncovered = [f for f in STRATEGY_FAMILIES if not coverage.get(f, [])]
    if uncovered:
        for family in uncovered:
            lines.append(f"  ⬆️  {family} — NO ideas yet, high priority")
    else:
        # All families have at least one idea — recommend the thinnest
        sorted_families = sorted(
            STRATEGY_FAMILIES.keys(),
            key=lambda f: len(coverage.get(f, []))
        )
        for family in sorted_families[:3]:
            count = len(coverage.get(family, []))
            lines.append(f"  🔄 {family} — only {count} idea(s), thin coverage")
    lines.append("")

    # — Recent ideas (last 5)
    if ideas:
        lines.append("🔍 RECENT IDEAS (last 5):")
        lines.append("-" * 40)
        for idea in ideas[-5:]:
            lines.append(f"  • {idea.get('name', 'unknown')} "
                         f"[{idea.get('family', 'other')}] "
                         f"(self-grade: {idea.get('self_grade', 'N/A')})")
            lines.append(f"    {idea.get('description', '')[:100]}")
        lines.append("")

    # — Instruments not yet covered
    instruments_used = set()
    for idea in ideas:
        for inst in idea.get("instruments", []):
            instruments_used.add(inst.upper())
    missing_instruments = [k for k in INSTRUMENTS if k not in instruments_used]
    if missing_instruments:
        lines.append("🎯 INSTRUMENTS WITH NO HYPOTHESES:")
        lines.append("-" * 40)
        for inst in missing_instruments:
            lines.append(f"  • {inst} — {INSTRUMENTS[inst]}")

    lines.append("=" * 60)
    lines.append("INSTRUCTIONS FOR NEXT RUN:")
    lines.append("Generate ideas targeting the gaps above.")
    lines.append("EACH new idea MUST have a unique name not in the archive.")
    lines.append("Save new ideas to the archive file AND deliver the report.")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    archive = load_archive()
    report = build_coverage_report(archive)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
