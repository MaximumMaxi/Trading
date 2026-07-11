"""
strategies/momentum.py — MACD/ROC continuation, TREND regimes.

Rides established momentum in the trend direction. In the router this runs
alongside the MA-bounce trend strategy: when both agree it's a confluence
signal; on its own it catches trend continuations that never pull back to the MA.
"""

from typing import Optional

from regime.detector import TREND_UP, TREND_DOWN
from strategies.base import Signal, StratContext, Strategy, build_signal


class MomentumStrategy(Strategy):
    name = "momentum_macd_roc"
    allowed_regimes = {TREND_UP, TREND_DOWN}

    def __init__(self, roc_min: float = 0.0):
        self.roc_min = roc_min

    def generate(self, i: int, df, ctx: StratContext) -> Optional[Signal]:
        if i < 1:
            return None
        r = df.iloc[i]
        p = df.iloc[i - 1]
        atr = r["atr"]
        if atr is None or atr <= 0:
            return None
        regime = r["regime"]

        # ── BUY: rising positive momentum in an uptrend ──
        if regime == TREND_UP and ctx.htf_bias != TREND_DOWN:
            mom = (r["macd_hist"] > 0 and r["macd_hist"] > p["macd_hist"]
                   and r["roc"] > self.roc_min and r["close"] > r["ema50"])
            if mom:
                return build_signal(
                    "BUY", r["close"], atr, ctx, self.name, regime,
                    reasons=[f"MACD hist rising>0, ROC={r['roc']:.2f}%"],
                )

        # ── SELL: falling negative momentum in a downtrend ──
        if regime == TREND_DOWN and ctx.htf_bias != TREND_UP:
            mom = (r["macd_hist"] < 0 and r["macd_hist"] < p["macd_hist"]
                   and r["roc"] < -self.roc_min and r["close"] < r["ema50"])
            if mom:
                return build_signal(
                    "SELL", r["close"], atr, ctx, self.name, regime,
                    reasons=[f"MACD hist falling<0, ROC={r['roc']:.2f}%"],
                )
        return None
