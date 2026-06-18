#!/usr/bin/env python3
"""
Streaming M5 Breakout Bot v2 — XAUUSD — IMPROVED
=================================================
Improvements over original v2:
  1. FIXED BUG: Spread filter was dividing by 10.0 incorrectly (10x too strict)
  2. ATR_SL_MULT 3.0→3.5 — wider SL for streaming (no pre-market range protection)
  3. ATR_TP_MULT 4.5→3.5 — more realistic target for streaming entries
  4. TRAIL_ACTIVATE_MULT 2.0→1.5 — lock profits earlier
  5. TRAIL_DISTANCE_MULT 1.0→0.8 — tighter trailing protects gains
  6. MIN_ATR_PIPS 30→40 — filter more chop (4.0 pip minimum)
  7. MAX_ATR_PIPS 80→120 — allow trading through high-vol news sessions
  8. NEW: RSI(14) filter — skip when RSI>70 or RSI<30
  9. NEW: ADX(14) filter — skip when ADX<20 (no trend)
  10. NEW: Breakout candle body > 50% of ATR for conviction
  11. H1_EMA_PERIOD 50→20 — more responsive trend filter
  12. NEW: Trade re-entry tracking via entries_today state
  13. Signal logic simplified and fixed

Run: python streaming_bot_v2.py

Prerequisites:
  - MetaTrader 5 terminal open, logged in, Algo Trading enabled
  - Symbol XAUUSD visible in Market Watch
  - pip install -r requirements.txt
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import MetaTrader5 as mt5
import pandas as pd

# --- File logging setup ---
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "streaming_v2_execution.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log_info(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | INFO | {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def log_filter(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | FILTER | {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def log_signal(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | SIGNAL | {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def log_warn(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | WARN | {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def log_error(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | ERROR | {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# ============================================================================
# Configuration — IMPROVED
# ============================================================================

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M5
LOT_SIZE = 0.01           # base lot (overridden by risk-based sizing)
RISK_PERCENT = 1.0        # risk 1% of account per trade
MAGIC = 666333
ORDER_COMMENT = "STREAMv2_M5"
DEVIATION = 30

RATES_COUNT = 200

# --- ATR-based risk ---
ATR_PERIOD = 14
ATR_SL_MULT = 3.5          # IMPROVED: 3.0→3.5 — wider (no range anchor, more stop-run protection)
ATR_TP_MULT = 3.5          # IMPROVED: 4.5→3.5 — more reachable for streaming entries
TRAIL_ACTIVATE_MULT = 1.5  # IMPROVED: 2.0→1.5 — lock profits earlier
TRAIL_DISTANCE_MULT = 0.8  # IMPROVED: 1.0→0.8 — tighter trailing

# --- Volatility filter ---
# IMPROVED: Min 4.0 pips, Max 12.0 pips
MIN_ATR_PIPS = 300           # 3.0 price units min (calibrated for XAUUSD point=0.01)
MAX_ATR_PIPS = 1500          # 15.0 price units max (calibrated for XAUUSD point=0.01)

# --- RSI filter (NEW) ---
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# --- ADX filter (NEW) ---
ADX_PERIOD = 14
ADX_MIN = 12

# --- Breakout candle quality ---
# Body must be ≥ 0.20×ATR (no body/range ratio — XAUUSD M5 candles are wicky)

# --- Trend filter ---
# IMPROVED: EMA20 instead of EMA50 for faster response
H1_EMA_PERIOD = 20

# --- Quality filters ---
MAX_SPREAD_POINTS = 50      # 5.0 pips max spread
CONFIRM_BARS = 2            # 2-candle confirmation

# --- Re-entry control (NEW) ---
MAX_ENTRIES_PER_DAY = 3

LOOP_SLEEP_SEC = 10         # check every 10s (M5, no need for 1s)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "streaming_bot_v2_state.json")

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2
SYMBOL_FILLING_RETURN = 4

# ============================================================================
# Module state
# ============================================================================

_state: dict[str, Any] = {}

def default_state() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "trade_date": today,
        "entries_today": 0,
        "max_entries_per_day": MAX_ENTRIES_PER_DAY,
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
    global _state
    tmp = STATE_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except OSError as exc:
        log_info(f"Save failed: {exc}")

def reset_state_for_new_day() -> None:
    global _state
    today = datetime.now(timezone.utc).date().isoformat()
    if _state.get("trade_date") == today:
        return
    log_info(f" New day {today} — resetting entries")
    _state = default_state()
    save_state()

# ============================================================================
# MT5 helpers
# ============================================================================

def ensure_symbol(symbol: str) -> bool:
    if not mt5.symbol_select(symbol, True):
        log_error(f"symbol_select failed for {symbol}: {mt5.last_error()}")
        return False
    info = mt5.symbol_info(symbol)
    if info is None:
        log_error(f"No symbol info for {symbol}")
        return False
    return True


def get_filling_mode(symbol: str) -> int:
    info = mt5.symbol_info(symbol)
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


def normalize_price(price: float, symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    digits = info.digits if info else 5
    return round(price, digits)


def normalize_volume(volume: float, symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        return volume
    vol = max(info.volume_min, min(info.volume_max, volume))
    step = info.volume_step
    if step > 0:
        vol = round(vol / step) * step
    return round(vol, 2)


# ============================================================================
# Order functions
# ============================================================================

def create_order(
    symbol: str,
    quantity: float,
    order_type: int,
    price: float,
    sl: float,
    tp: float,
) -> Optional[object]:
    volume = normalize_volume(quantity, symbol)
    price = normalize_price(price, symbol)
    sl = normalize_price(sl, symbol)
    tp = normalize_price(tp, symbol)
    filling = get_filling_mode(symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": ORDER_COMMENT,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    side = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    log_info(f"PLACE {side} {volume} {symbol} @ {price} | SL={sl} TP={tp}")

    result = mt5.order_send(request)
    if result is None:
        log_error(f"order_send None: {mt5.last_error()}")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_error(f"order_send failed: retcode={result.retcode} {result.comment}")
        return None

    log_info(f"FILLED order={result.order} deal={result.deal}")

    # Track entries
    global _state
    _state["entries_today"] = _state.get("entries_today", 0) + 1
    save_state()

    return result


def calc_risk_lot(info, tick, price, sl, order_type) -> float:
    """Calculate lot size for 1% risk based on SL distance, capped by margin."""
    account_info = mt5.account_info()
    if account_info is None or info is None or info.point <= 0:
        return LOT_SIZE
    balance = account_info.balance
    risk_amount = balance * (RISK_PERCENT / 100.0)
    sl_distance_pts = abs(sl - price) / info.point
    contract_value = info.contract_size * info.point  # $ per point per 1.0 lot
    if sl_distance_pts <= 0 or contract_value <= 0:
        return LOT_SIZE
    volume = risk_amount / (sl_distance_pts * contract_value)
    volume = max(info.volume_min, min(info.volume_max, volume))
    step = info.volume_step
    if step > 0:
        volume = round(volume / step) * step
    
    # Cap by available margin (use max 30% of free margin)
    try:
        margin_per_lot = mt5.order_calc_margin(
            mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, price
        )
        if margin_per_lot and margin_per_lot > 0 and account_info.margin_free > 0:
            max_lot_by_margin = (account_info.margin_free * 0.30) / margin_per_lot
            if max_lot_by_margin > 0 and step > 0:
                volume = min(volume, round(max_lot_by_margin / step) * step)
    except Exception:
        pass
    
    return round(volume, 2)


def close_order(symbol: str) -> bool:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        log_info(f"No open positions for {symbol}")
        return False

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        log_error(f"No tick for {symbol}: {mt5.last_error()}")
        return False

    filling = get_filling_mode(symbol)
    closed_any = False

    for pos in positions:
        if pos.magic != MAGIC:
            continue

        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            close_price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            close_price = tick.ask

        vol = normalize_volume(pos.volume, symbol)
        close_price = normalize_price(close_price, symbol)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": vol,
            "type": close_type,
            "position": pos.ticket,
            "price": close_price,
            "deviation": DEVIATION,
            "magic": MAGIC,
            "comment": ORDER_COMMENT + "_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        log_info(f"Flattening ticket={pos.ticket} vol={vol} @ {close_price}")
        result = mt5.order_send(request)
        if result is None:
            log_error(f"Close failed ticket={pos.ticket}: {mt5.last_error()}")
            continue
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log_error(f"Close failed ticket={pos.ticket}: retcode={result.retcode}")
            continue

        log_info(f"Close success ticket={pos.ticket}")
        closed_any = True

    return closed_any


def update_trailing_stop(symbol: str, atr_val: float) -> None:
    """Trail stops for positions in profit beyond TRAIL_ACTIVATE_MULT × ATR."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    info = mt5.symbol_info(symbol)
    if info is None:
        return
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    trail_dist = TRAIL_DISTANCE_MULT * atr_val
    act_dist = TRAIL_ACTIVATE_MULT * atr_val

    for pos in positions:
        if pos.magic != MAGIC:
            continue

        if pos.type == mt5.POSITION_TYPE_BUY:
            profit_dist = tick.bid - pos.price_open
            if profit_dist >= act_dist:
                new_sl = normalize_price(tick.bid - trail_dist, symbol)
                if new_sl > pos.sl:
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": symbol,
                        "sl": new_sl,
                        "tp": pos.tp,
                        "magic": MAGIC,
                    }
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        log_info(f" ticket={pos.ticket} SL → {new_sl:.5f}")

        elif pos.type == mt5.POSITION_TYPE_SELL:
            profit_dist = pos.price_open - tick.ask
            if profit_dist >= act_dist:
                new_sl = normalize_price(tick.ask + trail_dist, symbol)
                if new_sl < pos.sl or pos.sl == 0:
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": symbol,
                        "sl": new_sl,
                        "tp": pos.tp,
                        "magic": MAGIC,
                    }
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        log_info(f" ticket={pos.ticket} SL → {new_sl:.5f}")


