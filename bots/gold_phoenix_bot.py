#!/usr/bin/env python3
"""
Gold Phoenix Bot — Live Trading Bot (XAUUSD, H1)
================================================
Real-world implementation of the Gold Phoenix strategy on MT5 demo.
Runs 7-17 UTC, H1 timeframe, 4 signal types:

  1) ASIAN_BREAK  — London open breakout of Asian session range (7-10 UTC)
  2) SQUEEZE      — Bollinger Band width contraction → expansion breakout
  3) PULLBACK     — EMA pullback entry in ADX-confirmed strong trend (ADX≥31)
  4) REVERSAL     — RSI extreme at key level in low-trend environment (ADX<26)

SL/TP: Fixed 200/400 pips (1:2 R:R) — confirmed optimal in 3.5-year backtest.
Lot: 0.10 (or env GOLD_PHOENIX_LOT). Max 2 trades/day.

Run: python gold_phoenix_bot.py
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# --- Session filter (shared module) ---
SESSION_FILTER_ENABLED = True
from session_filters import should_trade as _session_should_trade

# ============================================================================
# Configuration — from backtest optimal params
# ============================================================================

SYMBOL = "XAUUSD"
MAGIC = 777888                       # Phoenix magic number
ORDER_COMMENT = "PHOENIX_H1"

# --- Trade session ---
SESSION_START_UTC = 4                # 04:00 UTC (expanded — Asian best WR hours)
SESSION_END_UTC = 22                 # 22:00 UTC (expanded — US session profitable)

# --- Risk management (percentage-based, dynamic sizing) ---
# RISK_PERCENT = percentage of CURRENT account balance risked per trade
#   Example: 0.15% on $10K account = $15 max loss per trade
#   If account drops to $9K → $13.50 max loss → smaller lot size
#   If account grows to $12K → $18.00 max loss → larger lot size
# This is 100% dynamic — reads live MT5 balance every trade, no fixed lots
RISK_PERCENT = 0.15                   # % of current balance risked per trade
FIXED_SL_PIPS = 200                  # 200 pip stop loss
FIXED_TP_PIPS = 400                  # 400 pip take profit
DEVIATION = 30
MAX_VOLUME_PER_TRADE = 3.0           # Safety cap — never exceed this many lots
MAX_SPREAD_POINTS = 50               # 5.0 pips max

# --- Strategy parameters (backtest-optimised) ---
ADX_PERIOD = 14
ADX_THRESHOLD = 26.0                 # Min ADX for trend signals
ADX_STRONG_THRESHOLD = 31.0          # ADX for pullback signals
BB_PERIOD = 20
BB_STD = 2.0
BB_SQUEEZE_MIN = 0.40                # Max BB width ratio for squeeze
EMA_FAST = 21
EMA_SLOW = 55
ATR_PERIOD = 14
RSI_PERIOD = 14
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75
ASIAN_RANGE_BARS = 6                 # First 6 H1 bars = Asian session
MAX_TRADES_PER_DAY = 99               # Effectively unlimited — take every valid setup

# --- Timing ---
STATUS_LOG_INTERVAL_SEC = 30
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
OFFSET_REVALIDATE_SEC = 3600
RATES_BARS = 500

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "phoenix_bot_state.json")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "phoenix_execution.log")

# ============================================================================
# Module state
# ============================================================================

logger = logging.getLogger("phoenix_bot")
_broker_offset_sec: float = 0.0
_last_offset_check: float = 0.0
_last_h1_bar_time: int = 0
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
        "entries_today": 0,
        "max_entries_per_day": MAX_TRADES_PER_DAY,
        "last_entry_atr": None,
        "asian_high": None,
        "asian_low": None,
        "range_frozen": False,
        "range_date": today,
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
    _state["entries_today"] = 0
    _state["last_entry_atr"] = None
    _state["range_date"] = today
    _state["asian_high"] = None
    _state["asian_low"] = None
    _state["range_frozen"] = False
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

def in_session(hour: int) -> bool:
    return SESSION_START_UTC <= hour < SESSION_END_UTC

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

def get_h1_rates(count: int = RATES_BARS):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, count)
    if rates is None:
        return None
    if len(rates) < 60:
        return None
    return rates

def rates_to_dataframe(rates) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={"time": "date"}, inplace=True)
    return df

def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute all indicators for the last bar. Returns dict or None."""
    if df is None or len(df) < 60:
        return None

    # True Range
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = high_low.combine(high_close, max).combine(low_close, max)

    # EMAs
    ema_fast = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    # ADX
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_adx = tr.rolling(ADX_PERIOD).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(ADX_PERIOD).mean() / atr_adx.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(ADX_PERIOD).mean() / atr_adx.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = dx.rolling(ADX_PERIOD).mean()

    # Bollinger Bands
    bb_mid = df["close"].rolling(BB_PERIOD).mean()
    bb_std_val = df["close"].rolling(BB_PERIOD).std()
    bb_upper = bb_mid + BB_STD * bb_std_val
    bb_lower = bb_mid - BB_STD * bb_std_val
    bb_width = (bb_upper - bb_lower) / bb_mid

    # RSI
    change = df["close"].diff()
    gain = change.mask(change < 0, 0.0)
    loss = (-change).mask(change > 0, 0.0)
    ema_gain = gain.ewm(com=13, adjust=False).mean()
    ema_loss = loss.ewm(com=13, adjust=False).mean()
    rs = ema_gain / ema_loss.replace(0, np.nan)
    rsi_series = 100.0 - (100.0 / (1.0 + rs))

    # ATR
    atr_series = tr.rolling(ATR_PERIOD).mean()

    # Asian session range (first N bars of each day)
    day_of_year = df["date"].dt.dayofyear
    asian_high = df.groupby(day_of_year)["high"].transform(
        lambda x: x.iloc[:ASIAN_RANGE_BARS].max()
    )
    asian_low = df.groupby(day_of_year)["low"].transform(
        lambda x: x.iloc[:ASIAN_RANGE_BARS].min()
    )

    i = len(df) - 1
    return {
        "close": df.iloc[i]["close"],
        "prev_close": df.iloc[i - 1]["close"],
        "high": df.iloc[i]["high"],
        "low": df.iloc[i]["low"],
        "hour": df.iloc[i]["date"].hour,
        "atr": atr_series.iloc[i],
        "adx": adx_line.iloc[i],
        "plus_di": plus_di.iloc[i],
        "minus_di": minus_di.iloc[i],
        "rsi": rsi_series.iloc[i],
        "ema_fast": ema_fast.iloc[i],
        "ema_slow": ema_slow.iloc[i],
        "bb_upper": bb_upper.iloc[i],
        "bb_lower": bb_lower.iloc[i],
        "bb_width": bb_width.iloc[i],
        "asian_high": asian_high.iloc[i],
        "asian_low": asian_low.iloc[i],
        "df": df,
        "i": i,
    }

