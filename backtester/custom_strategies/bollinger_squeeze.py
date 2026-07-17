"""
Bollinger Squeeze Breakout Strategy — matches volatility_breakout_bot.py logic
M5 timeframe, BB squeeze detection, 1:4 RR
"""
import numpy as np
import pandas as pd


class BollingerSqueezeStrategy:
    """Bollinger Squeeze Breakout — matches the volatility_breakout_bot.

    Configurable params:
        bb_period (int):    BB SMA period (default: 20)
        bb_std (float):     BB std dev multiplier (default: 2.0)
        squeeze_thresh (float): BW must shrink to this fraction (default: 0.85)
        squeeze_count (int): Minimum consecutive squeeze bars (default: 3)
        expansion_thresh (float): BW must expand to this fraction (default: 1.1)
        sl_atr (float):     SL as ATR multiple (default: 1.5)
        tp_atr (float):     TP as ATR multiple (default: 6.0)
        atr_period (int):   ATR lookback (default: 14)
        risk (float):       Risk per trade (default: 0.005)
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.bb_period = int(kwargs.get("bb_period", 20))
        self.bb_std = float(kwargs.get("bb_std", 2.0))
        self.squeeze_thresh = float(kwargs.get("squeeze_thresh", 0.85))
        self.squeeze_count = int(kwargs.get("squeeze_count", 3))
        self.expansion_thresh = float(kwargs.get("expansion_thresh", 1.1))
        self.sl_atr = float(kwargs.get("sl_atr", 1.5))
        self.tp_atr = float(kwargs.get("tp_atr", 6.0))
        self.atr_period = int(kwargs.get("atr_period", 14))
        self.risk = float(kwargs.get("risk", 0.005))
        self._name = f"BollingerSqueeze(BB{self.bb_period}_SQ{self.squeeze_count})"

        closes = data["close"].values.astype(float)
        highs = data["high"].values.astype(float)
        lows = data["low"].values.astype(float)

        # Precompute BB
        self.middle = self._sma(closes, self.bb_period)
        self.std = self._rolling_std(closes, self.bb_period)
        self.upper = self.middle + self.bb_std * self.std
        self.lower = self.middle - self.bb_std * self.std
        self.bandwidth = (self.upper - self.lower) / self.middle

        # Precompute ATR
        self.atr = self._compute_atr(highs, lows, closes, self.atr_period)

        # Track squeeze state across bars
        self._squeeze_count = np.zeros(len(data), dtype=int)

    @staticmethod
    def _sma(arr, period):
        out = np.full_like(arr, np.nan)
        if len(arr) < period:
            return out
        cumsum = np.cumsum(arr)
        out[period - 1] = cumsum[period - 1] / period
        out[period:] = (cumsum[period:] - cumsum[:-period]) / period
        return out

    @staticmethod
    def _rolling_std(arr, period):
        out = np.full_like(arr, np.nan)
        if len(arr) < period:
            return out
        for i in range(period - 1, len(arr)):
            out[i] = np.std(arr[i - period + 1 : i + 1])
        return out

    @staticmethod
    def _compute_atr(highs, lows, closes, period):
        tr = np.full_like(highs, np.nan)
        for i in range(1, len(highs)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr[i] = max(hl, hc, lc)
        atr = np.full_like(tr, np.nan)
        if len(tr) < period:
            return atr
        atr[period] = np.nanmean(tr[1: period + 1])
        for i in range(period + 1, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        return atr

    def next(self, i: int) -> dict:
        if i < self.bb_period + self.atr_period + 2:
            return {"action": None}
        if np.isnan(self.bandwidth[i]) or np.isnan(self.atr[i]) or np.isnan(self.upper[i]):
            return {"action": None}

        closes = self.data["close"].values.astype(float)
        highs = self.data["high"].values.astype(float)
        lows = self.data["low"].values.astype(float)
        opens = self.data["open"].values.astype(float)

        # Track squeeze
        if i > 0 and not np.isnan(self.bandwidth[i - 1]):
            if self.bandwidth[i] < self.bandwidth[i - 1] * self.squeeze_thresh:
                self._squeeze_count[i] = self._squeeze_count[i - 1] + 1
            else:
                self._squeeze_count[i] = 0
        else:
            self._squeeze_count[i] = 0

        # Need squeeze_count consecutive squeezed bars, then expansion
        if self._squeeze_count[i] < self.squeeze_count:
            return {"action": None}

        # Check for breakout: price breaks above upper or below lower band
        tick_high = highs[i]
        tick_low = lows[i]

        direction = None
        if tick_high > self.upper[i]:
            direction = "buy"
        elif tick_low < self.lower[i]:
            direction = "sell"

        if direction is None:
            return {"action": None}

        # Use ATR for SL/TP (matching the bot: SL=1.5×ATR, TP=6.0×ATR)
        atr_val = self.atr[i]
        entry = closes[i]

        if direction == "buy":
            sl = entry - self.sl_atr * atr_val
            tp = entry + self.tp_atr * atr_val
        else:
            sl = entry + self.sl_atr * atr_val
            tp = entry - self.tp_atr * atr_val

        return {"action": direction, "entry_price": entry, "sl": sl, "tp": tp, "atr_val": atr_val}

    @property
    def name(self) -> str:
        return self._name
