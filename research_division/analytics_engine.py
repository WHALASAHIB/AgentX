"""
analytics_engine.py — Research Division Analytics Engine

Computes comprehensive performance KPIs for pairs, strategies, and time-series
analysis. Consumes trade data from ``data_collector`` (field specification below)
and produces structured reports consumable by the dashboard and other divisions.

Trade fields (from data_collector):
    position_id, symbol, type, volume, entry_price, exit_price,
    open_time, close_time, profit, swap, commission, net_profit,
    duration, magic, comment

Session definitions (HKT = UTC + HKT_OFFSET):
    Asian:  00:00 – 09:00 HKT
    London: 09:00 – 17:00 HKT
    US:     17:00 – 00:00 HKT
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────────

HKT_OFFSET = 8  # UTC → HKT: add 8 hours

SESSION_DEFS: Dict[str, Tuple[int, int]] = {
    "asian":  (0, 9),    # 00:00 – 09:00 HKT
    "london": (9, 17),   # 09:00 – 17:00 HKT
    "us":     (17, 24),  # 17:00 – 00:00 HKT
}

STATE_DIR = os.path.join(os.path.dirname(__file__) or ".", "state")
ANALYTICS_HISTORY_FILE = os.path.join(STATE_DIR, "analytics_history.json")

# ── Helpers ─────────────────────────────────────────────────────────────────────


def _utc_to_hkt(ts_str: str) -> Optional[datetime]:
    """Convert a UTC ISO timestamp string to a timezone-aware HKT datetime.

    Returns None if the string is empty/None/invalid.
    """
    if not ts_str:
        return None
    try:
        dt_utc = datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        try:
            dt_utc = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            return None
    # If the parsed datetime is naive, assume UTC.
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    hkt_tz = timezone(timedelta(hours=HKT_OFFSET))
    return dt_utc.astimezone(hkt_tz)


def _session_for_hour(hour: int) -> str:
    """Return the session label (asian/london/us) for a given HKT hour."""
    if 0 <= hour < 9:
        return "asian"
    elif 9 <= hour < 17:
        return "london"
    else:  # 17–23
        return "us"


def _is_win(trade: dict) -> bool:
    """A trade is a 'win' if net_profit > 0. Ties (net_profit == 0) count as losses."""
    np_val = trade.get("net_profit", 0) or 0
    return float(np_val) > 0


def _net_profit(trade: dict) -> float:
    return float(trade.get("net_profit", 0) or 0)


def _to_native(obj: Any) -> Any:
    """Recursively convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_native(i) for i in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.ndarray,)):
        return _to_native(obj.tolist())
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


# ── Core KPI computation ────────────────────────────────────────────────────────


