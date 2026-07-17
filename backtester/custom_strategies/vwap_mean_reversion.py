"""
VWAP Mean Reversion Strategy — for Propfirm Pass backtest
Matches the propfirm_pass_bot.py logic: VWAP deviation + rejection candle on M1 during session.
"""
import numpy as np
import pandas as pd


class VWAPMeanReversionStrategy:
    """VWAP Mean Reversion with Rejection Candle Confirmation.

    Configurable params:
        deviation_pips (int):  Min pips from VWAP to trigger (default: 8)
        sl_pips (int):         Stop loss in pips (default: 12)
        tp_pips (int):         Take profit in pips (default: 24)
        session_start (int):   Session start hour UTC (default: 13)
        session_end (int):     Session end hour UTC (default: 15)
        wick_ratio (float):    Min wick:body ratio for pin bar (default: 1.5)
        body_max_pct (float):  Max body % of range (default: 0.40)
        momentum_skip (float): Skip if body > this % of range (default: 0.60)
        pip_value (float):     Instrument pip value (default: 0.0001 for EURUSD)
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.deviation_pips = int(kwargs.get("deviation_pips", 8))
        self.sl_pips = int(kwargs.get("sl_pips", 12))
        self.tp_pips = int(kwargs.get("tp_pips", 24))
        self.session_start = int(kwargs.get("session_start", 13))
        self.session_end = int(kwargs.get("session_end", 15))
        self.wick_ratio = float(kwargs.get("wick_ratio", 1.5))
        self.body_max_pct = float(kwargs.get("body_max_pct", 0.40))
        self.momentum_skip = float(kwargs.get("momentum_skip", 0.60))
        self.pip_value = float(kwargs.get("pip_value", 0.0001))
        self._name = f"VWAP_MeanRev({self.deviation_pips}pip_SL{self.sl_pips}_TP{self.tp_pips})"

        # Precompute VWAP for each bar (rolling session VWAP)
        closes = data["close"].values.astype(float)
        highs = data["high"].values.astype(float)
        lows = data["low"].values.astype(float)
        volumes = data.get("tick_volume", data.get("volume", pd.Series(np.ones(len(data))))).values
        typical = (highs + lows + closes) / 3.0
        self.vwap = np.full_like(closes, np.nan)

        # Compute VWAP per session window (rolling from session start)
        times = data["time"].values
        cum_typ_vol = 0.0
        cum_vol = 0.0
        last_hour = None
        for i in range(len(data)):
            t = pd.Timestamp(times[i])
            hour = t.hour
            # Reset VWAP at each new hour boundary (hourly VWAP)
            if hour != last_hour:
                cum_typ_vol = 0.0
                cum_vol = 0.0
                last_hour = hour
            if volumes[i] > 0:
                cum_typ_vol += typical[i] * volumes[i]
                cum_vol += volumes[i]
                self.vwap[i] = cum_typ_vol / cum_vol
            elif cum_vol > 0:
                self.vwap[i] = self.vwap[i - 1]

    def next(self, i: int) -> dict:
        if i < 10 or np.isnan(self.vwap[i]) or np.isnan(self.vwap[i - 1]):
            return {"action": None}

        times = self.data["time"].values
        t = pd.Timestamp(times[i])
        hour = t.hour

        # Session filter
        if not (self.session_start <= hour < self.session_end):
            return {"action": None}

        closes = self.data["close"].values.astype(float)
        highs = self.data["high"].values.astype(float)
        lows = self.data["low"].values.astype(float)
        opens = self.data["open"].values.astype(float)

        price = closes[i]
        vwap = self.vwap[i]
        deviation = abs(price - vwap) / self.pip_value

        # Check deviation
        if deviation < self.deviation_pips:
            return {"action": None}

        # Build 5-bar rejection candle check (last 5 bars as proxy for 5M on M1 data)
        n_lookback = min(5, i)
        bar_high = np.max(highs[i - n_lookback : i + 1])
        bar_low = np.min(lows[i - n_lookback : i + 1])
        bar_open = opens[i - n_lookback]
        bar_close = closes[i]

        bar_body = abs(bar_close - bar_open)
        bar_range = bar_high - bar_low
        if bar_range == 0:
            return {"action": None}

        body_pct = bar_body / bar_range

        # Momentum filter — skip trend candles
        if body_pct > self.momentum_skip:
            return {"action": None}

        # Determine direction
        is_bullish = bar_close > bar_open

        if price < vwap:  # Below VWAP → look for BUY
            lower_wick = bar_open - bar_low if is_bullish else bar_close - bar_low
            upper_wick = bar_high - bar_close if is_bullish else bar_high - bar_open
            if is_bullish and lower_wick > bar_body * self.wick_ratio and body_pct < self.body_max_pct:
                return {"action": "buy", "entry_price": price,
                        "sl": price - self.sl_pips * self.pip_value,
                        "tp": price + self.tp_pips * self.pip_value,
                        "deviation_pips": deviation}
        else:  # Above VWAP → look for SELL
            lower_wick = bar_close - bar_low if not is_bullish else bar_open - bar_low
            upper_wick = bar_high - bar_close if not is_bullish else bar_high - bar_open
            if not is_bullish and upper_wick > bar_body * self.wick_ratio and body_pct < self.body_max_pct:
                return {"action": "sell", "entry_price": price,
                        "sl": price + self.sl_pips * self.pip_value,
                        "tp": price - self.tp_pips * self.pip_value,
                        "deviation_pips": deviation}

        return {"action": None}

    @property
    def name(self) -> str:
        return self._name
