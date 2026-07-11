"""backtest/report.py — pretty-print a PortfolioResult."""

from backtest.engine import PortfolioResult


def print_report(res: PortfolioResult) -> None:
    line = "-" * 60
    print(line)
    print("  PORTFOLIO BACKTEST RESULT" + ("  [HALTED: max drawdown hit]" if res.halted else ""))
    print(line)
    print(f"  Initial capital   : {res.initial_capital:,.2f}")
    print(f"  Final equity      : {res.final_equity:,.2f}")
    print(f"  Total return      : {res.total_return_pct:+.2f}%")
    print(f"  Total trades      : {res.total_trades}")
    print(f"  Win rate          : {res.win_rate:.1f}%")
    print(f"  Profit factor     : {res.profit_factor}")
    print(f"  Expectancy/trade  : {res.expectancy:,.2f}")
    print(f"  Max drawdown      : {res.max_drawdown_pct:.2f}%")
    print(f"  Sharpe / Sortino  : {res.sharpe} / {res.sortino}")
    print(f"  Calmar            : {res.calmar}")

    if res.per_strategy:
        print(line)
        print("  BY STRATEGY")
        print(f"  {'strategy':22}{'trades':>7}{'win%':>7}{'PF':>8}{'pnl':>12}")
        for k, s in sorted(res.per_strategy.items(), key=lambda x: -x[1]["pnl"]):
            print(f"  {k:22}{s['trades']:>7}{s['win_rate']:>7}{s['profit_factor']:>8}{s['pnl']:>12,.2f}")

    if res.per_symbol:
        print(line)
        print("  BY SYMBOL")
        print(f"  {'symbol':22}{'trades':>7}{'win%':>7}{'PF':>8}{'pnl':>12}")
        for k, s in sorted(res.per_symbol.items(), key=lambda x: -x[1]["pnl"]):
            print(f"  {k:22}{s['trades']:>7}{s['win_rate']:>7}{s['profit_factor']:>8}{s['pnl']:>12,.2f}")
    print(line)
