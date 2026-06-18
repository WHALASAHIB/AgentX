from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.cache import get_cache
from bridge.config import AccountConfig

logger = logging.getLogger(__name__)

REFRESH_INTERVAL = 3.0
WATCHDOG_INTERVAL = 10.0
BACKOFF_BASE = 1.0
BACKOFF_MAX = 60.0
HISTORY_DAYS_DEFAULT = 30

# Global lock serializing ALL MT5 API access.
# MT5's Python API is process-global — only one initialize() at a time.
_mt5_lock = threading.Lock()


class MT5Connection:
    """
    State + config container for one MT5 account.
    Does NOT call mt5.* directly — the MT5Manager does that serially.
    """

    def __init__(self, config: AccountConfig):
        self.config = config
        self.lock = threading.Lock()
        self.connected = False
        self.last_error: Optional[str] = None
        self.last_data_time: Optional[float] = None
        self._cache = get_cache()
        self._ws_callbacks: list = []

    def __repr__(self) -> str:
        return f"MT5Connection(id={self.config.id}, login={self.config.login})"

    # ── Data access (thread-safe, returns from cache) ─────────────────────────

    def get_account_info(self) -> dict[str, Any]:
        cached = self._cache.get_with_meta(self.config.id, "account_info")
        if cached["data"] is not None:
            with self.lock:
                cached["data"]["stale"] = not self.connected
                cached["data"]["connected"] = self.connected
            if cached["last_updated"]:
                cached["data"]["last_updated"] = cached["last_updated"].isoformat()
        return cached

    def get_positions(self) -> dict[str, Any]:
        cached = self._cache.get_with_meta(self.config.id, "positions")
        if cached["data"] is not None:
            with self.lock:
                stale = not self.connected
            for pos in cached["data"]:
                pos["stale"] = stale
        return cached

    def get_closed_trades(self) -> dict[str, Any]:
        return self._cache.get_with_meta(self.config.id, "closed_trades")

    def get_equity_curve(self) -> dict[str, Any]:
        return self._cache.get_with_meta(self.config.id, "equity_curve")

    def get_stats(self) -> dict[str, Any]:
        return self._cache.get_with_meta(self.config.id, "stats")

    def get_tick(self, symbol: str) -> Optional[dict[str, Any]]:
        return self._cache.get(self.config.id, f"tick_{symbol}")

    # ── WS callbacks ──────────────────────────────────────────────────────────

    def register_ws_callback(self, callback) -> None:
        with self.lock:
            self._ws_callbacks.append(callback)

    def unregister_ws_callback(self, callback) -> None:
        with self.lock:
            if callback in self._ws_callbacks:
                self._ws_callbacks.remove(callback)

    def notify_ws_callbacks(self, message: dict) -> None:
        with self.lock:
            callbacks = list(self._ws_callbacks)
        for cb in callbacks:
            try:
                cb(self.config.id, message)
            except Exception as e:
                logger.warning("WS callback error: %s", e)


