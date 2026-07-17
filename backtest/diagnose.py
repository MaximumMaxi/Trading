"""
backtest/diagnose.py — per-strategy / per-symbol edge breakdown of a trade log.

Reads a trades CSV (from backtest.run -> logs/bt_trades.csv, or the walk-forward's
out-of-sample trades -> logs/wf_oos_trades.csv) and reports the size-independent
edge metric, avg realized R (= pnl / risk_usd), grouped by strategy x regime and
by symbol x strategy. This is the honest "where does the edge actually live"
view — dollar P&L is confounded by the equity path, avg R is not.

    python backtest/diagnose.py                          # logs/bt_trades.csv
    python backtest/diagnose.py logs/wf_oos_trades.csv   # walk-forward OOS trades
"""

import sys

import pandas as pd

p = sys.argv[1] if len(sys.argv) > 1 else "logs/bt_trades.csv"
df = pd.read_csv(p)
df["win"] = df["pnl"] > 0
df["R"] = df["pnl"] / df["risk_usd"].replace(0, float("nan"))   # realized R multiple


def grp(by):
    g = df.groupby(by).agg(trades=("pnl", "size"), win_pct=("win", "mean"),
                           pnl=("pnl", "sum"), avg_R=("R", "mean"),
                           bars=("bars_held", "mean"))
    g["win_pct"] = (g["win_pct"] * 100).round(1)
    g["pnl"] = g["pnl"].round(0)
    g["avg_R"] = g["avg_R"].round(3)
    g["bars"] = g["bars"].round(0)
    return g.sort_values("avg_R", ascending=False)


pd.set_option("display.width", 140, "display.max_rows", 80)
print(f"Trade log: {p}  ({len(df)} trades)")
print("\n=== EXIT REASON (TP vs SL vs forced) ===")
print(df.groupby("status").agg(n=("pnl", "size"), win_pct=("win", "mean"),
                               pnl=("pnl", "sum")).round(2))
print("\n=== EDGE BY STRATEGY x REGIME (sorted by avg R) ===")
print(grp(["strategy", "regime"]))
print("\n=== EDGE BY SYMBOL x STRATEGY ===")
print(grp(["symbol", "strategy"]))
