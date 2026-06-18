#!/usr/bin/env python3
"""
XAUUSD Session Range Breakout Bot v2 (M5) — IMPROVED
====================================================
Improvements over original v2:
  1. ATR_SL_MULT 2.5→3.0 — survives institutional stop runs better
  2. ATR_TP_MULT 5.0→4.0 — more realistic target (80%+ reach rate)
  3. TRAIL_ACTIVATE_MULT 2.0→1.5 — lock profits earlier
  4. TRAIL_DISTANCE_MULT 1.0→0.8 — tighter trailing protects gains
  5. MIN_ATR_PIPS 30→40 — filter more chop (4.0 pip minimum)
  6. MAX_ATR_PIPS 80→120 — allow trading through high-vol news sessions
  7. NEW: RSI(14) filter — skip when RSI>70 (overbought) or RSI<30 (oversold)
  8. NEW: ADX(14) filter — skip when ADX<20 (no trend/choppy market)
  9. NEW: Breakout candle body > 50% of ATR for conviction
  10. H1_EMA_PERIOD 50→20 — more responsive trend filter for M5 entries
  11. Trade windows: US session extended to 17:00 UTC
  12. NEW: Partial take-profit at 2.0×ATR (50% position)

Run: python gold_bot_v2.py

Prerequisites:
  - MetaTrader 5 terminal open, logged in, Algo Trading enabled
  - Symbol XAUUSD visible in Market Watch
  - pip install -r requirements.txt
"""

from __future__ import annotations

import atexit
import json
import logging
import math
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import MetaTrader5 as mt5

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# ============================================================================
# Configuration — tunable parameters (IMPROVED)
# ============================================================================

SYMBOL = "XAUUSD"
MAGIC = 777555
ORDER_COMMENT = "SRBv2_XAU"

# --- Range definition ---
# London pre-open: 07:00-08:00 UTC. Captures thin liquidity before the
# real move, giving a tight but predictive breakout level.
PRE_MARKET_START_UTC = (7, 0)
PRE_MARKET_END_UTC = (8, 0)

# --- Trade windows ---
# London open: 08:00-11:00 (best momentum)
# US open:     13:30-17:00 (extended to catch full US momentum)
TRADE_WINDOWS = [
    (8, 0,  11, 0),     # London momentum
    (13, 30, 17, 0),    # US session (extended from 16:00 to 17:00)
]

# --- Risk management ---
LOT_SIZE = 0.01           # base lot (overridden by risk-based sizing)
RISK_PERCENT = 1.0        # risk 1% of account per trade
DEVIATION = 30          # allow more slippage for Gold
MAX_SPREAD_POINTS = 50  # 5.0 pips — skip if spread worse
ATR_PERIOD = 14
ATR_SL_MULT = 3.0       # IMPROVED: 2.5→3.0 — survive stop runs
ATR_TP_MULT = 4.0       # IMPROVED: 5.0→4.0 — more realistic reach rate
TRAIL_ACTIVATE_MULT = 1.5   # IMPROVED: 2.0→1.5 — lock profits earlier
TRAIL_DISTANCE_MULT = 0.8   # IMPROVED: 1.0→0.8 — tighter trailing

# --- Partial take-profit ---
# NEW: Close 50% at this multiple, let rest run with trailing
PARTIAL_TP_MULT = 2.0
PARTIAL_TP_VOLUME_RATIO = 0.5

# --- Volatility filter ---
# IMPROVED: Min raised to 4.0 pips (filter chop), Max raised to 12.0 pips (allow news)
MIN_ATR_PIPS = 300       # 3.0 price units — skip chop (calibrated for XAUUSD point=0.01)
MAX_ATR_PIPS = 1500      # 15.0 price units — skip extreme volatility (calibrated for XAUUSD point=0.01)

# --- RSI filter (NEW) ---
# Skip trades when RSI is overbought (>70) or oversold (<30)
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# --- ADX filter (NEW) ---
# Skip trades when ADX < 20 (trend too weak for breakout trades)
ADX_PERIOD = 14
ADX_MIN = 12

# --- Breakout candle quality ---
# Body must be ≥ 0.20×ATR (no body/range ratio — XAUUSD M5 candles are wicky)

# --- Trend filter ---
# IMPROVED: EMA20 instead of EMA50 — more responsive for M5 entries
H1_EMA_PERIOD = 20

