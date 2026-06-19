#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║        TRADING SYSTEM — HEALTH CHECK             ║
║  Checks: backend · bridge · db · account · bots  ║
║         trades · positions · research             ║
╚══════════════════════════════════════════════════╝
"""

import sys
import json
import time
from datetime import datetime, timedelta

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

# ── Config ──────────────────────────────────────────────────────────────
BASE_URL = "http://10.10.10.100:8005"
TIMEOUT = 5  # seconds
EXPECTED_BOT_COUNT = 23

# ── ANSI Colors ─────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS = f"{GREEN}✅ PASS{RESET}"
FAIL = f"{RED}❌ FAIL{RESET}"
WARN = f"{YELLOW}⚠️  WARN{RESET}"
INFO = f"{CYAN}ℹ️  INFO{RESET}"

# ── Results accumulator ─────────────────────────────────────────────────
results = []  # list of (label, status_str, is_critical_bool)
start_time = datetime.now()


def log(label, status, detail="", critical=True):
    """Append a check result and print it immediately."""
    results.append((label, status, critical))
    icon = status.split(" ")[0] if not status.startswith("\033") else ""
    padded = f"{label:36s}"
    print(f"  {status}  {padded} {detail}")


def http_get(path, timeout=TIMEOUT):
    """Safe HTTP GET returning parsed JSON or None."""
    url = f"{BASE_URL}{path}"
    try:
        if HAS_REQUESTS:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        else:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode()
                return json.loads(body)
    except Exception as e:
        return None


# ── Header ──────────────────────────────────────────────────────────────
def print_header():
    print()
    print(f"{'=' * 60}")
    print(f"  {BOLD}TRADING SYSTEM HEALTH CHECK{RESET}")
    print(f"  Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Target:  {BASE_URL}")
    print(f"{'=' * 60}")
    print()


# ── 1. Backend Connectivity ─────────────────────────────────────────────
def check_backend():
    print(f"  {CYAN}{'─'*56}{RESET}")
    print(f"  {BOLD}1. BACKEND & INFRASTRUCTURE{RESET}")
    print(f"  {CYAN}{'─'*56}{RESET}")

    data = http_get("/api/health")
    if data is None:
        log("Backend API reachable", FAIL, "Connection refused or timeout", critical=True)
        return None  # signal total failure — skip remaining checks
    else:
        log("Backend API reachable", PASS, f"HTTP 200 OK", critical=True)

    # Bridge status
    bridge = data.get("bridge", data.get("bridge_status", {}))
    bridge_ok = bridge.get("connected", False) if isinstance(bridge, dict) else False
    if bridge_ok:
        log("MT5 Bridge connected", PASS, "", critical=True)
    else:
        log("MT5 Bridge connected", FAIL, "bridge reports disconnected", critical=True)

    # Database status
    db = data.get("database", data.get("db_status", {}))
    db_ok = db.get("connected", False) if isinstance(db, dict) else isinstance(db, bool) and db
    if db_ok:
        log("Database connected", PASS, "", critical=True)
    else:
        log("Database connected", FAIL, "database reports disconnected", critical=True)

    # Bridge diagnostic (extra detail)
    diag = http_get("/api/diagnostic")
    if diag is not None and isinstance(diag, dict):
        detail = diag.get("connection_type", diag.get("status", "connected"))
        log("Bridge diagnostic", PASS, detail, critical=False)
    else:
        log("Bridge diagnostic", WARN, "diagnostic endpoint unavailable", critical=False)

    return True


# ── 2. Account ──────────────────────────────────────────────────────────
def check_account():
    print()
    print(f"  {CYAN}{'─'*56}{RESET}")
    print(f"  {BOLD}2. ACCOUNT{RESET}")
    print(f"  {CYAN}{'─'*56}{RESET}")

    data = http_get("/api/accounts/active")
    if data is None:
        log("Account info reachable", FAIL, "endpoint unreachable", critical=True)
        return

    acct = data.get("account", data)
    if not isinstance(acct, dict):
        log("Account data format", WARN, f"unexpected response: {type(acct).__name__}", critical=True)
        return

    connected = acct.get("connected", False)
    if connected:
        login = acct.get("login", "?")
        balance = acct.get("balance", 0.0)
        equity = acct.get("equity", 0.0)
        log("Account connected", PASS, f"Login: {login}", critical=True)
        log("Account balance", INFO, f"${balance:,.2f}  (Equity: ${equity:,.2f})", critical=False)
    else:
        log("Account connected", FAIL, "account not connected to broker", critical=True)

    trade_allowed = acct.get("trade_allowed", False)
    if trade_allowed:
        log("Trade allowed flag", PASS, "trading is enabled", critical=True)
    else:
        log("Trade allowed flag", FAIL, "trading is DISABLED", critical=True)


# ── 3. Bots ─────────────────────────────────────────────────────────────
def check_bots():
    print()
    print(f"  {CYAN}{'─'*56}{RESET}")
    print(f"  {BOLD}3. BOTS ({EXPECTED_BOT_COUNT} expected){RESET}")
    print(f"  {CYAN}{'─'*56}{RESET}")

    data = http_get("/api/bots")
    if data is None:
        log("Bots list reachable", FAIL, "endpoint unreachable", critical=True)
        return

    bots = data if isinstance(data, list) else data.get("bots", [])

    total = len(bots)
    running = sum(1 for b in bots if b.get("running", False))

    if total == EXPECTED_BOT_COUNT:
        log(f"Bot count ({total}/{EXPECTED_BOT_COUNT})", PASS, "all bots present", critical=True)
    else:
        log(f"Bot count ({total}/{EXPECTED_BOT_COUNT})", WARN, f"found {total}, expected {EXPECTED_BOT_COUNT}", critical=False)

    pct = (running / total * 100) if total > 0 else 0
    if running == total:
        log(f"Bots running ({running}/{total})", PASS, f"100% online", critical=True)
    elif pct >= 80:
        log(f"Bots running ({running}/{total})", WARN, f"{pct:.0f}% online", critical=False)
    else:
        log(f"Bots running ({running}/{total})", FAIL, f"{pct:.0f}% online — {total - running} stopped", critical=True)

    # List stopped bots
    stopped = [b.get("name", "?") for b in bots if not b.get("running", False)]
    if stopped:
        print(f"    {YELLOW}⚠  Stopped bots:{RESET} {', '.join(stopped)}")

    # Show a few running as sample
    running_names = [b.get("name", "?") for b in bots if b.get("running", False)]
    if running_names:
        sample = ", ".join(running_names[:5])
        extra = f" ... and {len(running_names)-5} more" if len(running_names) > 5 else ""
        print(f"    {CYAN}ℹ  Running:{RESET} {sample}{extra}")


# ── 4. Open Positions ───────────────────────────────────────────────────
def check_positions():
    print()
    print(f"  {CYAN}{'─'*56}{RESET}")
    print(f"  {BOLD}4. OPEN POSITIONS{RESET}")
    print(f"  {CYAN}{'─'*56}{RESET}")

    data = http_get("/api/positions")
    if data is None:
        log("Positions endpoint", WARN, "endpoint unreachable (non-critical)", critical=False)
        return

    positions = data if isinstance(data, list) else data.get("positions", data.get("active_trades", []))
    count = len(positions)

    if count == 0:
        log("Open positions", PASS, "0 positions — no exposure", critical=False)
    else:
        total_pnl = sum(float(p.get("profit", p.get("pnl", 0))) for p in positions)
        log("Open positions", WARN, f"{count} position(s), total P&L: ${total_pnl:+.2f}", critical=False)
        for p in positions:
            sym = p.get("symbol", p.get("ticket", "?"))
            vol = p.get("volume", p.get("lots", "?"))
            prof = p.get("profit", p.get("pnl", 0))
            tp = p.get("tp", p.get("take_profit", "—"))
            sl = p.get("sl", p.get("stop_loss", "—"))
            print(f"    {CYAN}ℹ{RESET}  {sym}  vol={vol}  profit={prof:+.2f}  TP={tp}  SL={sl}")


# ── 5. Recent Trades (24h) ──────────────────────────────────────────────
def check_trades():
    print()
    print(f"  {CYAN}{'─'*56}{RESET}")
    print(f"  {BOLD}5. RECENT TRADES (24h){RESET}")
    print(f"  {CYAN}{'─'*56}{RESET}")

    data = http_get("/api/trades/filter?days=1")
    if data is None:
        # Try stats endpoint as fallback
        stats = http_get("/api/stats")
        if stats and isinstance(stats, dict):
            total = stats.get("total_trades", 0)
            net_pnl = stats.get("net_pnl", 0.0)
            win_rate = stats.get("win_rate", 0)
            pf = stats.get("profit_factor", 0)
            log("Recent trades (from stats)", PASS, f"{total} trades, P&L: ${net_pnl:+.2f}, WR: {win_rate:.1f}%, PF: {pf:.2f}", critical=False)
        else:
            log("Recent trades endpoint", WARN, "unreachable (non-critical)", critical=False)
        return

    trades = data if isinstance(data, list) else data.get("trades", data.get("history", []))
    count = len(trades)

    if count == 0:
        log("Recent trades (24h)", PASS, "0 trades in last 24h", critical=False)
        return

    total_pnl = sum(float(t.get("profit", t.get("pnl", 0))) for t in trades)
    wins = sum(1 for t in trades if float(t.get("profit", t.get("pnl", 0))) > 0)
    losses = count - wins
    win_rate = (wins / count * 100) if count > 0 else 0.0

    log(f"Recent trades (24h)", PASS, f"{count} trades, P&L: ${total_pnl:+.2f}", critical=False)
    log(f"  Win/Loss", INFO, f"{wins}W / {losses}L  ({win_rate:.1f}% WR)", critical=False)


# ── 6. Stats Dashboard ──────────────────────────────────────────────────
def check_stats():
    print()
    print(f"  {CYAN}{'─'*56}{RESET}")
    print(f"  {BOLD}6. PERFORMANCE STATS{RESET}")
    print(f"  {CYAN}{'─'*56}{RESET}")

    data = http_get("/api/stats")
    if data is None or not isinstance(data, dict):
        log("Stats endpoint", WARN, "unreachable (non-critical)", critical=False)
        return

    total = data.get("total_trades", 0)
    wr = data.get("win_rate", 0)
    pf = data.get("profit_factor", 0)
    net = data.get("net_pnl", 0)
    open_pos = data.get("open_positions", 0)

    print(f"    {CYAN}ℹ{RESET}  Total trades:     {total}")
    print(f"    {CYAN}ℹ{RESET}  Win rate:         {wr:.1f}%")
    print(f"    {CYAN}ℹ{RESET}  Profit factor:    {pf:.2f}")
    print(f"    {CYAN}ℹ{RESET}  Net P&L:          ${net:+.2f}")
    print(f"    {CYAN}ℹ{RESET}  Open positions:   {open_pos}")

    log("Dashboard stats", PASS, "all metrics retrieved", critical=False)


# ── 7. Research Division ────────────────────────────────────────────────
def check_research():
    print()
    print(f"  {CYAN}{'─'*56}{RESET}")
    print(f"  {BOLD}7. RESEARCH DIVISION{RESET}")
    print(f"  {CYAN}{'─'*56}{RESET}")

    status = http_get("/api/research/division-status")
    insights = http_get("/api/research/insights")

    if status is None and insights is None:
        log("Research division", WARN, "endpoints unreachable (non-critical)", critical=False)
        return

    # Division status
    if status is not None and isinstance(status, dict):
        div_status = status.get("status", status.get("division_status", "unknown"))
        if div_status in ("active", "running", "ok", "healthy"):
            log("Division status", PASS, div_status, critical=False)
        elif div_status in ("degraded", "warning", "partial"):
            log("Division status", WARN, div_status, critical=False)
        else:
            log("Division status", INFO, div_status, critical=False)

        # Show any sub-fields
        for key in ("active_pairs", "pairs_analyzed", "last_update", "last_analysis"):
            val = status.get(key)
            if val is not None:
                if isinstance(val, list):
                    print(f"    {CYAN}ℹ{RESET}  {key}: {', '.join(val[:6])}{'...' if len(val) > 6 else ''}")
                else:
                    print(f"    {CYAN}ℹ{RESET}  {key}: {val}")
    else:
        log("Division status endpoint", WARN, "no status data", critical=False)

    # Insights
    if insights is not None:
        pairs = insights if isinstance(insights, list) else insights.get("insights", insights.get("pairs", []))
        if isinstance(pairs, list):
            log(f"Pair insights ({len(pairs)} pairs)", PASS, "research data available", critical=False)
            for p in pairs[:5]:
                name = p.get("pair", p.get("symbol", "?"))
                signal = p.get("signal", p.get("verdict", "—"))
                strength = p.get("strength", p.get("confidence", ""))
                print(f"    {CYAN}ℹ{RESET}  {name}: {signal} {strength}")
            if len(pairs) > 5:
                print(f"    {CYAN}ℹ{RESET}  ... and {len(pairs)-5} more pairs")
        else:
            log("Pair insights", INFO, "data retrieved", critical=False)
    else:
        log("Pair insights", WARN, "insights endpoint unreachable", critical=False)


# ── Summary ─────────────────────────────────────────────────────────────
def print_summary():
    elapsed = (datetime.now() - start_time).total_seconds()
    critical_passed = all(critical for _, status, critical in results if critical and "FAIL" in status)
    # Recalculate: all critical checks should have PASS or INFO status (not FAIL)
    all_critical_ok = True
    for label, status_text, critical in results:
        if critical and ("FAIL" in status_text or "❌" in status_text):
            all_critical_ok = False

    passed = sum(1 for _, s, _ in results if "PASS" in s or "ℹ️" in s)
    warned = sum(1 for _, s, _ in results if "WARN" in s or "⚠️" in s)
    failed = sum(1 for _, s, _ in results if "FAIL" in s or "❌" in s)
    total = len(results)

    print()
    print(f"{'=' * 60}")
    print(f"  {BOLD}SUMMARY{RESET}")
    print(f"{'=' * 60}")
    print(f"  Checks run:   {total}")
    print(f"  Passed:       {GREEN}{passed}{RESET}")
    print(f"  Warnings:     {YELLOW}{warned}{RESET}")
    print(f"  Failed:       {RED}{failed}{RESET}")
    print(f"  Duration:     {elapsed:.1f}s")
    print(f"  Timestamp:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    if all_critical_ok:
        print(f"  {GREEN}{BOLD}✅ SYSTEM HEALTH: PASS{RESET}")
        print(f"  {GREEN}All critical checks passed. System is operational.{RESET}")
        print()
        return 0
    else:
        print(f"  {RED}{BOLD}❌ SYSTEM HEALTH: FAIL{RESET}")
        print(f"  {RED}One or more critical checks failed. Review above.{RESET}")
        print()
        return 1


# ── Main ────────────────────────────────────────────────────────────────
def main():
    print_header()

    # Run checks in order
    backend_ok = check_backend()
    if backend_ok is not None:
        check_account()
        check_bots()
        check_positions()
        check_trades()
        check_stats()
        check_research()
    else:
        # Backend is down — record remaining critical checks as failed
        log("Account check", FAIL, "skipped — backend unavailable", critical=True)
        log("Bots check", FAIL, "skipped — backend unavailable", critical=True)
        print()
        print(f"  {RED}{BOLD}⚠  Backend is DOWN — most checks could not run.{RESET}")

    exit_code = print_summary()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
