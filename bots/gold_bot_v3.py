#!/usr/bin/env python3
"""
Gold Bot v3
⚠️ DISABLED by Council Decision — 83% WR but PF 0.34, one loss = 14 wins wiped
"""
import sys
print("⚠️  GOLD BOT DISABLED — catastrophic loss risk, 83% WR but PF 0.34", flush=True)
sys.exit(0)
"""
Gold Bot v3 — Multi-Timeframe Session Range Breakout (XAUUSD)
============================================================
R:R ≥ 1:3 | Multi-TF: H1→M15→M5

Strategy:
  HTF (H1):   EMA50 determines primary trend direction
  MTF (M15):  Price relative to M15 EMA50 — ensure room to run
  LTF (M5):   London pre-market range breakout with 2-candle confirmation

Only trade WITH the trend:
  - BUY: H1 trend BULLISH + M5 breakout above pre-market high
  - SELL: H1 trend BEARISH + M5 breakout below pre-market low

Risk:
  SL = 2.0 × M5 ATR(14)
  TP = 6.0 × M5 ATR(14)  →  R:R = 1:3
  No partial TP — let winners run
  Trailing stop activates at 3.0×ATR profit

Run: python gold_bot_v3.py
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import MetaTrader5 as mt5

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# --- Session filter (shared module) ---
SESSION_FILTER_ENABLED = True
from session_filters import should_trade as _session_should_trade

# ============================================================================
# Configuration
# ============================================================================

SYMBOL = "XAUUSD"
MAGIC = 777556                      # v3 magic number
ORDER_COMMENT = "GOLDv3_MTF"

# --- Range definition (London pre-open) ---
PRE_MARKET_START_UTC = (7, 0)
PRE_MARKET_END_UTC = (8, 0)

# --- Trade windows ---
TRADE_WINDOWS = [
    (8, 0,  11, 0),      # London momentum
    (13, 30, 17, 0),     # US session
]

# --- Risk management (R:R = 1:3) ---
LOT_SIZE = 0.01
RISK_PERCENT = 1.0                    # 1% risk per trade
DEVIATION = 30
MAX_SPREAD_POINTS = 50                # 5.0 pips max
ATR_PERIOD = 14
ATR_SL_MULT = 2.0                     # SL = 2.0 × ATR
ATR_TP_MULT = 6.0                     # TP = 6.0 × ATR → R:R = 1:3
TRAIL_ACTIVATE_MULT = 3.0             # Activate trailing at 3.0×ATR profit
TRAIL_DISTANCE_MULT = 1.5             # Trail stays 1.5×ATR behind

# --- Volatility filter ---
MIN_ATR_PIPS = 300
MAX_ATR_PIPS = 1500

# --- RSI filter (relaxed — we trade WITH trend) ---
RSI_PERIOD = 14
RSI_OVERBOUGHT = 75                   # Only block if extreme
RSI_OVERSOLD = 25

# --- ADX filter ---
ADX_PERIOD = 14
ADX_MIN = 15

# --- Multi-timeframe ---
H1_EMA_PERIOD = 50                    # Primary trend on H1
M15_EMA_PERIOD = 50                   # Medium-term alignment on M15

# --- Entry controls ---
MAX_ENTRIES_PER_DAY = 2               # Quality over quantity

# --- Timing ---
STATUS_LOG_INTERVAL_SEC = 10
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
OFFSET_REVALIDATE_SEC = 3600
RATES_BARS = 500

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "gold_bot_v3_state.json")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "gold_v3_execution.log")

# --- Sentiment engine path ---
SENTIMENT_ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "sentiment_engine.py")

# ============================================================================
# Module state
# ============================================================================

logger = logging.getLogger("gold_bot_v3")
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
# State management
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
        "max_entries_per_day": MAX_ENTRIES_PER_DAY,
        "last_entry_atr": None,
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
    except (json.JSONDecodeError, OSError):
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
    logger.info("New UTC day — resetting state")
    _state["trade_date"] = today
    _state["trade_taken"] = False
    _state["trade_side"] = None
    _state["range_date"] = today
    _state["pre_high"] = None
    _state["pre_low"] = None
    _state["range_frozen"] = False
    _state["entries_today"] = 0
    _state["last_entry_atr"] = None
    save_state()

# ============================================================================
# UTC helpers
# ============================================================================

def today_utc_date() -> date:
    return datetime.now(timezone.utc).date()

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def broker_ts_to_utc(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts - _broker_offset_sec, tz=timezone.utc)

def utc_time_on_date(d: date, hour: int, minute: int) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=timezone.utc)

def utc_in_time_range(dt: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    t = dt.hour * 60 + dt.minute
    return (start[0] * 60 + start[1]) <= t < (end[0] * 60 + end[1])

def utc_at_or_after(dt: datetime, hour: int, minute: int) -> bool:
    return (dt.hour, dt.minute) >= (hour, minute)

def in_trade_window() -> bool:
    now = utc_now()
    t = now.hour * 60 + now.minute
    for h1, m1, h2, m2 in TRADE_WINDOWS:
        if (h1 * 60 + m1) <= t < (h2 * 60 + m2):
            return True
    return False

# ============================================================================
# Broker offset
# ============================================================================

def detect_broker_offset() -> float:
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        raise RuntimeError(f"No tick for {SYMBOL}: {mt5.last_error()}")
    return float(tick.time) - datetime.now(timezone.utc).timestamp()

def revalidate_offset_if_needed() -> None:
    global _broker_offset_sec, _last_offset_check
    now = time.time()
    if now - _last_offset_check < OFFSET_REVALIDATE_SEC:
        return
    try:
        new_off = detect_broker_offset()
        drift = abs(new_off - _broker_offset_sec)
        if drift > 1800:
            logger.warning("Broker offset drift %.0fs", drift)
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
        logger.error("symbol_select failed: %s", mt5.last_error())
        return False
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        logger.error("symbol_info missing")
        return False
    if not info.visible:
        mt5.symbol_select(SYMBOL, True)
    if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        logger.error("Trading disabled for %s", SYMBOL)
        return False
    return True

def shutdown_mt5() -> None:
    mt5.shutdown()
    logger.info("MT5 shutdown")

def wait_for_mt5() -> None:
    while True:
        if init_mt5() and ensure_symbol():
            return
        logger.info("Retrying MT5 in %ss...", MT5_RETRY_SEC)
        time.sleep(MT5_RETRY_SEC)

# ============================================================================
# Data helpers
# ============================================================================

def get_rates(timeframe=mt5.TIMEFRAME_M5, count: int = RATES_BARS):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, count)
    if rates is None or len(rates) < 3:
        return None
    return rates

def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))

def compute_atr(rates, period: int = ATR_PERIOD) -> Optional[float]:
    if len(rates) < period + 2:
        return None
    trs = []
    for i in range(1, len(rates)):
        trs.append(true_range(float(rates[i]["high"]), float(rates[i]["low"]), float(rates[i - 1]["close"])))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def compute_ema(rates, period: int) -> Optional[float]:
    if len(rates) < period + 1:
        return None
    closes = [float(r["close"]) for r in rates]
    k = 2.0 / (period + 1.0)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema

def atr_in_pips(atr_value: float, point: float) -> float:
    return atr_value / point if point > 0 else 0.0

def compute_rsi(rates, period: int = RSI_PERIOD) -> Optional[float]:
    if len(rates) < period + 2:
        return None
    closes = [float(r["close"]) for r in rates]
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
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
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

def compute_adx(rates, period: int = ADX_PERIOD) -> Optional[float]:
    if len(rates) < period * 2 + 2:
        return None
    highs = [float(r["high"]) for r in rates]
    lows = [float(r["low"]) for r in rates]
    closes = [float(r["close"]) for r in rates]
    tr14, plus_dm14, minus_dm14 = [], [], []
    for i in range(1, len(rates)):
        tr14.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm14.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm14.append(down_move if down_move > up_move and down_move > 0 else 0)
    if len(tr14) < period:
        return None
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
    return dx

def bars_in_time_window(rates, day: date, start: tuple[int, int], end: tuple[int, int]) -> list:
    start_dt = utc_time_on_date(day, *start)
    end_dt = utc_time_on_date(day, *end)
    return [b for b in rates if broker_ts_to_utc(b["time"]).date() == day and start_dt <= broker_ts_to_utc(b["time"]) < end_dt]

def compute_range_from_bars(bars) -> tuple[Optional[float], Optional[float]]:
    if not bars:
        return None, None
    return max(float(b["high"]) for b in bars), min(float(b["low"]) for b in bars)

# ============================================================================
# Pre-market range management
# ============================================================================

def backfill_trade_range(day: date) -> tuple[Optional[float], Optional[float]]:
    rates = get_rates(mt5.TIMEFRAME_M5, RATES_BARS)
    if rates is None:
        return None, None
    bars = bars_in_time_window(rates, day, PRE_MARKET_START_UTC, PRE_MARKET_END_UTC)
    if not bars:
        logger.warning("No pre-market bars for %s", day)
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
    if utc_at_or_after(now, *PRE_MARKET_END_UTC):
        if _state["pre_high"] is None or _state["pre_low"] is None:
            hi, lo = backfill_trade_range(day)
            if hi is None or lo is None:
                return
            _state["pre_high"] = hi
            _state["pre_low"] = lo
        _state["range_frozen"] = True
        logger.info("Range FROZEN | high=%.5f low=%.5f", _state["pre_high"], _state["pre_low"])
        save_state()
        return
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
# Multi-timeframe trend analysis
# ============================================================================

def get_h1_trend() -> Optional[str]:
    """HTF: H1 EMA50. Returns 'BULLISH', 'BEARISH', or None."""
    h1_rates = get_rates(mt5.TIMEFRAME_H1, 200)
    if h1_rates is None or len(h1_rates) < H1_EMA_PERIOD + 2:
        return None
    ema_val = compute_ema(h1_rates, H1_EMA_PERIOD)
    if ema_val is None:
        return None
    last_close = float(h1_rates[-1]["close"])
    if last_close > ema_val * 1.002:      # 0.2% buffer to avoid whipsaw
        return "BULLISH"
    elif last_close < ema_val * 0.998:
        return "BEARISH"
    return "NEUTRAL"

def get_m15_alignment(h1_trend: Optional[str]) -> tuple[bool, str]:
    """
    MTF: M15 EMA50 alignment check.
    Returns (aligned: bool, message: str).
    For BULLISH trend: price should be at or above M15 EMA50 (pullback allowed).
    For BEARISH trend: price should be at or below M15 EMA50.
    """
    m15_rates = get_rates(mt5.TIMEFRAME_M15, 100)
    if m15_rates is None or len(m15_rates) < M15_EMA_PERIOD + 2:
        return True, "M15 data insufficient — assuming aligned"
    ema_val = compute_ema(m15_rates, M15_EMA_PERIOD)
    if ema_val is None:
        return True, "M15 EMA compute failed — assuming aligned"
    last_close = float(m15_rates[-1]["close"])
    if h1_trend == "BULLISH":
        aligned = last_close > ema_val * 0.995  # allow slight pullback below M15 EMA50
        msg = f"M15 aligned={aligned} price={last_close:.2f} EMA50={ema_val:.2f}"
        return aligned, msg
    elif h1_trend == "BEARISH":
        aligned = last_close < ema_val * 1.005
        msg = f"M15 aligned={aligned} price={last_close:.2f} EMA50={ema_val:.2f}"
        return aligned, msg
    return True, "Neutral trend — M15 alignment skipped"

# ============================================================================
# Filters
# ============================================================================

def spread_ok() -> tuple[bool, int]:
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False, 999
    return (info.spread <= MAX_SPREAD_POINTS, info.spread)

def volatility_ok() -> tuple[bool, Optional[float], str]:
    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    if rates is None:
        return False, None, "No rates"
    atr_val = compute_atr(rates, ATR_PERIOD)
    if atr_val is None:
        return False, None, "ATR failed"
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False, atr_val, "No symbol info"
    atr_pips = atr_in_pips(atr_val, info.point)
    if atr_pips < MIN_ATR_PIPS:
        return False, atr_val, f"ATR too low: {atr_pips:.0f}pts"
    if atr_pips > MAX_ATR_PIPS:
        return False, atr_val, f"ATR too high: {atr_pips:.0f}pts"
    return True, atr_val, f"ATR ok: {atr_pips:.0f}pts"

def rsi_filter_ok(direction: int) -> tuple[bool, Optional[float], str]:
    """Relaxed RSI — only block if extreme AND counter-trend."""
    rates = get_rates(mt5.TIMEFRAME_M5, RSI_PERIOD + 5)
    if rates is None:
        return True, None, "No rates"
    rsi = compute_rsi(rates, RSI_PERIOD)
    if rsi is None:
        return True, None, "RSI failed"
    if direction == mt5.ORDER_TYPE_BUY and rsi > RSI_OVERBOUGHT:
        return False, rsi, f"RSI overbought: {rsi:.1f} > {RSI_OVERBOUGHT}"
    if direction == mt5.ORDER_TYPE_SELL and rsi < RSI_OVERSOLD:
        return False, rsi, f"RSI oversold: {rsi:.1f} < {RSI_OVERSOLD}"
    return True, rsi, f"RSI ok: {rsi:.1f}"

def adx_filter_ok() -> tuple[bool, Optional[float], str]:
    rates = get_rates(mt5.TIMEFRAME_M5, ADX_PERIOD * 2 + 5)
    if rates is None:
        return True, None, "No rates"
    adx = compute_adx(rates, ADX_PERIOD)
    if adx is None:
        return True, None, "ADX failed"
    if adx < ADX_MIN:
        return False, adx, f"ADX too low: {adx:.1f} < {ADX_MIN}"
    return True, adx, f"ADX ok: {adx:.1f}"

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
    if positions is not None and len(positions) > 0:
        if not _state.get("trade_taken"):
            logger.info("Reconciling: open position found")
            _state["trade_taken"] = True
            _state["trade_date"] = today_utc_date().isoformat()
            save_state()
    else:
        if _state.get("trade_taken") and _state.get("entries_today", 0) < _state.get("max_entries_per_day", MAX_ENTRIES_PER_DAY):
            _state["trade_taken"] = False
            save_state()

def evaluate_signal() -> Optional[int]:
    """
    Multi-TF signal evaluation:
    1. Pre-market range must be frozen
    2. Must be in trade window
    3. No existing position
    4. HTF (H1 EMA50) trend alignment
    5. MTF (M15 EMA50) alignment check
    6. LTF (M5) breakout with 2-candle confirmation
    7. Volatility filter
    8. ADX trend strength
    9. RSI filter (relaxed)
    10. Spread filter
    """
    if not _state.get("range_frozen"):
        return None
    if _state.get("trade_taken"):
        return None
    if not in_trade_window():
        return None
    pos = bot_positions()
    if pos is not None and len(pos) > 0:
        return None

    pre_high = _state.get("pre_high")
    pre_low = _state.get("pre_low")
    if pre_high is None or pre_low is None:
        return None

    # --- HTF: H1 trend ---
    h1_trend = get_h1_trend()
    if h1_trend is None:
        logger.warning("H1 trend unavailable — waiting for data")
        return None
    logger.info("H1 trend: %s", h1_trend)

    # --- MTF: M15 alignment ---
    m15_aligned, m15_msg = get_m15_alignment(h1_trend)
    if not m15_aligned:
        logger.info("M15 alignment BLOCKED: %s", m15_msg)
        return None
    logger.info("M15: %s", m15_msg)

    # --- Volatility ---
    vol_ok, atr_val, vol_msg = volatility_ok()
    if not vol_ok or atr_val is None:
        logger.info("Vol filter: %s", vol_msg)
        return None

    # --- Spread ---
    sp_ok, spread = spread_ok()
    if not sp_ok:
        logger.info("Spread too high: %d", spread)
        return None

    # --- ADX ---
    adx_ok, adx_val, adx_msg = adx_filter_ok()
    if not adx_ok:
        logger.info("ADX filter: %s", adx_msg)
        return None

    # --- LTF: M5 breakout with 2-candle confirmation ---
    rates = get_rates(mt5.TIMEFRAME_M5, 50)
    if rates is None or len(rates) < 5:
        return None

    c1 = float(rates[1]["close"])
    c2 = float(rates[2]["close"])

    # BUY signal
    if c1 > pre_high and c2 > pre_high:
        if h1_trend == "BEARISH":
            logger.info("BUY breakout but H1 trend BEARISH — skipping")
            return None

        # RSI check for BUY
        rsi_ok, rsi_val, rsi_msg = rsi_filter_ok(mt5.ORDER_TYPE_BUY)
        if not rsi_ok:
            logger.info("BUY RSI filter: %s", rsi_msg)
            return None

        logger.info("BUY signal CONFIRMED | c1=%.5f c2=%.5f high=%.5f trend=%s ADX=%.1f RSI=%s",
                     c1, c2, pre_high, h1_trend, adx_val or 0, rsi_val or 0)
        return mt5.ORDER_TYPE_BUY

    # SELL signal
    if c1 < pre_low and c2 < pre_low:
        if h1_trend == "BULLISH":
            logger.info("SELL breakout but H1 trend BULLISH — skipping")
            return None

        rsi_ok, rsi_val, rsi_msg = rsi_filter_ok(mt5.ORDER_TYPE_SELL)
        if not rsi_ok:
            logger.info("SELL RSI filter: %s", rsi_msg)
            return None

        logger.info("SELL signal CONFIRMED | c1=%.5f c2=%.5f low=%.5f trend=%s ADX=%.1f RSI=%s",
                     c1, c2, pre_low, h1_trend, adx_val or 0, rsi_val or 0)
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
    if filling & 2:
        return mt5.ORDER_FILLING_IOC
    if filling & 1:
        return mt5.ORDER_FILLING_FOK
    if filling & 4:
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

def adjust_stops(side: int, entry: float, sl: float, tp: float,
                 stops_level: int, point: float, digits: int) -> tuple[float, float]:
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
    else:
        price = tick.bid
        sl = price + ATR_SL_MULT * atr
        tp = price - ATR_TP_MULT * atr

    sl, tp = adjust_stops(order_type, price, sl, tp, stops_level, point, digits)
    price = normalize_price(price, digits)

    # Risk-based position sizing: 1% risk
    account_info = mt5.account_info()
    if account_info and point > 0:
        balance = account_info.balance
        risk_amount = balance * (RISK_PERCENT / 100.0)
        sl_distance_points = abs(sl - price) / point
        contract_value = info.trade_contract_size * point
        if sl_distance_points > 0 and contract_value > 0:
            volume = risk_amount / (sl_distance_points * contract_value)
            volume = max(info.volume_min, min(info.volume_max, volume))
            step = info.volume_step
            if step > 0:
                volume = round(volume / step) * step
            volume = round(volume, 2)

            # Cap by margin (30% of free margin)
            try:
                margin_per_lot = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, price)
                if margin_per_lot and margin_per_lot > 0 and account_info.margin_free > 0:
                    max_lot = (account_info.margin_free * 0.30) / margin_per_lot
                    volume = min(volume, round(max_lot / step) * step)
            except Exception:
                pass
        else:
            volume = LOT_SIZE
    else:
        volume = LOT_SIZE
    volume = normalize_volume(volume)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": ORDER_COMMENT,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(),
    }

    atr_pips = atr_in_pips(atr, point)
    logger.info("PLACING %s | vol=%.2f price=%.5f sl=%.5f tp=%.5f atr=%.5f R:R=1:%.1f spread=%d",
                "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
                volume, price, sl, tp, atr, ATR_TP_MULT / ATR_SL_MULT,
                info.spread)

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Order REJECTED retcode=%s comment=%s", result.retcode, result.comment)
        return False

    logger.info("ORDER FILLED | ticket=%s deal=%s | Price=%.5f SL=%.5f TP=%.5f | R:R=1:%.1f",
                result.order, result.deal, price, sl, tp, ATR_TP_MULT / ATR_SL_MULT)

    _state["trade_taken"] = True
    _state["trade_date"] = today_utc_date().isoformat()
    _state["trade_side"] = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    _state["entries_today"] = _state.get("entries_today", 0) + 1
    _state["last_entry_atr"] = atr
    save_state()
    return True

# ============================================================================
# Trailing stop (v3 — wider, no partial TP)
# ============================================================================

def update_trailing_stops() -> None:
    positions = bot_positions()
    if positions is None or len(positions) == 0:
        return
    info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    if info is None or tick is None:
        return
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
                if new_sl > pos.sl:
                    req = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket,
                           "symbol": SYMBOL, "sl": new_sl, "tp": pos.tp, "magic": MAGIC}
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info("TRAIL BUY t=%s SL→%.5f (profit %.1f×ATR)", pos.ticket, new_sl, profit_dist / atr_val)
        elif pos.type == mt5.POSITION_TYPE_SELL:
            profit_dist = pos.price_open - tick.ask
            if profit_dist >= activate_dist:
                new_sl = normalize_price(tick.ask + trail_dist, info.digits)
                if new_sl < pos.sl or pos.sl == 0:
                    req = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket,
                           "symbol": SYMBOL, "sl": new_sl, "tp": pos.tp, "magic": MAGIC}
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info("TRAIL SELL t=%s SL→%.5f (profit %.1f×ATR)", pos.ticket, new_sl, profit_dist / atr_val)

# ============================================================================
# End-of-session close
# ============================================================================

def at_end_of_session() -> bool:
    now = utc_now()
    return now.hour >= 17 and now.minute >= 0

def close_bot_positions() -> None:
    positions = bot_positions()
    if positions is None or len(positions) == 0:
        return
    filling = get_filling_mode()
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        return
    for pos in positions:
        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": pos.volume,
               "type": order_type, "position": pos.ticket, "price": price,
               "deviation": DEVIATION, "magic": MAGIC, "comment": ORDER_COMMENT + "_CLOSE",
               "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling}
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info("CLOSED t=%s at %.5f", pos.ticket, price)
    _state["trade_taken"] = False
    save_state()

# ============================================================================
# Sentiment filter
# ============================================================================

def check_sentiment_filter(signal_direction: int) -> tuple[bool, str]:
    """
    Check market sentiment before entering a trade.
    Imports and calls the sentiment engine directly (no HTTP).
    signal_direction: 1=BUY, -1=SELL
    Returns (allowed: bool, message: str).

    Sentiment thresholds:
      >= +3 (BULLISH)  → only BUY signals allowed
      <= -3 (BEARISH)   → only SELL signals allowed
      -3 to +3 (NEUTRAL) → both directions allowed
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("sentiment_engine", SENTIMENT_ENGINE_PATH)
        if spec is None or spec.loader is None:
            return True, "Sentiment engine unavailable — proceeding without filter"
        sen_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sen_mod)
        score_obj = sen_mod.get_sentiment()
        score = score_obj.score
        bias = score_obj.bias
    except Exception as e:
        logger.warning("Sentiment engine error: %s", e)
        return True, f"Sentiment engine error ({e}) — proceeding without filter"

    if signal_direction == 1:  # BUY signal
        if score >= 3:
            return True, f"Sentiment {bias} (+{score}) — BUY aligned with bullish sentiment"
        elif score <= -3:
            return False, f"Sentiment {bias} ({score}) — BUY blocked by bearish sentiment"
        else:
            return True, f"Sentiment {bias} ({score:+d}) — BUY allowed in neutral conditions"
    else:  # SELL signal
        if score <= -3:
            return True, f"Sentiment {bias} ({score}) — SELL aligned with bearish sentiment"
        elif score >= 3:
            return False, f"Sentiment {bias} (+{score}) — SELL blocked by bullish sentiment"
        else:
            return True, f"Sentiment {bias} ({score:+d}) — SELL allowed in neutral conditions"

