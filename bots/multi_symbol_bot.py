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
    - Strategy logic is loaded from backtester/active_strategies/<SYMBOL>/<strategy_file>
    - MT5 connection via shared utils/mt5_connect.py
    - Logging to bots/logs/<symbol>_<strategy>.log
    - Configurable per-symbol parameters (magic number, lot size, risk)
    #    - Production-ready main loop with reconnection, state persistence,
    #      and error recovery

Based on gold_bot_v3.py MT5 connection and lifecycle patterns.
"""

from __future__ import annotations

import argparse
import atexit
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

# 🛡️ Trade Guardrail — safety layer between strategy signal and MT5 execution
# See trade_guardrail.py for full documentation
from trade_guardrail import guard_trade

# 🔒 5-Loss Circuit Breaker + FTMO Drawdown Guard
# Prevents bot from overtrading after losses or exceeding drawdown limits
from circuit_breaker import CircuitBreaker, FtmoDrawdownGuard

# 📊 ATR Regime Selector — prevents trading in wrong volatility regime
# High vol → breakout only, Low vol → mean-reversion only
from session_filters import get_regime_mode, get_regime_summary

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

# ──────────────────────────────────────────────────────────────────────────────
# Symbol Parameters
# ──────────────────────────────────────────────────────────────────────────────
# (magic_number, risk_percent, max_entries_per_day)
# risk_percent = percentage of CURRENT account balance risked per trade
#   Example: 0.15% risk on $10,000 account = $15 risk per trade
#   If account grows to $12,000 → risk = $18 per trade
#   If account shrinks to $8,000  → risk = $12 per trade
#   This is DYNAMIC — reads live MT5 balance every trade, no fixed lots
#
# FTMO Challenge Mode: standard 0.15% risk gives ~$15/trade on $10K
# 10% max drawdown = $1,000 total risk buffer ≈ 66 losing trades in a row
# 5% daily loss limit = $500/day
#
# risk = 0.0 means DISABLED (bot will skip that symbol)
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_PARAMS = {
    "XAUUSD":  {"magic": 888222, "risk": 0.0, "max_entries": 0},   # PAUSED by CEO
    "EURUSD":  {"magic": 888223, "risk": 0.15, "max_entries": 2},   # Max 2/day per council verdict
    "GBPUSD":  {"magic": 780003, "risk": 0.15, "max_entries": 2},
    "USDJPY":  {"magic": 780004, "risk": 0.15, "max_entries": 2},
    "USDCHF":  {"magic": 780005, "risk": 0.15, "max_entries": 2},
    "USDCAD":  {"magic": 780006, "risk": 0.15, "max_entries": 2},
    "AUDUSD":  {"magic": 780007, "risk": 0.15, "max_entries": 2},
    "NZDUSD":  {"magic": 780008, "risk": 0.15, "max_entries": 2},
    "BTCUSD":  {"magic": 780009, "risk": 0.0, "max_entries": 0},   # DISABLED — not available on MetaQuotes-Demo
}

# Default overrides if not in DEFAULT_PARAMS
FALLBACK_MAGIC = 780000
FALLBACK_RISK = 0.15
FALLBACK_MAX_ENTRIES = 2

# ATR-based risk defaults (R:R = 1:3)
ATR_PERIOD = 14
ATR_SL_MULT = 1.0       # SL = 1.0 x ATR
ATR_TP_MULT = 4.0       # TP = 4.0 x ATR -> R:R = 1:4
# Trailing stop constants removed per council verdict P0 — breakeven trail eliminated

# Timing
STATUS_LOG_INTERVAL_SEC = 15
LOOP_SLEEP_SEC = 1
MT5_RETRY_SEC = 30
RATES_BARS = 300

# Maximum position size cap (lots) — critical safety limit
# Prevents M5 ATR position sizing paradox where tiny forex ATR
# produces absurdly large volumes (e.g., 19.51 lots on $10K)
MAX_VOLUME_PER_TRADE = 3.0

# Spread filter
MAX_SPREAD_POINTS = 50

# FTMO Challenge Mode — Daily Risk Limits
# $10K FTMO: 5% daily loss limit = $500, 10% max drawdown = $1,000
FTMO_MODE = True                          # Set True when running on prop firm account
FTMO_ACCOUNT_SIZE = 100000                 # Starting balance on the challenge (FTMO $100K)
FTMO_MAX_DAILY_LOSS_PCT = 5.0              # 5% max daily loss
FTMO_MAX_DRAWDOWN_PCT = 10.0               # 10% max total drawdown
_daily_pnl_start_balance: float = 0.0      # Tracked at first trade of the UTC day

# ── FTMO Combat Circuit Breakers ───────────────────────────────────────────
# Research-backed: 99% of algo bots fail FTMO. These protect against the
# top 5 killers: daily loss limit breach, consecutive losses, news traps,
# overtrading on profitable days, and correlation clustering.
# ───────────────────────────────────────────────────────────────────────────
CONSECUTIVE_LOSS_LIMIT = 3                 # Auto-pause after 3 losses in a row
DAILY_PROFIT_CAP_PCT = 0.5                 # Stop trading after +0.5% daily profit
HIGH_IMPACT_NEWS_WINDOW_MIN = 15           # Minutes to avoid around high-impact news
# Trading window (UTC) — London/NY overlap for best liquidity
TRADING_WINDOW_START_UTC = 7               # London open
TRADING_WINDOW_END_UTC = 17                # NY close
# Track consecutive losses (persisted in state)
_consecutive_losses: int = 0
_circuit_breaker_active: bool = False
_circuit_breaker_until: float = 0.0        # Unix timestamp when breaker resets
_daily_profit_hit_limit: bool = False

# ============================================================================
# Module state
# ============================================================================

logger = logging.getLogger("multi_symbol_bot")
_symbol: str = ""
_strategy_name: str = ""
_magic: int = FALLBACK_MAGIC
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
    """Select the trading symbol in MT5. Triggers full reconnect on IPC failure."""
    success = mt5.symbol_select(_symbol, True)
    if not success:
        err = mt5.last_error()
        logger.error("symbol_select failed: %s", err)
        # IPC failure (-1 or -10003) means MT5 pipe is congested — full restart needed
        if err and err[0] in (-1, -10003):
            logger.warning("🔌 MT5 IPC failure detected — restarting MT5 connection")
            mt5.shutdown()
            time.sleep(3)  # Brief cooldown before reconnecting
            return init_mt5() and ensure_symbol()
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
        rates = get_rates(mt5.TIMEFRAME_H1, 100)
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
            signal = mt5.ORDER_TYPE_BUY
        elif latest_signal == -1:
            signal = mt5.ORDER_TYPE_SELL
        else:
            return None

        # ── Sentiment filter ──────────────────────────────────────────────
        # Load sentiment_engine via importlib (fail-open on error)
        try:
            import importlib
            se = importlib.import_module("research.sentiment_engine")
            sentiment = se.get_sentiment()
            logger.info("Sentiment score: %+d (%s)", sentiment.score, sentiment.bias)
            # Threshold: >= +3 allows only BUY, <= -3 allows only SELL
            if sentiment.score >= 3 and signal == mt5.ORDER_TYPE_SELL:
                logger.info("Sentiment filter BLOCKED SELL (sentiment=%+d >= +3)", sentiment.score)
                return None
            if sentiment.score <= -3 and signal == mt5.ORDER_TYPE_BUY:
                logger.info("Sentiment filter BLOCKED BUY (sentiment=%+d <= -3)", sentiment.score)
                return None
        except Exception as exc:
            logger.debug("Sentiment filter unavailable (fail-open): %s", exc)
        # ── End sentiment filter ──────────────────────────────────────────

        return signal

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
    """Reconcile state with open positions. Tracks consecutive losses."""
    global _consecutive_losses, _circuit_breaker_active
    positions = bot_positions()
    positions_exist = positions and len(positions) > 0
    
    # Position closed — check if it was a winner or loser
    if _state.get("trade_taken") and not positions_exist:
        # Try to get the last closed order P&L from MT5 history
        last_pnl = 0.0
        try:
            from_time = datetime.now(timezone.utc) - timedelta(hours=24)
            history = mt5.history_orders_get(from_time, datetime.now(timezone.utc))
            if history:
                # Find our magic number orders
                our_orders = [o for o in history if o.magic == _magic]
                if our_orders:
                    last_order = max(our_orders, key=lambda o: o.time_done or o.time_setup)
                    # Get the corresponding deal for P&L
                    deals = mt5.history_deals_get(from_time, datetime.now(timezone.utc))
                    if deals:
                        our_deals = [d for d in deals if d.magic == _magic and d.order == last_order.ticket]
                        if our_deals:
                            last_pnl = float(our_deals[-1].profit)
        except Exception:
            pass
        
        # 🔄 5-LOSS CIRCUIT BREAKER — record trade result
        try:
            CircuitBreaker.record_trade(_symbol, _strategy_name, last_pnl)
        except Exception:
            pass

        if last_pnl < 0:
            _consecutive_losses += 1
            logger.info(
                "📉 Consecutive loss #%d/%d (P&L: $%.2f)",
                _consecutive_losses, CONSECUTIVE_LOSS_LIMIT, last_pnl
            )
            if _consecutive_losses >= CONSECUTIVE_LOSS_LIMIT:
                # Activate circuit breaker until end of UTC day
                _circuit_breaker_active = True
                tomorrow = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) + timedelta(days=1)
                _circuit_breaker_until = tomorrow.timestamp()
                logger.warning(
                    "🔴 CIRCUIT BREAKER TRIGGERED — %d consecutive losses. "
                    "Pausing until %s UTC",
                    _consecutive_losses,
                    datetime.fromtimestamp(_circuit_breaker_until, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                )
        elif last_pnl > 0:
            # Win — reset counter
            if _consecutive_losses > 0:
                logger.info("📈 Win! Resetting consecutive loss counter (was %d)", _consecutive_losses)
            _consecutive_losses = 0
    
    if positions_exist:
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

    # ── Risk-based position sizing (100% dynamic) ──────────────────────
    # Reads current MT5 balance live — no fixed lots, no trails
    #   risk_amount = current_balance × (risk_percent / 100)
    #   volume = risk_amount / (SL_distance_in_points × contract_value_per_point)
    #
    # Example: $10,000 balance, 0.15% risk, 50-pip SL:
    #   risk_amount = $15.00
    #   volume = $15 / (500 points × $10/point) = 0.03 lots
    #   If balance drops to $8,000 → risk_amount = $12.00 → 0.024 lots
    #   If balance grows to $12,000 → risk_amount = $18.00 → 0.036 lots
    # ────────────────────────────────────────────────────────────────────
    account_info = mt5.account_info()
    if account_info is None or point <= 0:
        logger.error("Cannot size position: no account info or zero point")
        return False

    balance = account_info.balance
    risk_amount = balance * (_risk_percent / 100.0)
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
            mt5.ORDER_TYPE_BUY, _symbol, 1.0, price
        )
        if margin_per_lot and margin_per_lot > 0 and account_info.margin_free > 0:
            max_lot = (account_info.margin_free * 0.30) / margin_per_lot
            volume = min(volume, round(max_lot / step) * step)
    except Exception:
        pass

    volume = normalize_volume(volume)
    volume = min(volume, MAX_VOLUME_PER_TRADE)

    # 🛡️ GUARDRAIL CHECK — Phase 1: Static Rule Validation
    # Screens every trade against safety limits before sending to MT5
    guard_side = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    guard_result = guard_trade(
        symbol=_symbol,
        side=guard_side,
        risk_pct=_risk_percent,
        volume=volume,
        balance=balance,
        entry_price=price,
        sl_price=sl,
        symbol_info={"trade_contract_size": info.trade_contract_size, "point": point},
        entries_today=_state.get("entries_today", 0),
        max_entries=_state.get("max_entries_per_day", _max_entries_per_day),
        start_balance=_daily_pnl_start_balance if _daily_pnl_start_balance > 0 else None,
        peak_balance=None,
        open_positions_pnl=sum(p.profit for p in (mt5.positions_get() or []) if p.symbol == _symbol),
        consecutive_losses=_consecutive_losses,
        open_positions_for_symbol=len(bot_positions()),
    )
    if guard_result.blocked:
        logger.warning(
            "🛡️ GUARDRAIL BLOCKED %s %s: %s",
            guard_side, _symbol, guard_result.reason
        )
        return False
    logger.info(
        "🛡️ GUARDRAIL APPROVED %s %s: %s",
        guard_side, _symbol, guard_result.reason
    )

    # 📝 REASONING RECORD (Ch.17: Chain of Thought)
    # Record structured audit trail BEFORE order execution
    try:
        from trade_reasoner import record_trade_reasoning
        # Simple trend heuristic: price position vs ATR bands
        atr_ratio = atr / price if price > 0 else 0
        vol_str = "high" if atr_ratio > 0.002 else "normal" if atr_ratio > 0.0003 else "low"
        record_trade_reasoning(
            symbol=_symbol,
            strategy=_strategy_name,
            direction=guard_side,
            entry_trigger=f"{_strategy_name} signal on H1",
            balance=balance,
            risk_percent=_risk_percent,
            volume=volume,
            entry_price=price,
            sl_price=sl,
            tp_price=tp,
            atr=atr,
            ema_50=price,  # Will use actual EMA50 via get_rates in Phase 2
            ema_200=price,
            spread=info.spread,
            bid=tick.bid,
            ask=tick.ask,
            trend="calculated post-merge",
            volatility=vol_str,
            guardrail_result=f"APPROVED ({guard_result.reason[:40]})",
        )
    except Exception as exc:
        logger.debug("Reasoning record skipped: %s", exc)

    # 🛡️ SANITY CHECK: Volume should never risk more than 1.5x the risk target
    actual_risk_pct = (volume * sl_distance_points * contract_value) / balance * 100
    if actual_risk_pct > _risk_percent * 1.5:
        logger.warning(
            "🛡️ POSITION SIZING SANITY CHECK FAILED: calculated risk=%.2f%% vs target=%.2f%%. "
            "Capping volume from %.2f to %.2f",
            actual_risk_pct, _risk_percent, volume, volume * (_risk_percent * 1.5 / actual_risk_pct)
        )
        volume = normalize_volume(volume * (_risk_percent * 1.5 / actual_risk_pct))

    logger.info(
        "💰 POSITION SIZING | balance=$%.2f risk=%.2f%% risk_amt=$%.2f "
        "SL_dist=%.0fpts volume=%.2f lots",
        balance, _risk_percent, risk_amount,
        sl_distance_points, volume,
    )

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

# ── Trailing stop REMOVED per council verdict P0 ──────────────────────────
# Breakeven trail (was at 3.0xATR → breakeven halfway to 6.0xATR TP)
# converted 4R winners into 0R scratches. Removed unanimously.
# Trades now run from entry to SL (1.0xATR) or TP (4.0xATR) with NO
# mid-trade adjustments.
# ──────────────────────────────────────────────────────────────────────────

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
    # 🏆 PORTFOLIO PRIORITIZER CHECK
    try:
        from portfolio_prioritizer import should_trade
        ok, priority_reason = should_trade(_symbol, _strategy_name)
        if not ok:
            logger.info("🏆 Prioritizer: %s", priority_reason)
            return
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("Prioritizer check failed: %s", exc)

    # ⚠️ RISK SUPERVISOR CHECK
    # If risk supervisor says PAUSE this symbol, skip
    try:
        from risk_supervisor import RiskSnapshot
        symbol_action = RiskSnapshot.check_symbol(_symbol)
        if symbol_action == "pause":
            logger.info("⚠️ Risk Supervisor: %s PAUSED — no trades allowed", _symbol)
            return
        elif symbol_action == "reduce":
            logger.info("⚠️ Risk Supervisor: %s REDUCED — monitoring", _symbol)
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("Risk supervisor check failed: %s", exc)

    # 🧠 STRATEGY SUPERVISOR CHECK
    # If strategy supervisor recommends a different strategy, skip this bot
    try:
        from strategy_supervisor import StrategyAllocations
        ok, strat_reason = StrategyAllocations.should_trade_strategy(_symbol, _strategy_name)
        if not ok:
            logger.info("🧠 Strategy Supervisor: %s", strat_reason)
            return
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("Strategy supervisor check failed: %s", exc)

    # 📋 STRATEGIC PLANNER CHECK (Ch.6: Planning Pattern)
    # Check if today's plan allows entries at this time
    try:
        from strategic_planner import check_entry_allowed
        plan_ok, plan_reason = check_entry_allowed(_symbol)
        if not plan_ok:
            logger.info("📋 Planner: %s", plan_reason)
            return
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("Planner check failed: %s", exc)

    # 🔔 HUMAN-IN-THE-LOOP CHECK (Ch.13: HITL Pattern)
    # If there's a pending HITL request for a critical category, pause
    try:
        from human_in_the_loop import is_category_blocked
        blocked, hitl_reason = is_category_blocked("drawdown")
        if blocked:
            logger.info("🔔 HITL: %s", hitl_reason)
            return
        blocked, hitl_reason = is_category_blocked("daily_loss")
        if blocked:
            logger.info("🔔 HITL: %s", hitl_reason)
            return
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("HITL check failed: %s", exc)
    # DISABLED: risk_percent = 0.0 means skip this symbol entirely
    if _risk_percent <= 0.0:
        return

    if _state.get("entries_today", 0) >= _state.get("max_entries_per_day", _max_entries_per_day):
        return

    # ── FTMO Circuit Breaker ──────────────────────────────────────────────
    # After 3 consecutive losses, auto-pause trading for the rest of the day
    global _consecutive_losses, _circuit_breaker_active, _circuit_breaker_until, _daily_profit_hit_limit
    if _circuit_breaker_active:
        now = time.time()
        if now < _circuit_breaker_until:
            logger.warning(
                "⚠️  CIRCUIT BREAKER ACTIVE — %d consecutive losses. "
                "Resuming at %s UTC",
                _consecutive_losses,
                datetime.fromtimestamp(_circuit_breaker_until, tz=timezone.utc).strftime("%H:%M")
            )
            return
        else:
            logger.info("🔌 Circuit breaker reset — resuming trading")
            _circuit_breaker_active = False
            _consecutive_losses = 0
            _circuit_breaker_until = 0.0
    # ───────────────────────────────────────────────────────────────────────

    # ── FTMO Trading Window ───────────────────────────────────────────────
    # Only trade during London/NY overlap for best liquidity
    now_hour = datetime.now(timezone.utc).hour
    if not (TRADING_WINDOW_START_UTC <= now_hour < TRADING_WINDOW_END_UTC):
        return
    # ───────────────────────────────────────────────────────────────────────

    # ── FTMO Daily Profit Cap ─────────────────────────────────────────────
    # Stop trading for the day after hitting +0.5% profit
    if _daily_profit_hit_limit:
        logger.info("💰 Daily profit cap reached — no more trades today")
        return
    # ───────────────────────────────────────────────────────────────────────

    # FTMO Daily Loss Check (percentage of starting balance)
    if FTMO_MODE:
        today = datetime.now(timezone.utc).date()
        if _daily_pnl_start_balance <= 0:
            acct = mt5.account_info()
            if acct:
                _daily_pnl_start_balance = acct.balance
        else:
            acct = mt5.account_info()
            if acct:
                daily_pnl = acct.balance - _daily_pnl_start_balance
                daily_loss_limit = -_daily_pnl_start_balance * (FTMO_MAX_DAILY_LOSS_PCT / 100.0)
                # Check current position P&L too
                pos_pnl = sum(p.profit for p in (mt5.positions_get() or []))
                if daily_pnl + pos_pnl < daily_loss_limit:
                    logger.warning(
                        "FTMO DAILY LOSS LIMIT REACHED: balance=%.2f start=%.2f pnl=%.2f limit=%.2f — PAUSING",
                        acct.balance, _daily_pnl_start_balance, daily_pnl, daily_loss_limit
                    )
                    return
                # Also check daily profit cap
                daily_profit_limit = _daily_pnl_start_balance * (DAILY_PROFIT_CAP_PCT / 100.0)
                if daily_pnl + pos_pnl >= daily_profit_limit:
                    logger.info(
                        "💰 Daily profit cap hit: +$%.2f (+%.2f%%) — stopping for the day",
                        daily_pnl + pos_pnl, (daily_pnl + pos_pnl) / _daily_pnl_start_balance * 100
                    )
                    _daily_profit_hit_limit = True
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
    rates = get_rates(mt5.TIMEFRAME_H1, ATR_PERIOD + 5)
    if rates is None:
        logger.warning("No rates for ATR — skipping entry")
        return
    atr_val = compute_atr(rates, ATR_PERIOD)
    if atr_val is None or atr_val <= 0:
        logger.warning("ATR unavailable — skipping entry")
        return

    # 🚨 FTMO DRAWDOWN GUARD — 8% warning threshold
    # Blocks ALL entries if drawdown exceeds 8% of peak balance
    try:
        acct = mt5.account_info()
        if acct:
            # Record current peak for drawdown tracking
            FtmoDrawdownGuard.record_peak(acct.balance)
            if not FtmoDrawdownGuard.should_trade(balance=acct.balance):
                logger.warning("🚨 FTMO Drawdown Guard blocked entry for %s", _symbol)
                return
    except Exception:
        pass

    # 🔒 5-LOSS CIRCUIT BREAKER — auto-pause after 5 consecutive losses
    # Per-symbol tracking, auto-resets at midnight UTC
    if not CircuitBreaker.should_trade(_symbol, _strategy_name):
        cb_status = CircuitBreaker.get_status(_symbol, _strategy_name)
        logger.info(
            "🔒 5-Loss CircuitBreaker blocked %s %s (losses=%d, paused=%s)",
            _strategy_name, _symbol,
            cb_status.get("consecutive_losses", 0),
            cb_status.get("paused", False)
        )
        return

    # 📊 ATR REGIME SELECTOR — prevent trading in wrong volatility regime
    # High vol: breakout only | Low vol: mean-reversion only | Normal: everything
    regime_ok, regime_msg = get_regime_mode(_symbol, _strategy_name)
    if not regime_ok:
        logger.info("📊 ATR Regime Selector blocked %s %s: %s", _strategy_name, _symbol, regime_msg)
        return
    logger.debug("📊 ATR Regime: %s", regime_msg)

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
    rates = get_rates(mt5.TIMEFRAME_H1, ATR_PERIOD + 5)
    atr_val = compute_atr(rates) if rates is not None else None
    atr_str = f"ATR={atr_val:.5f}" if atr_val else "ATR=?"

    # ATR Regime summary (cached internally)
    regime_str = get_regime_summary(_symbol)
    # Circuit breaker status
    cb = CircuitBreaker.get_status(_symbol, _strategy_name)
    cb_str = f"CB={'🔒' if cb.get('paused') else '✅'}({cb.get('consecutive_losses', 0)})"

    logger.info(
        "STATUS | %s | %s | bid=%s ask=%s | %s | %s | entry=%d/%d | %s | %s",
        now_str, _symbol, bid, ask, atr_str, regime_str,
        entries, max_entries, cb_str, pos_str
    )

# ============================================================================
# Main loop
# ============================================================================

def startup(symbol: str, strategy: str) -> None:
    """Initialize everything before the main loop."""
    global _symbol, _strategy_name, _magic, _risk_percent
    global _max_entries_per_day, _state, _broker_offset_sec, _last_offset_check

    _symbol = symbol.upper()
    _strategy_name = strategy.lower()

    # Load symbol-specific parameters
    params = DEFAULT_PARAMS.get(_symbol, {})
    _magic = params.get("magic", FALLBACK_MAGIC)
    _risk_percent = params.get("risk", FALLBACK_RISK)
    _max_entries_per_day = params.get("max_entries", FALLBACK_MAX_ENTRIES)

    setup_logging(_symbol, _strategy_name)
    logger.info("=" * 60)
    logger.info("Multi-Symbol Bot | Symbol=%s Strategy=%s", _symbol, _strategy_name)
    logger.info("Magic=%d Risk=%.2f%% MaxEntries=%d",
                _magic, _risk_percent, _max_entries_per_day)
    logger.info("R:R = 1:%.1f (SL=%.1fxATR TP=%.1fxATR)",
                ATR_TP_MULT / ATR_SL_MULT, ATR_SL_MULT, ATR_TP_MULT)
    logger.info("=" * 60)

    # Load strategy
    if not load_strategy(_symbol, _strategy_name):
        logger.error("Strategy loading failed — exiting")
        sys.exit(1)

    # Connect to MT5
    wait_for_mt5()
    # Log explicit MT5 connection status for the per-symbol log
    _account = mt5.account_info()
    _terminal = mt5.terminal_info()
    if _account:
        logger.info("MT5 connected | account=%s server=%s balance=%.2f trade_allowed=%s",
                     _account.login, _account.server, _account.balance, _account.trade_allowed)
    if _terminal:
        logger.info("Terminal build=%s connected=%s dlls_allowed=%s",
                     _terminal.build, _terminal.connected, _terminal.dlls_allowed)
    _broker_offset_sec = detect_broker_offset()
    _last_offset_check = time.time()
    logger.info("Broker offset: %.0fs", _broker_offset_sec)

    # Initialize FTMO drawdown tracking with current balance
    try:
        acct = mt5.account_info()
        if acct:
            FtmoDrawdownGuard.record_peak(acct.balance)
            dd_info = FtmoDrawdownGuard.get_current_dd(balance=acct.balance)
            logger.info("FTMO Drawdown: DD=%.2f%% Peak=$%.2f",
                        dd_info.get("current_dd_pct", 0.0),
                        dd_info.get("peak_balance", 0.0))
    except Exception:
        pass

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
            
            # Ensure symbol is still selected (catches IPC failures between calls)
            if not ensure_symbol():
                continue

            # Close at end of session
            if at_end_of_session():
                bpos = bot_positions()
                if bpos and len(bpos) > 0:
                    logger.info("End of session — closing positions")
                    close_bot_positions()

            # Trailing stop REMOVED per council verdict P0

            # Status log
            now = time.time()
            if now - _last_status_log >= STATUS_LOG_INTERVAL_SEC:
                log_status()
                _last_status_log = now

            # New bar event — check for entry
            if new_bar_closed():
                reconcile_trade_state()

                # Record peak balance for FTMO drawdown tracking
                try:
                    acct = mt5.account_info()
                    if acct:
                        FtmoDrawdownGuard.record_peak(acct.balance)
                except Exception:
                    pass

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
    symbol = args.symbol.upper()
    strategy = args.strategy.lower()

    # 🔒 PID Lock File — zombie process prevention
    PID_DIR = os.path.join(os.path.dirname(__file__), "locks")
    PID_FILE = os.path.join(PID_DIR, f"{symbol}_{strategy}.pid")
    os.makedirs(PID_DIR, exist_ok=True)
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            print(f"PID {old_pid} still running for {symbol}/{strategy}. Exiting.")
            sys.exit(0)
        except (OSError, ValueError, ProcessLookupError):
            pass
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    def _cleanup_pid():
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    atexit.register(_cleanup_pid)

    startup(symbol, strategy)
    try:
        run_loop()
    finally:
        shutdown_mt5()

if __name__ == "__main__":
    main()
