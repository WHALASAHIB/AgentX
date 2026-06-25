#!/usr/bin/env python3
"""
Multi-Symbol Trading Bot — AGENTX Platform
===========================================
Runs a continuous trading loop for a given symbol and strategy.
Connects directly to MetaTrader 5 via the installed terminal.

Usage:  python multi_symbol_bot.py --symbol EURUSD --strategy bollinger

Strategies: bollinger, macd, sma
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
    print("ERROR: MetaTrader5 package not installed. Install with: pip install MetaTrader5")
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────
CHECK_INTERVAL = 10          # seconds between checks
DAILY_MAX_TRADES = 999       # no practical limit per user approval
MAGIC_BASE = 200000          # base magic number offset per strategy

STRATEGY_MAGIC = {
    "bollinger": 100,
    "macd": 200,
    "sma": 300,
    "rsi": 400,
    "volatilitybreakout": 500,
}

# ── Bridge Logger ──────────────────────────────────────────────────────
import urllib.request
import urllib.error

BACKEND_URL = "http://localhost:8006"


def _log_decision(agent_name: str, action: str, detail: str, outcome: str = "success"):
    """Send decision log entry to backend."""
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
        pass  # Don't let logging failure crash the bot


def _post_trade(trade_data: dict):
    """Report a completed trade to backend."""
    try:
        payload = json.dumps(trade_data).encode()
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/trades",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


# ── Strategy Helpers ──────────────────────────────────────────────────

def _get_sma(data: list[float], period: int) -> Optional[float]:
    """Simple Moving Average."""
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


def _bollinger_bands(data: list[float], period: int = 20, std_mult: float = 2.0):
    """Calculate Bollinger Bands. Returns (middle, upper, lower) or None."""
    if len(data) < period:
        return None, None, None
    recent = data[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    return middle, upper, lower


# ── Strategy Signal Functions ─────────────────────────────────────────

def bollinger_signal(price: float, data: list[float]) -> Optional[str]:
    """
    Bollinger Bands Mean Reversion.
    Returns 'buy', 'sell', or None.
    """
    middle, upper, lower = _bollinger_bands(data)
    if middle is None:
        return None
    if price <= lower:
        return "buy"   # price below lower band → oversold, go long
    elif price >= upper:
        return "sell"  # price above upper band → overbought, go short
    return None


def macd_signal(price: float, data: list[float]) -> Optional[str]:
    """
    MACD Crossover (12, 26, 9).
    Returns 'buy', 'sell', or None.
    """
    fast_period = 12
    slow_period = 26
    signal_period = 9

    if len(data) < slow_period + signal_period:
        return None

    # Calculate EMAs
    def ema(values: list[float], period: int) -> list[float]:
        result = []
        multiplier = 2.0 / (period + 1)
        # Start with SMA
        if len(values) < period:
            return result
        ema_val = sum(values[:period]) / period
        result.append(ema_val)
        for v in values[period:]:
            ema_val = (v - ema_val) * multiplier + ema_val
            result.append(ema_val)
        return result

    ema_fast = ema(data, fast_period)
    ema_slow = ema(data, slow_period)

    if len(ema_fast) < 2 or len(ema_slow) < 2:
        return None

    # MACD line = fast EMA - slow EMA
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(min(len(ema_fast), len(ema_slow)))]

    if len(macd_line) < signal_period:
        return None

    # Signal line = EMA of MACD line
    signal_line = ema(macd_line, signal_period)

    if len(signal_line) < 2:
        return None

    # Check for crossover
    curr_macd = macd_line[-1]
    prev_macd = macd_line[-2]
    curr_signal = signal_line[-1]
    prev_signal = signal_line[-2]

    if prev_macd <= prev_signal and curr_macd > curr_signal:
        return "buy"   # MACD crossed above signal → bullish
    elif prev_macd >= prev_signal and curr_macd < curr_signal:
        return "sell"  # MACD crossed below signal → bearish
    return None


def sma_signal(price: float, data: list[float]) -> Optional[str]:
    """
    SMA Crossover (fast=10, slow=30).
    Returns 'buy', 'sell', or None.
    """
    fast_period = 10
    slow_period = 30

    if len(data) < slow_period + 1:
        return None

    fast_curr = _get_sma(data, fast_period)
    slow_curr = _get_sma(data, slow_period)
    fast_prev = _get_sma(data[:-1], fast_period)
    slow_prev = _get_sma(data[:-1], slow_period)

    if None in (fast_curr, slow_curr, fast_prev, slow_prev):
        return None

    if fast_prev <= slow_prev and fast_curr > slow_curr:
        return "buy"
    elif fast_prev >= slow_prev and fast_curr < slow_curr:
        return "sell"
    return None


# Strategy registry
STRATEGIES = {
    "bollinger": bollinger_signal,
    "macd": macd_signal,
    "sma": sma_signal,
}


# ── MT5 Interaction ───────────────────────────────────────────────────

def _get_price_data(symbol: str, count: int = 50) -> Optional[list[float]]:
    """Fetch recent close prices for the symbol."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, count)
    if rates is None or len(rates) == 0:
        return None
    return [r[4] for r in rates]  # index 4 = close


