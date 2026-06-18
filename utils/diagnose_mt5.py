"""
Read recent MT5 terminal logs for connection errors (no password needed).
Run: python diagnose_mt5.py
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

TERMINAL_DATA = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"


def latest_log_lines(max_lines: int = 30) -> list[str]:
    logs: list[tuple[float, Path]] = []
    if not TERMINAL_DATA.is_dir():
        return []
    for root in TERMINAL_DATA.iterdir():
        log_dir = root / "logs"
        if not log_dir.is_dir():
            continue
        for log_file in log_dir.glob("*.log"):
            logs.append((log_file.stat().st_mtime, log_file))
    if not logs:
        return []
    logs.sort(reverse=True)
    text = logs[0][1].read_text(encoding="utf-16-le", errors="ignore")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-max_lines:]


def main() -> None:
    print("=== MT5 log check (last lines) ===\n")
    lines = latest_log_lines()
    if not lines:
        print("No MT5 logs found.")
        return

    for ln in lines:
        print(ln)

    joined = "\n".join(lines)
    print()
    if "Invalid account" in joined:
        print(
            "*** CAUSE: Invalid account ***\n"
            "Your login/password is wrong, or the demo account expired.\n"
            "Fix:\n"
            "  1. In MT5: File -> Open an Account -> MetaQuotes-Demo -> open NEW demo\n"
            "  2. Log in with the NEW login + password shown by MT5\n"
            "  3. Update mt5_config.json with the new login, password, server\n"
            "  4. Run .\\test_mt5.bat again\n"
        )
    elif "authorization" in joined.lower() and "failed" in joined.lower():
        print("*** Login failed in MT5 — fix account in mt5_config.json ***")


if __name__ == "__main__":
    main()
