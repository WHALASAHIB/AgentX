"""
mt5_data.py — Real MetaTrader 5 Data Engine
Connects to the MT5 terminal running on this machine and exposes
live account info, positions, deal history, equity curve, and stats.
"""
from __future__ import annotations
import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import MetaTrader5 as mt5
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.mt5_connect import load_config

logger = logging.getLogger(__name__)

# ── Connection ──────────────────────────────────────────────────────────────

_connected = False

def connect() -> bool:
    global _connected
    cfg = load_config()
    if _connected:
        term = mt5.terminal_info()
        if term and term.connected:
            return True
        _connected = False

    mt5.shutdown()
    init_kwargs: dict[str, Any] = {}
    if cfg:
        path = cfg.get("terminal_path", r"C:\Program Files\MetaTrader 5\terminal64.exe")
        init_kwargs["path"] = path
        if cfg.get("login") and cfg.get("password") and cfg.get("server"):
            init_kwargs["login"] = int(cfg["login"])
            init_kwargs["password"] = str(cfg["password"])
            init_kwargs["server"] = str(cfg["server"])

    if not mt5.initialize(**init_kwargs):
        logger.error("MT5 initialize failed: %s", mt5.last_error())
        _connected = False
        return False

    acc = mt5.account_info()
    if acc is None:
        logger.error("No account_info after connect: %s", mt5.last_error())
        mt5.shutdown()
        _connected = False
        return False

    _connected = True
    return True


def is_connected() -> bool:
    try:
        term = mt5.terminal_info()
        return term is not None and term.connected
    except Exception:
        return False


# ── Account ─────────────────────────────────────────────────────────────────

def get_account_info() -> dict[str, Any]:
    if not connect():
        return {"error": "MT5 not connected"}
    acc = mt5.account_info()
    if acc is None:
        return {"error": str(mt5.last_error())}
    term = mt5.terminal_info()
    return {
        "login":        acc.login,
        "name":         acc.name,
        "server":       acc.server,
        "broker":       acc.company,
        "currency":     acc.currency,
        "leverage":     acc.leverage,
        "balance":      round(acc.balance, 2),
        "equity":       round(acc.equity, 2),
        "margin":       round(acc.margin, 2),
        "free_margin":  round(acc.margin_free, 2),
        "margin_level": round(acc.margin_level, 2) if acc.margin_level else 0.0,
        "profit":       round(acc.profit, 2),
        "trade_allowed": acc.trade_allowed,
        "terminal_build": term.build if term else "N/A",
        "connected":    True,
    }


# ── Live Positions ───────────────────────────────────────────────────────────

def get_open_positions() -> list[dict[str, Any]]:
    if not connect():
        return []
    positions = mt5.positions_get()
    if positions is None:
        return []
    rows = []
    for p in positions:
        tick = mt5.symbol_info_tick(p.symbol)
        current = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask if tick else p.price_open
        direction = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
        open_dt = datetime.fromtimestamp(p.time, tz=timezone.utc)
        duration = datetime.now(timezone.utc) - open_dt
        hours, rem = divmod(int(duration.total_seconds()), 3600)
        mins = rem // 60
        rows.append({
            "ticket":       p.ticket,
            "symbol":       p.symbol,
            "type":         direction,
            "volume":       p.volume,
            "open_price":   round(p.price_open, 5),
            "current_price":round(current, 5),
            "sl":           round(p.sl, 5),
            "tp":           round(p.tp, 5),
            "swap":         round(p.swap, 2),
            "profit":       round(p.profit, 2),
            "open_time":    open_dt.strftime("%Y-%m-%d %H:%M"),
            "duration":     f"{hours}h {mins}m",
            "magic":        p.magic,
            "comment":      p.comment,
        })
    return rows


# ── Deal / Trade History ─────────────────────────────────────────────────────

def get_closed_trades(days: int = 30) -> list[dict[str, Any]]:
    if not connect():
        return []
    date_from = datetime.now(timezone.utc) - timedelta(days=days)
    date_to   = datetime.now(timezone.utc) + timedelta(days=1)
    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        return []

    # Group deals by position_id to pair entry/exit
    by_pos: dict[int, list] = {}
    for d in deals:
        by_pos.setdefault(d.position_id, []).append(d)

    rows = []
    for pos_id, deal_list in by_pos.items():
        entries = [d for d in deal_list if d.entry == mt5.DEAL_ENTRY_IN]
        exits   = [d for d in deal_list if d.entry == mt5.DEAL_ENTRY_OUT]
        if not entries:
            continue

        entry_deal = entries[0]
        exit_deal  = exits[0] if exits else None

        direction = "BUY" if entry_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
        open_dt  = datetime.fromtimestamp(entry_deal.time, tz=timezone.utc)
        close_dt = datetime.fromtimestamp(exit_deal.time, tz=timezone.utc) if exit_deal else None

        total_profit = sum(d.profit for d in deal_list)
        total_swap   = sum(d.swap for d in deal_list)
        total_comm   = sum(d.commission for d in deal_list)
        net_profit   = round(total_profit + total_swap + total_comm, 2)

        duration_str = ""
        if close_dt:
            secs = int((close_dt - open_dt).total_seconds())
            h, r = divmod(secs, 3600)
            duration_str = f"{h}h {r//60}m"

        rows.append({
            "position_id":   pos_id,
            "symbol":        entry_deal.symbol,
            "type":          direction,
            "volume":        round(entry_deal.volume, 2),
            "entry_price":   round(entry_deal.price, 5),
            "exit_price":    round(exit_deal.price, 5) if exit_deal else None,
            "open_time":     open_dt.strftime("%Y-%m-%d %H:%M"),
            "close_time":    close_dt.strftime("%Y-%m-%d %H:%M") if close_dt else "OPEN",
            "profit":        round(total_profit, 2),
            "swap":          round(total_swap, 2),
            "commission":    round(total_comm, 2),
            "net_profit":    net_profit,
            "duration":      duration_str,
            "magic":         entry_deal.magic,
            "comment":       entry_deal.comment,
        })

    # Sort newest first
    rows.sort(key=lambda x: x["open_time"], reverse=True)
    return rows