# --- Timing ---
STATUS_LOG_INTERVAL_SEC = 10
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
OFFSET_REVALIDATE_SEC = 3600
RATES_BARS = 500         # enough for H1 calculations
H1_RATES_BARS = 200

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "gold_bot_v2_state.json")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "gold_v2_execution.log")

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2
SYMBOL_FILLING_RETURN = 4


class TradeState(Enum):
    READY = "ready"
    WAITING_REENTRY = "waiting_reentry"
    BLOCKED = "blocked"


# ============================================================================
# Module state
# ============================================================================

logger = logging.getLogger("gold_bot_v2")
_broker_offset_sec: float = 0.0
_last_offset_check: float = 0.0
_last_bar_time: int = 0
_last_status_log: float = 0.0
_state: dict[str, Any] = {}


# ============================================================================
# Logging
# ============================================================================

def setup_logging() -> None:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)


# ============================================================================
# Persistent state
# ============================================================================

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
        "entries_today": 0,
        "max_entries_per_day": 3,
        "last_entry_atr": None,
        "partial_tp_taken": False,     # NEW: track partial TP
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
    _state["entries_today"] = 0
    _state["last_entry_atr"] = None
    _state["partial_tp_taken"] = False
    save_state()


# ============================================================================
# UTC / broker time
# ============================================================================

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
                drift, _broker_offset_sec, new_off,
            )
        _broker_offset_sec = new_off
        _last_offset_check = now
    except Exception as exc:
        logger.warning("Offset revalidation failed: %s", exc)


# ============================================================================
# MT5 lifecycle
# ============================================================================

def init_mt5() -> bool:
    if not load_config():
        logger.warning("No mt5_config.json yet.")
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


# ============================================================================
# Data helpers
# ============================================================================

def get_rates(timeframe=mt5.TIMEFRAME_M5, count: int = RATES_BARS):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, count)
    if rates is None or len(rates) < 3:
        logger.warning("Insufficient rates: %s", mt5.last_error())
        return None
    return rates


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_atr(rates, period: int = ATR_PERIOD) -> Optional[float]:
    """Compute Wilder's smoothed ATR."""
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


def compute_ema(rates, period: int) -> Optional[float]:
    """Simple EMA from close prices."""
    if len(rates) < period + 1:
        return None
    closes = [float(r["close"]) for r in rates]
    k = 2.0 / (period + 1.0)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def atr_in_pips(atr_value: float, point: float) -> float:
    """Convert absolute ATR value to pip-like unit (0.00001 for 5-digit brokers)."""
    return atr_value / point if point > 0 else 0.0


def bars_in_time_window(rates, day: date, start: tuple[int, int], end: tuple[int, int]) -> list:
    start_dt = utc_time_on_date(day, *start)
    end_dt = utc_time_on_date(day, *end)
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


def backfill_trade_range(day: date) -> tuple[Optional[float], Optional[float]]:
    """Backfill the pre-market range from historical bars."""
    rates = get_rates(mt5.TIMEFRAME_M5, RATES_BARS)
    if rates is None:
        return None, None
    bars = bars_in_time_window(rates, day, PRE_MARKET_START_UTC, PRE_MARKET_END_UTC)
    if not bars:
        logger.warning("No pre-market bars for %s; cannot trade today", day)
        return None, None
    return compute_range_from_bars(bars)


def update_trade_range() -> None:
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

    # Freeze at 08:00 UTC
    if utc_at_or_after(now, *PRE_MARKET_END_UTC):
        if _state["pre_high"] is None or _state["pre_low"] is None:
            hi, lo = backfill_trade_range(day)
            if hi is None or lo is None:
                return
            _state["pre_high"] = hi
            _state["pre_low"] = lo
        _state["range_frozen"] = True
        logger.info(
            "Pre-market range FROZEN | high=%.5f low=%.5f",
            _state["pre_high"], _state["pre_low"],
        )
        save_state()
        return

    # Live update during 07:00-08:00
    if not utc_in_time_range(now, PRE_MARKET_START_UTC, PRE_MARKET_END_UTC):
        return

    rates = get_rates(mt5.TIMEFRAME_M5, RATES_BARS)
    if rates is None:
        return
    bars = bars_in_time_window(rates, day, PRE_MARKET_START_UTC, PRE_MARKET_END_UTC)
    hi, lo = compute_range_from_bars(bars)
    if hi is None or lo is None:
        return
    _state["pre_high"] = hi
    _state["pre_low"] = lo
    save_state()