def _get_current_price(symbol: str) -> Optional[tuple[float, float]]:
    """Get current bid/ask. Returns (bid, ask) or None."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return tick.bid, tick.ask


def _count_open_positions(symbol: str, magic: int) -> int:
    """Count open positions for this symbol + magic number."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return 0
    return sum(1 for p in positions if p.magic == magic)


def _calculate_atr(symbol: str, period: int = 14) -> float:
    """Calculate Average True Range from H1 price data.

    Returns ATR value, or a sensible default based on symbol type
    (50 pips for forex, 500 points for XAUUSD).
    """
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20)
    info = mt5.symbol_info(symbol)

    if rates is None or len(rates) < period:
        # Fallback default based on symbol type
        if info is None:
            return 0.005
        point = info.point if info.point else 0.0001
        if "XAU" in symbol.upper() or "GOLD" in symbol.upper():
            return 50.0 * point if point else 5.0
        return 50.0 * point if point else 0.005

    # ATR = average of (high - low) over 'period' bars
    tr_values = [rates[i][2] - rates[i][3] for i in range(min(period, len(rates)))]
    if not tr_values:
        return 0.005
    return sum(tr_values) / len(tr_values)


def _calculate_sl_tp(symbol: str, order_type: int, entry_price: float,
                     atr: float) -> tuple[float, float]:
    """Calculate stop-loss and take-profit prices based on ATR.

    SL = 1.5 x ATR away from entry (opposite direction)
    TP = 3.0 x ATR away from entry (profit direction, 1:2 RR ratio)
    Returns (sl_price, tp_price).
    """
    if order_type == mt5.ORDER_TYPE_BUY:
        sl_price = entry_price - (1.5 * atr)
        tp_price = entry_price + (3.0 * atr)
    else:  # SELL
        sl_price = entry_price + (1.5 * atr)
        tp_price = entry_price - (3.0 * atr)
    return sl_price, tp_price


def _open_trade(symbol: str, order_type: int, lot: float, magic: int,
                comment: str, deviation: int = 20,
                atr: Optional[float] = None) -> Optional[int]:
    """Open a market order. Returns ticket number or None.
    If atr is provided, calculates SL/TP automatically using _calculate_sl_tp.
    """
    price = mt5.symbol_info_tick(symbol)
    if price is None:
        return None

    entry_price = price.ask if order_type == mt5.ORDER_TYPE_BUY else price.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": entry_price,
        "sl": 0.0,
        "tp": 0.0,
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    # Calculate SL/TP using ATR if provided
    if atr is not None:
        sl_price, tp_price = _calculate_sl_tp(symbol, order_type, entry_price, atr)
        request["sl"] = round(sl_price, 5)
        request["tp"] = round(tp_price, 5)

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        return None
    return result.order


