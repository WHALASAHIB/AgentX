#!/usr/bin/env python3
"""
Multi-Symbol Strategy Bot — Production Template
================================================
Executes a selected strategy on a given forex/commodity symbol via MetaTrader 5.

Usage:
    python multi_symbol_bot.py --symbol XAUUSD --strategy macd
    python multi_symbol_bot.py --symbol EURUSD --strategy goldphoenix
    python multi_symbol_bot.py --symbol BTCUSD --strategy sma

Arguments:
    --symbol      Trading symbol (e.g., XAUUSD, EURUSD, BTCUSD)
    --strategy    Strategy name: macd | goldphoenix | bollinger | sma

Architecture:
    - Strategy logic is loaded from C:\Trading\backtester\active_strategies\<SYMBOL>\<strategy_file>
    - MT5 connection via shared utils/mt5_connect.py
    - Logging to C:\Trading\bots\logs\<symbol>_<strategy>.log
    - Configurable per-symbol parameters (magic number, lot size, risk)
    - Production-ready main loop with reconnection, state persistence,
      trailing stops, and error recovery

Based on gold_bot_v3.py MT5 connection and lifecycle patterns.
"""

from __future__ import annotations

import argparse
import importlib.util
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

# ============================================================================
# Constants
# ============================================================================

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STRATEGIES_DIR = os.path.join(BASE_DIR, "backtester", "active_strategies")
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# Strategy file mapping
STRATEGY_FILES = {
    "macd":         "macd_crossover.py",
    "goldphoenix":  "gold_phoenix.py",
    "bollinger":    "bollinger_bands.py",
    "sma":          "sma_crossover.py",
}

# Strategy class mapping
STRATEGY_CLASSES = {
    "macd":         "macd_crossover_strategy",
    "goldphoenix":  "GoldPhoenixStrategy",
    "bollinger":    "bollinger_bands_strategy",
    "sma":          "sma_crossover_strategy",
}

# Default symbol-specific parameters
# (magic_number, lot_size, risk_percent, max_entries_per_day)
DEFAULT_PARAMS = {
    "XAUUSD":  {"magic": 780001, "lot": 0.01, "risk": 1.0, "max_entries": 2},
    "EURUSD":  {"magic": 780002, "lot": 0.01, "risk": 1.0, "max_entries": 2},
    "GBPUSD":  {"magic": 780003, "lot": 0.01, "risk": 1.0, "max_entries": 2},
    "USDJPY":  {"magic": 780004, "lot": 0.01, "risk": 0.8, "max_entries": 2},  # Lower risk due to 21.9% DD
    "USDCHF":  {"magic": 780005, "lot": 0.01, "risk": 1.0, "max_entries": 2},
    "USDCAD":  {"magic": 780006, "lot": 0.01, "risk": 1.0, "max_entries": 2},
    "AUDUSD":  {"magic": 780007, "lot": 0.01, "risk": 1.0, "max_entries": 2},
    "NZDUSD":  {"magic": 780008, "lot": 0.01, "risk": 1.0, "max_entries": 2},
    "BTCUSD":  {"magic": 780009, "lot": 0.01, "risk": 1.0, "max_entries": 2},
}

# Default overrides if not in DEFAULT_PARAMS
FALLBACK_MAGIC = 780000
FALLBACK_LOT = 0.01
FALLBACK_RISK = 1.0
FALLBACK_MAX_ENTRIES = 2

# ATR-based risk defaults (R:R = 1:3)
ATR_PERIOD = 14
ATR_SL_MULT = 2.0       # SL = 2.0 x ATR
ATR_TP_MULT = 6.0       # TP = 6.0 x ATR -> R:R = 1:3
TRAIL_ACTIVATE_MULT = 3.0
TRAIL_DISTANCE_MULT = 1.5

# Timing
STATUS_LOG_INTERVAL_SEC = 15
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
RATES_BARS = 300

# Spread filter
MAX_SPREAD_POINTS = 50

# ============================================================================
# Module state
# ============================================================================

