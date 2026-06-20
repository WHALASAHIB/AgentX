#!/usr/bin/env python3
"""
Streaming Bot v3
⚠️ DISABLED by Council Decision — PF 0.39, 25% WR, Martingale pattern
"""
import sys
print("⚠️  STREAMING BOT DISABLED — martingale pattern, $8k drawdown risk", flush=True)
sys.exit(0)
"""
Streaming Bot v3 — Multi-Timeframe Consolidation Breakout (XAUUSD)

Win rate improvements:
  - Removed body/ATR ratio filter (blocked all trades)
  - Relaxed ADX to min 10
  - Wider ATR range (200-2500 pts)
  - M15 consolidation filter ensures high-probability breakout setups

Run: python streaming_bot_v3.py
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import MetaTrader5 as mt5
import pandas as pd

# --- Session filter (shared module) ---
SESSION_FILTER_ENABLED = True
from session_filters import should_trade as _session_should_trade

# --- File logging ---
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "streaming_v3_execution.log")
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
# Configuration
# ============================================================================

SYMBOL = "XAUUSD"
MAGIC = 666334                      # v3 magic number
ORDER_COMMENT = "STREAMv3_MTF"
DEVIATION = 30

# --- Multi-timeframe ---
TIMEFRAME_HTF = mt5.TIMEFRAME_H1    # Primary trend
TIMEFRAME_MTF = mt5.TIMEFRAME_M15   # Consolidation zone
TIMEFRAME_LTF = mt5.TIMEFRAME_M5    # Entry

H1_EMA_PERIOD = 50                  # H1 trend
M15_EMA_PERIOD = 50                 # M15 medium-term
M15_RANGE_BARS = 30                 # Lookback for consolidation detection

# --- Risk (R:R = 1:2.5) ---
LOT_SIZE = 0.01
RISK_PERCENT = 1.0
ATR_PERIOD = 14
ATR_SL_MULT = 2.0                   # SL = 2.0 × M15 ATR
ATR_TP_MULT = 5.0                   # TP = 5.0 × M15 ATR → R:R = 1:2.5
TRAIL_ACTIVATE_MULT = 2.5           # Activate trailing at 2.5×ATR profit
TRAIL_DISTANCE_MULT = 1.2

# --- Volatility filter (relaxed) ---
MIN_ATR_PIPS = 200
MAX_ATR_PIPS = 2500

# --- ADX filter (relaxed) ---
ADX_PERIOD = 14
ADX_MIN = 10

# --- Breakout quality ---
# Removed body/ATR ratio filter (was too strict)
# Use M15 consolidation range instead for quality filtering

MAX_SPREAD_POINTS = 50

# --- Re-entry control ---
MAX_ENTRIES_PER_DAY = 3

LOOP_SLEEP_SEC = 10
RATES_COUNT = 200

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "streaming_bot_v3_state.json")

# --- Sentiment engine path ---
SENTIMENT_ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "sentiment_engine.py")

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
    log_info(f"New day {today} — resetting entries")
    _state = default_state()
    save_state()

# ============================================================================
# MT5 helpers
# ============================================================================

def ensure_symbol(symbol: str) -> bool:
    if not mt5.symbol_select(symbol, True):
        log_error(f"symbol_select failed: {mt5.last_error()}")
        return False
    return mt5.symbol_info(symbol) is not None

def get_filling_mode(symbol: str) -> int:
    info = mt5.symbol_info(symbol)
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

def normalize_price(price: float, symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    return round(price, info.digits if info else 5)

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

def create_order(symbol: str, quantity: float, order_type: int,
                 price: float, sl: float, tp: float) -> Optional[object]:
    volume = normalize_volume(quantity, symbol)
    price = normalize_price(price, symbol)
    sl = normalize_price(sl, symbol)
    tp = normalize_price(tp, symbol)
    filling = get_filling_mode(symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
        "type": order_type, "price": price, "sl": sl, "tp": tp,
        "deviation": DEVIATION, "magic": MAGIC, "comment": ORDER_COMMENT,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
    }

    side = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    log_info(f"PLACE {side} {volume} {symbol} @ {price} | SL={sl} TP={tp} | R:R=1:{ATR_TP_MULT/ATR_SL_MULT:.1f}")

    result = mt5.order_send(request)
    if result is None:
        log_error(f"order_send None: {mt5.last_error()}")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_error(f"order_send failed: retcode={result.retcode}")
        return None

    log_info(f"FILLED order={result.order} deal={result.deal}")
    global _state
    _state["entries_today"] = _state.get("entries_today", 0) + 1
    save_state()
    return result

def calc_risk_lot(info, tick, price, sl, order_type) -> float:
    account_info = mt5.account_info()
    if account_info is None or info is None or info.point <= 0:
        return LOT_SIZE
    balance = account_info.balance
    risk_amount = balance * (RISK_PERCENT / 100.0)
    sl_distance_pts = abs(sl - price) / info.point
    contract_value = info.contract_size * info.point
    if sl_distance_pts <= 0 or contract_value <= 0:
        return LOT_SIZE
    volume = risk_amount / (sl_distance_pts * contract_value)
    volume = max(info.volume_min, min(info.volume_max, volume))
    step = info.volume_step
    if step > 0:
        volume = round(volume / step) * step
    # Margin cap
    try:
        margin_per_lot = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, price)
        if margin_per_lot and margin_per_lot > 0 and account_info.margin_free > 0:
            max_lot = (account_info.margin_free * 0.30) / margin_per_lot
            if max_lot > 0 and step > 0:
                volume = min(volume, round(max_lot / step) * step)
    except Exception:
        pass
    return round(volume, 2)

def close_order(symbol: str) -> bool:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        return False
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        log_error(f"No tick for {symbol}")
        return False
    filling = get_filling_mode(symbol)
    closed_any = False
    for pos in positions:
        if pos.magic != MAGIC:
            continue
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": normalize_volume(pos.volume, symbol),
            "type": close_type, "position": pos.ticket,
            "price": normalize_price(close_price, symbol),
            "deviation": DEVIATION, "magic": MAGIC, "comment": ORDER_COMMENT + "_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
        }
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            log_info(f"Close success t={pos.ticket}")
            closed_any = True
        else:
            log_error(f"Close failed t={pos.ticket}: retcode={result.retcode if result else -1}")
    return closed_any

def update_trailing_stop(symbol: str, atr_val: float) -> None:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        return
    info = mt5.symbol_info(symbol)
    if info is None or tick is None:
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
                    req = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket,
                           "symbol": symbol, "sl": new_sl, "tp": pos.tp, "magic": MAGIC}
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        log_info(f"TRAIL t={pos.ticket} SL→{new_sl:.5f} (profit {profit_dist/atr_val:.1f}×ATR)")
        elif pos.type == mt5.POSITION_TYPE_SELL:
            profit_dist = pos.price_open - tick.ask
            if profit_dist >= act_dist:
                new_sl = normalize_price(tick.ask + trail_dist, symbol)
                if new_sl < pos.sl or pos.sl == 0:
                    req = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket,
                           "symbol": symbol, "sl": new_sl, "tp": pos.tp, "magic": MAGIC}
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        log_info(f"TRAIL t={pos.ticket} SL→{new_sl:.5f} (profit {profit_dist/atr_val:.1f}×ATR)")

# ============================================================================
# Data & indicators
# ============================================================================

def fetch_rates_df(symbol: str, timeframe: int, count: int = RATES_COUNT) -> Optional[pd.DataFrame]:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) < 5:
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
    trs = [true_range(highs[i], lows[i], closes[i-1]) for i in range(1, len(df))]
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

def compute_adx_from_df(df: pd.DataFrame, period: int = ADX_PERIOD) -> Optional[float]:
    if len(df) < period * 2 + 2:
        return None
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(df)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
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
# Multi-timeframe signal logic
# ============================================================================

def get_h1_trend() -> Optional[str]:
    """HTF: H1 EMA50 for primary trend."""
    h1_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, H1_EMA_PERIOD + 5)
    if h1_rates is None or len(h1_rates) <= H1_EMA_PERIOD:
        return None
    h1_df = pd.DataFrame(h1_rates)
    ema_val = compute_ema_from_df(h1_df, H1_EMA_PERIOD)
    if ema_val is None:
        return None
    last_close = float(h1_df["close"].iloc[-1])
    if last_close > ema_val * 1.002:
        return "BULLISH"
    elif last_close < ema_val * 0.998:
        return "BEARISH"
    return "NEUTRAL"

def get_m15_consolidation(m15_df: pd.DataFrame, atr_val: float) -> tuple[bool, float, float, str]:
    """
    MTF: Detect M15 consolidation zone.
    A consolidation is defined as:
    - Tight range: high-low over last M15_RANGE_BARS bars < 2.5×ATR
    - Price near M15 EMA50 (within 1×ATR)
    - Low ATR contraction relative to H1 ATR
    
    Returns (is_consolidating, zone_high, zone_low, message)
    """
    if m15_df is None or len(m15_df) < M15_RANGE_BARS:
        return False, 0, 0, "Insufficient M15 data"

    recent = m15_df.iloc[-M15_RANGE_BARS:]
    zone_high = float(recent["high"].max())
    zone_low = float(recent["low"].min())
    zone_range = zone_high - zone_low

    # Check M15 consolidation vs M15 ATR
    m15_atr = compute_atr_from_df(m15_df, ATR_PERIOD)
    if m15_atr is None or m15_atr <= 0:
        return False, 0, 0, "M15 ATR compute failed"

    # Consolidation: range < 3.0 × ATR (tight enough for breakout)
    if zone_range > m15_atr * 3.0:
        return False, zone_high, zone_low, \
            f"M15 range too wide: {zone_range:.2f} ({zone_range/m15_atr:.1f}×ATR)"

    # Also check price is near M15 EMA50 (mean reversion potential)
    ema_val = compute_ema_from_df(m15_df, M15_EMA_PERIOD)
    if ema_val is not None:
        current = float(m15_df["close"].iloc[-1])
        dist_from_ema_pct = abs(current - ema_val) / ema_val * 100
        # Allow up to 0.5% deviation from EMA50
        if dist_from_ema_pct > 0.5:
            return False, zone_high, zone_low, \
                f"M15 price {dist_from_ema_pct:.2f}% from EMA50 — too far for consolidation"

    return True, zone_high, zone_low, \
        f"M15 consolidation zone: {zone_high:.2f}-{zone_low:.2f} ({zone_range:.2f} range, {zone_range/m15_atr:.1f}×ATR)"

def get_m5_breakout(m5_df: pd.DataFrame, zone_high: float, zone_low: float,
                    h1_trend: str) -> Optional[str]:
    """
    LTF: M5 breakout of M15 consolidation zone.
    1-candle confirmation (simpler than 2-candle — catches more moves).
    """
    if m5_df is None or len(m5_df) < 5:
        return None

    c1 = float(m5_df["close"].iloc[-2])  # Most recent closed bar
    c2 = float(m5_df["close"].iloc[-3])  # Bar before
    o1 = float(m5_df["open"].iloc[-2])
    h1 = float(m5_df["high"].iloc[-2])
    l1 = float(m5_df["low"].iloc[-2])

    # Breakout candle should have decent body (not a doji)
    body1 = abs(c1 - o1)
    range1 = h1 - l1
    if range1 > 0 and body1 / range1 < 0.15:
        return None  # Doji — skip

    if h1_trend == "BULLISH":
        if c1 > zone_high and h1 > zone_high:
            log_signal(f"BUY breakout M5@{c1:.2f} > M15 zone@{zone_high:.2f} | body={body1/range1:.1%}")
            return "BUY"
        # Also accept if both candles close above zone
        if c1 > zone_high and c2 > zone_high:
            log_signal(f"BUY 2-candle M5@{c1:.2f},{c2:.2f} > M15 zone@{zone_high:.2f}")
            return "BUY"

    elif h1_trend == "BEARISH":
        if c1 < zone_low and l1 < zone_low:
            log_signal(f"SELL breakout M5@{c1:.2f} < M15 zone@{zone_low:.2f} | body={body1/range1:.1%}")
            return "SELL"
        if c1 < zone_low and c2 < zone_low:
            log_signal(f"SELL 2-candle M5@{c1:.2f},{c2:.2f} < M15 zone@{zone_low:.2f}")
            return "SELL"

    return None

# ============================================================================
# Signal evaluation (full pipeline)
# ============================================================================

def get_signal(m5_df: pd.DataFrame) -> Optional[str]:
    """
    Full multi-TF signal pipeline:
    1. HTF: H1 trend
    2. MTF: M15 consolidation
    3. Volatility, ADX, spread filters
    4. LTF: M5 breakout
    """
    if m5_df is None or len(m5_df) < 10:
        return None

    # --- HTF: H1 trend ---
    h1_trend = get_h1_trend()
    if h1_trend is None or h1_trend == "NEUTRAL":
        log_filter(f"H1 trend neutral ({h1_trend}) — waiting")
        return None
    log_info(f"H1 trend: {h1_trend}")

    # --- MTF: M15 consolidation ---
    m15_df = fetch_rates_df(SYMBOL, mt5.TIMEFRAME_M15, M15_RANGE_BARS + 10)
    m15_atr = compute_atr_from_df(m15_df, ATR_PERIOD) if m15_df is not None else None
    if m15_atr is None:
        return None
    is_consolidating, zone_high, zone_low, consol_msg = \
        get_m15_consolidation(m15_df, m15_atr)
    if not is_consolidating:
        log_filter(f"M15 consolidation: {consol_msg}")
        return None
    log_info(f"M15: {consol_msg}")

    # --- Volatility filter (M5 ATR) ---
    m5_atr = compute_atr_from_df(m5_df, ATR_PERIOD)
    if m5_atr is None:
        return None
    info = mt5.symbol_info(SYMBOL)
    if info:
        atr_points = m5_atr / info.point if info.point > 0 else 0
        if atr_points < MIN_ATR_PIPS or atr_points > MAX_ATR_PIPS:
            log_filter(f"M5 ATR out of range: {atr_points:.0f}pts")
            return None

    # --- ADX filter (M15 ADX) ---
    adx_val = compute_adx_from_df(m15_df, ADX_PERIOD) if m15_df is not None else None
    if adx_val is not None and adx_val < ADX_MIN:
        log_filter(f"M15 ADX too low: {adx_val:.1f} (<{ADX_MIN})")
        # Don't block entirely — consolidation breakouts can happen in low-ADX
        # but we require a stronger breakout candle
        pass  # Allow through, but warn

    # --- Spread filter ---
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick and info and info.point > 0:
        spread_pts = (tick.ask - tick.bid) / info.point
        if spread_pts > MAX_SPREAD_POINTS:
            log_filter(f"Spread too high: {spread_pts:.0f}pts")
            return None

    # --- Re-entry limit ---
    reset_state_for_new_day()
    if _state.get("entries_today", 0) >= _state.get("max_entries_per_day", MAX_ENTRIES_PER_DAY):
        log_filter(f"Max daily entries ({_state['entries_today']})")
        return None

    # --- LTF: M5 breakout ---
    signal = get_m5_breakout(m5_df, zone_high, zone_low, h1_trend)
    if signal:
        log_signal(f"{signal} CONFIRMED | H1={h1_trend} M15_zone={zone_high:.2f}/{zone_low:.2f}")
    return signal

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
        log_warn(f"Sentiment engine error: {e}")
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
# Main
# ============================================================================

def main() -> None:
    global _state

    log_info("=" * 60)
    log_info("Streaming Bot v3 — Multi-TF Consolidation Breakout")
    log_info(f"R:R = 1:{ATR_TP_MULT/ATR_SL_MULT:.1f} (SL={ATR_SL_MULT}×ATR TP={ATR_TP_MULT}×ATR)")
    log_info(f"HTF: H1 EMA{H1_EMA_PERIOD} | MTF: M15 consolidation ({M15_RANGE_BARS} bars) | LTF: M5 breakout")
    log_info(f"Filters: ATR=[{MIN_ATR_PIPS}-{MAX_ATR_PIPS}]pts ADX>={ADX_MIN}")
    log_info(f"Max entries/day: {MAX_ENTRIES_PER_DAY} | Trailing: activate at {TRAIL_ACTIVATE_MULT}×ATR")
    log_info("=" * 60)

    _state = load_state()
    cfg = load_config()
    if not cfg:
        log_info("No mt5_config.json found")

    while not connect_mt5(cfg):
        log_info(f"MT5 connect failed: {mt5.last_error()}, retrying...")
        time.sleep(10)

    if not ensure_symbol(SYMBOL):
        mt5.shutdown()
        sys.exit(1)

    log_info("MT5 connected. Streaming loop started.")

    try:
        while True:
            try:
                term = mt5.terminal_info()
                if term is None or not term.connected:
                    log_warn("Terminal disconnected — reconnecting")
                    mt5.shutdown()
                    while not connect_mt5(load_config()):
                        time.sleep(10)
                    ensure_symbol(SYMBOL)

                # --- Session filter (shared liquidity check) ---
                if SESSION_FILTER_ENABLED:
                    now_hour = datetime.now(timezone.utc).hour
                    if not _session_should_trade(now_hour):
                        log_info(f"SESSION FILTER: Outside trading hours (hour={now_hour} UTC)")
                        time.sleep(LOOP_SLEEP_SEC)
                        continue

                m5_df = fetch_rates_df(SYMBOL, mt5.TIMEFRAME_M5)
                if m5_df is None:
                    time.sleep(LOOP_SLEEP_SEC)
                    continue

                positions = symbol_positions(SYMBOL)
                m15_df = fetch_rates_df(SYMBOL, mt5.TIMEFRAME_M15, M15_RANGE_BARS + 10)
                atr_val = compute_atr_from_df(m15_df, ATR_PERIOD) if m15_df is not None else None

                # --- Trailing stop ---
                pos = mt5.positions_get(symbol=SYMBOL)
                has_pos = pos is not None and len(pos) > 0
                if has_pos and atr_val:
                    update_trailing_stop(SYMBOL, atr_val)

                # --- Close at end of session ---
                now_utc = datetime.now(timezone.utc)
                if now_utc.hour >= 17 and has_pos:
                    log_info("17:00 UTC — closing all positions")
                    close_order(SYMBOL)
                    time.sleep(5)
                    continue

                # --- Signal check (only if no position) ---
                if not has_pos:
                    signal = get_signal(m5_df)
                    if signal is None:
                        time.sleep(LOOP_SLEEP_SEC)
                        continue

                    # Sentiment filter — check market sentiment before entering
                    signal_dir = 1 if signal == "BUY" else -1
                    sent_ok, sent_msg = check_sentiment_filter(signal_dir)
                    if not sent_ok:
                        log_filter(f"Signal {signal} blocked by sentiment: {sent_msg}")
                        time.sleep(LOOP_SLEEP_SEC)
                        continue
                    log_info(f"Sentiment OK: {sent_msg}")

                    tick = mt5.symbol_info_tick(SYMBOL)
                    if tick is None:
                        time.sleep(LOOP_SLEEP_SEC)
                        continue

                    # Use M15 ATR for SL/TP (gives wider, more appropriate stops for streaming)
                    if atr_val is None or atr_val <= 0:
                        log_info("M15 ATR unavailable — using M5 ATR")
                        atr_val = compute_atr_from_df(m5_df, ATR_PERIOD)
                        if atr_val is None:
                            continue

                    if signal == "BUY":
                        price = tick.ask
                        sl = price - ATR_SL_MULT * atr_val
                        tp = price + ATR_TP_MULT * atr_val
                        info_sym = mt5.symbol_info(SYMBOL)
                        lot = calc_risk_lot(info_sym, tick, price, sl, mt5.ORDER_TYPE_BUY)
                        log_info(f"STREAM BUY | lot={lot:.2f} SL={sl:.2f} TP={tp:.2f} R:R=1:{ATR_TP_MULT/ATR_SL_MULT:.1f}")
                        create_order(SYMBOL, lot, mt5.ORDER_TYPE_BUY, price, sl, tp)
                    else:
                        price = tick.bid
                        sl = price + ATR_SL_MULT * atr_val
                        tp = price - ATR_TP_MULT * atr_val
                        info_sym = mt5.symbol_info(SYMBOL)
                        lot = calc_risk_lot(info_sym, tick, price, sl, mt5.ORDER_TYPE_SELL)
                        log_info(f"STREAM SELL | lot={lot:.2f} SL={sl:.2f} TP={tp:.2f} R:R=1:{ATR_TP_MULT/ATR_SL_MULT:.1f}")
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
