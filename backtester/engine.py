"""
AGENTX Backtester — Core Backtesting Engine
Processes strategy signals against historical data and computes performance metrics.
Enhanced with: R:R, expectancy, streaks, prop firm 2-step, deploy recommendation.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def run(
    strategy_class,
    data: pd.DataFrame,
    initial_capital: float = 10000.0,
    spread_pips: float = 1.0,
    pip_value: float = 0.0001,
    contract_size: float = 100,  # units per lot (100 oz for XAUUSD, 100k for forex)
    commission_per_lot: float = 7.0,
    slippage_pips: float = 0.0,
    risk_per_trade: float = 0.01,
    strategy_params: dict = None,
    ftmo_mode: bool = True,
    lot_size: float = 0.01,
) -> dict:
    """
    Run a full backtest for a given strategy.

    Args:
        strategy_class: Strategy class (instantiated inside)
        data: OHLCV DataFrame with columns: date, open, high, low, close [, volume]
        initial_capital: Starting account balance
        spread_pips: Spread in pips
        pip_value: Value of one pip for the instrument
        contract_size: Units per standard lot (100 for XAUUSD, 100000 for EURUSD)
        commission_per_lot: Commission per standard lot (round turn)
        slippage_pips: Slippage in pips applied on entry/exit
        risk_per_trade: Fraction of capital risked per trade
        ftmo_mode: If True, applies FTMO challenge rules (10% drawdown limit, profit target)
        lot_size: Base lot size
        strategy_params: Dict of params to pass to strategy constructor

    Returns:
        dict with keys: metrics, equity_curve, trades, ftmo, final_equity
    """
    strategy_params = strategy_params or {}

    # Ensure data is sorted
    data = data.copy().sort_values("date").reset_index(drop=True)
    if "date" not in data.columns:
        raise ValueError("Data must have a 'date' column")

    # Instantiate strategy
    strategy = strategy_class(**strategy_params) if strategy_params else strategy_class()

    # Generate signals
    df = strategy.on_data(data) if hasattr(strategy, "on_data") else data
    if df is None or len(df) == 0:
        raise ValueError("Strategy returned empty DataFrame")

    # Ensure signal column exists
    if "signal" not in df.columns:
        logger.warning("Strategy did not add 'signal' column. Defaulting to 0 (no trades).")
        df["signal"] = 0

    # Run simulation
    equity = float(initial_capital)
    balance = float(initial_capital)
    peak = float(initial_capital)

    trades = []
    equity_curve = []
    in_position = False
    entry_price = 0.0
    entry_idx = 0
    position_side = 0  # 1 = long, -1 = short
    position_volume = lot_size
    high_equity = float(initial_capital)

    max_dd_pct = 0.0
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    wins = 0
    losses = 0
    total_bars = len(df)
    ftmo_passed = None

    # Additional tracking
    lowest_equity = float(initial_capital)
    bankrupt = False
    total_pips = 0.0
    gross_pips = 0.0
    pips_won = 0.0
    pips_lost = 0.0
    win_pips_list = []
    loss_pips_list = []
    pnl_list = []
    current_streak = 0        # positive = wins, negative = losses
    max_consec_wins = 0
    max_consec_losses = 0
    trade_days = set()

    # FTMO rules
    ftmo_max_dd = initial_capital * 0.10  # 10% drawdown limit
    ftmo_profit_target = initial_capital * 0.10  # 10% profit target
    ftmo_min_trading_days = 10

    # FTMO Phase 2 rules
    ftmo2_max_dd = initial_capital * 0.05    # 5% drawdown
    ftmo2_profit_target = initial_capital * 0.05  # 5% profit target

    for i in range(total_bars):
        row = df.iloc[i]
        current_price = row["close"]

        # Margin-call: force-close if equity drops to 0 or below during a position
        if in_position and not bankrupt:
            if position_side == 1:
                unrealized_check = (current_price - entry_price) * position_volume * contract_size
            else:
                unrealized_check = (entry_price - current_price) * position_volume * contract_size
            if balance + unrealized_check <= 0:
                exit_signal = True
                exit_reason = "margin_call"
                bankrupt = True
                # equity after liquidation at current price
                current_equity = 0.0
                equity_curve.append({
                    "time": row["date"],
                    "equity": 0.0,
                })
                # Force close position logic inline
                if position_side == 1:
                    pnl_pips = (current_price - entry_price) / pip_value
                else:
                    pnl_pips = (entry_price - current_price) / pip_value
                gross_pnl = pnl_pips * pip_value * position_volume * contract_size
                commission_cost = position_volume * commission_per_lot * 2
                net_pnl = gross_pnl - commission_cost
                balance = 0.0
                total_pips += pnl_pips
                pnl_list.append(net_pnl)
                if net_pnl > 0:
                    wins += 1
                    total_gross_profit += net_pnl
                else:
                    losses += 1
                    total_gross_loss += abs(net_pnl)
                trades.append({
                    "entry_time": str(df.iloc[entry_idx]["date"]),
                    "exit_time": str(row["date"]),
                    "side": "BUY" if position_side == 1 else "SELL",
                    "entry_price": round(entry_price, 5),
                    "exit_price": round(current_price, 5),
                    "pnl": round(net_pnl, 2),
                    "pnl_pips": round(pnl_pips, 2),
                    "pnl_pct": round((net_pnl / initial_capital) * 100, 4),
                    "exit_reason": exit_reason,
                })
                in_position = False
                position_side = 0
                continue  # Skip to next bar

        # Record equity
        if in_position:
            if position_side == 1:
                unrealized = (current_price - entry_price) * position_volume * contract_size
            else:
                unrealized = (entry_price - current_price) * position_volume * contract_size
            current_equity = balance + unrealized
        else:
            current_equity = balance

        # Track lowest equity for FTMO drawdown
        if current_equity < lowest_equity:
            lowest_equity = current_equity

        equity_curve.append({
            "time": row["date"],
            "equity": round(current_equity, 2),
        })

        if current_equity > high_equity:
            high_equity = current_equity

        dd_pct = (high_equity - current_equity) / high_equity * 100 if high_equity > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = min(dd_pct, 100.0)  # Cap at 100%

        # Check position exit
        if in_position:
            exit_signal = False
            exit_reason = "signal"

            # Check if signal reversed (skip if already margin-called)
            if not bankrupt and i > entry_idx:
                prev_signal = df.iloc[i - 1]["signal"]
                if position_side == 1 and prev_signal <= 0 and row["signal"] < 0:
                    exit_signal = True
                elif position_side == -1 and prev_signal >= 0 and row["signal"] > 0:
                    exit_signal = True

            # Check stop loss / take profit (skip if already margin-called)
            if not bankrupt and position_side == 1:
                loss_pips = (entry_price - row["low"]) / pip_value
                profit_pips = (row["high"] - entry_price) / pip_value
                if loss_pips > 200:
                    exit_signal = True
                    exit_reason = "stop_loss"
                    current_price = entry_price - 200 * pip_value
                elif profit_pips > 400:
                    exit_signal = True
                    exit_reason = "take_profit"
                    current_price = entry_price + 400 * pip_value
            elif not bankrupt:
                loss_pips = (row["high"] - entry_price) / pip_value
                profit_pips = (entry_price - row["low"]) / pip_value
                if loss_pips > 200:
                    exit_signal = True
                    exit_reason = "stop_loss"
                    current_price = entry_price + 200 * pip_value
                elif profit_pips > 400:
                    exit_signal = True
                    exit_reason = "take_profit"
                    current_price = entry_price - 400 * pip_value

            if exit_signal or i == total_bars - 1:
                # Calculate PnL for the position
                if position_side == 1:
                    pnl_pips = (current_price - entry_price) / pip_value
                else:
                    pnl_pips = (entry_price - current_price) / pip_value

                gross_pnl = pnl_pips * pip_value * position_volume * contract_size
                slippage_cost = slippage_pips * pip_value * position_volume * contract_size  # applied on both entry + exit
                commission_cost = position_volume * commission_per_lot * 2  # round turn
                net_pnl = gross_pnl - commission_cost - slippage_cost

                balance += net_pnl

                # Bankruptcy protection: don't let balance go below 0
                if balance < 0:
                    balance = 0.0
                    bankrupt = True

                peak = max(peak, balance)
                total_pips += pnl_pips
                pnl_list.append(net_pnl)

                # Track streaks
                if net_pnl > 0:
                    wins += 1
                    total_gross_profit += net_pnl
                    win_pips_list.append(pnl_pips)
                    pips_won += pnl_pips
                    if current_streak >= 0:
                        current_streak += 1
                    else:
                        current_streak = 1
                    max_consec_wins = max(max_consec_wins, current_streak)
                else:
                    losses += 1
                    total_gross_loss += abs(net_pnl)
                    loss_pips_list.append(pnl_pips)
                    pips_lost += abs(pnl_pips)
                    if current_streak <= 0:
                        current_streak -= 1
                    else:
                        current_streak = -1
                    max_consec_losses = max(max_consec_losses, abs(current_streak))

                # Track trading days
                trade_date = str(df.iloc[entry_idx]["date"])[:10]
                trade_days.add(trade_date)

                trades.append({
                    "entry_time": str(df.iloc[entry_idx]["date"]),
                    "exit_time": str(row["date"]),
                    "side": "BUY" if position_side == 1 else "SELL",
                    "entry_price": round(entry_price, 5),
                    "exit_price": round(current_price, 5),
                    "pnl": round(net_pnl, 2),
                    "pnl_pips": round(pnl_pips, 2),
                    "pnl_pct": round((net_pnl / initial_capital) * 100, 4),
                    "exit_reason": exit_reason,
                })

                in_position = False
                position_side = 0
                logger.debug("Trade closed: %s PnL=%.2f (%s)", exit_reason, net_pnl, exit_reason)

        # Check position entry (skip if bankrupt)
        if not in_position and i < total_bars - 1 and not bankrupt:
            signal = row["signal"]
            if signal > 0:
                # Long entry
                in_position = True
                position_side = 1
                entry_price = row["open"] if row["open"] > 0 else current_price
                entry_idx = i
                # Add spread cost
                entry_price += spread_pips * pip_value
            elif signal < 0:
                # Short entry
                in_position = True
                position_side = -1
                entry_price = row["open"] if row["open"] > 0 else current_price
                entry_idx = i
                entry_price -= spread_pips * pip_value

    final_equity = balance

    # ==============================
    # Compute base metrics
    # ==============================
    total_trades = len(trades)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    loss_rate = (losses / total_trades * 100) if total_trades > 0 else 0
    total_return = ((final_equity - initial_capital) / initial_capital) * 100
    profit_factor = total_gross_profit / total_gross_loss if total_gross_loss > 0 else (
        total_gross_profit if total_gross_profit > 0 else 0
    )

    # Sharpe ratio (simplified: based on trade returns)
    if total_trades > 1:
        trade_returns = [t["pnl_pct"] for t in trades]
        avg_return = np.mean(trade_returns)
        std_return = np.std(trade_returns)
        sharpe = (avg_return / (std_return + 1e-10)) * np.sqrt(252) if std_return > 0 else 0
    else:
        sharpe = 0

    # ==============================
    # Enhanced metrics
    # ==============================

    # Best / worst trade (already existed)
    best_trade = max([t["pnl"] for t in trades]) if trades else 0
    worst_trade = min([t["pnl"] for t in trades]) if trades else 0
    avg_profit = float(np.mean([t["pnl"] for t in trades])) if trades else 0

    # --- Average win / loss ---
    avg_win = float(np.mean([p for p in pnl_list if p > 0])) if wins > 0 else 0
    avg_loss = float(np.mean([abs(p) for p in pnl_list if p < 0])) if losses > 0 else 0

    # --- Risk:Reward ratio ---
    rr_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    # --- Expectancy (average $ per trade) ---
    expectancy = round(avg_profit, 2)

    # --- Expectancy ratio (expectancy / avg_loss) ---
    expectancy_ratio = round(avg_profit / avg_loss, 2) if avg_loss > 0 else 0

    # --- Pip stats ---
    avg_pips_per_trade = round(total_pips / total_trades, 2) if total_trades > 0 else 0
    avg_win_pips = round(float(np.mean(win_pips_list)), 2) if win_pips_list else 0
    avg_loss_pips = round(float(np.mean([abs(p) for p in loss_pips_list])), 2) if loss_pips_list else 0

    # --- Calmar ratio (return / max drawdown) ---
    calmar = round(total_return / max_dd_pct, 2) if max_dd_pct > 0 else 0

    # ==============================
    # FTMO checks (Phase 1 & Phase 2)
    # ==============================
    ftmo_result = None
    ftmo2_result = None
    if ftmo_mode:
        ftmo_dd_pct = max(0, (high_equity - lowest_equity)) / initial_capital * 100 if initial_capital > 0 else 0
        total_profit_pct = total_return

        active_trading_days = len(trade_days)

        # Phase 1: 10% profit, 10% DD, 10 trading days
        phase1_passed = (
            active_trading_days >= ftmo_min_trading_days
            and ftmo_dd_pct <= 10.0
            and total_profit_pct >= 10.0
        )
        ftmo_result = {
            "passed": phase1_passed,
            "phase": "Phase 1",
            "max_drawdown_pct": round(ftmo_dd_pct, 2),
            "profit_pct": round(total_profit_pct, 2),
            "trading_days": active_trading_days,
            "min_days_required": ftmo_min_trading_days,
            "profit_target_met": total_profit_pct >= 10.0,
            "drawdown_ok": ftmo_dd_pct <= 10.0,
            "min_days_met": active_trading_days >= ftmo_min_trading_days,
        }

        # Phase 2: 5% profit, 5% DD, 10 trading days
        phase2_passed = (
            active_trading_days >= ftmo_min_trading_days
            and ftmo_dd_pct <= 5.0
            and total_profit_pct >= 5.0
        )
        ftmo2_result = {
            "passed": phase2_passed,
            "phase": "Phase 2",
            "max_drawdown_pct": round(ftmo_dd_pct, 2),
            "profit_pct": round(total_profit_pct, 2),
            "trading_days": active_trading_days,
            "min_days_required": ftmo_min_trading_days,
            "profit_target_met": total_profit_pct >= 5.0,
            "drawdown_ok": ftmo_dd_pct <= 5.0,
            "min_days_met": active_trading_days >= ftmo_min_trading_days,
        }

    # ==============================
    # Worth deploying? — Composite scoring
    # ==============================
    deploy_score = 0
    deploy_flags = []
    if total_trades >= 20:
        deploy_score += 2
        deploy_flags.append("✓ Sufficient sample (≥20 trades)")
    else:
        deploy_flags.append("✗ Low sample (<20 trades)")

    if sharpe >= 1.0:
        deploy_score += 2
        deploy_flags.append("✓ Sharpe ≥ 1.0")
    else:
        deploy_flags.append(f"✗ Sharpe below 1.0 ({sharpe:.2f})")

    if profit_factor >= 1.5:
        deploy_score += 2
        deploy_flags.append("✓ Profit factor ≥ 1.5")
    elif profit_factor >= 1.2:
        deploy_score += 1
        deploy_flags.append("~ PF 1.2-1.5 (acceptable)")
    else:
        deploy_flags.append(f"✗ Profit factor low ({profit_factor:.2f})")

    if win_rate >= 40:
        deploy_score += 1.5
        deploy_flags.append("✓ Win rate ≥ 40%")
    elif win_rate >= 30:
        deploy_score += 0.5
        deploy_flags.append("~ Win rate 30-40%")
    else:
        deploy_flags.append(f"✗ Win rate low ({win_rate:.1f}%)")

    if max_dd_pct <= 15:
        deploy_score += 1.5
        deploy_flags.append("✓ Max DD ≤ 15%")
    elif max_dd_pct <= 25:
        deploy_score += 0.5
        deploy_flags.append(f"~ Max DD {max_dd_pct:.1f}% (manageable)")
    else:
        deploy_flags.append(f"✗ Max DD too high ({max_dd_pct:.1f}%)")

    if expectancy > 0:
        deploy_score += 1
        deploy_flags.append("✓ Positive expectancy")
    else:
        deploy_flags.append("✗ Negative expectancy")

    if rr_ratio >= 1.5:
        deploy_score += 1
        deploy_flags.append(f"✓ R:R ≥ 1.5 ({rr_ratio})")
    elif rr_ratio >= 1.0:
        deploy_score += 0.5
        deploy_flags.append(f"~ R:R 1.0-1.5 ({rr_ratio})")
    else:
        deploy_flags.append(f"✗ R:R < 1.0 ({rr_ratio})")

    # Deploy recommendation
    if deploy_score >= 8:
        deploy_verdict = "STRONG YES — Deploy to live"
        deploy_confidence = "high"
    elif deploy_score >= 5:
        deploy_verdict = "CAUTIOUS YES — Paper trade first, monitor closely"
        deploy_confidence = "medium"
    elif deploy_score >= 3:
        deploy_verdict = "UNCERTAIN — Optimise further or use as filter only"
        deploy_confidence = "low"
    else:
        deploy_verdict = "NO — Do not deploy, revisit strategy logic"
        deploy_confidence = "none"

    # ==============================
    # Assemble metrics dict
    # ==============================
    metrics = {
        # Core
        "total_return_pct": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": calmar,
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "loss_rate_pct": round(loss_rate, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "profit_factor": round(profit_factor, 2),

        # P&L detail
        "gross_profit": round(total_gross_profit, 2),
        "gross_loss": round(total_gross_loss, 2),
        "net_profit": round(total_gross_profit - total_gross_loss, 2),
        "final_balance": round(final_equity, 2),

        # Enhanced
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "avg_profit_per_trade": round(avg_profit, 2),
        "risk_reward_ratio": rr_ratio,
        "expectancy": expectancy,
        "expectancy_ratio": expectancy_ratio,

        # Streaks
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,

        # Pips
        "total_pips": round(total_pips, 2),
        "avg_pips_per_trade": avg_pips_per_trade,
        "avg_win_pips": avg_win_pips,
        "avg_loss_pips": avg_loss_pips,
        "pip_ratio": round(avg_win_pips / avg_loss_pips, 2) if avg_loss_pips > 0 else 0,

        # Trading days
        "active_trading_days": len(trade_days),

        # Deploy recommendation
        "deploy_score": round(deploy_score, 1),
        "deploy_verdict": deploy_verdict,
        "deploy_confidence": deploy_confidence,
        "deploy_details": deploy_flags,
    }

    # ==============================
    # Convert numpy types to native Python for JSON serialization
    # ==============================

    eq_list = [{"time": str(e["time"]), "equity": e["equity"]} for e in equity_curve]

    def _to_native(obj):
        """Recursively convert numpy types to native Python."""
        if isinstance(obj, dict):
            return {k: _to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_to_native(item) for item in obj]
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return _to_native(obj.tolist())
        return obj

    metrics = _to_native(metrics)
    trades = _to_native(trades)
    eq_list = _to_native(eq_list)
    ftmo_result = _to_native(ftmo_result) if ftmo_result else None
    ftmo2_result = _to_native(ftmo2_result) if ftmo2_result else None

    logger.info(
        "Backtest complete: %d trades, return=%.2f%%, Sharpe=%.2f, DD=%.2f%%, R:R=%.2f, Deploy=%s",
        total_trades, total_return, sharpe, max_dd_pct, rr_ratio, deploy_verdict,
    )

    return {
        "metrics": metrics,
        "equity_curve": eq_list,
        "trades": trades,
        "ftmo": ftmo_result,
        "ftmo_phase2": ftmo2_result,
        "final_equity": float(round(final_equity, 2)),
    }
