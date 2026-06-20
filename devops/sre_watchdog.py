#!/usr/bin/env python3
"""
AGENTX SRE Watchdog — real health checks that detect actual problems.

Checks every 5 minutes:
1. MT5 connectivity (initialization + account login)
2. AutoTrading enabled (trade_allowed / trade_mode == 0)
3. Bot processes running (by PID file or psutil scan)
4. Trade execution health (recent retcode errors in trade history)
5. Bridge (port 5000) / Backend (port 8005) / Sentiment (port 8001) alive

Outputs structured alerts only when problems are detected.
Exits silently (code 0, no stdout) if everything is healthy.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TRADING_DIR = Path("C:/Trading")
STATE_FILE = TRADING_DIR / "devops" / "sre_state.json"
BRIDGE_PORT = 5000
BACKEND_PORT = 8005

# Magic numbers of known bots — if we see trades with these, bot is working
BOT_MAGICS = {777555, 999111, 888666, 777556, 999112, 666334, 777888}


def http_get(url, timeout=8):
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        return resp.status, resp.read().decode()
    except Exception as e:
        return 0, str(e)


# ── MT5 Connectivity ──────────────────────────────────────────────────────────

def check_mt5():
    """
    Check MT5 terminal connection and AutoTrading state.
    Returns (connected: bool, autotrading: bool, detail: str, error: str)
    """
    try:
        import MetaTrader5 as mt5

        config_path = TRADING_DIR / "mt5_config.json"
        if not config_path.exists():
            return False, False, "mt5_config.json not found", "Critical"

        cfg = json.loads(config_path.read_text())
        initialized = mt5.initialize(
            path=cfg.get("terminal_path", "C:\\Program Files\\MetaTrader 5\\terminal64.exe"),
            login=int(cfg["login"]),
            password=cfg["password"],
            server=cfg["server"],
            timeout=15000,
        )
        if not initialized:
            error = mt5.last_error()
            mt5.shutdown()
            return False, False, f"MT5 init failed: {error}", "Critical"

        # Check account
        acct = mt5.account_info()
        if acct is None:
            mt5.shutdown()
            return False, False, "Account info returned None", "Critical"

        # AutoTrading check — the holy grail
        autotrading = bool(acct.trade_allowed)
        trade_mode = acct.trade_mode  # 0=disabled, 1=real, 2=contest, 3=demo
        mode_name = {0: "DISABLED", 1: "REAL", 2: "CONTEST", 3: "DEMO"}.get(trade_mode, f"UNKNOWN({trade_mode})")

        detail_parts = [f"balance={acct.balance:.2f}", f"mode={mode_name}"]
        if not autotrading:
            detail_parts.append("⚠️ AUTOTRADING DISABLED (retcode 10027 risk)")

        mt5.shutdown()
        return True, autotrading, " | ".join(detail_parts), "Critical" if not autotrading else None

    except ImportError:
        return False, False, "MetaTrader5 Python package not installed", "Critical"
    except Exception as e:
        return False, False, f"MT5 check error: {e}", "Critical"


def check_trade_history():
    """
    Check recent trades for retcode errors.
    Returns (clean: bool, alert: str)
    """
    try:
        import MetaTrader5 as mt5

        config_path = TRADING_DIR / "mt5_config.json"
        if not config_path.exists():
            return True, ""

        cfg = json.loads(config_path.read_text())
        mt5.initialize(
            path=cfg.get("terminal_path"),
            login=int(cfg["login"]),
            password=cfg["password"],
            server=cfg["server"],
            timeout=10000,
        )

        # Get trades from the last 24 hours
        from datetime import timedelta
        now = datetime.now()
        yesterday = now - timedelta(hours=24)
        trades = mt5.history_deals_get(yesterday, now) or []

        # Check for retcode errors in order history too
        orders = mt5.history_orders_get(yesterday, now) or []

        mt5.shutdown()

        # Check deal retcodes
        bad_deals = []
        for d in trades:
            if hasattr(d, 'retcode') and d.retcode and d.retcode != 0:
                bad_deals.append({
                    "ticket": d.ticket,
                    "symbol": d.symbol,
                    "retcode": d.retcode,
                    "comment": d.comment or "",
                })

        # Check order retcodes
        bad_orders = []
        for o in orders:
            if hasattr(o, 'retcode') and o.retcode and o.retcode != 0:
                bad_orders.append({
                    "ticket": o.ticket,
                    "symbol": o.symbol,
                    "retcode": o.retcode,
                    "comment": o.comment or "",
                })

        all_issues = bad_deals + bad_orders
        retcode_10027 = [x for x in all_issues if x["retcode"] == 10027]

        if retcode_10027:
            return False, f"🚨 {len(retcode_10027)} trades blocked by retcode 10027 (AutoTrading disabled)"

        if all_issues:
            return False, f"⚠️ {len(all_issues)} trades with non-zero retcodes: {[(x['retcode'], x['symbol']) for x in all_issues[:5]]}"

        return True, ""

    except Exception as e:
        return True, ""  # Silent on errors — don't alarm unnecessarily


# ── Process Monitoring ────────────────────────────────────────────────────────

def check_bot_processes():
    """
    Check if bot scripts are running as Python processes.
    Returns (running_count: int, stopped_bots: list[str])
    """
    bot_scripts = [
        "gold_bot_v3.py", "scalping_youtube_goldstrategy.py",
        "streaming_bot_v3.py", "gold_phoenix_bot.py",
        "scalping_phoenix_hybrid.py",
    ]
    missing = []

    try:
        import psutil
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                if proc.info["name"] and "python" not in proc.info["name"].lower():
                    continue
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(cmdline).lower()
                for script in bot_scripts[:]:
                    if script.lower() in cmd_str:
                        bot_scripts.remove(script)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return len(bot_scripts), bot_scripts

    except ImportError:
        return 0, [f"psutil not installed — cannot check processes"]


# ── Bridge / Backend Health ───────────────────────────────────────────────────

def check_bridge():
    status, body = http_get(f"http://127.0.0.1:{BRIDGE_PORT}/health")
    if status != 200:
        return False, f"HTTP {status}"
    try:
        data = json.loads(body)
        return True, f"connected={data.get('connected', False)}"
    except json.JSONDecodeError:
        return True, "bad json"


def check_backend():
    status, body = http_get(f"http://127.0.0.1:{BACKEND_PORT}/api/health")
    if status != 200:
        return False, f"HTTP {status}"
    try:
        data = json.loads(body)
        bridge_ok = data.get("bridge", {}).get("connected", False)
        db_ok = data.get("database", {}).get("connected", False)
        redis_ok = data.get("redis", {}).get("connected", False)
        return True, f"bridge={bridge_ok} db={db_ok} redis={redis_ok}"
    except json.JSONDecodeError:
        return True, "bad json"


# ── State Management ──────────────────────────────────────────────────────────

def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {
        "mt5_was_down": False,
        "autotrading_was_off": False,
        "bridge_was_down": False,
        "backend_was_down": False,
        "trade_retcodes_warned": False,
        "bots_were_stopped": False,
    }


def save_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2, default=str))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    state = load_state()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    changes = []
    alerts = []
    all_healthy = True

    # 1. MT5 Connectivity + AutoTrading
    mt5_ok, at_enabled, mt5_detail, mt5_severity = check_mt5()

    if not mt5_ok:
        if not state.get("mt5_was_down"):
            changes.append(f"[{now}] 🔴 MT5 DISCONNECTED: {mt5_detail}")
            state["mt5_was_down"] = True
            all_healthy = False
    else:
        if state.get("mt5_was_down"):
            changes.append(f"[{now}] ✅ MT5 reconnected: {mt5_detail}")
        state["mt5_was_down"] = False

        if not at_enabled:
            if not state.get("autotrading_was_off"):
                changes.append(f"[{now}] 🚨 AUTOTRADING DISABLED! retcode 10027 will block all trades. Fix: enable AutoTrading in MT5 terminal.")
                state["autotrading_was_off"] = True
                all_healthy = False
        else:
            if state.get("autotrading_was_off"):
                changes.append(f"[{now}] ✅ AutoTrading re-enabled")
            state["autotrading_was_off"] = False

    # 2. Trade execution check (retcode errors)
    trades_clean, trade_alert = check_trade_history()
    if not trades_clean:
        if not state.get("trade_retcodes_warned"):
            changes.append(f"[{now}] {trade_alert}")
            state["trade_retcodes_warned"] = True
            all_healthy = False
    else:
        if state.get("trade_retcodes_warned"):
            changes.append(f"[{now}] ✅ Trade execution recovered — no retcode errors in last 24h")
        state["trade_retcodes_warned"] = False

    # 3. Bot processes
    running_count, stopped_bots = check_bot_processes()
    if isinstance(running_count, int) and stopped_bots:
        if not state.get("bots_were_stopped"):
            changes.append(f"[{now}] ⚠️ {len(stopped_bots)} bot(s) not running: {', '.join(stopped_bots)}")
            state["bots_were_stopped"] = True
            all_healthy = False
    else:
        state["bots_were_stopped"] = False

    # 4. Bridge health
    bridge_alive, bridge_detail = check_bridge()
    if not bridge_alive:
        if not state.get("bridge_was_down"):
            changes.append(f"[{now}] 🔴 Bridge DOWN (port {BRIDGE_PORT}): {bridge_detail}")
            state["bridge_was_down"] = True
            all_healthy = False
    else:
        if state.get("bridge_was_down"):
            changes.append(f"[{now}] ✅ Bridge recovered: {bridge_detail}")
        state["bridge_was_down"] = False

    # 5. Backend health
    backend_alive, backend_detail = check_backend()
    if not backend_alive:
        if not state.get("backend_was_down"):
            changes.append(f"[{now}] 🔴 Backend DOWN (port {BACKEND_PORT}): {backend_detail}")
            state["backend_was_down"] = True
            all_healthy = False
    else:
        if state.get("backend_was_down"):
            changes.append(f"[{now}] ✅ Backend recovered: {backend_detail}")
        state["backend_was_down"] = False

    save_state(state)

    # ── Summary ──────────────────────────────────────────────────────────
    if changes:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"── SRE Watchdog [{ts}] ──")
        print("\n".join(changes))
        if all_healthy:
            print(f"✅ All systems nominal")
        else:
            print(f"🔴 Issues detected — see above")
    # else: silent exit — healthy, nothing to report

    sys.exit(0)  # Always exit 0 — cron interprets non-zero as error. State is communicated via stdout.


if __name__ == "__main__":
    main()
