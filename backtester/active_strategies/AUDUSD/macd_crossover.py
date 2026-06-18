"""MACD Crossover strategy."""
import pandas as pd
import numpy as np

class macd_crossover_strategy:
    """MACD crossover with histogram confirmation."""
    def __init__(self, fast=12, slow=26, signal=9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def on_data(self, df):
        df = df.copy()
        ema_fast = df['close'].ewm(span=self.fast).mean()
        ema_slow = df['close'].ewm(span=self.slow).mean()
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=self.signal).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        # Signal: macd crosses above signal line = buy, below = sell
        df['signal'] = 0
        df.loc[(df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1)), 'signal'] = 1
        df.loc[(df['macd'] < df['macd_signal']) & (df['macd'].shift(1) >= df['macd_signal'].shift(1)), 'signal'] = -1
        return df
