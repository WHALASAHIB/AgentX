"""
Propfirm Pass Strategy v11 — Backtestable Python version
=========================================================
Matches propfirm_pass_bot.py logic:
  - EURUSD only
  - London 7:00-9:00 UTC + US Open 13:00-15:00 UTC (Mon-Fri)
  - VWAP deviation >= 10 pips + 5M rejection candle (pin bar/doji)
  - Momentum filter: skip if candle body > 60% of range
  - Max 2 trades/day, max 2 consecutive losses -> stop
  - SL: 12 pips, TP: 24 pips (1:2 RR)
  - 30-min cooldown for opposite-direction trades
  - Session trend filter (15 pips threshold)
"""
import numpy as np
import pandas as pd


class PropfirmPassStrategy:
    """Propfirm Pass v11 — VWAP Mean Reversion on EURUSD.

    Configurable params:
        deviation_pips (int):  Min pips from VWAP to trigger (default: 10)
        sl_pips (int):         Stop loss in pips (default: 12)
        tp_pips (int):         Take profit in pips (default: 24)
        session_start (int):   Session start hour UTC (default: 7)
        session_end (int):     Session end hour UTC (default: 15)
        wick_ratio (float):    Min wick:body ratio for pin bar (default: 1.5)
        body_max_pct (float):  Max body %% of range for pin bar (default: 0.40)
        momentum_skip (float): Skip if body > this %% of range (default: 0.60)
        max_daily_trades (int): Max trades per day (default: 2)
        max_consecutive_losses (int): Stop after this many losses (default: 2)
        cooldown_minutes (int): Cooldown for opposite direction (default: 30)
        trend_pips (int):      Pips to establish session trend (default: 15)
        pip_value (float):     Instrument pip value (default: 0.0001 for EURUSD)
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.deviation_pips = int(kwargs.get("deviation_pips", 10))
        self.sl_pips = int(kwargs.get("sl_pips", 12))
        self.tp_pips = int(kwargs.get("tp_pips", 24))
        self.session_start = int(kwargs.get("session_start", 7))
        self.session_end = int(kwargs.get("session_end", 15))
        self.wick_ratio = float(kwargs.get("wick_ratio", 1.5))
        self.body_max_pct = float(kwargs.get("body_max_pct", 0.40))
        self.momentum_skip = float(kwargs.get("momentum_skip", 0.60))
        self.max_daily_trades = int(kwargs.get("max_daily_trades", 2))
        self.max_consecutive_losses = int(kwargs.get("max_consecutive_losses", 2))
        self.cooldown_minutes = int(kwargs.get("cooldown_minutes", 30))
        self.trend_pips = int(kwargs.get("trend_pips", 15))
        self.pip_value = float(kwargs.get("pip_value", 0.0001))
        self._name = "PropfirmPass_v11"

        # Precompute VWAP for each bar (rolling session VWAP)
        closes = data["close"].values.astype(float)
        highs = data["high"].values.astype(float)
        lows = data["low"].values.astype(float)
        volumes = data.get("tick_volume", data.get("volume", pd.Series(np.ones(len(data))))).values
        typical = (highs + lows + closes) / 3.0
        self.vwap = np.full_like(closes, np.nan)

        # Compute VWAP — rolling 20-bar VWAP (works on any timeframe)
        times = data["time"].values
        cum_typ_vol = 0.0
        cum_vol = 0.0
        window = 20
        for i in range(len(data)):
            if i < window:
                if volumes[i] > 0:
                    cum_typ_vol += typical[i] * volumes[i]
                    cum_vol += volumes[i]
                    self.vwap[i] = cum_typ_vol / cum_vol if cum_vol > 0 else typical[i]
                elif cum_vol > 0:
                    self.vwap[i] = self.vwap[i - 1]
            else:
                # Rolling window: remove the bar going out, add the new one
                out_idx = i - window
                if volumes[out_idx] > 0:
                    cum_typ_vol -= typical[out_idx] * volumes[out_idx]
                    cum_vol -= volumes[out_idx]
                if volumes[i] > 0:
                    cum_typ_vol += typical[i] * volumes[i]
                    cum_vol += volumes[i]
                self.vwap[i] = cum_typ_vol / cum_vol if cum_vol > 0 else typical[i]

        # State tracking
        self._daily_trade_count = 0
        self._consecutive_losses = 0
        self._last_trade_day = -1
        self._last_trade_close_idx = -1
        self._last_trade_direction = 0
        self._session_trend = 0
        self._session_trend_price = 0.0
        self._in_position = False
        self._entry_price = 0.0
        self._sl_price = 0.0
        self._tp_price = 0.0
        self._position_side = 0  # 1=buy, -1=sell
        self._entry_bar = -1
        self._bars_until_reentry = 0  # cooldown bars after any close to prevent immediate re-entry

    def next(self, i: int) -> dict:
        if i < 10 or np.isnan(self.vwap[i]) or np.isnan(self.vwap[i - 1]):
            return {"action": None}

        # Decrement re-entry cooldown
        if self._bars_until_reentry > 0:
            self._bars_until_reentry -= 1

        times = self.data["time"].values
        t = pd.Timestamp(times[i])
        hour = t.hour
        day = t.dayofyear

        # Reset daily state at new day
        if day != self._last_trade_day:
            self._daily_trade_count = 0
            self._consecutive_losses = 0
            self._last_trade_day = day
            self._session_trend = 0
            self._session_trend_price = 0.0

        closes = self.data["close"].values.astype(float)
        highs = self.data["high"].values.astype(float)
        lows = self.data["low"].values.astype(float)

        # --- If in a position, check SL/TP on this bar ---
        if self._in_position:
            bar_high = highs[i]
            bar_low = lows[i]
            if self._position_side == 1:  # Long position
                # SL hit
                if bar_low <= self._sl_price:
                    self._close_trade(i)
                    return {"action": "sell"}
                # TP hit
                if bar_high >= self._tp_price:
                    self._close_trade(i)
                    return {"action": "sell"}
            else:  # Short position
                # SL hit
                if bar_high >= self._sl_price:
                    self._close_trade(i)
                    return {"action": "buy"}
                # TP hit
                if bar_low <= self._tp_price:
                    self._close_trade(i)
                    return {"action": "buy"}
            # Still in position — no new signals
            return {"action": None}

        # --- Look for new entry signals ---
        # Re-entry cooldown — wait after any close before new entry
        if self._bars_until_reentry > 0:
            return {"action": None}

        # Session filter
        if not (self.session_start <= hour < self.session_end):
            return {"action": None}

        # Weekend filter
        weekday = t.dayofweek
        if weekday >= 5:  # Sat/Sun
            return {"action": None}

        # Max daily trades / consecutive losses limits
        if self._daily_trade_count >= self.max_daily_trades:
            return {"action": None}
        if self._consecutive_losses >= self.max_consecutive_losses:
            return {"action": None}

        opens = self.data["open"].values.astype(float)

        price = closes[i]
        vwap = self.vwap[i]
        deviation = abs(price - vwap) / self.pip_value

        # VWAP deviation check
        if deviation < self.deviation_pips:
            return {"action": None}

        # Build 5-bar rejection candle (proxy for 5M on M1 data)
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

        # Momentum filter -- skip strong trend candles
        if body_pct > self.momentum_skip:
            return {"action": None}

        # Determine direction
        is_bullish = bar_close > bar_open

        signal_direction = 0

        if price < vwap:  # Below VWAP -> look for BUY
            lower_wick = bar_open - bar_low if is_bullish else bar_close - bar_low
            if (is_bullish and lower_wick > bar_body * self.wick_ratio and body_pct < self.body_max_pct):
                signal_direction = 1
            elif body_pct < 0.10:  # Doji -> trade in deviation direction
                signal_direction = 1  # Buy (below VWAP)
        else:  # Above VWAP -> look for SELL
            upper_wick = bar_high - bar_close if not is_bullish else bar_high - bar_open
            if (not is_bullish and upper_wick > bar_body * self.wick_ratio and body_pct < self.body_max_pct):
                signal_direction = -1
            elif body_pct < 0.10:  # Doji -> trade in deviation direction
                signal_direction = -1  # Sell (above VWAP)

        if signal_direction == 0:
            return {"action": None}

        # Session trend tracking
        if self._session_trend_price == 0.0:
            self._session_trend_price = price
        move_pips = (price - self._session_trend_price) / self.pip_value
        if self._session_trend == 0:
            if move_pips >= self.trend_pips:
                self._session_trend = 1
            elif move_pips <= -self.trend_pips:
                self._session_trend = -1

        # Trend filter: if trend established, only allow aligned trades
        if self._session_trend != 0 and self._session_trend != signal_direction:
            return {"action": None}

        # Cooldown: opposite-direction trade blocked within cooldown period
        if self._last_trade_close_idx > 0 and self._last_trade_direction != 0:
            if signal_direction != self._last_trade_direction:
                bars_since_close = i - self._last_trade_close_idx
                mins_since_close = bars_since_close  # assume M1 data
                if mins_since_close < self.cooldown_minutes:
                    return {"action": None}

        # Enter trade: store SL/TP levels so next() can check them on each bar
        self._daily_trade_count += 1
        self._last_trade_direction = signal_direction
        self._position_side = signal_direction
        self._entry_bar = i
        self._entry_price = price  # entry at the bar's close (approximate)
        if signal_direction == 1:
            self._sl_price = price - self.sl_pips * self.pip_value
            self._tp_price = price + self.tp_pips * self.pip_value
        else:
            self._sl_price = price + self.sl_pips * self.pip_value
            self._tp_price = price - self.tp_pips * self.pip_value
        self._in_position = True

        return {
            "action": "buy" if signal_direction == 1 else "sell",
            "deviation_pips": deviation,
        }

    def _close_trade(self, i: int):
        """Called internally when SL or TP is hit."""
        self._last_trade_close_idx = i
        self._in_position = False
        self._position_side = 0
        self._bars_until_reentry = 5  # wait 5 bars before re-entry

    @property
    def name(self) -> str:
        return self._name
