"""
loader.py — Strategy Discovery
===============================
Scans C:\\Trading\\bots\\active_bots\\ for bot scripts and registers
them as available backtest strategies.
Also provides built-in crossover strategy classes for the most common
signal types (MACD, SMA, Bollinger Bands, Volatility Breakout, Gold Phoenix).

Each strategy class follows the interface:
    __init__(self, data, **kwargs)   — data is a DataFrame with OHLC columns
    next(self, i) -> dict            — called on bar indexed i, returns signal
    name -> str                      — human-readable name
"""

import importlib.util
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from custom_strategies.propfirm_pass import PropfirmPassStrategy

logger = logging.getLogger(__name__)

# ── Paths ───────────────────────────────────────────────────────────────────
BOTS_DIR = Path(__file__).resolve().parent.parent / "bots" / "active_bots"


# ═══════════════════════════════════════════════════════════════════════════════
#  Built-in Strategy Classes
# ═══════════════════════════════════════════════════════════════════════════════

class SMAStrategy:
    """Simple Moving Average Crossover Strategy.

    Configurable params:
        fast_period (int):  fast SMA period (default: 9)
        slow_period (int):  slow SMA period (default: 21)
    Signal logic:
        BUY  when fast SMA crosses above slow SMA
        SELL when fast SMA crosses below slow SMA
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.fast = int(kwargs.get("fast_period", 9))
        self.slow = int(kwargs.get("slow_period", 21))
        self._name = f"SMA({self.fast}/{self.slow})"

        # Precompute indicators
        closes = data["close"].values.astype(float)
        self.fast_sma = self._sma(closes, self.fast)
        self.slow_sma = self._sma(closes, self.slow)

    @staticmethod
    def _sma(arr: np.ndarray, period: int) -> np.ndarray:
        out = np.full_like(arr, np.nan)
        if len(arr) < period:
            return out
        cumsum = np.cumsum(arr)
        out[period - 1] = cumsum[period - 1] / period
        out[period:] = (cumsum[period:] - cumsum[:-period]) / period
        return out

    def next(self, i: int) -> dict:
        """Return signal dict for bar i.

        Returns:
            {"action": "buy" | "sell" | None}
        """
        if i < max(self.fast, self.slow) or np.isnan(self.fast_sma[i]) or np.isnan(self.slow_sma[i]):
            return {"action": None}

        # Crossover detection
        prev_fast = self.fast_sma[i - 1]
        prev_slow = self.slow_sma[i - 1]
        curr_fast = self.fast_sma[i]
        curr_slow = self.slow_sma[i]

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return {"action": "buy"}
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            return {"action": "sell"}
        return {"action": None}

    @property
    def name(self) -> str:
        return self._name


class MACDStrategy:
    """MACD Crossover Strategy.

    Configurable params:
        fast (int):    fast EMA period (default: 12)
        slow (int):    slow EMA period (default: 26)
        signal (int):  signal line period (default: 9)
    Signal logic:
        BUY  when MACD line crosses above signal line
        SELL when MACD line crosses below signal line
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.fast = int(kwargs.get("fast", 12))
        self.slow = int(kwargs.get("slow", 26))
        self.signal_period = int(kwargs.get("signal", 9))
        self._name = f"MACD({self.fast},{self.slow},{self.signal_period})"

        closes = data["close"].values.astype(float)
        self.macd_line, self.signal_line = self._compute_macd(
            closes, self.fast, self.slow, self.signal_period
        )

    @staticmethod
    def _ema(arr: np.ndarray, period: int) -> np.ndarray:
        out = np.full_like(arr, np.nan)
        if len(arr) < period:
            return out
        k = 2.0 / (period + 1)
        out[period - 1] = np.mean(arr[:period])
        for j in range(period, len(arr)):
            out[j] = arr[j] * k + out[j - 1] * (1 - k)
        return out

    def _compute_macd(self, closes: np.ndarray, fast: int, slow: int, signal: int):
        ema_fast = self._ema(closes, fast)
        ema_slow = self._ema(closes, slow)
        macd = ema_fast - ema_slow
        # Signal EMA — skip NaN region in macd before computing
        first_valid = np.where(~np.isnan(macd))[0]
        if len(first_valid) == 0:
            return macd, np.full_like(macd, np.nan)
        start = first_valid[0]
        sig = np.full_like(macd, np.nan)
        if len(macd) - start >= signal:
            k = 2.0 / (signal + 1)
            sig[start + signal - 1] = np.nanmean(macd[start:start + signal])
            for j in range(start + signal, len(macd)):
                sig[j] = macd[j] * k + sig[j - 1] * (1 - k)
        return macd, sig

    def next(self, i: int) -> dict:
        if i < max(self.fast, self.slow) + self.signal_period + 1:
            return {"action": None}  # Warmup: need ema_fast + ema_slow + signal_line all stable
        if np.isnan(self.macd_line[i]) or np.isnan(self.signal_line[i]):
            return {"action": None}

        prev_macd = self.macd_line[i - 1]
        prev_sig = self.signal_line[i - 1]
        curr_macd = self.macd_line[i]
        curr_sig = self.signal_line[i]

        if prev_macd <= prev_sig and curr_macd > curr_sig:
            return {"action": "buy"}
        elif prev_macd >= prev_sig and curr_macd < curr_sig:
            return {"action": "sell"}
        return {"action": None}

    @property
    def name(self) -> str:
        return self._name