logger = logging.getLogger("multi_symbol_bot")
_symbol: str = ""
_strategy_name: str = ""
_magic: int = FALLBACK_MAGIC
_lot_size: float = FALLBACK_LOT
_risk_percent: float = FALLBACK_RISK
_max_entries_per_day: int = FALLBACK_MAX_ENTRIES
_state: dict[str, Any] = {}
_strategy_instance = None
_broker_offset_sec: float = 0.0
_last_offset_check: float = 0.0
_last_bar_time: int = 0
_last_status_log: float = 0.0

# ============================================================================
# Logging
# ============================================================================

def setup_logging(symbol: str, strategy: str) -> None:
    """Configure logging to file + stdout."""
    global logger
    logger = logging.getLogger(f"bot_{symbol}_{strategy}")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, f"{symbol}_{strategy}.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.info("Logging to %s", log_file)

# ============================================================================
# State management
# ============================================================================

def state_file_path() -> str:
    return os.path.join(STATE_DIR, f"{_symbol}_{_strategy_name}_state.json")

def default_state() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "trade_date": today,
        "trade_taken": False,
        "trade_side": None,
        "entries_today": 0,
        "max_entries_per_day": _max_entries_per_day,
        "last_entry_atr": None,
    }

def load_state() -> dict[str, Any]:
    path = state_file_path()
    if not os.path.exists(path):
        return default_state()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        base = default_state()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError):
        return default_state()

def save_state() -> None:
    path = state_file_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        logger.error("State save failed: %s", exc)

def reset_state_for_new_utc_day() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if _state.get("trade_date") == today:
        return
    logger.info("New UTC day — resetting state")
    _state["trade_date"] = today
    _state["trade_taken"] = False
    _state["trade_side"] = None
    _state["entries_today"] = 0
    _state["last_entry_atr"] = None
    save_state()

# ============================================================================
# Strategy loader
# ============================================================================

def load_strategy(symbol: str, strategy: str) -> bool:
    """
    Load the strategy module from active_strategies/<SYMBOL>/.
    Returns True on success, False on failure.
    """
    global _strategy_instance

    strategy_file = STRATEGY_FILES.get(strategy)
    if not strategy_file:
        logger.error("Unknown strategy: %s (valid: %s)", strategy, list(STRATEGY_FILES.keys()))
        return False

    strategy_class = STRATEGY_CLASSES.get(strategy)
    if not strategy_class:
        logger.error("Unknown strategy class mapping for: %s", strategy)
        return False

    strategy_path = os.path.join(STRATEGIES_DIR, symbol, strategy_file)
    if not os.path.exists(strategy_path):
        # Fallback: try generic strategies folder
        strategy_path = os.path.join(
            BASE_DIR, "backtester", "strategies", strategy_file
        )
    if not os.path.exists(strategy_path):
        logger.error("Strategy file not found: %s", strategy_path)
        return False

    try:
        spec = importlib.util.spec_from_file_location(
            f"strategy_{symbol}_{strategy}", strategy_path
        )
        if spec is None or spec.loader is None:
            logger.error("Failed to create module spec for %s", strategy_path)
            return False

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        klass = getattr(module, strategy_class)
        _strategy_instance = klass()
        logger.info(
            "Loaded strategy %s (%s) for %s",
            strategy, strategy_class, symbol
        )
        return True
    except Exception as exc:
        logger.error("Failed to load strategy %s: %s", strategy, exc)
        return False

# ============================================================================
# UTC helpers
# ============================================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def broker_ts_to_utc(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts - _broker_offset_sec, tz=timezone.utc)

def detect_broker_offset() -> float:
    tick = mt5.symbol_info_tick(_symbol)
    if tick is None:
        raise RuntimeError(f"No tick for {_symbol}: {mt5.last_error()}")
    return float(tick.time) - datetime.now(timezone.utc).timestamp()

def revalidate_offset_if_needed() -> None:
    global _broker_offset_sec, _last_offset_check
    now = time.time()
    if now - _last_offset_check < 3600:
        return
    try:
        new_off = detect_broker_offset()
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
    if not mt5.symbol_select(_symbol, True):
        logger.error("symbol_select failed: %s", mt5.last_error())
        return False
    info = mt5.symbol_info(_symbol)
    if info is None:
        logger.error("symbol_info missing for %s", _symbol)
        return False
    if not info.visible:
        mt5.symbol_select(_symbol, True)
    if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        logger.error("Trading disabled for %s", _symbol)
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
    rates = mt5.copy_rates_from_pos(_symbol, timeframe, 0, count)
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
        trs.append(
            true_range(
                float(rates[i]["high"]),
                float(rates[i]["low"]),
                float(rates[i - 1]["close"]),
            )
        )
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def atr_in_pips(atr_value: float, point: float) -> float:
    return atr_value / point if point > 0 else 0.0

