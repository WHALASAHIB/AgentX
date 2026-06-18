#!/usr/bin/env python3
"""
Scalping Phoenix Hybrid Bot — Multi-TF Scalper + Gold Phoenix Optional Mode
============================================================================
Dual-mode trading bot for XAUUSD on MT5.

Modes:
  USE_GOLD_PHOENIX = False (default): Original scalping bot v4 logic
    - Multi-TF (M15→M5→M1) momentum scalper
    - Dynamic SL/TP based on M5 ATR (2× ATR SL, 5× ATR TP → R:R 1:2.5)
    - 1% risk per trade

  USE_GOLD_PHOENIX = True: Gold Phoenix signal engine
    - H1-based 4-signal system: AsianBreak, Squeeze, Pullback, Reversal
    - Fixed SL/TP: 200/400 pips (1:2 R:R)
    - Same 1% risk-based position sizing

Trade execution (both modes): MT5 orders with risk management, logging, state.

Run: python scalping_phoenix_hybrid.py
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
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# ============================================================================
# MODE SWITCH — set True to use Gold Phoenix signal engine
# ============================================================================

USE_GOLD_PHOENIX = True   # <-- Toggle: False = scalping, True = Gold Phoenix

# ============================================================================
# Common Configuration
# ============================================================================

SYMBOL = "XAUUSD"
MAGIC = 999112                     # Shared magic number
ORDER_COMMENT = "HYBRIDv4"

# --- Risk ---
RISK_PERCENT = 1.0                 # 1% risk per trade
DEVIATION = 30
MAX_SPREAD_POINTS = 35             # 3.5 pips max

# --- Timing ---
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
HEARTBEAT_INTERVAL = 60
STATUS_LOG_INTERVAL_SEC = 30

# --- Paths ---
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BOT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "hybrid_execution.log")
STATE_FILE = os.path.join(LOG_DIR, "hybrid_state.json")

# ============================================================================
# Gold Phoenix Configuration (only used when USE_GOLD_PHOENIX=True)
# ============================================================================

# Trade session (UTC)
PHOENIX_SESSION_START_UTC = 7
PHOENIX_SESSION_END_UTC = 17

# Fixed SL/TP (1:2 R:R)
FIXED_SL_PIPS = 200
FIXED_TP_PIPS = 400

# Strategy parameters
ADX_PERIOD = 14
ADX_THRESHOLD = 26.0
ADX_STRONG_THRESHOLD = 31.0
BB_PERIOD = 20
BB_STD = 2.0
BB_SQUEEZE_MIN = 0.40
EMA_FAST = 21
EMA_SLOW = 55
ATR_PERIOD = 14
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75
ASIAN_RANGE_BARS = 6
MAX_TRADES_PER_DAY_PHOENIX = 2

RATES_BARS = 500

# ============================================================================
# Scalping Configuration (only used when USE_GOLD_PHOENIX=False)
# ============================================================================

SCALP_TRADE_SESSIONS = [
    (8, 0,  11, 0),      # London (high liquidity open)
    (13, 30, 16, 0),     # US session (avoid late-day chop)
]

# Multi-timeframe parameters
M15_EMA_FAST = 20
M15_EMA_SLOW = 50
M15_EMA_ULTRA = 200

M5_EMA_FAST = 20
M5_EMA_SLOW = 50

RSI_PERIOD = 5
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75

MIN_ATR_PRICE = 0.10

# Risk (R:R = 1:2.5)
ATR_SL_MULT = 2.0
ATR_TP_MULT = 5.0

MAX_CONSECUTIVE_LOSSES = 999
MAX_TRADES_PER_SESSION = 999

M5_REFRESH_SEC = 10

# ============================================================================
# Logging
# ============================================================================

logger = logging.getLogger("hybrid_bot")

def setup_logging():
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)

# ============================================================================
# State management
# ============================================================================

class BotState:
    def __init__(self):
        self.consecutive_losses = 0
        self.session_trades = 0
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.current_session_date: Optional[date] = None
        self.paused_till: Optional[datetime] = None
        self.stop_reason = ""
        self._tracked_positions: set = set()
        # Phoenix-specific
        self.entries_today = 0
        self.phoenix_trade_date: Optional[str] = None

    def save(self):
        data = {
            "consecutive_losses": self.consecutive_losses,
            "session_trades": self.session_trades,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "current_session_date": str(self.current_session_date) if self.current_session_date else None,
            "paused_till": self.paused_till.isoformat() if self.paused_till else None,
            "stop_reason": self.stop_reason,
            "entries_today": self.entries_today,
            "phoenix_trade_date": self.phoenix_trade_date,
        }
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                self.consecutive_losses = data.get("consecutive_losses", 0)
                self.session_trades = data.get("session_trades", 0)
                self.total_trades = data.get("total_trades", 0)
                self.wins = data.get("wins", 0)
                self.losses = data.get("losses", 0)
                if data.get("current_session_date"):
                    self.current_session_date = date.fromisoformat(data["current_session_date"])
                if data.get("paused_till"):
                    self.paused_till = datetime.fromisoformat(data["paused_till"])
                self.stop_reason = data.get("stop_reason", "")
                self.entries_today = data.get("entries_today", 0)
                self.phoenix_trade_date = data.get("phoenix_trade_date")
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("State file corrupt, resetting")

    def reset_session(self, today: date):
        if self.current_session_date != today:
            logger.info("New session day — resetting counters")
            self.consecutive_losses = 0
            self.session_trades = 0
            self.entries_today = 0
            self.current_session_date = today
            self.phoenix_trade_date = today.isoformat()
            self.paused_till = None
            self.stop_reason = ""

state = BotState()

# ============================================================================
# Gold Phoenix — Indicator computation (H1 data)
# ============================================================================
# These functions mirror gold_phoenix_bot.py's compute_indicators.

def phoenix_get_h1_rates(count: int = RATES_BARS):
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, count)
    if rates is None:
        return None
    if len(rates) < 60:
        return None
    return rates

def phoenix_rates_to_dataframe(rates) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={"time": "date"}, inplace=True)
    return df

def phoenix_compute_indicators(df: pd.DataFrame) -> dict:
    """Compute all indicators for the last bar. Returns dict or None."""
    if df is None or len(df) < 60:
        return None

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = high_low.combine(high_close, max).combine(low_close, max)

    ema_fast = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_adx = tr.rolling(ADX_PERIOD).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(ADX_PERIOD).mean() / atr_adx.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(ADX_PERIOD).mean() / atr_adx.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = dx.rolling(ADX_PERIOD).mean()

    bb_mid = df["close"].rolling(BB_PERIOD).mean()
    bb_std_val = df["close"].rolling(BB_PERIOD).std()
    bb_upper = bb_mid + BB_STD * bb_std_val
    bb_lower = bb_mid - BB_STD * bb_std_val
    bb_width = (bb_upper - bb_lower) / bb_mid

    change = df["close"].diff()
    gain = change.mask(change < 0, 0.0)
    loss = (-change).mask(change > 0, 0.0)
    ema_gain = gain.ewm(com=13, adjust=False).mean()
    ema_loss = loss.ewm(com=13, adjust=False).mean()
    rs = ema_gain / ema_loss.replace(0, np.nan)
    rsi_series = 100.0 - (100.0 / (1.0 + rs))

    atr_series = tr.rolling(ATR_PERIOD).mean()

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

def phoenix_compute_full_indicators(df: pd.DataFrame) -> dict:
    """Extended version with full series for lookback checks."""
    result = phoenix_compute_indicators(df)
    if result is None:
        return None

    change = df["close"].diff()
    gain = change.mask(change < 0, 0.0)
    loss = (-change).mask(change > 0, 0.0)
    ema_gain = gain.ewm(com=13, adjust=False).mean()
    ema_loss = loss.ewm(com=13, adjust=False).mean()
    rs = ema_gain / ema_loss.replace(0, np.nan)
    df["rsi_series"] = 100.0 - (100.0 / (1.0 + rs))

    bb_mid = df["close"].rolling(BB_PERIOD).mean()
    bb_std_val = df["close"].rolling(BB_PERIOD).std()
    df["bb_upper"] = bb_mid + BB_STD * bb_std_val
    df["bb_lower"] = bb_mid - BB_STD * bb_std_val
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid

    result["df"] = df
    return result

# ============================================================================
# Gold Phoenix — Signal evaluation (4-signal system)
# ============================================================================

def phoenix_evaluate_signal(ind: dict) -> Optional[int]:
    """
    Evaluate all 4 Gold Phoenix signal types on latest H1 bar.
    Returns 1 (BUY), -1 (SELL), or None (no signal).
    """
    if ind is None:
        return None

    close = ind["close"]
    prev_close = ind["prev_close"]
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

    trend_up = close > ema_s and adx >= ADX_THRESHOLD and plus_di > minus_di
    trend_down = close < ema_s and adx >= ADX_THRESHOLD and minus_di > plus_di
    no_trend = adx < ADX_THRESHOLD

    # ── Signal 1: Asian Range Breakout (7-10 UTC) ──
    if 7 <= h <= 10:
        if not pd.isna(a_high) and not pd.isna(a_low):
            a_range = a_high - a_low
            if a_range > atr * 0.3:
                if (trend_up or no_trend) and close > a_high and prev_close <= a_high:
                    logger.info("GOLD_PHOENIX SIGNAL: ASIAN_BREAK BUY | range=%.2f ATR=%.2f ADX=%.1f", a_range, atr, adx)
                    return 1
                if (trend_down or no_trend) and close < a_low and prev_close >= a_low:
                    logger.info("GOLD_PHOENIX SIGNAL: ASIAN_BREAK SELL | range=%.2f ATR=%.2f ADX=%.1f", a_range, atr, adx)
                    return -1

    # ── Signal 2: Bollinger Squeeze Breakout ──
    df = ind["df"]
    i = ind["i"]
    if not pd.isna(bb_w):
        bb_w_max = df["bb_width"].iloc[max(0, i - 50):i].max()
        if not pd.isna(bb_w_max) and bb_w_max > 0:
            squeeze_ratio = bb_w / bb_w_max
            if squeeze_ratio <= BB_SQUEEZE_MIN:
                if close > bb_u and i > 0 and prev_close <= df["bb_upper"].iloc[i - 1]:
                    logger.info("GOLD_PHOENIX SIGNAL: SQUEEZE BUY | ratio=%.3f ATR=%.2f ADX=%.1f", squeeze_ratio, atr, adx)
                    return 1
                if close < bb_l and i > 0 and prev_close >= df["bb_lower"].iloc[i - 1]:
                    logger.info("GOLD_PHOENIX SIGNAL: SQUEEZE SELL | ratio=%.3f ATR=%.2f ADX=%.1f", squeeze_ratio, atr, adx)
                    return -1

    # ── Signal 3: EMA Pullback in Strong Trend (ADX >= 31) ──
    if adx >= ADX_STRONG_THRESHOLD:
        ema_f_series = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
        pullback_buffer = atr * 0.5
        if trend_up and abs(close - ema_f) <= pullback_buffer:
            was_below = any(
                df["close"].iloc[i - k] < ema_f_series.iloc[i - k]
                for k in range(1, min(5, i) + 1)
            ) if i >= 5 else False
            if was_below and rsi >= 40:
                logger.info("GOLD_PHOENIX SIGNAL: PULLBACK BUY | ADX=%.1f RSI=%.1f dist=%.2f", adx, rsi, abs(close - ema_f))
                return 1
        if trend_down and abs(close - ema_f) <= pullback_buffer:
            was_above = any(
                df["close"].iloc[i - k] > ema_f_series.iloc[i - k]
                for k in range(1, min(5, i) + 1)
            ) if i >= 5 else False
            if was_above and rsi <= 60:
                logger.info("GOLD_PHOENIX SIGNAL: PULLBACK SELL | ADX=%.1f RSI=%.1f dist=%.2f", adx, rsi, abs(close - ema_f))
                return -1

    # ── Signal 4: RSI Reversal at Slow EMA (no trend) ──
    if no_trend:
        atr_buffer = atr * 1.5
        if rsi < RSI_OVERSOLD and close >= ema_s - atr_buffer:
            if i > 1:
                prev_rsi = df["rsi_series"].iloc[i - 1] if "rsi_series" in df else None
                if prev_rsi is not None and prev_rsi < RSI_OVERSOLD:
                    logger.info("GOLD_PHOENIX SIGNAL: REVERSAL BUY | RSI=%.1f ADX=%.1f", rsi, adx)
                    return 1
        if rsi > RSI_OVERBOUGHT and close <= ema_s + atr_buffer:
            if i > 1:
                prev_rsi = df["rsi_series"].iloc[i - 1] if "rsi_series" in df else None
                if prev_rsi is not None and prev_rsi > RSI_OVERBOUGHT:
                    logger.info("GOLD_PHOENIX SIGNAL: REVERSAL SELL | RSI=%.1f ADX=%.1f", rsi, adx)
                    return -1

    return None

# ============================================================================
# Gold Phoenix — Entry (triggered on new H1 bar)
# ============================================================================

def phoenix_in_session(now: datetime) -> bool:
    return PHOENIX_SESSION_START_UTC <= now.hour < PHOENIX_SESSION_END_UTC

def phoenix_new_h1_bar_closed() -> bool:
    """Check if a new H1 candle has closed since last check."""
    if not hasattr(phoenix_new_h1_bar_closed, "_last_h1_bar_time"):
        phoenix_new_h1_bar_closed._last_h1_bar_time = 0
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, 5)
    if rates is None or len(rates) < 2:
        return False
    closed_time = int(rates[1]["time"])
    if closed_time == phoenix_new_h1_bar_closed._last_h1_bar_time:
        return False
    is_new = phoenix_new_h1_bar_closed._last_h1_bar_time != 0
    phoenix_new_h1_bar_closed._last_h1_bar_time = closed_time
    return is_new

def phoenix_spread_ok() -> tuple[bool, int]:
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False, 999
    return (info.spread <= MAX_SPREAD_POINTS, info.spread)

def phoenix_try_entry() -> None:
    """Evaluate Gold Phoenix signals and enter trades on H1 bar close."""
    if state.entries_today >= MAX_TRADES_PER_DAY_PHOENIX:
        return

    # Check for existing position
    positions = mt5.positions_get(symbol=SYMBOL, group=str(MAGIC))
    if positions:
        for pos in positions:
            if pos.magic == MAGIC:
                return  # Already in a trade

    rates = phoenix_get_h1_rates(RATES_BARS)
    if rates is None:
        return

    df = phoenix_rates_to_dataframe(rates)
    ind = phoenix_compute_full_indicators(df)
    if ind is None:
        return

    signal = phoenix_evaluate_signal(ind)
    if signal is None:
        return

    # Spread check
    sp_ok, spread = phoenix_spread_ok()
    if not sp_ok:
        logger.info("Spread too high (%d) — skipping Phoenix entry", spread)
        return

    # Execute trade with Phoenix SL/TP
    order_type = mt5.ORDER_TYPE_BUY if signal == 1 else mt5.ORDER_TYPE_SELL
    place_phoenix_order(order_type)

# ============================================================================
# Gold Phoenix — Fixed SL/TP order placement
# ============================================================================

def place_phoenix_order(order_type: int) -> bool:
    """Place market order with FIXED SL/TP (200/400 pips) and dynamic lot sizing."""
    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)
    if tick is None or info is None:
        logger.error("Tick/symbol info unavailable")
        return False

    digits = info.digits
    point = info.point

    # Fixed SL/TP in points (XAUUSD: 1 pip = 10 points)
    sl_points = int(FIXED_SL_PIPS * 10)   # 200 pips = 2000 points
    tp_points = int(FIXED_TP_PIPS * 10)   # 400 pips = 4000 points

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
        sl = price - sl_points * point
        tp = price + tp_points * point
    else:
        price = tick.bid
        sl = price + sl_points * point
        tp = price - tp_points * point

    # Ensure minimum stop distance
    stops_level = info.trade_stops_level if hasattr(info, 'trade_stops_level') else 0
    min_dist = max(stops_level, getattr(info, "stops_level", 0) or 0) * point
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

    # Dynamic lot sizing based on risk (same as scalping bot)
    sl_distance = abs(sl - price)
    account_info = mt5.account_info()
    if not account_info:
        logger.error("No account info")
        return False

    sym_info = get_symbol_info(SYMBOL)
    if not sym_info:
        logger.error("No symbol info")
        return False

    lot = calculate_lot_size(account_info.balance, sl_distance, sym_info)

    # Normalize
    sl = round(sl, digits)
    tp = round(tp, digits)
    price = round(price, digits)

    # Filling mode
    filling_mode = mt5.ORDER_FILLING_IOC
    filling = info.filling_mode
    if filling & 2:
        filling_mode = mt5.ORDER_FILLING_IOC
    elif filling & 1:
        filling_mode = mt5.ORDER_FILLING_FOK
    elif filling & 4:
        filling_mode = mt5.ORDER_FILLING_RETURN

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": ORDER_COMMENT + "_PHOENIX",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    logger.info("PLACING PHOENIX %s | vol=%.2f price=%.5f sl=%.5f tp=%.5f (SL=%dp TP=%dp) spread=%d",
                "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
                lot, price, sl, tp, FIXED_SL_PIPS, FIXED_TP_PIPS, info.spread)

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Order REJECTED retcode=%s comment=%s", result.retcode, result.comment)
        return False

    logger.info("ORDER FILLED | ticket=%s deal=%s | Price=%.5f SL=%.5f TP=%.5f lot=%.2f | R:R=1:2",
                result.order, result.deal, price, sl, tp, lot)

    state.entries_today += 1
    state.total_trades += 1
    state.save()
    return True

# ============================================================================
# Scalping — Indicator functions (M5/M15/M1 based)
# ============================================================================

def calculate_ema(prices: list, period: int) -> float:
    if len(prices) < period:
        return prices[-1]
    multiplier = 2.0 / (period + 1)
    ema = sum(prices[-period:]) / period
    for price in prices[-(period + 1):-period]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(rates: tuple, period: int) -> float:
    closes = [r['close'] for r in rates]
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(-period - 1, -1):
        diff = closes[i + 1] - closes[i]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    avg_gain = gains / period
    avg_loss = losses / period
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

def calculate_atr(rates: tuple, period: int) -> float:
    if len(rates) < period + 1:
        return 0
    tr_values = []
    for i in range(-period - 1, -1):
        h, l, pc = rates[i + 1]['high'], rates[i + 1]['low'], rates[i]['close']
        tr_values.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(tr_values) / len(tr_values)

# ============================================================================
# Scalping — Multi-timeframe analysis
# ============================================================================

def get_m15_trend() -> Optional[str]:
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, M15_EMA_SLOW + 20)
    if rates is None or len(rates) < M15_EMA_SLOW + 5:
        return None
    prices = [r['close'] for r in rates]
    ema_fast = calculate_ema(prices, M15_EMA_FAST)
    ema_slow = calculate_ema(prices, M15_EMA_SLOW)
    current = prices[-1]

    rates_200 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, M15_EMA_ULTRA + 10)
    if rates_200 is not None and len(rates_200) > M15_EMA_ULTRA:
        prices_200 = [r['close'] for r in rates_200]
        ema_ultra = calculate_ema(prices_200, M15_EMA_ULTRA)
        if current > ema_ultra * 1.003:
            return "BULLISH"
        if current < ema_ultra * 0.997:
            return "BEARISH"

    if current > ema_fast > ema_slow:
        return "BULLISH"
    if current < ema_fast < ema_slow:
        return "BEARISH"
    return "NEUTRAL"

def get_m5_pullback_structure(m5_rates: tuple, trend: str) -> tuple[bool, float, float, str]:
    if m5_rates is None or len(m5_rates) < M5_EMA_SLOW + 5:
        return False, 0, 0, "Insufficient M5 data"

    prices = [r['close'] for r in m5_rates]
    ema_fast = calculate_ema(prices, M5_EMA_FAST)
    ema_slow = calculate_ema(prices, M5_EMA_SLOW)
    current = prices[-1]
    last_high = m5_rates[-1]['high']
    last_low = m5_rates[-1]['low']
    atr_val = calculate_atr(m5_rates, ATR_PERIOD)

    if atr_val < MIN_ATR_PRICE:
        return False, 0, atr_val, f"M5 ATR too low: {atr_val:.3f}"

    if trend == "BULLISH":
        near_fast = abs(current - ema_fast) <= atr_val * 0.5
        near_slow = abs(current - ema_slow) <= atr_val * 0.8
        if near_fast or near_slow:
            upper_wick = last_high - max(m5_rates[-1]['close'], m5_rates[-1]['open'])
            lower_wick = min(m5_rates[-1]['close'], m5_rates[-1]['open']) - last_low
            body = abs(m5_rates[-1]['close'] - m5_rates[-1]['open'])
            candle_range = last_high - last_low

            if candle_range > 0:
                if lower_wick > body * 1.5 and upper_wick < body:
                    return True, (ema_fast if near_fast else ema_slow), atr_val, \
                        f"M5 bullish rejection at EMA (lower wick {lower_wick:.2f})"
                if len(m5_rates) >= 3:
                    prev = m5_rates[-2]
                    if m5_rates[-1]['close'] > m5_rates[-1]['open'] and \
                       prev['close'] < prev['open'] and \
                       abs(m5_rates[-1]['close'] - m5_rates[-1]['open']) > abs(prev['close'] - prev['open']) * 1.2:
                        return True, (ema_fast if near_fast else ema_slow), atr_val, \
                            "M5 bullish engulfing at EMA"
            return False, (ema_fast if near_fast else ema_slow), atr_val, "Near EMA but no rejection"

    elif trend == "BEARISH":
        near_fast = abs(current - ema_fast) <= atr_val * 0.5
        near_slow = abs(current - ema_slow) <= atr_val * 0.8
        if near_fast or near_slow:
            upper_wick = last_high - max(m5_rates[-1]['close'], m5_rates[-1]['open'])
            lower_wick = min(m5_rates[-1]['close'], m5_rates[-1]['open']) - last_low
            body = abs(m5_rates[-1]['close'] - m5_rates[-1]['open'])
            candle_range = last_high - last_low

            if candle_range > 0:
                if upper_wick > body * 1.5 and lower_wick < body:
                    return True, (ema_fast if near_fast else ema_slow), atr_val, \
                        f"M5 bearish rejection at EMA (upper wick {upper_wick:.2f})"
                if len(m5_rates) >= 3:
                    prev = m5_rates[-2]
                    if m5_rates[-1]['close'] < m5_rates[-1]['open'] and \
                       prev['close'] > prev['open'] and \
                       abs(m5_rates[-1]['close'] - m5_rates[-1]['open']) > abs(prev['close'] - prev['open']) * 1.2:
                        return True, (ema_fast if near_fast else ema_slow), atr_val, \
                            "M5 bearish engulfing at EMA"
            return False, (ema_fast if near_fast else ema_slow), atr_val, "Near EMA but no rejection"

    return False, 0, atr_val, "No pullback setup"

def get_m1_micro_breakout(m1_rates: tuple, trend: str, m5_atr: float) -> tuple[bool, float, float, float, str]:
    if m1_rates is None or len(m1_rates) < 5:
        return False, 0, 0, 0, "Insufficient M1 data"

    last = m1_rates[-1]
    prev = m1_rates[-2]
    current_close = last['close']
    current_high = last['high']
    current_low = last['low']

    m1_atr = calculate_atr(m1_rates, ATR_PERIOD)
    if m1_atr <= 0:
        return False, 0, 0, 0, "M1 ATR zero"

    m1_rsi = calculate_rsi(m1_rates, RSI_PERIOD)

    if trend == "BULLISH":
        if current_close > prev['high'] and current_high > prev['high']:
            if m1_rsi < RSI_OVERBOUGHT:
                tick = mt5.symbol_info_tick(SYMBOL)
                if tick is None:
                    return False, 0, 0, 0, "No tick"
                entry = tick.ask
                sl = entry - ATR_SL_MULT * m5_atr
                tp = entry + ATR_TP_MULT * m5_atr
                return True, entry, sl, tp, \
                    f"M1 micro-breakout BUY @{entry:.2f} SL={sl:.2f} TP={tp:.2f} RSI={m1_rsi:.0f}"
        m1_prices = [r['close'] for r in m1_rates]
        m1_ema8 = calculate_ema(m1_prices, 8)
        pullback_to_ema = abs(current_close - m1_ema8) <= m1_atr * 0.5
        if pullback_to_ema and m1_rsi <= RSI_OVERSOLD:
            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                return False, 0, 0, 0, "No tick"
            entry = tick.ask
            sl = entry - ATR_SL_MULT * m5_atr
            tp = entry + ATR_TP_MULT * m5_atr
            return True, entry, sl, tp, \
                f"M1 EMA8 pullback BUY @{entry:.2f} RSI={m1_rsi:.0f}"

    elif trend == "BEARISH":
        if current_close < prev['low'] and current_low < prev['low']:
            if m1_rsi > RSI_OVERSOLD:
                tick = mt5.symbol_info_tick(SYMBOL)
                if tick is None:
                    return False, 0, 0, 0, "No tick"
                entry = tick.bid
                sl = entry + ATR_SL_MULT * m5_atr
                tp = entry - ATR_TP_MULT * m5_atr
                return True, entry, sl, tp, \
                    f"M1 micro-breakout SELL @{entry:.2f} SL={sl:.2f} TP={tp:.2f} RSI={m1_rsi:.0f}"
        m1_prices = [r['close'] for r in m1_rates]
        m1_ema8 = calculate_ema(m1_prices, 8)
        pullback_to_ema = abs(current_close - m1_ema8) <= m1_atr * 0.5
        if pullback_to_ema and m1_rsi >= RSI_OVERBOUGHT:
            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                return False, 0, 0, 0, "No tick"
            entry = tick.bid
            sl = entry + ATR_SL_MULT * m5_atr
            tp = entry - ATR_TP_MULT * m5_atr
            return True, entry, sl, tp, \
                f"M1 EMA8 pullback SELL @{entry:.2f} RSI={m1_rsi:.0f}"

    return False, 0, 0, 0, "No M1 entry signal"

# ============================================================================
# Session helpers (scalping mode)
# ============================================================================

def is_in_scalp_session(current_dt: datetime) -> bool:
    now_minutes = current_dt.hour * 60 + current_dt.minute
    for sh, sm, eh, em in SCALP_TRADE_SESSIONS:
        if (sh * 60 + sm) <= now_minutes < (eh * 60 + em):
            return True
    return False

# ============================================================================
# Shared — MT5 trade execution helpers
# ============================================================================

def get_symbol_info(symbol: str) -> dict:
    info = mt5.symbol_info(symbol)
    if info is None:
        return {}
    return {
        "point": info.point,
        "digits": info.digits,
        "trade_tick_value": info.trade_tick_value,
        "trade_tick_size": info.trade_tick_size,
        "spread": info.spread,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
    }

def calculate_lot_size(account_balance: float, sl_price_distance: float, symbol_info: dict) -> float:
    risk_amount = account_balance * (RISK_PERCENT / 100.0)
    tick_value = symbol_info.get("trade_tick_value", 0.1)
    tick_size = symbol_info.get("trade_tick_size", 0.01)
    if tick_value <= 0 or tick_size <= 0:
        return 0.01
    risk_per_unit = tick_value / tick_size
    lot_raw = risk_amount / (sl_price_distance * risk_per_unit)
    try:
        account_info = mt5.account_info()
        if account_info and account_info.margin_free > 0:
            tick_price = mt5.symbol_info_tick(SYMBOL)
            entry_price = tick_price.ask if tick_price else 0
            if entry_price > 0:
                margin_per_lot = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, entry_price)
                if margin_per_lot and margin_per_lot > 0:
                    max_lot_by_margin = (account_info.margin_free * 0.30) / margin_per_lot
                    lot_raw = min(lot_raw, max_lot_by_margin)
    except Exception:
        pass
    step = symbol_info.get("volume_step", 0.01)
    lot = round(lot_raw / step) * step
    return max(symbol_info.get("volume_min", 0.01), min(lot, symbol_info.get("volume_max", 100)))

def place_scalp_order(order_type: int, lot: float, price: float, sl: float, tp: float,
                      symbol_info: dict) -> Optional[int]:
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": ORDER_COMMENT + "_SCALP",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info("ORDER FILLED | t=%s %s lot=%.2f price=%.2f SL=%.2f TP=%.2f R:R=1:%.1f",
                     result.order, "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
                     lot, price, sl, tp, ATR_TP_MULT / ATR_SL_MULT)
        return result.order
    else:
        logger.warning("ORDER REJECTED | retcode=%s", result.retcode if result else -1)
        return None

def close_position(ticket: int, symbol_info: dict) -> bool:
    position = mt5.positions_get(ticket=ticket)
    if position is None or len(position) == 0:
        return True
    pos = position[0]
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(SYMBOL).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(SYMBOL).ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": pos.volume,
        "type": order_type, "position": ticket, "price": price,
        "deviation": DEVIATION, "magic": MAGIC, "comment": "CLOSE_HYBRID",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info("CLOSED t=%s at %.2f", ticket, price)
        return True
    logger.warning("CLOSE FAILED t=%s retcode=%s", ticket, result.retcode if result else -1)
    return False

def close_all_open_positions(symbol_info: dict) -> int:
    positions = mt5.positions_get(symbol=SYMBOL, group=str(MAGIC))
    if positions is None or len(positions) == 0:
        return 0
    closed = 0
    for pos in positions:
        if pos.magic == MAGIC:
            if close_position(pos.ticket, symbol_info):
                closed += 1
    return closed

def get_position_ticket() -> Optional[int]:
    positions = mt5.positions_get(symbol=SYMBOL, group=str(MAGIC))
    if positions is not None:
        for pos in positions:
            if pos.magic == MAGIC:
                return pos.ticket
    return None

# ============================================================================
# Main loop
# ============================================================================

def main():
    setup_logging()
    logger.info("=" * 60)

    if USE_GOLD_PHOENIX:
        logger.info("Scalping Phoenix Hybrid — MODE: GOLD PHOENIX (H1 signals)")
        logger.info("Signals: AsianBreak + Squeeze + Pullback + Reversal")
        logger.info("SL/TP: %d/%d pips (1:2 R:R) | Risk: %.0f%% | Max %d trades/day",
                    FIXED_SL_PIPS, FIXED_TP_PIPS, RISK_PERCENT, MAX_TRADES_PER_DAY_PHOENIX)
        logger.info("Session: %d-%d UTC | ADX>=%.0f | BB Squeeze<=%.2f",
                    PHOENIX_SESSION_START_UTC, PHOENIX_SESSION_END_UTC, ADX_THRESHOLD, BB_SQUEEZE_MIN)
    else:
        logger.info("Scalping Phoenix Hybrid — MODE: SCALPING v4 (M15/M5/M1)")
        logger.info("R:R = 1:%.1f (SL=%.1f×M5 ATR TP=%.1f×M5 ATR)", ATR_TP_MULT / ATR_SL_MULT, ATR_SL_MULT, ATR_TP_MULT)
        logger.info("HTF: M15 EMA20/50/200 | MTF: M5 pullback+rejection | LTF: M1 breakout")

    logger.info("=" * 60)

    state.load()
    today = date.today()
    state.reset_session(today)

    config = load_config()
    if not connect_mt5(config):
        logger.error("Failed to connect to MT5")
        return

    account = mt5.account_info()
    if account:
        logger.info("Connected: %s | Balance: $%.2f", account.login, account.balance)

    sym_info = get_symbol_info(SYMBOL)
    if not sym_info:
        logger.error("Cannot get symbol info")
        return

    # Phoenix-specific state
    _last_status_log = 0.0
    phoenix_new_h1_bar_closed._last_h1_bar_time = 0

    # Scalping caches
    m5_trend_check = 0
    m15_trend_cache: Optional[str] = None
    m15_trend_time = 0
    m5_setup_cache: tuple = (False, 0, 0, "")
    m5_setup_time = 0

    last_heartbeat = time.time()
    last_state_save = time.time()

    try:
        while True:
            now_utc = datetime.now(timezone.utc)
            current_ts = time.time()

            # --- Heartbeat ---
            if current_ts - last_heartbeat > HEARTBEAT_INTERVAL:
                pos = get_position_ticket()
                mode_str = "PHOENIX" if USE_GOLD_PHOENIX else "SCALP"
                if USE_GOLD_PHOENIX:
                    logger.info("HEARTBEAT | %s | entries_today=%d/%d pos=%s",
                                mode_str, state.entries_today, MAX_TRADES_PER_DAY_PHOENIX,
                                f"t={pos}" if pos else "FLAT")
                else:
                    logger.info("HEARTBEAT | %s | trend=%s trades=%d/%d wins=%d losses=%d pos=%s",
                                mode_str, m15_trend_cache, state.session_trades, MAX_TRADES_PER_SESSION,
                                state.wins, state.losses, f"t={pos}" if pos else "FLAT")
                last_heartbeat = current_ts

            # --- State save every 5 min ---
            if current_ts - last_state_save > 300:
                state.save()
                last_state_save = current_ts

            # --- RESET for new UTC day ---
            if state.current_session_date != date.today():
                state.reset_session(date.today())

            if USE_GOLD_PHOENIX:
                # ================================================================
                # GOLD PHOENIX MODE — H1 bar signal evaluation
                # ================================================================
                now = datetime.now(timezone.utc)

                # End-of-session close
                if now.hour >= PHOENIX_SESSION_END_UTC:
                    pos_ticket = get_position_ticket()
                    if pos_ticket:
                        logger.info("End of Phoenix session — closing position %s", pos_ticket)
                        close_position(pos_ticket, sym_info)
                    time.sleep(30)
                    continue

                # Only evaluate during session hours
                if phoenix_in_session(now):
                    if phoenix_new_h1_bar_closed():
                        phoenix_try_entry()

                # Periodic status log
                if current_ts - _last_status_log >= STATUS_LOG_INTERVAL_SEC:
                    tick = mt5.symbol_info_tick(SYMBOL)
                    bid = tick.bid if tick else 0.0
                    ask = tick.ask if tick else 0.0
                    pos = get_position_ticket()
                    pos_str = f"t={pos}" if pos else "FLAT"
                    logger.info("PHOENIX STATUS | entries=%d/%d | bid=%.5f ask=%.5f | %s",
                                state.entries_today, MAX_TRADES_PER_DAY_PHOENIX, bid, ask, pos_str)
                    _last_status_log = current_ts

            else:
                # ================================================================
                # SCALPING MODE — Multi-TF signal evaluation
                # ================================================================

                # Session check
                if not is_in_scalp_session(now_utc):
                    open_ticket = get_position_ticket()
                    if open_ticket:
                        logger.info("Outside session — closing %s", open_ticket)
                        close_position(open_ticket, sym_info)
                    time.sleep(30)
                    continue

                # HTF: Refresh M15 trend (every 60s)
                if current_ts - m15_trend_time > 60:
                    m15_trend_cache = get_m15_trend()
                    m15_trend_time = current_ts
                    if m15_trend_cache:
                        logger.info("M15 trend: %s", m15_trend_cache)

                if m15_trend_cache is None or m15_trend_cache == "NEUTRAL":
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                # MTF: Refresh M5 structure
                if current_ts - m5_setup_time > M5_REFRESH_SEC:
                    m5_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100)
                    if m5_rates is not None and len(m5_rates) >= M5_EMA_SLOW + 5:
                        m5_setup_cache = get_m5_pullback_structure(m5_rates, m15_trend_cache)
                    m5_setup_time = current_ts

                has_setup, _, m5_atr, setup_msg = m5_setup_cache
                if not has_setup:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                # Check for open position
                open_ticket = get_position_ticket()
                if open_ticket:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                # Spread check
                tick = mt5.symbol_info_tick(SYMBOL)
                if not tick:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue
                spread = tick.ask - tick.bid
                if sym_info.get("point", 0.01) > 0:
                    spread_pips = spread / (sym_info["point"] * 10)
                    if spread_pips > MAX_SPREAD_POINTS / 10.0:
                        time.sleep(LOOP_SLEEP_SEC)
                        continue

                # LTF: Get M1 micro-breakout
                m1_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 30)
                if m1_rates is None or len(m1_rates) < 10:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                should_enter, entry, sl, tp, entry_msg = get_m1_micro_breakout(m1_rates, m15_trend_cache, m5_atr)
                if not should_enter:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                # Place the scalping trade
                logger.info("SIGNAL: %s", entry_msg)

                account_info = mt5.account_info()
                if not account_info:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                sl_distance = abs(sl - entry)
                lot = calculate_lot_size(account_info.balance, sl_distance, sym_info)

                if entry < sl:  # BUY (entry below SL)
                    order_type = mt5.ORDER_TYPE_BUY
                else:  # SELL
                    order_type = mt5.ORDER_TYPE_SELL

                ticket = place_scalp_order(order_type, lot, entry, sl, tp, sym_info)
                if ticket:
                    state.session_trades += 1
                    state.total_trades += 1
                    state.save()
                    logger.info("TRADE PLACED | %s lot=%.2f R:R=1:%.1f | Session: %d/%d",
                                "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
                                lot, ATR_TP_MULT / ATR_SL_MULT,
                                state.session_trades, MAX_TRADES_PER_SESSION)
                    time.sleep(30)  # Cooldown after entry

                # Track completed trades
                if current_ts - last_state_save > 300:
                    now_dt = datetime.now()
                    from_time = now_dt - timedelta(hours=24)
                    history = mt5.history_deals_get(from_time, now_dt, group=str(MAGIC))
                    if history:
                        closed_buys = [d for d in history if d.magic == MAGIC and d.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)]
                        entry_deals = [d for d in closed_buys if d.entry == mt5.DEAL_ENTRY_IN]
                        if entry_deals:
                            for pid in set(d.position_id for d in entry_deals):
                                pos_deals = [d for d in closed_buys if d.position_id == pid]
                                total_profit = sum(d.profit for d in pos_deals if d.profit != 0)
                                if total_profit != 0:
                                    if pid not in state._tracked_positions:
                                        state._tracked_positions.add(pid)
                                        if total_profit > 0:
                                            state.wins += 1
                                            state.consecutive_losses = 0
                                            logger.info("TRADE WIN | pos=%s +$%.2f | Wins=%d", pid, total_profit, state.wins)
                                        else:
                                            state.losses += 1
                                            logger.info("TRADE LOSS | pos=%s $%.2f | Losses=%d",
                                                        pid, total_profit, state.losses)
                        state.save()
                        last_state_save = current_ts

            time.sleep(LOOP_SLEEP_SEC)

    except KeyboardInterrupt:
        logger.info("Shutdown by user")
        close_all_open_positions(sym_info)
    except Exception as e:
        logger.error("Fatal: %s\n%s", e, traceback.format_exc())
        close_all_open_positions(sym_info)
        raise
    finally:
        state.save()
        logger.info("Bot stopped. Total trades: %d (W:%d L:%d)", state.total_trades, state.wins, state.losses)
        mt5.shutdown()

if __name__ == "__main__":
    main()
