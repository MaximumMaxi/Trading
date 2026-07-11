"""
strategies/trend.py — MA-bounce pullback (the core idea).

"Buy when price bounces off a moving average in an uptrend" (and the mirror
for downtrends). Fires only in TREND_UP / TREND_DOWN regimes.

Entry logic (BUY):
  * structure: ema20 > ema50 (uptrend intact)
  * pullback : the *previous* bar dipped to within `touch_atr` of ema20
  * reclaim  : current close is back above ema20 AND above the previous close
  * filter   : RSI not already overbought
"""

from typing import Optional

from regime.detector import TREND_UP, TREND_DOWN
from strategies.base import Signal, StratContext, Strategy, build_signal


class TrendStrategy(Strategy):
    name = "trend_ma_bounce"
    allowed_regimes = {TREND_UP, TREND_DOWN}

    def __init__(self, touch_atr: float = 0.5, rsi_cap: float = 70.0):
        self.touch_atr = touch_atr   # how close to the MA counts as a "touch"
        self.rsi_cap = rsi_cap

    def generate(self, i: int, df, ctx: StratContext) -> Optional[Signal]:
        if i < 1:
            return None
        r = df.iloc[i]
        atr = r["atr"]
        if atr is None or atr <= 0:
            return None
        regime = r["regime"]
        tol = self.touch_atr * atr

        # ── BUY: bounce off rising EMA20 in an uptrend ──
        if regime == TREND_UP and ctx.htf_bias != TREND_DOWN:
            uptrend = r["ema20"] > r["ema50"]
            pulled_back = r["low_prev"] <= r["ema20_prev"] + tol
            reclaimed = r["close"] > r["ema20"] and r["close"] > r["close_prev"]
            not_hot = r["rsi"] < self.rsi_cap
            if uptrend and pulled_back and reclaimed and not_hot:
                return build_signal(
                    "BUY", r["close"], atr, ctx, self.name, regime,
                    reasons=[f"pullback to EMA20 in uptrend, RSI={r['rsi']:.0f}"],
                )

        # ── SELL: rejection off falling EMA20 in a downtrend ──
        if regime == TREND_DOWN and ctx.htf_bias != TREND_UP:
            downtrend = r["ema20"] < r["ema50"]
            pulled_back = r["high_prev"] >= r["ema20_prev"] - tol
            rejected = r["close"] < r["ema20"] and r["close"] < r["close_prev"]
            not_cold = r["rsi"] > (100 - self.rsi_cap)
            if downtrend and pulled_back and rejected and not_cold:
                return build_signal(
                    "SELL", r["close"], atr, ctx, self.name, regime,
                    reasons=[f"rejection at EMA20 in downtrend, RSI={r['rsi']:.0f}"],
                )
        return None
