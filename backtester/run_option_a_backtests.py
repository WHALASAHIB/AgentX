#!/usr/bin/env python3
"""
OPTION A — Master Historical Backtest
All 5 strategies, recent MT5 data, full metrics.
"""
import sys, json, logging, os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtester.engine import run as run_backtest
from backtester.loader import (
    SMAStrategy, MACDStrategy, BollingerBandsStrategy,
    VolatilityBreakoutStrategy, GoldPhoenixStrategy, PineScriptStrategy,
)

# Custom strategies
sys.path.insert(0, str(Path(__file__).resolve().parent / "custom_strategies"))
from vwap_mean_reversion import VWAPMeanReversionStrategy
from atr_expansion import ATRExpansionStrategy

logging.basicConfig(level=logging.WARNING, format="%(levelname)s|%(message)s")

MT5_TIMEFRAMES = {
    "H1": mt5.TIMEFRAME_H1,
    "M1": mt5.TIMEFRAME_M1,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
}

def fetch_data(symbol, timeframe, bars=2000):
    """Fetch OHLC data from MT5."""
    tf = MT5_TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    cols = {"open", "high", "low", "close", "tick_volume", "time"}
    for c in cols:
        if c not in df.columns:
            return None
    return df


def run_strategy(name, strategy_class, data, params, capital=10000, lot=0.1, spread=1.0, pip_val=0.0001, contract=100000):
    """Run one backtest and return metrics."""
    if data is None or len(data) < 100:
        return {"strategy": name, "error": "Insufficient data", "trades": 0}

    result = run_backtest(
        strategy_class=strategy_class,
        data=data,
        initial_capital=capital,
        spread_pips=spread,
        pip_value=pip_val,
        contract_size=contract,
        risk_per_trade=params.get("risk", 0.005),
        strategy_params=params,
        ftmo_mode=False,
        lot_size=lot,
    )

    metrics = result.get("metrics", {})
    trades_list = result.get("trades", [])
    trades = len(trades_list)

    wins = sum(1 for t in trades_list if t.get("pnl", 0) > 0)
    losses = sum(1 for t in trades_list if t.get("pnl", 0) < 0)
    wr = (wins / trades * 100) if trades > 0 else 0
    gross_win = sum(t["pnl"] for t in trades_list if t.get("pnl", 0) > 0) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in trades_list if t.get("pnl", 0) < 0)) if losses else 0
    pf = gross_win / gross_loss if gross_loss > 0 else (gross_win if gross_win > 0 else 0)
    net_pnl = sum(t["pnl"] for t in trades_list)
    max_dd = metrics.get("max_drawdown_pct", 0)
    avg_win = gross_win / wins if wins else 0
    avg_loss = gross_loss / losses if losses else 0
    expectancy = net_pnl / trades if trades else 0

    return {
        "strategy": name,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net_pnl": round(net_pnl, 2),
        "max_dd_pct": round(max_dd, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
    }


def main():
    if not mt5.initialize():
        print("FATAL: MT5 init failed")
        return

    results = []

    # ── 1. Propfirm Pass (VWAP Mean Reversion) ── EURUSD M1 ──
    print("\n[1/5] Propfirm Pass (VWAP Mean Reversion)...")
    data_vwap = fetch_data("EURUSD", "M1", 5000)
    if data_vwap is not None:
        r = run_strategy(
            "1. Propfirm Pass (VWAP)",
            VWAPMeanReversionStrategy, data_vwap,
            {"deviation_pips": 8, "sl_pips": 12, "tp_pips": 24,
             "session_start": 13, "session_end": 15,
             "wick_ratio": 1.5, "body_max_pct": 0.40, "momentum_skip": 0.60,
             "risk": 0.01, "pip_value": 0.0001},
            capital=100000, lot=1.0, spread=1.0,
            pip_val=0.0001, contract=100000)
        results.append(r)
        print(f"   ✓ {r['trades']} trades, WR={r['win_rate']}%, PF={r['profit_factor']}, PnL=${r['net_pnl']}")

    # ── 2. Gold Phoenix ── XAUUSD H1 ──
    print("\n[2/5] Gold Phoenix (XAUUSD)...")
    data_gp = fetch_data("XAUUSD", "H1", 2000)
    if data_gp is not None:
        r = run_strategy(
            "2. Gold Phoenix",
            GoldPhoenixStrategy, data_gp,
            {"adx_threshold": 26.0, "asian_range_bars": 6, "risk": 0.005},
            capital=10000, lot=0.1, spread=1.0,
            pip_val=0.01, contract=100)  # XAUUSD: pip=0.01, contract=100oz
        results.append(r)
        print(f"   ✓ {r['trades']} trades, WR={r['win_rate']}%, PF={r['profit_factor']}, PnL=${r['net_pnl']}")

    # ── 3. Bot Park - MACD (most common) ── EURUSD H1 ──
    print("\n[3/5] Bot Park - MACD (EURUSD H1)...")
    data_macd = fetch_data("EURUSD", "H1", 2000)
    if data_macd is not None:
        r = run_strategy(
            "3. Bot Park (MACD EURUSD)",
            MACDStrategy, data_macd,
            {"fast": 12, "slow": 26, "signal": 9, "risk": 0.005},
            capital=10000, lot=0.1, spread=1.0)
        results.append(r)
        print(f"   ✓ {r['trades']} trades, WR={r['win_rate']}%, PF={r['profit_factor']}, PnL=${r['net_pnl']}")

    # ── 4. Volatility Breakout ── XAUUSD H1 ──
    print("\n[4/5] Volatility Breakout (XAUUSD H1)...")
    data_vb = fetch_data("XAUUSD", "H1", 2000)
    if data_vb is not None:
        r = run_strategy(
            "4. Volatility Breakout",
            VolatilityBreakoutStrategy, data_vb,
            {"lookback": 14, "mult": 2.0, "risk": 0.005},
            capital=10000, lot=0.1, spread=1.0,
            pip_val=0.01, contract=100)
        results.append(r)
        print(f"   ✓ {r['trades']} trades, WR={r['win_rate']}%, PF={r['profit_factor']}, PnL=${r['net_pnl']}")

    # ── 5. ATR Expansion Breakout ── EURUSD H1 ──
    print("\n[5/5] ATR Expansion (EURUSD H1)...")
    data_atr = fetch_data("EURUSD", "H1", 2000)
    if data_atr is not None:
        r = run_strategy(
            "5. ATR Expansion",
            ATRExpansionStrategy, data_atr,
            {"fast_atr": 14, "slow_atr": 50, "expansion_thresh": 1.10,
             "contraction_thresh": 1.15, "sl_atr_mult": 1.5,
             "tp_atr_mult": 3.0, "max_trades": 3, "risk": 0.005},
            capital=10000, lot=0.1, spread=1.0)
        results.append(r)
        print(f"   ✓ {r['trades']} trades, WR={r['win_rate']}%, PF={r['profit_factor']}, PnL=${r['net_pnl']}")

    mt5.shutdown()

    # ── Results Table ──
    print("\n" + "=" * 110)
    print(f"{'STRATEGY':<38} {'TRADES':>7} {'WR%':>6} {'PF':>6} {'NET PnL':>10} {'MAX DD%':>8} {'EXP/T':>8}")
    print("-" * 110)
    for r in results:
        if "error" in r:
            print(f"{r['strategy']:<38} {'ERROR':>7} {r['error']}")
        else:
            print(f"{r['strategy']:<38} {r['trades']:>7} {r['win_rate']:>5.1f}% {r['profit_factor']:>5.2f} "
                  f"${r['net_pnl']:>8.2f} {r['max_dd_pct']:>7.2f}% ${r['expectancy']:>7.2f}")
    print("=" * 110)

    # Save to JSON for later reference
    out = Path(__file__).resolve().parent / "option_a_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
