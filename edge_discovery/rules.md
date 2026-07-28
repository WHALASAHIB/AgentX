# Rules & Constraints — Edge Discovery Loop

## Inviolable Rules

### 1. NO overfitting
- Every candidate edge MUST be tested on out-of-sample data (last 25% of dataset)
- Walk-forward: 3-fold split, edge must survive all 3
- Minimum 30 signal-generating trades for statistical validity
- If win rate drops > 10% between in-sample and out-of-sample → REJECT

### 2. Economic rationale is MANDATORY
- An edge without a "who loses?" explanation is NOT an edge — it's noise
- Acceptable explanations: institutional flow, retail behavior, structural market mechanics, liquidity dynamics
- Unacceptable: "the indicator works because it works"

### 3. No data snooping
- Holm-Bonferroni correction for multiple comparisons
- If scanning 20,000 parameter combinations, adjust p-value threshold accordingly
- Report the total number of combos scanned alongside results

### 4. No peak-performance chasing
- The "best" parameter combo is almost certainly overfitted
- Prefer parameter neighborhoods (any combo within 10% of peak is valid)
- Report robustness: what % of nearby parameters also produce positive results

### 5. Council diversity
- No single perspective can determine an edge is valid
- Minimum 3 council members must agree
- Disagreements must be documented, not hidden
- If council cannot reach consensus → edge is rejected

### 6. Edge decay monitoring
- Once discovered, edges are tracked in `edge_state.json`
- Each subsequent run compares current performance to discovery baseline
- If current WR drops > 20% relative to baseline → FLAG
- If below baseline for 3 consecutive runs → REMOVE from active list

### 7. Honesty over actionability
- It is BETTER to report "no significant edges found this run" than to report a weak edge
- Edge discovery is allowed to return ZERO results
- Return nothing rather than garbage

## Technical Constraints

- Single-threaded Python (no multiprocessing on this machine)
- MT5 cached data: ~2000 bars max per symbol/tf
- Total run time must be < 30 min (cron has 60 min timeout)
- Logging: verbose to file, minimal to stdout (cron wrapper pattern)
- No external API calls (no TradingView, no broker API beyond MT5)

## Edge Quality Thresholds

| Metric | Minimum | Strong | Elite |
|--------|---------|--------|-------|
| Win Rate | > 55% | > 60% | > 65% |
| Profit Factor | > 1.3 | > 1.5 | > 2.0 |
| Sharpe Ratio | > 0.5 | > 1.0 | > 1.5 |
| Drawdown | < 15% | < 10% | < 5% |
| Min Trades | 30 | 50 | 100 |
| Walk-forward consistency | 3/3 | 3/3 | 3/3 |
| OOS p-value | < 0.05 | < 0.01 | < 0.001 |
| Council score | > 60 | > 75 | > 85 |
