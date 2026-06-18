#!/usr/bin/env python3
"""
Streaming M1 Breakout Bot — XAUUSD / EURUSD

Run: python streaming_bot.py

Prerequisites:
  - MetaTrader 5 terminal open, logged in, Algo Trading enabled
  - Target symbol visible in Market Watch
  - pip install -r requirements.txt
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.mt5_connect import connect_mt5, load_config

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOL = "XAUUSD"  # or "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
LOT_SIZE = 0.01
MAGIC = 888222
ORDER_COMMENT = "STREAM_M1"
DEVIATION = 20
RATES_COUNT = 100

SL_PCT = 0.0005   # 0.05%
TP_PCT = 0.001    # 0.10%
FLIP_PAUSE_SEC = 1
LOOP_SLEEP_SEC = 60

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2
SYMBOL_FILLING_RETURN = 4


# ---------------------------------------------------------------------------
# MT5 helpers
# ---------------------------------------------------------------------------


def ensure_symbol(symbol: str) -> bool:
    if not mt5.symbol_select(symbol, True):
        print(f"[ERROR] symbol_select failed for {symbol}: {mt5.last_error()}")
        return False
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"[ERROR] No symbol info for {symbol}")
        return False
    return True


def get_filling_mode(symbol: str) -> int:
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    filling = info.filling_mode
    if filling & SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    if filling & SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if filling & SYMBOL_FILLING_RETURN:
        return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_IOC


def normalize_price(price: float, symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    digits = info.digits if info else 5
    return round(price, digits)


def normalize_volume(volume: float, symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        return volume
    vol = max(info.volume_min, min(info.volume_max, volume))
    step = info.volume_step
    if step > 0:
        vol = round(vol / step) * step
    return round(vol, 2)


def sl_tp_for_side(order_type: int, price: float, symbol: str) -> tuple[float, float]:
    if order_type == mt5.ORDER_TYPE_BUY:
        sl = price * (1 - SL_PCT)
        tp = price * (1 + TP_PCT)
    else:
        sl = price * (1 + SL_PCT)
        tp = price * (1 - TP_PCT)
    return normalize_price(sl, symbol), normalize_price(tp, symbol)


# ---------------------------------------------------------------------------
# Order state functions
# ---------------------------------------------------------------------------


def create_order(
    symbol: str,
    quantity: float,
    order_type: int,
    price: float,
    sl: float,
    tp: float,
) -> Optional[object]:
    """Build and send a market deal request."""
    volume = normalize_volume(quantity, symbol)
    price = normalize_price(price, symbol)
    sl = normalize_price(sl, symbol)
    tp = normalize_price(tp, symbol)
    filling = get_filling_mode(symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": ORDER_COMMENT,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    side = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    print(f"[ORDER] Sending {side} {volume} {symbol} @ {price} | SL={sl} TP={tp}")

    result = mt5.order_send(request)
    if result is None:
        print(f"[ERROR] order_send returned None: {mt5.last_error()}")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[ERROR] order_send failed: retcode={result.retcode} comment={result.comment}")
        return None

    print(f"[ORDER] Filled | order={result.order} deal={result.deal}")
    return result


def close_order(
    symbol: str,
    quantity: float,
    order_type: int,
    price: float,
) -> bool:
    """
    Close open positions for symbol by ticket.
    order_type / price are used when closing a specific direction;
    otherwise each position is flattened using live tick prices.
    """
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        print(f"[CLOSE] No open positions for {symbol}")
        return False

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[ERROR] No tick for {symbol}: {mt5.last_error()}")
        return False

    filling = get_filling_mode(symbol)
    closed_any = False

    for pos in positions:
        if pos.magic != MAGIC:
            continue

        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            close_price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            close_price = tick.ask

        vol = quantity if quantity > 0 else pos.volume
        vol = min(vol, pos.volume)
        vol = normalize_volume(vol, symbol)
        close_price = normalize_price(close_price, symbol)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": vol,
            "type": close_type,
            "position": pos.ticket,
            "price": close_price,
            "deviation": DEVIATION,
            "magic": MAGIC,
            "comment": ORDER_COMMENT + "_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        print(f"[CLOSE] Flattening ticket={pos.ticket} vol={vol} @ {close_price}")
        result = mt5.order_send(request)
        if result is None:
            print(f"[ERROR] Close failed ticket={pos.ticket}: {mt5.last_error()}")
            continue
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(
                f"[ERROR] Close failed ticket={pos.ticket}: "
                f"retcode={result.retcode} {result.comment}"
            )
            continue

        print(f"[CLOSE] Success ticket={pos.ticket}")
        closed_any = True

    return closed_any


# ---------------------------------------------------------------------------
# Data & signals
# ---------------------------------------------------------------------------


def fetch_rates_df(symbol: str, count: int = RATES_COUNT) -> Optional[pd.DataFrame]:
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, count)
    if rates is None or len(rates) < 3:
        print(f"[ERROR] Insufficient rates: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    return df


def symbol_positions(symbol: str) -> list:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC]


def all_positions_empty() -> bool:
    positions = mt5.positions_get()
    return positions is None or len(positions) == 0


def get_signal(df: pd.DataFrame) -> Optional[str]:
    current_close = float(df["close"].iloc[-1])
    last_high = float(df["high"].iloc[-2])
    last_low = float(df["low"].iloc[-2])

    if current_close > last_high:
        return "BUY"
    if current_close < last_low:
        return "SELL"
    return None


def adverse_exit(df: pd.DataFrame, position_type: int) -> bool:
    current_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])

    if position_type == mt5.POSITION_TYPE_BUY and current_close < prev_close:
        return True
    if position_type == mt5.POSITION_TYPE_SELL and current_close > prev_close:
        return True
    return False


def print_status(symbol: str, df: pd.DataFrame) -> None:
    tick = mt5.symbol_info_tick(symbol)
    positions = mt5.positions_get()
    bot_pos = symbol_positions(symbol)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    bid = tick.bid if tick else 0.0
    ask = tick.ask if tick else 0.0
    current_close = float(df["close"].iloc[-1])
    last_high = float(df["high"].iloc[-2])
    last_low = float(df["low"].iloc[-2])
    prev_close = float(df["close"].iloc[-2])

    pos_summary = "FLAT"
    if bot_pos:
        p = bot_pos[0]
        side = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
        pos_summary = f"{side} ticket={p.ticket} vol={p.volume} profit={p.profit:.2f}"

    total_pos = len(positions) if positions else 0

    print(
        f"\n--- STATUS {now} ---\n"
        f"  Symbol: {symbol} | bid={bid:.5f} ask={ask:.5f}\n"
        f"  Close={current_close:.5f} | prev_close={prev_close:.5f} | "
        f"last_high={last_high:.5f} | last_low={last_low:.5f}\n"
        f"  All positions: {total_pos} | Bot position: {pos_summary}\n"
        f"----------------------"
    )


def execute_strategy(symbol: str, df: pd.DataFrame) -> None:
    signal = get_signal(df)
    bot_pos = symbol_positions(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[ERROR] No tick available for {symbol}")
        return

    # --- Adverse exit (preserve profit profile) ---
    if bot_pos:
        pos = bot_pos[0]
        if adverse_exit(df, pos.type):
            print("[ACTION] Adverse move detected — closing position")
            close_order(symbol, pos.volume, 0, 0)
            return

    # --- Flip or new entry ---
    if signal == "BUY":
        if bot_pos and bot_pos[0].type == mt5.POSITION_TYPE_SELL:
            print("[ACTION] Sell open + BUY signal — flip to long")
            close_order(symbol, bot_pos[0].volume, mt5.ORDER_TYPE_BUY, tick.ask)
            time.sleep(FLIP_PAUSE_SEC)
            price = tick.ask
            sl, tp = sl_tp_for_side(mt5.ORDER_TYPE_BUY, price, symbol)
            create_order(symbol, LOT_SIZE, mt5.ORDER_TYPE_BUY, price, sl, tp)
        elif all_positions_empty():
            print("[ACTION] No positions + BUY breakout — entering long")
            price = tick.ask
            sl, tp = sl_tp_for_side(mt5.ORDER_TYPE_BUY, price, symbol)
            create_order(symbol, LOT_SIZE, mt5.ORDER_TYPE_BUY, price, sl, tp)

    elif signal == "SELL":
        if bot_pos and bot_pos[0].type == mt5.POSITION_TYPE_BUY:
            print("[ACTION] Buy open + SELL signal — flip to short")
            close_order(symbol, bot_pos[0].volume, mt5.ORDER_TYPE_SELL, tick.bid)
            time.sleep(FLIP_PAUSE_SEC)
            price = tick.bid
            sl, tp = sl_tp_for_side(mt5.ORDER_TYPE_SELL, price, symbol)
            create_order(symbol, LOT_SIZE, mt5.ORDER_TYPE_SELL, price, sl, tp)
        elif all_positions_empty():
            print("[ACTION] No positions + SELL breakout — entering short")
            price = tick.bid
            sl, tp = sl_tp_for_side(mt5.ORDER_TYPE_SELL, price, symbol)
            create_order(symbol, LOT_SIZE, mt5.ORDER_TYPE_SELL, price, sl, tp)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"Starting Streaming M1 Bot | symbol={SYMBOL} | lot={LOT_SIZE}")

    cfg = load_config()
    print(f"Strategy symbol: {SYMBOL}")
    if not cfg:
        print("Tip: create mt5_config.json from mt5_config.example.json for reliable login")

    while not connect_mt5(cfg):
        print(f"MT5 connect failed: {mt5.last_error()}")
        print(f"Retrying in {LOOP_SLEEP_SEC}s...")
        time.sleep(LOOP_SLEEP_SEC)

    if not ensure_symbol(SYMBOL):
        mt5.shutdown()
        sys.exit(1)

    print("MT5 connected. Entering streaming loop (poll every 60s). Ctrl+C to stop.")

    try:
        while True:
            try:
                term = mt5.terminal_info()
                if term is None or not term.connected:
                    print("[WARN] Terminal disconnected — reconnecting MT5")
                    mt5.shutdown()
                    while not connect_mt5(load_config()):
                        time.sleep(LOOP_SLEEP_SEC)
                    ensure_symbol(SYMBOL)

                df = fetch_rates_df(SYMBOL)
                if df is not None:
                    print_status(SYMBOL, df)
                    execute_strategy(SYMBOL, df)

            except Exception:
                print(f"[ERROR] Loop iteration failed:\n{traceback.format_exc()}")

            time.sleep(LOOP_SLEEP_SEC)

    except KeyboardInterrupt:
        print("\nShutdown requested.")
    finally:
        mt5.shutdown()
        print("MT5 shutdown complete.")


if __name__ == "__main__":
    main()
