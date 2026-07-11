"""
strategies/base.py — common interface for every sub-strategy.

Each strategy declares which regimes it may trade in and implements
generate(i, df, ctx) -> Optional[Signal]. The router only calls a strategy on
bars whose regime is in the strategy's `allowed_regimes`, so strategies don't
need to re-check the regime themselves (but may use it for context).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Set

from config.instruments import SymbolSpec


@dataclass
class Signal:
    symbol:    str
    direction: str            # "BUY" | "SELL"
    entry:     float
    sl:        float
    tp:        float
    rr:        float
    atr:       float
    strategy:  str
    regime:    str
    reasons:   List[str] = field(default_factory=list)


@dataclass
class StratContext:
    symbol:      str
    spec:        SymbolSpec
    htf_bias:    str                 # H4 regime label at this bar
    atr_sl_mult: float = 1.5
    atr_tp_mult: float = 3.0
    min_rr:      float = 1.5


def build_signal(direction: str, entry: float, atr: float, ctx: StratContext,
                 strategy: str, regime: str, reasons: List[str],
                 sl: Optional[float] = None, tp: Optional[float] = None
                 ) -> Optional[Signal]:
    """
    Construct a Signal with ATR-based SL/TP (unless explicit sl/tp given) and
    enforce the minimum reward:risk. Returns None if the trade fails min_rr or
    has a non-positive risk distance.
    """
    if atr is None or atr <= 0:
        return None

    if direction == "BUY":
        sl = sl if sl is not None else entry - atr * ctx.atr_sl_mult
        tp = tp if tp is not None else entry + atr * ctx.atr_tp_mult
        risk = entry - sl
        reward = tp - entry
    else:  # SELL
        sl = sl if sl is not None else entry + atr * ctx.atr_sl_mult
        tp = tp if tp is not None else entry - atr * ctx.atr_tp_mult
        risk = sl - entry
        reward = entry - tp

    if risk <= 0 or reward <= 0:
        return None
    rr = reward / risk
    if rr < ctx.min_rr:
        return None

    return Signal(symbol=ctx.symbol, direction=direction, entry=entry,
                  sl=sl, tp=tp, rr=round(rr, 2), atr=atr,
                  strategy=strategy, regime=regime, reasons=reasons)


class Strategy(ABC):
    name: str = "base"
    allowed_regimes: Set[str] = set()

    @abstractmethod
    def generate(self, i: int, df, ctx: StratContext) -> Optional[Signal]:
        """Return a Signal for bar `i` of feature-frame `df`, or None."""
        ...
