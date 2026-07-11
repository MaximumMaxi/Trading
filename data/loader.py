"""
data/loader.py — download OHLCV from MT5 and cache to CSV.

Usage (once MT5 credentials are set):
    python -m data.loader            # download all symbols, H1 + H4
    python -m data.loader EURUSD     # download a single symbol

Then anywhere in the system:
    from data.loader import load_cached
    h1 = load_cached("EURUSD", "H1")
"""

import logging
import os
import sys

import pandas as pd

# allow `python -m data.loader` and direct execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from config.instruments import build_specs_from_mt5
from mt5io.connection import (connect, disconnect, get_ohlcv, get_symbol_spec,
                              get_account_info)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("loader")

CACHE_DIR = os.path.abspath(settings.CACHE_DIR)
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(symbol: str, timeframe: str) -> str:
    return os.path.join(CACHE_DIR, f"{symbol}_{timeframe}.csv")


def load_cached(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Load a cached OHLCV CSV as a DataFrame (parsed time column), or None."""
    path = _cache_path(symbol, timeframe)
    if not os.path.exists(path):
        logger.warning(f"No cache for {symbol} {timeframe} at {path}")
        return None
    df = pd.read_csv(path, parse_dates=["time"])
    return df


def download_all(symbols=None, timeframes=("H1", "H4"),
                 bars: int = settings.HISTORY_BARS) -> None:
    """Connect to MT5, refresh instrument specs, and cache OHLCV for all symbols."""
    symbols = symbols or settings.ALL_SYMBOLS

    if not connect(settings.MT5_LOGIN, settings.MT5_PASSWORD,
                   settings.MT5_SERVER, settings.MT5_PATH):
        logger.error("Aborting: could not connect to MT5. "
                     "Set credentials in config/secrets.py or env vars.")
        return

    acc = get_account_info()
    if acc:
        logger.info(f"Account {acc['login']} | {acc['balance']} {acc['currency']}")

    # 1. Refresh authoritative instrument specs (tick_value/tick_size/etc.)
    specs = build_specs_from_mt5(symbols, get_symbol_spec, save=True)
    logger.info(f"Resolved specs for {len(specs)}/{len(symbols)} symbols.")

    # 2. Download + cache OHLCV
    ok, fail = 0, 0
    for sym in symbols:
        for tf in timeframes:
            df = get_ohlcv(sym, tf, bars=bars)
            if df is None or df.empty:
                logger.warning(f"  {sym} {tf}: no data")
                fail += 1
                continue
            df.to_csv(_cache_path(sym, tf), index=False)
            logger.info(f"  {sym} {tf}: {len(df)} bars "
                        f"({df['time'].iloc[0].date()} → {df['time'].iloc[-1].date()})")
            ok += 1

    disconnect()
    logger.info(f"Done. {ok} series cached, {fail} failed. Cache dir: {CACHE_DIR}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        download_all(symbols=args)
    else:
        download_all()
