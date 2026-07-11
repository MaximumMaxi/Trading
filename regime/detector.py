"""
regime/detector.py — classify each bar's market regime.

The regime decides which sub-strategy is allowed to trade:
    TREND_UP / TREND_DOWN  -> trend-following (MA-bounce pullback)
    RANGE                  -> mean-reversion
    VOLATILE               -> breakout (volatility expansion)

Method (pure pandas/numpy, no TA libs):
  * ADX + directional indicators (Wilder) measure *trend strength & direction*.
  * Normalized ATR (natr = ATR / its own rolling median) measures *volatility
    expansion* — a spike means a breakout environment.

Precedence per bar:
  1. VOLATILE  if natr >= vol_expansion            (expansion dominates)
  2. TREND_*   elif adx >= adx_trend               (direction from +DI/-DI)
  3. RANGE     otherwise
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Regime labels
TREND_UP   = "TREND_UP"
TREND_DOWN = "TREND_DOWN"
RANGE      = "RANGE"
VOLATILE   = "VOLATILE"


@dataclass
class RegimeConfig:
    adx_period:    int   = 14
    atr_period:    int   = 14
    natr_lookback: int   = 100    # window for the ATR baseline (rolling median)
    adx_trend:     float = 25.0   # ADX at/above this = trending
    vol_expansion: float = 1.6    # ATR this many x its median = volatile/expansion
    di_spread_min: float = 2.0    # min |+DI - -DI| to assign a trend direction


# ─── Wilder-smoothed indicators ──────────────────────────────────────────────

def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's RMA smoothing (equivalent to ewm alpha = 1/period)."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def compute_adx(df: pd.DataFrame, period: int = 14):
    """Return (adx, plus_di, minus_di, atr) as Series, Wilder-smoothed."""
    up_move   = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm  = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr  = _true_range(df)
    atr = _wilder(tr, period)

    # avoid div-by-zero
    atr_safe = atr.replace(0, np.nan)
    plus_di  = 100 * _wilder(plus_dm, period) / atr_safe
    minus_di = 100 * _wilder(minus_dm, period) / atr_safe

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx  = 100 * (plus_di - minus_di).abs() / di_sum
    adx = _wilder(dx.fillna(0), period)

    return adx, plus_di, minus_di, atr


# ─── Regime classification ────────────────────────────────────────────────────

def add_regime(df: pd.DataFrame, cfg: RegimeConfig = RegimeConfig()) -> pd.DataFrame:
    """
    Attach regime columns to an OHLCV DataFrame.

    Adds: adx, plus_di, minus_di, atr, natr, regime.
    Does NOT drop rows — early bars get regime NaN until indicators warm up.
    """
    out = df.copy()
    adx, plus_di, minus_di, atr = compute_adx(out, cfg.adx_period)
    out["adx"] = adx
    out["plus_di"] = plus_di
    out["minus_di"] = minus_di
    out["atr"] = atr

    # normalized ATR: current ATR vs its own rolling median baseline
    baseline = atr.rolling(cfg.natr_lookback, min_periods=cfg.natr_lookback // 2).median()
    out["natr"] = atr / baseline.replace(0, np.nan)

    out["regime"] = _classify(out, cfg)
    return out


def _classify(df: pd.DataFrame, cfg: RegimeConfig) -> pd.Series:
    adx   = df["adx"]
    natr  = df["natr"]
    dip   = df["plus_di"]
    dim   = df["minus_di"]

    regime = pd.Series(np.nan, index=df.index, dtype=object)

    warm = adx.notna() & natr.notna()

    is_vol   = warm & (natr >= cfg.vol_expansion)
    is_trend = warm & ~is_vol & (adx >= cfg.adx_trend)
    is_range = warm & ~is_vol & ~is_trend

    regime[is_vol] = VOLATILE
    # trend direction from DI spread; tie/too-close -> treat as RANGE
    up   = is_trend & ((dip - dim) >= cfg.di_spread_min)
    down = is_trend & ((dim - dip) >= cfg.di_spread_min)
    flat = is_trend & ~up & ~down
    regime[up]   = TREND_UP
    regime[down] = TREND_DOWN
    regime[flat] = RANGE
    regime[is_range] = RANGE

    return regime


def current_regime(df: pd.DataFrame, cfg: RegimeConfig = RegimeConfig()) -> str:
    """Convenience: regime label of the most recent completed bar."""
    labeled = add_regime(df, cfg)
    val = labeled["regime"].iloc[-1]
    return val if isinstance(val, str) else "UNKNOWN"


def regime_summary(df: pd.DataFrame) -> dict:
    """Distribution of regimes over a labeled DataFrame (for diagnostics)."""
    if "regime" not in df.columns:
        return {}
    counts = df["regime"].value_counts(dropna=True)
    total = counts.sum()
    return {k: f"{v} ({v / total * 100:.1f}%)" for k, v in counts.items()}