def _calculate_lot(symbol: str, risk_pct: float = 0.005,
                   sl_distance: Optional[float] = None) -> float:
    """
    Calculate position size based on risk % of account balance.
    Default 0.5% risk per trade.

    If sl_distance is provided, uses the precise formula:
        lot = (balance * risk_pct) / (sl_distance_in_ticks * trade_tick_value)
    Falls back to rough estimate if sl_distance is None.
    """
    account = mt5.account_info()
    if account is None:
        return 0.01  # minimum lot fallback

    balance = account.balance
    risk_amount = balance * risk_pct

    # Get symbol info for pip/point value
    info = mt5.symbol_info(symbol)
    if info is None:
        return max(0.01, round(risk_amount / 1000, 2))

    if sl_distance is not None and sl_distance > 0 and info.trade_tick_size and info.trade_tick_value:
        # Precise lot sizing using SL distance (in price units)
        tick_size = info.trade_tick_size
        tick_value = info.trade_tick_value
        ticks_in_sl = sl_distance / tick_size
        loss_per_lot = ticks_in_sl * tick_value
        if loss_per_lot > 0:
            lot = risk_amount / loss_per_lot
        else:
            lot = risk_amount / 5000
    else:
        # Fallback: rough estimate using standard pip value
        lot = risk_amount / 5000  # rough: $5000 risk = 1 standard lot

    lot = max(info.volume_min, min(lot, info.volume_max))
    lot = round(lot / info.volume_step) * info.volume_step
    return max(0.01, lot)


def _has_been_trading_recently(symbol: str, magic: int, minutes: int = 1440) -> bool:
    """Check if there were any trades in the last N minutes (default 24h)."""
    from time import time as _time
    cutoff = _time() - (minutes * 60)
    try:
        deals = mt5.history_deals_get(
            datetime.fromtimestamp(cutoff),
            datetime.now(),
        )
        if deals:
            for d in deals:
                if d.symbol == symbol and d.magic == magic:
                    return True
    except Exception:
        pass
    return False


