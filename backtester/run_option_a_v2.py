#!/usr/bin/env python3
"""
OPTION A v2 — Master Historical Backtest (Fixed)
All 5 strategies with corrected strategy classes and data.
"""
import sys, json, logging, os
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtester.engine import run as run_backtest
from backtester.loader import (
    MACDStrategy, GoldPhoenixStrategy,
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "custom_strategies"))
from vwap_mean_reversion import VWAPMeanReversionStrategy
from atr_expansion import ATRExpansionStrategy
from bollinger_squeeze import BollingerSqueezeStrategy

logging.basicConfig(level=logging.WARNING, format="%(levelname)s|%(message)s")

TF_MAP = {"H1": mt5.TIMEFRAME_H1, "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15}

def fetch(symbol, timeframe, bars):
    tf = TF_MAP.get(timeframe, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def bt(name, strategy, data, params, capital=10000, lot=0.1, spread=1.0, pip_val=0.0001, contract=100000):
    if data is None or len(data) < 100:
        return {"strategy": name, "error": "No data", "trades": 0}
    result = run_backtest(
        strategy_class=strategy, data=data,
        initial_capital=capital, spread_pips=spread,
        pip_value=pip_val, contract_size=contract,
        risk_per_trade=params.pop("risk", 0.005),
        strategy_params=params, ftmo_mode=False, lot_size=lot,
    )
    tlist = result.get("trades", [])
    n = len(tlist)
    wins = sum(1 for t in tlist if t.get("pnl", 0) > 0)
    losses = sum(1 for t in tlist if t.get("pnl", 0) < 0)
    wr = wins / n * 100 if n else 0
    gw = sum(t["pnl"] for t in tlist if t.get("pnl", 0) > 0) or 0
    gl = abs(sum(t["pnl"] for t in tlist if t.get("pnl", 0) < 0)) or 0
    pf = gw / gl if gl else 0
    net = sum(t["pnl"] for t in tlist)
    mdd = result.get("metrics", {}).get("max_drawdown_pct", 0)
    aw = gw / wins if wins else 0
    al = gl / losses if losses else 0
    exp = net / n if n else 0
    return {"name": name, "trades": n, "wins": wins, "losses": losses,
            "wr": round(wr, 1), "pf": round(pf, 2), "net": round(net, 2),
            "mdd": round(mdd, 2), "aw": round(aw, 2), "al": round(al, 2),
            "exp": round(exp, 2)}


def main():
    if not mt5.initialize():
        print("FATAL: MT5 init failed")
        return
    results = []

    # ── 1. Propfirm Pass (VWAP Mean Reversion) ── EURUSD H1 (approximation) ──
    print("\n[1/5] Propfirm Pass VWAP (EURUSD H1, session-filtered)...")
    d = fetch("EURUSD", "H1", 2000)
    if d is not None:
        r = bt("1. Propfirm Pass (VWAP H1)", VWAPMeanReversionStrategy, d,
               {"deviation_pips": 1, "sl_pips": 12, "tp_pips": 24,
                "session_start": 13, "session_end": 15,
                "wick_ratio": 1.5, "body_max_pct": 0.40, "momentum_skip": 0.60,
                "risk": 0.01, "pip_value": 0.0001},
               capital=100000, lot=1.0, spread=1.0, pip_val=0.0001, contract=100000)
        # Also try with smaller deviation since H1 has wider range
        results.append(r)
        print(f"   → {r['trades']} trades, WR={r['wr']}%, PF={r['pf']}, PnL=${r['net']}")

    # ── 2. Gold Phoenix ── XAUUSD H1 ──
    print("\n[2/5] Gold Phoenix (XAUUSD H1)...")
    d = fetch("XAUUSD", "H1", 2000)
    if d is not None:
        r = bt("2. Gold Phoenix", GoldPhoenixStrategy, d,
               {"adx_threshold": 26.0, "asian_range_bars": 6, "risk": 0.005},
               capital=10000, lot=0.1, spread=1.0, pip_val=0.01, contract=100)
        results.append(r)
        print(f"   → {r['trades']} trades, WR={r['wr']}%, PF={r['pf']}, PnL=${r['net']}")

    # ── 3. Bot Park - MACD ── EURUSD H1 ──
    print("\n[3/5] Bot Park (MACD EURUSD H1)...")
    d = fetch("EURUSD", "H1", 2000)
    if d is not None:
        r = bt("3. Bot Park (MACD)", MACDStrategy, d,
               {"fast": 12, "slow": 26, "signal": 9, "risk": 0.005},
               capital=10000, lot=0.1, spread=1.0)
        results.append(r)
        print(f"   → {r['trades']} trades, WR={r['wr']}%, PF={r['pf']}, PnL=${r['net']}")

    # ── 4. Volatility Breakout (Bollinger Squeeze) ── XAUUSD M5 ──
    print("\n[4/5] Volatility Breakout (BollingerSqueeze XAUUSD M5)...")
    d = fetch("XAUUSD", "M5", 5000)
    if d is not None:
        r = bt("4. VolBreak (BollingerSqueeze)", BollingerSqueezeStrategy, d,
               {"bb_period": 20, "bb_std": 2.0, "squeeze_thresh": 0.85,
                "squeeze_count": 3, "expansion_thresh": 1.1,
                "sl_atr": 1.5, "tp_atr": 6.0, "atr_period": 14,
                "risk": 0.005},
               capital=10000, lot=0.1, spread=1.0, pip_val=0.01, contract=100)
        results.append(r)
        print(f"   → {r['trades']} trades, WR={r['wr']}%, PF={r['pf']}, PnL=${r['net']}")

    # ── 5. ATR Expansion Breakout ── EURUSD H1 ──
    print("\n[5/5] ATR Expansion (EURUSD H1)...")
    d = fetch("EURUSD", "H1", 2000)
    if d is not None:
        r = bt("5. ATR Expansion", ATRExpansionStrategy, d,
               {"fast_atr": 14, "slow_atr": 50, "expansion_thresh": 1.10,
                "contraction_thresh": 1.15, "sl_atr_mult": 1.5,
                "tp_atr_mult": 3.0, "max_trades": 3, "risk": 0.005},
               capital=10000, lot=0.1, spread=1.0)
        results.append(r)
        print(f"   → {r['trades']} trades, WR={r['wr']}%, PF={r['pf']}, PnL=${r['net']}")

    mt5.shutdown()

    # ── Results Table ──
    print("\n" + "=" * 120)
    h = f"{'STRATEGY':<38} {'TRADES':>7} {'WR%':>6} {'PF':>7} {'NET PnL':>10} {'MAX DD%':>8} {'AVG WIN':>9} {'AVG LOSS':>9} {'EXP/T':>8}"
    print(h)
    print("-" * 120)
    for r in results:
        if "error" in r:
            print(f"{r['name']:<38} ERROR: {r['error']}")
        else:
            print(f"{r['name']:<38} {r['trades']:>7} {r['wr']:>5.1f}% {r['pf']:>6.2f} "
                  f"${r['net']:>8.2f} {r['mdd']:>7.2f}% ${r['aw']:>7.2f} ${r['al']:>7.2f} ${r['exp']:>7.2f}")
    print("=" * 120)

    out = Path(__file__).resolve().parent / "option_a_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {out}")

if __name__ == "__main__":
    main()