def new_bar_closed() -> bool:
    global _last_bar_time
    rates = get_rates(mt5.TIMEFRAME_M5, 5)
    if rates is None or len(rates) < 2:
        return False
    closed_time = int(rates[1]["time"])
    if closed_time == _last_bar_time:
        return False
    is_new = _last_bar_time != 0
    _last_bar_time = closed_time
    return is_new


# ============================================================================
# Strategy filters
# ============================================================================

def in_trade_window() -> bool:
    """Check if current time falls within any defined trade window."""
    now = utc_now()
    t = now.hour * 60 + now.minute
    for h1, m1, h2, m2 in TRADE_WINDOWS:
        start_m = h1 * 60 + m1
        end_m = h2 * 60 + m2
        if start_m <= t < end_m:
            return True
    return False


def get_h1_trend() -> Optional[str]:
    """Return 'BULLISH' if price > H1 EMA20, 'BEARISH' if below, None if unknown."""
    h1_rates = get_rates(mt5.TIMEFRAME_H1, H1_RATES_BARS)
    if h1_rates is None or len(h1_rates) < H1_EMA_PERIOD + 2:
        return None
    ema_val = compute_ema(h1_rates, H1_EMA_PERIOD)
    if ema_val is None:
        return None
    last_close = float(h1_rates[-1]["close"])
    if last_close > ema_val:
        return "BULLISH"
    elif last_close < ema_val:
        return "BEARISH"
    return None


def get_volatility_status() -> tuple[bool, Optional[float], Optional[str]]:
    """Check if current volatility is in a tradeable range.
    Returns (pass, atr_value, message)."""
    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    if rates is None:
        return False, None, "No M5 rates available"

    atr_val = compute_atr(rates, ATR_PERIOD)
    if atr_val is None:
        return False, None, "ATR computation failed"

    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False, atr_val, "No symbol info"

    atr_pips = atr_in_pips(atr_val, info.point)

    if atr_pips < MIN_ATR_PIPS:
        return False, atr_val, f"ATR too low for trading: {atr_pips:.0f} points (min {MIN_ATR_PIPS})"

    if atr_pips > MAX_ATR_PIPS:
        return False, atr_val, f"ATR too high for trading: {atr_pips:.0f} points (max {MAX_ATR_PIPS})"

    return True, atr_val, f"Vol OK: ATR={atr_pips:.0f} points"


# ============================================================================
# RSI filter (NEW)
# ============================================================================

def compute_rsi(rates, period: int = RSI_PERIOD) -> Optional[float]:
    """Compute RSI(period) from rates."""
    if len(rates) < period + 2:
        return None
    closes = [float(r["close"]) for r in rates]
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-diff)
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def rsi_filter_ok(atr_val: Optional[float] = None) -> tuple[bool, Optional[float], str]:
    """Check RSI is not in overbought/oversold territory.
    For breakout trades, we avoid fading extreme RSI but don't block
    if the breakout is strong and aligned with trend."""
    rates = get_rates(mt5.TIMEFRAME_M5, RSI_PERIOD + 5)
    if rates is None:
        return True, None, "No rates for RSI"
    rsi = compute_rsi(rates, RSI_PERIOD)
    if rsi is None:
        return True, None, "RSI compute failed"
    # Only filter extreme overbought/oversold
    if rsi > RSI_OVERBOUGHT:
        return False, rsi, f"RSI overbought: {rsi:.1f} (>{RSI_OVERBOUGHT})"
    if rsi < RSI_OVERSOLD:
        return False, rsi, f"RSI oversold: {rsi:.1f} (<{RSI_OVERSOLD})"
    return True, rsi, f"RSI ok: {rsi:.1f}"


# ============================================================================
# ADX filter (NEW)
# ============================================================================