# ── Main Loop ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-Symbol Trading Bot")
    parser.add_argument("--symbol", type=str, required=True, help="Trading symbol (e.g. EURUSD)")
    parser.add_argument("--strategy", type=str, required=True,
                        choices=list(STRATEGIES.keys()) + ["all"],
                        help="Trading strategy")
    parser.add_argument("--risk", type=float, default=0.005, help="Risk per trade (decimal, default 0.005 = 0.5%%)")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default 60)")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    strategy_name = args.strategy
    risk_pct = args.risk
    interval = args.interval

    bot_name = f"{strategy_name.capitalize()}_{symbol}"
    strategy_magic = MAGIC_BASE + STRATEGY_MAGIC.get(strategy_name, 0)
    daily_trades_today = 0
    last_trade_day = datetime.now().day

    print(f"[{bot_name}] Starting — symbol={symbol} strategy={strategy_name} risk={risk_pct*100:.1f}% interval={interval}s")

    # ── Init MT5 ────────────────────────────────────────────────────
    if not mt5.initialize():
        print(f"[{bot_name}] MT5 init FAILED: {mt5.last_error()}")
        _log_decision(bot_name, "MT5 Init Failed", f"symbol={symbol} error={mt5.last_error()}", "error")
        mt5.shutdown()
        sys.exit(1)

    account = mt5.account_info()
    if account is None:
        print(f"[{bot_name}] No account connected: {mt5.last_error()}")
        _log_decision(bot_name, "No Account", f"symbol={symbol} error={mt5.last_error()}", "error")
        mt5.shutdown()
        sys.exit(1)

    print(f"[{bot_name}] Account: {account.login} @ {account.server} | Balance: {account.balance:.2f}")

    # Ensure symbol is in market watch
    if not mt5.symbol_select(symbol, True):
        print(f"[{bot_name}] Failed to select {symbol}")
        _log_decision(bot_name, "Symbol Select Failed", f"symbol={symbol}", "error")
        mt5.shutdown()
        sys.exit(1)

    _log_decision(bot_name, "Bot Started", f"symbol={symbol} strategy={strategy_name} balance={account.balance:.2f}")

    # Price history for signal calculation
    price_history = _get_price_data(symbol, 60)
    if price_history is None:
        print(f"[{bot_name}] Failed to fetch initial price data")
        mt5.shutdown()
        sys.exit(1)

    print(f"[{bot_name}] Initial price data: {len(price_history)} candles loaded")
    print(f"[{bot_name}] Last close: {price_history[-1]:.5f}")

    # ── Main Loop ────────────────────────────────────────────────────
    while True:
        try:
            # Reset daily counter on day change
            today = datetime.now().day
            if today != last_trade_day:
                daily_trades_today = 0
                last_trade_day = today

            # Check daily limit
            if daily_trades_today >= DAILY_MAX_TRADES:
                time.sleep(CHECK_INTERVAL)
                continue

            # Get current price and position count
            price = _get_current_price(symbol)
            if price is None:
                time.sleep(CHECK_INTERVAL)
                continue
            bid, ask = price

            # Update price history
            new_data = _get_price_data(symbol, 60)
            if new_data and len(new_data) > len(price_history):
                price_history = new_data
            elif new_data and len(new_data) == len(price_history) and new_data[-1] != price_history[-1]:
                price_history = new_data

            # Count open positions for this bot
            open_positions = _count_open_positions(symbol, strategy_magic)
            if open_positions > 0:
                time.sleep(interval)
                continue  # Already in a trade

            # Get trading signal
            current_price = (bid + ask) / 2
            signal_fn = STRATEGIES.get(strategy_name)
            if signal_fn is None:
                print(f"[{bot_name}] Unknown strategy: {strategy_name}")
                time.sleep(interval)
                continue

            signal = signal_fn(current_price, price_history)
            if signal is None:
                time.sleep(interval)
                continue  # No signal this tick

            # ── Execute Trade ──────────────────────────────────────
            atr = _calculate_atr(symbol)
            order_type = mt5.ORDER_TYPE_BUY if signal == "buy" else mt5.ORDER_TYPE_SELL
            order_type_str = "BUY" if signal == "buy" else "SELL"

            # Calculate SL distance for precise lot sizing
            entry_price = ask if signal == "buy" else bid
            sl_price, tp_price = _calculate_sl_tp(symbol, order_type, entry_price, atr)
            sl_distance = abs(entry_price - sl_price)

            lot = _calculate_lot(symbol, risk_pct, sl_distance)

            ticket = _open_trade(symbol, order_type, lot, strategy_magic, bot_name, atr=atr)
            if ticket is not None:
                daily_trades_today += 1
                open_price = ask if signal == "buy" else bid
                print(f"[{bot_name}] {order_type_str} {lot} {symbol} @ {open_price:.5f} ticket={ticket}")
                _log_decision(bot_name, f"{order_type_str} OPEN", f"{lot} {symbol} @ {open_price:.5f} ticket={ticket}")
                _post_trade({
                    "symbol": symbol,
                    "direction": order_type_str,
                    "volume": lot,
                    "price": open_price,
                    "magic": strategy_magic,
                    "comment": bot_name,
                    "ticket": ticket,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            else:
                print(f"[{bot_name}] Order send FAILED for {signal}")
                _log_decision(bot_name, f"{order_type_str} FAILED", f"{lot} {symbol}", "error")

            # Wait before next check
            time.sleep(interval)

        except KeyboardInterrupt:
            print(f"[{bot_name}] Shutting down (interrupt)")
            _log_decision(bot_name, "Bot Stopped", "Keyboard interrupt")
            break
        except Exception as e:
            print(f"[{bot_name}] Error: {e}")
            traceback.print_exc()
            _log_decision(bot_name, "Bot Error", str(e), "error")
            time.sleep(CHECK_INTERVAL)

    mt5.shutdown()
    print(f"[{bot_name}] Exited cleanly")


if __name__ == "__main__":
    main()
