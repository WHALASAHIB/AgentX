# Clean State Protocol — Reference Document

**One-line summary:** Before any deployment or research cycle, verify zero residual state — if dirty, purge and reacquire from source of truth.

---

## What Is the Clean State Protocol?

The Clean State Protocol (CSP) is a discipline for ensuring that every new feature deployment, research cycle, or system operation starts from a known-good, zero-residual state. It prevents stale data, phantom signals, corrupted analytics, and "works on my machine" bugs caused by accumulated dirt in the filesystem, database caches, and in-memory state.

---

## The 8 Steps

### Step 1: Define the Clean Boundary

**Action:** Enumerate every location where persistent state lives.

**Checklist:**
- [ ] Filesystem directories (reports, logs, temp files, uploads)
- [ ] Database tables and caches (application cache, session cache, query cache)
- [ ] In-memory state (global variables, singleton instances, class-level caches)
- [ ] External service state (Redis keys, Cloudflare KV, Notion page caches)
- [ ] Environment artifacts (`.pyc` files, `__pycache__/`, stale `.env` overrides)

**AGENTX Example:**
| Location | Type | Clean Action |
|---|---|---|
| `research_division/reports/` | Filesystem | `rm -rf *.json` |
| SQLite cache (pool.py) | Database | `flush_cache()` |
| Redis (if used) | External | `FLUSHDB` on cache DB |
| `__pycache__/` dirs | Filesystem | `find . -type d -name __pycache__ -exec rm -rf {} +` |

---

### Step 2: Snapshot Current State (Pre-Clean)

**Action:** Before modifying anything, record what exists. This enables rollback if the clean operation destroys something unexpectedly.

**Checklist:**
- [ ] `ls -laR` of all clean-boundary directories → piped to `pre_clean_manifest.txt`
- [ ] SQLite dump of relevant cache tables → `pre_clean_cache_dump.sql`
- [ ] Redis `KEYS *` → `pre_clean_redis_keys.txt`
- [ ] Git status (`git status --short`) → `pre_clean_git_status.txt`

**AGENTX Command:**
```bash
# Snapshot reports directory
ls -laR research_division/reports/ > /tmp/pre_clean_reports.txt

# Snapshot SQLite cache tables
sqlite3 data/trading.db ".dump cache_trades" > /tmp/pre_clean_cache.sql

# Snapshot git dirty files
git status --short > /tmp/pre_clean_git.txt
```

---

### Step 3: Assert Clean State (The Check)

**Action:** Verify that each location in the clean boundary is empty or at its expected baseline. If any location is dirty, fail immediately — do not proceed.

**Checklist:**
- [ ] Reports directory is empty: `ls research_division/reports/ | wc -l` → 0
- [ ] Cache table row count: `SELECT COUNT(*) FROM cache_trades` → 0
- [ ] Redis cache DB size: `DBSIZE` → 0
- [ ] No stale `.pyc` outside `__pycache__`: `find . -name '*.pyc'` → empty
- [ ] No orphaned PID files: `ls *.pid 2>/dev/null` → empty

**AGENTX Implementation (`clean_state.py`):**
```python
def check_clean() -> bool:
    checks = [
        (is_dir_empty, "research_division/reports/"),
        (is_table_empty, "cache_trades", "sqlite:///data/trading.db"),
        (is_redis_empty, "redis://localhost:6379/1"),
        (no_stale_pyc, "."),
    ]
    for check_fn, *args in checks:
        if not check_fn(*args):
            log_dirty("check", args[0])
            return False
    log_clean("All clean-boundary locations verified empty")
    return True
```

**Exit codes:** 0 = clean (proceed), 1 = dirty (block).

---

### Step 4: Execute the Clean (The Purge)

**Action:** Remove all state within the clean boundary. Do this only after Step 3 has failed (i.e., dirt was found) OR when `--force` is passed.

**Checklist:**
- [ ] `rm -rf research_division/reports/*`
- [ ] `DELETE FROM cache_trades`
- [ ] `VACUUM` on SQLite to reclaim space
- [ ] Redis `FLUSHDB` on the cache DB index
- [ ] `find . -type d -name __pycache__ -exec rm -rf {} +`
- [ ] Remove stale PID files: `rm -f *.pid`

**AGENTX Command:**
```bash
python backend/clean_state.py --clean
```

**Safety:**
- Never `--clean` without first taking a snapshot (Step 2).
- Log every deletion with timestamp, path, and file count.
- If a critical file would be deleted (e.g., a database file not in cache), abort.

---

### Step 5: Verify Clean State (Post-Clean Assertion)

**Action:** Re-run Step 3 checks to confirm the purge was successful. If any location is still dirty, log a critical error and exit non-zero.

**Checklist:**
- [ ] Re-run all Step 3 checks
- [ ] Compare output against expected empty baseline
- [ ] If any check fails → exit code 1, do not proceed