# ── Equity Curve ─────────────────────────────────────────────────────────────

def get_equity_curve(days: int = 30) -> list[dict[str, Any]]:
    """
    Reconstructs equity curve from real deal history.
    Each closed trade adds/subtracts from starting balance.
    """
    if not connect():
        return []

    acc = mt5.account_info()
    if acc is None:
        return []

    trades = get_closed_trades(days=days)
    if not trades:
        return [{
            "time":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "equity": acc.balance,
            "is_trade": False,
            "type": ""
        }]

    # Rebuild from oldest to newest
    sorted_trades = sorted(trades, key=lambda x: x["open_time"])
    running_balance = acc.balance - sum(t["net_profit"] for t in sorted_trades)

    curve = []
    for t in sorted_trades:
        running_balance += t["net_profit"]
        curve.append({
            "time":     t["close_time"] if t["close_time"] != "OPEN" else t["open_time"],
            "equity":   round(running_balance, 2),
            "is_trade": True,
            "type":     t["type"] + "_CLOSE",
            "profit":   t["net_profit"],
        })

    return curve


# ── Statistics ────────────────────────────────────────────────────────────────

def calculate_stats(days: int = 30) -> dict[str, Any]:
    trades = get_closed_trades(days=days)
    if not trades:
        return {
            "total_trades":   0,
            "wins":           0,
            "losses":         0,
            "win_rate":       0.0,
            "gross_profit":   0.0,
            "gross_loss":     0.0,
            "net_profit":     0.0,
            "profit_factor":  0.0,
            "max_drawdown":   0.0,
            "best_trade":     0.0,
            "worst_trade":    0.0,
            "avg_profit":     0.0,
            "daily_pnl":      0.0,
        }

    closed = [t for t in trades if t["close_time"] != "OPEN"]
    wins   = [t for t in closed if t["net_profit"] > 0]
    losses = [t for t in closed if t["net_profit"] <= 0]

    gross_profit = sum(t["net_profit"] for t in wins)
    gross_loss   = abs(sum(t["net_profit"] for t in losses))
    net_profit   = sum(t["net_profit"] for t in closed)
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0

    # Daily PnL — trades closed today UTC
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_trades = [t for t in closed if t["close_time"].startswith(today_str)]
    daily_pnl = round(sum(t["net_profit"] for t in today_trades), 2)

    # Max drawdown from equity curve
    curve = get_equity_curve(days=days)
    max_dd = 0.0
    if curve:
        peak = curve[0]["equity"]
        for point in curve:
            if point["equity"] > peak:
                peak = point["equity"]
            dd = peak - point["equity"]
            if dd > max_dd:
                max_dd = dd

    return {
        "total_trades":   len(closed),
        "wins":           len(wins),
        "losses":         len(losses),
        "win_rate":       round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "gross_profit":   round(gross_profit, 2),
        "gross_loss":     round(gross_loss, 2),
        "net_profit":     round(net_profit, 2),
        "profit_factor":  profit_factor,
        "max_drawdown":   round(max_dd, 2),
        "best_trade":     round(max((t["net_profit"] for t in closed), default=0.0), 2),
        "worst_trade":    round(min((t["net_profit"] for t in closed), default=0.0), 2),
        "avg_profit":     round(net_profit / len(closed), 2) if closed else 0.0,
        "daily_pnl":      daily_pnl,
    }


# ── Enhanced Analytics (for rich charts) ──────────────────────────────────────

def get_daily_pnl_series(days: int = 30) -> list[dict[str, Any]]:
    """Daily PnL breakdown for bar charts."""
    trades = get_closed_trades(days=days)
    if not trades:
        return []
    from collections import defaultdict
    daily: dict[str, float] = defaultdict(float)
    for t in trades:
        if t["close_time"] == "OPEN":
            continue
        day_key = t["close_time"][:10]
        daily[day_key] += t["net_profit"]
    result = [{"date": k, "pnl": round(v, 2)} for k, v in sorted(daily.items())]
    return result