class MT5Manager:
    """
    Singleton coordinator for all MT5 account connections.
    Serializes all MT5 API calls through a global lock because
    MetaTrader5's Python API is process-global — only one account
    can be initialized at a time.

    The manager runs a single coordinator thread that rotates through
    accounts: connect → fetch → disconnect → next account.
    """

    def __init__(self):
        self._connections: dict[str, MT5Connection] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._coordinator_thread: Optional[threading.Thread] = None
        self._started = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start_all(self, accounts: list[AccountConfig]) -> None:
        with self._lock:
            if self._started:
                return
            for acct in accounts:
                if acct.id not in self._connections:
                    self._connections[acct.id] = MT5Connection(acct)
            self._stop_event.clear()
            self._coordinator_thread = threading.Thread(
                target=self._coordinator_loop, daemon=True, name="mt5-coordinator"
            )
            self._coordinator_thread.start()
            self._started = True
            logger.info("MT5Manager started with %d account(s): %s",
                        len(self._connections),
                        [c.config.id for c in self._connections.values()])

    def stop_all(self) -> None:
        self._stop_event.set()
        if self._coordinator_thread:
            self._coordinator_thread.join(timeout=5)
        with self._lock:
            with _mt5_lock:
                try:
                    mt5.shutdown()
                except Exception:
                    pass
            for conn in self._connections.values():
                conn.connected = False
            self._connections.clear()
            self._started = False
            logger.info("MT5Manager stopped")

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_connection(self, account_id: str) -> Optional[MT5Connection]:
        with self._lock:
            return self._connections.get(account_id)

    def get_all_connections(self) -> list[MT5Connection]:
        with self._lock:
            return list(self._connections.values())

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "id": conn.config.id,
                    "name": conn.config.name,
                    "login": conn.config.login,
                    "server": conn.config.server,
                    "connected": conn.last_data_time is not None and (time.time() - conn.last_data_time) < 15,
                    "last_error": conn.last_error,
                    "stale": conn.last_data_time is not None and (time.time() - conn.last_data_time) > 10,
                }
                for conn in self._connections.values()
            ]

    @property
    def any_connected(self) -> bool:
        with self._lock:
            now = time.time()
            return any(c.last_data_time is not None and (now - c.last_data_time) < 15 for c in self._connections.values())

    @property
    def all_disconnected(self) -> bool:
        with self._lock:
            return all(not c.connected for c in self._connections.values())

    # ── Coordinator Loop ──────────────────────────────────────────────────────

    def _coordinator_loop(self) -> None:
        """
        Single thread that rotates through all accounts.
        For each account: connect → fetch all → cache → disconnect.
        This avoids MT5's global-state conflict between accounts.
        """
        while not self._stop_event.is_set():
            connections = self.get_all_connections()
            for conn in connections:
                if self._stop_event.is_set():
                    return
                try:
                    self._refresh_one(conn)
                except Exception as e:
                    logger.error("Coordinator: error refreshing %s: %s", conn.config.id, e)
                    with conn.lock:
                        conn.connected = False
                        conn.last_error = str(e)
                self._stop_event.wait(REFRESH_INTERVAL)

    def _refresh_one(self, conn: MT5Connection) -> None:
        """Connect to one account, fetch all data, cache it, then disconnect."""
        config = conn.config

        with _mt5_lock:
            if not self._try_connect(conn):
                conn.notify_ws_callbacks({
                    "type": "connection_status",
                    "data": {"connected": False, "error": conn.last_error},
                })
                return

            try:
                self._fetch_all(conn)
                with conn.lock:
                    conn.connected = True
                    conn.last_data_time = time.time()
            except Exception as e:
                logger.error("Fetch error for %s: %s\n%s", config.id, e, traceback.format_exc())
                with conn.lock:
                    conn.connected = False
                    conn.last_error = str(e)
            finally:
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                with conn.lock:
                    conn.connected = False

        conn.notify_ws_callbacks({
            "type": "data_refreshed",
            "data": {"account_id": config.id, "timestamp": datetime.now(timezone.utc).isoformat()},
        })

    # ── Connection (MUST be called inside _mt5_lock) ──────────────────────────

    def _try_connect(self, conn: MT5Connection) -> bool:
        config = conn.config
        cfg = config.to_mt5_config()
        try:
            mt5.shutdown()
            init_kwargs = {"path": cfg.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe")}
            if cfg.get("login") and cfg.get("password") and cfg.get("server"):
                init_kwargs["login"] = int(cfg["login"])
                init_kwargs["password"] = str(cfg["password"])
                init_kwargs["server"] = str(cfg["server"])

            if not mt5.initialize(**init_kwargs):
                err = mt5.last_error()
                logger.warning("MT5 init failed for %s: %s", config.id, err)
                with conn.lock:
                    conn.last_error = str(err)
                return False

            acc = mt5.account_info()
            if acc is None:
                err = mt5.last_error()
                logger.warning("No account_info for %s: %s", config.id, err)
                with conn.lock:
                    conn.last_error = str(err)
                mt5.shutdown()
                return False

            with conn.lock:
                conn.last_error = None
            logger.info("Connected | account=%s login=%s balance=%s", config.id, acc.login, acc.balance)
            return True

        except Exception as e:
            logger.error("Connection error for %s: %s", config.id, e)
            with conn.lock:
                conn.last_error = str(e)
            return False

    # ── Data Fetching (MUST be called inside _mt5_lock) ───────────────────────

    def _fetch_all(self, conn: MT5Connection) -> None:
        self._fetch_account_info(conn)
        self._fetch_positions(conn)
        self._fetch_closed_trades(conn)
        self._fetch_equity_curve(conn)
        self._fetch_stats(conn)
        self._fetch_ticks(conn)

    def _fetch_account_info(self, conn: MT5Connection) -> None:
        acc = mt5.account_info()
        if acc is None:
            return
        data = {
            "login": acc.login,
            "name": acc.name,
            "server": acc.server,
            "broker": acc.company,
            "currency": acc.currency,
            "leverage": acc.leverage,
            "balance": round(acc.balance, 2),
            "equity": round(acc.equity, 2),
            "margin": round(acc.margin, 2),
            "free_margin": round(acc.margin_free, 2),
            "margin_level": round(acc.margin_level, 2) if acc.margin_level else 0.0,
            "profit": round(acc.profit, 2),
            "trade_allowed": acc.trade_allowed,
            "connected": True,
        }
        conn._cache.update(conn.config.id, "account_info", data)

    def _fetch_positions(self, conn: MT5Connection) -> None:
        positions = mt5.positions_get()
        rows = []
        if positions:
            for p in positions:
                tick = mt5.symbol_info_tick(p.symbol)
                current = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask if tick else p.price_open
                direction = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
                open_dt = datetime.fromtimestamp(p.time, tz=timezone.utc)
                duration = datetime.now(timezone.utc) - open_dt
                hours, rem = divmod(int(duration.total_seconds()), 3600)
                mins = rem // 60
                rows.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": direction,
                    "volume": p.volume,
                    "open_price": round(p.price_open, 5),
                    "current_price": round(current, 5),
                    "sl": round(p.sl, 5),
                    "tp": round(p.tp, 5),
                    "swap": round(p.swap, 2),
                    "profit": round(p.profit, 2),
                    "open_time": open_dt.strftime("%Y-%m-%d %H:%M"),
                    "duration": f"{hours}h {mins}m",
                    "magic": p.magic,
                    "comment": p.comment or "",
                })
        conn._cache.update(conn.config.id, "positions", rows)

    def _fetch_closed_trades(self, conn: MT5Connection) -> None:
        date_from = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS_DEFAULT)
        date_to = datetime.now(timezone.utc) + timedelta(days=1)
        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return

        by_pos: dict[int, list] = {}
        for d in deals:
            by_pos.setdefault(d.position_id, []).append(d)

        rows = []
        for pos_id, deal_list in by_pos.items():
            entries = [d for d in deal_list if d.entry == mt5.DEAL_ENTRY_IN]
            exits = [d for d in deal_list if d.entry == mt5.DEAL_ENTRY_OUT]
            if not entries:
                continue
            entry_deal = entries[0]
            exit_deal = exits[0] if exits else None

            direction = "BUY" if entry_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
            open_dt = datetime.fromtimestamp(entry_deal.time, tz=timezone.utc)
            close_dt = datetime.fromtimestamp(exit_deal.time, tz=timezone.utc) if exit_deal else None

            total_profit = sum(d.profit for d in deal_list)
            total_swap = sum(d.swap for d in deal_list)
            total_comm = sum(d.commission for d in deal_list)
            net_profit = round(total_profit + total_swap + total_comm, 2)

            duration_str = ""
            if close_dt:
                secs = int((close_dt - open_dt).total_seconds())
                h, r = divmod(secs, 3600)
                duration_str = f"{h}h {r//60}m"

            rows.append({
                "position_id": pos_id,
                "symbol": entry_deal.symbol,
                "type": direction,
                "volume": round(entry_deal.volume, 2),
                "entry_price": round(entry_deal.price, 5),
                "exit_price": round(exit_deal.price, 5) if exit_deal else None,
                "open_time": open_dt.strftime("%Y-%m-%d %H:%M"),
                "close_time": close_dt.strftime("%Y-%m-%d %H:%M") if close_dt else "OPEN",
                "profit": round(total_profit, 2),
                "swap": round(total_swap, 2),
                "commission": round(total_comm, 2),
                "net_profit": net_profit,
                "duration": duration_str,
                "magic": entry_deal.magic,
                "comment": entry_deal.comment or "",
            })

        rows.sort(key=lambda x: x["open_time"], reverse=True)
        conn._cache.update(conn.config.id, "closed_trades", rows)

    def _fetch_equity_curve(self, conn: MT5Connection) -> None:
        trades_data = conn._cache.get(conn.config.id, "closed_trades")
        acc = mt5.account_info()
        if acc is None:
            return
        if not trades_data:
            conn._cache.update(conn.config.id, "equity_curve", [{
                "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "equity": acc.balance,
                "is_trade": False,
                "type": "",
            }])
            return

        sorted_trades = sorted(trades_data, key=lambda x: x["open_time"])
        running_balance = acc.balance - sum(t["net_profit"] for t in sorted_trades)
        curve = []
        for t in sorted_trades:
            running_balance += t["net_profit"]
            curve.append({
                "time": t["close_time"] if t["close_time"] != "OPEN" else t["open_time"],
                "equity": round(running_balance, 2),
                "is_trade": True,
                "type": t["type"] + "_CLOSE",
                "profit": t["net_profit"],
            })
        conn._cache.update(conn.config.id, "equity_curve", curve)

    def _fetch_stats(self, conn: MT5Connection) -> None:
        aid = conn.config.id
        trades_data = conn._cache.get(aid, "closed_trades", [])
        if not trades_data:
            conn._cache.update(aid, "stats", {
                "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "gross_profit": 0.0, "gross_loss": 0.0, "net_profit": 0.0,
                "profit_factor": 0.0, "max_drawdown": 0.0, "best_trade": 0.0,
                "worst_trade": 0.0, "avg_profit": 0.0, "daily_pnl": 0.0,
            })
            return

        closed = [t for t in trades_data if t["close_time"] != "OPEN"]
        wins = [t for t in closed if t["net_profit"] > 0]
        losses = [t for t in closed if t["net_profit"] <= 0]

        gross_profit = sum(t["net_profit"] for t in wins)
        gross_loss = abs(sum(t["net_profit"] for t in losses))
        net_profit = sum(t["net_profit"] for t in closed)
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = round(sum(t["net_profit"] for t in closed if t["close_time"].startswith(today_str)), 2)

        curve_data = conn._cache.get(aid, "equity_curve", [])
        max_dd = 0.0
        if curve_data:
            peak = curve_data[0]["equity"]
            for point in curve_data:
                if point["equity"] > peak:
                    peak = point["equity"]
                dd = peak - point["equity"]
                if dd > max_dd:
                    max_dd = dd

        conn._cache.update(aid, "stats", {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "net_profit": round(net_profit, 2),
            "profit_factor": profit_factor,
            "max_drawdown": round(max_dd, 2),
            "best_trade": round(max((t["net_profit"] for t in closed), default=0.0), 2),
            "worst_trade": round(min((t["net_profit"] for t in closed), default=0.0), 2),
            "avg_profit": round(net_profit / len(closed), 2) if closed else 0.0,
            "daily_pnl": daily_pnl,
        })

    def _fetch_ticks(self, conn: MT5Connection) -> None:
        for symbol in conn.config.symbols:
            tick = mt5.symbol_info_tick(symbol)
            info = mt5.symbol_info(symbol)
            if tick is None:
                continue
            data = {
                "bid": round(tick.bid, 5),
                "ask": round(tick.ask, 5),
                "spread": info.spread if info else 0,
                "time": datetime.fromtimestamp(tick.time, tz=timezone.utc).strftime("%H:%M:%S"),
            }
            conn._cache.update(conn.config.id, f"tick_{symbol}", data)


# Global manager instance
_manager = MT5Manager()


def get_manager() -> MT5Manager:
    return _manager
