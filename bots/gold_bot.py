#!/usr/bin/env python3
"""
XAUUSD Session Range Breakout Bot (M5)

Run: python gold_bot.py

Prerequisites:
  - MetaTrader 5 terminal open, logged in, Algo Trading enabled
  - Symbol XAUUSD visible in Market Watch
  - pip install -r requirements.txt

Demo checklist:
  1. Terminal closed -> retry logs every 30s
  2. Verify logged broker UTC offset at startup
  3. Restart after range freeze -> same pre_high/pre_low
  4. Restart after trade -> no second entry same UTC day
  5. Entry -> SL ~1.5*ATR, TP ~3.0*ATR
  6. Open position at 20:00 UTC -> market close
  7. No invalid filling (retcode 10030)
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import MetaTrader5 as mt5

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M5
MAGIC = 999111
ORDER_COMMENT = "SRB_XAU"

PRE_MARKET_START_UTC = (6, 0)
PRE_MARKET_END_UTC = (8, 0)
TRADE_START_UTC = (8, 1)
TRADE_END_UTC = (20, 0)

ATR_PERIOD = 14
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.0

LOT_SIZE = 0.01
DEVIATION = 20
MAX_SPREAD_POINTS = 500

STATUS_LOG_INTERVAL_SEC = 10
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
OFFSET_REVALIDATE_SEC = 3600
RATES_BARS = 200

STATE_FILE = "logs/gold_bot_state.json"
LOG_FILE = "logs/gold_execution.log"

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2
SYMBOL_FILLING_RETURN = 4

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

logger = logging.getLogger("gold_bot")
_broker_offset_sec: float = 0.0
_last_offset_check: float = 0.0
_last_bar_time: int = 0
_last_status_log: float = 0.0
_state: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)


# ---------------------------------------------------------------------------
# Persistent state
# ---------------------------------------------------------------------------


def default_state() -> dict[str, Any]:
    today = today_utc_date().isoformat()
    return {
        "trade_date": today,
        "trade_taken": False,
        "trade_side": None,
        "pre_high": None,
        "pre_low": None,
        "range_date": today,
        "range_frozen": False,
    }


def load_state() -> dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return default_state()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        base = default_state()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("State load failed (%s); using defaults", exc)
        return default_state()


def save_state() -> None:
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except OSError as exc:
        logger.error("State save failed: %s", exc)


def reset_state_for_new_utc_day() -> None:
    today = today_utc_date().isoformat()
    if _state.get("trade_date") == today and _state.get("range_date") == today:
        return
    logger.info("New UTC day detected; resetting daily state")
    _state["trade_date"] = today
    _state["trade_taken"] = False
    _state["trade_side"] = None
    _state["range_date"] = today
    _state["pre_high"] = None
    _state["pre_low"] = None
    _state["range_frozen"] = False
    save_state()


# ---------------------------------------------------------------------------
# UTC / broker time
# ---------------------------------------------------------------------------


def today_utc_date() -> date:
    return datetime.now(timezone.utc).date()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def broker_ts_to_utc(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts - _broker_offset_sec, tz=timezone.utc)


def utc_to_broker_ts(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() + _broker_offset_sec)


def utc_time_on_date(d: date, hour: int, minute: int) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=timezone.utc)


def utc_in_time_range(dt: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    t = dt.hour * 60 + dt.minute
    start_m = start[0] * 60 + start[1]
    end_m = end[0] * 60 + end[1]
    return start_m <= t < end_m


def utc_at_or_after(dt: datetime, hour: int, minute: int) -> bool:
    return (dt.hour, dt.minute) >= (hour, minute)


def detect_broker_offset() -> float:
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        raise RuntimeError(f"No tick for {SYMBOL}: {mt5.last_error()}")
    utc_ts = datetime.now(timezone.utc).timestamp()
    return float(tick.time) - utc_ts


def revalidate_offset_if_needed() -> None:
    global _broker_offset_sec, _last_offset_check
    now = time.time()
    if now - _last_offset_check < OFFSET_REVALIDATE_SEC:
        return
    try:
        new_off = detect_broker_offset()
        drift = abs(new_off - _broker_offset_sec)
        if drift > 1800:
            logger.warning(
                "Broker offset drift %.0fs (was %.0fs, now %.0fs)",
                drift,
                _broker_offset_sec,
                new_off,
            )
        _broker_offset_sec = new_off
        _last_offset_check = now
    except Exception as exc:
        logger.warning("Offset revalidation failed: %s", exc)


# ---------------------------------------------------------------------------
# MT5 lifecycle
# ---------------------------------------------------------------------------


def init_mt5() -> bool:
    if not load_config():
        logger.warning(
            "No mt5_config.json — copy mt5_config.example.json and add login/password/server."
        )
    if connect_mt5():
        return True
    logger.error("MT5 connect failed: %s", mt5.last_error())
    return False


def ensure_symbol() -> bool:
    if not mt5.symbol_select(SYMBOL, True):
        logger.error("symbol_select failed for %s: %s", SYMBOL, mt5.last_error())
        return False
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        logger.error("symbol_info missing for %s", SYMBOL)
        return False
    if not info.visible:
        mt5.symbol_select(SYMBOL, True)
    mode = info.trade_mode
    if mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        logger.error("Symbol %s trading is disabled", SYMBOL)
        return False
    return True


def shutdown_mt5() -> None:
    mt5.shutdown()
    logger.info("MT5 shutdown complete")


def wait_for_mt5() -> None:
    while True:
        if init_mt5() and ensure_symbol():
            return
        logger.info("Retrying MT5 connection in %ss...", MT5_RETRY_SEC)
        time.sleep(MT5_RETRY_SEC)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def get_rates(count: int = RATES_BARS):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, count)
    if rates is None or len(rates) < 3:
        logger.warning("Insufficient rates: %s", mt5.last_error())
        return None
    return rates


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_atr_wilder(rates, period: int = ATR_PERIOD) -> Optional[float]:
    if len(rates) < period + 2:
        return None
    trs = []
    for i in range(1, len(rates)):
        prev_c = float(rates[i - 1]["close"])
        trs.append(true_range(float(rates[i]["high"]), float(rates[i]["low"]), prev_c))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def bars_in_pre_market_window(rates, day: date) -> list:
    start_dt = utc_time_on_date(day, *PRE_MARKET_START_UTC)
    end_dt = utc_time_on_date(day, *PRE_MARKET_END_UTC)
    selected = []
    for bar in rates:
        bar_utc = broker_ts_to_utc(bar["time"])
        if bar_utc.date() != day:
            continue
        if start_dt <= bar_utc < end_dt:
            selected.append(bar)
    return selected


def compute_range_from_bars(bars) -> tuple[Optional[float], Optional[float]]:
    if not bars:
        return None, None
    high = max(float(b["high"]) for b in bars)
    low = min(float(b["low"]) for b in bars)
    return high, low


def backfill_pre_market_range(day: date) -> tuple[Optional[float], Optional[float]]:
    rates = get_rates(RATES_BARS)
    if rates is None:
        return None, None
    bars = bars_in_pre_market_window(rates, day)
    if not bars:
        logger.warning("No pre-market bars for %s; cannot trade today", day)
        return None, None
    return compute_range_from_bars(bars)


def update_pre_market_range() -> None:
    global _state
    now = utc_now()
    day = now.date()
    if _state.get("range_date") != day.isoformat():
        _state["range_date"] = day.isoformat()
        _state["pre_high"] = None
        _state["pre_low"] = None
        _state["range_frozen"] = False

    if _state.get("range_frozen"):
        return

    if utc_at_or_after(now, *PRE_MARKET_END_UTC):
        if _state["pre_high"] is None or _state["pre_low"] is None:
            hi, lo = backfill_pre_market_range(day)
            if hi is None or lo is None:
                return
            _state["pre_high"] = hi
            _state["pre_low"] = lo
        _state["range_frozen"] = True
        logger.info(
            "Pre-market range FROZEN | high=%.5f low=%.5f",
            _state["pre_high"],
            _state["pre_low"],
        )
        save_state()
        return

    if not utc_in_time_range(now, PRE_MARKET_START_UTC, PRE_MARKET_END_UTC):
        return

    rates = get_rates(RATES_BARS)
    if rates is None:
        return
    bars = bars_in_pre_market_window(rates, day)
    hi, lo = compute_range_from_bars(bars)
    if hi is None or lo is None:
        return
    _state["pre_high"] = hi
    _state["pre_low"] = lo
    save_state()


def new_bar_closed() -> bool:
    global _last_bar_time
    rates = get_rates(5)
    if rates is None or len(rates) < 2:
        return False
    closed_time = int(rates[1]["time"])
    if closed_time == _last_bar_time:
        return False
    is_new = _last_bar_time != 0
    _last_bar_time = closed_time
    return is_new


def in_trade_window() -> bool:
    now = utc_now()
    if not utc_at_or_after(now, *TRADE_START_UTC):
        return False
    if utc_at_or_after(now, *TRADE_END_UTC):
        return False
    return True


def at_hard_close_time() -> bool:
    return utc_at_or_after(utc_now(), *TRADE_END_UTC)


# ---------------------------------------------------------------------------
# Positions & signals
# ---------------------------------------------------------------------------


def bot_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC]


def reconcile_trade_state() -> None:
    if bot_positions():
        if not _state.get("trade_taken"):
            logger.info("Reconciling: open bot position found; marking trade_taken=True")
            _state["trade_taken"] = True
            _state["trade_date"] = today_utc_date().isoformat()
            save_state()


def evaluate_signal() -> Optional[int]:
    if not _state.get("range_frozen"):
        return None
    if _state.get("trade_taken"):
        return None
    if not in_trade_window():
        return None
    if bot_positions():
        return None

    pre_high = _state.get("pre_high")
    pre_low = _state.get("pre_low")
    if pre_high is None or pre_low is None:
        return None

    rates = get_rates(50)
    if rates is None or len(rates) < 3:
        return None

    bar = rates[1]
    prev = rates[2]
    close = float(bar["close"])
    prev_close = float(prev["close"])

    if prev_close <= pre_high < close:
        logger.info(
            "BUY signal | prev_close=%.5f close=%.5f pre_high=%.5f",
            prev_close,
            close,
            pre_high,
        )
        return mt5.ORDER_TYPE_BUY

    if prev_close >= pre_low > close:
        logger.info(
            "SELL signal | prev_close=%.5f close=%.5f pre_low=%.5f",
            prev_close,
            close,
            pre_low,
        )
        return mt5.ORDER_TYPE_SELL

    return None


# ---------------------------------------------------------------------------
# Order execution
# ---------------------------------------------------------------------------


def get_filling_mode() -> int:
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    filling = info.filling_mode
    if filling & SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    if filling & SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if filling & SYMBOL_FILLING_RETURN:
        return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_IOC


def normalize_price(price: float, digits: int) -> float:
    return round(price, digits)


def normalize_volume(volume: float) -> float:
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return volume
    vol = max(info.volume_min, min(info.volume_max, volume))
    step = info.volume_step
    if step > 0:
        vol = round(vol / step) * step
    return round(vol, 2)


def adjust_stops(
    side: int,
    entry: float,
    sl: float,
    tp: float,
    stops_level: int,
    point: float,
    digits: int,
) -> tuple[float, float]:
    min_dist = stops_level * point
    if min_dist <= 0:
        return sl, tp
    if side == mt5.ORDER_TYPE_BUY:
        if entry - sl < min_dist:
            sl = entry - min_dist
        if tp - entry < min_dist:
            tp = entry + min_dist
    else:
        if sl - entry < min_dist:
            sl = entry + min_dist
        if entry - tp < min_dist:
            tp = entry - min_dist
    return normalize_price(sl, digits), normalize_price(tp, digits)


def spread_ok() -> bool:
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False
    return info.spread <= MAX_SPREAD_POINTS


def place_market_order(order_type: int, atr: float) -> bool:
    global _state
    if not spread_ok():
        logger.warning("Spread too wide; skipping entry")
        return False

    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)
    if tick is None or info is None:
        logger.error("Tick/symbol info unavailable")
        return False

    digits = info.digits
    point = info.point
    stops_level = max(info.trade_stops_level, getattr(info, "stops_level", 0) or 0)

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
        sl = price - ATR_SL_MULT * atr
        tp = price + ATR_TP_MULT * atr
        deal_type = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl = price + ATR_SL_MULT * atr
        tp = price - ATR_TP_MULT * atr
        deal_type = mt5.ORDER_TYPE_SELL

    sl, tp = adjust_stops(order_type, price, sl, tp, stops_level, point, digits)
    price = normalize_price(price, digits)
    volume = normalize_volume(LOT_SIZE)
    filling = get_filling_mode()

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": deal_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": ORDER_COMMENT,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    logger.info(
        "Sending %s | vol=%.2f price=%.5f sl=%.5f tp=%.5f atr=%.5f fill=%s",
        "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
        volume,
        price,
        sl,
        tp,
        atr,
        filling,
    )

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(
            "order_send failed retcode=%s comment=%s",
            result.retcode,
            result.comment,
        )
        return False

    logger.info("Order filled | ticket=%s deal=%s", result.order, result.deal)
    _state["trade_taken"] = True
    _state["trade_date"] = today_utc_date().isoformat()
    _state["trade_side"] = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    save_state()
    return True


def close_bot_positions() -> None:
    positions = bot_positions()
    if not positions:
        return
    filling = get_filling_mode()
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        logger.error("Cannot close: no tick")
        return

    for pos in positions:
        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": DEVIATION,
            "magic": MAGIC,
            "comment": ORDER_COMMENT + "_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(request)
        if result is None:
            logger.error("Close failed ticket=%s: %s", pos.ticket, mt5.last_error())
            continue
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                "Close failed ticket=%s retcode=%s %s",
                pos.ticket,
                result.retcode,
                result.comment,
            )
        else:
            logger.info("Hard close filled | ticket=%s", pos.ticket)


def try_execute_entry() -> None:
    order_type = evaluate_signal()
    if order_type is None:
        return
    rates = get_rates(50)
    if rates is None:
        return
    atr = compute_atr_wilder(rates, ATR_PERIOD)
    if atr is None or atr <= 0:
        logger.warning("ATR unavailable; skipping entry")
        return
    place_market_order(order_type, atr)


# ---------------------------------------------------------------------------
# Status logging
# ---------------------------------------------------------------------------


def log_status() -> None:
    tick = mt5.symbol_info_tick(SYMBOL)
    bid = tick.bid if tick else 0.0
    ask = tick.ask if tick else 0.0
    now = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    offset_h = _broker_offset_sec / 3600.0
    pre_h = _state.get("pre_high")
    pre_l = _state.get("pre_low")
    positions = bot_positions()
    pos_str = "FLAT"
    if positions:
        p = positions[0]
        pos_str = f"ticket={p.ticket} type={p.type} profit={p.profit:.2f} sl={p.sl} tp={p.tp}"

    logger.info(
        "STATUS | %s | bid=%.5f ask=%.5f | pre_high=%s pre_low=%s | frozen=%s "
        "trade_taken=%s | offset=%.2fh | %s",
        now,
        bid,
        ask,
        f"{pre_h:.5f}" if pre_h is not None else "—",
        f"{pre_l:.5f}" if pre_l is not None else "—",
        _state.get("range_frozen"),
        _state.get("trade_taken"),
        offset_h,
        pos_str,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def startup() -> None:
    global _broker_offset_sec, _last_offset_check, _state

    setup_logging()
    logger.info("Starting Session Range Breakout Bot | symbol=%s", SYMBOL)
    wait_for_mt5()

    _broker_offset_sec = detect_broker_offset()
    _last_offset_check = time.time()
    logger.info("Broker UTC offset detected: %.0f seconds (%.2f hours)", _broker_offset_sec, _broker_offset_sec / 3600)

    _state = load_state()
    reset_state_for_new_utc_day()
    reconcile_trade_state()
    update_pre_market_range()

    atexit.register(shutdown_mt5)


def run_loop() -> None:
    global _last_status_log

    while True:
        try:
            term = mt5.terminal_info()
            if term is None or not term.connected:
                logger.warning("Terminal disconnected; reconnecting...")
                mt5.shutdown()
                wait_for_mt5()
                revalidate_offset_if_needed()

            revalidate_offset_if_needed()
            reset_state_for_new_utc_day()
            update_pre_market_range()

            if at_hard_close_time():
                if bot_positions():
                    logger.info("20:00 UTC hard stop — closing bot positions")
                    close_bot_positions()

            now = time.time()
            if now - _last_status_log >= STATUS_LOG_INTERVAL_SEC:
                log_status()
                _last_status_log = now

            if new_bar_closed():
                try_execute_entry()

            time.sleep(LOOP_SLEEP_SEC)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — shutting down")
            break
        except Exception:
            logger.error("Loop error:\n%s", traceback.format_exc())
            time.sleep(LOOP_SLEEP_SEC)


def main() -> None:
    startup()
    try:
        run_loop()
    finally:
        shutdown_mt5()


if __name__ == "__main__":
    main()
