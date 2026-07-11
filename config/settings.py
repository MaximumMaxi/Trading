"""
settings.py — Central configuration for the v2 regime-switching system.

Credentials are read from environment variables first, then fall back to a
git-ignored `config/secrets.py` (see secrets.example.py). Never hardcode a
live password in this file.
"""

import os

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
SYMBOLS = {
    "fx_majors":   ["EURUSD", "GBPUSD", "USDJPY", "USDCHF",
                    "AUDUSD", "USDCAD", "NZDUSD"],
    "metals":      ["XAUUSD"],
    "indices":     ["US30"],
    "energy":      ["USOIL"],
    "crypto":      ["BTCUSD"],
}

ALL_SYMBOLS = [s for group in SYMBOLS.values() for s in group]

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
