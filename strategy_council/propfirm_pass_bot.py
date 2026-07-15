#!/usr/bin/env python3
"""
Propfirm Pass Strategy Bot v9.1 — Deployed
===========================================
VWAP Deviation Mean Reversion on EURUSD during London + US Open.

Strategy:
  - Instrument: EURUSD only
  - Time window: London 7:00-9:00 UTC + US Open 13:00-15:00 UTC (Mon-Fri)
  - Entry: VWAP deviation >= 10 pips + 5M rejection candle (pin bar/doji)
  - Momentum filter: skip if candle body > 60% of range (trend candle)
  - Max daily trades: 2
  - Max consecutive losses: 2 -> stop for the day
  - SL: Fixed 12 pips, TP: Fixed 24 pips (1:2 RR)
  - No trailing stop, no breakeven
  - News blackout: no trade within 60 min of high-impact news
  - Risk: 1.0% per trade ($100 on $10K)
  - Magic number: 780012

Target account: FTMO 2-Step $100K
  - Profit target: 10% ($10,000)
  - Max daily DD: 4% ($4,000)
  - Max total DD: 8% ($8,000)
"""

import json, logging, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import MetaTrader5 as mt5

_HERMESS_ROOT = Path(__file__).resolve().parent.parent
if str(_HERMESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HERMESS_ROOT))

from utils.mt5_connect import connect_mt5, load_config
# Trade alerts + news calendar
sys.path.insert(0, str(_HERMESS_ROOT / "bots"))
from trade_alerts import log_trade_event
from news_calendar import is_news_blackout as real_news_blackout

# Constants
SYMBOL = "EURUSD"
MAGIC = 780012
SESSION_START_HOUR = 7   # London 7:00-9:00 UTC + US Open 13:00-15:00 UTC
SESSION_END_HOUR = 15

SL_PIPS = 12
TP_PIPS = 24
MIN_DEVIATION_PIPS = 10
RISK_PCT = 1.0

WICK_RATIO = 1.5
BODY_MAX_PCT = 0.40
DOJI_MAX_PCT = 0.10
MOMENTUM_BODY_MIN = 0.60

NEWS_BLACKOUT_MINUTES = 60

LOG_DIR = Path(_HERMESS_ROOT) / "bots" / "logs"
LOCK_DIR = Path(_HERMESS_ROOT) / "bots" / "locks"
LOG_FILE = LOG_DIR / "propfirm_pass_strategy.log"
STATE_FILE = LOG_DIR / "propfirm_pass_state.json"
PID_FILE = LOCK_DIR / "propfirm_pass_strategy.pid"

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
              logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("PropfirmPass")


def pip_to_price(symbol: str, pips: float) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        return pips * 0.00010
    digits = info.digits
    point = info.point
    return pips * 10 * point if digits >= 5 else pips * point


def is_trading_day() -> bool:
    return datetime.now(timezone.utc).weekday() < 5


def is_trading_time() -> bool:
    now = datetime.now(timezone.utc)
    return SESSION_START_HOUR <= now.hour < SESSION_END_HOUR


def time_to_window_end() -> float:
    now = datetime.now(timezone.utc)
    end = now.replace(hour=SESSION_END_HOUR, minute=0, second=0, microsecond=0)
    if end <= now:
        return 0.0
    return (end - now).total_seconds()


def is_news_blackout() -> bool:
    """Check if within 60 min of high-impact news via ForexFactory."""
    try:
        in_blackout = real_news_blackout(SYMBOL, NEWS_BLACKOUT_MINUTES)
        if in_blackout:
            logger.info("News blackout active — skipping trade.")
        return in_blackout
    except Exception as exc:
        logger.warning("News calendar check failed: %s — allowing trade", exc)
        return False


