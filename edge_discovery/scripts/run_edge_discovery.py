#!/usr/bin/env python3
"""
Edge Discovery Orchestrator — full pipeline runner.
Chains: data fetch → parameter scan → pattern scan → council review → report.

Usage:
    python run_edge_discovery.py                    # Auto-rotate, all TFs
    python run_edge_discovery.py --pair EURUSD      # Force pair
    python run_edge_discovery.py --pair XAUUSD --timeframe H1
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))
STATE_DIR = os.path.join(BASE_DIR, "state")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


def run_step(name: str, script: str, args: list[str],
             timeout: int = 600) -> tuple[int, str, str]:
    """Run a pipeline step as a subprocess."""
    print(f"\n{'='*60}")
    print(f"  [{name}] Running {script}...")
    print(f"{'='*60}")

    start = time.time()
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, script)] + args,
        capture_output=True, text=True, timeout=timeout
    )
    elapsed = time.time() - start

    out = result.stdout.strip()
    err = result.stderr.strip()

    print(f"  [{name}] Completed in {elapsed:.1f}s (exit={result.returncode})")
    if out:
        print(f"  >> {out.split(chr(10))[-1]}")
    if err and result.returncode != 0:
        print(f"  !! {err.split(chr(10))[-1]}")

    return result.returncode, out, err


def main() -> int:
    parser = argparse.ArgumentParser(description="Edge Discovery Orchestrator")
    parser.add_argument("--pair", type=str, default=None,
                        help="Force specific pair")
    parser.add_argument("--timeframe", type=str, default=None,
                        help="Single timeframe only")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Force data re-download")
    parser.add_argument("--skip-scan", action="store_true",
                        help="Skip scan step (council only)")
    parser.add_argument("--skip-council", action="store_true",
                        help="Skip council step (scan only)")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimal output")
    args = parser.parse_args()

    overall_start = time.time()
    pair = args.pair or "auto"

    # Build common args
    scan_args = ["--file-only", "--quiet"]
    if args.pair:
        scan_args += ["--pair", args.pair]
    if args.timeframe:
        scan_args += ["--timeframe", args.timeframe]
    if args.force_refresh:
        scan_args.append("--force-refresh")

    council_args = ["--file-only", "--quiet"]
    if args.pair:
        council_args += ["--input", os.path.join(STATE_DIR, "edge_state.json")]

    # Step 1: Scan
    if not args.skip_scan:
        rc, out, err = run_step("SCAN", "edge_scanner.py", scan_args)
        if rc != 0:
            print(f"  ❌ Scan failed (exit={rc})")
            return rc
    else:
        print("  ⏭️  Scan skipped")

    # Step 2: Council
    if not args.skip_council:
        rc, out, err = run_step("COUNCIL", "council.py", council_args)
        if rc != 0:
            print(f"  ❌ Council failed (exit={rc})")
            return rc
    else:
        print("  ⏭️  Council skipped")

    # Summary
    elapsed = time.time() - overall_start
    print(f"\n{'='*60}")
    print(f"  ✅ EDGE DISCOVERY COMPLETE — {pair}")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Pair: {pair} | Timeframe: {args.timeframe or 'all'}")

    # Read results
    verdict_file = os.path.join(STATE_DIR, "council_verdict.json")
    if os.path.exists(verdict_file):
        with open(verdict_file, "r") as f:
            verdict = json.load(f)
        accepted = verdict.get("accepted", 0)
        rejected = verdict.get("rejected", 0)
        print(f"  Council: {accepted} accepted | {rejected} rejected")

        if accepted > 0:
            top = verdict["edges"][0]
            print(f"  🏆 Top edge: {top['pair']} {top['timeframe']} {top['indicator']} "
                  f"(score={top['council_final']})")
            print(f"     WR={top['win_rate']*100:.1f}% PF={top['profit_factor']:.2f}")
    else:
        print(f"  ⚠️  No council verdict (scan yielded zero candidates)")

    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
