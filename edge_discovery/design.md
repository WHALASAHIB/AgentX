# Design Document — Edge Discovery Loop

## 1. Data Cache (`data_cache.py`)

### Data Model
```python
@dataclass
class CachedDataset:
    symbol: str          # EURUSD, GBPUSD, etc.
    timeframe: int       # mt5.TIMEFRAME_M5, TIMEFRAME_M15, etc.
    bars: np.ndarray     # structured array: [time, open, high, low, close, tick_volume]
    fetched_at: float    # timestamp
    cached_at: float     # when last written to disk
```

### Cache Strategy
- CSV files per pair+tf: `state/data_{symbol}_{tf}.csv`
- Expire after 30 minutes (refetch if older)
- On refetch, download last 2000 bars via `mt5.copy_rates_from_pos()`
- Fast path: if cache is fresh, skip MT5 connection entirely

### Performance
- All calculations use **numpy vectorization** (no loop-over-bars)
- Rolling windows via numpy strides + bottleneck where available
- Pure Python numpy only (no pandas dependency for speed)

---

## 2. Indicator Library (`indicator_lib.py`)

### Indicator → Signal Pattern
Every indicator follows:
```python
def compute(high, low, close, volume, params: dict) -> np.ndarray:
    """Returns signal array: 1 = long, -1 = short, 0 = neutral"""
```

### Trend Indicators
| Indicator | Parameters | Signal Logic |
|-----------|-----------|-------------|
| SMA Cross | fast=[5,10,20,50], slow=[50,100,200] | fast > slow = 1, fast < slow = -1 |
| EMA Cross | fast=[5,10,20,50], slow=[50,100,200] | Same as SMA |
| WMA Cross | fast=[5,10,20], slow=[50,100] | Same |
| HMA Cross | fast=[10,20], slow=[50,100] | Hull MA variant |
| Price vs MA | period=[20,50,100,200] | close > MA×1.02 = 1, < MA×0.98 = -1 |

### Momentum Indicators
| Indicator | Parameters | Signal Logic |
|-----------|-----------|-------------|
| RSI | period=[7,9,14,21], ob=[65,70,75,80], os=[20,25,30,35] | RSI < os = 1, RSI > ob = -1 |
| Stochastic | k=[5,8,14], d=[3,5], ob=[80], os=[20] | K < os = 1, K > ob = -1 |
| MACD | fast=[5,8,12], slow=[17,21,26], signal=[5,9,12] | MACD > signal = 1, < signal = -1 |
| CCI | period=[10,14,20], ob=[100], os=[-100] | CCI < -100 = 1, > 100 = -1 |
| Williams %R | period=[10,14,21], ob=[-20], os=[-80] | %R < -80 = 1, > -20 = -1 |

### Volatility Indicators
| Indicator | Parameters | Signal Logic |
|-----------|-----------|-------------|
| Bollinger Bands | period=[10,20,50], std=[1.5,2.0,2.5,3.0] | close < lower = 1 (reversion), close > upper = -1 |
| ATR Channels | period=[7,14,21], mult=[1.0,1.5,2.0,2.5] | close > upper = 1 (breakout), < lower = -1 |
| Keltner | period=[10,20], atr_mult=[1.0,1.5,2.0] | Same as BB |

### Trend Strength
| Indicator | Parameters | Signal Logic |
|-----------|-----------|-------------|
| ADX/DMI | period=[7,10,14,21], threshold=[20,25,30] | DI+ > DI- AND ADX > threshold = 1, opposite = -1 |
| Aroon | period=[10,14,21,25] | Aroon Up > Aroon Down = 1 |

### Patterns (`pattern_lib.py`)
| Pattern | Logic |
|---------|-------|
| Doji | |open-close| ≤ 0.1×(high-low) AND body < 5% of range |
| Engulfing | Current body > prev body × 1.5 AND opposite color |
| Hammer | Lower wick > 2× body, upper wick < 0.5× body |
| Shooting Star | Upper wick > 2× body, lower wick < 0.5× body |
| Harami | Current body inside prev body, opposite color |
| Morning/Evening Star | 3-bar reversal pattern |
| Pin Bar | Wick/body ratio > 3:1 |
| Inside Bar | Current range inside prev range |
| Breakout | Close > prev 20-bar high OR < 20-bar low |
| Session-specific | Stat accuracy by session (Asian/London/US) |
| Day-of-week | Win rate by day |