def new_bar_closed() -> bool:
    """Check if a new 5M candle has closed since last check."""
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
# Strategy signal evaluation
# ============================================================================

def get_strategy_signal() -> Optional[int]:
    """
    Fetch market data, run the loaded strategy, and return a signal.
    Returns: 1 (BUY), -1 (SELL), or None (HOLD/no signal)
    """
    if _strategy_instance is None:
        return None

    try:
        # Get price data as pandas-compatible structure
        rates = get_rates(mt5.TIMEFRAME_M5, 100)
        if rates is None or len(rates) < 30:
            return None

        import pandas as pd
        df = pd.DataFrame(rates)
        df.rename(columns={
            "open": "open", "high": "high", "low": "low",
            "close": "close", "tick_volume": "volume"
        }, inplace=True)
        df["date"] = pd.to_datetime(df["time"], unit="s", utc=True)

        # Run strategy on_data
        result_df = _strategy_instance.on_data(df)

        if result_df is None or result_df.empty:
            return None

        latest_signal = result_df["signal"].iloc[-1]
        if latest_signal == 1:
            return mt5.ORDER_TYPE_BUY
        elif latest_signal == -1:
            return mt5.ORDER_TYPE_SELL
        return None

    except ImportError:
        logger.warning("pandas not available — using fallback signal logic")
        return None
    except Exception as exc:
        logger.warning("Strategy signal error: %s", exc)
        return None

# ============================================================================
# Position management
# ============================================================================

def bot_positions():
    positions = mt5.positions_get(symbol=_symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == _magic]

def reconcile_trade_state() -> None:
    positions = bot_positions()
    if positions and len(positions) > 0:
        if not _state.get("trade_taken"):
            logger.info("Reconciling: open position found")
            _state["trade_taken"] = True
            _state["trade_date"] = datetime.now(timezone.utc).date().isoformat()
            save_state()
    else:
        if _state.get("trade_taken") and \
           _state.get("entries_today", 0) < _state.get("max_entries_per_day", _max_entries_per_day):
            _state["trade_taken"] = False
            save_state()

# ============================================================================
# Spread filter
# ============================================================================

def spread_ok() -> tuple[bool, int]:
    info = mt5.symbol_info(_symbol)
    if info is None:
        return False, 999
    return (info.spread <= MAX_SPREAD_POINTS, info.spread)

# ============================================================================
# Order execution
# ============================================================================

def get_filling_mode() -> int:
    info = mt5.symbol_info(_symbol)
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
    info = mt5.symbol_info(_symbol)
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
    """Place a market order with ATR-based SL/TP and risk-based position sizing."""
    global _state
    tick = mt5.symbol_info_tick(_symbol)
    info = mt5.symbol_info(_symbol)
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

    # Risk-based position sizing
    account_info = mt5.account_info()
    if account_info and point > 0:
        balance = account_info.balance
        risk_amount = balance * (_risk_percent / 100.0)
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
                margin_per_lot = mt5.order_calc_margin(
                    mt5.ORDER_TYPE_BUY, _symbol, 1.0, price
                )
                if margin_per_lot and margin_per_lot > 0 and account_info.margin_free > 0:
                    max_lot = (account_info.margin_free * 0.30) / margin_per_lot
                    volume = min(volume, round(max_lot / step) * step)
            except Exception:
                pass
        else:
            volume = _lot_size
    else:
        volume = _lot_size

    volume = normalize_volume(volume)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": _symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 30,
        "magic": _magic,
        "comment": f"MSB_{_strategy_name.upper()}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(),
    }

    logger.info(
        "PLACING %s %s | vol=%.2f price=%s sl=%s tp=%s atr=%s R:R=1:%.1f spread=%d",
        "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL",
        _symbol, volume, price, sl, tp, atr, ATR_TP_MULT / ATR_SL_MULT, info.spread
    )

    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send None: %s", mt5.last_error())
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error("Order REJECTED retcode=%s comment=%s", result.retcode, result.comment)
        return False

    logger.info(
        "ORDER FILLED | ticket=%s deal=%s | Price=%s SL=%s TP=%s | R:R=1:%.1f",
        result.order, result.deal, price, sl, tp, ATR_TP_MULT / ATR_SL_MULT
    )

    _state["trade_taken"] = True
    _state["trade_date"] = datetime.now(timezone.utc).date().isoformat()
    _state["trade_side"] = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    _state["entries_today"] = _state.get("entries_today", 0) + 1
    _state["last_entry_atr"] = atr
    save_state()
    return True