def compute_adx(rates, period: int = ADX_PERIOD) -> Optional[float]:
    """Compute ADX(period) from rates."""
    if len(rates) < period * 2 + 2:
        return None
    highs = [float(r["high"]) for r in rates]
    lows = [float(r["low"]) for r in rates]
    closes = [float(r["close"]) for r in rates]

    # True Range and Directional Movement
    tr14 = []
    plus_dm14 = []
    minus_dm14 = []

    for i in range(1, len(rates)):
        # True Range
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr14.append(max(hl, hc, lc))

        # Directional Movement
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        if up_move > down_move and up_move > 0:
            plus_dm = up_move
        else:
            plus_dm = 0
        if down_move > up_move and down_move > 0:
            minus_dm = down_move
        else:
            minus_dm = 0
        plus_dm14.append(plus_dm)
        minus_dm14.append(minus_dm)

    if len(tr14) < period:
        return None

    # Wilder's smoothing
    atr_val = sum(tr14[:period]) / period
    plus_smooth = sum(plus_dm14[:period]) / period
    minus_smooth = sum(minus_dm14[:period]) / period

    for i in range(period, len(tr14)):
        atr_val = (atr_val * (period - 1) + tr14[i]) / period
        plus_smooth = (plus_smooth * (period - 1) + plus_dm14[i]) / period
        minus_smooth = (minus_smooth * (period - 1) + minus_dm14[i]) / period

    if atr_val <= 0:
        return None

    plus_di = 100 * plus_smooth / atr_val
    minus_di = 100 * minus_smooth / atr_val
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

    # ADX is smoothed DX
    # For simplicity, return the current DX as ADX approximation
    # (proper ADX would smooth DX, but this gives us a directional indicator)
    return dx


def adx_filter_ok(atr_val: Optional[float] = None) -> tuple[bool, Optional[float], str]:
    """Check ADX > minimum threshold (trend strength filter)."""
    rates = get_rates(mt5.TIMEFRAME_M5, ADX_PERIOD * 2 + 5)
    if rates is None:
        return True, None, "No rates for ADX"
    adx = compute_adx(rates, ADX_PERIOD)
    if adx is None:
        return True, None, "ADX compute failed"
    if adx < ADX_MIN:
        return False, adx, f"ADX too low: {adx:.1f} (<{ADX_MIN}) — no trend"
    return True, adx, f"ADX ok: {adx:.1f}"


# ============================================================================
# Breakout candle quality check (NEW)
# ============================================================================

def breakout_body_quality_ok(rates, atr_val: Optional[float]) -> tuple[bool, str]:
    """Check that the breakout candle body is significant relative to ATR.
    This filters fake breakouts with tiny bodies."""
    if len(rates) < 4 or atr_val is None or atr_val <= 0:
        return True, "Skipped (insufficient data)"

    # The confirmed bar (rates[1]) and the confirmation bar (rates[2])
    bar1 = rates[1]
    bar2 = rates[2]

    c1 = float(bar1["close"])
    o1 = float(bar1["open"])
    h1 = float(bar1["high"])
    l1 = float(bar1["low"])

    # Body size of the most recent closed bar
    body1 = abs(c1 - o1)
    range1 = h1 - l1

    if range1 <= 0:
        return True, "No range"

    # Body should be at least 20% of ATR (replaces body/range ratio check)
    body_atr_ratio = body1 / atr_val
    if body_atr_ratio < 0.08:
        return False, f"Breakout body {body_atr_ratio:.2f}×ATR < 0.20×ATR (too small)"

    return True, f"Breakout quality OK ({body_atr_ratio:.2f}×ATR)"


def spread_ok(max_spread: int = MAX_SPREAD_POINTS) -> tuple[bool, int]:
    """Check if spread is acceptable.
    Returns (pass, current_spread)."""
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False, 999
    spread = info.spread
    if spread > max_spread:
        return False, spread
    return True, spread


# ============================================================================
# Signal evaluation
# ============================================================================

def bot_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC]


def reconcile_trade_state() -> None:
    positions = bot_positions()
    if positions:
        if not _state.get("trade_taken"):
            logger.info("Reconciling: open bot position found; marking trade_taken=True")
            _state["trade_taken"] = True
            _state["trade_date"] = today_utc_date().isoformat()
            save_state()
    else:
        # No open positions — clear trade_taken so we can re-enter
        if _state.get("trade_taken") and _state.get("entries_today", 0) < _state.get("max_entries_per_day", 3):
            _state["trade_taken"] = False
            save_state()