# ============================================================================
# Filters
# ============================================================================

def spread_ok() -> tuple[bool, int]:
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False, 999
    return (info.spread <= MAX_SPREAD_POINTS, info.spread)

# ============================================================================
# Signal evaluation — Gold Phoenix 4-signal system
# ============================================================================

def bot_positions():
    try:
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            return []
        result = [p for p in positions if p.magic == MAGIC]
        return result
    except Exception:
        return []

def evaluate_phoenix_signal(ind: dict) -> Optional[int]:
    """
    Evaluate all 4 Gold Phoenix signal types on latest H1 bar.
    Returns 1 (BUY), -1 (SELL), or None (no signal).
    """
    if ind is None:
        return None

    close = ind["close"]
    prev_close = ind["prev_close"]
    high = ind["high"]
    low = ind["low"]
    h = ind["hour"]
    atr = ind["atr"]
    adx = ind["adx"]
    rsi = ind["rsi"]
    ema_f = ind["ema_fast"]
    ema_s = ind["ema_slow"]
    bb_u = ind["bb_upper"]
    bb_l = ind["bb_lower"]
    bb_w = ind["bb_width"]
    a_high = ind["asian_high"]
    a_low = ind["asian_low"]
    plus_di = ind["plus_di"]
    minus_di = ind["minus_di"]

    if pd.isna(atr) or atr <= 0 or pd.isna(adx):
        return None

    # Trend directions
    trend_up = close > ema_s and adx >= ADX_THRESHOLD and plus_di > minus_di
    trend_down = close < ema_s and adx >= ADX_THRESHOLD and minus_di > plus_di
    no_trend = adx < ADX_THRESHOLD

    # ── Signal 1: Asian Range Breakout (7-10 UTC) ──
    if 7 <= h <= 10:
        if not pd.isna(a_high) and not pd.isna(a_low):
            a_range = a_high - a_low
            if a_range > atr * 0.3:
                # BUY: breakout above Asian high
                if (trend_up or no_trend) and close > a_high and prev_close <= a_high:
                    logger.info("SIGNAL: ASIAN_BREAK BUY | range=%.2f ATR=%.2f ADX=%.1f", a_range, atr, adx)
                    return 1
                # SELL: breakout below Asian low
                if (trend_down or no_trend) and close < a_low and prev_close >= a_low:
                    logger.info("SIGNAL: ASIAN_BREAK SELL | range=%.2f ATR=%.2f ADX=%.1f", a_range, atr, adx)
                    return -1

    # ── Signal 2: Bollinger Squeeze Breakout ──
    df = ind["df"]
    i = ind["i"]
    if not pd.isna(bb_w):
        bb_w_max = df["bb_width"].iloc[max(0, i - 50):i].max()
        if not pd.isna(bb_w_max) and bb_w_max > 0:
            squeeze_ratio = bb_w / bb_w_max
            if squeeze_ratio <= BB_SQUEEZE_MIN:
                # BUY: price breaks above upper band
                if close > bb_u and i > 0 and prev_close <= df["bb_upper"].iloc[i - 1]:
                    logger.info("SIGNAL: SQUEEZE BUY | ratio=%.3f ATR=%.2f ADX=%.1f", squeeze_ratio, atr, adx)
                    return 1
                # SELL: price breaks below lower band
                if close < bb_l and i > 0 and prev_close >= df["bb_lower"].iloc[i - 1]:
                    logger.info("SIGNAL: SQUEEZE SELL | ratio=%.3f ATR=%.2f ADX=%.1f", squeeze_ratio, atr, adx)
                    return -1

    # ── Signal 3: EMA Pullback in Strong Trend (ADX >= 31) ──
    if adx >= ADX_STRONG_THRESHOLD:
        ema_f_series = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
        pullback_buffer = atr * 0.5
        # BUY: pullback to fast EMA in uptrend
        if trend_up and abs(close - ema_f) <= pullback_buffer:
            was_below = any(
                df["close"].iloc[i - k] < ema_f_series.iloc[i - k]
                for k in range(1, min(5, i) + 1)
            ) if i >= 5 else False
            if was_below and rsi >= 40:
                logger.info("SIGNAL: PULLBACK BUY | ADX=%.1f RSI=%.1f dist=%.2f", adx, rsi, abs(close - ema_f))
                return 1
        # SELL: pullback to fast EMA in downtrend
        if trend_down and abs(close - ema_f) <= pullback_buffer:
            was_above = any(
                df["close"].iloc[i - k] > ema_f_series.iloc[i - k]
                for k in range(1, min(5, i) + 1)
            ) if i >= 5 else False
            if was_above and rsi <= 60:
                logger.info("SIGNAL: PULLBACK SELL | ADX=%.1f RSI=%.1f dist=%.2f", adx, rsi, abs(close - ema_f))
                return -1

    # ── Signal 4: RSI Reversal at Slow EMA (no trend / low ADX) ──
    if no_trend:
        atr_buffer = atr * 1.5
        # Oversold bounce
        if rsi < RSI_OVERSOLD and close >= ema_s - atr_buffer:
            if i > 1:
                prev_rsi = df["rsi_series"].iloc[i - 1] if "rsi_series" in df else None
                if prev_rsi is not None and prev_rsi < RSI_OVERSOLD:
                    logger.info("SIGNAL: REVERSAL BUY | RSI=%.1f ADX=%.1f", rsi, adx)
                    return 1
        # Overbought drop
        if rsi > RSI_OVERBOUGHT and close <= ema_s + atr_buffer:
            if i > 1:
                prev_rsi = df["rsi_series"].iloc[i - 1] if "rsi_series" in df else None
                if prev_rsi is not None and prev_rsi > RSI_OVERBOUGHT:
                    logger.info("SIGNAL: REVERSAL SELL | RSI=%.1f ADX=%.1f", rsi, adx)
                    return -1

    return None

