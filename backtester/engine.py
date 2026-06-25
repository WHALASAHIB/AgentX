"""
engine.py — Backtest Simulation Engine
========================================
Runs a backtest using OHLC data and a strategy class.
Simulates entries based on the strategy's next() signals,
tracks PnL, and returns performance metrics.

Interface expected from strategy_class:
    __init__(self, data, **kwargs)
    next(self, i) -> dict   (must contain "action": "buy" | "sell" | None)
    name -> str

Returns:
    dict with keys:
        metrics       — dict of performance metrics
        equity_curve  — list of {time, equity} dicts
        trades        — list of trade dicts
        ftmo          — FTMO phase 1 evaluation dict or None
        ftmo_phase2   — FTMO phase 2 evaluation dict or None
        final_equity  — float
"""

import logging
import math
from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── FTMO Challenge Defaults ──────────────────────────────────────────────────
FTMO_PHASE1_PROFIT_TARGET = 0.10  # 10%
FTMO_PHASE1_MAX_DD = 0.10  # 10% daily loss or total drawdown
FTMO_PHASE1_MIN_DAYS = 4
FTMO_PHASE1_MAX_DAYS = 30
FTMO_PHASE2_PROFIT_TARGET = 0.05  # 5%
FTMO_PHASE2_MAX_DD = 0.10


