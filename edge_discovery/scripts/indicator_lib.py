#!/usr/bin/env python3
"""
Indicator Library — numpy-vectorized technical indicators.
All functions return signal arrays: 1 = long, -1 = short, 0 = neutral.
"""

from __future__ import annotations
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from typing import Tuple, Optional


# ============================================================================
# Utility functions
# ============================================================================

def rolling_window(arr: np.ndarray, window: int) -> np.ndarray:
    """Fast rolling window view (no data copy)."""
    return sliding_window_view(arr, window_shape=window)


def sma(arr: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average — returns same length as input (NaN-padded)."""
    result = np.full_like(arr, np.nan)
    if len(arr) < period:
        return result
    windows = rolling_window(arr, period)
    result[period - 1:] = np.mean(windows, axis=1)
    return result


def ema(arr: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    result = np.full_like(arr, np.nan)
    if len(arr) < period:
        return result
    alpha = 2.0 / (period + 1)
    result[period - 1] = np.mean(arr[:period])  # seed
    for i in range(period, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
    return result


def wma(arr: np.ndarray, period: int) -> np.ndarray:
    """Weighted moving average (linear weights)."""
    result = np.full_like(arr, np.nan)
    if len(arr) < period:
        return result
    weights = np.arange(1, period + 1, dtype=float)
    weights /= weights.sum()
    windows = rolling_window(arr, period)
    result[period - 1:] = np.dot(windows, weights)
    return result


def hma(arr: np.ndarray, period: int) -> np.ndarray:
    """Hull Moving Average."""
    half = int(period / 2)
    sqrt = int(np.sqrt(period))
    wma_half = wma(arr, half)
    wma_full = wma(arr, period)
    raw = 2 * wma_half - wma_full
    return wma(raw, sqrt)


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True Range."""
    tr = np.full_like(close, np.nan)
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1])
        )
    )
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range."""
    tr = true_range(high, low, close)
    return ema(tr, period)


def stddev(arr: np.ndarray, period: int, ddof: int = 0) -> np.ndarray:
    """Rolling standard deviation."""
    result = np.full_like(arr, np.nan)
    if len(arr) < period:
        return result
    windows = rolling_window(arr, period)
    result[period - 1:] = np.std(windows, axis=1, ddof=ddof)
    return result


def highest(arr: np.ndarray, period: int) -> np.ndarray:
    """Rolling highest value."""
    result = np.full_like(arr, np.nan)
    if len(arr) < period:
        return result
    windows = rolling_window(arr, period)
    result[period - 1:] = np.max(windows, axis=1)
    return result


def lowest(arr: np.ndarray, period: int) -> np.ndarray:
    """Rolling lowest value."""
    result = np.full_like(arr, np.nan)
    if len(arr) < period:
        return result
    windows = rolling_window(arr, period)
    result[period - 1:] = np.min(windows, axis=1)
    return result


def cross_over(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cross over: a crossed above b. Returns 0/1 array."""
    result = np.zeros(len(a), dtype=int)
    if len(a) < 2:
        return result
    result[1:] = ((a[:-1] <= b[:-1]) & (a[1:] > b[1:])).astype(int)
    return result


