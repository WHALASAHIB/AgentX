"""
ATR Expansion Breakout Strategy
Detects volatility expansion: when ATR(14) > threshold × ATR(50), enter on breakout direction.
"""
import numpy as np
import pandas as pd


class ATRExpansionStrategy:
    """ATR Expansion Breakout Strategy.

    Configurable params:
        fast_atr (int):     Fast ATR period (default: 14)
        slow_atr (int):     Slow ATR period (default: 50)
        expansion_thresh (float):  ATR ratio to trigger (default: 1.10)
        contraction_thresh (float): ATR ratio to exit (default: 1.15)
        sl_atr_mult (float): Stop loss as ATR multiple (default: 1.5)
        tp_atr_mult (float): Take profit as ATR multiple (default: 3.0)
        max_trades (int):   Max trades per day (default: 3)
        risk_pct (float):   Risk per trade (default: 0.005)
        pip_value (float):  Instrument pip value (default: 0.0001)
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.fast_atr = int(kwargs.get("fast_atr", 14))
        self.slow_atr = int(kwargs.get("slow_atr", 50))
        self.expansion_thresh = float(kwargs.get("expansion_thresh", 1.10))
        self.contraction_thresh = float(kwargs.get("contraction_thresh", 1.15))
        self.sl_atr_mult = float(kwargs.get("sl_atr_mult", 1.5))
        self.tp_atr_mult = float(kwargs.get("tp_atr_mult", 3.0))
        self.max_trades = int(kwargs.get("max_trades", 3))
        self.risk_pct = float(kwargs.get("risk_pct", 0.005))
        self.pip_value = float(kwargs.get("pip_value", 0.0001))
        self._name = f"ATR_Expansion(thresh={self.expansion_thresh}_fast{self.fast_atr}_slow{self.slow_atr})"

        highs = data["high"].values.astype(float)
        lows = data["low"].values.astype(float)
        closes = data["close"].values.astype(float)

        self.atr_fast = self._compute_atr(highs, lows, closes, self.fast_atr)
        self.atr_slow = self._compute_atr(highs, lows, closes, self.slow_atr)

        # Track daily trades
        self._daily_trades = {}

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
        if i < self.slow_atr + 2:
            return {"action": None}
        if np.isnan(self.atr_fast[i]) or np.isnan(self.atr_slow[i]) or self.atr_slow[i] <= 0:
            return {"action": None}

        # Check daily trade limit
        times = self.data["time"].values
        t = pd.Timestamp(times[i])
        date_key = t.strftime("%Y-%m-%d")
        if self._daily_trades.get(date_key, 0) >= self.max_trades:
            return {"action": None}

        # Check volatility expansion
        ratio = self.atr_fast[i] / self.atr_slow[i]
        if ratio < self.expansion_thresh:
            return {"action": None}

        highs = self.data["high"].values.astype(float)
        lows = self.data["low"].values.astype(float)
        closes = self.data["close"].values.astype(float)
        opens = self.data["open"].values.astype(float)

        direction = None
        # Price broke above previous candle high
        if i > 0 and closes[i] > highs[i - 1]:
            direction = "buy"
        elif i > 0 and closes[i] < lows[i - 1]:
            direction = "sell"

        if direction is None:
            return {"action": None}

        entry = closes[i]
        atr_val = self.atr_fast[i]
        sl = entry - self.sl_atr_mult * atr_val if direction == "buy" else entry + self.sl_atr_mult * atr_val
        tp = entry + self.tp_atr_mult * atr_val if direction == "buy" else entry - self.tp_atr_mult * atr_val

        # Increment daily trade counter
        self._daily_trades[date_key] = self._daily_trades.get(date_key, 0) + 1

        return {
            "action": direction,
            "entry_price": entry,
            "sl": sl,
            "tp": tp,
            "atr_ratio": ratio,
        }

    @property
    def name(self) -> str:
        return self._name