# ============================================================================
# Trailing stop
# ============================================================================

def update_trailing_stops() -> None:
    """Trailing stop that activates at TRAIL_ACTIVATE_MULT x ATR profit."""
    positions = bot_positions()
    if not positions:
        return
    info = mt5.symbol_info(_symbol)
    tick = mt5.symbol_info_tick(_symbol)
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
        if pos.magic != _magic:
            continue
        if pos.type == mt5.POSITION_TYPE_BUY:
            profit_dist = tick.bid - pos.price_open
            if profit_dist >= activate_dist:
                new_sl = normalize_price(tick.bid - trail_dist, info.digits)
                if new_sl > pos.sl:
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": _symbol,
                        "sl": new_sl,
                        "tp": pos.tp,
                        "magic": _magic,
                    }
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(
                            "TRAIL BUY t=%s SL->%s (profit %.1fxATR)",
                            pos.ticket, new_sl, profit_dist / atr_val
                        )
        elif pos.type == mt5.POSITION_TYPE_SELL:
            profit_dist = pos.price_open - tick.ask
            if profit_dist >= activate_dist:
                new_sl = normalize_price(tick.ask + trail_dist, info.digits)
                if new_sl < pos.sl or pos.sl == 0:
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": _symbol,
                        "sl": new_sl,
                        "tp": pos.tp,
                        "magic": _magic,
                    }
                    result = mt5.order_send(req)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(
                            "TRAIL SELL t=%s SL->%s (profit %.1fxATR)",
                            pos.ticket, new_sl, profit_dist / atr_val
                        )

# ============================================================================
# End-of-session close
# ============================================================================

def at_end_of_session() -> bool:
    """Close positions at 17:00 UTC (end of main session)."""
    now = utc_now()
    return now.hour >= 17 and now.minute >= 0

def close_bot_positions() -> None:
    positions = bot_positions()
    if not positions:
        return
    filling = get_filling_mode()
    tick = mt5.symbol_info_tick(_symbol)
    if tick is None:
        return
    for pos in positions:
        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": _symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 30,
            "magic": _magic,
            "comment": f"MSB_{_strategy_name.upper()}_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info("CLOSED t=%s at %s", pos.ticket, price)
    _state["trade_taken"] = False
    save_state()

# ============================================================================
# Entry execution
# ============================================================================

def try_execute_entry() -> None:
    """Evaluate strategy, check filters, and place order if conditions met."""
    if _state.get("entries_today", 0) >= _state.get("max_entries_per_day", _max_entries_per_day):
        return

    # Check for existing positions
    pos = bot_positions()
    if pos and len(pos) > 0:
        return

    # Check spread
    sp_ok, spread = spread_ok()
    if not sp_ok:
        logger.debug("Spread too high: %d — skipping", spread)
        return

    # Get strategy signal
    signal = get_strategy_signal()
    if signal is None:
        return

    logger.info(
        "Signal: %s on %s",
        "BUY" if signal == mt5.ORDER_TYPE_BUY else "SELL",
        _symbol
    )

    # Compute ATR for position sizing
    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    if rates is None:
        logger.warning("No rates for ATR — skipping entry")
        return
    atr_val = compute_atr(rates, ATR_PERIOD)
    if atr_val is None or atr_val <= 0:
        logger.warning("ATR unavailable — skipping entry")
        return

    place_market_order(signal, atr_val)

# ============================================================================
# Status logging
# ============================================================================