**AGENTX Pattern:**
```python
if not check_clean():
    log_critical("Post-clean verification FAILED — aborting deployment")
    sys.exit(1)
log_info("Post-clean verification PASSED")
```

---

### Step 6: Reacquire from Source of Truth

**Action:** Populate the clean boundary with fresh data from the authoritative source. If the clean boundary should remain empty (e.g., reports before a research cycle), this step is a no-op.

**Checklist:**
- [ ] Re-fetch market data from MT5 bridge (if needed)
- [ ] Rebuild cache from database source tables (not from cache)
- [ ] Reinitialize in-memory singletons
- [ ] Verify reacquired data integrity (checksums, row counts)

**AGENTX Example:**
```python
# After clean, reacquire only what's needed for this cycle
if args.reacquire:
    market_data = bridge_client.fetch_current_prices()
    db.cache_trades.insert_many(market_data)
    log_info(f"Reacquired {len(market_data)} market data points from MT5 bridge")
```

---

### Step 7: Proceed with Deployment / Operation

**Action:** Run the feature deployment, research cycle, or system operation now that the clean state is confirmed.

**Checklist:**
- [ ] Deployment script runs without dirty-state warnings
- [ ] Research cycle begins with zero residual data
- [ ] Feature tests pass on clean baseline

---

### Step 8: Post-Operation Assertion

**Action:** After the operation completes, verify the system state is consistent. This catches unexpected side effects.

**Checklist:**
- [ ] No unexpected files created outside expected output directories
- [ ] Database integrity check: `PRAGMA integrity_check`
- [ ] Logs show clean shutdown (no unhandled exceptions)
- [ ] Snapshot post-operation state for comparison with pre-clean snapshot

**AGENTX Command:**
```bash
python backend/clean_state.py --verify-post
```

---

## Checklist Template

```
CLEAN STATE PROTOCOL CHECKLIST
===============================
Feature/Operation: _______________________
Date: ___________________________________

[ ] Step 1: Clean boundary defined
[ ] Step 2: Pre-clean snapshot taken
[ ] Step 3: Clean state asserted (pre-clean)
[ ] Step 4: Purge executed (if needed)
[ ] Step 5: Post-clean verification
[ ] Step 6: Reacquire from source of truth
[ ] Step 7: Proceed with deployment
[ ] Step 8: Post-operation assertion

Pre-clean snapshot path: ________________
Post-clean snapshot path: _______________
Operator: _______________________________
```

---

## Common Dirty-State Traps

| # | Trap | Symptom | How to Avoid |
|---|------|---------|--------------|
| 1 | **Stale report JSON** | Old analytics included in new deployment | Always clear `research_division/reports/` before research cycle |
| 2 | **Database cache drift** | `cache_trades` table has rows from previous session | Add `flush_cache()` to pre-hook |
| 3 | **Orphaned `__pycache__`** | Python imports stale bytecode after rename | `find . -type d -name __pycache__ -exec rm -rf {} +` |
| 4 | **Global variable bleed** | Singleton `AppState` retains values from previous test | Re-initialize singletons in `setUp()` or pre-hook |
| 5 | **PID file left over** | New process thinks old one is still running | Clean all `*.pid` at startup |
| 6 | **Redis keys from old sessions** | Cache hit returns stale data | Use separate Redis DB index per environment; flush on start |
| 7 | **Log file accumulation** | Disk fills up over weeks | Rotate logs and set retention policy in Step 1 |
| 8 | **.env override leaks** | A stale environment variable overrides new config | Load env from canonical file only; verify expected key count |

---

## One-Line Summary

> **Before any deployment or research cycle, verify zero residual state — if dirty, purge and reacquire from source of truth.**

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│                     CLEAN STATE PROTOCOL                    │
├─────────────────────────────────────────────────────────────┤
│  1. Define  → What is the clean boundary?                   │
│  2. Snapshot → Save current state for rollback              │
│  3. Assert   → Is it already clean? (exit 0=yes, 1=no)     │
│  4. Purge    → Remove dirt (only if Step 3 failed)         │
│  5. Verify   → Confirm purge succeeded                     │
│  6. Reacquire→ Re-fetch from source of truth               │
│  7. Proceed  → Run deployment / operation                  │
│  8. Assert   → Post-operation consistency check            │
└─────────────────────────────────────────────────────────────┘
```

## AGENTX Integration Points

- **Hermes Cron Pre-Hook:** `backend/clean_state.py --check` runs before every research cycle. If dirty (exit 1), the cron job sends a Telegram alert and aborts.
- **Deployment Gate:** CI/CD pipeline runs `clean_state.py --check --verbose` before `git pull && systemctl restart trading-backend`.
- **Feature Testing:** Every new feature's test suite calls `CleanStateProtocol().execute()` in its `setUp()` to ensure test isolation.