def run(
    strategy_class: type,
    data: pd.DataFrame,
    initial_capital: float = 10_000.0,
    spread_pips: float = 1.0,
    pip_value: float = 0.0001,
    contract_size: int = 100_000,
    risk_per_trade: float = 0.01,
    strategy_params: Optional[dict] = None,
    ftmo_mode: bool = True,
    lot_size: float = 0.01,
) -> dict:
    """Run a full backtest simulation.

    Parameters
    ----------
    strategy_class : type
        A class with __init__(self, data, **kwargs) and next(self, i) -> dict.
    data : pd.DataFrame
        OHLC data with columns: time, open, high, low, close, (optional tick_volume).
    initial_capital : float
        Starting account balance.
    spread_pips : float
        Spread in pips (deducted per trade round-trip).
    pip_value : float
        Monetary value per pip for the instrument.
    contract_size : int
        Units per lot (e.g. 100,000 for forex standard lot).
    risk_per_trade : float
        Fraction of capital risked per trade (default 1%).
    strategy_params : dict or None
        Additional kwargs passed to the strategy class constructor.
    ftmo_mode : bool
        If True, evaluate FTMO challenge compliance.
    lot_size : float
        Lot size for position sizing (e.g. 0.01 = micro lot).

    Returns
    -------
    dict with keys: metrics, equity_curve, trades, ftmo, ftmo_phase2, final_equity
    """
    if strategy_params is None:
        strategy_params = {}

    if data is None or len(data) < 20:
        logger.error("Insufficient data (%d bars) for backtest", len(data) if data is not None else 0)
        return _empty_result(initial_capital, "Insufficient data")

    # Ensure required columns
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(data.columns)
    if missing:
        logger.error("Missing columns in data: %s", missing)
        return _empty_result(initial_capital, f"Missing columns: {missing}")

    # Normalise time column
    df = data.copy()
    if "time" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["time"]):
        df["time"] = pd.to_datetime(df["time"])

    # Instantiate the strategy
    try:
        strategy = strategy_class(df, **strategy_params)
    except Exception as exc:
        logger.error("Failed to instantiate strategy %s: %s", strategy_class, exc)
        return _empty_result(initial_capital, f"Strategy init error: {exc}")

    logger.info(
        "Starting backtest: %s | capital=%.2f | lot=%.4f | spread=%.1f pips",
        strategy.name, initial_capital, lot_size, spread_pips,
    )

    # ── Simulation state ─────────────────────────────────────────────────
    balance = initial_capital
    equity = initial_capital
    peak_equity = initial_capital

    position: Optional[dict] = None  # {"side": "buy"/"sell", "entry_price": float, "entry_time": ..., "bars_held": int}
    trades: list[dict] = []
    eq_curve: list[dict] = []

    # For metrics
    pnl_list: list[float] = []

    # For drawdown tracking
    max_dd = 0.0
    dd_start_equity = initial_capital

    # For FTMO daily tracking
    daily_pnl: dict[str, float] = {}
    daily_peak: dict[str, float] = {}

    n = len(df)

    for i in range(n):
        row = df.iloc[i]
        ts = row["time"]
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        date_key = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]

        # --- Generate signal ---
        try:
            signal = strategy.next(i)
        except Exception as exc:
            logger.debug("Strategy.next() error at bar %d: %s", i, exc)
            signal = {"action": None}

        action = signal.get("action") if isinstance(signal, dict) else None

        # --- Close existing position (if any) on opposite signal or on each bar ---
        if position is not None:
            pos_side = position["side"]
            exit_price = close
            exit_reason = "signal"

            # Check if we have an opposite signal
            should_close = False
            if action == "buy" and pos_side == "sell":
                should_close = True
            elif action == "sell" and pos_side == "buy":
                should_close = True

            if should_close:
                # Close position
                pnl = _calc_pnl(pos_side, position["entry_price"], exit_price, lot_size, contract_size, pip_value)
                pnl -= spread_pips * pip_value * lot_size * contract_size  # spread cost
                balance += pnl
                pnl_list.append(pnl)

                trades.append({
                    "entry_time": str(position["entry_time"]),
                    "exit_time": str(ts),
                    "side": pos_side,
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "pnl": round(pnl, 2),
                    "pnl_pips": round((exit_price - position["entry_price"]) / pip_value * (1 if pos_side == "buy" else -1), 1),
                    "pnl_pct": round(pnl / initial_capital * 100, 2) if initial_capital else 0.0,
                    "exit_reason": exit_reason,
                    "bars_held": i - position.get("entry_index", i),
                })
                position = None

        # --- Enter new position ---
        if position is None and action in ("buy", "sell"):
            position = {
                "side": action,
                "entry_price": open_price,  # enter at next bar's open
                "entry_time": ts,
                "entry_index": i,
                "bars_held": 0,
            }

        # --- Update equity (mark-to-market) ---
        if position is not None:
            pos_side = position["side"]
            unrealized = _calc_pnl(pos_side, position["entry_price"], close, lot_size, contract_size, pip_value)
            equity = balance + unrealized
        else:
            equity = balance

        # Track equity curve
        eq_curve.append({
            "time": ts,
            "equity": round(equity, 2),
            "balance": round(balance, 2),
        })

        # Track peak equity and drawdown
        if equity > peak_equity:
            peak_equity = equity
            dd_start_equity = peak_equity

        current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if current_dd > max_dd:
            max_dd = current_dd

        # FTMO daily tracking
        if ftmo_mode:
            if date_key not in daily_pnl:
                daily_pnl[date_key] = 0.0
                daily_peak[date_key] = equity
            daily_pnl[date_key] += (equity - daily_peak[date_key]) if equity < daily_peak[date_key] else 0
            if equity > daily_peak[date_key]:
                daily_peak[date_key] = equity

    # --- Close any remaining open position at last bar ---
    if position is not None:
        exit_price = float(df.iloc[-1]["close"])
        pnl = _calc_pnl(position["side"], position["entry_price"], exit_price, lot_size, contract_size, pip_value)
        pnl -= spread_pips * pip_value * lot_size * contract_size
        balance += pnl
        pnl_list.append(pnl)
        trades.append({
            "entry_time": str(position["entry_time"]),
            "exit_time": str(df.iloc[-1]["time"]),
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "pnl_pips": round((exit_price - position["entry_price"]) / pip_value * (1 if position["side"] == "buy" else -1), 1),
            "pnl_pct": round(pnl / initial_capital * 100, 2) if initial_capital else 0.0,
            "exit_reason": "end_of_data",
            "bars_held": n - position.get("entry_index", n - 1),
        })
        position = None

    final_equity = balance

    # ── Compute Metrics ──────────────────────────────────────────────────
    metrics = _compute_metrics(pnl_list, eq_curve, initial_capital, final_equity, max_dd, daily_pnl)

    # ── FTMO Evaluation ──────────────────────────────────────────────────
    ftmo_result = None
    ftmo_phase2_result = None
    if ftmo_mode:
        ftmo_result = _evaluate_ftmo_phase1(
            pnl_list, eq_curve, daily_pnl, initial_capital, final_equity, n, df
        )
        if ftmo_result and ftmo_result.get("passed"):
            ftmo_phase2_result = _evaluate_ftmo_phase2(
                pnl_list, eq_curve, daily_pnl, initial_capital, final_equity, n, df
            )

    logger.info(
        "Backtest complete: %d trades, net=%.2f, win_rate=%.1f%%, Sharpe=%.2f, max_dd=%.1f%%",
        metrics.get("total_trades", 0),
        metrics.get("net_profit", 0),
        metrics.get("win_rate", 0) * 100,
        metrics.get("sharpe", 0),
        metrics.get("max_dd", 0) * 100,
    )

    return {
        "metrics": metrics,
        "equity_curve": eq_curve,
        "trades": trades,
        "ftmo": ftmo_result,
        "ftmo_phase2": ftmo_phase2_result,
        "final_equity": round(final_equity, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

def _calc_pnl(
    side: str,
    entry_price: float,
    exit_price: float,
    lot_size: float,
    contract_size: int,
    pip_value: float,
) -> float:
    """Calculate PnL for a single trade."""
    price_diff = (exit_price - entry_price) * (1 if side == "buy" else -1)
    return price_diff * lot_size * contract_size if pip_value != 0 else 0.0


def _compute_metrics(
    pnl_list: list[float],
    eq_curve: list[dict],
    initial_capital: float,
    final_equity: float,
    max_dd: float,
    daily_pnl: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute aggregate backtest metrics."""
    total_trades = len(pnl_list)
    net_profit = final_equity - initial_capital
    total_return = net_profit / initial_capital if initial_capital > 0 else 0.0

    win_rate = 0.0
    profit_factor = 0.0
    sharpe = 0.0

    if total_trades > 0:
        wins = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p < 0]
        win_rate = len(wins) / total_trades

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

        # Sharpe ratio (using PnL as returns proxy)
        if len(pnl_list) > 1:
            pnl_array = np.array(pnl_list, dtype=float)
            mean_pnl = np.mean(pnl_array)
            std_pnl = np.std(pnl_array, ddof=1)
            sharpe = (mean_pnl / std_pnl) * np.sqrt(252) if std_pnl > 1e-10 else 0.0

    avg_trade = net_profit / total_trades if total_trades > 0 else 0.0

    # Expectancy = avg_win * win_rate - avg_loss * loss_rate
    expectancy = 0.0
    if total_trades > 0:
        wins = [p for p in pnl_list if p > 0]
        losses = [p for p in pnl_list if p < 0]
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        loss_rate = len(losses) / total_trades if losses else 0.0
        expectancy = avg_win * win_rate - avg_loss * loss_rate

    # Max daily drawdown as % of initial capital (worst single day)
    max_daily_dd_pct = 0.0
    if daily_pnl and initial_capital > 0:
        worst_day = min(daily_pnl.values()) if daily_pnl else 0.0
        if worst_day < 0:
            max_daily_dd_pct = abs(worst_day) / initial_capital

    return {
        "total_return": round(total_return, 4),
        "net_profit": round(net_profit, 2),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "sharpe": round(sharpe, 4),
        "max_dd": round(max_dd, 4),
        "avg_trade": round(avg_trade, 2),
        "expectancy": round(expectancy, 4),
        "max_daily_dd_pct": round(max_daily_dd_pct, 4),
    }


def _evaluate_ftmo_phase1(
    pnl_list, eq_curve, daily_pnl, initial_capital, final_equity, n_bars, df
) -> dict:
    """Evaluate FTMO Phase 1 (Challenge)."""
    total_return = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    # Max drawdown from equity curve
    eq_values = [p["equity"] for p in eq_curve]
    peak = 0.0
    max_dd_val = 0.0
    for eq_val in eq_values:
        if eq_val > peak:
            peak = eq_val
        dd = (peak - eq_val) / peak if peak > 0 else 0.0
        if dd > max_dd_val:
            max_dd_val = dd

    # Max daily loss
    max_daily_loss = min(daily_pnl.values()) / initial_capital if daily_pnl and min(daily_pnl.values()) < 0 else 0.0

    # Days traded (unique trading days)
    days_traded = len(set(
        str(ts)[:10] for ts in df["time"]
    )) if "time" in df.columns else n_bars

    passed = (
        total_return >= FTMO_PHASE1_PROFIT_TARGET
        and max_dd_val <= FTMO_PHASE1_MAX_DD
        and max_daily_loss >= -FTMO_PHASE1_MAX_DD
        and days_traded >= FTMO_PHASE1_MIN_DAYS
    )

    return {
        "passed": passed,
        "profit": round(total_return * 100, 2),
        "max_drawdown": round(max_dd_val * 100, 2),
        "max_daily_loss": round(max_daily_loss * 100, 2),
        "days_traded": days_traded,
        "target_profit": FTMO_PHASE1_PROFIT_TARGET * 100,
        "max_dd_allowed": FTMO_PHASE1_MAX_DD * 100,
    }


def _evaluate_ftmo_phase2(
    pnl_list, eq_curve, daily_pnl, initial_capital, final_equity, n_bars, df
) -> dict:
    """Evaluate FTMO Phase 2 (Verification)."""
    total_return = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    eq_values = [p["equity"] for p in eq_curve]
    peak = 0.0
    max_dd_val = 0.0
    for eq_val in eq_values:
        if eq_val > peak:
            peak = eq_val
        dd = (peak - eq_val) / peak if peak > 0 else 0.0
        if dd > max_dd_val:
            max_dd_val = dd

    days_traded = len(set(
        str(ts)[:10] for ts in df["time"]
    )) if "time" in df.columns else n_bars

    passed = (
        total_return >= FTMO_PHASE2_PROFIT_TARGET
        and max_dd_val <= FTMO_PHASE2_MAX_DD
    )

    return {
        "passed": passed,
        "profit": round(total_return * 100, 2),
        "max_drawdown": round(max_dd_val * 100, 2),
        "days_traded": days_traded,
        "target_profit": FTMO_PHASE2_PROFIT_TARGET * 100,
        "max_dd_allowed": FTMO_PHASE2_MAX_DD * 100,
    }


def _empty_result(initial_capital: float, reason: str = "") -> dict:
    """Return an empty/failed backtest result."""
    return {
        "metrics": {
            "total_return": 0.0,
            "net_profit": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "max_dd": 0.0,
            "avg_trade": 0.0,
            "expectancy": 0.0,
            "max_daily_dd_pct": 0.0,
        },
        "equity_curve": [
            {"time": "start", "equity": initial_capital},
            {"time": "end", "equity": initial_capital},
        ],
        "trades": [],
        "ftmo": None,
        "ftmo_phase2": None,
        "final_equity": initial_capital,
        "error": reason,
    }
