# Feature Specification Template — AGENTX

Use this template to define every new feature, modification, or bugfix in the AGENTX trading system. Each feature gets its own file under `features/` (e.g., `features/F-042-add-bridge-retry.md`).

---

```yaml
---
feature_id: F-XXX
status: draft | approved | in-progress | done | blocked
created: YYYY-MM-DD
author: <name>
---
```

## 1. Feature Name / ID

**Feature Name:** <short, descriptive name, e.g., "Bridge Retry with Exponential Backoff">
**Feature ID:** F-XXX

## 2. Description (What to Build)

<A clear, concise description of what this feature does. Write it for a developer who has context on the system but has not seen this ticket before. Include the motivation/problem this solves.>

**Problem:** <what currently doesn't work or what gap exists>
**Solution:** <what the feature implements>
**User Story:** As a <role>, I want <capability> so that <benefit>.

## 3. Acceptance Criteria (Definition of Done)

*How will we verify this feature is working? Each criterion must be testable — preferably automatable.*

- [ ] AC-1: <specific, measurable condition, e.g., "When bridge drops connection, client retries up to 3 times with 1s/2s/4s backoff">
- [ ] AC-2: <e.g., "Logs record each retry attempt with timestamp and attempt number">
- [ ] AC-3: <e.g., "Dashboard shows bridge connection status as 'Connected' / 'Reconnecting' / 'Disconnected'">
- [ ] AC-4: <e.g., "Existing tests still pass (`pytest tests/`)">

## 4. Dependencies (Must Exist First)

*What must be true, installed, or already built before this feature can be implemented?*

- [ ] <dependency 1, e.g., "bridge_client.py must expose status endpoint">
- [ ] <dependency 2, e.g., "Hermes profile must have cron permissions">
- [ ] <dependency 3, e.g., "Python `tenacity` library installed (`pip install tenacity`)">

## 5. Files to Modify

*Which files will be created or changed? Be specific — use relative paths from the repo root.*

- `backend/bridge_client.py` — add retry logic to `send_order()` and `fetch_ticks()`
- `backend/routes/bridge_status.py` — new file: expose connection status endpoint
- `frontend/public/index.html` — add bridge status indicator to dashboard header

## 6. Files NOT to Modify (Anti-Scope)

*Explicitly list files that are off-limits for this feature. Prevents scope creep and accidental side effects.*

- `backend/db/pool.py` — no database changes
- `bots/` — no bot logic changes
- `research_division/` — no research pipeline changes
- `.env.keys` — no secret changes
- `backend/auth.py` — no authentication changes

## 7. Priority

| Priority | Meaning                                              |
|----------|------------------------------------------------------|
| **P0**   | Blocking / critical — system unusable without it     |
| **P1**   | Important — should be done this sprint               |
| **P2**   | Nice to have — when time permits                     |

**Priority:** P1

## 8. Estimated Session Count

<How many Hermes agent sessions (or developer sessions) to implement, test, and verify?>

**Estimated Sessions:** 2
**Estimated Developer Hours:** 4–6

---

## Example Filled-In Feature

Below is a real example using the template above.

```yaml
---
feature_id: F-001
status: done
created: 2025-11-15
author: Hermes
---
```

### 1. Feature Name / ID

**Feature Name:** Clean State Protocol Enforcement
**Feature ID:** F-001

### 2. Description

**Problem:** Dirty state in research_division/reports/ and SQLite caches causes stale data to leak into new feature deployments. When the research cycle runs, it picks up old session data alongside new, producing corrupted analytics and phantom trade signals.

**Solution:** Add a pre-deployment clean-state check that clears research_division/reports/ contents, flushes relevant SQLite caches, and verifies zero residual state before a new research cycle begins. The check runs as a Hermes cron pre-hook and blocks deployment if dirt is detected.

**User Story:** As a system operator, I want the research pipeline to start from a clean state every cycle so that analytics, backtests, and deployments are based on current data only.

### 3. Acceptance Criteria

- [ ] AC-1: Running `python backend/clean_state.py --check` returns exit code 0 if clean, 1 if dirty
- [ ] AC-2: Running `python backend/clean_state.py --clean` removes all files in `research_division/reports/` and clears stale cache entries
- [ ] AC-3: If dirty state is detected and `--clean` is not passed, the research cron job exits with error before any data collection
- [ ] AC-4: A log entry is written to `backend/logs/clean_state.log` for every check/clean action
- [ ] AC-5: All existing tests pass after clean state enforcement is in place

### 4. Dependencies

- [ ] `research_division/reports/` directory must exist
- [ ] Hermes cron job for research cycle has pre-hook support
- [ ] SQLite `backend/db/pool.py` exposes `flush_cache()` method

### 5. Files to Modify

- `backend/clean_state.py` — new file: clean state checker/cleaner
- `backend/scheduler.py` — add pre-hook call to clean_state before research cycle
- `backend/db/pool.py` — add `flush_cache()` and `is_cache_stale()` methods

### 6. Files NOT to Modify

- `bots/` — no bot logic changes
- `frontend/public/index.html` — no UI changes
- `backend/auth.py` — no auth changes
- `backend/bridge_client.py` — no bridge changes
- `research_division/` — no logic changes; data directory is consumed, not modified

### 7. Priority

**Priority:** P0

### 8. Estimated Session Count

**Estimated Sessions:** 2
**Estimated Developer Hours:** 3–5
