#!/usr/bin/env python3
"""
AGENTX Trade Watchdog — real-time trade monitoring with health detection.

Checks every 5 minutes:
1. Open positions and trade activity
2. MT5 trade execution errors (retcode 10027 and others)
3. Trade execution success rate

Outputs:
- New positions opened (full details)
- Positions closed (P&L)
- Trade execution errors detected
- Silent exit if nothing changed
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path(os.environ.get("HERMES_SCRIPTS_DIR", "C:/Users/nryur/AppData/Local/hermes/cron")) / "watchdog_state.json"
MT5_CONFIG = Path("C:/Trading/mt5_config.json")
TRADING_DIR = Path("C:/Trading")

BOT_MAGICS = {
    777555: "GoldBot_v2", 999111: "Scalping_v3", 888666: "Streaming_v2",
    777556: "GoldBot_v3", 999112: "Scalping_v4", 666334: "Streaming_v3",
    777888: "GoldPhoenix",
}


def get_mt5_state():
    """Get open positions, account info, and check for trade execution errors."""
    try:
        import MetaTrader5 as mt5

        if not MT5_CONFIG.exists():
            return {"error": f"Config not found: {MT5_CONFIG}"}

        cfg = json.loads(MT5_CONFIG.read_text())
        initialized = mt5.initialize(
            path=cfg.get("terminal_path", "C:\\Program Files\\MetaTrader 5\\terminal64.exe"),
            login=int(cfg["login"]),
            password=cfg["password"],
            server=cfg["server"],
            timeout=15000,
        )
        if not initialized:
            return {"error": f"MT5 init failed: {mt5.last_error()}"}

        positions = mt5.positions_get() or []
        acct = mt5.account_info()
        tick = mt5.symbol_info_tick("XAUUSD")

        # Check for recent trade execution errors (last 24h)
        now = datetime.now()
        from datetime import timedelta
        yesterday = now - timedelta(hours=24)
        recent_orders = mt5.history_orders_get(yesterday, now) or []
        recent_deals = mt5.history_deals_get(yesterday, now) or []

        # Collect retcode errors
        trade_errors = []
        for o in recent_orders:
            ret = getattr(o, 'retcode', 0)
            if ret and ret != 0:
                trade_errors.append({
                    "ticket": o.ticket,
                    "symbol": o.symbol,
                    "type": "ORDER",
                    "retcode": ret,
                    "retcode_name": _retcode_name(ret),
                    "comment": o.comment or "",
                    "time": str(getattr(o, 'time_done', o.time_setup)),
                })
        for d in recent_deals:
            ret = getattr(d, 'retcode', 0)
            if ret and ret != 0:
                trade_errors.append({
                    "ticket": d.ticket,
                    "symbol": d.symbol,
                    "type": "DEAL",
                    "retcode": ret,
                    "retcode_name": _retcode_name(ret),
                    "comment": d.comment or "",
                    "time": str(d.time),
                })

        result = {
            "positions": [],
            "balance": acct.balance if acct else 0,
            "equity": acct.equity if acct else 0,
            "free_margin": acct.margin_free if acct else 0,
            "bid": tick.bid if tick else 0,
            "ask": tick.ask if tick else 0,
            "autotrading": bool(acct.trade_allowed) if acct else False,
            "trade_errors": trade_errors[:20],  # cap at 20
            "total_errors_24h": len(trade_errors),
        }

        for p in positions:
            bot_name = BOT_MAGICS.get(p.magic, f"Bot#{p.magic}")
            sl_distance = abs(p.price_open - p.sl) if p.sl else 0
            tp_distance = abs(p.tp - p.price_open) if p.tp else 0

            result["positions"].append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": round(p.profit, 2),
                "swap": p.swap,
                "magic": p.magic,
                "comment": p.comment,
                "bot_name": bot_name,
                "open_time": str(p.time),
            })

        mt5.shutdown()
        return result

    except Exception as e:
        return {"error": str(e), "positions": []}


def _retcode_name(code):
    """Map MT5 retcode to human-readable name."""
    names = {
        10004: "TRADE_RETCODE_REQUOTE",
        10006: "TRADE_RETCODE_REJECT",
        10007: "TRADE_RETCODE_CANCEL",
        10008: "TRADE_RETCODE_PLACEOFF",
        10009: "TRADE_RETCODE_NO_MONEY",
        10010: "TRADE_RETCODE_INVALID_PRICE",
        10011: "TRADE_RETCODE_INVALID_STOPS",
        10012: "TRADE_RETCODE_INVALID_VOLUME",
        10013: "TRADE_RETCODE_MARKET_CLOSED",
        10014: "TRADE_RETCODE_LIMIT_ORDERS",
        10015: "TRADE_RETCODE_NO_CONNECTION",
        10016: "TRADE_RETCODE_TOO_FREQUENT",
        10017: "TRADE_RETCODE_TOO_MANY",
        10018: "TRADE_RETCODE_MODIFY_DENIED",
        10019: "TRADE_RETCODE_FROZEN",
        10020: "TRADE_RETCODE_SAME",
        10021: "TRADE_RETCODE_WRONG_ID",
        10022: "TRADE_RETCODE_WRONG_GROUP",
        10023: "TRADE_RETCODE_HEDGE_PROHIBITED",
        10024: "TRADE_RETCODE_TOO_MANY_POSITIONS",
        10025: "TRADE_RETCODE_ORDER_LOCKED",
        10026: "TRADE_RETCODE_LONG_ONLY",
        10027: "TRADE_RETCODE_SHORT_ONLY / AUTOTRADING DISABLED",
    }
    return names.get(code, f"UNKNOWN({code})")


def format_retcode_alert(errors, now):
    """Format trade execution error alerts."""
    lines = []
    retcode_10027 = [e for e in errors if e["retcode"] == 10027]
    other_errors = [e for e in errors if e["retcode"] != 10027]

    if retcode_10027:
        lines.append(f"🚨 **AutoTrading DISABLED** — {len(retcode_10027)} trades blocked by retcode 10027")
        lines.append(f"   Fix: Open MT5 → Tools → Options → Expert Advisors → 'Allow automated trading' → OK")
        lines.append(f"")

    if other_errors:
        lines.append(f"⚠️ **{len(other_errors)} trade execution errors** in last 24h:")
        for e in other_errors[:5]:
            lines.append(f"   • {e['symbol']}: retcode {e['retcode']} ({e['retcode_name']}) — {e['comment']}")
        if len(other_errors) > 5:
            lines.append(f"   ... and {len(other_errors) - 5} more")

    if lines:
        lines.insert(0, f"── Trade Errors [{now}] ──")
    return "\n".join(lines)


def main():
    state = get_mt5_state()
    if "error" in state:
        print(f"⚠️ Watchdog error: {state['error']}")
        sys.exit(0)

    # Load previous state
    prev = {"tickets": [], "trade_errors": []}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text())
        except Exception:
            pass

    current_tickets = {p["ticket"] for p in state["positions"]}
    prev_tickets = set(prev.get("tickets", []))
    new_tickets = current_tickets - prev_tickets
    closed_tickets = prev_tickets - current_tickets

    # Save current state
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "tickets": list(current_tickets),
        "last_positions": state["positions"],
        "balance": state["balance"],
        "trade_errors": state["trade_errors"],
        "autotrading": state["autotrading"],
    }))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    output_parts = []

    # ── NEW POSITIONS OPENED ──────────────────────────────────────────────
    if new_tickets:
        for p in state["positions"]:
            if p["ticket"] in new_tickets:
                direction = "🟢 LONG" if p["type"] == "BUY" else "🔴 SHORT"
                output_parts.append(
                    f"⚡ **TRADE OPENED** ⚡\n"
                    f"{direction} {p['symbol']} — {p['bot_name']}\n"
                    f"**Entry:** ${p['price_open']:.2f}\n"
                    f"**Volume:** {p['volume']} lots\n"
                    f"**Account:** ${state['balance']:,.2f}\n"
                    f"**Time:** {now}"
                )

    # ── POSITIONS CLOSED ──────────────────────────────────────────────────
    if closed_tickets:
        for ticket in closed_tickets:
            for pp in prev.get("last_positions", []):
                if pp["ticket"] == ticket:
                    direction = "🟢 LONG" if pp["type"] == "BUY" else "🔴 SHORT"
                    pl_delta = state.get("balance", 0) - prev.get("balance", 0)
                    emoji = "✅" if pl_delta >= 0 else "❌"
                    output_parts.append(
                        f"{emoji} **TRADE CLOSED** {emoji}\n"
                        f"{direction} {pp['symbol']} — {pp.get('bot_name', 'Bot')}\n"
                        f"**Entry:** ${pp['price_open']:.2f}\n"
                        f"**Result:** ${pl_delta:+.2f}\n"
                        f"**Time:** {now}"
                    )
                    break

    # ── TRADE EXECUTION ERRORS ────────────────────────────────────────────
    if state.get("trade_errors"):
        # Only alert if new errors since last check
        prev_error_count = len(prev.get("trade_errors", []))
        current_error_count = state["total_errors_24h"]

        if current_error_count > prev_error_count or (current_error_count > 0 and not prev.get("trade_errors")):
            alert = format_retcode_alert(state["trade_errors"][:5], now)
            if alert:
                output_parts.append(alert)

        # Always report retcode 10027 — it's critical
        retcode_10027 = [e for e in state["trade_errors"] if e["retcode"] == 10027]
        if retcode_10027 and not prev.get("autotrading", True):
            pass  # Already warned about this
        elif retcode_10027 and prev.get("autotrading", True):
            output_parts.append(
                f"🚨 **AUTOTRADING DISABLED** — {len(retcode_10027)} trades rejected!\n"
                f"Fix: MT5 → Tools → Options → Expert Advisors → Allow automated trading"
            )

    # ── OUTPUT ────────────────────────────────────────────────────────────
    if output_parts:
        print("\n\n".join(output_parts))
    else:
        # Silent — nothing changed
        sys.exit(0)


if __name__ == "__main__":
    main()
