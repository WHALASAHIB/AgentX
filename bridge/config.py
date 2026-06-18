from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet
from pydantic import BaseModel, SecretStr, Field

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "accounts"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Key management ────────────────────────────────────────────────────────────

_KEY_ENV = "AGENTX_BRIDGE_KEY"
_KEY_FILE = Path(__file__).resolve().parent.parent / ".bridge_key"


def _get_or_create_key() -> bytes:
    env_key = os.environ.get(_KEY_ENV)
    if env_key:
        return env_key.encode()
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    logger.info("Generated new bridge encryption key at %s", _KEY_FILE)
    return key


_fernet = Fernet(_get_or_create_key())


def encrypt_password(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


# ── Account config ────────────────────────────────────────────────────────────

class AccountConfig(BaseModel):
    id: str
    name: str
    login: int
    password_encrypted: str = ""
    password: str = ""
    server: str
    terminal_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    symbols: list[str] = Field(default_factory=lambda: ["XAUUSD", "EURUSD"])
    enabled: bool = True

    def get_password(self) -> str:
        if self.password:
            return self.password
        if self.password_encrypted:
            return decrypt_password(self.password_encrypted)
        return ""

    def to_mt5_config(self) -> dict[str, Any]:
        return {
            "login": self.login,
            "password": self.get_password(),
            "server": self.server,
            "terminal_path": self.terminal_path,
        }


# ── Config loader ─────────────────────────────────────────────────────────────

def load_accounts() -> list[AccountConfig]:
    accounts: list[AccountConfig] = []

    legacy_path = Path(__file__).resolve().parent.parent / "mt5_config.json"
    if legacy_path.exists():
        try:
            with open(legacy_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("login"):
                accounts.append(AccountConfig(
                    id="default",
                    name=data.get("name", "Default Account"),
                    login=int(data["login"]),
                    password=str(data.get("password", "")),
                    server=str(data.get("server", "")),
                    terminal_path=data.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
                    symbols=data.get("symbols", ["XAUUSD", "EURUSD"]),
                ))
                logger.info("Loaded legacy account from mt5_config.json: login=%s", data["login"])
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning("Failed to load mt5_config.json: %s", e)

    if CONFIG_DIR.exists():
        for fpath in sorted(CONFIG_DIR.glob("*.json")):
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                acct = AccountConfig(**data)
                if acct.enabled:
                    accounts.append(acct)
                    logger.info("Loaded account from %s: id=%s login=%s", fpath.name, acct.id, acct.login)
            except Exception as e:
                logger.warning("Failed to load account config %s: %s", fpath.name, e)

    if not accounts:
        logger.warning("No MT5 account configurations found. Create mt5_config.json or config/accounts/*.json")

    return accounts


def save_account(acct: AccountConfig) -> None:
    data = acct.model_dump(exclude={"password"})
    if acct.password and not acct.password_encrypted:
        data["password_encrypted"] = encrypt_password(acct.password)
    data["password_encrypted"] = data.get("password_encrypted") or ""
    fpath = CONFIG_DIR / f"{acct.id}.json"
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Saved account config: %s", fpath)


def remove_account(account_id: str) -> bool:
    fpath = CONFIG_DIR / f"{account_id}.json"
    if fpath.exists():
        fpath.unlink()
        logger.info("Removed account config: %s", fpath)
        return True
    return False