class BollingerBandsStrategy:
    """Bollinger Bands Mean Reversion / Breakout Strategy.

    Configurable params:
        period (int):    SMA period (default: 20)
        std_dev (float): number of standard deviations (default: 2.0)
        rsi_oversold (int):    RSI threshold for oversold (default: 30)
        rsi_overbought (int):  RSI threshold for overbought (default: 70)
    Signal logic:
        BUY  when close touches below lower band AND RSI < oversold
        SELL when close touches above upper band AND RSI > overbought
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.period = int(kwargs.get("period", 20))
        self.std_dev = float(kwargs.get("std_dev", 2.0))
        self.rsi_oversold = int(kwargs.get("rsi_oversold", 30))
        self.rsi_overbought = int(kwargs.get("rsi_overbought", 70))
        self._name = f"BB({self.period},{self.std_dev})"

        closes = data["close"].values.astype(float)
        self.middle, self.upper, self.lower = self._compute_bands(closes, self.period, self.std_dev)
        self.rsi = self._compute_rsi(closes, self.period)

    @staticmethod
    def _sma(arr: np.ndarray, period: int) -> np.ndarray:
        out = np.full_like(arr, np.nan)
        if len(arr) < period:
            return out
        cumsum = np.cumsum(arr)
        out[period - 1] = cumsum[period - 1] / period
        out[period:] = (cumsum[period:] - cumsum[:-period]) / period
        return out

    @staticmethod
    def _std(arr: np.ndarray, period: int, mean: np.ndarray) -> np.ndarray:
        out = np.full_like(arr, np.nan)
        for i in range(period - 1, len(arr)):
            out[i] = np.std(arr[i - period + 1 : i + 1])
        return out

    def _compute_bands(self, closes, period, std_dev):
        middle = self._sma(closes, period)
        std = self._std(closes, period, middle)
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        return middle, upper, lower

    @staticmethod
    def _compute_rsi(closes: np.ndarray, period: int) -> np.ndarray:
        out = np.full_like(closes, np.nan)
        if len(closes) < period + 1:
            return out
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        if avg_loss == 0:
            out[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[period] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(period + 1, len(closes)):
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
            if avg_loss == 0:
                out[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                out[i] = 100.0 - (100.0 / (1.0 + rs))
        return out

    def next(self, i: int) -> dict:
        if i < self.period + 2:
            return {"action": None}
        if np.isnan(self.upper[i]) or np.isnan(self.lower[i]) or np.isnan(self.rsi[i]):
            return {"action": None}

        close = self.data["close"].values.astype(float)[i]

        if close <= self.lower[i] and self.rsi[i] < self.rsi_oversold:
            return {"action": "buy"}
        elif close >= self.upper[i] and self.rsi[i] > self.rsi_overbought:
            return {"action": "sell"}
        return {"action": None}

    @property
    def name(self) -> str:
        return self._name


class VolatilityBreakoutStrategy:
    """Volatility Breakout Strategy.

    Configurable params:
        lookback (int):    ATR lookback period (default: 14)
        mult (float):      ATR multiplier for breakout level (default: 2.0)
    Signal logic:
        BUY  when close breaks above (high + mult * ATR) of lookback period
        SELL when close breaks below (low - mult * ATR) of lookback period
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.lookback = int(kwargs.get("lookback", 14))
        self.mult = float(kwargs.get("mult", 2.0))
        self._name = f"VolBreak({self.lookback},{self.mult})"

        highs = data["high"].values.astype(float)
        lows = data["low"].values.astype(float)
        closes = data["close"].values.astype(float)
        self.atr = self._compute_atr(highs, lows, closes, self.lookback)

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
        atr[period] = np.nanmean(tr[1 : period + 1])
        for i in range(period + 1, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        return atr

    def next(self, i: int) -> dict:
        if i < self.lookback + 2 or np.isnan(self.atr[i]):
            return {"action": None}

        high = self.data["high"].values.astype(float)
        low = self.data["low"].values.astype(float)
        close = self.data["close"].values.astype(float)

        upper_band = high[i] + self.mult * self.atr[i]
        lower_band = low[i] - self.mult * self.atr[i]

        if close[i] > upper_band:
            return {"action": "buy"}
        elif close[i] < lower_band:
            return {"action": "sell"}
        return {"action": None}

    @property
    def name(self) -> str:
        return self._name


class GoldPhoenixStrategy:
    """Gold Phoenix — Asian-session breakout with ADX filter.

    Configurable params:
        adx_threshold (float):  ADX value above which trend is strong (default: 26.0)
        asian_range_bars (int): number of bars to define Asian range (default: 6)
    Signal logic:
        BUY when price breaks above Asian session high with ADX > threshold
        SELL when price breaks below Asian session low with ADX > threshold
    """

    def __init__(self, data: pd.DataFrame, **kwargs):
        self.data = data
        self.adx_threshold = float(kwargs.get("adx_threshold", 26.0))
        self.asian_bars = int(kwargs.get("asian_range_bars", 6))
        self._name = f"GoldPhoenix(ADX>{self.adx_threshold})"

        highs = data["high"].values.astype(float)
        lows = data["low"].values.astype(float)
        closes = data["close"].values.astype(float)
        self.adx = self._compute_adx(highs, lows, closes, 14)

    @staticmethod
    def _compute_adx(highs, lows, closes, period):
        # Directional Movement
        up = np.full_like(highs, np.nan)
        down = np.full_like(lows, np.nan)
        for i in range(1, len(highs)):
            up[i] = highs[i] - highs[i - 1]
            down[i] = lows[i - 1] - lows[i]

        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        # True Range
        tr = np.full_like(highs, np.nan)
        for i in range(1, len(highs)):
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

        # Smoothed
        def smooth(arr, period):
            out = np.full_like(arr, np.nan)
            if len(arr) < period:
                return out
            out[period] = np.nansum(arr[1 : period + 1])
            for i in range(period + 1, len(arr)):
                out[i] = out[i - 1] - out[i - 1] / period + arr[i]
            return out

        tr_smooth = smooth(tr, period)
        plus_smooth = smooth(plus_dm, period)
        minus_smooth = smooth(minus_dm, period)

        plus_di = 100 * plus_smooth / tr_smooth
        minus_di = 100 * minus_smooth / tr_smooth

        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = smooth(dx, period)
        return adx

    def next(self, i: int) -> dict:
        if i < 14 + self.asian_bars + 2 or np.isnan(self.adx[i]):
            return {"action": None}

        highs = self.data["high"].values.astype(float)
        lows = self.data["low"].values.astype(float)
        close = self.data["close"].values.astype(float)

        if self.adx[i] < self.adx_threshold:
            return {"action": None}

        # Asian session range (first N bars of the day)
        if self.asian_bars > 0 and i >= self.asian_bars:
            asian_high = np.max(highs[i - self.asian_bars : i])
            asian_low = np.min(lows[i - self.asian_bars : i])

            if close[i] > asian_high:
                return {"action": "buy", "asian_high": float(asian_high), "asian_low": float(asian_low)}
            elif close[i] < asian_low:
                return {"action": "sell", "asian_high": float(asian_high), "asian_low": float(asian_low)}

        return {"action": None}

    @property
    def name(self) -> str:
        return self._name


class PineScriptStrategy:
    """Pine Script strategy — translated from .pine files to local backtester.

    Uses EMA crossover + ADX > threshold + RSI > min for long entries.
    Conforms to the same interface as other built-in strategies (next, name, __init__).

    Configurable params:
        fast_ema (int):   fast EMA period (default: 5)
        slow_ema (int):   slow EMA period (default: 13)
        adx_len (int):    ADX lookback period (default: 14)
        adx_thresh (int): ADX threshold for trending market (default: 15)
        rsi_len (int):    RSI lookback period (default: 14)
        rsi_min (int):    RSI minimum for long entry (default: 50)
        tp_ratio (float): take-profit multiple of ATR (default: 1.0)
        sl_ratio (float): stop-loss multiple of ATR (default: 1.5)
    Signal logic:
        BUY when fast EMA crosses above slow EMA
             AND ADX > threshold
             AND RSI > minimum
    """

    def __init__(self, data: pd.DataFrame, fast_ema: int = 5, slow_ema: int = 13,
                 adx_len: int = 14, adx_thresh: int = 15,
                 rsi_len: int = 14, rsi_min: int = 50,
                 tp_ratio: float = 1.0, sl_ratio: float = 1.5):
        self.data = data
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.adx_len = adx_len
        self.adx_thresh = adx_thresh
        self.rsi_len = rsi_len
        self.rsi_min = rsi_min
        self.tp_ratio = tp_ratio
        self.sl_ratio = sl_ratio
        self._name = f"PineScript(EMA{fast_ema}_{slow_ema}_ADX{adx_len}_{adx_thresh}_RSI{rsi_len}_{rsi_min})"
        self._in_position = False  # Track open position state for exit signals

        closes = data["close"].values.astype(float)
        highs = data["high"].values.astype(float)
        lows = data["low"].values.astype(float)

        # EMA via pandas ewm
        self.ema_fast = data["close"].ewm(span=fast_ema, adjust=False).mean().values
        self.ema_slow = data["close"].ewm(span=slow_ema, adjust=False).mean().values

        # RSI & ADX
        self.rsi_arr = self._compute_rsi(closes, rsi_len)
        self.adx_arr = self._compute_adx(highs, lows, closes, adx_len)

    # ── Classmethod: parse .pine file ──────────────────────────────────────

    @classmethod
    def from_pine_file(cls, pine_path: str, data: pd.DataFrame) -> "PineScriptStrategy":
        """Parse a .pine file, extract strategy inputs, return a configured instance.

        Handles both styles seen in the iter_*.pine files:
            var_name = input.int(5, "Label", ...)
            input.int(5, "Label", ...)
        Maps variable names and labels to the PineScriptStrategy parameter names.
        """
        with open(pine_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract variable-name + default-value from both input.int and input.float
        # Pattern: varName = input.int(DEFAULT, "LABEL" ...
        # Pattern: varName = input.float(DEFAULT, "LABEL" ...
        raw_params: dict[str, int | float] = {}

        for m in re.finditer(
            r"(\w+)\s*=\s*input\.int\s*\(\s*(\d+)\s*,\s*\"([^\"]+)\"",
            content,
        ):
            raw_params[m.group(1)] = int(m.group(2))
            raw_params[m.group(3)] = int(m.group(2))  # also store by label

        for m in re.finditer(
            r"(\w+)\s*=\s*input\.float\s*\(\s*([\d.]+)\s*,\s*\"([^\"]+)\"",
            content,
        ):
            raw_params[m.group(1)] = float(m.group(2))
            raw_params[m.group(3)] = float(m.group(2))

        for m in re.finditer(
            r"input\.int\s*\(\s*(\d+)\s*,\s*\"([^\"]+)\"",
            content,
        ):
            raw_params[m.group(2)] = int(m.group(1))

        for m in re.finditer(
            r"input\.float\s*\(\s*([\d.]+)\s*,\s*\"([^\"]+)\"",
            content,
        ):
            raw_params[m.group(2)] = float(m.group(1))

        # Fuzzy mapping from .pine identifiers → PineScriptStrategy kwargs
        # Compiled from ALL 168 iter_*.pine files to cover every naming convention
        mapping: dict[str, list[str]] = {
            "fast_ema": [
                "fast_len", "fastLen", "ema_fast_len", "emaFastLen",
                "ema_fast", "emaFast", "fastLength", "fast_length",
                "emaLength1", "fastLength", "fast",
                "Fast EMA Length", "EMA Fast Length",
            ],
            "slow_ema": [
                "slow_len", "slowLen", "ema_slow_len", "emaSlowLen",
                "ema_slow", "emaSlow", "slowLength", "slow_length",
                "emaLength2", "slowLength",
                "Slow EMA Length", "EMA Slow Length",
            ],
            "adx_len": [
                "adx_len", "adxLen", "adx_length", "adxLength",
                "dmi_len", "diLength", "adxPeriod", "adx_period",
                "ADX Length",
            ],
            "adx_thresh": [
                "adx_threshold", "adxThreshold", "adx_thresh", "adxThresh",
                "adx_min", "adxMin", "adxMin",
                "ADX Threshold", "ADX Minimum (Trending)",
            ],
            "rsi_len": [
                "rsi_len", "rsiLen", "rsi_length", "rsiLength",
                "rsiPeriod", "rsi_period", "rsiLen",
                "RSI Length",
            ],
            "rsi_min": [
                "rsi_min", "rsiMin", "rsi_threshold", "rsiThreshold",
                "rsi_thresh", "rsiThresh", "rsiLongMin", "rsi_long_min",
                "rsiLongThresh", "rsiMinLong", "rsi_entry_threshold",
                "rsiThresh", "rsiMin",
                "RSI Minimum (Long Only)", "RSI Minimum (long)",
                "RSI Threshold (min for long)", "RSI Long Threshold",
            ],
            "tp_ratio": [
                "tp_ratio", "tpRatio", "tp_sl_ratio", "tpSlRatio",
                "tp_mult", "tpMult", "tpMulti", "tpMultiplier",
                "tp_atr_mult", "tpATRMult", "tpAtrMultiplier",
                "tpPoints", "tp_points", "targetDist",
                "Take Profit (R)", "Take Profit (×ATR)",
            ],
            "sl_ratio": [
                "sl_ratio", "slRatio", "sl_atr_mult", "slAtrMult",
                "slMulti", "slMultiplier", "slMult",
                "slPct", "sl_pct", "sl_percent",
                "slPoints", "sl_points",
                "slAtrMultiplier", "slATRMult", "slMultiplier",
                "Stop Loss (R)", "Stop Loss (×ATR)",
            ],
        }

        kwargs: dict[str, object] = {}
        for our_key, aliases in mapping.items():
            for alias in aliases:
                val = raw_params.get(alias)
                if val is not None:
                    kwargs[our_key] = val
                    break

        return cls(data, **kwargs)

    # ── Indicator computations ────────────────────────────────────────────

    @staticmethod
    def _compute_rsi(closes: np.ndarray, period: int) -> np.ndarray:
        """Wilder-style RSI."""
        out = np.full_like(closes, np.nan)
        if len(closes) < period + 1:
            return out
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = float(np.mean(gains[:period]))
        avg_loss = float(np.mean(losses[:period]))
        if avg_loss == 0:
            out[period] = 100.0
        else:
            out[period] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        for i in range(period + 1, len(closes)):
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
            if avg_loss == 0:
                out[i] = 100.0
            else:
                out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        return out

    @staticmethod
    def _compute_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> np.ndarray:
        """Standard DMI-based ADX calculation."""
        up = np.full_like(highs, np.nan)
        down = np.full_like(lows, np.nan)
        for i in range(1, len(highs)):
            up[i] = highs[i] - highs[i - 1]
            down[i] = lows[i - 1] - lows[i]

        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)

        tr = np.full_like(highs, np.nan)
        for i in range(1, len(highs)):
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )

        def _smooth(arr, per):
            out = np.full_like(arr, np.nan)
            if len(arr) < per:
                return out
            out[per] = np.nansum(arr[1 : per + 1])
            for j in range(per + 1, len(arr)):
                out[j] = out[j - 1] - out[j - 1] / per + arr[j]
            return out

        tr_s = _smooth(tr, period)
        plus_s = _smooth(plus_dm, period)
        minus_s = _smooth(minus_dm, period)

        pdi = 100.0 * plus_s / tr_s
        mdi = 100.0 * minus_s / tr_s
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi + 1e-10)
        return _smooth(dx, period)

    # ── Signal logic ──────────────────────────────────────────────────────

    def next(self, i: int) -> dict:
        """Return signal dict for bar i.

        BUY when fast EMA crosses above slow EMA AND ADX > threshold AND RSI > min.
        SELL (exit long) when fast EMA crosses below slow EMA to close the position.
        Uses self._in_position to ensure SELL only triggers when a position is open.
        """
        min_idx = max(self.fast_ema, self.slow_ema, self.adx_len, self.rsi_len)
        if i < min_idx:
            return {"action": None}
        if (
            np.isnan(self.ema_fast[i])
            or np.isnan(self.ema_slow[i])
            or np.isnan(self.adx_arr[i])
            or np.isnan(self.rsi_arr[i])
        ):
            return {"action": None}

        prev_fast = self.ema_fast[i - 1]
        prev_slow = self.ema_slow[i - 1]
        curr_fast = self.ema_fast[i]
        curr_slow = self.ema_slow[i]

        # Exit signal: fast EMA crosses below slow EMA (reverse of entry)
        if self._in_position and prev_fast >= prev_slow and curr_fast < curr_slow:
            self._in_position = False
            return {"action": "sell"}

        # Entry signal: fast EMA crosses above slow EMA + ADX + RSI filter
        if (
            not self._in_position
            and prev_fast <= prev_slow
            and curr_fast > curr_slow
            and self.adx_arr[i] > self.adx_thresh
            and self.rsi_arr[i] > self.rsi_min
        ):
            self._in_position = True
            return {"action": "buy"}

        return {"action": None}

    @property
    def name(self) -> str:
        return self._name


