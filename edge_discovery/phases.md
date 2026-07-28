# Phased Execution Plan — Edge Discovery Loop

## Phase 1: Foundation (Build)
**Estimated: 2-3 hours**

Build the core engine scripts:
- [ ] `data_cache.py` — MT5 data fetching, caching, bar management
- [ ] `indicator_lib.py` — All indicator calculations (numpy-vectorized)
- [ ] `pattern_lib.py` — Candlestick + chart pattern recognition
- [ ] `edge_scanner.py` — Brute-force scan engine (main orchestrator)
- [ ] `council.py` — Edge evaluation & scoring
- [ ] Cron job registration

**Verify:** Run a dry scan on 1 pair × 1 timeframe × 1 indicator family. Should complete < 30s.

## Phase 2: Full Scan + Tuning
**Estimated: 1-2 hours**

- [ ] Run full scan (all pairs × all tfs × all indicators) in foreground
- [ ] Profile performance — optimize slow paths
- [ ] Verify cache works correctly (skip fresh data)
- [ ] Tune parameter grids to balance coverage vs speed
- [ ] Run council review on dummy edges to verify logic

**Verify:** Complete scan in < 15 min. Council produces reasoned output.

## Phase 3: Council Refinement
**Estimated: 1 hour**

- [ ] Write the council prompt logic (LLM-based review)
- [ ] Test with real scan output
- [ ] Verify "who loses?" reasoning is required
- [ ] Test edge case: no valid edges → returns empty
- [ ] Test edge case: all edges rejected → explains why

**Verify:** Council rejects weak edges with specific reasoning. Accepts strong edges with "who loses?" explanation.

## Phase 4: Cron Integration
**Estimated: 30 min**

- [ ] Register cron job: every 6h (07, 13, 19, 01 HKT)
- [ ] Set up delivery to appropriate channel/thread
- [ ] Test first automated run
- [ ] Verify archive/ gets populated

**Verify:** First cron run completes, report lands in Telegram.

## Phase 5: Decay Tracking
**Estimated: 30 min**

- [ ] Implement edge_state.json with baseline tracking
- [ ] Implement decay detection logic (>20% drop = alert)
- [ ] Wire into existing risk_supervisor (risk supervisor reads edge state)

**Verify:** Manually adjust baseline, confirm alert fires.

## Phase 6: Review & Iterate
**Ongoing**

- First week: manually review every run. Check council logic.
- After week 1: trust the system, respond to alerts only.
- Monthly: archive review and parameter space expansion.
