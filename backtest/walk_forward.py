"""
backtest/walk_forward.py — walk-forward validation.

Why this exists: an in-sample backtest tells you how well you fit the past. It
says nothing about the future. Walk-forward optimization is the honest test:
repeatedly optimize parameters on a training window, then measure performance on
the *next, unseen* window — and stitch those out-of-sample (OOS) segments into
one continuous equity curve. That OOS curve is the closest thing to "what live
would have looked like."

    python -m backtest.walk_forward                 # all cached symbols
    python -m backtest.walk_forward EURUSD XAUUSD    # subset

Design:
  * Expanding (anchored) windows by default: train grows, each OOS block is new.
  * Small parameter grid over the levers that matter most (ATR SL/TP, ADX trend
    threshold). Expand it once we see real behavior.
  * Objective is Calmar-like (return per unit drawdown) with a min-trades guard,
    so it rewards robustness, not lucky single-trade spikes.
  * Each window is self-contained via the engine's entry_start/entry_end gating.
"""

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import PortfolioBacktestEngine
from config import settings
from regime.detector import RegimeConfig
from ensemble.router import EnsembleRouter


# ─── parameter grid ───────────────────────────────────────────────────────────
PARAM_GRID = {
    "atr_sl_mult": [1.0, 1.5, 2.0],
    "atr_tp_mult": [2.0, 3.0],
    "adx_trend":   [22.0, 28.0],
}


def _grid():
    keys = list(PARAM_GRID)
    for combo in itertools.product(*(PARAM_GRID[k] for k in keys)):
        yield dict(zip(keys, combo))


def _make_router(p, min_rr, strategy_by_category=None):
    cfg = RegimeConfig(adx_trend=p["adx_trend"])
    return EnsembleRouter(regime_cfg=cfg, atr_sl_mult=p["atr_sl_mult"],
                          atr_tp_mult=p["atr_tp_mult"], min_rr=min_rr,
                          strategy_by_category=strategy_by_category)


def _objective(res, min_trades):
    """Calmar-like: return per unit drawdown, guarded by a minimum trade count."""
    if res.total_trades < min_trades:
        return -np.inf
    return res.total_return_pct / (res.max_drawdown_pct + 1.0)


# ─── folds ─────────────────────────────────────────────────────────────────────
def _build_folds(symbol_data, n_splits, anchored=True):
    """Return list of (is_start, is_end, oos_start, oos_end) timestamps."""
    times = pd.Index(sorted(set().union(
        *[set(pd.to_datetime(d["h1"]["time"])) for d in symbol_data.values()])))
    n = len(times)
    block = n // (n_splits + 1)
    if block < 50:
        raise ValueError(f"Not enough data ({n} bars) for {n_splits} folds.")
    folds = []
    for k in range(n_splits):
        is_lo = 0 if anchored else k * block
        is_hi = (k + 1) * block - 1
        oos_lo = (k + 1) * block
        oos_hi = min((k + 2) * block - 1, n - 1)
        folds.append((times[is_lo], times[is_hi], times[oos_lo], times[oos_hi]))
    return folds