def compute_pair_kpis(pair: str, trades: List[dict], initial_balance: float = 0.0) -> dict:
    """Compute a comprehensive KPI dictionary for a list of trades.

    Args:
        pair:            Trading pair symbol (e.g. "XAUUSD").
        trades:          List of trade dicts.
        initial_balance: Starting account balance for realistic drawdown calc.

    Returns:
        dict with all KPIs listed in the module spec.
    """
    if not trades:
        return _empty_kpis(pair)

    n = len(trades)
    profits = np.array([_net_profit(t) for t in trades], dtype=np.float64)
    wins_mask = profits > 0
    loss_mask = profits <= 0

    total_wins = int(wins_mask.sum())
    total_losses = int(loss_mask.sum())

    # Gross profit / loss
    gross_profit = float(profits[wins_mask].sum()) if total_wins > 0 else 0.0
    gross_loss = float(abs(profits[loss_mask].sum())) if total_losses > 0 else 0.0

    net = float(profits.sum())

    # Win rate
    win_rate = total_wins / n if n > 0 else 0.0

    # Profit factor
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # Average win / loss
    avg_win = float(profits[wins_mask].mean()) if total_wins > 0 else 0.0
    avg_loss = float(abs(profits[loss_mask].mean())) if total_losses > 0 else 0.0

    # Max consecutive wins / losses
    max_cons_wins = _max_consecutive(wins_mask)
    max_cons_losses = _max_consecutive(loss_mask)

    # Max drawdown % — compute from equity curve (profits + starting balance)
    max_dd_pct = _compute_max_drawdown_pct(trades, initial_balance)

    # Sharpe ratio (annualised, risk-free rate ≈ 0)
    sharpe = _compute_sharpe_ratio(trades)

    # Expectancy
    expectancy = (net / n) / avg_loss if avg_loss > 0 else 0.0
    expectancy_ratio = (win_rate * avg_win) / ((1 - win_rate) * avg_loss) if (1 - win_rate) * avg_loss > 0 else 0.0

    # Duration stats
    avg_duration_minutes = _compute_avg_duration_minutes(trades)
    avg_bars_held = _compute_avg_bars_held(trades)

    # R-multiple
    r_multiple_avg = _compute_r_multiple_avg(trades)

    # Profit per calendar day
    profit_per_day = _compute_profit_per_day(trades)

    # Best / worst trade
    best_trade = _best_trade(trades)
    worst_trade = _worst_trade(trades)

    # Win rate by session
    wr_by_session = _compute_win_rate_by_session(trades)

    # Monthly breakdown
    monthly = _compute_monthly_breakdown(trades)

    return _to_native({
        "pair": pair,
        "total_trades": n,
        "wins": total_wins,
        "losses": total_losses,
        "win_rate": round(win_rate, 4),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_profit": round(net, 2),
        "profit_factor": round(profit_factor, 4) if np.isfinite(profit_factor) else None,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_consecutive_wins": max_cons_wins,
        "max_consecutive_losses": max_cons_losses,
        "max_drawdown_pct": round(max_dd_pct, 4),
        "sharpe_ratio": round(sharpe, 4) if np.isfinite(sharpe) else None,
        "expectancy": round(expectancy, 4),
        "expectancy_ratio": round(expectancy_ratio, 4),
        "avg_bars_held": round(avg_bars_held, 2),
        "avg_duration_minutes": round(avg_duration_minutes, 2),
        "r_multiple_avg": round(r_multiple_avg, 4),
        "profit_per_day": round(profit_per_day, 2),
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "win_rate_by_session": wr_by_session,
        "monthly_breakdown": monthly,
    })


def _empty_kpis(pair: str) -> dict:
    """Return a zeroed-out KPI dict for an empty trade list."""
    return _to_native({
        "pair": pair,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_profit": 0.0,
        "profit_factor": None,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": None,
        "expectancy": 0.0,
        "expectancy_ratio": 0.0,
        "avg_bars_held": 0.0,
        "avg_duration_minutes": 0.0,
        "r_multiple_avg": 0.0,
        "profit_per_day": 0.0,
        "best_trade": None,
        "worst_trade": None,
        "win_rate_by_session": {"asian": 0.0, "london": 0.0, "us": 0.0},
        "monthly_breakdown": {},
    })


def _max_consecutive(mask: np.ndarray) -> int:
    """Compute the longest run of True values in a boolean array."""
    if len(mask) == 0:
        return 0
    # Pad with False on both ends so diff works at boundaries
    padded = np.concatenate(([False], mask, [False]))
    diffs = np.diff(padded.astype(int))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    if len(starts) == 0:
        return 0
    return int((ends - starts).max())


def _compute_max_drawdown_pct(trades: List[dict], initial_balance: float = 0.0) -> float:
    """Compute peak-to-trough drawdown from trade profits relative to starting balance.

    Uses ``initial_balance + cumulative_profits`` as the equity curve so
    drawdowns are expressed as a percentage of peak equity — not peak profit.

    Args:
        trades:          Chronological list of closed trades.
        initial_balance: Account balance before the first trade (default 0).

    Returns:
        Maximum drawdown as a positive percentage (e.g. 15.0 = 15% drop).
        Returns 0.0 if fewer than 2 trades or no drawdowns detected.
    """
    if len(trades) < 2:
        return 0.0

    sorted_trades = sorted(trades, key=lambda t: t.get("close_time", "") or "")
    cumulative = np.cumsum([_net_profit(t) for t in sorted_trades])

    if len(cumulative) < 2:
        return 0.0

    # Equity curve = starting balance + cumulative PnL
    equity = initial_balance + cumulative

    peak = np.maximum.accumulate(equity)
    drawdowns = peak - equity

    # Only consider points where equity < peak
    mask = drawdowns > 1.0  # Ignore sub-$1 noise
    peak_at_dd = peak[mask]
    dd_at_peak = drawdowns[mask]

    if len(peak_at_dd) == 0:
        return 0.0

    # Drawdown % = (peak - current) / peak * 100
    dd_pcts = np.where(peak_at_dd > 0, dd_at_peak / peak_at_dd * 100, 0.0)
    return float(dd_pcts.max())


