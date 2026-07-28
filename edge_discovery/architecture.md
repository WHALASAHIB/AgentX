# Architecture — Edge Discovery Loop

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    EDGE DISCOVERY LOOP                       │
│                   (runs every 6h via cron)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│   Phase 1: DATA COLLECTION                                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  mt5_connect → copy_rates_from_pos(pair, tf)       │   │
│   │  Cache to CSV (skip if <30min old)                 │   │
│   │  8 pairs × 5 tfs = 40 datasets                     │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│   Phase 2: PARAMETER SCANNING                               │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  For each pair × tf:                                │   │
│   │    For each indicator family:                       │   │
│   │      For each parameter combo:                      │   │
│   │        Generate signals → compute metrics           │   │
│   │        Rank by Sharpe / PF / WR / consistency       │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│   Phase 3: STATISTICAL VALIDATION                           │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Walk-forward (3 splits) → OOS test                 │   │
│   │  Bootstrap confidence intervals                     │   │
│   │  Multiple comparison correction (Holm-Bonferroni)   │   │
│   │  Filter: PF>1.3, WR>55%, Sharpe>0.5, p<0.05        │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│   Phase 4: PATTERN RECOGNITION                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Candle patterns (doji, engulf, hammer, etc.)       │   │
│   │  Support/Resistance bounce detection                │   │
│   │  Session-specific behavior (London/Asian overlap)   │   │
│   │  Day-of-week / time-of-day effects                  │   │
│   │  Statistical significance of each pattern           │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│   Phase 5: COUNCIL REVIEW                                   │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Top 10 candidates → Council judges each:           │   │
│   │   • Quant: statistical rigor score                  │   │
│   │   • Microstructure: "who loses?" score              │   │
│   │   • Behavioral: psychology rationale score          │   │
│   │   • Risk: edge survival score                       │   │
│   │  Aggregate → Top 3 edges with explanations          │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│   Phase 6: OUTPUT + DECAY TRACKING                          │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  Write report to archive/ and state/                │   │
│   │  Compare current edges vs historical baselines      │   │
│   │  If edge decay > 20% → ALERT                        │   │
│   │  If new edge found → ALERT with explanation         │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

```
MT5 ──[copy_rates]──> DataCache ──> Scanner ──> Validator ──> Council ──> Report
       │                               │
       └──[positions_get]──> LiveContext (current positions for reference)
```

## Indicator Families (Phase 2 Scope)

| Family | Indicators | Parameter Space |
|--------|-----------|-----------------|
| Moving Averages | SMA, EMA, WMA, HMA | period: 5-200 (12 steps), src: close/hl2/hlc3 |
| Momentum | RSI, CCI, Stochastic, MACD | period: 5-50, thresholds: variable |
| Volatility | ATR, Bollinger Bands, Keltner | period: 5-50, multiplier: 1.0-3.0 |
| Trend | ADX, Aroon, Parabolic SAR | period: 5-30 |
| Volume | MFI, OBV signals (if available) | period: 7-30 |
| Patterns | 12 candle patterns + S/R tests | Pattern type + confirmation bar |

**Total parameter combinations: ~15,000-25,000 per run** (pre-filtered for sensible ranges)

## File Structure

```
C:/Trading/edge_discovery/
├── prd.md                    # This document
├── architecture.md           # This document  
├── rules.md                  # Rules & constraints
├── phases.md                 # Implementation phases
├── design.md                 # Detailed design
├── memory.md                 # Session memory
├── scripts/
│   ├── edge_scanner.py       # Main scanner engine
│   ├── indicator_lib.py      # All indicator implementations
│   ├── pattern_lib.py        # Pattern recognition
│   ├── council.py            # Council review logic
│   └── data_cache.py         # MT5 data fetching + caching
├── state/
│   ├── risk_state.json       # Reference from risk supervisor
│   └── edge_state.json       # Current discovered edges
├── archive/                  # Historical reports
└── logs/                     # Run logs
```
