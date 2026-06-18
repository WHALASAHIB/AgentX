"""
MT5 connection test (initialize + login like Python MT5.ipynb).

Setup:
  1. Copy mt5_config.example.json -> mt5_config.json
  2. Fill in YOUR login, password, server (from MT5 Navigator)
  3. Enable Python integration in MT5 Expert Advisors options
  4. Run: .\\test_mt5.bat
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import MetaTrader5 as mt5

from mt5_connect import CONFIG_FILE, connect_mt5, load_config, read_experts_api_setting

DEFAULT_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"


def main() -> int:
    print("=== MT5 Connection Test ===\n")
    print(f"Python: {struct.calcsize('P') * 8}-bit")
    print(f"Config file: {CONFIG_FILE}")
    print(f"Config exists: {CONFIG_FILE.is_file()}\n")

    if not CONFIG_FILE.is_file():
        print(
            "STEP 1: Create your config file\n"
            "  copy mt5_config.example.json mt5_config.json\n"
            "  Edit login, password, server (see MT5: File -> Login to Trade Account)\n"
        )

    import subprocess
    mt5_running = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
        capture_output=True,
        text=True,
    ).stdout.find("terminal64.exe") >= 0
    print(f"MT5 terminal64.exe running: {mt5_running}")
    if not mt5_running:
        print("  -> Open MetaTrader 5 and log in BEFORE running this test.\n")

    api = read_experts_api_setting()
    if api is not None:
        print(f"Experts.Api in config file: {api}")
        print(
            "  (In MT5: 'Disable algorithmic trading via external Python API' must be UNCHECKED)"
        )

    cfg = load_config()
    if cfg:
        print(f"Will login: {cfg.get('login')} @ {cfg.get('server')}")
    else:
        print("No valid config — only initialize() will be tried (often fails with -6).\n")

    print("Connecting...")
    if not connect_mt5(cfg):
        err = mt5.last_error()
        print(f"\nFAILED: {err}")
        print("\nRun: python diagnose_mt5.py")
        print("  (checks MT5 logs for 'Invalid account' — common cause of error -6)")
        mt5.shutdown()
        return 1

    account = mt5.account_info()
    terminal = mt5.terminal_info()
    print("\nConnected OK")
    if account:
        print(f"  Login:    {account.login}")
        print(f"  Server:   {account.server}")
        print(f"  Balance:  {account.balance} {account.currency}")
        print(f"  Trading:  allowed={account.trade_allowed}")
    if terminal:
        print(f"  Terminal: {terminal.name} build={terminal.build}")

    print("  (Symbol is set in each strategy .py file, not in mt5_config.json)")

    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
