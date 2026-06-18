"""
app_state.py — Real Dashboard State Manager
No mock data. All metrics pulled directly from MetaTrader 5.
Manages bot subprocess lifecycle (start/stop gold_bot.py / streaming_bot.py).
"""
from __future__ import annotations
import os
import sys
import json
import time
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

import mt5_data
from log_streamer import get_log_lines

CONFIG_FILE = Path(__file__).resolve().parent / "dashboard_config.json"
BOTS_DIR    = Path(__file__).resolve().parent / "bots"
LOGS_DIR    = Path(__file__).resolve().parent / "logs"

BOT_SCRIPTS = {
    "Gold Bot (M5 Breakout)":      "bots/gold_bot.py",
    "Streaming Bot (M1 Breakout)": "bots/streaming_bot.py",
}


class DashboardState:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    # ── Init ─────────────────────────────────────────────────────────────────

    def _init(self):
        self.lock = threading.Lock()
        self.LOGS_DIR = LOGS_DIR
        LOGS_DIR.mkdir(exist_ok=True)

        # Live MT5 cache
        self.account_info:   dict[str, Any] = {}
        self.open_positions: list[dict]     = []
        self.closed_trades:  list[dict]     = []
        self.equity_curve:   list[dict]     = []
        self.stats:          dict[str, Any] = {}
        self.daily_pnl:      list[dict]     = []
        self.pnl_dist:       list[float]    = []
        self.drawdown_series:list[dict]     = []
        self.symbol_perf:    list[dict]     = []
        self.diagnostic:     dict[str, Any] = {}
        self.mt5_connected:  bool           = False
        self.last_refresh:   float          = 0.0

        # Bot subprocess state
        self.active_bot_name: str                    = "Gold Bot (M5 Breakout)"
        self.bot_process:     Optional[subprocess.Popen] = None
        self.bot_running:     bool                   = False

        # Dashboard config
        self.history_days: int = 30
        self.load_config()

        # Start background refresh loop
        self._stop_refresh = threading.Event()
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()

    # ── Background Refresh ────────────────────────────────────────────────────

    def _refresh_loop(self):
        while not self._stop_refresh.is_set():
            try:
                self._fetch_all()
            except Exception as e:
                print(f"[DashboardState] Refresh error: {e}", flush=True)
            self._stop_refresh.wait(timeout=3)  # refresh every 3 seconds

    def _fetch_all(self):
        # ALWAYS fetch diagnostic first (needed both online and offline)
        diag = mt5_data.get_diagnostic_info()
        with self.lock:
            self.diagnostic = diag

        connected = mt5_data.is_connected() or mt5_data.connect()
        with self.lock:
            self.mt5_connected = connected

        if not connected:
            return

        # Fetch all real data
        account    = mt5_data.get_account_info()
        positions  = mt5_data.get_open_positions()
        trades     = mt5_data.get_closed_trades(days=self.history_days)
        curve      = mt5_data.get_equity_curve(days=self.history_days)
        stats      = mt5_data.calculate_stats(days=self.history_days)
        daily_pnl  = mt5_data.get_daily_pnl_series(days=self.history_days)
        pnl_dist   = mt5_data.get_pnl_distribution(days=self.history_days)
        dd_series  = mt5_data.get_drawdown_series(curve)
        sym_perf   = mt5_data.get_symbol_performance(days=self.history_days)

        with self.lock:
            self.account_info    = account
            self.open_positions  = positions
            self.closed_trades   = trades
            self.equity_curve    = curve
            self.stats           = stats
            self.daily_pnl       = daily_pnl
            self.pnl_dist        = pnl_dist
            self.drawdown_series = dd_series
            self.symbol_perf     = sym_perf
            self.last_refresh    = time.time()

        # Sync bot running state with process
        self._sync_bot_state()

    def _sync_bot_state(self):
        with self.lock:
            if self.bot_process is not None:
                retcode = self.bot_process.poll()
                if retcode is not None:
                    # Process has exited
                    self.bot_running = False
                    self.bot_process = None

    # ── Snapshot for UI (avoids lock in render) ───────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "connected":       self.mt5_connected,
                "account":         dict(self.account_info),
                "positions":       list(self.open_positions),
                "trades":          list(self.closed_trades),
                "curve":           list(self.equity_curve),
                "stats":           dict(self.stats),
                "daily_pnl":       list(self.daily_pnl),
                "pnl_dist":        list(self.pnl_dist),
                "drawdown_series":  list(self.drawdown_series),
                "symbol_perf":     list(self.symbol_perf),
                "diagnostic":      dict(self.diagnostic),
                "bot_running":     self.bot_running,
                "active_bot":      self.active_bot_name,
                "last_refresh":    self.last_refresh,
                "history_days":    self.history_days,
            }

    # ── Bot Process Control ───────────────────────────────────────────────────

    def start_bot(self, bot_name: str | None = None) -> str:
        with self.lock:
            if self.bot_running and self.bot_process:
                return "Bot is already running."

            name   = bot_name or self.active_bot_name
            script = BOT_SCRIPTS.get(name)
            if not script:
                return f"Unknown bot: {name}"

            script_path = Path(__file__).resolve().parent / script
            if not script_path.exists():
                return f"Script not found: {script_path}"

            try:
                self.bot_process = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    cwd=str(Path(__file__).resolve().parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.bot_running    = True
                self.active_bot_name = name
                return f"✅ {name} started (PID {self.bot_process.pid})"
            except Exception as e:
                return f"❌ Failed to start bot: {e}"

    def stop_bot(self) -> str:
        with self.lock:
            if not self.bot_running or self.bot_process is None:
                return "No bot is running."
            try:
                self.bot_process.terminate()
                try:
                    self.bot_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.bot_process.kill()
                pid = self.bot_process.pid
                self.bot_process = None
                self.bot_running = False
                return f"⛔ Bot stopped (was PID {pid})"
            except Exception as e:
                return f"❌ Failed to stop bot: {e}"

    def panic_close(self) -> str:
        import MetaTrader5 as mt5
        msg = self.stop_bot()
        msgs = [msg, "🚨 PANIC CLOSE — Flattening all positions..."]

        positions = mt5.positions_get()
        if not positions:
            msgs.append("No open positions found.")
            return "\n".join(msgs)

        for pos in positions:
            tick = mt5.symbol_info_tick(pos.symbol)
            info = mt5.symbol_info(pos.symbol)
            if tick is None or info is None:
                continue

            filling = mt5.ORDER_FILLING_IOC
            if info.filling_mode & 2:
                filling = mt5.ORDER_FILLING_IOC
            elif info.filling_mode & 1:
                filling = mt5.ORDER_FILLING_FOK

            close_type  = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

            req = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       pos.symbol,
                "volume":       pos.volume,
                "type":         close_type,
                "position":     pos.ticket,
                "price":        close_price,
                "deviation":    20,
                "magic":        pos.magic,
                "comment":      "PANIC_CLOSE",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }
            result = mt5.order_send(req)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                msgs.append(f"✅ Closed ticket {pos.ticket} ({pos.symbol})")
            else:
                code = result.retcode if result else "None"
                msgs.append(f"❌ Failed ticket {pos.ticket}: retcode={code}")

        return "\n".join(msgs)

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self):
        if CONFIG_FILE.is_file():
            try:
                data = json.loads(CONFIG_FILE.read_text())
                self.history_days    = data.get("history_days", 30)
                self.active_bot_name = data.get("active_bot", "Gold Bot (M5 Breakout)")
            except Exception:
                pass

    def save_config(self):
        try:
            CONFIG_FILE.write_text(json.dumps({
                "history_days": self.history_days,
                "active_bot":   self.active_bot_name,
            }, indent=2))
        except Exception as e:
            print(f"Config save error: {e}")

    def update_config(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, v)
        self.save_config()

    # ── Log Lines ─────────────────────────────────────────────────────────────

    def get_log_lines(self) -> list[str]:
        return get_log_lines(self.active_bot_name)

    # ── Bot list ─────────────────────────────────────────────────────────────

    @staticmethod
    def available_bots() -> list[str]:
        return list(BOT_SCRIPTS.keys())