# ── Registry: maps strategy keys → classes ─────────────────────────────────
BUILTIN_STRATEGIES: dict[str, type] = {
    "sma_crossover": SMAStrategy,
    "macd_crossover": MACDStrategy,
    "bollinger_bands": BollingerBandsStrategy,
    "volatility_breakout": VolatilityBreakoutStrategy,
    "gold_phoenix": GoldPhoenixStrategy,
    "propfirm_pass": PropfirmPassStrategy,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Discovery
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_strategy_key(script_name: str) -> Optional[str]:
    """Map a run_*.py script name to a strategy key.

    run_macd.py         → macd_crossover
    run_sma.py          → sma_crossover
    run_bollinger.py    → bollinger_bands
    run_volatility_breakout.py → volatility_breakout
    """
    name = script_name.replace("run_", "").replace(".py", "").lower().replace("-", "_")
    mapping = {
        "macd": "macd_crossover",
        "sma": "sma_crossover",
        "bollinger": "bollinger_bands",
        "volatility_breakout": "volatility_breakout",
        "gold_phoenix": "gold_phoenix",
    }
    return mapping.get(name, name)


def list_strategies() -> dict[str, type]:
    """Scan C:\\Trading\\bots\\active_bots\\ for bot scripts and return
    a dict of {strategy_key: strategy_class}.

    Scans all subdirectories under active_bots/ for run_*.py files.
    Deduplicates by strategy key — first unique key wins.
    Falls back to the built-in strategy classes for known keys.
    """
    strategies: dict[str, type] = {}

    if not BOTS_DIR.is_dir():
        logger.warning("Bots directory not found: %s", BOTS_DIR)
        return dict(BUILTIN_STRATEGIES)  # fallback to built-ins

    for pair_dir in sorted(BOTS_DIR.iterdir()):
        if not pair_dir.is_dir():
            continue
        for fpath in sorted(pair_dir.glob("run_*.py")):
            key = _extract_strategy_key(fpath.name)
            if key is None:
                continue
            if key not in strategies:
                # Use built-in class if known, otherwise register the script path
                if key in BUILTIN_STRATEGIES:
                    strategies[key] = BUILTIN_STRATEGIES[key]
                    logger.debug("Registered strategy %r from %s", key, fpath)
                else:
                    # Unknown key — try to dynamically import the script
                    cls = _import_strategy_class(fpath, key)
                    if cls:
                        strategies[key] = cls

    # Ensure all built-in strategies are available even if no bot scripts found
    for key, cls in BUILTIN_STRATEGIES.items():
        if key not in strategies:
            strategies[key] = cls

    logger.info("Discovered %d strategies: %s", len(strategies), list(strategies.keys()))
    return strategies


def _import_strategy_class(fpath: Path, key: str) -> Optional[type]:
    """Try to dynamically import a strategy class from a bot script file."""
    try:
        module_name = f"bot_{key}"
        spec = importlib.util.spec_from_file_location(module_name, fpath)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Look for a class with a name containing "Strategy"
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if isinstance(attr, type) and "Strategy" in attr_name:
                return attr
        return None
    except Exception as exc:
        logger.debug("Could not import %s from %s: %s", key, fpath, exc)
        return None


def get_strategy(key: str) -> Optional[type]:
    """Get a single strategy class by key. Returns None if not found."""
    return list_strategies().get(key)
