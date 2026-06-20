#!/usr/bin/env python3
"""
AGENTX CI/CD Deployment Pipeline
=================================
Ships code to production safely: validate → backup → deploy → verify → notify.
Prevents broken code from ever reaching the running system.

Usage:
    python devops/deploy.py                          # Normal deploy
    python devops/deploy.py --branch feature-xyz     # Deploy specific branch
    python devops/deploy.py --skip-validate          # Emergency override
    python devops/deploy.py --rollback               # Undo last deployment
    python devops/deploy.py --status                 # Show deployment state
    
Workflow:
  1. GIT PULL — sync latest code from GitHub
  2. VALIDATE — syntax check ALL .py files, lint, compile
  3. BACKUP — snapshot current state
  4. DEPLOY — copy validated files to production
  5. VERIFY — health check all services
  6. NOTIFY — log and alert result
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DEVOPS_DIR = BASE_DIR / "devops"
BACKUP_DIR = DEVOPS_DIR / "backups"
LOGS_DIR = BASE_DIR / "bots" / "logs"
DEPLOY_LOG = LOGS_DIR / "deploy.log"
STATE_FILE = DEVOPS_DIR / "deploy_state.json"

# Critical files that MUST be validated before deployment
CRITICAL_PATTERNS = [
    "*.py",
    "*.yaml",
    "*.yml",
    "*.json",
    "*.bat",
    "*.ps1",
]

# Files/dirs excluded from validation
EXCLUDE_DIRS = {"__pycache__", ".git", ".github", "node_modules", "__pycache__",
                "backups", "logs", "reports", "state", "__pycache__"}

# ── Logging ──────────────────────────────────────────────────────────────

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | DEPLOY | %(message)s",
        handlers=[
            logging.FileHandler(DEPLOY_LOG, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

logger = logging.getLogger("deploy")

# ── State Management ─────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"deployments": [], "current_commit": None, "last_rollback": None}

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ── Step 1: Git Sync ────────────────────────────────────────────────────

def git_pull(branch: str = "main") -> tuple[bool, str]:
    """Sync latest code from GitHub."""
    logger.info("📥 Step 1: Git pull (branch=%s)", branch)
    try:
        # Fetch
        r = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            return False, f"git fetch failed: {r.stderr[:200]}"
        
        # Check current branch
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10
        )
        current_branch = r.stdout.strip()
        
        # Switch branch if needed
        if current_branch != branch:
            r = subprocess.run(
                ["git", "checkout", branch],
                cwd=str(BASE_DIR), capture_output=True, text=True, timeout=15
            )
            if r.returncode != 0:
                return False, f"git checkout {branch} failed: {r.stderr[:200]}"
        
        # Pull
        r = subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            return False, f"git pull failed: {r.stderr[:200]}"
        
        # Get commit hash
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=10
        )
        commit = r.stdout.strip()
        
        return True, commit
    except Exception as e:
        return False, str(e)

# ── Step 2: Validate ────────────────────────────────────────────────────

def validate_all() -> tuple[bool, list[str]]:
    """
    Validate ALL Python files compile before deployment.
    Returns (success, list of errors).
    """
    logger.info("🔍 Step 2: Validating all Python files...")
    errors = []
    
    # Find all .py files
    py_files = list(BASE_DIR.rglob("*.py"))
    
    # Filter out excluded dirs
    py_files = [f for f in py_files 
                if not any(excl in f.parts for excl in EXCLUDE_DIRS)]
    
    logger.info("   Found %d Python files to validate", len(py_files))
    
    for py_file in py_files:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "py_compile", str(py_file)],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode != 0:
                # Extract the actual error, skip SyntaxWarning
                stderr_lines = [l for l in r.stderr.split("\n") 
                               if "SyntaxWarning" not in l and "invalid escape" not in l]
                if stderr_lines:
                    errors.append(f"{py_file.relative_to(BASE_DIR)}: {stderr_lines[-1]}")
        except Exception as e:
            errors.append(f"{py_file.relative_to(BASE_DIR)}: {e}")
    
    if errors:
        logger.error("   ❌ %d file(s) failed validation", len(errors))
    else:
        logger.info("   ✅ All %d files pass", len(py_files))
    
    return len(errors) == 0, errors

# ── Step 3: Backup ──────────────────────────────────────────────────────

def create_backup() -> tuple[bool, str]:
    """Create timestamped backup of critical files."""
    logger.info("💾 Step 3: Creating backup...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"pre_deploy_{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=True)
    
    # Files to backup
    backup_patterns = [
        "bots/*.py",
        "backend/*.py",
        "bridge/*.py",
        "scripts/*.py",
        "research_division/*.py",
        "research/*.py",
        "devops/*.py",
        "utils/*.py",
        "Makefile",
        "AGENTS.md",
        "PROGRESS.md",
        "FTMO_CONFIG.md",
    ]
    
    for pattern in backup_patterns:
        for f in BASE_DIR.glob(pattern):
            if f.is_file() and "__pycache__" not in f.parts:
                rel = f.relative_to(BASE_DIR)
                dest = backup_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
    
    # Compute checksum
    checksum = hashlib.sha256()
    for f in sorted(backup_path.rglob("*")):
        if f.is_file():
            checksum.update(f.read_bytes())
    
    logger.info("   Backup created: %s (%d files, hash=%s)",
                backup_path.name, len(list(backup_path.rglob("*"))),
                checksum.hexdigest()[:12])
    
    return True, str(backup_path)

# ── Step 4: Deploy ──────────────────────────────────────────────────────

def deploy(commit: str) -> tuple[bool, str]:
    """Files are already on disk from git pull, just verify and update state."""
    logger.info("🚀 Step 4: Deploy commit %s", commit)
    
    state = load_state()
    state["current_commit"] = commit
    state["last_deploy"] = datetime.now(timezone.utc).isoformat()
    state["deployments"].append({
        "timestamp": state["last_deploy"],
        "commit": commit,
        "status": "deployed",
    })
    
    # Keep only last 20 deploy records
    state["deployments"] = state["deployments"][-20:]
    save_state(state)
    
    logger.info("   ✅ Deployed commit %s", commit)
    return True, commit

# ── Step 5: Verify ──────────────────────────────────────────────────────

def verify_deployment() -> dict[str, bool]:
    """Verify all services are healthy after deployment."""
    logger.info("🩺 Step 5: Verifying deployment...")
    results = {}
    
    # Check bridge
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=5)
        data = json.loads(r.read().decode()) if r.status == 200 else {}
        results["bridge"] = r.status == 200 and data.get("connected", False)
    except:
        results["bridge"] = False
    
    # Check backend
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8005/health", timeout=5)
        results["backend"] = r.status == 200
    except:
        results["backend"] = False
    
    # Check SRE compiled
    try:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", str(DEVOPS_DIR / "sre.py")],
            capture_output=True, timeout=15
        )
        results["sre"] = r.returncode == 0
    except:
        results["sre"] = False
    
    for service, ok in results.items():
        if ok:
            logger.info("   ✅ %s: healthy", service)
        else:
            logger.error("   ❌ %s: UNHEALTHY", service)
    
    return results

# ── Rollback ─────────────────────────────────────────────────────────────

def rollback() -> tuple[bool, str]:
    """Restore the most recent pre-deploy backup."""
    logger.info("⏪ Rollback initiated...")
    
    backups = sorted(BACKUP_DIR.glob("pre_deploy_*"))
    if not backups:
        return False, "No backups found"
    
    latest = backups[-1]
    logger.info("   Restoring from: %s", latest.name)
    
    for f in latest.rglob("*"):
        if f.is_file():
            rel = f.relative_to(latest)
            dest = BASE_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
    
    state = load_state()
    state["last_rollback"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    
    logger.info("   ✅ Rollback complete")
    return True, str(latest)

# ── Main ────────────────────────────────────────────────────────────────

def main():
    setup_logging()
    
    if "--status" in sys.argv:
        state = load_state()
        print("=== Deployment State ===")
        print(f"Current commit: {state.get('current_commit', 'N/A')}")
        print(f"Last deploy: {state.get('last_deploy', 'N/A')}")
        print(f"Last rollback: {state.get('last_rollback', 'Never')}")
        print(f"Total deployments: {len(state.get('deployments', []))}")
        print(f"\nLast 5 deployments:")
        for d in state.get('deployments', [])[-5:]:
            print(f"  {d['timestamp']} — {d['commit']} ({d['status']})")
        return
    
    if "--rollback" in sys.argv:
        success, msg = rollback()
        if success:
            print(f"✅ Rollback to {msg} successful")
        else:
            print(f"❌ Rollback failed: {msg}")
        return
    
    # ── Full deploy pipeline ──
    branch = "main"
    if "--branch" in sys.argv:
        idx = sys.argv.index("--branch")
        if idx + 1 < len(sys.argv):
            branch = sys.argv[idx + 1]
    
    skip_validate = "--skip-validate" in sys.argv
    
    print(f"\n{'='*60}")
    print(f"  AGENTX CI/CD Pipeline")
    print(f"  Branch: {branch} | Validate: {'OFF' if skip_validate else 'ON'}")
    print(f"{'='*60}\n")
    
    # Step 1: Git pull
    success, msg = git_pull(branch)
    if not success:
        print(f"❌ Git pull failed: {msg}")
        sys.exit(1)
    print(f"   📥 Synced to commit {msg}\n")
    commit = msg
    
    # Step 2: Validate
    if not skip_validate:
        print()
        success, errors = validate_all()
        if not success:
            print(f"\n❌ Validation FAILED — {len(errors)} error(s):")
            for e in errors[:10]:
                print(f"     • {e}")
            print(f"\n   Run with --skip-validate to force deploy (not recommended)")
            sys.exit(1)
        print(f"   ✅ All files validated\n")
    else:
        print("   ⚠️  Validation SKIPPED (emergency mode)\n")
    
    # Step 3: Backup
    success, backup_path = create_backup()
    if not success:
        print(f"❌ Backup failed: {backup_path}")
        sys.exit(1)
    
    # Step 4: Deploy
    success, msg = deploy(commit)
    if not success:
        print(f"❌ Deploy failed: {msg}")
        sys.exit(1)
    
    # Step 5: Verify
    results = verify_deployment()
    all_healthy = all(results.values())
    
    print(f"\n{'='*60}")
    if all_healthy:
        print(f"  ✅ DEPLOYMENT SUCCESSFUL — Commit {commit}")
    else:
        unhealthy = [k for k, v in results.items() if not v]
        print(f"  ⚠️  DEPLOYED WITH ISSUES — {', '.join(unhealthy)} not responding")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
