"""SMA Crossover strategy."""
import pandas as pd

class sma_crossover_strategy:
    """EMA 9/21 crossover strategy for trend following."""
    def __init__(self, fast_period=9, slow_period=21):
        self.fast_period = fast_period
        self.slow_period = slow_period

    def on_data(self, df):
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=self.fast_period).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_period).mean()
        df['signal'] = 0
        df.loc[df['ema_fast'] > df['ema_slow'], 'signal'] = 1
        df.loc[df['ema_fast'] <= df['ema_slow'], 'signal'] = -1
        return df