def get_pnl_distribution(days: int = 30) -> list[float]:
    """List of net_profit values for histogram."""
    trades = get_closed_trades(days=days)
    return [t["net_profit"] for t in trades if t["close_time"] != "OPEN"]


def get_win_loss_counts(days: int = 30) -> dict[str, int]:
    """Win/Loss breakdown for donut chart."""
    trades = get_closed_trades(days=days)
    closed = [t for t in trades if t["close_time"] != "OPEN"]
    wins = sum(1 for t in closed if t["net_profit"] > 0)
    losses = sum(1 for t in closed if t["net_profit"] <= 0)
    return {"wins": wins, "losses": losses}


def get_symbol_performance(days: int = 30) -> list[dict[str, Any]]:
    """Per-symbol PnL breakdown."""
    trades = get_closed_trades(days=days)
    closed = [t for t in trades if t["close_time"] != "OPEN"]
    from collections import defaultdict
    by_sym: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "count": 0, "wins": 0})
    for t in closed:
        sym = t["symbol"]
        by_sym[sym]["pnl"] += t["net_profit"]
        by_sym[sym]["count"] += 1
        if t["net_profit"] > 0:
            by_sym[sym]["wins"] += 1
    result = []
    for sym, data in sorted(by_sym.items(), key=lambda x: x[1]["pnl"], reverse=True):
        result.append({
            "symbol": sym,
            "net_pnl": round(data["pnl"], 2),
            "trades": data["count"],
            "win_rate": round(data["wins"] / data["count"] * 100, 1) if data["count"] else 0.0,
        })
    return result


def get_drawdown_series(curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute drawdown series from equity curve."""
    if not curve:
        return []
    dd_series = []
    peak = curve[0]["equity"]
    for point in curve:
        if point["equity"] > peak:
            peak = point["equity"]
        dd = peak - point["equity"]
        dd_pct = round((dd / peak) * 100, 2) if peak > 0 else 0.0
        dd_series.append({
            "time": point["time"],
            "drawdown": round(dd, 2),
            "drawdown_pct": dd_pct,
        })
    return dd_series


def get_diagnostic_info() -> dict[str, Any]:
    """Return diagnostic information about MT5 connection status."""
    import platform
    import os as _os

    # Robust OS detection — platform.system() can return "Unknown" on some Windows builds
    os_name = platform.system()
    if not os_name or os_name == "Unknown":
        if _os.name == "nt":
            os_name = "Windows"
        elif _os.name == "posix":
            os_name = "Linux/Mac"
        else:
            os_name = _os.name or "Unknown"

    is_windows = _os.name == "nt"

    info = {
        "os": os_name,
        "os_release": platform.release() or "N/A",
        "is_windows": is_windows,
        "mt5_installed": False,
        "mt5_connect_error": "",
        "terminal_running": False,
        "suggestions": [],
    }
    try:
        import MetaTrader5 as mt5
        info["mt5_installed"] = True
        # Try to initialize to check terminal
        try:
            term = mt5.terminal_info()
            if term:
                info["terminal_running"] = term.connected
                info["terminal_build"] = term.build if hasattr(term, 'build') else 'N/A'
            else:
                info["mt5_connect_error"] = "Terminal not launched or not logged in"
        except Exception:
            # terminal_info may fail if initialize() not called first
            try:
                if mt5.initialize():
                    term = mt5.terminal_info()
                    if term:
                        info["terminal_running"] = term.connected
                    mt5.shutdown()
            except Exception:
                pass
        if not info["terminal_running"] and not info["mt5_connect_error"]:
            info["mt5_connect_error"] = str(mt5.last_error()) if mt5.last_error() else "Terminal not open"
    except ImportError:
        info["mt5_connect_error"] = "MetaTrader5 Python package not installed"
    except Exception as e:
        info["mt5_connect_error"] = str(e)

    if not is_windows:
        info["suggestions"].append("🖥️ This machine runs {}. MT5 only works on Windows.".format(os_name))
        info["suggestions"].append("→ Deploy dashboard.py to your AWS Windows VPS where MT5 is installed.")
        info["suggestions"].append("→ Run: python -m streamlit run dashboard.py --server.port 80 --server.address 0.0.0.0")
    elif not info["terminal_running"]:
        info["suggestions"].append("⚠️ MT5 terminal is not open or not logged in.")
        info["suggestions"].append("→ Launch MetaTrader 5, log into your broker, and enable Algo Trading (Ctrl+E).")
        info["suggestions"].append("→ Verify mt5_config.json has correct login/password/server.")
        info["suggestions"].append("→ Make sure XAUUSD is in Market Watch (right-click → Show All).")

    return info


# ── Live Tick ─────────────────────────────────────────────────────────────────

def get_live_tick(symbol: str) -> dict[str, Any]:
    if not connect():
        return {}
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None:
        return {}
    return {
        "bid":    round(tick.bid, 5),
        "ask":    round(tick.ask, 5),
        "spread": info.spread if info else 0,
        "time":   datetime.fromtimestamp(tick.time, tz=timezone.utc).strftime("%H:%M:%S"),
    }
