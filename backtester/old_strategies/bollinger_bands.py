"""Bollinger Bands mean reversion strategy."""
import pandas as pd
import numpy as np

class bollinger_bands_strategy:
    """Bollinger Bands mean reversion strategy."""
    def __init__(self, period=20, std_dev=2.0):
        self.period = period
        self.std_dev = std_dev

    def on_data(self, df):
        df = df.copy()
        df['bb_mid'] = df['close'].rolling(self.period).mean()
        df['bb_std'] = df['close'].rolling(self.period).std()
        df['bb_upper'] = df['bb_mid'] + self.std_dev * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - self.std_dev * df['bb_std']
        # RSI for confirmation
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        # Signals
        df['signal'] = 0
        # Buy when price touches lower band and RSI > 30 (oversold but not extreme)
        df.loc[(df['close'] <= df['bb_lower']) & (df['rsi'] > 30), 'signal'] = 1
        # Sell when price touches upper band and RSI < 70 (overbought but not extreme)
        df.loc[(df['close'] >= df['bb_upper']) & (df['rsi'] < 70), 'signal'] = -1
        return df
