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
    allowed_regimes = {TREND_UP, TREND_DOWN}

    def __init__(self, roc_min: float = 0.0, require_htf_agree: bool = False):
        self.roc_min = roc_min
        # Default (False) matches the original, locked behavior exactly:
        # only avoid trading directly against the H4 bias. True requires the
        # H4 bias to actively agree, filtering out choppy/ambiguous periods.
        self.require_htf_agree = require_htf_agree
        self.name = "momentum_macd_roc_strict" if require_htf_agree else "momentum_macd_roc"

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
        htf_ok_up = (ctx.htf_bias == TREND_UP) if self.require_htf_agree \
            else (ctx.htf_bias != TREND_DOWN)
        if regime == TREND_UP and htf_ok_up:
            mom = (r["macd_hist"] > 0 and r["macd_hist"] > p["macd_hist"]
                   and r["roc"] > self.roc_min and r["close"] > r["ema50"])
            if mom:
                return build_signal(
                    "BUY", r["close"], atr, ctx, self.name, regime,
                    reasons=[f"MACD hist rising>0, ROC={r['roc']:.2f}%"],
                )

        # ── SELL: falling negative momentum in a downtrend ──
        htf_ok_down = (ctx.htf_bias == TREND_DOWN) if self.require_htf_agree \
            else (ctx.htf_bias != TREND_UP)
        if regime == TREND_DOWN and htf_ok_down:
            mom = (r["macd_hist"] < 0 and r["macd_hist"] < p["macd_hist"]
                   and r["roc"] < -self.roc_min and r["close"] < r["ema50"])
            if mom:
                return build_signal(
                    "SELL", r["close"], atr, ctx, self.name, regime,
                    reasons=[f"MACD hist falling<0, ROC={r['roc']:.2f}%"],
                )
        return None
