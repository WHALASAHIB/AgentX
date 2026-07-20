from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PostgresPool:
    """
    AGENTX database pool.
    - PostgreSQL when available (psycopg2 + configured env vars)
    - Falls back to persistent JSON file store
    """

    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "5432"))
        self.dbname = os.getenv("DB_NAME", "agentx")
        self.user = os.getenv("DB_USER", "agentx")
        self.password = os.getenv("DB_PASSWORD", "agentx")
        self._pool: Any = None
        self._json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agentx_store.json")
        self._mock_store: dict[str, list] = {
            "accounts": [],
            "trades": [],
            "positions": [],
            "bots": [],
            "bot_logs": [],
            "agent_logs": [],
            "system_events": [],
            "active_account_id": None,
        }
        self._mock_seq: dict[str, int] = {}
        self._connected = False
        self._init()

    def _init(self):
        try:
            import psycopg2
            from psycopg2 import pool
            self._pool = pool.ThreadedConnectionPool(
                1, 10,
                host=self.host, port=self.port,
                dbname=self.dbname, user=self.user, password=self.password,
            )
            self._connected = True
            logger.info("PostgreSQL connected: %s:%s/%s", self.host, self.port, self.dbname)
        except ImportError:
            logger.info("psycopg2 not installed — using persistent JSON store")
            self._load_json_store()
        except Exception as e:
            logger.warning("PostgreSQL unavailable (%s) — using persistent JSON store", e)
            self._load_json_store()

    def _load_json_store(self):
        if os.path.exists(self._json_path):
            try:
                with open(self._json_path, "r") as f:
                    data = json.load(f)
                    self._mock_store.update(data)
                logger.info("Loaded persistent store: %s", self._json_path)
            except Exception as e:
                logger.warning("Failed to load store: %s", e)
        self._save_json_store()
        self._connected = True

    def _save_json_store(self):
        try:
            with open(self._json_path, "w") as f:
                json.dump(self._mock_store, f, indent=2, default=str)
        except Exception as e:
            logger.warning("Failed to save store: %s", e)

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _next_id(self, table: str) -> int:
        seq = self._mock_seq.get(table, 0) + 1
        self._mock_seq[table] = seq
        return seq

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── PostgreSQL helpers (unused in JSON mode) ─────────────────────────────

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        if not self._pool:
            return []
        conn = None
        try:
            conn = self._pool.getconn()
            with conn.cursor(cursor_factory=__import__("psycopg2").extras.RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error("DB query error: %s", e)
            return []
        finally:
            if conn:
                self._pool.putconn(conn)

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        rows = self.fetch_all(query, params)
        return rows[0] if rows else None

    def execute(self, query: str, params: tuple = ()) -> Optional[int]:
        if not self._pool:
            return None
        conn = None
        try:
            conn = self._pool.getconn()
            with conn.cursor() as cur:
                cur.execute(query, params)
                conn.commit()
                return cur.rowcount
        except Exception as e:
            logger.error("DB execute error: %s", e)
            return None
        finally:
            if conn:
                self._pool.putconn(conn)

    # ── Account operations ────────────────────────────────────────────────────

    def save_account(self, acct: dict) -> dict:
        if self._pool:
            self.execute("""
                INSERT INTO accounts (id, name, login, password_encrypted, server, terminal_path, symbols, enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, login = EXCLUDED.login,
                    password_encrypted = EXCLUDED.password_encrypted, server = EXCLUDED.server,
                    terminal_path = EXCLUDED.terminal_path, symbols = EXCLUDED.symbols,
                    enabled = EXCLUDED.enabled, updated_at = NOW()
            """, (
                acct["id"], acct["name"], acct["login"],
                acct.get("password_encrypted", ""), acct["server"],
                acct.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
                acct.get("symbols", ["XAUUSD", "EURUSD"]),
                acct.get("enabled", True),
            ))
        else:
            existing = [a for a in self._mock_store["accounts"] if a["id"] == acct["id"]]
            if existing:
                existing[0].update(acct)
            else:
                self._mock_store["accounts"].append(dict(acct))
            self._save_json_store()
        return acct

    def get_accounts(self) -> list[dict]:
        if self._pool:
            return self.fetch_all("SELECT * FROM accounts ORDER BY name")
        return list(self._mock_store["accounts"])

    def get_account(self, account_id: str) -> Optional[dict]:
        if self._pool:
            return self.fetch_one("SELECT * FROM accounts WHERE id = %s", (account_id,))
        for a in self._mock_store["accounts"]:
            if a["id"] == account_id:
                return dict(a)
        return None

    def delete_account(self, account_id: str) -> bool:
        if self._pool:
            return self.execute("DELETE FROM accounts WHERE id = %s", (account_id,)) > 0
        before = len(self._mock_store["accounts"])
        self._mock_store["accounts"] = [a for a in self._mock_store["accounts"] if a["id"] != account_id]
        self._save_json_store()
        return len(self._mock_store["accounts"]) < before

    # ── Trade operations ──────────────────────────────────────────────────────

    def upsert_trades(self, account_id: str, trades: list[dict]) -> int:
        count = 0
        for t in trades:
            if self._pool:
                self.execute("""
                    INSERT INTO trades (account_id, position_id, symbol, type, volume, entry_price,
                        exit_price, open_time, close_time, profit, swap, commission, net_profit,
                        duration, magic, comment)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (account_id, position_id) DO NOTHING
                """, (
                    account_id, t["position_id"], t["symbol"], t["type"], t["volume"],
                    t["entry_price"], t.get("exit_price"), t["open_time"], t.get("close_time"),
                    t["profit"], t["swap"], t["commission"], t["net_profit"],
                    t.get("duration", ""), t.get("magic", 0), t.get("comment", ""),
                ))
            else:
                t_copy = dict(t)
                t_copy["id"] = self._next_id("trades")
                t_copy["account_id"] = account_id
                self._mock_store["trades"].append(t_copy)
            count += 1
        if not self._pool and count > 0:
            self._save_json_store()
        return count

    def get_trades(self, account_id: Optional[str] = None, limit: int = 100) -> list[dict]:
        if self._pool:
            if account_id:
                return self.fetch_all(
                    "SELECT * FROM trades WHERE account_id = %s ORDER BY open_time DESC LIMIT %s",
                    (account_id, limit),
                )
            return self.fetch_all("SELECT * FROM trades ORDER BY open_time DESC LIMIT %s", (limit,))
        trades = self._mock_store["trades"]
        if account_id:
            trades = [t for t in trades if t.get("account_id") == account_id]
        return sorted(trades, key=lambda t: t.get("open_time", ""), reverse=True)[:limit]

    # ── Bot operations ────────────────────────────────────────────────────────

    def upsert_bot(self, bot: dict) -> dict:
        if self._pool:
            self.execute("""
                INSERT INTO bots (name, display_name, script_path, strategy, symbol, account_id,
                    status, config, pid, uptime_seconds, last_started, last_stopped)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name, status = EXCLUDED.status,
                    config = EXCLUDED.config, pid = EXCLUDED.pid,
                    uptime_seconds = EXCLUDED.uptime_seconds,
                    last_started = EXCLUDED.last_started, last_stopped = EXCLUDED.last_stopped,
                    updated_at = NOW()
            """, (
                bot["name"], bot.get("display_name", bot["name"]),
                bot.get("script_path", ""), bot.get("strategy", ""),
                bot.get("symbol", "XAUUSD"), bot.get("account_id"),
                bot.get("status", "stopped"), json.dumps(bot.get("config", {})),
                bot.get("pid"), bot.get("uptime_seconds", 0),
                bot.get("last_started"), bot.get("last_stopped"),
            ))
        else:
            existing = [b for b in self._mock_store["bots"] if b["name"] == bot["name"]]
            if existing:
                existing[0].update(bot)
            else:
                b = dict(bot)
                b["id"] = self._next_id("bots")
                self._mock_store["bots"].append(b)
            self._save_json_store()
        return bot

    def get_bots(self) -> list[dict]:
        if self._pool:
            return self.fetch_all("SELECT * FROM bots ORDER BY name")
        return list(self._mock_store["bots"])

    def get_bot(self, name: str) -> Optional[dict]:
        if self._pool:
            return self.fetch_one("SELECT * FROM bots WHERE name = %s", (name,))
        for b in self._mock_store["bots"]:
            if b["name"] == name:
                return dict(b)
        return None

    def delete_bot(self, name: str) -> bool:
        if self._pool:
            return self.execute("DELETE FROM bots WHERE name = %s", (name,)) > 0
        before = len(self._mock_store["bots"])
        self._mock_store["bots"] = [b for b in self._mock_store["bots"] if b["name"] != name]
        self._save_json_store()
        return len(self._mock_store["bots"]) < before

    # ── Bot Logs ──────────────────────────────────────────────────────────────

    def save_bot_log(self, bot_id: int, level: str, message: str):
        if self._pool:
            self.execute(
                "INSERT INTO bot_logs (bot_id, level, message) VALUES (%s, %s, %s)",
                (bot_id, level, message),
            )
        else:
            self._mock_store["bot_logs"].append({
                "id": self._next_id("bot_logs"),
                "bot_id": bot_id,
                "level": level,
                "message": message,
                "created_at": self._ts(),
            })
            self._save_json_store()

    # ── Agent Logs ────────────────────────────────────────────────────────────

    def get_agent_logs(self, limit: int = 50) -> list[dict]:
        """Return the most recent agent log entries."""
        if self._pool:
            return self.fetch_all(
                "SELECT * FROM agent_logs ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        logs = list(self._mock_store.get("agent_logs", []))
        return sorted(logs, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]

    def save_agent_log(self, agent_name: str, task: str, decision: str, outcome: str, metadata: dict = None):
        if self._pool:
            self.execute(
                "INSERT INTO agent_logs (agent_name, task, decision, outcome, metadata) VALUES (%s, %s, %s, %s, %s)",
                (agent_name, task, decision, outcome, json.dumps(metadata or {})),
            )
        else:
            self._mock_store["agent_logs"].append({
                "id": self._next_id("agent_logs"),
                "agent_name": agent_name,
                "task": task,
                "decision": decision,
                "outcome": outcome,
                "metadata": metadata or {},
                "created_at": self._ts(),
            })
            self._save_json_store()

    # ── Active Account ────────────────────────────────────────────────────────

    def set_active_account(self, account_id: str):
        self._mock_store["active_account_id"] = account_id
        self._save_json_store()

    def get_active_account(self) -> Optional[str]:
        return self._mock_store.get("active_account_id")

    # ── Account balance cache (persists last-known values across restarts) ──

    def cache_account_balance(self, account_id: str, balance: float, equity: float, profit: float):
        if "account_balances" not in self._mock_store:
            self._mock_store["account_balances"] = {}
        self._mock_store["account_balances"][account_id] = {
            "balance": balance,
            "equity": equity,
            "profit": profit,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_json_store()

    def get_cached_account_balance(self, account_id: str) -> Optional[dict]:
        return self._mock_store.get("account_balances", {}).get(account_id)

    # ── System Events ─────────────────────────────────────────────────────────

    def save_system_event(self, event_type: str, severity: str, message: str, metadata: dict = None):
        if self._pool:
            self.execute(
                "INSERT INTO system_events (event_type, severity, message, metadata) VALUES (%s, %s, %s, %s)",
                (event_type, severity, message, json.dumps(metadata or {})),
            )
        else:
            self._mock_store["system_events"].append({
                "id": self._next_id("system_events"),
                "event_type": event_type,
                "severity": severity,
                "message": message,
                "metadata": metadata or {},
                "created_at": self._ts(),
            })
            self._save_json_store()


_db = PostgresPool()


def get_db() -> PostgresPool:
    return _db