# No global state needed — all data lives in the DataFrame

def compute_full_indicators(df: pd.DataFrame) -> dict:
    """Extended version with full series for lookback checks."""
    result = compute_indicators(df)
    if result is None:
        return None

    # Store RSI series for consecutive check
    change = df["close"].diff()
    gain = change.mask(change < 0, 0.0)
    loss = (-change).mask(change > 0, 0.0)
    ema_gain = gain.ewm(com=13, adjust=False).mean()
    ema_loss = loss.ewm(com=13, adjust=False).mean()
    rs = ema_gain / ema_loss.replace(0, np.nan)
    df["rsi_series"] = 100.0 - (100.0 / (1.0 + rs))

    # BB full series for squeeze lookback
    bb_mid = df["close"].rolling(BB_PERIOD).mean()
    bb_std_val = df["close"].rolling(BB_PERIOD).std()
    df["bb_upper"] = bb_mid + BB_STD * bb_std_val
    df["bb_lower"] = bb_mid - BB_STD * bb_std_val
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid

    result["df"] = df
    return result

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

def place_phoenix_order(order_type: int) -> bool:
    """
    Place market order with FIXED SL/TP (200/400 pips).
    Lot size calculated dynamically from current account balance × RISK_PERCENT.
    No trailing stop — fixed TP is the exit.
    """
    global _state
    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)
    if tick is None or info is None:
        logger.error("Tick/symbol info unavailable")
        return False

    digits = info.digits
    point = info.point

    # Fixed SL/TP in points
    sl_points = int(FIXED_SL_PIPS * 10)   # 200 pips = 2000 points (XAUUSD has 0.01 point)
    tp_points = int(FIXED_TP_PIPS * 10)

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
        sl = price - sl_points * point
        tp = price + tp_points * point
    else:
        price = tick.bid
        sl = price + sl_points * point
        tp = price - tp_points * point

    # Ensure minimum stop distance
    stops_level = max(info.trade_stops_level, getattr(info, "stops_level", 0) or 0)
    min_dist = stops_level * point
    if min_dist > 0:
        if order_type == mt5.ORDER_TYPE_BUY:
            if price - sl < min_dist:
                sl = price - min_dist
            if tp - price < min_dist:
                tp = price + min_dist
        else:
            if sl - price < min_dist:
                sl = price + min_dist
            if price - tp < min_dist:
                tp = price - min_dist

    sl = normalize_price(sl, digits)
    tp = normalize_price(tp, digits)
    price = normalize_price(price, digits)

    # ── Risk-based position sizing (100% dynamic) ──────────────────────
    # Reads current MT5 balance live — no fixed lots whatsoever
    #   risk_amount = current_balance × (RISK_PERCENT / 100)
    #   volume = risk_amount / (SL_distance_in_points × contract_value_per_point)
    #
    # Example: $10,000 balance, 0.15% risk, 200 pip SL on XAUUSD:
    #   risk_amount = $15.00
    #   SL dist = 2000 points (XAUUSD 0.01 point)
    #   contract = 100 units × 0.01 = $1.0 per point
    #   volume = $15 / (2000 × $1.0) = 0.0075 → rounded to 0.01 lots
    #   If balance drops to $8,000 → risk = $12.00 → 0.006 → 0.01 lots
    #   If balance grows to $12,000 → risk = $18.00 → 0.009 → 0.01 lots
    # ────────────────────────────────────────────────────────────────────
    account_info = mt5.account_info()
    if account_info is None or point <= 0:
        logger.error("Cannot size position: no account info or zero point")
        return False

    balance = account_info.balance
    risk_amount = balance * (RISK_PERCENT / 100.0)
    sl_distance_points = abs(sl - price) / point
    contract_value = info.trade_contract_size * point

    if sl_distance_points <= 0 or contract_value <= 0:
        logger.error("Cannot size position: invalid SL distance or contract value")
        return False

    volume = risk_amount / (sl_distance_points * contract_value)

    # Safety: enforce min/max and step rounding
    step = info.volume_step
    volume = max(info.volume_min, min(info.volume_max, volume))
    if step > 0:
        volume = round(volume / step) * step
    volume = round(volume, 2)

    # Cap by margin (use 30% of free margin max)
    try:
        margin_per_lot = mt5.order_calc_margin(
            mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, price
        )
        if margin_per_lot and margin_per_lot > 0 and account_info.margin_free > 0:
            max_lot = (account_info.margin_free * 0.30) / margin_per_lot
            volume = min(volume, round(max_lot / step) * step)
    except Exception:
        pass

    volume = normalize_volume(volume)
    volume = min(volume, MAX_VOLUME_PER_TRADE)

    logger.info(
        "💰 PHOENIX POSITION SIZING | balance=$%.2f risk=%.2f%% risk_amt=$%.2f "
        "SL_dist=%.0fpts volume=%.2f lots | R:R=1:2",
        balance, RISK_PERCENT, risk_amount,
        sl_distance_points, volume,
    )

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

    logger.info("PLACING %s | vol=%.2f price=%.5f sl=%.5f tp=%.5f (SL=%dp TP=%dp) spread=%d",
                "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
                volume, price, sl, tp, FIXED_SL_PIPS, FIXED_TP_PIPS, info.spread)

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Order REJECTED retcode=%s comment=%s", result.retcode, result.comment)
        return False

    logger.info("ORDER FILLED | ticket=%s deal=%s | Price=%.5f SL=%.5f TP=%.5f | R:R=1:2",
                result.order, result.deal, price, sl, tp)

    _state["entries_today"] = _state.get("entries_today", 0) + 1
    _state["trade_date"] = today_utc_date().isoformat()
    save_state()
    return True

