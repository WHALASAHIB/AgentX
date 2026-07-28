# Session Memory — Edge Discovery Loop

## Project Created
**Date:** 2026-07-27
**User Request:** Loop to find technical/statistical edges for trading, with economic rationale ("who loses on the other side").

## Scope
- 8 instruments: EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD, XAUUSD
- 5 timeframes: M5, M15, H1, H4, D1
- All technical indicators (MA, RSI, MACD, Stochastic, BB, ATR, ADX, patterns, etc.)
- Every 6h scan during session
- Output: top 3 edges with council-critiqued explainations

## Key Decisions
- Council has 5 members: Quant, Microstructure, Behavioral, Risk, Strategy
- "Who loses?" explanation is mandatory — auto-reject if missing
- Holm-Bonferroni correction for multiple comparisons
- Walk-forward validation (3 splits)
- No pandas dependency — pure numpy for speed

## Directory
`C:/Trading/edge_discovery/`
- scripts/ — Python implementation
- state/ — JSON state files
- archive/ — historical run reports
- 6 project files (prd.md, architecture.md, rules.md, phases.md, design.md, memory.md)

## User Preferences
- Don't be a yes man — tell the hard reality
- Trading is zero-sum: explain who loses
- Prefers concise, direct explanations with tabular data
- Runs MT5 on Windows, git-bash terminal
- Telegram for delivery