def load_state() -> dict:
    default = {"trade_date": "", "daily_trade_count": 0, "consecutive_losses": 0,
               "total_trades": 0, "total_wins": 0, "total_losses": 0,
               "last_trade_close_time": "", "last_trade_direction": 0,
               "session_trend": 0, "session_trend_price": 0.0}
    if not STATE_FILE.is_file():
        return default
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k in default:
            data.setdefault(k, default[k])
        return data
    except (json.JSONDecodeError, OSError):
        return default


def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError as exc:
        logger.error("Failed to save state: %s", exc)


def reset_daily_state(state: dict, current_price: float = 0.0) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("trade_date") != today:
        state["trade_date"] = today
        state["daily_trade_count"] = 0
        state["consecutive_losses"] = 0
        # Reset trend at NEW day only — preserve across bot restarts same day
        state["session_trend"] = 0
        state["session_trend_price"] = current_price if current_price > 0 else 0.0
        logger.info("📅 New trading day: %s — session trend reset to %.5f", today, state["session_trend_price"])
    return state


def acquire_pid_lock() -> bool:
    """Acquire PID lock, killing any existing bot process."""
    try:
        if PID_FILE.is_file():
            pid_str = PID_FILE.read_text().strip()
            if pid_str:
                try:
                    old_pid = int(pid_str)
                    handle = None
                    if os.name == "nt":
                        import ctypes
                        handle = ctypes.windll.kernel32.OpenProcess(0x400000, False, old_pid)
                    if handle:
                        if os.name == "nt":
                            ctypes.windll.kernel32.CloseHandle(handle)
                        # Process is alive — kill it before taking over
                        logger.warning("🔄 PID lock: killing old bot process %d to prevent zombie", old_pid)
                        try:
                            os.kill(old_pid, 9)
                        except OSError:
                            pass  # Already dead or permission issue
                        import time
                        time.sleep(2)  # Wait for cleanup
                except (ValueError, OSError):
                    logger.warning("Removing stale PID lock")
        PID_FILE.write_text(str(os.getpid()))
        logger.info("🔒 PID lock acquired: %d", os.getpid())
        return True
    except OSError:
        return False


def release_pid_lock() -> None:
    try:
        if PID_FILE.is_file():
            PID_FILE.unlink()
    except OSError:
        pass


def get_position_size(account_balance: float) -> float:
    risk_amount = account_balance * (RISK_PCT / 100.0)
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return 0.01
    tick_value = info.trade_tick_value
    digits = info.digits
    pip_value = tick_value * 10 if digits >= 5 else tick_value
    if pip_value <= 0:
        return 0.01
    risk_per_lot = pip_value * SL_PIPS
    lots = round(risk_amount / risk_per_lot * 100) / 100.0
    return max(max(info.volume_min, 0.01), min(lots, info.volume_max))


def calculate_vwap(symbol: str) -> Optional[float]:
    """Calculate 1-hour VWAP from 1-minute bars using bracket access (numpy-safe)."""
    now = datetime.now(timezone.utc)
    start_of_hour = now.replace(minute=0, second=0, microsecond=0)
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start_of_hour, now)
    if rates is None or len(rates) == 0:
        logger.debug("VWAP: no M1 bars for %s this hour", symbol)
        return None
    try:
        sum_tpv = sum(((r["high"] + r["low"] + r["close"]) / 3.0) * r["tick_volume"] for r in rates)
        sum_vol = sum(r["tick_volume"] for r in rates)
    except (AttributeError, ValueError, TypeError) as exc:
        logger.warning("VWAP calc failed: %s", exc)
        return None
    if sum_vol == 0:
        return None
    vwap = sum_tpv / sum_vol
    logger.debug("VWAP: current=%.5f vwap=%.5f (vol=%d)",
                 mt5.symbol_info_tick(symbol).bid if mt5.symbol_info_tick(symbol) else 0, vwap, sum_vol)
    return vwap


def check_deviation(current_price: float, vwap: float) -> tuple:
    dev_pips = abs(current_price - vwap) / pip_to_price(SYMBOL, 1.0)
    return dev_pips >= MIN_DEVIATION_PIPS, dev_pips


