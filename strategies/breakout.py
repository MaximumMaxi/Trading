"""
strategies/breakout.py — Donchian channel breakout, VOLATILE regime only.

A close beyond the prior 20-bar high/low during a volatility expansion is the
classic breakout trigger. Optionally aligns with the higher-timeframe bias so we
don't fade a strong HTF trend. Fires only in VOLATILE.
"""

from typing import Optional

from regime.detector import VOLATILE, TREND_UP, TREND_DOWN
from strategies.base import Signal, StratContext, Strategy, build_signal


class BreakoutStrategy(Strategy):
    name = "breakout_donchian"
    allowed_regimes = {VOLATILE}

    def __init__(self, respect_htf: bool = True):
        self.respect_htf = respect_htf

    def generate(self, i: int, df, ctx: StratContext) -> Optional[Signal]:
        r = df.iloc[i]
        atr = r["atr"]
        if atr is None or atr <= 0:
            return None
        regime = r["regime"]
        if regime != VOLATILE:
            return None
        dh, dl = r["donch_high"], r["donch_low"]
        if dh != dh or dl != dl:   # NaN guard during warm-up
            return None

        # ── BUY: break above prior range high ──
        if r["close"] > dh:
            if self.respect_htf and ctx.htf_bias == TREND_DOWN:
                return None
            return build_signal(
                "BUY", r["close"], atr, ctx, self.name, regime,
                reasons=[f"close>{dh:.5f} (20-bar high) on expansion"],
            )

        # ── SELL: break below prior range low ──
        if r["close"] < dl:
            if self.respect_htf and ctx.htf_bias == TREND_UP:
                return None
            return build_signal(
                "SELL", r["close"], atr, ctx, self.name, regime,
                reasons=[f"close<{dl:.5f} (20-bar low) on expansion"],
            )
        return None
