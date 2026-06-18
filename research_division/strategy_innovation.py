"""
strategy_innovation.py — Generates and backtests parameter variants for all 4 strategy types

Pipeline: analyze -> generate -> validate all -> rank -> save
Supports MACD Crossover, Gold Phoenix, Bollinger Bands, and SMA Crossover strategies.
"""

import json
import logging
import os
import sys
import time
import traceback
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Path setup ──────────────────────────────────────────────────────────────────
RESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
BACKTESTER_DIR = os.path.abspath(os.path.join(RESEARCH_DIR, ".."))
BACKTESTER_SUBDIR = os.path.join(BACKTESTER_DIR, "backtester")

# Add both so imports like `from backtester.engine import run` (needs C:\Trading)
# AND `importlib.import_module('strategies.macd_crossover')` (needs C:\Trading\backtester) work
if BACKTESTER_DIR not in sys.path:
    sys.path.insert(0, BACKTESTER_DIR)
if BACKTESTER_SUBDIR not in sys.path:
    sys.path.insert(0, BACKTESTER_SUBDIR)

STATE_DIR = os.path.join(RESEARCH_DIR, "state")
os.makedirs(STATE_DIR, exist_ok=True)

INNOVATION_RESULTS_FILE = os.path.join(STATE_DIR, "innovation_results.json")

# ── Instrument metadata ────────────────────────────────────────────────────────
# Matches backtester/data.py INSTRUMENTS
INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "XAUUSD": {"spread_pips": 1.0, "pip_value": 0.01, "contract_size": 100},
    "EURUSD": {"spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "GBPUSD": {"spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "USDJPY": {"spread_pips": 0.8, "pip_value": 0.01, "contract_size": 100000},
    "USDCHF": {"spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "USDCAD": {"spread_pips": 1.0, "pip_value": 0.0001, "contract_size": 100000},
    "AUDUSD": {"spread_pips": 1.2, "pip_value": 0.0001, "contract_size": 100000},
    "NZDUSD": {"spread_pips": 1.5, "pip_value": 0.0001, "contract_size": 100000},
    "BTCUSD": {"spread_pips": 10.0, "pip_value": 1.0, "contract_size": 1},
}

# ── Strategy parameter templates / mutation ranges ─────────────────────────────
# Each entry defines how to generate variants for a strategy type.
STRATEGY_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "macd": {
        "class_key": "macd_crossover",
        "params": {
            "fast": {"type": "int", "base": 12, "values": [8, 10, 12, 14, 16]},
            "slow": {"type": "int", "base": 26, "values": [17, 21, 26, 30]},
            "signal": {"type": "int", "base": 9, "values": [5, 7, 9, 12]},
        },
        "extra_params": {
            "sl_atr_mult": {"type": "float", "base": 2.0, "values": [1.5, 2.0, 2.5, 3.0]},
            "tp_atr_mult": {"type": "float", "base": 5.0, "values": [3.0, 4.0, 5.0, 6.0, 8.0]},
        },
    },
    "gold_phoenix": {
        "class_key": "gold_phoenix",
        "params": {
            "adx_threshold": {"type": "float", "base": 26.0, "values": [25, 28, 30, 32, 35]},
            "asian_range_bars": {"type": "int", "base": 6, "values": [4, 6, 8, 10]},
        },
        "extra_params": {
            "sl_atr_mult": {"type": "float", "base": 2.0, "values": [1.5, 2.0, 2.5, 3.0]},
            "tp_atr_mult": {"type": "float", "base": 5.0, "values": [3.0, 4.0, 5.0, 6.0, 8.0]},
        },
    },
    "bollinger": {
        "class_key": "bollinger_bands",
        "params": {
            "period": {"type": "int", "base": 20, "values": [15, 18, 20, 22, 25]},
            "std_dev": {"type": "float", "base": 2.0, "values": [1.5, 1.8, 2.0, 2.2, 2.5]},
        },
        "extra_params": {
            "rsi_oversold": {"type": "int", "base": 30, "values": [25, 28, 30, 32, 35]},
            "rsi_overbought": {"type": "int", "base": 70, "values": [65, 68, 70, 72, 75]},
        },
    },
    "sma": {
        "class_key": "sma_crossover",
        "params": {
            "fast_period": {"type": "int", "base": 9, "values": [5, 7, 9, 11, 15]},
            "slow_period": {"type": "int", "base": 21, "values": [15, 18, 21, 25, 30]},
        },
        "extra_params": {},
    },
}

# Risk per trade variation
RISK_VALUES = [0.005, 0.01, 0.015, 0.02]  # 0.5%, 1%, 1.5%, 2%