def cross_under(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cross under: a crossed below b. Returns 0/1 array."""
    result = np.zeros(len(a), dtype=int)
    if len(a) < 2:
        return result
    result[1:] = ((a[:-1] >= b[:-1]) & (a[1:] < b[1:])).astype(int)
    return result


# ============================================================================
# Trend Indicators
# ============================================================================

def signal_sma_cross(close: np.ndarray, params: dict) -> np.ndarray:
    """SMA fast/slow cross."""
    fast = sma(close, params["fast"])
    slow = sma(close, params["slow"])
    signals = np.zeros(len(close), dtype=int)
    # Long: fast > slow
    valid = ~(np.isnan(fast) | np.isnan(slow))
    signals[valid & (fast > slow)] = 1
    signals[valid & (fast < slow)] = -1
    return signals


def signal_ema_cross(close: np.ndarray, params: dict) -> np.ndarray:
    """EMA fast/slow cross."""
    fast = ema(close, params["fast"])
    slow = ema(close, params["slow"])
    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(fast) | np.isnan(slow))
    signals[valid & (fast > slow)] = 1
    signals[valid & (fast < slow)] = -1
    return signals


def signal_wma_cross(close: np.ndarray, params: dict) -> np.ndarray:
    """WMA fast/slow cross."""
    fast = wma(close, params["fast"])
    slow = wma(close, params["slow"])
    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(fast) | np.isnan(slow))
    signals[valid & (fast > slow)] = 1
    signals[valid & (fast < slow)] = -1
    return signals


def signal_hma_cross(close: np.ndarray, params: dict) -> np.ndarray:
    """HMA fast/slow cross."""
    fast = hma(close, params["fast"])
    slow = hma(close, params["slow"])
    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(fast) | np.isnan(slow))
    signals[valid & (fast > slow)] = 1
    signals[valid & (fast < slow)] = -1
    return signals


def signal_price_vs_ma(close: np.ndarray, params: dict) -> np.ndarray:
    """Price vs MA band — close above/below MA by threshold%."""
    ma = sma(close, params["period"])
    threshold = params.get("threshold", 0.02)  # 2% default
    signals = np.zeros(len(close), dtype=int)
    valid = ~np.isnan(ma)
    deviation = (close - ma) / ma
    signals[valid & (deviation > threshold)] = -1  # Overextended short
    signals[valid & (deviation < -threshold)] = 1   # Overextended long
    return signals


# ============================================================================
# Momentum Indicators
# ============================================================================

def signal_rsi(close: np.ndarray, params: dict) -> np.ndarray:
    """RSI — oversold = long, overbought = short."""
    period = params["period"]
    ob = params.get("overbought", 70)
    os = params.get("oversold", 30)

    rsi = np.full_like(close, np.nan)
    if len(close) < period + 1:
        return np.zeros(len(close), dtype=int)

    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.full_like(close, np.nan)
    avg_loss = np.full_like(close, np.nan)
    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])

    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

    rs = avg_gain / np.maximum(avg_loss, 1e-10)
    rsi = 100 - (100 / (1 + rs))

    signals = np.zeros(len(close), dtype=int)
    valid = ~np.isnan(rsi)
    signals[valid & (rsi < os)] = 1
    signals[valid & (rsi > ob)] = -1
    return signals


def signal_stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      params: dict) -> np.ndarray:
    """Stochastic Oscillator."""
    k_period = params.get("k_period", 14)
    d_period = params.get("d_period", 3)
    ob = params.get("overbought", 80)
    os = params.get("oversold", 20)

    highest_high = highest(high, k_period)
    lowest_low = lowest(low, k_period)

    k_raw = np.full_like(close, np.nan)
    denom = highest_high - lowest_low
    valid = denom > 0
    k_raw[valid] = (close[valid] - lowest_low[valid]) / denom[valid] * 100

    k = sma(k_raw, d_period)  # Smooth K with SMA of period D
    d = sma(k, d_period)

    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(k) | np.isnan(d))
    signals[valid & (k < os)] = 1
    signals[valid & (k > ob)] = -1
    signals[valid & cross_over(k, d)] = 1  # Bullish cross
    signals[valid & cross_under(k, d)] = -1  # Bearish cross
    return signals


def signal_macd(close: np.ndarray, params: dict) -> np.ndarray:
    """MACD — signal line cross."""
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)
    signal = params.get("signal", 9)

    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)

    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(macd_line) | np.isnan(signal_line))
    # Crosses
    signals[valid & cross_over(macd_line, signal_line)] = 1
    signals[valid & cross_under(macd_line, signal_line)] = -1
    # Also signal on histogram zero cross
    histogram = macd_line - signal_line
    signals[valid & cross_over(histogram, np.zeros_like(histogram))] = 1
    signals[valid & cross_under(histogram, np.zeros_like(histogram))] = -1
    return signals


def signal_cci(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               params: dict) -> np.ndarray:
    """Commodity Channel Index."""
    period = params.get("period", 14)
    ob = params.get("overbought", 100)
    os = params.get("oversold", -100)

    tp = (high + low + close) / 3
    tp_sma = sma(tp, period)
    mad = sma(np.abs(tp - tp_sma), period)  # Mean absolute deviation
    cci = np.full_like(close, np.nan)
    valid = mad > 0
    cci[valid] = (tp[valid] - tp_sma[valid]) / (0.015 * mad[valid])

    signals = np.zeros(len(close), dtype=int)
    valid = ~np.isnan(cci)
    signals[valid & (cci < os)] = 1
    signals[valid & (cci > ob)] = -1
    return signals


def signal_williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      params: dict) -> np.ndarray:
    """Williams %R."""
    period = params.get("period", 14)
    ob = params.get("overbought", -20)
    os = params.get("oversold", -80)

    hh = highest(high, period)
    ll = lowest(low, period)
    wr = np.full_like(close, np.nan)
    denom = hh - ll
    valid = denom > 0
    wr[valid] = (hh[valid] - close[valid]) / denom[valid] * -100

    signals = np.zeros(len(close), dtype=int)
    valid = ~np.isnan(wr)
    signals[valid & (wr < os)] = 1
    signals[valid & (wr > ob)] = -1
    return signals


# ============================================================================
# Volatility Indicators
# ============================================================================

def signal_bollinger_bands(close: np.ndarray, params: dict) -> np.ndarray:
    """Bollinger Bands — touch lower = long, touch upper = short (reversion)."""
    period = params.get("period", 20)
    n_std = params.get("num_std", 2.0)

    middle = sma(close, period)
    std = stddev(close, period)
    upper = middle + n_std * std
    lower = middle - n_std * std

    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(upper) | np.isnan(lower))
    signals[valid & (close <= lower)] = 1
    signals[valid & (close >= upper)] = -1
    return signals


def signal_keltner(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                   params: dict) -> np.ndarray:
    """Keltner Channels."""
    period = params.get("period", 20)
    mult = params.get("multiplier", 1.5)

    middle = ema(close, period)
    atr_val = atr(high, low, close, period)
    upper = middle + mult * atr_val
    lower = middle - mult * atr_val

    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(upper) | np.isnan(lower))
    signals[valid & (close <= lower)] = 1
    signals[valid & (close >= upper)] = -1
    return signals


def signal_atr_breakout(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                        params: dict) -> np.ndarray:
    """ATR-based breakout — price moves > N × ATR."""
    period = params.get("period", 14)
    mult = params.get("multiplier", 2.0)

    atr_val = atr(high, low, close, period)
    signals = np.zeros(len(close), dtype=int)
    valid = ~np.isnan(atr_val)

    # Measure move from previous close
    move = np.abs(close - np.roll(close, 1))
    breakout = move > mult * atr_val

    signals[valid & breakout & (close > np.roll(close, 1))] = 1  # bullish breakout
    signals[valid & breakout & (close < np.roll(close, 1))] = -1  # bearish breakout
    return signals


# ============================================================================
# Trend Strength Indicators
# ============================================================================

def signal_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               params: dict) -> np.ndarray:
    """ADX/DMI — trend strength + direction."""
    period = params.get("period", 14)
    threshold = params.get("threshold", 25)

    # +DM, -DM
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    pos_dm[0] = 0
    neg_dm[0] = 0

    atr_val = atr(high, low, close, period)
    di_pos = 100 * ema(pos_dm, period) / np.maximum(atr_val, 1e-10)
    di_neg = 100 * ema(neg_dm, period) / np.maximum(atr_val, 1e-10)
    dx = 100 * np.abs(di_pos - di_neg) / np.maximum(di_pos + di_neg, 1e-10)
    adx_val = ema(dx, period)

    signals = np.zeros(len(close), dtype=int)
    valid = ~(np.isnan(adx_val) | np.isnan(di_pos) | np.isnan(di_neg))
    signals[valid & (adx_val > threshold) & (di_pos > di_neg)] = 1
    signals[valid & (adx_val > threshold) & (di_neg > di_pos)] = -1
    return signals


def signal_aroon(high: np.ndarray, low: np.ndarray, params: dict) -> np.ndarray:
    """Aroon — trend direction strength."""
    period = params.get("period", 14)

    aroon_up = np.full(len(high), np.nan)
    aroon_down = np.full(len(low), np.nan)

    for i in range(period, len(high)):
        idx_h = np.argmax(high[i - period + 1:i + 1])
        idx_l = np.argmin(low[i - period + 1:i + 1])
        aroon_up[i] = (period - idx_h) / period * 100
        aroon_down[i] = (period - idx_l) / period * 100

    signals = np.zeros(len(high), dtype=int)
    valid = ~(np.isnan(aroon_up) | np.isnan(aroon_down))
    signals[valid & (aroon_up > 70) & (aroon_up > aroon_down)] = 1
    signals[valid & (aroon_down > 70) & (aroon_down > aroon_up)] = -1
    return signals


# ============================================================================
# Volume Indicators
# ============================================================================

def signal_mfi(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               volume: np.ndarray, params: dict) -> np.ndarray:
    """Money Flow Index."""
    period = params.get("period", 14)
    ob = params.get("overbought", 80)
    os = params.get("oversold", 20)

    tp = (high + low + close) / 3
    mf = tp * volume

    pos_mf = np.where(tp > np.roll(tp, 1), mf, 0)
    neg_mf = np.where(tp < np.roll(tp, 1), mf, 0)
    pos_mf[0] = 0
    neg_mf[0] = 0

    pos_sum = sma(pos_mf, period) * period
    neg_sum = sma(neg_mf, period) * period
    mfr = pos_sum / np.maximum(neg_sum, 1e-10)
    mfi_val = 100 - (100 / (1 + mfr))

    signals = np.zeros(len(close), dtype=int)
    valid = ~np.isnan(mfi_val)
    signals[valid & (mfi_val < os)] = 1
    signals[valid & (mfi_val > ob)] = -1
    return signals


# ============================================================================
# Indicator Registry
# ============================================================================

INDICATOR_REGISTRY = {
    # Trend
    "SMA_Cross": {
        "func": lambda o, h, l, c, v, p: signal_sma_cross(c, p),
        "params": [
            {"fast": 5, "slow": 20},
            {"fast": 10, "slow": 50},
            {"fast": 20, "slow": 100},
            {"fast": 50, "slow": 200},
        ],
        "description": "SMA fast/slow cross — trend follower",
        "family": "trend",
    },
    "EMA_Cross": {
        "func": lambda o, h, l, c, v, p: signal_ema_cross(c, p),
        "params": [
            {"fast": 5, "slow": 20},
            {"fast": 10, "slow": 50},
            {"fast": 20, "slow": 100},
            {"fast": 50, "slow": 200},
        ],
        "description": "EMA fast/slow cross — trend follower",
        "family": "trend",
    },
    "WMA_Cross": {
        "func": lambda o, h, l, c, v, p: signal_wma_cross(c, p),
        "params": [
            {"fast": 5, "slow": 20},
            {"fast": 10, "slow": 50},
            {"fast": 20, "slow": 100},
        ],
        "description": "WMA fast/slow cross",
        "family": "trend",
    },
    "HMA_Cross": {
        "func": lambda o, h, l, c, v, p: signal_hma_cross(c, p),
        "params": [
            {"fast": 10, "slow": 30},
            {"fast": 20, "slow": 50},
            {"fast": 30, "slow": 100},
        ],
        "description": "Hull MA cross — reduced lag trend",
        "family": "trend",
    },
    "Price_vs_MA": {
        "func": lambda o, h, l, c, v, p: signal_price_vs_ma(c, p),
        "params": [
            {"period": 20, "threshold": 0.02},
            {"period": 50, "threshold": 0.03},
            {"period": 100, "threshold": 0.05},
            {"period": 200, "threshold": 0.08},
        ],
        "description": "Price deviation from SMA — mean reversion",
        "family": "trend",
    },

    # Momentum
    "RSI": {
        "func": lambda o, h, l, c, v, p: signal_rsi(c, p),
        "params": [
            {"period": 7, "oversold": 25, "overbought": 75},
            {"period": 9, "oversold": 25, "overbought": 75},
            {"period": 14, "oversold": 30, "overbought": 70},
            {"period": 14, "oversold": 25, "overbought": 75},
            {"period": 21, "oversold": 30, "overbought": 70},
            {"period": 21, "oversold": 35, "overbought": 65},
        ],
        "description": "RSI oversold/overbought — mean reversion",
        "family": "momentum",
    },
    "Stochastic": {
        "func": lambda o, h, l, c, v, p: signal_stochastic(h, l, c, p),
        "params": [
            {"k_period": 5, "d_period": 3, "oversold": 20, "overbought": 80},
            {"k_period": 8, "d_period": 3, "oversold": 20, "overbought": 80},
            {"k_period": 14, "d_period": 3, "oversold": 20, "overbought": 80},
            {"k_period": 14, "d_period": 5, "oversold": 20, "overbought": 80},
        ],
        "description": "Stochastic K/D cross + levels",
        "family": "momentum",
    },
    "MACD": {
        "func": lambda o, h, l, c, v, p: signal_macd(c, p),
        "params": [
            {"fast": 5, "slow": 13, "signal": 5},
            {"fast": 5, "slow": 21, "signal": 9},
            {"fast": 8, "slow": 17, "signal": 9},
            {"fast": 8, "slow": 21, "signal": 5},
            {"fast": 12, "slow": 26, "signal": 9},
        ],
        "description": "MACD signal line cross — trend momentum",
        "family": "momentum",
    },
    "CCI": {
        "func": lambda o, h, l, c, v, p: signal_cci(h, l, c, p),
        "params": [
            {"period": 10, "oversold": -100, "overbought": 100},
            {"period": 14, "oversold": -100, "overbought": 100},
            {"period": 20, "oversold": -100, "overbought": 100},
        ],
        "description": "CCI extremes — mean reversion",
        "family": "momentum",
    },
    "Williams_R": {
        "func": lambda o, h, l, c, v, p: signal_williams_r(h, l, c, p),
        "params": [
            {"period": 10, "oversold": -80, "overbought": -20},
            {"period": 14, "oversold": -80, "overbought": -20},
            {"period": 21, "oversold": -80, "overbought": -20},
        ],
        "description": "Williams %R extremes",
        "family": "momentum",
    },

    # Volatility
    "Bollinger_Bands": {
        "func": lambda o, h, l, c, v, p: signal_bollinger_bands(c, p),
        "params": [
            {"period": 10, "num_std": 2.0},
            {"period": 20, "num_std": 2.0},
            {"period": 20, "num_std": 2.5},
            {"period": 50, "num_std": 2.0},
            {"period": 50, "num_std": 3.0},
        ],
        "description": "BB touch — volatility mean reversion",
        "family": "volatility",
    },
    "Keltner": {
        "func": lambda o, h, l, c, v, p: signal_keltner(h, l, c, p),
        "params": [
            {"period": 10, "multiplier": 1.5},
            {"period": 20, "multiplier": 1.5},
            {"period": 20, "multiplier": 2.0},
            {"period": 30, "multiplier": 2.0},
        ],
        "description": "Keltner channel touch",
        "family": "volatility",
    },
    "ATR_Breakout": {
        "func": lambda o, h, l, c, v, p: signal_atr_breakout(h, l, c, p),
        "params": [
            {"period": 7, "multiplier": 1.5},
            {"period": 14, "multiplier": 2.0},
            {"period": 14, "multiplier": 2.5},
            {"period": 21, "multiplier": 2.0},
        ],
        "description": "ATR breakout — volatility expansion",
        "family": "volatility",
    },

    # Trend Strength
    "ADX_DMI": {
        "func": lambda o, h, l, c, v, p: signal_adx(h, l, c, p),
        "params": [
            {"period": 7, "threshold": 20},
            {"period": 10, "threshold": 20},
            {"period": 14, "threshold": 25},
            {"period": 14, "threshold": 30},
            {"period": 21, "threshold": 25},
        ],
        "description": "ADX trend strength + DMI direction",
        "family": "trend_strength",
    },
    "Aroon": {
        "func": lambda o, h, l, c, v, p: signal_aroon(h, l, p),
        "params": [
            {"period": 10},
            {"period": 14},
            {"period": 21},
            {"period": 25},
        ],
        "description": "Aroon trend direction",
        "family": "trend_strength",
    },

    # Volume
    "MFI": {
        "func": lambda o, h, l, c, v, p: signal_mfi(h, l, c, v, p),
        "params": [
            {"period": 7, "oversold": 20, "overbought": 80},
            {"period": 14, "oversold": 20, "overbought": 80},
            {"period": 14, "oversold": 30, "overbought": 70},
            {"period": 21, "oversold": 20, "overbought": 80},
        ],
        "description": "MFI — volume-weighted RSI",
        "family": "volume",
    },
}

# Total parameter combinations
TOTAL_COMBOS = sum(len(v["params"]) for v in INDICATOR_REGISTRY.values())
