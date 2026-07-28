#!/usr/bin/env python3
"""
Edge Scanner — brute-force parameter scan + pattern recognition engine.
Orchestrates data loading, indicator scanning, pattern detection,
statistical validation, and council review.

One pair per run (rotating). 3+ years of M1 data cached locally.
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from math import sqrt
from typing import Any, Optional

import numpy as np

# Add project root to path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

from data_cache import (
    get_data, get_next_pair, print_data_summary,
    ROTATION, TIMEFRAME_NAMES, STATE_DIR as CACHE_STATE_DIR
)
from indicator_lib import INDICATOR_REGISTRY, TOTAL_COMBOS
from pattern_lib import PATTERN_REGISTRY, PATTERN_COMBOS

STATE_DIR = os.path.join(BASE_DIR, "state")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger("edge_scanner")


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class EdgeResult:
    """A single discovered edge candidate."""
    run_timestamp: float
    pair: str
    timeframe: str
    indicator: str
    parameters: dict
    trades: int
    win_rate: float
    profit_factor: float
    sharpe: float
    avg_win: float
    avg_loss: float
    max_drawdown_pct: float
    max_cons_losses: int
    total_return_pct: float
    walk_forward_pass: bool
    oos_win_rate: float
    oos_profit_factor: float
    p_value: float
    council_quant: float = 0.0
    council_microstructure: float = 0.0
    council_behavioral: float = 0.0
    council_risk: float = 0.0
    council_strategy: float = 0.0
    council_final: float = 0.0
    economic_rationale: str = ""
    who_loses: str = ""
    status: str = "candidate"
    discovered: str = ""
    session_bias: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanReport:
    """Complete scan output for one run."""
    run_timestamp: float
    datetime_utc: str
    pair: str
    timeframes_scanned: list[str]
    total_combos: int
    scan_duration_seconds: float
    candidates_found: int
    edges: list[dict]
    data_summary: dict
    council_verdicts: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def write(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return path


# ============================================================================
# Performance Metrics
# ============================================================================

def compute_metrics(signals: np.ndarray, close: np.ndarray,
                    forward_bars: int = 5) -> dict:
    """
    Compute comprehensive performance metrics for a signal array.
    Forward returns over `forward_bars` bars after signal.

    Returns dict with:
      trades, win_rate, profit_factor, sharpe, avg_win, avg_loss,
      max_drawdown_pct, max_cons_losses, total_return_pct
    """
    n = len(signals)
    if n < forward_bars + 1:
        return {"trades": 0, "win_rate": 0, "profit_factor": 0, "sharpe": 0,
                "avg_win": 0, "avg_loss": 0, "max_drawdown_pct": 0,
                "max_cons_losses": 0, "total_return_pct": 0}

    # Forward returns: percentage change over forward_bars
    forward_returns = np.full(n, np.nan)
    for i in range(n - forward_bars):
        forward_returns[i] = (close[i + forward_bars] - close[i]) / close[i] * 100

    # Find signal points (non-zero)
    signal_mask = signals != 0
    signal_indices = np.where(signal_mask)[0]

    if len(signal_indices) < 5:
        return {"trades": 0, "win_rate": 0, "profit_factor": 0, "sharpe": 0,
                "avg_win": 0, "avg_loss": 0, "max_drawdown_pct": 0,
                "max_cons_losses": 0, "total_return_pct": 0}

    # Get returns at signal points
    sig_returns = forward_returns[signal_indices]
    sig_directions = signals[signal_indices]

    # Trade outcomes (direction * return)
    trade_results = sig_directions * sig_returns
    trade_results = trade_results[~np.isnan(trade_results)]

    if len(trade_results) < 5:
        return {"trades": 0, "win_rate": 0, "profit_factor": 0, "sharpe": 0,
                "avg_win": 0, "avg_loss": 0, "max_drawdown_pct": 0,
                "max_cons_losses": 0, "total_return_pct": 0}

    trades = len(trade_results)
    wins = trade_results[trade_results > 0]
    losses = trade_results[trade_results < 0]
    win_rate = len(wins) / trades if trades > 0 else 0
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 0
    total_return = np.sum(trade_results)

    # Profit factor
    gross_profit = np.sum(wins) if len(wins) > 0 else 1e-10
    gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 1e-10
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Sharpe ratio (annualized approximation)
    avg_return = np.mean(trade_results)
    std_return = np.std(trade_results, ddof=1)
    sharpe = (avg_return / std_return * sqrt(252)) if std_return > 0 and avg_return > 0 else 0

    # Max consecutive losses
    cons_losses = 0
    max_cons = 0
    for r in trade_results:
        if r < 0:
            cons_losses += 1
            max_cons = max(max_cons, cons_losses)
        else:
            cons_losses = 0

    # Max drawdown from cumulative returns
    cum_returns = np.cumsum(trade_results)
    running_max = np.maximum.accumulate(cum_returns)
    drawdowns = cum_returns - running_max
    max_dd = abs(min(drawdowns)) if len(drawdowns) > 0 else 0

    return {
        "trades": trades,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "sharpe": round(sharpe, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "max_cons_losses": max_cons,
        "total_return_pct": round(total_return, 4),
    }


def compute_walk_forward(ohlcv_dict: dict, signal_func, params: dict,
                         forward_bars: int = 5) -> dict:
    """
    3-split walk-forward validation.
    Returns dict with in-sample and out-of-sample metrics.
    """
    close = ohlcv_dict["close"]
    high = ohlcv_dict["high"]
    low = ohlcv_dict["low"]
    open_p = ohlcv_dict["open"]
    volume = ohlcv_dict.get("tick_volume", np.zeros_like(close))

    n = len(close)
    split1 = int(n * 0.5)
    split2 = int(n * 0.75)

    sections = {
        "train": (0, split1),
        "validate": (split1, split2),
        "test": (split2, n),
    }

    results = {}
    for name, (start, end) in sections.items():
        c = close[start:end]
        h = high[start:end]
        lo = low[start:end]
        o = open_p[start:end]
        v = volume[start:end]

        signals = signal_func(o, h, lo, c, v, params)
        metrics = compute_metrics(signals, c, forward_bars)
        results[name] = metrics

    # Walk-forward pass = win_rate > 0 in ALL 3 splits
    all_positive = all(
        results[s].get("win_rate", 0) > 0.5
        for s in ["train", "validate", "test"]
    )
    wf_positive = all(
        results[s].get("profit_factor", 0) > 1.0
        for s in ["train", "validate", "test"]
    )
    walk_forward_pass = all_positive or wf_positive

    return {
        "results": results,
        "walk_forward_pass": walk_forward_pass,
        "oos_wr": results.get("test", {}).get("win_rate", 0),
        "oos_pf": results.get("test", {}).get("profit_factor", 0),
    }


def compute_p_value(win_rate: float, trades: int, null_hypothesis: float = 0.5) -> float:
    """
    Approximate p-value using z-score (normal approximation to binomial).
    H0: true win rate = 0.5 (no edge).
    """
    if trades < 10:
        return 1.0
    p_hat = win_rate
    p0 = null_hypothesis
    se = sqrt(p0 * (1 - p0) / trades)
    if se == 0:
        return 1.0
    z = (p_hat - p0) / se
    # Two-tailed p-value via approximation
    p = np.exp(-0.717 * z - 0.416 * z * z)  # Standard normal survival function approx
    return min(max(p, 0), 1.0)


# ============================================================================
# Scanner
# ============================================================================

def run_scan(pair: str, timeframe: str, min_trades: int = 30,
             force_refresh: bool = False) -> list[EdgeResult]:
    """
    Run full parameter scan on one pair × one timeframe.
    Returns list of EdgeResult objects (filtered and ranked).
    """
    logger.info("Scanning %s %s...", pair, timeframe)

    # Forward bars depends on timeframe and target RR
    # 1:2 RR means price must move 2x the stop distance
    # We look at forward return matching ~2 ATR or fixed pips
    forward_map = {"M5": 12, "M15": 8, "H1": 5, "H4": 3, "D1": 2}
    forward_bars = forward_map.get(timeframe, 5)

    # Get data
    data = get_data(pair, timeframe, force_refresh=force_refresh)
    if data is None or len(data) < 10:
        logger.warning("Insufficient data for %s %s", pair, timeframe)
        return []

    ohlcv = {
        "open": data["open"],
        "high": data["high"],
        "low": data["low"],
        "close": data["close"],
        "tick_volume": data["tick_volume"].astype(float),
    }

    n_bars = len(data["close"])
    # Split: last 20% for OOS, first 80% for IS
    oos_start = int(n_bars * 0.8)
    logger.info("  %s %s: %d bars total, %d in-sample, %d out-of-sample",
                pair, timeframe, n_bars, oos_start, n_bars - oos_start)

    candidates = []

    # --- Indicator-based scan ---
    for ind_name, ind_spec in INDICATOR_REGISTRY.items():
        signal_func = ind_spec["func"]

        for param_set in ind_spec["params"]:
            # Compute signals on full dataset
            try:
                signals = signal_func(ohlcv["open"], ohlcv["high"], ohlcv["low"],
                                      ohlcv["close"], ohlcv["tick_volume"], param_set)
            except Exception as e:
                logger.debug("  %s %s error: %s", ind_name, param_set, e)
                continue

            # In-sample metrics
            is_signals = signals[:oos_start]
            is_close = ohlcv["close"][:oos_start]
            metrics = compute_metrics(is_signals, is_close, forward_bars)

            if metrics["trades"] < min_trades:
                continue

            # Minimum quality thresholds
            if metrics["win_rate"] < 0.52 or metrics["profit_factor"] < 1.1:
                continue

            # Walk-forward validation
            wf = compute_walk_forward(
                {k: v[:oos_start] for k, v in ohlcv.items()},
                signal_func, param_set, forward_bars
            )

            if not wf["walk_forward_pass"]:
                continue

            # OOS test
            oos_signals = signals[oos_start:]
            oos_close = ohlcv["close"][oos_start:]
            oos_metrics = compute_metrics(oos_signals, oos_close, forward_bars)

            if oos_metrics["trades"] < max(10, min_trades // 3):
                continue
            if oos_metrics["win_rate"] < 0.50 or oos_metrics["profit_factor"] < 1.0:
                continue

            # Statistical significance
            p_value = compute_p_value(metrics["win_rate"], metrics["trades"])

            # Combine metrics
            candidate = EdgeResult(
                run_timestamp=time.time(),
                pair=pair,
                timeframe=timeframe,
                indicator=ind_name,
                parameters=param_set,
                trades=metrics["trades"],
                win_rate=metrics["win_rate"],
                profit_factor=metrics["profit_factor"],
                sharpe=metrics["sharpe"],
                avg_win=metrics["avg_win"],
                avg_loss=metrics["avg_loss"],
                max_drawdown_pct=metrics["max_drawdown_pct"],
                max_cons_losses=metrics["max_cons_losses"],
                total_return_pct=metrics["total_return_pct"],
                walk_forward_pass=True,
                oos_win_rate=oos_metrics["win_rate"],
                oos_profit_factor=oos_metrics["profit_factor"],
                p_value=p_value,
                discovered=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            )
            candidates.append(candidate)
            logger.info("  ✅ %s | %s | %s %s | WR=%.1f%% PF=%.2f OOS-WR=%.1f%% p=%.4f",
                        pair, timeframe, ind_name, param_set,
                        metrics["win_rate"] * 100, metrics["profit_factor"],
                        oos_metrics["win_rate"] * 100, p_value)

    # --- Pattern-based scan ---
    timestamps = data["time"]
    for pat_name, pat_spec in PATTERN_REGISTRY.items():
        signal_func = pat_spec["func"]
        for param_set in pat_spec["params"]:
            try:
                signals = signal_func(ohlcv["open"], ohlcv["high"], ohlcv["low"],
                                      ohlcv["close"], ohlcv["tick_volume"],
                                      timestamps, param_set)
            except Exception as e:
                logger.debug("  %s error: %s", pat_name, e)
                continue

            is_signals = signals[:oos_start]
            is_close = ohlcv["close"][:oos_start]
            metrics = compute_metrics(is_signals, is_close, forward_bars)

            if metrics["trades"] < min_trades // 2:
                continue
            if metrics["win_rate"] < 0.52 or metrics["profit_factor"] < 1.1:
                continue

            oos_signals = signals[oos_start:]
            oos_close = ohlcv["close"][oos_start:]
            oos_metrics = compute_metrics(oos_signals, oos_close, forward_bars)

            if oos_metrics["trades"] < 5 or oos_metrics["win_rate"] < 0.50:
                continue

            p_value = compute_p_value(metrics["win_rate"], metrics["trades"])

            candidate = EdgeResult(
                run_timestamp=time.time(),
                pair=pair,
                timeframe=timeframe,
                indicator=pat_name,
                parameters=param_set,
                trades=metrics["trades"],
                win_rate=metrics["win_rate"],
                profit_factor=metrics["profit_factor"],
                sharpe=metrics["sharpe"],
                avg_win=metrics["avg_win"],
                avg_loss=metrics["avg_loss"],
                max_drawdown_pct=metrics["max_drawdown_pct"],
                max_cons_losses=metrics["max_cons_losses"],
                total_return_pct=metrics["total_return_pct"],
                walk_forward_pass=True,
                oos_win_rate=oos_metrics["win_rate"],
                oos_profit_factor=oos_metrics["profit_factor"],
                p_value=p_value,
                discovered=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            )
            candidates.append(candidate)
            logger.info("  ✅ %s | %s | %s | WR=%.1f%% PF=%.2f OOS-WR=%.1f%%",
                        pair, timeframe, pat_name,
                        metrics["win_rate"] * 100, metrics["profit_factor"],
                        oos_metrics["win_rate"] * 100)

    return candidates


# ============================================================================
# Holm-Bonferroni Correction
# ============================================================================

def holm_bonferroni(candidates: list[EdgeResult],
                    total_tests: int, alpha: float = 0.05) -> list[EdgeResult]:
    """
    Apply Holm-Bonferroni correction for multiple comparisons.
    More powerful than Bonferroni while still controlling family-wise error rate.
    """
    if not candidates:
        return []

    # Sort by p-value ascending
    sorted_cands = sorted(candidates, key=lambda c: c.p_value)
    m = total_tests

    surviving = []
    for i, c in enumerate(sorted_cands):
        adjusted_alpha = alpha / (m - i)  # Holm step-down
        if c.p_value <= adjusted_alpha:
            surviving.append(c)
        else:
            # Once one fails, all subsequent also fail (stricter thresholds)
            break

    return surviving


# ============================================================================
# Session / Calendar Segment Analysis
# ============================================================================

def analyze_session_bias(data: np.ndarray, signals: np.ndarray,
                          pair: str, timeframe: str) -> dict:
    """
    Analyze which sessions/calendar segments produce the best signal performance.
    """
    from pattern_lib import session_times, day_of_week

    close = data["close"]
    timestamps = data["time"]

    sessions = session_times(timestamps)
    days = day_of_week(timestamps)

    results = {}

    # Session analysis
    for session_name, mask in sessions.items():
        sig_at_session = signals[mask]
        close_at_session = close[mask]
        if len(sig_at_session) > 10:
            metrics = compute_metrics(sig_at_session, close_at_session, 5)
            results[f"session_{session_name}"] = metrics

    # Day-of-week analysis
    for day_name, mask in days.items():
        sig_on_day = signals[mask]
        close_on_day = close[mask]
        if len(sig_on_day) > 10:
            metrics = compute_metrics(sig_on_day, close_on_day, 5)
            results[f"day_{day_name}"] = metrics

    return results


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Edge Discovery Scanner")
    parser.add_argument("--pair", type=str, default=None,
                        help="Force specific pair (default: auto-rotate)")
    parser.add_argument("--timeframe", type=str, default=None,
                        help="Single timeframe only (default: all)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Force re-download of M1 data")
    parser.add_argument("--file-only", action="store_true",
                        help="Only write JSON output")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress verbose output")
    parser.add_argument("--min-trades", type=int, default=30,
                        help="Minimum trades for a candidate (default: 30)")
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="Significance level for multiple comparison correction")
    args = parser.parse_args()

    # Logging
    log_level = logging.WARNING if (args.quiet or args.file_only) else logging.INFO
    logging.basicConfig(level=log_level,
                        format="%(asctime)s | %(levelname)s | %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

    log_path = os.path.join(LOGS_DIR, "edge_scanner.log")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logging.getLogger().addHandler(fh)

    start_time = time.time()

    # Determine which pair to scan
    pair = args.pair or get_next_pair()
    timeframes = [args.timeframe] if args.timeframe else TIMEFRAME_NAMES  # M5/M15/H1/H4/D1

    logger.info("=" * 60)
    logger.info("Edge Discovery Scan — %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    logger.info("Pair: %s | Timeframes: %s", pair, ", ".join(timeframes))
    logger.info("Total indicator combos: %d | Pattern combos: %d",
                TOTAL_COMBOS, PATTERN_COMBOS)
    logger.info("=" * 60)

    # Print data summary
    if not args.quiet and not args.file_only:
        print(f"\n{'='*60}")
        print(f"  EDGE DISCOVERY SCAN — {pair}")
        print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}\n")

        print("  Data Summary:")
        for tf in timeframes:
            d = get_data(pair, tf, force_refresh=args.force_refresh)
            print_data_summary(d, pair, tf)
        print()

    # Run scan per timeframe
    all_candidates: list[EdgeResult] = []
    for tf in timeframes:
        candidates = run_scan(pair, tf, args.min_trades, args.force_refresh)
        all_candidates.extend(candidates)

    # Apply multiple comparison correction
    total_tests = TOTAL_COMBOS + PATTERN_COMBOS
    surviving = holm_bonferroni(all_candidates, total_tests, args.alpha)

    # Sort by combined score (WR * PF * sqrt(trades))
    def combined_score(c: EdgeResult) -> float:
        return c.win_rate * c.profit_factor * sqrt(c.trades)

    surviving.sort(key=combined_score, reverse=True)

    # Take top 10 for council review (or fewer)
    top_n = min(10, len(surviving))
    top_candidates = surviving[:top_n]

    scan_duration = time.time() - start_time

    # Build report
    report = ScanReport(
        run_timestamp=time.time(),
        datetime_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        pair=pair,
        timeframes_scanned=timeframes,
        total_combos=total_tests,
        scan_duration_seconds=round(scan_duration, 1),
        candidates_found=len(all_candidates),
        edges=[c.to_dict() for c in top_candidates],
        data_summary={},
        council_verdicts=[],
    )

    # Save state
    state_file = os.path.join(STATE_DIR, "edge_state.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)

    # Archive
    archive_file = os.path.join(
        ARCHIVE_DIR,
        f"scan_{pair}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    report.write(archive_file)

    # Output
    if not args.file_only and not args.quiet:
        print(f"\n{'='*60}")
        print(f"  SCAN RESULTS — {pair}")
        print(f"  Duration: {scan_duration:.1f}s | Combos: {total_tests}")
        print(f"  Candidates found: {len(all_candidates)}")
        print(f"  Surviving Holm-Bonferroni: {len(surviving)}")
        print(f"{'='*60}\n")

        if top_candidates:
            for i, c in enumerate(top_candidates):
                print(f"  [{i+1}] {c.pair} {c.timeframe} | {c.indicator} | params={c.parameters}")
                print(f"      WR={c.win_rate*100:.1f}% PF={c.profit_factor:.2f} "
                      f"Sharpe={c.sharpe:.2f} Trades={c.trades}")
                print(f"      OOS-WR={c.oos_win_rate*100:.1f}% OOS-PF={c.oos_profit_factor:.2f} "
                      f"p={c.p_value:.4f}")
                print(f"      MaxDD={c.max_drawdown_pct:.1f}% MaxConsLoss={c.max_cons_losses}")
                print()
        else:
            print("  ⚠️  No statistically significant edges found.\n")
            print("  This is expected — true edges are rare.\n")

        print(f"  Report saved: {archive_file}")
        print(f"  State file: {state_file}")
        print()

    # For cron: print a one-line summary
    print(f"edge_discovery | {pair} | {len(all_candidates)} candidates | "
          f"{len(top_candidates)} edges | {scan_duration:.0f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