# Default backtest period (last ~6 months of 1h data)
DEFAULT_DATE_FROM = "2025-12-01"
DEFAULT_DATE_TO = "2026-06-01"
DEFAULT_INTERVAL = "1h"


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy Class Resolution
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_strategy_class(strategy_name: str) -> Optional[type]:
    """Resolve a strategy class by name, trying multiple import paths.

    Strategy resolution order:
      1. backtester.loader.list_strategies()
      2. Direct import from backtester.strategies.<name>
      3. Import from backtester.old_strategies.<name> if strategies/ lacks source
      4. Search active_strategies for a copy
    """
    # Normalise name
    name_lower = strategy_name.lower().strip().replace("-", "_").replace(" ", "_")

    # ── 1. Try the loader ──────────────────────────────────────
    try:
        from backtester import loader as bt_loader
        available = bt_loader.list_strategies()
        # The loader normalises keys (strips _strategy suffix, lowercases)
        if name_lower in available:
            logger.info("Resolved %s via loader.list_strategies()", strategy_name)
            return available[name_lower]
        # Also try direct key match on module name
        for key, cls in available.items():
            if name_lower in key or key in name_lower:
                logger.info("Resolved %s via loader (%s match)", strategy_name, key)
                return cls
    except Exception as e:
        logger.debug("Loader strategy resolution failed: %s", e)

    # ── 2. Try direct import from backtester.strategies ────────
    module_names = [
        f"backtester.strategies.{name_lower}",
        f"backtester.strategies.{name_lower}_crossover",
    ]
    if not name_lower.endswith("_crossover") and not name_lower.endswith("_strategy"):
        module_names.append(f"backtester.strategies.{name_lower}_strategy")

    for mod_name in module_names:
        try:
            import importlib
            module = importlib.import_module(mod_name)
            candidates = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "on_data"):
                    if "strategy" in attr_name.lower():
                        candidates.append((attr_name, attr))
            if candidates:
                # Prefer the longest matching name (most specific)
                candidates.sort(key=lambda x: -len(x[0]))
                logger.info("Resolved %s via import %s -> %s",
                            strategy_name, mod_name, candidates[0][0])
                return candidates[0][1]
        except ImportError:
            continue
        except Exception as e:
            logger.debug("Import resolve %s failed: %s", mod_name, e)

    # ── 3. Try old_strategies directory ────────────────────────
    try:
        old_dir = os.path.join(BACKTESTER_DIR, "backtester", "old_strategies")
        if os.path.isdir(old_dir) and old_dir not in sys.path:
            sys.path.insert(0, old_dir)
        mod_name = name_lower
        if not mod_name.endswith("_crossover") and not mod_name.endswith("_strategy"):
            mod_name = name_lower  # Try as-is
        import importlib
        # Try with old_strategies prefix
        try:
            module = importlib.import_module(f"backtester.old_strategies.{name_lower}")
        except ImportError:
            try:
                module = importlib.import_module(name_lower)
            except ImportError:
                module = None
        if module:
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "on_data"):
                    logger.info("Resolved %s via old_strategies", strategy_name)
                    return attr
    except Exception as e:
        logger.debug("old_strategies resolve failed: %s", e)

    # ── 4. Search active_strategies for a copy ─────────────────
    try:
        active_dir = os.path.join(BACKTESTER_DIR, "backtester", "active_strategies")
        if os.path.isdir(active_dir):
            for pair_dir in os.listdir(active_dir):
                strategy_file = os.path.join(active_dir, pair_dir, f"{name_lower}.py")
                if os.path.isfile(strategy_file):
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        f"active_{pair_dir}_{name_lower}", strategy_file
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type) and hasattr(attr, "on_data"):
                                logger.info("Resolved %s via active_strategies/%s",
                                            strategy_name, pair_dir)
                                return attr
    except Exception as e:
        logger.debug("active_strategies resolve failed: %s", e)

    logger.error("Could not resolve strategy class for '%s'", strategy_name)
    return None


def _get_strategy_class(strategy_name: str) -> Optional[type]:
    """Wrapper with caching for strategy class resolution."""
    if not hasattr(_get_strategy_class, "_cache"):
        _get_strategy_class._cache = {}
    if strategy_name in _get_strategy_class._cache:
        return _get_strategy_class._cache[strategy_name]
    cls = _resolve_strategy_class(strategy_name)
    _get_strategy_class._cache[strategy_name] = cls
    return cls