---

## 3. Scanner Engine (`edge_scanner.py`)

### Algorithm
```
For each pair in PAIRS:
  For each tf in TIMEFRAMES:
    Load/create cache
    For each indicator_family in INDICATORS:
      For each parameter combo in FAMILY_PARAMS:
        signals = compute(ohlcv, params)
        metrics = compute_performance(signals, returns)
        if metrics.pf > 1.3 AND metrics.wr > 0.55 AND metrics.trades > 30:
          result = run_walk_forward(ohlcv, compute, params)
          if result.oos_valid:
            candidates.append(result)
```

### Performance Metrics Engine
```python
def compute_performance(signals, close, forward_bars=5):
    """
    - Forward returns over next N bars (N varies by tf)
    - M5/M15: N=5 (25-75 min outlook)
    - H1/H4: N=3 (3-12h outlook)
    - D1: N=1 (1 day outlook)
    """
    sharpe, pf, wr, avg_win, avg_loss, max_dd, cons_losses = ...
    return Statistics(sharpe, pf, wr, ...)
```

### Walk-Forward
- Split data into 3 windows: 50% train, 25% validate, 25% OOS
- Edge must be positive in ALL 3
- Best params selected on train, verified on OOS
- Penalty for parameter instability

---

## 4. Council (`council.py`)

### Council Members
```
1. QUANT — Statistical Auditor
   - Validates p-values, multiple comparison correction, Sharpe ratio
   - Detects overfitting, survivorship bias, look-ahead bias
   - Score: 0-100 (statistical rigor)

2. MICROSTRUCTURE — Market Dynamics Analyst  
   - Identifies who is on the other side
   - Asks: retail vs institutional? Hedgers vs speculators?
   - What liquidity conditions support this edge?
   - Score: 0-100 (economic plausibility)

3. BEHAVIORAL — Psychology & Bias Analyst
   - Identifies behavioral bias being exploited
   - Fear/greed cycles, anchoring, herding, disposition effect
   - Is this edge exploiting human psychology?
   - Score: 0-100 (psychology rationale)

4. RISK — Edge Survival Analyst
   - What market regimes destroy this edge?
   - Historical drawdown scenarios
   - Correlated with other strategies?
   - Score: 0-100 (robustness)

5. STRATEGY — Implementation Analyst
   - Can we implement this in MT5?
   - Slippage/fill considerations
   - Position sizing recommendation
   - Score: 0-100 (feasibility)
```

### Scoring Algorithm
```python
final_score = (
    quant * 0.25 + microstructure * 0.25 + 
    behavioral * 0.20 + risk * 0.15 + strategy * 0.15
)
# If ANY council member scores < 30: auto-reject
# If microstructure < 40: auto-reject (must have "who loses?")
```

### Output Format
```json
{
  "run_timestamp": "...",
  "edges": [
    {
      "rank": 1,
      "pair": "EURUSD",
      "timeframe": "H1",
      "indicator": "RSI",
      "parameters": {"period": 14, "oversold": 30, "overbought": 70},
      "metrics": {
        "win_rate": 0.62,
        "profit_factor": 1.55,
        "sharpe": 0.95,
        "total_trades": 87,
        "walk_forward_pass": true,
        "oos_p_value": 0.008
      },
      "council_scores": {
        "quant": 82,
        "microstructure": 75,
        "behavioral": 80,
        "risk": 65,
        "strategy": 90,
        "final": 78
      },
      "economic_rationale": "...",
      "who_loses": "...",
      "decay_baseline": "WR=0.62, discovered=2026-07-27",
      "status": "active"
    }
  ]
}
```

---

## 5. Decay Tracking

Each run compares current edge performance to discovery baseline:
```python
decay_pct = (current_wr - baseline_wr) / baseline_wr * 100
if decay_pct < -20:
    alert("Edge DECAYING: EURUSD H1 RSI-14 WR dropped {decay_pct:.0f}%")
if decay_pct < -20 for 3 consecutive runs:
    remove("Edge REMOVED: EURUSD H1 RSI-14 — sustained decay")
```

---

## 6. Cron Wrapper

Follows the established pattern:
```python
# edge_discovery_wrapper.py
os.chdir(r"C:\Trading\edge_discovery\scripts")
subprocess.run([sys.executable, "edge_scanner.py", "--file-only", "--quiet"], timeout=600)
print("edge_discovery done")
```
