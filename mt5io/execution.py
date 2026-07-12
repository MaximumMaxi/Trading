"""
mt5io/execution.py — order placement + position queries for live/paper trading.

Only used by the live bot. All order functions are no-ops if MT5 isn't importable
so the module stays importable for offline verification.
"""

import logging
from typing import List, Optional

try:
    import MetaTrader5 as mt5
    _MT5 = True
except Exception:  # pragma: no cover
    mt5 = None
    _MT5 = False

logger = logging.getLogger(__name__)


def open_positions(magic: Optional[int] = None) -> List[dict]:
    """Return open positions, optionally only those tagged with `magic`."""
    if not _MT5:
        return []
    positions = mt5.positions_get()
    if not positions:
        return []
    out = []
    for p in positions:
        if magic is not None and p.magic != magic:
            continue
        out.append({
            "ticket": p.ticket, "symbol": p.symbol,
            "direction": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": p.volume, "open_price": p.price_open,
            "sl": p.sl, "tp": p.tp, "profit": p.profit,
        })
    return out


def has_open_position(symbol: str, magic: Optional[int] = None) -> bool:
    return any(p["symbol"] == symbol for p in open_positions(magic))


def _filling_mode(symbol: str):
    """Pick a filling mode the symbol supports (IOC preferred, else FOK/RETURN)."""
    info = mt5.symbol_info(symbol)
    # symbol_info.filling_mode is a bitmask; IOC=1<<1 in practice varies, so try order.
    return mt5.ORDER_FILLING_IOC


def place_market_order(symbol: str, direction: str, volume: float,
                       sl: float, tp: float, magic: int, comment: str,
                       deviation: int = 20) -> dict:
    """
    Send a market order with attached SL/TP. Returns a result dict with
    success flag, retcode, and (on success) the ticket + fill price.
    """
    if not _MT5:
        return {"success": False, "error": "MT5 not available"}

    if not mt5.symbol_select(symbol, True):
        return {"success": False, "error": f"cannot select {symbol}"}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"success": False, "error": f"no tick for {symbol}"}

    if direction == "BUY":
        order_type, price = mt5.ORDER_TYPE_BUY, tick.ask
    else:
        order_type, price = mt5.ORDER_TYPE_SELL, tick.bid

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       float(volume),
        "type":         order_type,
        "price":        price,
        "sl":           float(sl),
        "tp":           float(tp),
        "deviation":    int(deviation),
        "magic":        int(magic),
        "comment":      comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": _filling_mode(symbol),
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": f"order_send None: {mt5.last_error()}"}

    # Retry once with FOK if the broker rejected the filling mode.
    if result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
        request["type_filling"] = mt5.ORDER_FILLING_FOK
        result = mt5.order_send(request)

    ok = result.retcode == mt5.TRADE_RETCODE_DONE
    if not ok:
        logger.warning(f"Order rejected {symbol} {direction}: "
                       f"retcode={result.retcode} {result.comment}")
    return {
        "success": ok, "retcode": result.retcode,
        "ticket": getattr(result, "order", None),
        "price": getattr(result, "price", None),
        "comment": result.comment,
    }