# ============================================================================
# Entry execution
# ============================================================================

def try_execute_entry() -> None:
    if _state.get("entries_today", 0) >= _state.get("max_entries_per_day", MAX_ENTRIES_PER_DAY):
        return
    order_type = evaluate_signal()
    if order_type is None:
        return

    # Sentiment filter — check market sentiment before entering
    signal_dir = 1 if order_type == mt5.ORDER_TYPE_BUY else -1
    sent_ok, sent_msg = check_sentiment_filter(signal_dir)
    if not sent_ok:
        logger.info("Sentiment BLOCKED %s: %s", "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL", sent_msg)
        return
    logger.info("Sentiment OK: %s", sent_msg)

    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    if rates is None:
        return
    atr_val = compute_atr(rates, ATR_PERIOD)
    if atr_val is None or atr_val <= 0:
        logger.warning("ATR unavailable — skipping entry")
        return
    place_market_order(order_type, atr_val)

# ============================================================================
# Status logging
# ============================================================================

def log_status() -> None:
    tick = mt5.symbol_info_tick(SYMBOL)
    bid = tick.bid if tick else 0.0
    ask = tick.ask if tick else 0.0
    now_str = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    trend = get_h1_trend() or "?"
    entries = _state.get("entries_today", 0)
    max_entries = _state.get("max_entries_per_day", MAX_ENTRIES_PER_DAY)
    positions = bot_positions()
    pos_str = "FLAT"
    if positions is not None and len(positions) > 0:
        p = positions[0]
        pos_str = f"t={p.ticket} {'BUY' if p.type==0 else 'SELL'} P&L={p.profit:.2f}"
    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    atr_val = compute_atr(rates) if rates is not None else None
    atr_str = f"ATR={atr_val:.2f}" if atr_val else "ATR=?"
    rsi_rates = get_rates(mt5.TIMEFRAME_M5, RSI_PERIOD + 5)
    rsi = compute_rsi(rsi_rates, RSI_PERIOD) if rsi_rates is not None else None
    adx_rates = get_rates(mt5.TIMEFRAME_M5, ADX_PERIOD * 2 + 5)
    adx = compute_adx(adx_rates, ADX_PERIOD) if adx_rates is not None else None
    logger.info("STATUS | %s | bid=%.5f ask=%.5f | H1=%s | %s RSI=%s ADX=%s | entries=%d/%d | %s | frozen=%s",
                now_str, bid, ask, trend, atr_str,
                f"{rsi:.0f}" if rsi else "?", f"{adx:.0f}" if adx else "?",
                entries, max_entries, pos_str, _state.get("range_frozen"))