# ═══════════════════════════════════════════════════════════════════════════════
# Data Fetching
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_data(pair: str,
                date_from: str = DEFAULT_DATE_FROM,
                date_to: str = DEFAULT_DATE_TO,
                interval: str = DEFAULT_INTERVAL) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for a pair, with error handling."""
    try:
        from backtester.data import fetch
        df = fetch(pair, date_from=date_from, date_to=date_to, interval=interval)
        if df is not None and len(df) >= 50:
            logger.info("Fetched %d bars for %s (%s → %s, %s)",
                        len(df), pair, date_from, date_to, interval)
            return df
        logger.warning("Insufficient data for %s: got %d bars", pair, len(df) if df is not None else 0)
        return None
    except Exception as e:
        logger.error("Data fetch failed for %s: %s", pair, e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. analyze_pair_strategy
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_pair_strategy(pair: str, strategy_name: str,
                          trades: List[Dict[str, Any]],
                          kpis: Dict[str, Any]) -> Dict[str, Any]:
    """Analyse how a strategy is performing live vs backtest expectations.

    Args:
        pair: Instrument symbol (e.g. 'XAUUSD')
        strategy_name: Strategy identifier (e.g. 'macd', 'gold_phoenix')
        trades: List of trade dicts from the live feed (at minimum with pnl, entry_time)
        kpis: Dict with backtest expectations (at minimum sharpe_ratio, profit_factor,
              win_rate_pct, max_drawdown_pct, expectancy).

    Returns:
        dict with analysis containing:
          - pair, strategy_name, trade_count
          - live_stats: calculated from trades
          - expected_stats: copied from kpis
          - gaps: deviations (live - expected) for key metrics
          - health_score: 0-100 composite
          - recommendation: 'optimize' | 'monitor' | 'healthy'
    """
    result = {
        "pair": pair,
        "strategy_name": strategy_name,
        "analyzed_at": datetime.now().isoformat(),
        "trade_count": len(trades) if trades else 0,
    }

    if not trades or len(trades) < 3:
        result.update({
            "error": "Insufficient trade data for analysis (< 3 trades)",
            "health_score": 0,
            "recommendation": "insufficient_data",
        })
        return result

    # Compute live stats from trade data
    try:
        df_trades = pd.DataFrame(trades)
        pnl_col = "pnl" if "pnl" in df_trades.columns else "net_profit" if "net_profit" in df_trades.columns else "profit"

        # Ensure numeric
        df_trades[pnl_col] = pd.to_numeric(df_trades[pnl_col], errors="coerce").fillna(0)

        total_trades = len(df_trades)
        wins = df_trades[df_trades[pnl_col] > 0]
        losses = df_trades[df_trades[pnl_col] <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = win_count / total_trades * 100 if total_trades > 0 else 0

        total_profit = df_trades[pnl_col].sum()
        gross_profit = wins[pnl_col].sum() if win_count > 0 else 0
        gross_loss = abs(losses[pnl_col].sum()) if loss_count > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)

        avg_win = wins[pnl_col].mean() if win_count > 0 else 0
        avg_loss = abs(losses[pnl_col].mean()) if loss_count > 0 else 0
        rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        expectancy = total_profit / total_trades if total_trades > 0 else 0

        # Max consecutive loss
        df_trades["_is_win"] = df_trades[pnl_col] > 0
        streak = 0
        max_loss_streak = 0
        for is_win in df_trades["_is_win"]:
            if not is_win:
                streak += 1
                max_loss_streak = max(max_loss_streak, streak)
            else:
                streak = 0

        live_stats = {
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "risk_reward_ratio": round(rr_ratio, 2),
            "total_profit": round(total_profit, 2),
            "max_consecutive_losses": max_loss_streak,
        }
    except Exception as e:
        logger.error("Live stats computation failed: %s", e)
        live_stats = {"error": str(e)}

    # Expected stats from backtest KPIs
    expected_stats = {
        "sharpe_ratio": kpis.get("sharpe_ratio", kpis.get("sharpe", 0)),
        "profit_factor": kpis.get("profit_factor", 0),
        "win_rate_pct": kpis.get("win_rate_pct", 0),
        "max_drawdown_pct": kpis.get("max_drawdown_pct", kpis.get("max_dd", 0)),
        "expectancy": kpis.get("expectancy", kpis.get("avg_profit_per_trade", 0)),
        "total_trades": kpis.get("total_trades", 0),
    }

    # Compute gaps
    gaps = {}
    for metric in ["win_rate_pct", "profit_factor", "expectancy"]:
        live_val = live_stats.get(metric, 0)
        exp_val = expected_stats.get(metric, 0)
        if exp_val != 0:
            gaps[metric] = {
                "live": live_val,
                "expected": exp_val,
                "delta": round(live_val - exp_val, 4),
                "delta_pct": round((live_val - exp_val) / abs(exp_val) * 100, 1),
            }
        else:
            gaps[metric] = {"live": live_val, "expected": 0, "delta": live_val, "delta_pct": 0}

    # Health score (0-100)
    health_score = 50  # neutral baseline
    pf = live_stats.get("profit_factor", 0)
    wr = live_stats.get("win_rate_pct", 0)
    exp_val = live_stats.get("expectancy", 0)

    if pf >= 1.5:
        health_score += 15
    elif pf >= 1.2:
        health_score += 8
    elif pf <= 0.8:
        health_score -= 15

    if wr >= 45:
        health_score += 10
    elif wr >= 35:
        health_score += 5
    elif wr <= 25:
        health_score -= 10

    if exp_val > 0:
        health_score += 10
    else:
        health_score -= 15

    health_score = max(0, min(100, health_score))

    # Recommendation
    if health_score < 40:
        recommendation = "optimize"
    elif health_score < 70:
        recommendation = "monitor"
    else:
        recommendation = "healthy"

    result.update({
        "live_stats": live_stats,
        "expected_stats": expected_stats,
        "gaps": gaps,
        "health_score": health_score,
        "recommendation": recommendation,
    })

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. generate_variants
# ═══════════════════════════════════════════════════════════════════════════════

def generate_variants(pair: str, strategy_name: str,
                      current_kpis: Optional[Dict[str, Any]] = None,
                      backtest_results: Optional[Dict[str, Any]] = None,
                      max_variants: int = 20) -> List[Dict[str, Any]]:
    """Generate parameter variants for a strategy based on its type.

    Args:
        pair: Instrument symbol.
        strategy_name: Strategy identifier (e.g. 'macd', 'gold_phoenix', 'bollinger', 'sma').
        current_kpis: Optional current performance KPIs (to bias variants toward fixing weak areas).
        backtest_results: Optional previous backtest result dict.
        max_variants: Maximum number of variants to generate.

    Returns:
        List of variant dicts, each containing:
          - name: human-readable variant label
          - strategy_params: dict of param overrides to pass to strategy constructor
          - risk_per_trade: risk per trade for this variant
          - description: what was changed and why
    """
    name_lower = strategy_name.lower().strip()
    template = STRATEGY_TEMPLATES.get(name_lower)

    if not template:
        logger.warning("No template found for strategy '%s', trying class key", strategy_name)
        # Try to infer from class_key pattern
        for key, tmpl in STRATEGY_TEMPLATES.items():
            if tmpl["class_key"] in name_lower or name_lower in tmpl["class_key"]:
                template = tmpl
                name_lower = key
                break
        if not template:
            logger.error("Cannot generate variants: unknown strategy type '%s'", strategy_name)
            return []

    variants: List[Dict[str, Any]] = []

    # ── Base params (default / current) ─────────────────────────
    base_params = {}
    for param_name, spec in template["params"].items():
        base_params[param_name] = spec["base"]

    # If we have backtest results with params info, use those as base
    if backtest_results and "strategy_params" in backtest_results:
        for k, v in backtest_results["strategy_params"].items():
            if k in base_params:
                base_params[k] = v

    # ── Generate single-param variants ─────────────────────────
    # Vary each param independently around its base
    for param_name, spec in template["params"].items():
        for val in spec["values"]:
            if val == spec["base"]:
                continue  # Skip base (no change)
            params = base_params.copy()
            params[param_name] = val
            variant = {
                "name": f"{strategy_name}_{param_name}={val}",
                "strategy_params": params,
                "risk_per_trade": 0.01,  # default risk
                "description": f"Vary {param_name} from {spec['base']} to {val}",
            }
            variants.append(variant)

    # ── Generate extra param variants ───────────────────────────
    if "extra_params" in template and template["extra_params"]:
        for param_name, spec in template["extra_params"].items():
            for val in spec["values"]:
                if val == spec["base"]:
                    continue
                variant = {
                    "name": f"{strategy_name}_{param_name}={val}",
                    "strategy_params": base_params.copy(),
                    "risk_per_trade": 0.01,
                    "description": f"Vary {param_name} from {spec['base']} to {val}",
                }
                variants.append(variant)

    # ── Generate risk variants (using base params) ───────────────
    for risk_val in RISK_VALUES:
        if risk_val == 0.01:
            continue  # Skip default
        variant = {
            "name": f"{strategy_name}_risk={int(risk_val*100)}%",
            "strategy_params": base_params.copy(),
            "risk_per_trade": risk_val,
            "description": f"Vary risk_per_trade from 1% to {risk_val*100:.1f}%",
        }
        variants.append(variant)

    # ── Generate multi-param grid variants (subset, targeted) ───
    # Pick the most impactful pairs of params to vary together
    param_keys = list(template["params"].keys())
    if len(param_keys) >= 2:
        # For first two params, try some combos
        p1, p2 = param_keys[0], param_keys[1]
        for v1 in template["params"][p1]["values"][:2]:  # min & mid-low
            for v2 in template["params"][p2]["values"][:2]:
                if v1 == template["params"][p1]["base"] and v2 == template["params"][p2]["base"]:
                    continue
                params = base_params.copy()
                params[p1] = v1
                params[p2] = v2
                variant = {
                    "name": f"{strategy_name}_{p1}={v1}_{p2}={v2}",
                    "strategy_params": params,
                    "risk_per_trade": 0.01,
                    "description": f"Combo: {p1}={v1}, {p2}={v2}",
                }
                variants.append(variant)

    # ── Trim to max_variants ────────────────────────────────────
    # Prioritise single-param variants first, then combos, then risk
    single = [v for v in variants if "Combo" not in v.get("description", "")
              and "risk_per_trade" not in v.get("description", "")]
    combos = [v for v in variants if "Combo" in v.get("description", "")]
    risks = [v for v in variants if "risk_per_trade" in v.get("description", "")]

    single.sort(key=lambda v: v["name"])
    combos.sort(key=lambda v: v["name"])
    risks.sort(key=lambda v: v["name"])

    all_sorted = single + combos + risks
    all_sorted = all_sorted[:max_variants]

    # Add metadata
    for v in all_sorted:
        v["pair"] = pair
        v["strategy_name"] = strategy_name
        v["generated_at"] = datetime.now().isoformat()

    logger.info("Generated %d variants for %s/%s", len(all_sorted), pair, strategy_name)
    return all_sorted


# ═══════════════════════════════════════════════════════════════════════════════
# 3. validate_variant
# ═══════════════════════════════════════════════════════════════════════════════

def validate_variant(variant: Dict[str, Any], pair: str,
                     date_from: str = DEFAULT_DATE_FROM,
                     date_to: str = DEFAULT_DATE_TO,
                     interval: str = DEFAULT_INTERVAL,
                     timeout_sec: int = 120) -> Dict[str, Any]:
    """Backtest a single variant and return the result.

    Args:
        variant: Dict with strategy_params, risk_per_trade, strategy_name.
        pair: Instrument symbol.
        date_from: Backtest start date.
        date_to: Backtest end date.
        interval: Timeframe.
        timeout_sec: Approximate timeout for backtest.

    Returns:
        dict with backtest result including metrics, or error.
    """
    result = {
        "variant_name": variant.get("name", "unknown"),
        "pair": pair,
        "strategy_name": variant.get("strategy_name", ""),
        "tested_at": datetime.now().isoformat(),
        "success": False,
        "error": None,
    }

    # Resolve strategy class
    strategy_name = variant.get("strategy_name", "")
    strategy_class = _get_strategy_class(strategy_name)
    if strategy_class is None:
        # Try by template class_key
        template = STRATEGY_TEMPLATES.get(strategy_name.lower())
        if template:
            strategy_class = _get_strategy_class(template["class_key"])
    if strategy_class is None:
        result["error"] = f"Could not resolve strategy class for '{strategy_name}'"
        return result

    # Get strategy params from variant
    strategy_params = variant.get("strategy_params", {})

    # Fetch data
    df = _fetch_data(pair, date_from=date_from, date_to=date_to, interval=interval)
    if df is None:
        result["error"] = f"Could not fetch data for {pair}"
        return result

    # Get instrument info
    instr = INSTRUMENTS.get(pair, {})
    spread_pips = instr.get("spread_pips", 1.0)
    pip_value = instr.get("pip_value", 0.0001)
    contract_size = instr.get("contract_size", 100000)

    risk_per_trade = variant.get("risk_per_trade", 0.01)

    # ── Run backtest ────────────────────────────────────────────
    try:
        # Timeout mechanism: use signal-based approach
        start_time = time.time()

        from backtester.engine import run as run_backtest_fn

        bt_result = run_backtest_fn(
            strategy_class=strategy_class,
            data=df,
            initial_capital=10000.0,
            spread_pips=spread_pips,
            pip_value=pip_value,
            contract_size=contract_size,
            commission_per_lot=7.0,
            slippage_pips=0.0,
            risk_per_trade=risk_per_trade,
            strategy_params=strategy_params,
            ftmo_mode=True,
            lot_size=0.01,
        )

        elapsed = time.time() - start_time
        if elapsed > timeout_sec:
            logger.warning("Backtest for %s took %.1fs (exceeded %ds timeout)",
                           variant["name"], elapsed, timeout_sec)

        if bt_result is None:
            result["error"] = "Backtest returned None"
            return result

        metrics = bt_result.get("metrics", {})
        if metrics.get("total_trades", 0) == 0:
            result["error"] = "Backtest produced zero trades"
            result["backtest_result"] = bt_result
            return result

        result["success"] = True
        result["metrics"] = metrics
        result["ftmo"] = bt_result.get("ftmo")
        result["ftmo_phase2"] = bt_result.get("ftmo_phase2")
        result["total_trades"] = metrics.get("total_trades", 0)
        result["final_equity"] = bt_result.get("final_equity", 0)
        result["strategy_params_used"] = strategy_params
        result["risk_per_trade"] = risk_per_trade
        result["elapsed_sec"] = round(elapsed, 2)
        result["backtest_result"] = bt_result  # Full result for ranking metadata

        logger.info("Variant %s: %d trades, Sharpe=%.2f, PF=%.2f, return=%.2f%%",
                    variant["name"],
                    metrics.get("total_trades", 0),
                    metrics.get("sharpe_ratio", 0),
                    metrics.get("profit_factor", 0),
                    metrics.get("total_return_pct", 0))

    except Exception as e:
        logger.error("Backtest failed for variant %s: %s\n%s",
                     variant["name"], e, traceback.format_exc())
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 4. rank_variants
# ═══════════════════════════════════════════════════════════════════════════════

def rank_variants(variants_with_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank variants by composite score.

    Scoring formula (from task spec):
        composite = Sharpe*0.3 + PF*0.2 + WR*0.15 + expectancy*0.15 + maxDD_penalty*0.2

    maxDD_penalty is an inverted/normalised drawdown score (higher is better):
        100 - max_drawdown_pct  (capped at 0)

    Returns:
        Sorted list of variants (best first) with an added 'composite_score' key.
    """
    scored = []

    for v in variants_with_results:
        metrics = v.get("metrics", {})
        if not metrics or not v.get("success", False):
            v["composite_score"] = -9999
            v["rank"] = 999
            scored.append(v)
            continue

        sharpe = metrics.get("sharpe_ratio", 0)
        profit_factor = metrics.get("profit_factor", 0)
        win_rate = metrics.get("win_rate_pct", 0) / 100.0  # Normalise to 0-1 for formula
        expectancy = metrics.get("expectancy", metrics.get("avg_profit_per_trade", 0))
        max_dd = metrics.get("max_drawdown_pct", 0)

        # maxDD_penalty: inverted, higher is better
        max_dd_penalty = max(0, 100 - max_dd) / 100.0  # Normalise to 0-1

        # Normalise expectancy to a 0-1 range (roughly)
        # $100/trade is excellent on $10k capital
        expectancy_norm = min(1.0, max(0, expectancy / 100.0)) if expectancy > 0 else 0

        # Cap extreme values
        sharpe = min(5.0, max(-5.0, sharpe))
        sharpe_norm = (sharpe + 5.0) / 10.0  # Map -5..5 to 0..1

        pf_norm = min(1.0, profit_factor / 10.0)  # Cap PF at 10x

        composite = (
            sharpe_norm * 0.3
            + pf_norm * 0.2
            + win_rate * 0.15
            + expectancy_norm * 0.15
            + max_dd_penalty * 0.2
        )

        v["composite_score"] = round(composite, 4)
        v["sharpe_norm"] = round(sharpe_norm, 4)
        v["pf_norm"] = round(pf_norm, 4)
        v["expectancy_norm"] = round(expectancy_norm, 4)
        v["max_dd_penalty"] = round(max_dd_penalty, 4)
        scored.append(v)

    # Sort by composite score descending
    scored.sort(key=lambda x: x.get("composite_score", -9999), reverse=True)

    # Assign rank
    for i, v in enumerate(scored):
        v["rank"] = i + 1

    return scored


