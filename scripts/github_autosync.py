"""
AGENTX GitHub Auto-Sync
Pushes local code changes to GitHub every hour.
Handles: add, commit (if changes), push.
Silent if no changes (no output).
"""
import subprocess, os, sys
from pathlib import Path

REPO_DIR = Path(r"C:\Trading")
LOG_FILE = REPO_DIR / ".git" / "autosync.log"

os.chdir(str(REPO_DIR))

# Check if there are changes
r = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True, text=True, timeout=30
)

if not r.stdout.strip():
    # No changes — silent exit
    sys.exit(0)

# Changes detected — commit and push
changes = r.stdout.strip()
with open(LOG_FILE, "a") as f:
    f.write(f"Changes detected at {__import__('datetime').datetime.now()}\n")
    f.write(changes + "\n")

# Add all
subprocess.run(["git", "add", "-A"], capture_output=True, timeout=30)

# Commit
commit_msg = f"auto-sync: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}"
subprocess.run(
    ["git", "commit", "-m", commit_msg, "--author", "AGENTX Auto-Sync <auto@agentx.trading>"],
    capture_output=True, timeout=30
)

# Push
push = subprocess.run(
    ["git", "push", "origin", "main"],
    capture_output=True, text=True, timeout=120
)

with open(LOG_FILE, "a") as f:
    f.write(f"Push result: {push.returncode}\n")
    if push.stderr:
        f.write(push.stderr + "\n")

print(f"Auto-sync: {commit_msg}" if push.returncode == 0 else f"Push failed: {push.stderr}")