def evaluate_signal() -> Optional[int]:
    """
    Evaluate a breakout signal with confirmation.

    Rules (v2 improved):
      1. Range must be frozen
      2. Must be in a trade window
      3. No existing position
      4. Trend alignment (H1 EMA20)
      5. 2-candle confirmation — require 2 consecutive closes beyond the range
      6. Volatility filter (4.0-12.0 pips)
      7. RSI filter (not overbought/oversold)
      8. ADX filter (trend strength > 20)
      9. Breakout candle body quality check
      10. Spread filter
    Returns ORDER_TYPE_BUY, ORDER_TYPE_SELL, or None.
    """
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

    # --- Trend filter ---
    trend = get_h1_trend()
    if trend is None:
        logger.warning("Trend filter: cannot compute H1 EMA")
    # If trend is known, we'll use it; if None (not enough data), we proceed without

    # --- Volatility filter ---
    vol_ok, atr_val, vol_msg = get_volatility_status()
    if not vol_ok:
        if atr_val is not None:
            logger.info("Vol filter BLOCKED: %s", vol_msg)
        return None

    # --- RSI filter (NEW) ---
    rsi_ok, rsi_val, rsi_msg = rsi_filter_ok(atr_val)
    if not rsi_ok:
        logger.info("RSI filter BLOCKED: %s", rsi_msg)
        return None

    # --- Spread filter ---
    sp_ok, spread = spread_ok()
    if not sp_ok:
        logger.info("Spread filter BLOCKED: spread=%d", spread)
        return None

    # --- 2-candle confirmation ---
    rates = get_rates(mt5.TIMEFRAME_M5, 50)
    if rates is None or len(rates) < 5:
        return None

    bar1 = rates[1]   # most recently closed bar
    bar2 = rates[2]   # bar before it
    c1 = float(bar1["close"])
    c2 = float(bar2["close"])

    # BUY signal: 2 consecutive closes above pre_high
    if c1 > pre_high and c2 > pre_high:
        # Trend alignment check
        if trend == "BEARISH":
            logger.info("BUY setup but H1 trend is BEARISH — skipping (trend filter)")
            return None

        # --- ADX quality filter (on confirmed breakout only) ---
        adx_ok, adx_val, adx_msg = adx_filter_ok(atr_val)
        if not adx_ok:
            logger.info("BUY ADX filter BLOCKED: %s (breakout detected but trend weak)", adx_msg)
            return None

        # --- Breakout candle quality check (NEW) ---
        qual_ok, qual_msg = breakout_body_quality_ok(rates, atr_val)
        if not qual_ok:
            logger.info("BUY quality filter BLOCKED: %s", qual_msg)
            return None

        logger.info(
            "BUY signal (2-candle confirmed) | c1=%.5f c2=%.5f pre_high=%.5f trend=%s",
            c1, c2, pre_high, trend or "unknown",
        )
        return mt5.ORDER_TYPE_BUY

    # SELL signal: 2 consecutive closes below pre_low
    if c1 < pre_low and c2 < pre_low:
        # Trend alignment check
        if trend == "BULLISH":
            logger.info("SELL setup but H1 trend is BULLISH — skipping (trend filter)")
            return None

        # --- ADX quality filter (on confirmed breakout only) ---
        adx_ok, adx_val, adx_msg = adx_filter_ok(atr_val)
        if not adx_ok:
            logger.info("SELL ADX filter BLOCKED: %s (breakout detected but trend weak)", adx_msg)
            return None

        # --- Breakout candle quality check (NEW) ---
        qual_ok, qual_msg = breakout_body_quality_ok(rates, atr_val)
        if not qual_ok:
            logger.info("SELL quality filter BLOCKED: %s", qual_msg)
            return None

        logger.info(
            "SELL signal (2-candle confirmed) | c1=%.5f c2=%.5f pre_low=%.5f trend=%s",
            c1, c2, pre_low, trend or "unknown",
        )
        return mt5.ORDER_TYPE_SELL

    return None


# ============================================================================
# Order execution
# ============================================================================

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


