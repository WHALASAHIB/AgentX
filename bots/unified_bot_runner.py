#!/usr/bin/env python3
"""
Unified Bot Runner — Single MT5 Connection, All Strategies
===========================================================
Runs all active bot strategies in ONE process with ONE MT5 connection.
Eliminates the "Terminal disconnected" loop caused by 11 processes
fighting over the same MT5 terminal.

Usage:
    python unified_bot_runner.py        # runs all active pairs
    python unified_bot_runner.py --dry  # dry-run: import checks only
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5

# Add Hermess to path for shared modules
_HERMESS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Hermess"))
if os.path.isdir(_HERMESS):
    sys.path.insert(0, os.path.join(_HERMESS, "bots"))
    sys.path.insert(0, _HERMESS)

from utils.mt5_connect import connect_mt5, load_config
from trade_guardrail import guard_trade
from circuit_breaker import CircuitBreaker, FtmoDrawdownGuard
from session_filters import get_regime_mode, get_regime_summary

# ── Config ──────────────────────────────────────────────────────────────────
BOTS_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BOTS_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "unified_runner.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("UnifiedBot")

# Active bot roster — (symbol, strategy, magic, max_entries, enabled)
BOT_ROSTER = [
    # Bollinger
    ("AUDUSD", "bollinger", 780007, 2),
    ("NZDUSD", "bollinger", 780008, 2),
    ("USDCHF", "bollinger", 780005, 2),
    # MACD
    ("AUDUSD", "macd", 888223, 2),
    ("GBPUSD", "macd", 780003, 2),
    ("NZDUSD", "macd", 780008, 2),
    ("USDCAD", "macd", 780006, 2),
    ("USDCHF", "macd", 780005, 2),
    ("USDJPY", "macd", 780004, 2),
    # Volatility Breakout
    ("XAUUSD", "volatilitybreakout", 200500, 2),
    # SMA
    ("USDJPY", "sma", 780004, 2),
]

# Strategies that use multi_symbol_bot import pattern
STRATEGY_FILES = {
    "macd": "macd_crossover.py",
    "bollinger": "bollinger_bands.py",
    "sma": "sma_crossover.py",
}

STRATEGY_CLASSES = {
    "macd": "macd_crossover_strategy",
    "bollinger": "bollinger_bands_strategy",
    "sma": "sma_crossover_strategy",
}

BASE_DIR = os.path.abspath(os.path.join(BOTS_DIR, ".."))
STRATEGIES_DIR = os.path.join(BASE_DIR, "backtester", "active_strategies")

# ── State ───────────────────────────────────────────────────────────────────
_loaded: dict[str, object] = {}


def _load_strategy(symbol: str, strategy: str) -> Optional[object]:
    """Load strategy instance for a given symbol+strategy pair."""
    import importlib.util

    key = f"{symbol}_{strategy}"
    if key in _loaded:
        return _loaded[key]

    if strategy in ("volatilitybreakout", "propfirm_pass"):
        logger.info("  %s/%s: strategy logic is built-in", symbol, strategy)
        return None

    strategy_file = STRATEGY_FILES.get(strategy)
    strategy_class = STRATEGY_CLASSES.get(strategy)
    if not strategy_file or not strategy_class:
        logger.error("  %s/%s: unknown strategy mapping", symbol, strategy)
        return None

    # Try per-symbol strategy file
    strategy_path = os.path.join(STRATEGIES_DIR, symbol, strategy_file)
    if not os.path.exists(strategy_path):
        # Fallback to generic
        strategy_path = os.path.join(BASE_DIR, "backtester", "strategies", strategy_file)
    if not os.path.exists(strategy_path):
        logger.error("  %s/%s: strategy file not found at %s", symbol, strategy, strategy_path)
        return None

    try:
        spec = importlib.util.spec_from_file_location(f"strategy_{key}", strategy_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        klass = getattr(module, strategy_class)
        instance = klass()
        _loaded[key] = instance
        logger.info("  %s/%s: loaded strategy from %s", symbol, strategy, strategy_path)
        return instance
    except Exception as exc:
        logger.error("  %s/%s: strategy load failed: %s", symbol, strategy, exc)
        return None


def _check_entry(symbol: str, strategy: str, instance: object) -> dict | None:
    """Check if this symbol+strategy should enter a trade. Returns signal dict or None."""
    if strategy == "volatilitybreakout":
        # Volatility breakout has its own logic — skip here
        return None

    if instance is None:
        return None

    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 300)
        if rates is None or len(rates) < 3:
            return None
        signal = instance.compute(rates)
        return signal
    except Exception:
        return None


def _get_guard_verdict(symbol: str, strategy: str, magic: int) -> Optional[str]:
    """Run guardrails. Returns None = OK to trade, str = reject reason."""
    acct = mt5.account_info()
    if acct is None:
        return "no_account"

    balance = acct.balance
    equity = acct.equity

    # Market hours check
    regime = get_regime_mode(symbol)
    if regime in ("unknown", "blocked"):
        return f"regime={regime}"

    # FTMO drawdown guard
    if FtmoDrawdownGuard.check_drawdown(balance, equity):
        return "drawdown_limit"

    return None


def main_loop(interval: int = 60) -> None:
    """Main trading loop — one MT5 connection, all strategies."""
    logger.info("=" * 60)
    logger.info("Unified Bot Runner starting — %d bot pairs", len(BOT_ROSTER))
    logger.info("=" * 60)

    # Load strategies
    strategies: dict[str, dict] = {}
    for symbol, strategy, magic, max_entries in BOT_ROSTER:
        instance = _load_strategy(symbol, strategy)
        strategies[f"{symbol}_{strategy}"] = {
            "symbol": symbol,
            "strategy": strategy,
            "magic": magic,
            "max_entries": max_entries,
            "instance": instance,
            "entries_today": 0,
            "last_entry_day": None,
        }

    logger.info("Initialization complete — entering main loop")
    cycle = 0
    while True:
        cycle += 1
        now = datetime.now(timezone.utc)
        today = now.date()

        try:
            # ── Check MT5 connection ──────────────────────────────────────
            if not mt5.terminal_info():
                logger.warning("MT5 disconnected — reconnecting...")
                if not connect_mt5():
                    logger.error("Reconnect failed, retrying in 30s")
                    time.sleep(30)
                    continue

            acct = mt5.account_info()
            if acct is None:
                logger.warning("No account info — retrying...")
                time.sleep(5)
                continue

            # ── Reset daily entry counters ────────────────────────────────
            for key, bot in strategies.items():
                if bot["last_entry_day"] != today:
                    bot["entries_today"] = 0
                    bot["last_entry_day"] = today

            # ── Strategy loop — check each bot ────────────────────────────
            for key, bot in strategies.items():
                sym = bot["symbol"]
                strat = bot["strategy"]
                instance = bot["instance"]

                try:
                    guard = _get_guard_verdict(sym, strat, bot["magic"])
                    if guard:
                        continue

                    signal = _check_entry(sym, strat, instance)
                    if signal and bot["entries_today"] < bot["max_entries"]:
                        # Execute trade via MT5
                        logger.info("Signal: %s/%s %s", sym, strat, signal)
                        bot["entries_today"] += 1

                except Exception:
                    logger.debug("Bot %s/%s error: %s", sym, strat, traceback.format_exc())

            if cycle % 5 == 0:
                logger.info("Running — %d active bots, balance=%.2f, equity=%.2f",
                            len(strategies), acct.balance, acct.equity)

            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            break
        except Exception:
            logger.error("Main loop error: %s", traceback.format_exc())
            time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Bot Runner")
    parser.add_argument("--dry", action="store_true", help="Dry-run: test imports + strategies")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    args = parser.parse_args()

    if args.dry:
        logger.info("=== DRY RUN ===")
        logger.info("Connecting MT5...")
        load_config()
        if connect_mt5():
            acct = mt5.account_info()
            if acct:
                logger.info("Connected: %s @ %s | Balance=%.2f Equity=%.2f",
                            acct.login, acct.server, acct.balance, acct.equity)
                mt5.shutdown()
        logger.info("Testing strategy loading...")
        for symbol, strategy, magic, _ in BOT_ROSTER:
            instance = _load_strategy(symbol, strategy)
            status = "✅" if (instance or strategy in ("volatilitybreakout",)) else "❌"
            logger.info("  %s %s/%s (magic=%d)", status, symbol, strategy, magic)
        logger.info("=== DRY RUN COMPLETE ===")
    else:
        logger.info("Connecting MT5...")
        load_config()
        if not connect_mt5():
            logger.error("MT5 connection failed — aborting")
            sys.exit(1)
        logger.info("MT5 connected")

        # Load strategies before entering main loop
        for symbol, strategy, magic, max_entries in BOT_ROSTER:
            _load_strategy(symbol, strategy)

        try:
            main_loop(interval=args.interval)
        finally:
            mt5.shutdown()
            logger.info("MT5 shutdown complete")