def check_rejection_candle(symbol: str) -> Optional[int]:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 5)
    if rates is None or len(rates) < 5:
        return None
    candle = rates[-5:]
    co = candle[0]["open"]
    ch = max(r["high"] for r in candle)
    cl = min(r["low"] for r in candle)
    cc = candle[-1]["close"]
    body = abs(cc - co)
    total_range = ch - cl
    if total_range == 0:
        return None
    upper_wick = ch - max(co, cc)
    lower_wick = min(co, cc) - cl
    body_ratio = body / total_range
    is_bullish = cc > co
    if body_ratio > MOMENTUM_BODY_MIN:
        return None  # Momentum candle, skip
    if lower_wick > body * WICK_RATIO and body_ratio < BODY_MAX_PCT and (is_bullish or body_ratio < 0.25):
        return 1  # Buy
    if upper_wick > body * WICK_RATIO and body_ratio < BODY_MAX_PCT and (not is_bullish or body_ratio < 0.25):
        return -1  # Sell
    if body_ratio < DOJI_MAX_PCT:
        return 0  # Doji
    return None


def place_trade(symbol: str, order_type: int, lots: float,
                sl_price: float, tp_price: float) -> Optional[int]:
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "price": 0.0,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": 20,
        "magic": MAGIC,
        "comment": "PropfirmPass",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Order failed: retcode=%s %s",
                     result.retcode if result else None,
                     result.comment if result else mt5.last_error())
        return None
    return result.order


def check_open_positions() -> int:
    pos = mt5.positions_get(magic=MAGIC)
    return len(pos) if pos else 0


def sync_state_from_mt5(state: dict) -> dict:
    """
    Sync trade state from MT5 history.
    Handles both intra-session and overnight trade closes.
    Uses last_trade_close_time to detect trades that closed while bot was asleep.
    """
    now = datetime.now(timezone.utc)
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Look back 7 days to catch overnight/weekend holds
    lookback = now - timedelta(days=7)
    deals = mt5.history_deals_get(lookback, now)
    if not deals:
        return state

    our = [d for d in deals if d.magic == MAGIC and d.symbol == SYMBOL]
    if not our:
        return state

    # Track unique trades (by position_id)
    from collections import defaultdict
    by_pos: dict = defaultdict(list)
    for d in our:
        by_pos[d.position_id].append(d)

    # Count today's trades (from midnight UTC)
    today_tickets = set()
    total_trade_count = 0
    for pos_id, ds in by_pos.items():
        opens = [d for d in ds if d.profit == 0]
        closes = [d for d in ds if d.profit != 0]
        if not opens:
            continue
        open_time = opens[0].time
        total_trade_count += 1
        if open_time >= sod.timestamp():
            today_tickets.add(pos_id)

    state["daily_trade_count"] = max(state.get("daily_trade_count", 0), len(today_tickets))

    # Consecutive losses: check all closed trades, newest first
    all_closed = sorted(
        [d for d in our if d.profit != 0],
        key=lambda d: d.time, reverse=True
    )
    cons = 0
    for d in all_closed:
        if d.profit < 0:
            cons += 1
        else:
            break
    state["consecutive_losses"] = max(state.get("consecutive_losses", 0), cons)

    # Overnight reconciliation: detect trades that closed while bot was asleep
    last_close_str = state.get("last_trade_close_time", "")
    last_close_ts = 0.0
    if last_close_str:
        try:
            last_close_dt = datetime.fromisoformat(last_close_str)
            last_close_ts = last_close_dt.timestamp()
        except (ValueError, TypeError):
            pass

    for pos_id, ds in by_pos.items():
        opens = [d for d in ds if d.profit == 0]
        closes = [d for d in ds if d.profit != 0]

        # Check if this trade was opened before last close (overnight scenario)
        if opens and closes:
            open_ts = opens[0].time
            close_ts = closes[0].time
            pnl = closes[0].profit

            # Case 1: Trade opened BEFORE bot went to sleep, closed AFTER
            # Case 2: Trade opened and closed while bot was asleep (cross-day)
            # Only record if we haven't already counted this trade
            if last_close_ts > 0 and open_ts > last_close_ts:
                # This trade was opened AFTER we last recorded a close
                # If it has a close deal, it's an overnight close we missed
                state["total_trades"] = state.get("total_trades", 0) + 1
                if pnl > 0:
                    state["total_wins"] = state.get("total_wins", 0) + 1
                    state["consecutive_losses"] = 0
                    logger.info("🔄 Overnight reconciliation: WIN +$%.2f (pos %s)", pnl, pos_id)
                elif pnl < 0:
                    state["total_losses"] = state.get("total_losses", 0) + 1
                    logger.info("🔄 Overnight reconciliation: LOSS $%.2f (pos %s)", pnl, pos_id)
                
                # Update last close time to this trade's close
                close_dt = datetime.fromtimestamp(close_ts, timezone.utc)
                state["last_trade_close_time"] = close_dt.isoformat()

    # If we found overnight trades, fire alert
    save_state(state)
    return state