def _compute_sharpe_ratio(trades: List[dict], annual_factor: float = np.sqrt(252)) -> float:
    """Compute annualised Sharpe ratio from trade returns (net_profit).

    Each trade is treated as one 'period' return. Since trade frequency
    varies, this is an approximation. For high-frequency strategies, a
    time-based resampling would be more accurate.

    Uses the standard formula: Sharpe = (mean(returns) - rfr) / std(returns) * sqrt(periods)
    """
    if len(trades) < 2:
        return 0.0

    profits = np.array([_net_profit(t) for t in trades], dtype=np.float64)
    if profits.std() == 0:
        return 0.0

    # Sort chronologically for return series
    sorted_trades = sorted(trades, key=lambda t: t.get("close_time", "") or "")
    profits_sorted = np.array([_net_profit(t) for t in sorted_trades], dtype=np.float64)

    mean_ret = profits_sorted.mean()
    std_ret = profits_sorted.std()

    if std_ret == 0:
        return 0.0

    sharpe = (mean_ret / std_ret) * annual_factor
    return float(sharpe)


def _parse_duration_to_minutes(duration) -> Optional[float]:
    """Parse a duration value to minutes.

    Handles:
    - Numeric values (already in minutes)
    - String formats: "0h 5m", "1h 47m", "0h 30m", "2h", "30m", "1h30m"
    - Empty or None values (returns None)
    """
    if duration is None:
        return None
    if isinstance(duration, (int, float)):
        return float(duration)
    if not isinstance(duration, str) or not duration.strip():
        return None

    duration = duration.strip()
    # Try simple numeric parse first
    try:
        return float(duration)
    except (ValueError, TypeError):
        pass

    # Parse "Xh Ym" format (e.g. "0h 5m", "1h 47m", "1h30m", "2h", "30m")
    import re
    total_minutes = 0.0
    h_match = re.search(r'(\d+(?:\.\d+)?)\s*h', duration)
    m_match = re.search(r'(\d+(?:\.\d+)?)\s*m', duration)
    if h_match:
        total_minutes += float(h_match.group(1)) * 60
    if m_match:
        total_minutes += float(m_match.group(1))
    return total_minutes if (h_match or m_match) else None


def _compute_avg_duration_minutes(trades: List[dict]) -> float:
    """Compute the average trade duration in minutes from the ``duration`` field."""
    durations = []
    for t in trades:
        d = _parse_duration_to_minutes(t.get("duration"))
        if d is not None:
            durations.append(d)
    if not durations:
        return 0.0
    return float(np.mean(durations))


def _compute_avg_bars_held(trades: List[dict]) -> float:
    """Compute average bars held from duration (minutes / 60 for H1 bars,
    or from a 'bars_held' field if present). Falls back to duration_minutes / 60.
    """
    # If a 'bars_held' field exists, use it
    bars_list = []
    for t in trades:
        bh = t.get("bars_held")
        if bh is not None:
            try:
                bars_list.append(float(bh))
            except (ValueError, TypeError):
                pass
    if bars_list:
        return float(np.mean(bars_list))

    # Fallback: duration_minutes / 60 (H1 bars approximation)
    dur_min = _compute_avg_duration_minutes(trades)
    return dur_min / 60.0 if dur_min > 0 else 0.0


def _compute_r_multiple_avg(trades: List[dict]) -> float:
    """Compute the average R-multiple (reward / risk) across all trades.

    R = |net_profit| / avg_loss_per_losing_trade
    For winning trades: R = net_profit / avg_loss
    For losing trades: R = -|net_loss| / avg_loss = -1 (on average)

    If avg_loss is 0, returns 0.
    """
    if not trades:
        return 0.0

    losses = []
    for t in trades:
        np_val = _net_profit(t)
        if np_val <= 0:
            losses.append(abs(np_val))

    avg_loss = float(np.mean(losses)) if losses else 0.0
    if avg_loss == 0:
        return 0.0

    r_values = []
    for t in trades:
        np_val = _net_profit(t)
        r = np_val / avg_loss
        r_values.append(r)

    if not r_values:
        return 0.0
    return float(np.mean(r_values))