# ─── main walk-forward ──────────────────────────────────────────────────────────
def walk_forward(symbol_data, n_splits=4, anchored=True, min_trades=15,
                 base_capital=None, risk_pct=None, strategy_by_category=None):
    base_capital = base_capital or settings.INITIAL_CAPITAL
    risk_pct = risk_pct if risk_pct is not None else settings.RISK_PER_TRADE
    min_rr = settings.MIN_RR_RATIO

    folds = _build_folds(symbol_data, n_splits, anchored)
    print(f"Walk-forward: {len(folds)} folds, "
          f"{'anchored' if anchored else 'rolling'} windows, "
          f"grid={sum(1 for _ in _grid())} combos/fold\n")

    wf_equity = base_capital
    all_oos_trades = []
    oos_curve = [base_capital]
    fold_rows = []

    for fi, (is_s, is_e, oos_s, oos_e) in enumerate(folds, 1):
        # 1. optimize on in-sample
        best_p, best_score = None, -np.inf
        for p in _grid():
            eng = PortfolioBacktestEngine(initial_capital=base_capital,
                                          risk_pct=risk_pct)
            r = eng.run(symbol_data, _make_router(p, min_rr, strategy_by_category),
                        entry_start=is_s, entry_end=is_e)
            s = _objective(r, min_trades)
            if s > best_score:
                best_score, best_p = s, p

        # 2. validate on out-of-sample with best params, chaining equity
        eng = PortfolioBacktestEngine(initial_capital=wf_equity, risk_pct=risk_pct)
        oos = eng.run(symbol_data, _make_router(best_p, min_rr, strategy_by_category),
                      entry_start=oos_s, entry_end=oos_e)

        is_ret = best_score  # objective proxy for IS quality
        oos_curve.extend(oos.equity_curve[1:])   # continue the chained curve
        all_oos_trades.extend(oos.trades)
        prev_eq = wf_equity
        wf_equity = oos.final_equity if oos.total_trades else wf_equity
        oos_ret = (wf_equity / prev_eq - 1) * 100

        fold_rows.append({
            "fold": fi,
            "train": f"{str(is_s)[:10]}..{str(is_e)[:10]}",
            "test":  f"{str(oos_s)[:10]}..{str(oos_e)[:10]}",
            "best_params": best_p,
            "oos_trades": oos.total_trades,
            "oos_win%": oos.win_rate,
            "oos_PF": oos.profit_factor,
            "oos_ret%": round(oos_ret, 2),
            "oos_maxDD%": oos.max_drawdown_pct,
        })
        print(f"Fold {fi}: train {str(is_s)[:10]}..{str(is_e)[:10]} | "
              f"test {str(oos_s)[:10]}..{str(oos_e)[:10]} | "
              f"best={best_p} | OOS ret={oos_ret:+.2f}% "
              f"trades={oos.total_trades} PF={oos.profit_factor} DD={oos.max_drawdown_pct}%")

    _summary(base_capital, wf_equity, oos_curve, all_oos_trades, fold_rows)
    return fold_rows, oos_curve, all_oos_trades


def _summary(base, final, curve, trades, fold_rows):
    eq = np.array(curve, dtype=float)
    peak = np.maximum.accumulate(eq)
    max_dd = round(((peak - eq) / peak).max() * 100, 2) if len(eq) else 0
    rets = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([0.0])
    sharpe = round(rets.mean() / rets.std() * np.sqrt(252), 3) if rets.std() > 0 else 0
    total_ret = (final / base - 1) * 100
    wins = [t for t in trades if t.pnl > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    gp = sum(t.pnl for t in wins); gl = abs(sum(t.pnl for t in trades if t.pnl <= 0))
    pf = round(gp / gl, 3) if gl > 0 else float("inf")

    pos = sum(1 for f in fold_rows if f["oos_ret%"] > 0)
    line = "-" * 62
    print("\n" + line)
    print("  WALK-FORWARD (OUT-OF-SAMPLE, stitched)")
    print(line)
    print(f"  Folds profitable   : {pos}/{len(fold_rows)}")
    print(f"  OOS total return   : {total_ret:+.2f}%")
    print(f"  OOS trades         : {len(trades)}")
    print(f"  OOS win rate       : {wr:.1f}%")
    print(f"  OOS profit factor  : {pf}")
    print(f"  OOS max drawdown   : {max_dd:.2f}%")
    print(f"  OOS Sharpe         : {sharpe}")
    print(line)
    print("  Read: consistency across folds matters more than the headline.")
    print("  Many profitable folds + PF>1 OOS = the edge may generalize.")
    print("  One giant fold carrying all others = likely a fluke.")
    print(line)


if __name__ == "__main__":
    from backtest.run import build_symbol_data
    syms = sys.argv[1:] or settings.ALL_SYMBOLS
    data = build_symbol_data(syms)
    if not data:
        print("No usable data. Run `python -m data.loader` first.")
    else:
        walk_forward(data)