def log_status() -> None:
    tick = mt5.symbol_info_tick(_symbol)
    bid = tick.bid if tick else 0.0
    ask = tick.ask if tick else 0.0
    now_str = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    entries = _state.get("entries_today", 0)
    max_entries = _state.get("max_entries_per_day", _max_entries_per_day)
    positions = bot_positions()
    pos_str = "FLAT"
    if positions and len(positions) > 0:
        p = positions[0]
        pos_str = f"t={p.ticket} {'BUY' if p.type==0 else 'SELL'} P&L={p.profit:.2f}"
    rates = get_rates(mt5.TIMEFRAME_M5, ATR_PERIOD + 5)
    atr_val = compute_atr(rates) if rates is not None else None
    atr_str = f"ATR={atr_val:.2f}" if atr_val else "ATR=?"
    logger.info(
        "STATUS | %s | %s | bid=%s ask=%s | %s | entries=%d/%d | %s",
        now_str, _symbol, bid, ask, atr_str, entries, max_entries, pos_str
    )

# ============================================================================
# Main loop
# ============================================================================

def startup(symbol: str, strategy: str) -> None:
    """Initialize everything before the main loop."""
    global _symbol, _strategy_name, _magic, _lot_size, _risk_percent
    global _max_entries_per_day, _state, _broker_offset_sec, _last_offset_check

    _symbol = symbol.upper()
    _strategy_name = strategy.lower()

    # Load symbol-specific parameters
    params = DEFAULT_PARAMS.get(_symbol, {})
    _magic = params.get("magic", FALLBACK_MAGIC)
    _lot_size = params.get("lot", FALLBACK_LOT)
    _risk_percent = params.get("risk", FALLBACK_RISK)
    _max_entries_per_day = params.get("max_entries", FALLBACK_MAX_ENTRIES)

    setup_logging(_symbol, _strategy_name)
    logger.info("=" * 60)
    logger.info("Multi-Symbol Bot | Symbol=%s Strategy=%s", _symbol, _strategy_name)
    logger.info("Magic=%d Lot=%.2f Risk=%d%% MaxEntries=%d",
                _magic, _lot_size, int(_risk_percent), _max_entries_per_day)
    logger.info("R:R = 1:%.1f (SL=%.1fxATR TP=%.1fxATR)",
                ATR_TP_MULT / ATR_SL_MULT, ATR_SL_MULT, ATR_TP_MULT)
    logger.info("=" * 60)

    # Load strategy
    if not load_strategy(_symbol, _strategy_name):
        logger.error("Strategy loading failed — exiting")
        sys.exit(1)

    # Connect to MT5
    wait_for_mt5()
    _broker_offset_sec = detect_broker_offset()
    _last_offset_check = time.time()
    logger.info("Broker offset: %.0fs", _broker_offset_sec)

    # Load state
    _state = load_state()
    reset_state_for_new_utc_day()
    reconcile_trade_state()

def run_loop() -> None:
    """Main trading loop — runs forever until interrupted."""
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

            # Close at end of session
            if at_end_of_session():
                bpos = bot_positions()
                if bpos and len(bpos) > 0:
                    logger.info("End of session — closing positions")
                    close_bot_positions()

            # Trail existing positions
            bpos = bot_positions()
            if bpos and len(bpos) > 0:
                update_trailing_stops()

            # Status log
            now = time.time()
            if now - _last_status_log >= STATUS_LOG_INTERVAL_SEC:
                log_status()
                _last_status_log = now

            # New bar event — check for entry
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
    parser = argparse.ArgumentParser(
        description="Multi-Symbol Strategy Bot for MetaTrader 5"
    )
    parser.add_argument(
        "--symbol", required=True,
        help="Trading symbol (e.g., XAUUSD, EURUSD, GBPUSD, BTCUSD)"
    )
    parser.add_argument(
        "--strategy", required=True,
        choices=list(STRATEGY_FILES.keys()),
        help="Strategy to run: macd | goldphoenix | bollinger | sma"
    )
    args = parser.parse_args()

    startup(args.symbol, args.strategy)
    try:
        run_loop()
    finally:
        shutdown_mt5()

if __name__ == "__main__":
    main()