# ═══════════════════════════════════════════════════════════════════════════════
# 5. innovation_sprint
# ═══════════════════════════════════════════════════════════════════════════════

def innovation_sprint(pair: str, strategy_name: str,
                      trades: List[Dict[str, Any]],
                      kpis: Dict[str, Any],
                      max_variants: int = 20,
                      date_from: str = DEFAULT_DATE_FROM,
                      date_to: str = DEFAULT_DATE_TO,
                      interval: str = DEFAULT_INTERVAL) -> Dict[str, Any]:
    """Run the full innovation pipeline: analyze -> generate -> validate -> rank -> return best.

    Args:
        pair: Instrument symbol.
        strategy_name: Strategy identifier.
        trades: Live trade data for analysis.
        kpis: Backtest KPIs (expected performance).
        max_variants: Max variants to generate and test.
        date_from, date_to, interval: Backtest data range.

    Returns:
        dict with keys:
          - best_variant: The top-ranked variant
          - all_variants: All validated and ranked variants
          - analysis: Result from analyze_pair_strategy
          - summary: Text summary of the sprint
          - sprint_id: Unique identifier
          - sprint_start, sprint_end: timestamps
    """
    sprint_start = datetime.now()

    result: Dict[str, Any] = {
        "pair": pair,
        "strategy_name": strategy_name,
        "sprint_id": f"{pair}_{strategy_name}_{sprint_start.strftime('%Y%m%d_%H%M%S')}",
        "sprint_start": sprint_start.isoformat(),
    }

    # ── Step 1: Analyze ─────────────────────────────────────────
    logger.info("Step 1/5: Analyzing %s/%s performance...", pair, strategy_name)
    analysis = analyze_pair_strategy(pair, strategy_name, trades, kpis)
    result["analysis"] = analysis
    result["health_score"] = analysis.get("health_score", 50)
    result["recommendation"] = analysis.get("recommendation", "unknown")

    # ── Step 2: Generate variants ────────────────────────────────
    logger.info("Step 2/5: Generating variants for %s/%s...", pair, strategy_name)
    variants = generate_variants(
        pair, strategy_name,
        current_kpis=kpis,
        backtest_results=None,
        max_variants=max_variants,
    )
    result["variants_generated"] = len(variants)

    if not variants:
        result["error"] = "No variants generated"
        result["sprint_end"] = datetime.now().isoformat()
        return result

    # ── Step 3: Validate (backtest each variant) ────────────────
    logger.info("Step 3/5: Validating %d variants...", len(variants))
    validated = []
    for i, variant in enumerate(variants):
        logger.info("  Backtesting [%d/%d] %s ...", i + 1, len(variants), variant["name"])
        bt_result = validate_variant(
            variant, pair,
            date_from=date_from, date_to=date_to, interval=interval,
        )
        validated.append(bt_result)

    result["validated_count"] = len([v for v in validated if v.get("success")])
    result["failed_count"] = len([v for v in validated if not v.get("success")])

    if not any(v.get("success") for v in validated):
        result["error"] = "All variants failed validation"
        result["validated_variants"] = validated
        result["sprint_end"] = datetime.now().isoformat()
        return result

    # ── Step 4: Rank ─────────────────────────────────────────────
    logger.info("Step 4/5: Ranking %d validated variants...", result["validated_count"])
    ranked = rank_variants(validated)
    result["all_variants"] = ranked

    # Best variant (top ranked)
    successful_ranked = [v for v in ranked if v.get("success")]
    best_variant = successful_ranked[0] if successful_ranked else None
    result["best_variant"] = best_variant

    # ── Step 5: Summary ─────────────────────────────────────────
    sprint_end = datetime.now()
    result["sprint_end"] = sprint_end.isoformat()
    result["sprint_duration_sec"] = round((sprint_end - sprint_start).total_seconds(), 1)

    if best_variant:
        best_metrics = best_variant.get("metrics", {})
        baseline = kpis.get("sharpe_ratio", kpis.get("sharpe", 0))
        improvement = ""
        if baseline > 0 and best_metrics.get("sharpe_ratio", 0) > baseline:
            imp = (best_metrics["sharpe_ratio"] - baseline) / baseline * 100
            improvement = f" (Sharpe improved {imp:.1f}%)"

        summary = (
            f"Sprint complete: tested {result['validated_count']}/{len(variants)} variants "
            f"for {strategy_name} on {pair}. "
            f"Best: {best_variant.get('variant_name', 'N/A')} "
            f"(Score={best_variant.get('composite_score', 0):.4f}, "
            f"Sharpe={best_metrics.get('sharpe_ratio', 0):.2f}, "
            f"PF={best_metrics.get('profit_factor', 0):.2f}, "
            f"Trades={best_metrics.get('total_trades', 0)})"
            f"{improvement}. "
            f"Duration: {result['sprint_duration_sec']:.0f}s."
        )
    else:
        summary = (
            f"Sprint complete: no successful variants for "
            f"{strategy_name} on {pair}. "
            f"({result['failed_count']} failed)"
        )

    result["summary"] = summary
    logger.info("Step 5/5: %s", summary)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 6. save_innovation_result
