#!/usr/bin/env python3
"""
Volatility Breakout Bot — XAUUSD
==================================
Bollinger Squeeze / Volatility Contraction pattern for Gold.
Waits for low-volatility contraction, then trades the breakout direction.

Usage:  python volatility_breakout_bot.py --symbol XAUUSD --strategy volatilitybreakout
"""

import argparse
import json
import math
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed")
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────
CHECK_INTERVAL = 10
MAGIC = 200500
BACKEND_URL = "http://localhost:8006"


def _log_decision(agent_name: str, action: str, detail: str, outcome: str = "success"):
    """Send decision log to backend."""
    try:
        payload = json.dumps({
            "agent_id": agent_name,
            "agent_name": agent_name,
            "action": action,
            "detail": detail,
            "outcome": outcome,
        }).encode()
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/decisions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


import urllib.request
import urllib.error


def _safe_log(agent_name: str, action: str, detail: str, outcome: str = "success"):
    """Log a decision without blocking."""
    try:
        payload = json.dumps({
            "agent_id": agent_name,
            "agent_name": agent_name,
            "action": action,
            "detail": detail,
            "outcome": outcome,
        }).encode()
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/decisions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def _calculate_lot(symbol: str, risk_pct: float = 0.005,
                   sl_distance: Optional[float] = None) -> float:
    account = mt5.account_info()
    if account is None:
        return 0.01
    balance = account.balance
    risk_amount = balance * risk_pct
    info = mt5.symbol_info(symbol)
    if sl_distance and info and sl_distance > 0:
        point_value = info.trade_tick_value  # value per tick
        lot = risk_amount / (sl_distance * point_value)
    else:
        lot = risk_amount / 5000
    if info:
        lot = max(info.volume_min, min(lot, info.volume_max))
        lot = round(lot / info.volume_step) * info.volume_step
    return max(0.01, lot)


