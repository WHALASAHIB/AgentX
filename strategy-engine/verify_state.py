"""Strategy Engine state integrity check.

Verification command for this environment (make is not installed in git-bash):
    python verify_state.py

Checks: state.json parses, iteration counter is consistent with the evolution
log, last entry carries all required metrics, best_strategy pine exists, and
the newest pine file is a plausible Pine Script.
"""
import json
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / "state.json"
PINES = ROOT / "pines"

REQUIRED_METRICS = ("pf", "sharpe", "wr", "dd", "trades", "net_profit")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    if not STATE.exists():
        fail(f"{STATE} missing")
    s = json.loads(STATE.read_text(encoding="utf-8"))
    log = s.get("evolution_log", [])
    if not isinstance(log, list) or not log:
        fail("evolution_log empty")
    last = log[-1]
    if not isinstance(last.get("iteration"), int):
        fail("last log entry has no integer iteration")
    if s.get("iteration") != last["iteration"] + 1:
        fail(f"state iteration {s.get('iteration')} != last log iteration + 1 ({last['iteration'] + 1})")
    metrics = last.get("metrics", {})
    missing = [k for k in REQUIRED_METRICS if k not in metrics]
    if missing:
        fail(f"last entry missing metrics: {missing}")
    best = s.get("best_strategy")
    if best and not (PINES / best).exists():
        fail(f"best_strategy file missing: {PINES / best}")
    pines = sorted(PINES.glob("*.pine"), key=lambda p: p.stat().st_mtime)
    if not pines:
        fail("no .pine files in pines/")
    newest = pines[-1].read_text(encoding="utf-8", errors="replace")
    if "//@version=" not in newest or "strategy(" not in newest:
        fail(f"newest pine {pines[-1].name} is not a plausible Pine Script")
    print(f"PASS: iteration={s.get('iteration')} log_entries={len(log)} "
          f"last_iter={last['iteration']} best={best} newest_pine={pines[-1].name}")


if __name__ == "__main__":
    main()
