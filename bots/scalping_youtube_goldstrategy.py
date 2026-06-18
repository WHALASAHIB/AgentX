#!/usr/bin/env python3
"""
Scalping Bot v4 — Multi-Timeframe Momentum Scalper (XAUUSD)
============================================================
R:R ≥ 1:2.5 | Multi-TF: M15→M5→M1

Strategy:
  HTF (M15):  EMA50/200 determines primary trend bias
  MTF (M5):   Price pulls back to M5 EMA20/50. Wait for rejection candle.
  LTF (M1):   Micro-breakout of M5 rejection candle's range.

Only trade WITH the higher timeframe trend:
  - BUY: M15 trend BULLISH + M5 pullback to EMA + M1 breakout
  - SELL: M15 trend BEARISH + M5 pullback to EMA + M1 breakout

Risk:
  SL = 2.0 × M5 ATR(14)
  TP = 5.0 × M5 ATR(14)  →  R:R = 1:2.5
  Dynamic position sizing — 1% risk per trade
  No time stop — let trades run to SL/TP

Win rate improvement:
  - RSI(5) instead of RSI(2) — fewer false signals
  - Require M5 structure confirmation before M1 entry
  - Max 2 consecutive losses = stop for session
  - Only trade during high-liquidity windows

Run: python scalping_youtube_goldstrategy.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import MetaTrader5 as mt5

# --- Session filter (shared module) ---
SESSION_FILTER_ENABLED = True
from session_filters import should_trade as _session_should_trade

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# ============================================================================
# Configuration
# ============================================================================

SYMBOL = "XAUUSD"
MAGIC = 999112                      # v4 magic number
ORDER_COMMENT = "SCALPv4_MTF"

# --- Trade sessions (UTC) — tighter, best liquidity only ---
TRADE_SESSIONS = [
    (8, 0,  11, 0),     # London (high liquidity open)
    (13, 30, 16, 0),    # US session (avoid late-day chop)
]

# --- Multi-timeframe parameters ---
# HTF: M15 trend
M15_EMA_FAST = 20
M15_EMA_SLOW = 50
M15_EMA_ULTRA = 200     # Major trend filter

# MTF: M5 structure
M5_EMA_FAST = 20
M5_EMA_SLOW = 50

# LTF: M1 entry
RSI_PERIOD = 5          # More reliable than RSI(2)
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75

ATR_PERIOD = 14

# --- Entry conditions ---
MIN_ATR_PRICE = 0.10    # min M5 ATR in price units (10 pips)

# --- Risk (R:R = 1:2.5) ---
# SL and TP based on M5 ATR for dynamic sizing
ATR_SL_MULT = 2.0       # SL = 2.0 × M5 ATR
ATR_TP_MULT = 5.0       # TP = 5.0 × M5 ATR → R:R = 1:2.5

RISK_PERCENT = 1.0       # 1% risk per trade
DEVIATION = 30
MAX_SPREAD_POINTS = 35   # 3.5 pips max (tighter for scalping)

# --- Loss management (forward test — no limits) ---
MAX_CONSECUTIVE_LOSSES = 999  # No limit during forward testing
MAX_TRADES_PER_SESSION = 999  # No limit during forward testing

# --- Timing ---
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
M5_REFRESH_SEC = 10          # Re-check M5 structure every 10s
HEARTBEAT_INTERVAL = 60

# --- Paths ---
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BOT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "scalping_v4_execution.log")
STATE_FILE = os.path.join(LOG_DIR, "scalping_v4_state.json")

# --- Sentiment engine path ---
SENTIMENT_ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research", "sentiment_engine.py")

# ============================================================================
# Logging
# ============================================================================

logger = logging.getLogger("scalper_v4")
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
        }
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)

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
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("State file corrupt, resetting")

    def reset_session(self, today: date):
        if self.current_session_date != today:
            logger.info("New session day — resetting counters")
            self.consecutive_losses = 0
            self.session_trades = 0
            self.current_session_date = today
            self.paused_till = None
            self.stop_reason = ""

state = BotState()

# ============================================================================
# Indicator functions
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
# Multi-timeframe analysis
# ============================================================================

def get_m15_trend() -> Optional[str]:
    """
    HTF analysis on M15.
    Uses 3 EMAs for robust trend detection:
    - BULLISH: price > EMA20 > EMA50, OR price > EMA200 (strong uptrend)
    - BEARISH: price < EMA20 < EMA50, OR price < EMA200 (strong downtrend)
    - NEUTRAL: mixed signals
    """
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, M15_EMA_SLOW + 20)
    if rates is None or len(rates) < M15_EMA_SLOW + 5:
        return None
    prices = [r['close'] for r in rates]
    ema_fast = calculate_ema(prices, M15_EMA_FAST)
    ema_slow = calculate_ema(prices, M15_EMA_SLOW)
    current = prices[-1]

    # Check ultra-long trend with M15 EMA200
    rates_200 = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, M15_EMA_ULTRA + 10)
    if rates_200 is not None and len(rates_200) > M15_EMA_ULTRA:
        prices_200 = [r['close'] for r in rates_200]
        ema_ultra = calculate_ema(prices_200, M15_EMA_ULTRA)
        if current > ema_ultra * 1.003:
            return "BULLISH"
        if current < ema_ultra * 0.997:
            return "BEARISH"

    # Medium-term trend
    if current > ema_fast > ema_slow:
        return "BULLISH"
    if current < ema_fast < ema_slow:
        return "BEARISH"
    return "NEUTRAL"

def get_m5_pullback_structure(m5_rates: tuple, trend: str) -> tuple[bool, float, float, str]:
    """
    MTF analysis on M5.
    Check if price has pulled back to a key EMA and shows rejection.
    Returns (has_setup, ema_value, atr_value, message)
    """
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
        # In uptrend, price should pullback near EMA20 or EMA50
        near_fast = abs(current - ema_fast) <= atr_val * 0.5
        near_slow = abs(current - ema_slow) <= atr_val * 0.8
        if near_fast or near_slow:
            # Check for rejection candle on M5 (long wick / pin bar)
            upper_wick = last_high - max(m5_rates[-1]['close'], m5_rates[-1]['open'])
            lower_wick = min(m5_rates[-1]['close'], m5_rates[-1]['open']) - last_low
            body = abs(m5_rates[-1]['close'] - m5_rates[-1]['open'])
            candle_range = last_high - last_low

            if candle_range > 0:
                # Bullish rejection: long lower wick (hammer) at EMA support
                if lower_wick > body * 1.5 and upper_wick < body:
                    return True, (ema_fast if near_fast else ema_slow), atr_val, \
                        f"M5 bullish rejection at EMA (lower wick {lower_wick:.2f})"
                # Bullish engulfing at EMA
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
                # Bearish rejection: long upper wick (shooting star) at EMA resistance
                if upper_wick > body * 1.5 and lower_wick < body:
                    return True, (ema_fast if near_fast else ema_slow), atr_val, \
                        f"M5 bearish rejection at EMA (upper wick {upper_wick:.2f})"
                # Bearish engulfing at EMA
                if len(m5_rates) >= 3:
                    prev = m5_rates[-2]
                    if m5_rates[-1]['close'] < m5_rates[-1]['open'] and \
                       prev['close'] > prev['open'] and \
                       abs(m5_rates[-1]['close'] - m5_rates[-1]['open']) > abs(prev['close'] - prev['open']) * 1.2:
                        return True, (ema_fast if near_fast else ema_slow), atr_val, \
                            "M5 bearish engulfing at EMA"
            return False, (ema_fast if near_fast else ema_slow), atr_val, "Near EMA but no rejection"

    return False, 0, atr_val, "No pullback setup"

def get_m1_micro_breakout(m1_rates: tuple, trend: str, m5_atr: float) -> tuple[bool, float, float, str]:
    """
    LTF entry on M1.
    Look for micro-breakout of the M5 rejection candle's range.
    Returns (should_enter, entry_price, sl_price, tp_price, message)
    """
    if m1_rates is None or len(m1_rates) < 5:
        return False, 0, 0, 0, "Insufficient M1 data"

    last = m1_rates[-1]
    prev = m1_rates[-2]
    current_close = last['close']
    current_high = last['high']
    current_low = last['low']

    # M1 ATR for dynamic sizing
    m1_atr = calculate_atr(m1_rates, ATR_PERIOD)
    if m1_atr <= 0:
        return False, 0, 0, 0, "M1 ATR zero"

    # RSI(5) on M1 for momentum
    m1_rsi = calculate_rsi(m1_rates, RSI_PERIOD)

    if trend == "BULLISH":
        # Micro-breakout: M1 candle closes above previous M1 high
        if current_close > prev['high'] and current_high > prev['high']:
            # RSI should be 25-70 (not overbought, showing momentum)
            if m1_rsi < RSI_OVERBOUGHT:
                tick = mt5.symbol_info_tick(SYMBOL)
                if tick is None:
                    return False, 0, 0, 0, "No tick"
                entry = tick.ask
                sl = entry - ATR_SL_MULT * m5_atr
                tp = entry + ATR_TP_MULT * m5_atr
                return True, entry, sl, tp, \
                    f"M1 micro-breakout BUY @{entry:.2f} SL={sl:.2f} TP={tp:.2f} RSI={m1_rsi:.0f}"
        # Alternative: pullback to M1 EMA8 with RSI exhaustion
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
# Session helpers
# ============================================================================

def is_in_session(current_dt: datetime) -> bool:
    now_minutes = current_dt.hour * 60 + current_dt.minute
    for sh, sm, eh, em in TRADE_SESSIONS:
        if (sh * 60 + sm) <= now_minutes < (eh * 60 + em):
            return True
    return False

# ============================================================================
# Trade execution
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
    # Margin cap
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

def place_order(order_type: int, lot: float, price: float, sl: float, tp: float,
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
        "comment": ORDER_COMMENT,
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
        "deviation": DEVIATION, "magic": MAGIC, "comment": "CLOSE_SCALPv4",
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
# Main loop
# ============================================================================

def main():
    setup_logging()
    logger.info("=" * 60)
    logger.info("Scalping Bot v4 — Multi-TF Momentum Scalper")
    logger.info("R:R = 1:%.1f (SL=%.1f×M5 ATR TP=%.1f×M5 ATR)", ATR_TP_MULT / ATR_SL_MULT, ATR_SL_MULT, ATR_TP_MULT)
    logger.info("HTF: M15 EMA20/50/200 | MTF: M5 pullback+rejection | LTF: M1 breakout")
    logger.info("RSI(%d) oversold=%d overbought=%d | Risk=%.1f%% | Max losses=%d",
                 RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, RISK_PERCENT, MAX_CONSECUTIVE_LOSSES)
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

    # Cache for M5 structure to avoid re-computing every loop
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

            # --- Session filter (shared liquidity check) ---
            if SESSION_FILTER_ENABLED:
                if not _session_should_trade(now_utc.hour):
                    logger.info("SESSION FILTER: Outside trading hours (hour=%d UTC)", now_utc.hour)
                    # Close any open position when entering blocked hours
                    open_ticket = get_position_ticket()
                    if open_ticket:
                        logger.info("Session filter — closing position %s", open_ticket)
                        close_position(open_ticket, sym_info)
                    time.sleep(30)
                    continue

            # --- Heartbeat ---
            if current_ts - last_heartbeat > HEARTBEAT_INTERVAL:
                pos = get_position_ticket()
                logger.info("HEARTBEAT | trend=%s trades=%d/%d wins=%d losses=%d pos=%s",
                             m15_trend_cache, state.session_trades, MAX_TRADES_PER_SESSION,
                             state.wins, state.losses, f"t={pos}" if pos else "FLAT")
                last_heartbeat = current_ts

            # --- Session check ---
            if not is_in_session(now_utc):
                open_ticket = get_position_ticket()
                if open_ticket:
                    logger.info("Outside session — closing %s", open_ticket)
                    close_position(open_ticket, sym_info)
                time.sleep(30)
                continue

            # --- Session reset ---
            if state.current_session_date != date.today():
                state.reset_session(date.today())

            # --- HTF: Refresh M15 trend (every 60s) ---
            if current_ts - m15_trend_time > 60:
                m15_trend_cache = get_m15_trend()
                m15_trend_time = current_ts
                if m15_trend_cache:
                    logger.info("M15 trend: %s", m15_trend_cache)

            if m15_trend_cache is None or m15_trend_cache == "NEUTRAL":
                time.sleep(LOOP_SLEEP_SEC)
                continue

            # --- MTF: Refresh M5 structure (every M5_REFRESH_SEC) ---
            if current_ts - m5_setup_time > M5_REFRESH_SEC:
                m5_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 100)
                if m5_rates is not None and len(m5_rates) >= M5_EMA_SLOW + 5:
                    m5_setup_cache = get_m5_pullback_structure(m5_rates, m15_trend_cache)
                m5_setup_time = current_ts

            has_setup, _, m5_atr, setup_msg = m5_setup_cache
            if not has_setup:
                time.sleep(LOOP_SLEEP_SEC)
                continue

            # --- Check if we have an open position ---
            open_ticket = get_position_ticket()
            if open_ticket:
                time.sleep(LOOP_SLEEP_SEC)
                continue

            # --- Spread check ---
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

            # --- LTF: Get M1 micro-breakout ---
            m1_rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 30)
            if m1_rates is None or len(m1_rates) < 10:
                time.sleep(LOOP_SLEEP_SEC)
                continue

            should_enter, entry, sl, tp, entry_msg = get_m1_micro_breakout(m1_rates, m15_trend_cache, m5_atr)
            if not should_enter:
                time.sleep(LOOP_SLEEP_SEC)
                continue

            # --- Place the trade ---
            logger.info("SIGNAL: %s", entry_msg)

            # Sentiment filter — check market sentiment before entering
            signal_dir = 1 if entry < sl else -1
            sent_ok, sent_msg = check_sentiment_filter(signal_dir)
            if not sent_ok:
                logger.info("Sentiment BLOCKED %s: %s", "BUY" if signal_dir == 1 else "SELL", sent_msg)
                time.sleep(LOOP_SLEEP_SEC)
                continue
            logger.info("Sentiment OK: %s", sent_msg)

            account_info = mt5.account_info()
            if not account_info:
                time.sleep(LOOP_SLEEP_SEC)
                continue

            sl_distance = abs(sl - entry)
            lot = calculate_lot_size(account_info.balance, sl_distance, sym_info)

            # Determine direction from price relationship
            if entry < sl:  # BUY (entry below SL)
                order_type = mt5.ORDER_TYPE_BUY
            else:  # SELL
                order_type = mt5.ORDER_TYPE_SELL

            ticket = place_order(order_type, lot, entry, sl, tp, sym_info)
            if ticket:
                state.session_trades += 1
                state.total_trades += 1
                state.save()
                logger.info("TRADE PLACED | %s lot=%.2f R:R=1:%.1f | Session: %d/%d",
                             "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
                             lot, ATR_TP_MULT / ATR_SL_MULT,
                             state.session_trades, MAX_TRADES_PER_SESSION)
                time.sleep(30)  # Cooldown after entry

            # --- Track completed trades ---
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