def _calculate_atr(symbol: str, period: int = 14) -> float:
    """Fetch H1 bars and calculate ATR over `period` bars."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
    if rates is None or len(rates) < period:
        # Fallback defaults: 500 points for XAUUSD, 50 pips for forex
        info = mt5.symbol_info(symbol)
        if info:
            if "XAU" in symbol or "GOLD" in symbol:
                return 5.0 * info.point * 100  # 500 points
            else:
                return 0.0050 * info.point * 10000  # 50 pips
        return 0.0
    highs = [r[1] for r in rates[-period:]]
    lows = [r[2] for r in rates[-period:]]
    tr_sum = sum(highs[i] - lows[i] for i in range(period))
    return tr_sum / period


def _calculate_sl_tp(symbol: str, order_type: int,
                     entry_price: float, atr: float):
    """
    Compute SL and TP prices.
    SL = 1.5 × ATR away from entry (opposite direction).
    TP = 3.0 × ATR away (profit direction).
    Returns (sl_price, tp_price).
    """
    point = mt5.symbol_info(symbol).point
    sl_points = int(round(1.5 * atr / point))
    tp_points = int(round(3.0 * atr / point))
    if order_type == mt5.ORDER_TYPE_BUY:
        sl_price = entry_price - sl_points * point
        tp_price = entry_price + tp_points * point
    else:
        sl_price = entry_price + sl_points * point
        tp_price = entry_price - tp_points * point
    return sl_price, tp_price


def _calculate_bollinger(data: list[float], period: int = 20, std_mult: float = 2.0):
    """Returns (middle, upper, lower, bandwidth) where bandwidth = (upper-lower)/middle."""
    if len(data) < period:
        return None, None, None, None
    recent = data[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    bandwidth = (upper - lower) / middle if middle != 0 else 0
    return middle, upper, lower, bandwidth


def main():
    parser = argparse.ArgumentParser(description="Volatility Breakout Bot")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--strategy", default="volatilitybreakout")
    parser.add_argument("--risk", type=float, default=0.005)
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    symbol = args.symbol.upper()
    risk_pct = args.risk
    interval = args.interval
    bot_name = f"VolatilityBreakout_{symbol}"

    print(f"[{bot_name}] Starting — symbol={symbol} risk={risk_pct*100:.1f}% interval={interval}s")

    if not mt5.initialize():
        print(f"[{bot_name}] MT5 init FAILED: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)

    account = mt5.account_info()
    if account is None:
        print(f"[{bot_name}] No account connected")
        mt5.shutdown()
        sys.exit(1)

    print(f"[{bot_name}] Account: {account.login} @ {account.server} | Balance: {account.balance:.2f}")

    if not mt5.symbol_select(symbol, True):
        print(f"[{bot_name}] Failed to select {symbol}")
        mt5.shutdown()
        sys.exit(1)

    squeeze_count = 0
    last_bandwidth = 0

    while True:
        try:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 30)
            if rates is None or len(rates) < 20:
                time.sleep(CHECK_INTERVAL)
                continue

            prices = [r[4] for r in rates]  # close prices
            _, upper, lower, bandwidth = _calculate_bollinger(prices)

            if bandwidth is None:
                time.sleep(CHECK_INTERVAL)
                continue

            # Detect squeeze: bandwidth shrinking
            if last_bandwidth > 0 and bandwidth < last_bandwidth * 0.85:
                squeeze_count += 1
            else:
                squeeze_count = 0

            last_bandwidth = bandwidth

            # Check breakout after squeeze (bandwidth expanding again)
            if squeeze_count >= 3 and bandwidth > last_bandwidth * 1.1:
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    time.sleep(CHECK_INTERVAL)
                    continue

                # Check existing positions
                positions = mt5.positions_get(symbol=symbol)
                has_position = positions and any(p.magic == MAGIC for p in positions)

                if not has_position:
                    # Price broke above upper band → BUY, below lower → SELL
                    if tick.ask > upper:
                        atr = _calculate_atr(symbol)
                        sl_price, tp_price = _calculate_sl_tp(
                            symbol, mt5.ORDER_TYPE_BUY, tick.ask, atr
                        )
                        sl_distance = tick.ask - sl_price
                        lot = _calculate_lot(symbol, risk_pct,
                                             sl_distance=sl_distance)
                        req = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": symbol,
                            "volume": lot,
                            "type": mt5.ORDER_TYPE_BUY,
                            "price": tick.ask,
                            "sl": sl_price, "tp": tp_price,
                            "deviation": 20,
                            "magic": MAGIC,
                            "comment": bot_name,
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        result = mt5.order_send(req)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"[{bot_name}] BUY breakout {lot} {symbol} @ {tick.ask:.2f} sl={sl_price:.2f} tp={tp_price:.2f} ticket={result.order}")
                        squeeze_count = 0

                    elif tick.bid < lower:
                        atr = _calculate_atr(symbol)
                        sl_price, tp_price = _calculate_sl_tp(
                            symbol, mt5.ORDER_TYPE_SELL, tick.bid, atr
                        )
                        sl_distance = sl_price - tick.bid
                        lot = _calculate_lot(symbol, risk_pct,
                                             sl_distance=sl_distance)
                        req = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": symbol,
                            "volume": lot,
                            "type": mt5.ORDER_TYPE_SELL,
                            "price": tick.bid,
                            "sl": sl_price, "tp": tp_price,
                            "deviation": 20,
                            "magic": MAGIC,
                            "comment": bot_name,
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        result = mt5.order_send(req)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"[{bot_name}] SELL breakout {lot} {symbol} @ {tick.bid:.2f} sl={sl_price:.2f} tp={tp_price:.2f} ticket={result.order}")
                        squeeze_count = 0

            time.sleep(interval)

        except KeyboardInterrupt:
            print(f"[{bot_name}] Shutting down")
            break
        except Exception as e:
            print(f"[{bot_name}] Error: {e}")
            traceback.print_exc()
            time.sleep(CHECK_INTERVAL)

    mt5.shutdown()


if __name__ == "__main__":
    main()
