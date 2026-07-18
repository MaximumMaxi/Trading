"""
backtest/validate_mr.py — full-history mean-reversion validation for CANDIDATE
instruments, without touching the locked production universe (config/settings.py).

Tests whether `mean_reversion_bb` has a real full-history walk-forward edge on the
given symbols — the same bar US30 cleared and AUD/BTC/gold failed. Use it to vet
new range-prone candidates (e.g. FX crosses EURGBP/EURCHF) BEFORE adding them to
settings.py. Anything that doesn't clear this does not get traded.

    # 1. cache full history for the candidates (HISTORY_BARS=50k pulls ~2018+):
    python -m data.loader EURGBPm EURCHFm
    # 2. validate:
    python backtest/validate_mr.py EURGBPm EURCHFm
    # 3. per-symbol edge:
    python backtest/diagnose.py logs/mr_validate_trades.csv

Read the result like US30: many profitable folds + OOS PF>1 + positive per-symbol
avg R across FULL history = a real edge. A recent-only pass means nothing.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from backtest.run import build_symbol_data
from backtest.walk_forward import walk_forward
from config.instruments import _category_for


def main(symbols):
    data = build_symbol_data(symbols)
    if not data:
        print("No cached data. First run:  python -m data.loader " + " ".join(symbols))
        return

    # Allow mean-reversion on whatever categories these candidates fall into.
    # (Kept separate from settings.STRATEGY_BY_CATEGORY so production stays US30-only.)
    cats = {_category_for(s) for s in data}
    if "unknown" in cats:
        print("WARN: some symbols map to category 'unknown' — add them to "
              "FALLBACK_SPECS in config/instruments.py so _category_for resolves "
              "them, or they will never generate signals.")
    strat_map = {c: ["mean_reversion_bb"] for c in cats}

    print(f"Full-history MR validation: {list(data)} | categories={sorted(cats)}\n")
    _, _, oos_trades = walk_forward(data, n_splits=8, strategy_by_category=strat_map)

    out = os.path.join(os.path.dirname(__file__), "..", "logs", "mr_validate_trades.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pd.DataFrame([t.__dict__ for t in oos_trades]).to_csv(out, index=False)
    print(f"\nOOS trades -> {os.path.abspath(out)}")
    print("Per-symbol edge:  python backtest/diagnose.py logs/mr_validate_trades.csv")


if __name__ == "__main__":
    syms = sys.argv[1:]
    if not syms:
        print("Usage: python backtest/validate_mr.py EURGBPm EURCHFm")
    else:
        main(syms)