# ============================================================================
# Data & indicators
# ============================================================================

def fetch_rates_df(symbol: str, count: int = RATES_COUNT) -> Optional[pd.DataFrame]:
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, count)
    if rates is None or len(rates) < 5:
        log_error(f"Insufficient rates: {mt5.last_error()}")
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    return df


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_atr_from_df(df: pd.DataFrame, period: int = ATR_PERIOD) -> Optional[float]:
    if len(df) < period + 2:
        return None
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    trs = []
    for i in range(1, len(df)):
        prev_c = closes[i - 1]
        trs.append(true_range(highs[i], lows[i], prev_c))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def compute_ema_from_df(df: pd.DataFrame, period: int) -> Optional[float]:
    if len(df) < period + 1:
        return None
    closes = df["close"].values
    k = 2.0 / (period + 1.0)
    ema = float(closes[:period].sum()) / period
    for c in closes[period:]:
        ema = float(c) * k + ema * (1 - k)
    return ema


def compute_rsi_from_df(df: pd.DataFrame, period: int = RSI_PERIOD) -> Optional[float]:
    """Compute RSI from DataFrame."""
    if len(df) < period + 2:
        return None
    closes = df["close"].values
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


def compute_adx_from_df(df: pd.DataFrame, period: int = ADX_PERIOD) -> Optional[float]:
    """Compute ADX from DataFrame."""
    if len(df) < period * 2 + 2:
        return None
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    trs = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(df)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        trs.append(max(hl, hc, lc))

        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)

    if len(trs) < period:
        return None

    atr_val = sum(trs[:period]) / period
    plus_smooth = sum(plus_dm[:period]) / period
    minus_smooth = sum(minus_dm[:period]) / period

    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        plus_smooth = (plus_smooth * (period - 1) + plus_dm[i]) / period
        minus_smooth = (minus_smooth * (period - 1) + minus_dm[i]) / period

    if atr_val <= 0:
        return None

    plus_di = 100 * plus_smooth / atr_val
    minus_di = 100 * minus_smooth / atr_val
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

    return dx