# ============================================================================
# Main loop
# ============================================================================

def startup() -> None:
    global _broker_offset_sec, _last_offset_check, _state
    setup_logging()
    logger.info("=" * 60)
    logger.info("Gold Bot v3 — Multi-Timeframe Range Breakout")
    logger.info("R:R = 1:%.1f (SL=%.1f×ATR TP=%.1f×ATR)", ATR_TP_MULT / ATR_SL_MULT, ATR_SL_MULT, ATR_TP_MULT)
    logger.info("HTF: H1 EMA%d | MTF: M15 EMA%d | LTF: M5 breakout", H1_EMA_PERIOD, M15_EMA_PERIOD)
    logger.info("Filters: ATR=[%.0f-%.0f]pts ADX>=%.0f RSI=[%.0f-%.0f]", MIN_ATR_PIPS, MAX_ATR_PIPS, ADX_MIN, RSI_OVERSOLD, RSI_OVERBOUGHT)
    logger.info("Max entries/day: %d | Trailing: activate at %.1f×ATR", MAX_ENTRIES_PER_DAY, TRAIL_ACTIVATE_MULT)
    logger.info("=" * 60)
    wait_for_mt5()
    _broker_offset_sec = detect_broker_offset()
    _last_offset_check = time.time()
    logger.info("Broker offset: %.0fs", _broker_offset_sec)
    _state = load_state()
    reset_state_for_new_utc_day()
    reconcile_trade_state()
    update_trade_range()

def run_loop() -> None:
    global _last_status_log
    while True:
        try:
            term = mt5.terminal_info()
            if term is None or not term.connected:
                logger.warning("Terminal disconnected — reconnecting")
                mt5.shutdown()
                wait_for_mt5()
                revalidate_offset_if_needed()

            revalidate_offset_if_needed()
            reset_state_for_new_utc_day()
            update_trade_range()

            # --- Session filter (shared liquidity check) ---
            if SESSION_FILTER_ENABLED:
                now_hour = utc_now().hour
                if not _session_should_trade(now_hour):
                    logger.info("SESSION FILTER: Outside trading hours (hour=%d UTC)", now_hour)
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

            if at_end_of_session():
                bpos = bot_positions()
                if bpos is not None and len(bpos) > 0:
                    logger.info("End of session — closing positions")
                    close_bot_positions()

            bpos = bot_positions()
            if bpos is not None and len(bpos) > 0:
                update_trailing_stops()

            now = time.time()
            if now - _last_status_log >= STATUS_LOG_INTERVAL_SEC:
                log_status()
                _last_status_log = now

            if new_bar_closed():
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