# ============================================================================
# End-of-session close
# ============================================================================

def at_end_of_session() -> bool:
    now = utc_now()
    return now.hour >= SESSION_END_UTC

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
            logger.info("EOS CLOSED t=%s at %.5f | PnL=%.2f", pos.ticket, price, pos.profit)
    save_state()

# ============================================================================
# Asian range management
# ============================================================================

def update_asian_range() -> None:
    """Freeze Asian session range after 10 UTC."""
    global _state
    now = utc_now()
    day = now.date()
    if _state.get("range_date") != day.isoformat():
        _state["range_date"] = day.isoformat()
        _state["asian_high"] = None
        _state["asian_low"] = None
        _state["range_frozen"] = False

    if _state.get("range_frozen"):
        return

    # After 10 UTC, backfill the Asian range from H1 data
    if now.hour >= 10:
        rates = get_h1_rates(RATES_BARS)
        if rates is None:
            return
        df = rates_to_dataframe(rates)
        day_of_year = df["date"].dt.dayofyear
        today_doy = day.timetuple().tm_yday
        today_data = df[day_of_year == today_doy]
        if len(today_data) >= ASIAN_RANGE_BARS:
            _state["asian_high"] = float(today_data.iloc[:ASIAN_RANGE_BARS]["high"].max())
            _state["asian_low"] = float(today_data.iloc[:ASIAN_RANGE_BARS]["low"].min())
            _state["range_frozen"] = True
            logger.info("Asian range FROZEN | high=%.5f low=%.5f", _state["asian_high"], _state["asian_low"])
            save_state()

