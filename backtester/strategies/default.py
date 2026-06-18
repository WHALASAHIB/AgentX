"""Default strategy — SMA crossover as a fallback."""
import pandas as pd

class DefaultStrategy:
    """Simple SMA crossover strategy — default fallback."""
    def __init__(self, fast_period=9, slow_period=21):
        self.fast_period = fast_period
        self.slow_period = slow_period

    def on_data(self, df):
        df = df.copy()
        df['sma_fast'] = df['close'].rolling(self.fast_period).mean()
        df['sma_slow'] = df['close'].rolling(self.slow_period).mean()
        df['signal'] = 0
        df.loc[df['sma_fast'] > df['sma_slow'], 'signal'] = 1
        df.loc[df['sma_fast'] <= df['sma_slow'], 'signal'] = -1
        return df
