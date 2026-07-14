"""
ensemble/router.py — regime-switching signal router.

Ties everything together:
  1. prepare(h1, h4): add features + regime to H1, and map the H4 regime onto
     each H1 bar as `htf_bias`.
  2. route(i, df, ctx): for the bar's regime, run only the strategies allowed in
     that regime and resolve to at most one Signal:
        - single strategy fires        -> take it
        - multiple agree on direction  -> confluence (take best R:R, merge reasons)
        - multiple conflict            -> stand aside (no trade)

Routing map (regime -> strategies, priority order):
    TREND_UP / TREND_DOWN -> [trend MA-bounce, momentum]
    RANGE                 -> [mean reversion]
    VOLATILE              -> [breakout]
"""

from typing import List, Optional, Tuple

import pandas as pd

from config.instruments import SymbolSpec
from regime.detector import (add_regime, RegimeConfig,
                             TREND_UP, TREND_DOWN, RANGE, VOLATILE)
from strategies.base import Signal, StratContext
from strategies.breakout import BreakoutStrategy
from strategies.indicators import add_features
from strategies.mean_reversion import MeanReversionStrategy
from strategies.momentum import MomentumStrategy
from strategies.trend import TrendStrategy


class EnsembleRouter:
    def __init__(self, regime_cfg: RegimeConfig = RegimeConfig(),
                 atr_sl_mult: float = 1.5, atr_tp_mult: float = 3.0,
                 min_rr: float = 1.5, strategy_by_category=None,
                 require_confluence: bool = False, category_overrides: dict = None):
        """
        category_overrides: optional {category: {"regime_cfg":..., "atr_sl_mult":...,
        "atr_tp_mult":..., "min_rr":...}} to give one asset category its own
        regime/risk params instead of the router-wide defaults above. Categories
        not present here fall back to the defaults unchanged -- existing behavior
        for symbols with no override is exactly as before.
        """
        self.regime_cfg = regime_cfg
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.min_rr = min_rr
        self.strategy_by_category = strategy_by_category
        self.require_confluence = require_confluence
        self.category_overrides = category_overrides or {}

        trend = TrendStrategy()
        momentum = MomentumStrategy()
        trend_strict = TrendStrategy(require_htf_agree=True)
        momentum_strict = MomentumStrategy(require_htf_agree=True)
        self.routing = {
            TREND_UP:   [trend, momentum, trend_strict, momentum_strict],
            TREND_DOWN: [trend, momentum, trend_strict, momentum_strict],
            RANGE:      [MeanReversionStrategy()],
            VOLATILE:   [BreakoutStrategy()],
        }

    # ── per-category overrides ──────────────────────────────────────────────
    def _override(self, category: str) -> dict:
        return self.category_overrides.get(category, {})

    # ── data prep ────────────────────────────────────────────────────────────
    def prepare(self, h1: pd.DataFrame, h4: pd.DataFrame, category: str = None) -> pd.DataFrame:
        """Return an H1 frame with features, regime, and htf_bias columns."""
        cfg = self._override(category).get("regime_cfg", self.regime_cfg)
        h1p = add_features(h1)
        h1p = add_regime(h1p, cfg)

        h4r = add_regime(add_features(h4), cfg)[["time", "regime"]]
        h4r = h4r.rename(columns={"regime": "htf_bias"}).dropna(subset=["htf_bias"])

        # as-of merge: each H1 bar gets the most recent completed H4 regime
        h1p = h1p.sort_values("time")
        h4r = h4r.sort_values("time")
        merged = pd.merge_asof(h1p, h4r, on="time", direction="backward")
        merged["htf_bias"] = merged["htf_bias"].fillna("UNKNOWN")
        return merged

    # ── routing ────────────────────────────────────────────────────────────
    def make_context(self, symbol: str, spec: SymbolSpec, htf_bias: str) -> StratContext:
        ov = self._override(spec.category)
        return StratContext(symbol=symbol, spec=spec, htf_bias=htf_bias,
                            atr_sl_mult=ov.get("atr_sl_mult", self.atr_sl_mult),
                            atr_tp_mult=ov.get("atr_tp_mult", self.atr_tp_mult),
                            min_rr=ov.get("min_rr", self.min_rr))

    def route(self, i: int, df: pd.DataFrame, symbol: str,
              spec: SymbolSpec) -> Optional[Signal]:
        row = df.iloc[i]
        regime = row["regime"]
        if not isinstance(regime, str) or regime not in self.routing:
            return None

        ctx = self.make_context(symbol, spec, row.get("htf_bias", "UNKNOWN"))
        allowed = None
        if self.strategy_by_category is not None:
            allowed = self.strategy_by_category.get(spec.category, [])
        candidates: List[Signal] = []
        for strat in self.routing[regime]:
            if allowed is not None and strat.name not in allowed:
                continue
            sig = strat.generate(i, df, ctx)
            if sig is not None:
                candidates.append(sig)

        if not candidates:
            return None
        directions = {c.direction for c in candidates}
        if len(directions) > 1:
            return None   # conflict -> stand aside
        if (self.require_confluence and regime in (TREND_UP, TREND_DOWN)
                and len(candidates) < 2):
            return None   # trend regime needs trend+momentum agreement
        if len(candidates) == 1:
            return candidates[0]
        best = max(candidates, key=lambda c: c.rr)
        best.reasons = [f"confluence({len(candidates)}): "
                        + " + ".join(c.strategy for c in candidates)] + best.reasons
        return best

    def generate_all(self, df: pd.DataFrame, symbol: str,
                     spec: SymbolSpec) -> List[Tuple[int, Signal]]:
        """Run the router across every bar of a prepared frame (for backtests)."""
        out = []
        for i in range(len(df)):
            sig = self.route(i, df, symbol, spec)
            if sig is not None:
                out.append((i, sig))
        return out