# ============================================================================
# H1 bar detection
# ============================================================================

def new_h1_bar_closed() -> bool:
    global _last_h1_bar_time
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 5)
    if rates is None or len(rates) < 2:
        return False
    closed_time = int(rates[1]["time"])  # 2nd latest = most recent closed bar
    if closed_time == _last_h1_bar_time:
        return False
    is_new = _last_h1_bar_time != 0
    _last_h1_bar_time = closed_time
    return is_new

# ============================================================================
# Entry execution
# ============================================================================

SENTIMENT_ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "sentiment_engine.py")

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

def try_phoenix_entry() -> None:
    if _state.get("entries_today", 0) >= _state.get("max_entries_per_day", MAX_TRADES_PER_DAY):
        return
    positions = bot_positions()
    if positions and len(positions) > 0:
        return  # Already in a Phoenix trade

    rates = get_h1_rates(RATES_BARS)
    if rates is None:
        return
    df = rates_to_dataframe(rates)

    ind = compute_full_indicators(df)
    if ind is None:
        return

    signal = evaluate_phoenix_signal(ind)
    if signal is None:
        return

    # Sentiment filter — check market sentiment before entering
    sent_ok, sent_msg = check_sentiment_filter(signal)
    if not sent_ok:
        logger.info("Sentiment BLOCKED %s: %s", "BUY" if signal == 1 else "SELL", sent_msg)
        return
    logger.info("Sentiment OK: %s", sent_msg)

    # Spread check
    sp_ok, spread = spread_ok()
    if not sp_ok:
        logger.info("Spread too high (%d) — skipping Phoenix entry", spread)
        return

    order_type = mt5.ORDER_TYPE_BUY if signal == 1 else mt5.ORDER_TYPE_SELL
    place_phoenix_order(order_type)

# ============================================================================
# Status logging
# ============================================================================

