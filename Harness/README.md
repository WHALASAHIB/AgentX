# 🏗️ AGENTX Harness Engineering Framework

**Source:** [Learn Harness Engineering](https://walkinglabs.github.io/learn-harness-engineering/en/) by Walking Labs
**Applied to:** AGENTX v3 Trading System
**Date:** 2026-06-20

---

## What's in this folder

| File | What It Is | Read First? |
|------|-----------|-------------|
| **`AGENTS.md`** | 🧭 **Entry point / router** — project overview, 8 hard constraints, init phase, verification gating, scope boundaries, clean state protocol | ✅ Yes |
| **`ARCHITECTURE.md`** | 🏛️ **System architecture** — component diagram, data flow, port mapping, deployment model | When you need to understand how everything connects |
| **`PROGRESS.md`** | 📊 **Live state tracking** — sprint status, completed items, in-progress, blocked items, known issues | Every session start |
| **`FEATURES_TEMPLATE.md`** | 📋 **Feature specification template** — structured format for defining tasks with scope, acceptance criteria, dependencies | When creating a new task/feature |
| **`clean-state-protocol.md`** | 🧹 **End-of-session checklist** — 8 steps + common traps + templates | Before finishing any session |
| **`Makefile`** | ⚡ **Task automation** — `make init` (start), `make check` (health), `make e2e` (verify done) | For automation reference |

## The 5 Harness Subsystems

```
INSTRUCTIONS  → AGENTS.md (router)
TOOLS         → Makefile
ENVIRONMENT   → requirements.txt, .python-version
STATE         → PROGRESS.md
FEEDBACK      → make check, make e2e
```

## Quick Start

```bash
cd C:/Trading/Harness
less AGENTS.md    # Start here
less ARCHITECTURE.md  # Then architecture
```

---

*Part of AGENTX v3 — Sprint 4: Harness Engineering & Reliability*
