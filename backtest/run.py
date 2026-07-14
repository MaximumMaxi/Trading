"""
backtest/run.py — load cached data and run the portfolio backtest.

    python -m backtest.run                # all symbols with cached data
    python -m backtest.run EURUSD XAUUSD  # a subset

Requires cached CSVs from `python -m data.loader` and (ideally) specs.json.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import PortfolioBacktestEngine
from backtest.report import print_report
from config import settings
from config.instruments import load_specs
from data.loader import load_cached
from ensemble.router import EnsembleRouter
from regime.detector import RegimeConfig


def build_symbol_data(symbols):
    specs = load_specs()
    data = {}
    for sym in symbols:
        h1 = load_cached(sym, settings.SIGNAL_TF)
        h4 = load_cached(sym, settings.BIAS_TF)
        if h1 is None or h4 is None:
            print(f"  skip {sym}: missing cache (run `python -m data.loader {sym}`)")
            continue
        if sym not in specs:
            print(f"  skip {sym}: no spec")
            continue
        data[sym] = {"h1": h1, "h4": h4, "spec": specs[sym]}
    return data


def main(symbols):
    data = build_symbol_data(symbols)
    if not data:
        print("No usable symbol data. Download it first: python -m data.loader")
        return
    print(f"Running portfolio backtest on {len(data)} symbols: {list(data)}")
    router = EnsembleRouter(
        regime_cfg=RegimeConfig(adx_trend=settings.ADX_TREND),
        atr_sl_mult=settings.ATR_SL_MULT, atr_tp_mult=settings.ATR_TP_MULT,
        min_rr=settings.MIN_RR_RATIO, strategy_by_category=settings.STRATEGY_BY_CATEGORY,
        require_confluence=settings.REQUIRE_CONFLUENCE,
        category_overrides=settings.CATEGORY_PARAMS)
    engine = PortfolioBacktestEngine(
        initial_capital=settings.INITIAL_CAPITAL,
        risk_pct=settings.RISK_PER_TRADE,
        max_open_trades=settings.MAX_OPEN_TRADES,
        daily_loss_limit=settings.MAX_DAILY_LOSS,
        max_drawdown_halt=settings.MAX_DRAWDOWN_HALT,
    )
    res = engine.run(data, router)
    print_report(res)

    # save trades
    out = os.path.join(os.path.dirname(__file__), "..", "logs", "bt_trades.csv")
    import pandas as pd
    if res.trades:
        pd.DataFrame([t.__dict__ for t in res.trades]).to_csv(out, index=False)
        print(f"Trades written to {os.path.abspath(out)}")


if __name__ == "__main__":
    syms = sys.argv[1:] or settings.ALL_SYMBOLS
    main(syms)