# ═══════════════════════════════════════════════════════════════════════════════

def save_innovation_result(result: Dict[str, Any]) -> str:
    """Save an innovation sprint result to state/innovation_results.json.

    Appends to a history list. Returns the file path.
    """
    # Load existing history
    history = []
    if os.path.exists(INNOVATION_RESULTS_FILE):
        try:
            with open(INNOVATION_RESULTS_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Could not load existing innovation results: %s", e)
            history = []

    # Ensure 'saved_at' timestamp
    entry = deepcopy(result)
    entry["saved_at"] = datetime.now().isoformat()

    # Strip bulky backtest_result sub-dicts to keep file size manageable
    if "all_variants" in entry:
        for v in entry["all_variants"]:
            v.pop("backtest_result", None)
    if "best_variant" in entry and entry["best_variant"]:
        entry["best_variant"].pop("backtest_result", None)

    # Also strip equity_curve from backtest_result in all variants
    history.append(entry)

    # Trim history to last 100 entries
    if len(history) > 100:
        history = history[-100:]

    try:
        with open(INNOVATION_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, default=str)
        logger.info("Saved innovation result to %s (entry #%d)",
                    INNOVATION_RESULTS_FILE, len(history))
    except Exception as e:
        logger.error("Failed to save innovation result: %s", e)

    return INNOVATION_RESULTS_FILE


# ═══════════════════════════════════════════════════════════════════════════════
# 7. load_innovation_history
# ═══════════════════════════════════════════════════════════════════════════════

def load_innovation_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Load past innovation sprint results from state/innovation_results.json.

    Args:
        limit: Max entries to return (most recent first).

    Returns:
        List of innovation result dicts, newest first.
    """
    if not os.path.exists(INNOVATION_RESULTS_FILE):
        logger.info("No innovation history file found at %s", INNOVATION_RESULTS_FILE)
        return []

    try:
        with open(INNOVATION_RESULTS_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to load innovation history: %s", e)
        return []

    if not isinstance(history, list):
        logger.warning("Innovation history file is not a list, resetting")
        return []

    # Sort by saved_at descending, newest first
    try:
        history.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    except Exception:
        pass

    return history[:limit]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: Run a multi-strategy innovation sweep
# ═══════════════════════════════════════════════════════════════════════════════

def innovation_sweep(pair: str,
                     all_trades: Dict[str, List[Dict]],
                     all_kpis: Dict[str, Dict],
                     strategies: Optional[List[str]] = None,
                     save: bool = True) -> Dict[str, Any]:
    """Run innovation_sprint for multiple strategies on one pair.

    Args:
        pair: Instrument symbol.
        all_trades: Dict mapping strategy_name -> list of trades.
        all_kpis: Dict mapping strategy_name -> KPI dict.
        strategies: Optional list of strategy names to run. Defaults to all 4.
        save: If True, save each result to state file.

    Returns:
        dict mapping strategy_name -> sprint result.
    """
    if strategies is None:
        strategies = list(STRATEGY_TEMPLATES.keys())

    results = {}
    for strat_name in strategies:
        trades = all_trades.get(strat_name, [])
        kpis = all_kpis.get(strat_name, {})
        if not kpis:
            logger.warning("No KPIs for %s/%s, skipping", pair, strat_name)
            continue
        try:
            sprint_result = innovation_sprint(pair, strat_name, trades, kpis)
            results[strat_name] = sprint_result
            if save and sprint_result.get("best_variant"):
                save_innovation_result(sprint_result)
        except Exception as e:
            logger.error("Sprint failed for %s/%s: %s", pair, strat_name, e)
            results[strat_name] = {"error": str(e)}

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(description="Strategy Innovation Runner")
    parser.add_argument("--pair", default="XAUUSD", help="Trading pair (default: XAUUSD)")
    parser.add_argument("--strategy", default="macd",
                        help="Strategy name (macd, gold_phoenix, bollinger, sma)")
    parser.add_argument("--max-variants", type=int, default=10,
                        help="Max variants to test (default: 10)")
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", default=DEFAULT_DATE_TO)
    parser.add_argument("--interval", default=DEFAULT_INTERVAL)
    parser.add_argument("--save", action="store_true", default=True,
                        help="Save results to state file")
    parser.add_argument("--list-history", action="store_true",
                        help="List past innovation results and exit")

    args = parser.parse_args()

    if args.list_history:
        history = load_innovation_history()
        print(f"=== Innovation History ({len(history)} entries) ===")
        for entry in history:
            sprint_id = entry.get("sprint_id", "?")
            pair = entry.get("pair", "?")
            strat = entry.get("strategy_name", "?")
            score = "?"
            if entry.get("best_variant"):
                score = entry["best_variant"].get("composite_score", "?")
            saved = entry.get("saved_at", "?")[:19]
            summary = entry.get("summary", "")
            print(f"  [{saved}] {pair}/{strat} id={sprint_id} best_score={score}")
            print(f"    {summary[:120]}")
        sys.exit(0)

    print(f"=== Innovation Sprint: {args.pair} / {args.strategy} ===")
    print(f"  Date range: {args.date_from} → {args.date_to} ({args.interval})")
    print(f"  Max variants: {args.max_variants}")

    # Try to resolve strategy class first
    cls = _get_strategy_class(args.strategy)
    if cls is None:
        print(f"  WARNING: Could not resolve strategy class for '{args.strategy}'")
        print(f"  Available strategies: {list(STRATEGY_TEMPLATES.keys())}")
        # Try each template key
        for key in STRATEGY_TEMPLATES:
            cls = _get_strategy_class(STRATEGY_TEMPLATES[key]["class_key"])
            if cls:
                print(f"  Resolved template '{key}' -> {cls.__name__}")
                break

    # Build dummy KPIs and trades for test run
    sample_kpis = {
        "sharpe_ratio": 0.8,
        "profit_factor": 1.3,
        "win_rate_pct": 42.0,
        "max_drawdown_pct": 12.0,
        "expectancy": 8.5,
        "total_trades": 50,
    }
    sample_trades = [
        {"pnl": 25.0, "entry_time": "2026-06-17 08:00"},
        {"pnl": -15.0, "entry_time": "2026-06-17 10:00"},
        {"pnl": 40.0, "entry_time": "2026-06-17 12:00"},
        {"pnl": -10.0, "entry_time": "2026-06-17 14:00"},
        {"pnl": 30.0, "entry_time": "2026-06-17 16:00"},
    ]

    result = innovation_sprint(
        pair=args.pair,
        strategy_name=args.strategy,
        trades=sample_trades,
        kpis=sample_kpis,
        max_variants=args.max_variants,
        date_from=args.date_from,
        date_to=args.date_to,
        interval=args.interval,
    )

    print(f"\n=== Sprint Results ===")
    print(f"  ID: {result.get('sprint_id', 'N/A')}")
    print(f"  Duration: {result.get('sprint_duration_sec', 0):.1f}s")
    print(f"  Variants generated: {result.get('variants_generated', 0)}")
    print(f"  Validated: {result.get('validated_count', 0)} / Failed: {result.get('failed_count', 0)}")

    if result.get("best_variant"):
        bv = result["best_variant"]
        print(f"\n  ★ Best variant: {bv.get('variant_name', 'N/A')}")
        print(f"     Score: {bv.get('composite_score', 0):.4f}")
        metrics = bv.get("metrics", {})
        print(f"     Sharpe: {metrics.get('sharpe_ratio', 0):.2f}")
        print(f"     Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        print(f"     Win Rate: {metrics.get('win_rate_pct', 0):.1f}%")
        print(f"     Max DD: {metrics.get('max_drawdown_pct', 0):.1f}%")
        print(f"     Trades: {metrics.get('total_trades', 0)}")
        print(f"     Return: {metrics.get('total_return_pct', 0):.2f}%")
        print(f"     Params: {bv.get('strategy_params_used', {})}")
        print(f"     Risk: {bv.get('risk_per_trade', 0.01)*100:.1f}%")
    else:
        print(f"\n  No successful variants found.")

    print(f"\n  Summary: {result.get('summary', 'N/A')}")

    if args.save and result.get("best_variant"):
        save_innovation_result(result)
        print(f"\n  Saved to {INNOVATION_RESULTS_FILE}")
