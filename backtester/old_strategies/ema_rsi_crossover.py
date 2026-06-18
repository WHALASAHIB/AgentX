"""
EMA + RSI Momentum Crossover Strategy — Gold-Optimised (XAUUSD)
================================================================
Entry rules:
  BUY  → Fast EMA crosses ABOVE Slow EMA + RSI > 50 but < 70 (momentum building)
  SELL → Fast EMA crosses BELOW Slow EMA + RSI < 50 but > 30 (momentum fading)

Stop-loss / Take-profit: dynamic via ATR(14) — SL=2×ATR, TP=5×ATR (R:R=1:2.5)
Optimised for Gold's trending tendencies on 1h / 4h timeframes.
"""

import numpy as np
import pandas as pd


class EmaRsiCrossoverStrategy:
    """EMA(9/21) + RSI(14) momentum crossover strategy for Gold."""

    def __init__(self, ema_fast: int = 9, ema_slow: int = 21,
                 rsi_period: int = 14, rsi_buy_min: float = 50.0,
                 rsi_buy_max: float = 70.0, rsi_sell_min: float = 30.0,
                 rsi_sell_max: float = 50.0):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_buy_min = rsi_buy_min
        self.rsi_buy_max = rsi_buy_max
        self.rsi_sell_min = rsi_sell_min
        self.rsi_sell_max = rsi_sell_max

    def on_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute indicators and generate entry signals.

        Expects columns: date, open, high, low, close [, volume]
        Returns DataFrame with added 'signal' column:
            1 = BUY, -1 = SELL, 0 = HOLD
        """
        df = df.copy()

        # --- 1. EMAs (exponential) ---
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()

        # --- 2. RSI (Wilder's smoothed RSI) ---
        change = df['close'].diff()
        gain = change.mask(change < 0, 0.0)
        loss = (-change).mask(change > 0, 0.0)

        ema_gain = gain.ewm(com=self.rsi_period - 1, adjust=False).mean()
        ema_loss = loss.ewm(com=self.rsi_period - 1, adjust=False).mean()

        rs = ema_gain / ema_loss.replace(0, np.nan)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

        # --- 3. ATR(14) for dynamic SL/TP ---
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = high_low.combine(high_close, max).combine(low_close, max)
        df['atr'] = tr.rolling(14).mean()

        # --- 4. Entry signals ---
        df['signal'] = 0

        # Cross-up: EMA fast crossed above slow (this bar >, prev bar <=)
        cross_up = (df['ema_fast'] > df['ema_slow']) & \
                   (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1))

        # Cross-down: EMA fast crossed below slow
        cross_down = (df['ema_fast'] < df['ema_slow']) & \
                     (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1))

        # BUY: crossover + RSI momentum building (not overbought)
        buy_cond = cross_up & \
                   (df['rsi'] >= self.rsi_buy_min) & \
                   (df['rsi'] <= self.rsi_buy_max)

        # SELL: crossunder + RSI momentum fading (not oversold)
        sell_cond = cross_down & \
                    (df['rsi'] <= self.rsi_sell_max) & \
                    (df['rsi'] >= self.rsi_sell_min)

        df.loc[buy_cond, 'signal'] = 1
        df.loc[sell_cond, 'signal'] = -1

        # Forward-fill signals between crossovers (stay in position)
        df['signal'] = df['signal'].replace(0, np.nan).ffill().fillna(0)

        return df
