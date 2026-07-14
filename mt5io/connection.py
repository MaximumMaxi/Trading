"""
mt5io/connection.py — MetaTrader 5 connection + data retrieval.

Improved over module4's core: get_symbol_spec() now also returns
trade_tick_value / trade_tick_size, which lets the backtester compute P&L
*exactly* the way MT5 does — correct for FX, metals, indices, oil and crypto
alike, including quote-currency conversion.
"""

import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except Exception:  # pragma: no cover - lets the module import for offline planning
    mt5 = None
    _MT5_AVAILABLE = False

logger = logging.getLogger(__name__)

TIMEFRAMES = {}
if _MT5_AVAILABLE:
    TIMEFRAMES = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
    }


# ─── Connection ─────────────────────────────────────────────────────────────

def connect(login: int, password: str, server: str, path: Optional[str] = None,
            retries: int = 3, retry_delay: float = 5.0) -> bool:
    if not _MT5_AVAILABLE:
        logger.error("MetaTrader5 package not importable in this environment.")
        return False

    if not login:
        # No credentials configured -- attach to whatever terminal is already
        # running and logged in, instead of forcing a fresh (blank) login.
        logger.info("No MT5_LOGIN configured; attaching to running terminal session.")
        if mt5.initialize(path) if path else mt5.initialize():
            info = mt5.account_info()
            logger.info(f"Connected | Account {info.login} | "
                        f"{info.balance} {info.currency} | {info.server}")
            return True
        logger.error(f"Could not attach to a running MT5 terminal: {mt5.last_error()}")
        return False

    kwargs = {"login": int(login), "password": password, "server": server}
    if path:
        kwargs["path"] = path
    for attempt in range(1, retries + 1):
        logger.info(f"Connecting to MT5 (attempt {attempt}/{retries})...")
        if mt5.initialize(**kwargs):
            info = mt5.account_info()
            logger.info(f"Connected | Account {info.login} | "
                        f"{info.balance} {info.currency} | {info.server}")
            return True
        logger.warning(f"MT5 init failed: {mt5.last_error()}")
        if attempt < retries:
            time.sleep(retry_delay)
    logger.error("Could not connect to MT5.")
    return False


def disconnect() -> None:
    if _MT5_AVAILABLE:
        mt5.shutdown()
        logger.info("MT5 connection closed.")


# ─── Symbol spec (the important upgrade) ──────────────────────────────────────

def get_symbol_spec(symbol: str) -> Optional[dict]:
    """
    Return the full specification needed for correct P&L + sizing.

    tick_value / tick_size are the key fields: profit for a position is
        profit = (price_move / tick_size) * tick_value * volume
    which MT5 uses internally and which handles currency conversion for you.
    """
    if not _MT5_AVAILABLE:
        return None
    if not mt5.symbol_select(symbol, True):
        logger.warning(f"Could not select symbol: {symbol}")
    info = mt5.symbol_info(symbol)
    if info is None:
        logger.warning(f"Symbol not found: {symbol}")
        return None
    return {
        "symbol":        info.name,
        "description":   info.description,
        "digits":        info.digits,
        "point":         info.point,
        "tick_size":     info.trade_tick_size,
        "tick_value":    info.trade_tick_value,
        "contract_size": info.trade_contract_size,
        "spread_points": info.spread,
        "min_lot":       info.volume_min,
        "max_lot":       info.volume_max,
        "lot_step":      info.volume_step,
        "currency_base":   info.currency_base,
        "currency_profit": info.currency_profit,
    }


# ─── OHLCV ────────────────────────────────────────────────────────────────────

def get_ohlcv(symbol: str, timeframe: str = "H1", bars: int = 500,
              from_date: Optional[datetime] = None) -> Optional[pd.DataFrame]:
    if not _MT5_AVAILABLE:
        return None
    tf = TIMEFRAMES.get(timeframe.upper())
    if tf is None:
        logger.error(f"Unknown timeframe: {timeframe}")
        return None
    if not mt5.symbol_select(symbol, True):
        logger.warning(f"Could not select symbol: {symbol}")
    if from_date:
        rates = mt5.copy_rates_from(symbol, tf, from_date, bars)
    else:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    if rates is None or len(rates) == 0:
        logger.warning(f"No data for {symbol} {timeframe}: {mt5.last_error()}")
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    return df[["time", "open", "high", "low", "close", "volume"]].copy()


def get_account_info() -> Optional[dict]:
    if not _MT5_AVAILABLE:
        return None
    info = mt5.account_info()
    if info is None:
        return None
    return {"login": info.login, "balance": info.balance, "equity": info.equity,
            "currency": info.currency, "leverage": info.leverage}
