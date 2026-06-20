"""
Gold Phoenix Strategy — FTMO-Optimised Multi-Signal System for XAUUSD
=====================================================================
Combines session-based breakout, volatility expansion, and momentum
continuation. Designed specifically to pass FTMO Phase 1 (10% profit,
10% DD, 10 trading days) and Phase 2 (5%, 5%).

Signal Types (any can fire):
  1) ASIAN_BREAK — London open breakout of Asian session range
  2) SQUEEZE     — Bollinger Band width expansion after contraction
  3) PULLBACK    — EMA pullback entry in ADX-confirmed trend
  4) REVERSAL    — RSI extreme at key level

Engine handles SL/TP (200/400 pip hard caps for 1:2 R:R).
"""

import numpy as np
import pandas as pd


class GoldPhoenixStrategy:
    """
    Multi-signal Gold strategy optimised for FTMO challenge passing.

    Parameters:
        atr_period:      ATR lookback (default 14)
        adx_period:      ADX lookback (default 14)
        adx_threshold:   Min ADX to trade in trend mode (default 22)
        ema_fast:        Fast EMA for trend (default 21)
        ema_slow:        Slow EMA for trend (default 55)
        bb_period:       Bollinger Band period (default 20)
        bb_std:          Bollinger Band std dev (default 2.0)
        bb_squeeze_min:  Max BB width ratio to trigger squeeze mode
        max_trades_day:  Max trades per day (default 2)
        session_start_gmt: Trade start hour GMT (default 7)
        session_end_gmt:   Trade end hour GMT (default 17)
        asian_range_bars:  Bars for Asian session range calc (default 6)
    """

    def __init__(self,
                 atr_period: int = 14,
                 adx_period: int = 14,
                 adx_threshold: float = 28.0,       # Raised from 26 — fewer, higher quality signals
                 ema_fast: int = 21,
                 ema_slow: int = 55,
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 bb_squeeze_min: float = 0.35,       # Tightened from 0.40 — only strongest squeezes
                 max_trades_day: int = 2,
                 session_start_gmt: int = 8,         # Shifted from 7 — skip Asian open noise
                 session_end_gmt: int = 16,          # Tightened from 17
                 asian_range_bars: int = 6):
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.bb_squeeze_min = bb_squeeze_min
        self.max_trades_day = max_trades_day
        self.session_start_gmt = session_start_gmt
        self.session_end_gmt = session_end_gmt
        self.asian_range_bars = asian_range_bars

    def on_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate signals for XAUUSD on H1 timeframe."""
        df = df.copy()
        if len(df) < 60:
            df["signal"] = 0
            return df

        df["date"] = pd.to_datetime(df["date"])

        # ── 1. INDICATORS ──────────────────────────────────
        # True Range & ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = high_low.combine(high_close, max).combine(low_close, max)

        # EMAs
        ema_f = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        ema_s = df["close"].ewm(span=self.ema_slow, adjust=False).mean()
        ema_200 = df["close"].ewm(span=200, adjust=False).mean()

        # ADX
        up_move = df["high"].diff()
        down_move = -df["low"].diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        atr_adx = tr.rolling(self.adx_period).mean()
        plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(self.adx_period).mean() / atr_adx.replace(0, np.nan)
        minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(self.adx_period).mean() / atr_adx.replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx_line = dx.rolling(self.adx_period).mean()

        # Bollinger Bands
        bb_mid = df["close"].rolling(self.bb_period).mean()
        bb_std_val = df["close"].rolling(self.bb_period).std()
        bb_upper = bb_mid + self.bb_std * bb_std_val
        bb_lower = bb_mid - self.bb_std * bb_std_val
        bb_width = (bb_upper - bb_lower) / bb_mid

        # RSI(14)
        change = df["close"].diff()
        gain = change.mask(change < 0, 0.0)
        loss = (-change).mask(change > 0, 0.0)
        ema_gain = gain.ewm(com=13, adjust=False).mean()
        ema_loss = loss.ewm(com=13, adjust=False).mean()
        rs = ema_gain / ema_loss.replace(0, np.nan)
        rsi_series = 100.0 - (100.0 / (1.0 + rs))

        # Actual ATR for reference
        atr_series = tr.rolling(self.atr_period).mean()

        # Session/time features
        hour = df["date"].dt.hour
        day_of_year = df["date"].dt.dayofyear
        bar_of_day = df.groupby(day_of_year).cumcount()

        # Asian session range per day (first N bars)
        asian_high = df.groupby(day_of_year)["high"].transform(
            lambda x: x.iloc[:self.asian_range_bars].max()
        )
        asian_low = df.groupby(day_of_year)["low"].transform(
            lambda x: x.iloc[:self.asian_range_bars].min()
        )

        # ── 2. SIGNAL GENERATION ──────────────────────────
        df["signal"] = 0
        warmup = max(self.ema_slow + self.atr_period, self.bb_period * 3)

        for i in range(warmup, len(df)):
            h = hour.iloc[i]
            if h < self.session_start_gmt or h >= self.session_end_gmt:
                continue

            day = day_of_year.iloc[i]
            bar = bar_of_day.iloc[i]

            # Previous bar values
            idx = df.index[i]
            prev_idx = df.index[i - 1]

            # Get values
            close = df.at[idx, "close"]
            prev_close = df.at[prev_idx, "close"]
            high = df.at[idx, "high"]
            low = df.at[idx, "low"]
            atr = atr_series.iloc[i]
            adx = adx_line.iloc[i]
            rsi = rsi_series.iloc[i]

            if pd.isna(atr) or atr <= 0 or pd.isna(adx):
                continue

            # Trend direction
            trend_up = (
                close > ema_s.iloc[i]
                and adx >= self.adx_threshold
                and plus_di.iloc[i] > minus_di.iloc[i]
            )
            trend_down = (
                close < ema_s.iloc[i]
                and adx >= self.adx_threshold
                and minus_di.iloc[i] > plus_di.iloc[i]
            )
            no_trend = adx < self.adx_threshold

            # ── Signal 1: Asian Range Breakout ──
            # Best at London open (7-10 GMT)
            if 7 <= h <= 10:
                a_high = asian_high.iloc[i]
                a_low = asian_low.iloc[i]
                if not pd.isna(a_high) and not pd.isna(a_low):
                    a_range = a_high - a_low
                    # Breakout above Asian high (long)
                    if (trend_up or no_trend) and close > a_high and prev_close <= a_high:
                        if a_range > atr * 0.3:  # Asian range must be meaningful
                            df.at[idx, "signal"] = 1
                            continue
                    # Breakout below Asian low (short)
                    if (trend_down or no_trend) and close < a_low and prev_close >= a_low:
                        if a_range > atr * 0.3:
                            df.at[idx, "signal"] = -1
                            continue

            # ── Signal 2: Bollinger Squeeze Breakout ──
            bb_w = bb_width.iloc[i]
            bb_w_max = bb_width.iloc[max(0, i - 50):i].max()
            if not pd.isna(bb_w) and not pd.isna(bb_w_max) and bb_w_max > 0:
                squeeze_ratio = bb_w / bb_w_max
                if squeeze_ratio <= self.bb_squeeze_min:
                    # Breakout above upper band (long)
                    if close > bb_upper.iloc[i] and prev_close <= bb_upper.iloc[i - 1]:
                        df.at[idx, "signal"] = 1
                        continue
                    # Breakout below lower band (short)
                    if close < bb_lower.iloc[i] and prev_close >= bb_lower.iloc[i - 1]:
                        df.at[idx, "signal"] = -1
                        continue

            # ── Signal 3: EMA Pullback in Strong Trend ──
            if adx >= self.adx_threshold + 5:
                ema_f_val = ema_f.iloc[i]
                pullback_buffer = atr * 0.5
                # Long: price pulled back to fast EMA
                if trend_up and abs(close - ema_f_val) <= pullback_buffer:
                    lookback = min(5, i - 2)
                    was_below = any(
                        df.at[df.index[i - k], "close"] < ema_f.iloc[i - k]
                        for k in range(1, lookback + 1)
                    )
                    if was_below and rsi >= 40:
                        df.at[idx, "signal"] = 1
                        continue
                # Short
                if trend_down and abs(close - ema_f_val) <= pullback_buffer:
                    lookback = min(5, i - 2)
                    was_above = any(
                        df.at[df.index[i - k], "close"] > ema_f.iloc[i - k]
                        for k in range(1, lookback + 1)
                    )
                    if was_above and rsi <= 60:
                        df.at[idx, "signal"] = -1
                        continue

            # ── Signal 4: RSI Reversal at Slow EMA ──
            if no_trend:
                ema_s_val = ema_s.iloc[i]
                atr_buffer = atr * 1.5
                # Oversold bounce
                if rsi < 25 and close >= ema_s_val - atr_buffer:
                    if i > 1 and rsi_series.iloc[i - 1] < 25:
                        df.at[idx, "signal"] = 1
                        continue
                # Overbought drop
                if rsi > 75 and close <= ema_s_val + atr_buffer:
                    if i > 1 and rsi_series.iloc[i - 1] > 75:
                        df.at[idx, "signal"] = -1
                        continue

        # ── 3. POST-PROCESS: Cap trades per day ──
        signal_days = df[df["signal"] != 0].groupby(day_of_year)["signal"].count()
        for day_num in signal_days.index[signal_days > self.max_trades_day].tolist():
            day_mask = (day_of_year == day_num) & (df["signal"] != 0)
            day_indices = df[day_mask].index
            # Keep first N signals of the day
            keep = day_indices[:self.max_trades_day]
            drop = day_indices.difference(keep)
            df.loc[drop, "signal"] = 0

        # Add ATR column for engine's dynamic SL/TP calculation
        df["atr"] = atr_series

        return df