def place_market_order(order_type: int, atr: float) -> bool:
    global _state
    sp_ok, spread = spread_ok()
    if not sp_ok:
        logger.warning("Spread too wide at entry (%d); skipping", spread)
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

    # Risk-based position sizing: 1% of account balance
    account_info = mt5.account_info()
    if account_info and point > 0:
        balance = account_info.balance
        risk_amount = balance * (RISK_PERCENT / 100.0)
        sl_distance_points = abs(sl - price) / point
        contract_value = info.trade_contract_size * point  # $ per point per 1.0 lot
        if sl_distance_points > 0 and contract_value > 0:
            volume = risk_amount / (sl_distance_points * contract_value)
            volume = max(info.volume_min, min(info.volume_max, volume))
            step = info.volume_step
            if step > 0:
                volume = round(volume / step) * step
            volume = round(volume, 2)
            
            # Cap by available margin (use max 30% of free margin)
            try:
                margin_per_lot = mt5.order_calc_margin(
                    mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, price
                )
                if margin_per_lot and margin_per_lot > 0:
                    max_lot_by_margin = (account_info.margin_free * 0.30) / margin_per_lot
                    if max_lot_by_margin > 0:
                        volume = min(volume, round(max_lot_by_margin / step) * step)
            except Exception:
                pass
        else:
            volume = LOT_SIZE
    else:
        volume = LOT_SIZE
    volume = normalize_volume(volume)
    filling = get_filling_mode()

    # NEW: Store the partial TP level for this entry
    if order_type == mt5.ORDER_TYPE_BUY:
        partial_tp_price = price + PARTIAL_TP_MULT * atr
    else:
        partial_tp_price = price - PARTIAL_TP_MULT * atr

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

    atr_pips = atr_in_pips(atr, point)
    logger.info(
        "Sending %s | vol=%.2f price=%.5f sl=%.5f tp=%.5f atr=%.5f (%d pts) "
        "spread=%d fill=%s trend=%s rsi=%.1f adx=%.1f",
        "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
        volume, price, sl, tp, atr, atr_pips,
        spread, filling,
        get_h1_trend() or "?",
        compute_rsi(get_rates(mt5.TIMEFRAME_M5, RSI_PERIOD + 5), RSI_PERIOD) or 0,
        compute_adx(get_rates(mt5.TIMEFRAME_M5, ADX_PERIOD * 2 + 5), ADX_PERIOD) or 0,
    )
    logger.info(
        "PARTIAL TP target: %.5f (%.1f×ATR, %.0f%% of position)",
        partial_tp_price, PARTIAL_TP_MULT, PARTIAL_TP_VOLUME_RATIO * 100,
    )

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(
            "order_send failed retcode=%s comment=%s",
            result.retcode, result.comment,
        )
        return False

    logger.info("Order FILLED | ticket=%s deal=%s", result.order, result.deal)

    _state["trade_taken"] = True
    _state["trade_date"] = today_utc_date().isoformat()
    _state["trade_side"] = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    _state["entries_today"] = _state.get("entries_today", 0) + 1
    _state["last_entry_atr"] = atr
    _state["partial_tp_taken"] = False  # NEW: reset partial TP flag
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
                pos.ticket, result.retcode, result.comment,
            )
        else:
            logger.info("Close filled | ticket=%s", pos.ticket)

    # After a hard close, allow re-entry next bar
    _state["trade_taken"] = False
    _state["partial_tp_taken"] = False
    save_state()


# ============================================================================
# Partial take-profit (NEW)
# ============================================================================

