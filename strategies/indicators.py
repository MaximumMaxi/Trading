"""
strategies/indicators.py — compute the full feature set once.

The router calls add_features() on each symbol's H1 frame; every sub-strategy
then just reads the columns it needs. Regime columns are added separately by
regime.detector.add_regime (which also provides atr/adx used here).
"""

import numpy as np
import pandas as pd


def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(s: pd.Series, fast=12, slow=26, signal=9):
    line = ema(s, fast) - ema(s, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach all strategy indicators. Does not drop rows."""
    out = df.copy()
    c = out["close"]

    # trend / structure
    out["ema20"] = ema(c, 20)
    out["ema50"] = ema(c, 50)
    out["ema200"] = ema(c, 200)

    # oscillators
    out["rsi"] = rsi(c, 14)
    _, _, out["macd_hist"] = macd(c)
    out["roc"] = c.pct_change(10) * 100     # 10-bar rate of change

    # Bollinger Bands (20, 2σ) for mean reversion
    mid = c.rolling(20).mean()
    std = c.rolling(20).std()
    out["bb_mid"] = mid
    out["bb_upper"] = mid + 2 * std
    out["bb_lower"] = mid - 2 * std

    # Donchian channels (prior 20 bars, excludes current) for breakout
    out["donch_high"] = out["high"].rolling(20).max().shift(1)
    out["donch_low"] = out["low"].rolling(20).min().shift(1)

    # previous-bar helpers
    out["close_prev"] = c.shift(1)
    out["low_prev"] = out["low"].shift(1)
    out["high_prev"] = out["high"].shift(1)
    out["ema20_prev"] = out["ema20"].shift(1)
    out["ema50_prev"] = out["ema50"].shift(1)
    return out
