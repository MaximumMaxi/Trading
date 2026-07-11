"""
strategies/mean_reversion.py — Bollinger + RSI fade, RANGE regime only.

Buy the lower band when oversold, sell the upper band when overbought, with the
target set to the band midline (the mean). Fires only in RANGE.
"""

from typing import Optional

from regime.detector import RANGE
from strategies.base import Signal, StratContext, Strategy, build_signal


class MeanReversionStrategy(Strategy):
    name = "mean_reversion_bb"
    allowed_regimes = {RANGE}

    def __init__(self, rsi_low: float = 35.0, rsi_high: float = 65.0):
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high

    def generate(self, i: int, df, ctx: StratContext) -> Optional[Signal]:
        r = df.iloc[i]
        atr = r["atr"]
        if atr is None or atr <= 0:
            return None
        regime = r["regime"]
        if regime != RANGE:
            return None

        # ── BUY: oversold at/below lower band, target the mean ──
        if r["close"] <= r["bb_lower"] and r["rsi"] < self.rsi_low:
            sl = r["close"] - atr * ctx.atr_sl_mult
            tp = r["bb_mid"]              # revert to mean
            return build_signal(
                "BUY", r["close"], atr, ctx, self.name, regime,
                reasons=[f"close<=BBlower, RSI={r['rsi']:.0f}, target mean"],
                sl=sl, tp=tp,
            )

        # ── SELL: overbought at/above upper band, target the mean ──
        if r["close"] >= r["bb_upper"] and r["rsi"] > self.rsi_high:
            sl = r["close"] + atr * ctx.atr_sl_mult
            tp = r["bb_mid"]
            return build_signal(
                "SELL", r["close"], atr, ctx, self.name, regime,
                reasons=[f"close>=BBupper, RSI={r['rsi']:.0f}, target mean"],
                sl=sl, tp=tp,
            )
        return None