def _compute_profit_per_day(trades: List[dict]) -> float:
    """Compute average net profit per calendar day that had at least one trade."""
    day_profits: Dict[str, List[float]] = defaultdict(list)
    for t in trades:
        dt = _utc_to_hkt(t.get("close_time", ""))
        if dt is None:
            continue
        day_key = dt.strftime("%Y-%m-%d")
        day_profits[day_key].append(_net_profit(t))

    if not day_profits:
        return 0.0

    total_net = sum(sum(p) for p in day_profits.values())
    return total_net / len(day_profits)


def _best_trade(trades: List[dict]) -> Optional[dict]:
    """Return the trade with the highest net_profit."""
    if not trades:
        return None
    return max(trades, key=lambda t: _net_profit(t))


def _worst_trade(trades: List[dict]) -> Optional[dict]:
    """Return the trade with the lowest net_profit."""
    if not trades:
        return None
    return min(trades, key=lambda t: _net_profit(t))


def _compute_win_rate_by_session(trades: List[dict]) -> Dict[str, float]:
    """Compute win rate broken down by Asian / London / US session (HKT)."""
    session_counts: Dict[str, List[bool]] = defaultdict(list)
    for t in trades:
        dt = _utc_to_hkt(t.get("close_time", ""))
        if dt is None:
            continue
        session = _session_for_hour(dt.hour)
        session_counts[session].append(_is_win(t))

    result: Dict[str, float] = {}
    for ses in ("asian", "london", "us"):
        arr = session_counts.get(ses, [])
        result[ses] = round(sum(arr) / len(arr), 4) if arr else 0.0
    return result


def _compute_monthly_breakdown(trades: List[dict]) -> Dict[str, dict]:
    """Group trades by calendar month (HKT close_time) and compute summary stats."""
    monthly: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        dt = _utc_to_hkt(t.get("close_time", ""))
        if dt is None:
            continue
        month_key = dt.strftime("%Y-%m")
        if month_key not in monthly:
            monthly[month_key] = {"trades": 0, "wins": 0, "net": 0.0}
        monthly[month_key]["trades"] += 1
        monthly[month_key]["net"] += _net_profit(t)
        if _is_win(t):
            monthly[month_key]["wins"] += 1

    # Round monetary values
    for m in monthly.values():
        m["net"] = round(m["net"], 2)
    return dict(sorted(monthly.items()))


# ── Strategy KPIs ───────────────────────────────────────────────────────────────


def compute_strategy_kpis(magic: int, trades: List[dict]) -> dict:
    """Compute the same KPI set as :func:`compute_pair_kpis` but filtered
    to a specific magic number.

    Args:
        magic:   MT4/5 magic number to filter by.
        trades:  Full trade list (all pairs).

    Returns:
        KPI dict with an added ``magic`` field.
    """
    filtered = [t for t in trades if int(t.get("magic", 0) or 0) == magic]
    pair_label = f"magic_{magic}"
    kpi = compute_pair_kpis(pair_label, filtered)
    kpi["magic"] = magic
    return kpi


# ── Time analysis ───────────────────────────────────────────────────────────────


def compute_time_analysis(trades: List[dict]) -> dict:
    """Analyse performance by hour-of-day, day-of-week, and trading session.

    Returns:
        dict with keys:
            - by_hour:  {0..23: {trades, wins, net_profit, win_rate}}
            - by_day:   {Mon..Sun: {trades, wins, net_profit, win_rate}}
            - by_session: {asian/london/us: {trades, wins, net_profit, win_rate}}
    """
    by_hour: Dict[int, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "net_profit": 0.0})
    by_day: Dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "net_profit": 0.0})
    by_session: Dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "net_profit": 0.0})

    for t in trades:
        dt = _utc_to_hkt(t.get("close_time", ""))
        if dt is None:
            continue
        hour = dt.hour
        day_name = dt.strftime("%a")  # Mon, Tue, …
        session = _session_for_hour(hour)

        profit = _net_profit(t)
        is_win = _is_win(t)

        for bucket in (by_hour[hour], by_day[day_name], by_session[session]):
            bucket["trades"] += 1
            bucket["net_profit"] += profit
            if is_win:
                bucket["wins"] += 1

    def _finalise(bucket: dict) -> dict:
        t = bucket["trades"]
        return {
            "trades": t,
            "wins": bucket["wins"],
            "net_profit": round(bucket["net_profit"], 2),
            "win_rate": round(bucket["wins"] / t, 4) if t > 0 else 0.0,
        }

    return _to_native({
        "by_hour": {str(k): _finalise(v) for k, v in sorted(by_hour.items())},
        "by_day": {k: _finalise(v) for k, v in sorted(by_day.items(),
                                                       key=lambda item: _day_sort_key(item[0]))},
        "by_session": {k: _finalise(v) for k, v in sorted(by_session.items())},
    })


_DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day_sort_key(day_name: str) -> int:
    """Return a sort index for day-of-week names."""
    try:
        return _DAY_ORDER.index(day_name)
    except ValueError:
        return 99


# ── Market regime analysis ──────────────────────────────────────────────────────


def compute_market_regime_analysis(trades: List[dict],
                                   equity_curve: List[dict]) -> dict:
    """Analyse trade performance segmented by volatility regime.

    Regimes are determined from the equity curve's daily returns:
        - Low volatility:   std of daily returns ≤ 0.5 × overall std
        - Normal volatility: between low and high thresholds
        - High volatility:   std of daily returns > 1.5 × overall std

    Args:
        trades:        List of trade dicts.
        equity_curve:  List of equity-point dicts, each with at least
                       a ``value`` (float) and ``time`` (ISO string).

    Returns:
        dict with:
            - overall_volatility:  daily return std dev
            - regimes: {regime_name: {trades, wins, net_profit, win_rate, volatility}}
            - regime_transitions: count of transitions between regimes in the equity curve
    """
    result: dict = {
        "overall_volatility": 0.0,
        "regimes": {},
        "regime_transitions": 0,
    }

    if not equity_curve or len(equity_curve) < 5:
        return result

    # Build daily returns from equity curve
    sorted_equity = sorted(equity_curve, key=lambda e: str(e.get("time", "")))
    values = []
    for e in sorted_equity:
        try:
            v = float(e.get("value", 0) or 0)
            values.append(v)
        except (ValueError, TypeError):
            continue

    if len(values) < 5:
        return result

    values_arr = np.array(values, dtype=np.float64)
    daily_returns = np.diff(values_arr) / values_arr[:-1]
    daily_returns = daily_returns[np.isfinite(daily_returns)]

    if len(daily_returns) < 2:
        return result

    overall_std = float(daily_returns.std())
    result["overall_volatility"] = round(overall_std, 6)

    # Assign each point in equity curve to a regime
    low_thresh = 0.5 * overall_std
    high_thresh = 1.5 * overall_std

    regime_series = []
    for r in daily_returns:
        abs_r = abs(r)
        if abs_r <= low_thresh:
            regime_series.append("low")
        elif abs_r <= high_thresh:
            regime_series.append("normal")
        else:
            regime_series.append("high")

    # Count transitions
    transitions = 0
    for i in range(1, len(regime_series)):
        if regime_series[i] != regime_series[i - 1]:
            transitions += 1
    result["regime_transitions"] = transitions

    # Compute per-regime volatility
    regime_vol: Dict[str, list] = {"low": [], "normal": [], "high": []}
    for r_val, regime in zip(daily_returns, regime_series):
        regime_vol[regime].append(r_val)

    regime_stats: Dict[str, dict] = {}
    for regime_name in ("low", "normal", "high"):
        vol = float(np.std(regime_vol[regime_name])) if regime_vol[regime_name] else 0.0
        regime_stats[regime_name] = {
            "trades": 0,
            "wins": 0,
            "net_profit": 0.0,
            "win_rate": 0.0,
            "volatility": round(vol, 6),
        }

    # Assign trades to regimes based on close_time → nearest equity point
    # Use the trade's close_time to find which daily return bucket it falls into
    if trades:
        # Build time-indexed mapping of equity periods
        # Sort trades by close_time and assign to the regime at that point in equity curve
        trade_times = []
        for t in trades:
            dt = _utc_to_hkt(t.get("close_time", ""))
            if dt:
                trade_times.append((dt, t))

        trade_times.sort(key=lambda x: x[0])

        # Map each trade to the prevailing regime at its close time
        # by finding the nearest preceding equity point
        eq_times = []
        for e in sorted_equity:
            ts = e.get("time", "")
            dt_eq = _utc_to_hkt(ts) if ts else None
            if dt_eq:
                eq_times.append(dt_eq)

        if eq_times and trade_times:
            eq_times_arr = np.array([dt.timestamp() for dt in eq_times])
            for trade_dt, t in trade_times:
                trade_ts = trade_dt.timestamp()
                # Find index of nearest equity point ≤ trade time
                idx = np.searchsorted(eq_times_arr, trade_ts) - 1
                idx = max(0, min(idx, len(regime_series) - 1))
                regime = regime_series[idx]
                profit = _net_profit(t)
                is_win = _is_win(t)
                regime_stats[regime]["trades"] += 1
                regime_stats[regime]["net_profit"] += profit
                if is_win:
                    regime_stats[regime]["wins"] += 1

    # Finalise regime stats with win rates
    for rs in regime_stats.values():
        t = rs["trades"]
        rs["net_profit"] = round(rs["net_profit"], 2)
        rs["win_rate"] = round(rs["wins"] / t, 4) if t > 0 else 0.0

    result["regimes"] = regime_stats
    return _to_native(result)


