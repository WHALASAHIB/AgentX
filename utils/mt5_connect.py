"""
Shared MetaTrader 5 connection (matches notebook pattern: initialize + login).

Copy mt5_config.example.json to mt5_config.json and fill in YOUR account details.
Never commit mt5_config.json (contains password).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).resolve().parent.parent / "mt5_config.json"
DEFAULT_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"


def load_config() -> Optional[dict[str, Any]]:
    if not CONFIG_FILE.is_file():
        return None
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read %s: %s", CONFIG_FILE, exc)
        return None


def read_experts_api_setting() -> Optional[str]:
    """Experts.Api in common.ini (meaning varies by MT5 build)."""
    appdata = os.environ.get("APPDATA", "")
    terminal_root = os.path.join(appdata, "MetaQuotes", "Terminal")
    if not os.path.isdir(terminal_root):
        return None
    for name in os.listdir(terminal_root):
        ini_path = os.path.join(terminal_root, name, "config", "common.ini")
        if not os.path.isfile(ini_path):
            continue
        try:
            with open(ini_path, encoding="utf-16-le", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        if "[Experts]" not in text:
            continue
        section = text.split("[Experts]", 1)[1].split("[", 1)[0]
        for line in section.splitlines():
            if line.strip().startswith("Api="):
                return line.strip().split("=", 1)[1].strip()
    return None


def connect_mt5(config: Optional[dict[str, Any]] = None) -> bool:
    """
    Connect to MT5 (reference notebook pattern).

    Credentials are passed into initialize() when available so login works
    even if the terminal GUI session alone returns authorization errors.
    """
    cfg = config or load_config()
    terminal_path = DEFAULT_TERMINAL
    if cfg:
        terminal_path = cfg.get("terminal_path") or terminal_path

    mt5.shutdown()

    init_kwargs: dict[str, Any] = {"path": terminal_path}
    if cfg and cfg.get("login") and cfg.get("password") and cfg.get("server"):
        init_kwargs["login"] = int(cfg["login"])
        init_kwargs["password"] = str(cfg["password"])
        init_kwargs["server"] = str(cfg["server"])

    if not mt5.initialize(**init_kwargs):
        err = mt5.last_error()
        logger.error("mt5.initialize failed: %s", err)
        if err == (-6, "Terminal: Authorization failed"):
            logger.error(
                "Often means wrong login/password or expired demo — see MT5 Journal "
                "or run: python diagnose_mt5.py"
            )
        return False

    if cfg and cfg.get("login"):
        logger.info(
            "Logged in | login=%s server=%s",
            cfg["login"],
            cfg.get("server", ""),
        )

    account = mt5.account_info()
    if account is None:
        logger.error("No account_info after connect: %s", mt5.last_error())
        mt5.shutdown()
        return False

    terminal = mt5.terminal_info()
    logger.info(
        "MT5 connected | account=%s server=%s balance=%s trade_allowed=%s",
        account.login,
        account.server,
        account.balance,
        account.trade_allowed,
    )
    if terminal:
        logger.info("Terminal build=%s connected=%s", terminal.build, terminal.connected)
    return True