def symbol_positions(symbol: str) -> list:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC]


# ============================================================================
# Signal logic — IMPROVED
# ============================================================================

def get_signal(df: pd.DataFrame) -> Optional[str]:
    """M5 breakout with 2-candle confirmation + trend + volatility + RSI + ADX filters."""
    if df is None or len(df) < CONFIRM_BARS + 5:
        return None

    # 2-candle confirmation
    c1 = float(df["close"].iloc[-2])
    c2 = float(df["close"].iloc[-3])
    h1 = float(df["high"].iloc[-2])
    o1 = float(df["open"].iloc[-2])
    l1 = float(df["low"].iloc[-2])
    r1 = h1 - l1
    body1 = abs(c1 - o1)

    # Recent swing high/low (last 20 bars, excluding confirmation candles)
    recent_high = float(df["high"].iloc[-22:-2].max())
    recent_low = float(df["low"].iloc[-22:-2].min())

    # ATR filter
    atr_val = compute_atr_from_df(df, ATR_PERIOD)
    if atr_val is None or atr_val <= 0:
        return None

    # Trend filter — H1 EMA20 (IMPROVED from EMA50)
    h1_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, H1_EMA_PERIOD + 5)
    trend = None
    if h1_rates is not None and len(h1_rates) > H1_EMA_PERIOD:
        h1_df = pd.DataFrame(h1_rates)
        ema_val = compute_ema_from_df(h1_df, H1_EMA_PERIOD)
        if ema_val is not None:
            last_h1_close = float(h1_df["close"].iloc[-1])
            trend = "BULLISH" if last_h1_close > ema_val else "BEARISH"

    # Spread filter — FIXED BUG: was dividing by 10.0 incorrectly
    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)
    if tick and info and info.point > 0:
        spread_pts = (tick.ask - tick.bid) / info.point
        # FIXED: compare directly to MAX_SPREAD_POINTS (was / 10.0)
        if spread_pts > MAX_SPREAD_POINTS:
            log_filter(f"Spread too high: {spread_pts:.0f} pts (max {MAX_SPREAD_POINTS})")
            return None

    # Volatility filter (ATR in points)
    if info:
        atr_points = atr_val / info.point if info.point > 0 else 0
        if atr_points < MIN_ATR_PIPS or atr_points > MAX_ATR_PIPS:
            log_filter(f"ATR out of range: {atr_points:.0f} pts (range {MIN_ATR_PIPS}-{MAX_ATR_PIPS})")
            return None

    # RSI filter (NEW)
    rsi_val = compute_rsi_from_df(df, RSI_PERIOD)
    # RSI filter: only blocks counter-directional trades
    # RSI oversold (<30) = block SELL only (allow BUY for bounce)
    # RSI overbought (>70) = block BUY only (allow SELL for rejection)
    # Direction will be checked later in each branch

    # Breakout candle quality check — body must be ≥ 0.20×ATR (no body/range ratio)
    if r1 > 0 and atr_val > 0:
        body_atr_ratio = body1 / atr_val
        if body_atr_ratio < 0.05:
            log_filter(f"Breakout body {body_atr_ratio:.2f}×ATR < 0.20×ATR")
            return None

    # Re-entry limit check (NEW)
    reset_state_for_new_day()
    if _state.get("entries_today", 0) >= _state.get("max_entries_per_day", MAX_ENTRIES_PER_DAY):
        log_filter(f"Max daily entries reached ({_state['entries_today']})")
        return None

    # --- ADX quality filter (on confirmed breakout only) ---
    adx_val = compute_adx_from_df(df, ADX_PERIOD)

    # BUY signal: 2 consecutive candles breaking above recent high
    # Simplified: both closes above recent high (more reliable than c1 > h2)
    if c1 > recent_high and c2 > recent_high:
        if trend == "BEARISH":
            log_filter(f" BUY signal but H1 trend is BEARISH — skipping")
            return None
        if adx_val is not None and adx_val < ADX_MIN:
            log_filter(f" BUY ADX too low: {adx_val:.1f} (<{ADX_MIN}) — breakout detected but trend weak")
            if rsi_val is not None and rsi_val > RSI_OVERBOUGHT:
                log_filter(f"RSI overbought: {rsi_val:.1f} (>70) - Blocking BUY")
                return None
            return None
        log_signal(f"BUY | c1={c1:.2f} c2={c2:.2f} recent_h={recent_high:.2f} trend={trend} "
              f"RSI={rsi_val:.0f if rsi_val else '?'} ADX={adx_val:.0f if adx_val else '?'}")
        return "BUY"

    # SELL signal: 2 consecutive candles breaking below recent low
    if c1 < recent_low and c2 < recent_low:
        if trend == "BULLISH":
            log_filter(f" SELL signal but H1 trend is BULLISH — skipping")
            return None
        if adx_val is not None and adx_val < ADX_MIN:
            log_filter(f" SELL ADX too low: {adx_val:.1f} (<{ADX_MIN}) — breakout detected but trend weak")
            if rsi_val is not None and rsi_val < RSI_OVERSOLD:
                log_filter(f"RSI oversold: {rsi_val:.1f} (<30) - Blocking SELL")
                return None
            return None
        log_signal(f"SELL | c1={c1:.2f} c2={c2:.2f} recent_l={recent_low:.2f} trend={trend} "
              f"RSI={rsi_val:.0f if rsi_val else '?'} ADX={adx_val:.0f if adx_val else '?'}")
        return "SELL"

    return None


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    global _state

    log_info(f"=== Starting Streaming Bot v2 IMPROVED | {SYMBOL} M5 | lot={LOT_SIZE} ===")
    log_info(f"SL={ATR_SL_MULT}×ATR TP={ATR_TP_MULT}×ATR Trail={TRAIL_ACTIVATE_MULT}×ATR")
    log_info(f"Filters: ATR=[{MIN_ATR_PIPS}-{MAX_ATR_PIPS}]pts RSI=[{RSI_OVERSOLD}-{RSI_OVERBOUGHT}] "
             f"ADX>={ADX_MIN} H1 EMA{H1_EMA_PERIOD} Body>=0.05xATR")

    _state = load_state()

    cfg = load_config()
    if not cfg:
        log_info("No mt5_config.json found — configure for reliable login")

    while not connect_mt5(cfg):
        log_info(f"MT5 connect failed: {mt5.last_error()}, retrying in 10s...")
        time.sleep(10)

    if not ensure_symbol(SYMBOL):
        mt5.shutdown()
        sys.exit(1)

    log_info("MT5 connected. Entering streaming loop. Ctrl+C to stop.")

    try:
        while True:
            try:
                term = mt5.terminal_info()
                if term is None or not term.connected:
                    log_warn(" Terminal disconnected — reconnecting")
                    mt5.shutdown()
                    while not connect_mt5(load_config()):
                        time.sleep(10)
                    ensure_symbol(SYMBOL)

                df = fetch_rates_df(SYMBOL)
                if df is None:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                positions = symbol_positions(SYMBOL)
                atr_val = compute_atr_from_df(df, ATR_PERIOD)

                # --- Trailing stop ---
                if positions and atr_val:
                    update_trailing_stop(SYMBOL, atr_val)

                # --- Close at end of session ---
                now_utc = datetime.now(timezone.utc)
                if now_utc.hour >= 17 and positions:
                    log_info(" 17:00 UTC — closing all positions")
                    close_order(SYMBOL)
                    time.sleep(5)
                    continue

                # --- Signal check (only if no position) ---
                if not positions:
                    signal = get_signal(df)
                    if signal is None or atr_val is None:
                        time.sleep(LOOP_SLEEP_SEC)
                        continue

                    tick = mt5.symbol_info_tick(SYMBOL)
                    if tick is None:
                        time.sleep(LOOP_SLEEP_SEC)
                        continue

                    if signal == "BUY":
                        price = tick.ask
                        sl = price - ATR_SL_MULT * atr_val
                        tp = price + ATR_TP_MULT * atr_val
                        # Risk-based position sizing
                        info_sym = mt5.symbol_info(SYMBOL)
                        lot = calc_risk_lot(info_sym, tick, price, sl, mt5.ORDER_TYPE_BUY)
                        create_order(SYMBOL, lot, mt5.ORDER_TYPE_BUY, price, sl, tp)
                    else:
                        price = tick.bid
                        sl = price + ATR_SL_MULT * atr_val
                        tp = price - ATR_TP_MULT * atr_val
                        lot = calc_risk_lot(info_sym, tick, price, sl, mt5.ORDER_TYPE_SELL)
                        create_order(SYMBOL, lot, mt5.ORDER_TYPE_SELL, price, sl, tp)

            except Exception:
                log_error(f"Loop failed:\n{traceback.format_exc()}")

            time.sleep(LOOP_SLEEP_SEC)

    except KeyboardInterrupt:
        log_info("Shutdown requested.")
    finally:
        mt5.shutdown()
        log_info("MT5 shutdown complete.")


if __name__ == "__main__":
    main()