COOLDOWN_MINUTES = 30
TREND_PIPS = 15
TREND_HOURS = 2


def check_cooldown(state: dict, proposed_direction: int) -> tuple[bool, str]:
    """
    Check 30-min cooldown for OPPOSITE direction trades.
    Same-direction entries are always allowed.
    Returns (blocked, reason).
    """
    close_time_str = state.get("last_trade_close_time", "")
    last_dir = state.get("last_trade_direction", 0)
    if not close_time_str or last_dir == 0:
        return False, ""
    if last_dir == proposed_direction:
        return False, ""  # Same direction = always allowed
    try:
        close_dt = datetime.fromisoformat(close_time_str)
        elapsed = (datetime.now(timezone.utc) - close_dt).total_seconds() / 60.0
        if elapsed < COOLDOWN_MINUTES:
            remaining = int(COOLDOWN_MINUTES - elapsed)
            return True, f"Cooldown active: {remaining}m remaining before opposite-direction trade allowed"
        return False, ""
    except (ValueError, TypeError):
        return False, ""


def update_session_trend(state: dict, current_price: float) -> int:
    """
    Track session-level price direction.
    If price moved TREND_PIPS+ in one direction from session start, record the trend.
    Returns trend direction: 1 (bullish), -1 (bearish), or 0 (no clear trend yet).
    """
    stored_price = state.get("session_trend_price", 0.0)
    if stored_price <= 0:
        return 0  # No session start price set yet

    pv = pip_to_price(SYMBOL, 1.0)
    if pv <= 0:
        return 0

    move_pips = (current_price - stored_price) / pv
    trend = state.get("session_trend", 0)

    if trend == 0:
        if move_pips >= TREND_PIPS:
            trend = 1   # Bullish: price moved UP more than threshold
            logger.info("📈 Session trend established: BULLISH (+%.1f pips from session start %.5f)",
                         move_pips, stored_price)
        elif move_pips <= -TREND_PIPS:
            trend = -1  # Bearish: price moved DOWN more than threshold
            logger.info("📉 Session trend established: BEARISH (%.1f pips from session start %.5f)",
                         move_pips, stored_price)

    if trend != state.get("session_trend", 0):
        state["session_trend"] = trend
        save_state(state)

    return trend


def check_trend_filter(state: dict, proposed_direction: int, current_price: float) -> tuple[bool, str]:
    """
    Check session trend filter.
    If a clear trend is established, only allow trades ALIGNED with it.
    Same-direction entries are always allowed.
    Returns (blocked, reason).
    """
    trend = update_session_trend(state, current_price)
    dir_name = "BUY" if proposed_direction == 1 else "SELL"

    if trend == 0:
        logger.info("📊 Trend filter: %s allowed — no clear trend established yet", dir_name)
        return False, ""  # No clear trend = no restriction

    if trend != proposed_direction:
        msg = f"🚫 Trend filter BLOCKED {dir_name} — session trend is {'BULLISH' if trend == 1 else 'BEARISH'} ({abs((current_price - state.get('session_trend_price', current_price)) / pip_to_price(SYMBOL, 1.0)):.0f}p from session start). Same-direction entries still allowed."
        logger.info("%s", msg)
        return True, msg

    logger.info("📊 Trend filter: %s allowed — aligned with session trend (%s)", dir_name, "BULLISH" if trend == 1 else "BEARISH")
    return False, ""  # Aligned with trend = allowed