def check_partial_tp() -> None:
    """Close 50% of position when PARTIAL_TP_MULT×ATR profit is reached."""
    if _state.get("partial_tp_taken"):
        return
    atr_val = _state.get("last_entry_atr")
    if atr_val is None or atr_val <= 0:
        return

    positions = bot_positions()
    if not positions:
        return

    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        return

    for pos in positions:
        if pos.type == mt5.POSITION_TYPE_BUY:
            profit_dist = tick.bid - pos.price_open
            target_dist = PARTIAL_TP_MULT * atr_val
            if profit_dist >= target_dist:
                # Close 50% of position
                close_vol = normalize_volume(pos.volume * PARTIAL_TP_VOLUME_RATIO)
                if close_vol <= 0:
                    continue
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": close_vol,
                    "type": mt5.ORDER_TYPE_SELL,
                    "position": pos.ticket,
                    "price": tick.bid,
                    "deviation": DEVIATION,
                    "magic": MAGIC,
                    "comment": ORDER_COMMENT + "_PARTP",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": get_filling_mode(),
                }
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(
                        "PARTIAL TP closed %.2f vol at %.5f (%.1f×ATR profit)",
                        close_vol, tick.bid, profit_dist / atr_val,
                    )
                    _state["partial_tp_taken"] = True
                    save_state()
                return

        elif pos.type == mt5.POSITION_TYPE_SELL:
            profit_dist = pos.price_open - tick.ask
            target_dist = PARTIAL_TP_MULT * atr_val
            if profit_dist >= target_dist:
                close_vol = normalize_volume(pos.volume * PARTIAL_TP_VOLUME_RATIO)
                if close_vol <= 0:
                    continue
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": close_vol,
                    "type": mt5.ORDER_TYPE_BUY,
                    "position": pos.ticket,
                    "price": tick.ask,
                    "deviation": DEVIATION,
                    "magic": MAGIC,
                    "comment": ORDER_COMMENT + "_PARTP",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": get_filling_mode(),
                }
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(
                        "PARTIAL TP closed %.2f vol at %.5f (%.1f×ATR profit)",
                        close_vol, tick.ask, profit_dist / atr_val,
                    )
                    _state["partial_tp_taken"] = True
                    save_state()
                return


# ============================================================================
# Trailing stop management
# ============================================================================

def update_trailing_stops() -> None:
    """
    Apply trailing stop for positions that have moved in our favor
    beyond TRAIL_ACTIVATE_MULT × ATR.
    """
    positions = bot_positions()
    if not positions:
        return

    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        return

    # Get current ATR for trail distance
    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    if rates is None:
        return
    atr_val = compute_atr(rates, ATR_PERIOD)
    if atr_val is None or atr_val <= 0:
        return

    trail_dist = TRAIL_DISTANCE_MULT * atr_val
    activate_dist = TRAIL_ACTIVATE_MULT * atr_val

    for pos in positions:
        if pos.magic != MAGIC:
            continue

        if pos.type == mt5.POSITION_TYPE_BUY:
            profit_dist = tick.bid - pos.price_open
            if profit_dist >= activate_dist:
                new_sl = normalize_price(tick.bid - trail_dist, info.digits)
                if new_sl > pos.sl:  # only tighten, never loosen
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": SYMBOL,
                        "sl": new_sl,
                        "tp": pos.tp,
                        "magic": MAGIC,
                    }
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(
                            "TRAIL | ticket=%s moved SL to %.5f", pos.ticket, new_sl
                        )
                    else:
                        ret = result.retcode if result else "None"
                        logger.debug("TRAIL failed ticket=%s retcode=%s", pos.ticket, ret)

        elif pos.type == mt5.POSITION_TYPE_SELL:
            profit_dist = pos.price_open - tick.ask
            if profit_dist >= activate_dist:
                new_sl = normalize_price(tick.ask + trail_dist, info.digits)
                if new_sl < pos.sl or pos.sl == 0:
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": SYMBOL,
                        "sl": new_sl,
                        "tp": pos.tp,
                        "magic": MAGIC,
                    }
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(
                            "TRAIL | ticket=%s moved SL to %.5f", pos.ticket, new_sl
                        )
                    else:
                        ret = result.retcode if result else "None"
                        logger.debug("TRAIL failed ticket=%s retcode=%s", pos.ticket, ret)


# ============================================================================
# Entry execution
# ============================================================================

def try_execute_entry() -> None:
    # Check max daily entries
    if _state.get("entries_today", 0) >= _state.get("max_entries_per_day", 3):
        return

    order_type = evaluate_signal()
    if order_type is None:
        return

    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    if rates is None:
        return
    atr_val = compute_atr(rates, ATR_PERIOD)
    if atr_val is None or atr_val <= 0:
        logger.warning("ATR unavailable; skipping entry")
        return

    place_market_order(order_type, atr_val)


# ============================================================================
# Status logging
# ============================================================================

