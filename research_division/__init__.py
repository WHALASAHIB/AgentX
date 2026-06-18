"""
AGENTX Research & Invocation Division
======================================
Autonomous trading research system that monitors all pairs, analyzes performance,
generates improvement hypotheses, validates them via backtesting, and deploys winners.

Agile Sprint Cycle:
- Sprint length: 24 hours (08:00 HKT → next day 08:00 HKT)
- Data collection: every 15 minutes
- Analytics refresh: every hour
- Deep research: every 4 hours
- Sprint review: 20:00 HKT
- Sprint planning: 08:00 HKT

Roles:
- Project Manager: Prioritizes backlog by impact score
- Scrum Master: Tracks sprint progress, removes blockers
- Research Agents: Generate strategy variants
- Validation Agent: Backtests variants
- Deployment Agent: Deploys validated improvements
"""

__version__ = "1.0.0"