# ── Report generation ──────────────────────────────────────────────────────────


def generate_pair_report(pair: str, trades: List[dict],
                         equity: List[dict],
                         positions: List[dict]) -> dict:
    """Generate a full analytics report for a single trading pair.

    Combines pair KPIs, time analysis, regime analysis, and current
    open positions.

    Args:
        pair:      Trading pair symbol.
        trades:    Trade list for this pair.
        equity:    Full equity curve (unfiltered; regime analysis uses overall).
        positions: Currently open positions (unfiltered; caller should filter).

    Returns:
        dict with sections: kpis, time_analysis, market_regime, open_positions.
    """
    # Extract starting balance from equity curve if available
    # Equity curve points may use "equity" or "value" field
    starting_balance = 100000.0  # Default initial balance for drawdown calc
    if equity and len(equity) > 0:
        try:
            starting_balance = float(equity[0].get("equity") or equity[0].get("value") or starting_balance)
        except (ValueError, TypeError, AttributeError):
            pass

    return _to_native({
        "pair": pair,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "kpis": compute_pair_kpis(pair, trades, initial_balance=starting_balance),
        "time_analysis": compute_time_analysis(trades),
        "market_regime": compute_market_regime_analysis(trades, equity),
        "open_positions": len(positions),
        "position_detail": positions,
        "total_trade_count": len(trades),
    })


def generate_all_reports(trades_cache: List[dict],
                         equity: List[dict],
                         positions: List[dict]) -> Dict[str, dict]:
    """Generate reports for every pair present in the trade cache, plus an
    overall (all-pairs) report.

    Args:
        trades_cache:  Full list of trade dicts.
        equity:        Equity curve points.
        positions:     Currently open positions.

    Returns:
        dict mapping pair symbol → report dict, with key ``"overall"`` for
        the aggregate.
    """
    from data_collector import split_trades_by_pair

    # Handle both: list of trades OR dict with 'trades' key (from cache)
    if isinstance(trades_cache, dict):
        trades_list = trades_cache.get("trades", trades_cache.get("trades_cache", []))
    else:
        trades_list = trades_cache or []

    by_pair = split_trades_by_pair(trades_list)

    reports: Dict[str, dict] = {}
    # Overall report
    reports["overall"] = generate_pair_report("OVERALL", trades_list, equity, positions)

    # Per-pair reports
    for pair, pair_trades in sorted(by_pair.items()):
        pair_positions = [p for p in positions if
                          (p.get("symbol") or p.get("pair", "")).upper() == pair.upper()]
        reports[pair] = generate_pair_report(pair, pair_trades, equity, pair_positions)

    return reports


# ── Regression detection ────────────────────────────────────────────────────────