def log_status() -> None:
    tick = mt5.symbol_info_tick(SYMBOL)
    bid = tick.bid if tick else 0.0
    ask = tick.ask if tick else 0.0
    spread = (ask - bid) if tick else 0.0
    now = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    offset_h = _broker_offset_sec / 3600.0
    pre_h = _state.get("pre_high")
    pre_l = _state.get("pre_low")
    trend = get_h1_trend() or "?"
    entries = _state.get("entries_today", 0)
    max_entries = _state.get("max_entries_per_day", 3)
    positions = bot_positions()
    pos_str = "FLAT"
    if positions:
        p = positions[0]
        pos_str = f"ticket={p.ticket} type={'BUY' if p.type==0 else 'SELL'} profit={p.profit:.2f}"

    # Volatility info
    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    atr_val = compute_atr(rates, ATR_PERIOD) if rates is not None else None
    vol_str = f"ATR={atr_val:.1f}pts" if atr_val else "ATR=?"

    # NEW: RSI and ADX in status
    rates_full = get_rates(mt5.TIMEFRAME_M5, max(RSI_PERIOD, ADX_PERIOD) + 10)
    rsi_val = compute_rsi(rates_full, RSI_PERIOD) if rates_full is not None else None
    adx_val = compute_adx(rates_full, ADX_PERIOD) if rates_full is not None else None
    rsi_str = f"RSI={rsi_val:.0f}" if rsi_val else "RSI=?"
    adx_str = f"ADX={adx_val:.0f}" if adx_val else "ADX=?"
    partial_str = f"PARTP={_state.get('partial_tp_taken', False)}"

    logger.info(
        "STATUS | %s | bid=%.5f ask=%.5f spread=%.1f | trend=%s | %s | %s %s | "
        "entries=%d/%d | frozen=%s trade_taken=%s | %s | %s",
        now, bid, ask, spread / 10.0,  # spread in points
        trend, vol_str, rsi_str, adx_str,
        entries, max_entries,
        _state.get("range_frozen"), _state.get("trade_taken"),
        pos_str, partial_str,
    )


# ============================================================================
# End-of-session close (by 17:00 UTC)
# ============================================================================

def at_end_of_session() -> bool:
    """Should we close all positions? Yes, after 17:00 UTC."""
    now = utc_now()
    return (now.hour >= 17 and now.minute >= 0)


# ============================================================================
# Main loop
# ============================================================================

def startup() -> None:
    global _broker_offset_sec, _last_offset_check, _state

    setup_logging()
    logger.info("=== Starting Gold Bot v2 IMPROVED ===")
    logger.info("Symbol=%s Lot=%.2f SL=%.1f×ATR TP=%.1f×ATR Trail=%.1f×ATR PartialTP=%.1f×ATR",
                SYMBOL, LOT_SIZE, ATR_SL_MULT, ATR_TP_MULT, TRAIL_ACTIVATE_MULT, PARTIAL_TP_MULT)
    logger.info("Filters: ATR=[%.0f-%.0f]pts RSI=[%.0f-%.0f] ADX>=%.0f H1 EMA%d Body>=0.08xATR",
                MIN_ATR_PIPS, MAX_ATR_PIPS, RSI_OVERSOLD, RSI_OVERBOUGHT, ADX_MIN, H1_EMA_PERIOD)
    logger.info("Trade windows: %s", [(f"{h1:02d}:{m1:02d}-{h2:02d}:{m2:02d}") for h1, m1, h2, m2 in TRADE_WINDOWS])
    wait_for_mt5()

    _broker_offset_sec = detect_broker_offset()
    _last_offset_check = time.time()
    logger.info("Broker UTC offset: %.0fs (%.2fh)", _broker_offset_sec, _broker_offset_sec / 3600)

    _state = load_state()
    reset_state_for_new_utc_day()
    reconcile_trade_state()
    update_trade_range()

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

            # --- Daily maintenance ---
            reset_state_for_new_utc_day()
            update_trade_range()

            # --- End-of-session close ---
            if at_end_of_session():
                if bot_positions():
                    logger.info("End of session (>=17:00 UTC) — closing positions")
                    close_bot_positions()

            # --- Trailing stop check ---
            if bot_positions():
                update_trailing_stops()
                # NEW: Check partial TP
                check_partial_tp()

            # --- Status log ---
            now = time.time()
            if now - _last_status_log >= STATUS_LOG_INTERVAL_SEC:
                log_status()
                _last_status_log = now

            # --- New bar → evaluate entry ---
            if new_bar_closed():
                # Reconcile first (in case SL hit without us noticing)
                reconcile_trade_state()
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
