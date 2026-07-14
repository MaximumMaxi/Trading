"""
settings.py — Central configuration for the v2 regime-switching system.

Credentials are read from environment variables first, then fall back to a
git-ignored `config/secrets.py` (see secrets.example.py). Never hardcode a
live password in this file.
"""

import os

from regime.detector import RegimeConfig

# ─── MT5 credentials ────────────────────────────────────────────────────────
# Priority: environment variables > config/secrets.py > placeholders.
try:
    from config import secrets as _secrets  # git-ignored, optional
except Exception:  # pragma: no cover
    _secrets = None


def _cred(env_key: str, secret_attr: str, default):
    if os.getenv(env_key):
        return os.getenv(env_key)
    if _secrets and hasattr(_secrets, secret_attr):
        return getattr(_secrets, secret_attr)
    return default


MT5_LOGIN    = int(_cred("MT5_LOGIN", "MT5_LOGIN", 0) or 0)
MT5_PASSWORD = _cred("MT5_PASSWORD", "MT5_PASSWORD", "")
MT5_SERVER   = _cred("MT5_SERVER", "MT5_SERVER", "ICMarkets-Demo")
MT5_PATH     = _cred("MT5_PATH", "MT5_PATH", None)  # path to terminal64.exe, optional

# ─── Instruments to trade ───────────────────────────────────────────────────
# Grouped by asset class. Adjust to match your broker's exact symbol names
# (some brokers use suffixes like "XAUUSD.m" or "US30.cash").
# ── LOCKED validated universe (survived walk-forward, 2026-07) ──
# US30 & AUD mean-reversion = robust core; BTC momentum = thin satellite;
# XAUUSD trend/momentum (strict H4 agreement, wide asymmetric RR) added 2026-07 --
# supersedes the earlier rejected "Gold (XAU) trend" attempt (see CLAUDE.md):
# that one used the plain trend/momentum strategies at the shared 2.0/3.0 ATR
# mults and collapsed IS->OOS (+0.26 -> +0.02 avg R). This version requires the
# H4 bias to actively agree (not just "not opposed") and uses a much wider,
# asymmetric target (see CATEGORY_PARAMS below) -- walk-forward: 4/4 folds
# profitable, OOS PF 1.27, OOS avg R +0.26 (IS +0.29, so <15% IS->OOS decay).
SYMBOLS = {
    "indices":     ["US30m"],
    "fx_majors":   ["AUDUSDm"],
    "crypto":      ["BTCUSDm"],
    "metals":      ["XAUUSDm"],
}

ALL_SYMBOLS = [s for group in SYMBOLS.values() for s in group]

# Which strategy trades each asset class (validated edge assignment).
STRATEGY_BY_CATEGORY = {
    "indices":   ["mean_reversion_bb"],
    "fx_majors": ["mean_reversion_bb"],
    "crypto":    ["momentum_macd_roc"],
    "metals":    ["trend_ma_bounce_strict", "momentum_macd_roc_strict"],
}

# Per-category overrides for regime/risk params that differ from the shared
# ATR_SL_MULT/ATR_TP_MULT/ADX_TREND below (see EnsembleRouter's
# category_overrides). Categories absent here use the shared globals unchanged
# -- indices/fx_majors/crypto are untouched by adding this mechanism.
CATEGORY_PARAMS = {
    "metals": {
        "regime_cfg":  RegimeConfig(adx_trend=25.0),
        "atr_sl_mult": 1.5,
        "atr_tp_mult": 8.0,
    },
}

# ── LOCKED validated strategy parameters (walk-forward winners) ──
ATR_SL_MULT        = 2.0
ATR_TP_MULT        = 3.0
ADX_TREND          = 28.0
REQUIRE_CONFLUENCE = False

# ─── Timeframes ─────────────────────────────────────────────────────────────
SIGNAL_TF = "H1"   # entry timeframe
BIAS_TF   = "H4"   # higher-timeframe regime/bias
HISTORY_BARS = 20_000   # bars to pull per symbol per timeframe for backtesting

# ─── Data cache ─────────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")

# ─── Risk defaults (mirrors the module4 bot, per-instrument overrides later) ──
INITIAL_CAPITAL   = 10_000.0
RISK_PER_TRADE    = 1.0    # % of equity risked per trade
MAX_OPEN_TRADES   = 5
MAX_DAILY_LOSS    = 3.0    # % of equity
MAX_DRAWDOWN_HALT = 10.0   # % from peak
MIN_RR_RATIO      = 1.5

# ─── Live / paper-trading (demo forward test) ────────────────────────────────
DRY_RUN          = True         # True = compute + log signals, place NO orders
LOOP_SECONDS     = 60           # poll interval; the bot acts once per new H1 bar
LIVE_BARS        = 600          # bars pulled per scan (enough for EMA200/regime warm-up)
MAGIC_NUMBER     = 20260712     # tags this bot's orders in MT5
ORDER_COMMENT    = "v2_regime"
DEVIATION_POINTS = 20           # max slippage for market orders (points)
TRADE_JOURNAL    = os.path.join(os.path.dirname(__file__), "..", "logs", "live_trades.csv")