def detect_regression(report: dict, history: List[dict]) -> dict:
    """Compare the latest report against historical reports and detect
    performance regressions or improvements.

    Args:
        report:   Current report dict (from :func:`generate_pair_report`).
        history:  List of historical report dicts (from :func:`load_analytics_history`).

    Returns:
        dict with:
            - improved: bool — True if most KPIs improved
            - changes: list of {metric, old_value, new_value, direction} dicts
    """
    if not history:
        return {"improved": True, "changes": [], "message": "No history to compare against."}

    # Get the most recent historical report for the same pair
    current_pair = report.get("pair", "")
    prev = None
    for h in reversed(history):
        if h.get("pair", "") == current_pair:
            prev = h
            break

    if prev is None:
        return {"improved": True, "changes": [], "message": f"No history for pair {current_pair}."}

    current_kpis = report.get("kpis", {})
    prev_kpis = prev.get("kpis", {})

    # Metrics where higher is better
    higher_better = ["win_rate", "gross_profit", "net_profit", "profit_factor",
                     "avg_win", "sharpe_ratio", "expectancy", "expectancy_ratio",
                     "profit_per_day", "r_multiple_avg"]

    # Metrics where lower is better
    lower_better = ["gross_loss", "avg_loss", "max_consecutive_losses",
                    "max_drawdown_pct"]

    changes = []
    improvements = 0
    regressions = 0

    for metric in higher_better:
        old_val = prev_kpis.get(metric)
        new_val = current_kpis.get(metric)
        if old_val is None or new_val is None:
            continue
        # Skip None sentinels
        if old_val is None or new_val is None:
            continue
        try:
            old_f = float(old_val)
            new_f = float(new_val)
        except (TypeError, ValueError):
            continue
        direction = "improved" if new_f > old_f else ("regressed" if new_f < old_f else "unchanged")
        if direction == "improved":
            improvements += 1
        elif direction == "regressed":
            regressions += 1
        if direction != "unchanged":
            changes.append({
                "metric": metric,
                "old_value": old_f,
                "new_value": new_f,
                "direction": direction,
            })

    for metric in lower_better:
        old_val = prev_kpis.get(metric)
        new_val = current_kpis.get(metric)
        if old_val is None or new_val is None:
            continue
        try:
            old_f = float(old_val)
            new_f = float(new_val)
        except (TypeError, ValueError):
            continue
        direction = "improved" if new_f < old_f else ("regressed" if new_f > old_f else "unchanged")
        if direction == "improved":
            improvements += 1
        elif direction == "regressed":
            regressions += 1
        if direction != "unchanged":
            changes.append({
                "metric": metric,
                "old_value": old_f,
                "new_value": new_f,
                "direction": direction,
            })

    total_compared = improvements + regressions
    improved_overall = improvements >= regressions if total_compared > 0 else True

    return _to_native({
        "improved": improved_overall,
        "changes": changes,
        "improvements": improvements,
        "regressions": regressions,
        "total_compared": total_compared,
    })


# ── Persistence ─────────────────────────────────────────────────────────────────


def save_analytics(reports: dict) -> bool:
    """Persist a snapshot of analytics reports to ``state/analytics_history.json``.

    Appends the current reports as a new entry in the history list,
    each entry keyed by timestamp.

    Args:
        reports: Output of :func:`generate_all_reports`.

    Returns:
        True on success, False on failure.
    """
    history = load_analytics_history() or []
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reports": reports,
    }
    history.append(entry)

    # Keep only the last 30 entries to prevent unbounded growth
    if len(history) > 30:
        history = history[-30:]

    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        with open(ANALYTICS_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2, default=str)
        logger.info("Saved %d analytics entries to %s", len(history), ANALYTICS_HISTORY_FILE)
        return True
    except (OSError, IOError) as e:
        logger.exception("Failed to save analytics to %s: %s", ANALYTICS_HISTORY_FILE, e)
        return False


def load_analytics_history() -> Optional[List[dict]]:
    """Load the full history of analytics snapshots from disk.

    Returns:
        List of history entries (each with ``timestamp`` and ``reports`` keys),
        or None if the file does not exist or is corrupt.
    """
    if not os.path.isfile(ANALYTICS_HISTORY_FILE):
        logger.info("No analytics history file at %s", ANALYTICS_HISTORY_FILE)
        return None
    try:
        with open(ANALYTICS_HISTORY_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        logger.warning("Analytics history file has unexpected format (expected list)")
        return None
    except (json.JSONDecodeError, OSError, IOError) as e:
        logger.warning("Failed to load analytics history from %s: %s",
                       ANALYTICS_HISTORY_FILE, e)
        return None