def log_status() -> None:
    tick = mt5.symbol_info_tick(SYMBOL)
    bid = tick.bid if tick else 0.0
    ask = tick.ask if tick else 0.0
    now_str = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    entries = _state.get("entries_today", 0)
    max_entries = _state.get("max_entries_per_day", MAX_TRADES_PER_DAY)
    positions_list = bot_positions()
    pos_str = "FLAT"
    if positions_list is not None:
        if len(positions_list) > 0:
            p = positions_list[0]
            pos_str = f"t={p.ticket} {'BUY' if p.type==0 else 'SELL'} P&L={p.profit:.2f}"

    # Quick signal check — use try/except around numpy-heavy code
    signal_str = "?"
    try:
        raw_arr = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 500)
        raw_ok = raw_arr is not None
        if raw_ok and len(raw_arr) >= 60:
            rates_df = pd.DataFrame(raw_arr)
            rates_df["date"] = pd.to_datetime(rates_df["time"], unit="s")
            h = rates_df.iloc[-1]["date"].hour
            close = float(rates_df.iloc[-1]["close"])
            prev_close = float(rates_df.iloc[-2]["close"]) if len(rates_df) > 1 else close

            # Compute simple indicators inline — no numpy arrays in boolean context
            high_low = rates_df["high"].values - rates_df["low"].values
            # ADX
            high_vals = rates_df["high"].values.astype(float)
            low_vals = rates_df["low"].values.astype(float)
            close_vals = rates_df["close"].values.astype(float)

            # Quick ADX estimate
            up_move = np.maximum(high_vals[1:] - high_vals[:-1], 0)
            down_move = np.maximum(low_vals[:-1] - low_vals[1:], 0)
            tr_vals = np.maximum(high_vals[1:] - low_vals[1:],
                                 np.maximum(np.abs(high_vals[1:] - close_vals[:-1]),
                                            np.abs(low_vals[1:] - close_vals[:-1])))
            atr_val = float(np.mean(tr_vals[-14:])) if len(tr_vals) >= 14 else 0.0

            # RSI
            changes = close_vals[1:] - close_vals[:-1]
            gains = np.where(changes > 0, changes, 0.0)
            losses = np.where(changes < 0, -changes, 0.0)
            avg_g = float(np.mean(gains[-14:])) if len(gains) >= 14 else 50.0
            avg_l = float(np.mean(losses[-14:])) if len(losses) >= 14 else 1.0
            rsi_val = 100.0 - (100.0 / (1.0 + avg_g / avg_l)) if avg_l > 0 else 50.0

            signal_str = f"ADX={float(np.mean(tr_vals[-26:])):.0f} RSI={rsi_val:.0f} ATR={atr_val:.2f}"
    except Exception:
        signal_str = "?"

    logger.info("PHOENIX STATUS | %s | bid=%.5f ask=%.5f | %s | entries=%d/%d | %s",
                now_str, bid, ask, signal_str, entries, max_entries, pos_str)

# ============================================================================
# Main loop
# ============================================================================

def startup() -> None:
    global _broker_offset_sec, _last_offset_check, _state
    setup_logging()
    logger.info("=" * 60)
    logger.info("Gold Phoenix Bot — Live Trading on Demo Account")
    logger.info("Signals: AsianBreak + Squeeze + Pullback + Reversal")
    logger.info("SL/TP: %d/%d pips (1:2 R:R) | Risk: %.2f%% | Max %d trades/day",
                FIXED_SL_PIPS, FIXED_TP_PIPS, RISK_PERCENT, MAX_TRADES_PER_DAY)
    logger.info("Session: %d-%d UTC | ADX>=%.0f | BB Squeeze<=%.2f",
                SESSION_START_UTC, SESSION_END_UTC, ADX_THRESHOLD, BB_SQUEEZE_MIN)
    logger.info("=" * 60)
    wait_for_mt5()
    _broker_offset_sec = detect_broker_offset()
    _last_offset_check = time.time()
    logger.info("Broker offset: %.0fs", _broker_offset_sec)
    _state = load_state()
    reset_state_for_new_utc_day()
    update_asian_range()

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
            update_asian_range()

            now = utc_now()

            # --- Session filter (shared liquidity check) ---
            if SESSION_FILTER_ENABLED:
                if not _session_should_trade(now.hour):
                    logger.info("SESSION FILTER: Outside trading hours (hour=%d UTC)", now.hour)
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

            # End-of-session close at 17 UTC
            if at_end_of_session():
                bpos = bot_positions()
                if bpos and len(bpos) > 0:
                    logger.info("End of session — closing Phoenix positions")
                    close_bot_positions()

            # Only evaluate entries during session hours
            if SESSION_START_UTC <= now.hour < SESSION_END_UTC:
                if new_h1_bar_closed():
                    try_phoenix_entry()

            ts = time.time()
            if ts - _last_status_log >= STATUS_LOG_INTERVAL_SEC:
                log_status()
                _last_status_log = ts

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