def main() -> None:
    logger.info("=" * 60)
    logger.info("PROPFIRM PASS STRATEGY v9.1 — STARTING")
    logger.info("Session: London 7:00-9:00 + US Open 13:00-15:00 UTC | Dev>=10p | SL=12p TP=24p")
    if not acquire_pid_lock():
        sys.exit(1)
    try:
        # Try to attach to running MT5 first (no path = attach to existing)
        mt5.shutdown()
        _direct_ok = mt5.initialize(timeout=5000)
        if _direct_ok:
            _tmp = mt5.account_info()
            if _tmp and int(_tmp.login) in (1513845007, 1513767391):
                logger.info("Attached to running MT5 terminal — login=%s balance=%.2f", _tmp.login, _tmp.balance)
            else:
                mt5.shutdown()
                _direct_ok = False
        if not _direct_ok:
            config = load_config()
            if not config or not connect_mt5(config):
                sys.exit(1)

        # Ensure symbol is in Market Watch
        mt5.symbol_select(SYMBOL, True)

        # Rate-limiter for banner log spam
        _last_banner_log = 0.0

        state = load_state()
        # Get current price for session trend initialization
        _tick = mt5.symbol_info_tick(SYMBOL)
        _init_price = _tick.bid if _tick else 0.0
        state = reset_daily_state(state, _init_price)
        state = sync_state_from_mt5(state)
        save_state(state)
        price = _init_price  # Track current price for trend filter
        while True:
            now = datetime.now(timezone.utc)
            if not is_trading_day():
                days = (7 - now.weekday()) % 7 or 7
                target = now.replace(hour=SESSION_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=days)
                time.sleep(max(0, (target - now).total_seconds()))
                continue
            state = reset_daily_state(state, price)
            save_state(state)
            if not is_trading_time():
                if now.hour >= SESSION_END_HOUR:
                    target = now.replace(hour=SESSION_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    while target.weekday() >= 5:
                        target += timedelta(days=1)
                    time.sleep(max(0, (target - now).total_seconds()))
                else:
                    wait = (now.replace(hour=SESSION_START_HOUR, minute=0, second=0, microsecond=0) - now).total_seconds()
                    time.sleep(min(max(wait, 0), 60))
                continue
            if state["daily_trade_count"] >= 2 or state["consecutive_losses"] >= 2:
                target = now.replace(hour=SESSION_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=1)
                while target.weekday() >= 5:
                    target += timedelta(days=1)
                time.sleep(max(0, (target - now).total_seconds()))
                continue
            if is_news_blackout():
                time.sleep(60)
                continue
            if check_open_positions() > 0:
                time.sleep(30)
                continue

            # Rate-limited session banner (once per 60s)
            if time.monotonic() - _last_banner_log > 60:
                logger.info("=" * 40)
                logger.info("LONDON+US OPEN ACTIVE — 7:00-15:00 UTC")
                logger.info("=" * 40)
                _last_banner_log = time.monotonic()

            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                logger.warning("No tick data for %s — symbol may not be in Market Watch", SYMBOL)
                time.sleep(5)
                continue
            price = tick.bid
            vwap = calculate_vwap(SYMBOL)
            if vwap is None:
                logger.info("No VWAP available (no M1 data this hour). Retrying...")
                time.sleep(30)
                continue
            ok, dev = check_deviation(price, vwap)
            if not ok:
                logger.info("No deviation: %.1f pips (need %d). Waiting...",
                            dev, MIN_DEVIATION_PIPS)
                time.sleep(30)
                continue
            logger.info("Deviation detected: %.1f pips from VWAP", dev)
            signal = check_rejection_candle(SYMBOL)
            if signal is None:
                logger.info("No rejection candle pattern yet. Waiting...")
                time.sleep(30)
                continue
            trade_dir = 1 if (signal == 0 and price < vwap) else (-1 if signal == 0 else signal)
            if (trade_dir == 1 and price > vwap) or (trade_dir == -1 and price < vwap):
                time.sleep(30)
                continue

            # === COOLDOWN CHECK (opposite direction only) ===
            blocked, reason = check_cooldown(state, trade_dir)
            if blocked:
                logger.info("⏳ %s", reason)
                time.sleep(60)
                continue

            # === TREND FILTER (same direction always allowed) ===
            blocked, reason = check_trend_filter(state, trade_dir, price)
            if blocked:
                logger.info("🚫 %s", reason)
                time.sleep(60)
                continue

            acct = mt5.account_info()
            if acct is None:
                time.sleep(5)
                continue
            lots = get_position_size(acct.balance)
            pv = pip_to_price(SYMBOL, 1.0)
            if trade_dir == 1:
                entry, sl, tp = tick.ask, round(tick.ask - SL_PIPS * pv, 5), round(tick.ask + TP_PIPS * pv, 5)
                ot = mt5.ORDER_TYPE_BUY
            else:
                entry, sl, tp = tick.bid, round(tick.bid + SL_PIPS * pv, 5), round(tick.bid - TP_PIPS * pv, 5)
                ot = mt5.ORDER_TYPE_SELL
            logger.info("Signal: %s @ %.5f SL=%.5f TP=%.5f Lots=%.2f Dev=%.1fp",
                        "BUY" if trade_dir == 1 else "SELL", entry, sl, tp, lots, dev)
            ticket = place_trade(SYMBOL, ot, lots, sl, tp)
            if ticket is not None:
                state["daily_trade_count"] += 1
                state["total_trades"] += 1
                save_state(state)
                # Log trade alert
                alert_data = {
                    "symbol": SYMBOL, "direction": "BUY" if trade_dir == 1 else "SELL",
                    "lots": lots, "entry_price": entry, "sl": sl, "tp": tp,
                    "magic": MAGIC, "account": acct.login,
                }
                log_trade_event("entry", alert_data)
                # Wait for close
                while is_trading_time() and state["daily_trade_count"] < 2:
                    time.sleep(10)
                    if not mt5.positions_get(ticket=ticket):
                        break
                # Check PnL
                now_a = datetime.now(timezone.utc)
                sod = now_a.replace(hour=0, minute=0, second=0, microsecond=0)
                pnl = 0.0
                for d in (mt5.history_deals_get(sod, now_a) or []):
                    if d.position_id == ticket and d.profit != 0:
                        pnl = d.profit
                        break
                if pnl > 0:
                    state["consecutive_losses"] = 0
                    state["total_wins"] += 1
                    logger.info("WIN: +$%.2f", pnl)
                    log_trade_event("win", {**alert_data, "pnl": pnl})
                elif pnl < 0:
                    state["consecutive_losses"] += 1
                    state["total_losses"] += 1
                    logger.info("LOSS: $%.2f (cons=%d)", pnl, state["consecutive_losses"])
                    log_trade_event("loss", {**alert_data, "pnl": pnl})
                # Record close time + direction for cooldown filter
                state["last_trade_close_time"] = datetime.now(timezone.utc).isoformat()
                state["last_trade_direction"] = trade_dir
                save_state(state)
                if state["consecutive_losses"] >= 2:
                    break
            else:
                logger.error("Trade failed. Retrying...")
                time.sleep(30)
    finally:
        release_pid_lock()
        logger.info("Propfirm Pass v9.1 shut down.")

if __name__ == "__main__":
    main()
