"""
backtest/plot.py — dependency-free equity-curve plotter.

Renders a self-contained HTML file (inline SVG, no libraries, no CDN) with:
  * portfolio equity curve over time
  * underwater / drawdown curve
  * headline stats + per-strategy and per-symbol P&L tables

    python -m backtest.plot                       # reads logs/bt_trades.csv
    python -m backtest.plot path/to/trades.csv    # explicit file

Or from code:
    from backtest.plot import plot_result
    plot_result(res, out="logs/equity_curve.html")   # res = PortfolioResult
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings


# ─── data prep ─────────────────────────────────────────────────────────────
def _trades_to_frame(trades) -> pd.DataFrame:
    """Accept a list of Trade dataclasses or a DataFrame; normalize columns."""
    if isinstance(trades, pd.DataFrame):
        df = trades.copy()
    else:
        df = pd.DataFrame([t.__dict__ for t in trades])
    if df.empty:
        return df
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df = df.sort_values("exit_time").reset_index(drop=True)
    return df


def _equity_series(df: pd.DataFrame, initial: float):
    """Return (times, equity, drawdown_pct) built from realized trade P&L."""
    eq = initial + df["pnl"].cumsum()
    eq = pd.concat([pd.Series([initial]), eq], ignore_index=True)
    peak = eq.cummax()
    dd = (eq - peak) / peak * 100.0     # <= 0
    t0 = df["exit_time"].iloc[0]
    times = [t0] + list(df["exit_time"])
    return times, eq.tolist(), dd.tolist()


# ─── SVG helpers ───────────────────────────────────────────────────────────
def _poly(xs, ys):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


def _map_x(times, x0, w):
    v = [pd.Timestamp(t).value for t in times]
    lo, hi = min(v), max(v)
    span = (hi - lo) or 1
    return [x0 + (t - lo) / span * w for t in v]


def _map_y(vals, y_top, h, vmin=None, vmax=None):
    vmin = min(vals) if vmin is None else vmin
    vmax = max(vals) if vmax is None else vmax
    span = (vmax - vmin) or 1
    return [y_top + h - (val - vmin) / span * h for val in vals], vmin, vmax


# ─── render ────────────────────────────────────────────────────────────────
def render_html(df: pd.DataFrame, initial: float, title: str = "Equity Curve") -> str:
    if df.empty:
        return "<p>No trades to plot.</p>"

    times, eq, dd = _equity_series(df, initial)
    final = eq[-1]
    ret_pct = (final / initial - 1) * 100
    max_dd = min(dd)
    wins = df[df["pnl"] > 0]
    wr = len(wins) / len(df) * 100
    gp = df.loc[df["pnl"] > 0, "pnl"].sum()
    gl = abs(df.loc[df["pnl"] <= 0, "pnl"].sum())
    pf = gp / gl if gl > 0 else float("inf")

    W, H0 = 960, 40                       # canvas width, top margin
    PW = 860                              # plot width
    X0 = 80
    EH, DH = 300, 130                     # equity height, drawdown height
    eq_top = H0
    dd_top = H0 + EH + 60

    xs = _map_x(times, X0, PW)
    eys, ymin, ymax = _map_y(eq, eq_top, EH)
    dys, dmin, _ = _map_y(dd, dd_top, DH, vmin=min(dd), vmax=0)

    # equity gridlines (5 levels)
    grid = []
    for i in range(5):
        val = ymin + (ymax - ymin) * i / 4
        gy = eq_top + EH - (val - ymin) / ((ymax - ymin) or 1) * EH
        grid.append((gy, val))

    zero_dd_y = dd_top + DH - (0 - dmin) / ((0 - dmin) or 1) * DH
    color = "#16a34a" if ret_pct >= 0 else "#dc2626"

    def _table(d, keycol):
        rows = []
        agg = d.groupby(keycol)["pnl"].agg(["count", "sum"]).sort_values("sum", ascending=False)
        for name, r in agg.iterrows():
            w = d[(d[keycol] == name) & (d["pnl"] > 0)].shape[0]
            wrr = w / r["count"] * 100 if r["count"] else 0
            pnl_c = "#16a34a" if r["sum"] >= 0 else "#dc2626"
            rows.append(
                f"<tr><td>{name}</td><td>{int(r['count'])}</td>"
                f"<td>{wrr:.0f}%</td>"
                f"<td style='color:{pnl_c}'>{r['sum']:,.2f}</td></tr>")
        return "".join(rows)

    date_lbls = "".join(
        f'<text x="{xs[i]:.0f}" y="{eq_top+EH+18}" class="ax" text-anchor="middle">'
        f'{str(times[i])[:10]}</text>'
        for i in [0, len(times) // 2, len(times) - 1])

    grid_svg = "".join(
        f'<line x1="{X0}" y1="{gy:.0f}" x2="{X0+PW}" y2="{gy:.0f}" class="grid"/>'
        f'<text x="{X0-8}" y="{gy+4:.0f}" class="ax" text-anchor="end">{val:,.0f}</text>'
        for gy, val in grid)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{title}</title><style>
  body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;background:#fff;color:#111}}
  @media (prefers-color-scheme:dark){{body{{background:#0d1117;color:#e6edf3}}
    .card{{background:#161b22;border-color:#30363d}} .grid{{stroke:#30363d}} .ax{{fill:#8b949e}}
    th{{color:#8b949e}} td{{border-color:#21262d}}}}
  h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#888;font-size:13px;margin-bottom:16px}}
  .stats{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}}
  .card{{border:1px solid #e5e7eb;border-radius:10px;padding:10px 14px;min-width:110px}}
  .card .k{{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.04em}}
  .card .v{{font-size:19px;font-weight:600;margin-top:2px}}
  .grid{{stroke:#eee;stroke-width:1}} .ax{{fill:#999;font-size:11px}}
  .wrap{{overflow-x:auto}} svg{{max-width:100%;height:auto}}
  .tables{{display:flex;gap:28px;flex-wrap:wrap;margin-top:8px}}
  table{{border-collapse:collapse;font-size:13px}} th,td{{text-align:right;padding:4px 10px;border-bottom:1px solid #eee}}
  th:first-child,td:first-child{{text-align:left}} h3{{font-size:13px;margin:0 0 6px;color:#888}}
</style></head><body>
<h1>Portfolio Equity Curve</h1>
<div class="sub">{str(times[0])[:10]} &rarr; {str(times[-1])[:10]} &middot; {len(df)} trades</div>
<div class="stats">
  <div class="card"><div class="k">Final Equity</div><div class="v">{final:,.0f}</div></div>
  <div class="card"><div class="k">Return</div><div class="v" style="color:{color}">{ret_pct:+.1f}%</div></div>
  <div class="card"><div class="k">Max Drawdown</div><div class="v" style="color:#dc2626">{max_dd:.1f}%</div></div>
  <div class="card"><div class="k">Win Rate</div><div class="v">{wr:.0f}%</div></div>
  <div class="card"><div class="k">Profit Factor</div><div class="v">{pf:.2f}</div></div>
  <div class="card"><div class="k">Trades</div><div class="v">{len(df)}</div></div>
</div>
<div class="wrap"><svg viewBox="0 0 {W} {dd_top+DH+40}" xmlns="http://www.w3.org/2000/svg">
  {grid_svg}
  <polyline fill="none" stroke="{color}" stroke-width="2" points="{_poly(xs, eys)}"/>
  <line x1="{X0}" y1="{eys[0]:.0f}" x2="{X0+PW}" y2="{eys[0]:.0f}" stroke="#bbb" stroke-dasharray="4 4"/>
  {date_lbls}
  <text x="{X0}" y="{dd_top-14}" class="ax" font-weight="600">Drawdown %</text>
  <line x1="{X0}" y1="{zero_dd_y:.0f}" x2="{X0+PW}" y2="{zero_dd_y:.0f}" class="grid"/>
  <text x="{X0-8}" y="{zero_dd_y+4:.0f}" class="ax" text-anchor="end">0%</text>
  <text x="{X0-8}" y="{dd_top+DH:.0f}" class="ax" text-anchor="end">{dmin:.0f}%</text>
  <polygon fill="#dc2626" fill-opacity="0.15" points="{X0},{zero_dd_y:.0f} {_poly(xs, dys)} {X0+PW},{zero_dd_y:.0f}"/>
  <polyline fill="none" stroke="#dc2626" stroke-width="1.5" points="{_poly(xs, dys)}"/>
</svg></div>
<div class="tables">
  <div><h3>BY STRATEGY</h3><table>
    <tr><th>strategy</th><th>trades</th><th>win%</th><th>pnl</th></tr>{_table(df, 'strategy')}</table></div>
  <div><h3>BY SYMBOL</h3><table>
    <tr><th>symbol</th><th>trades</th><th>win%</th><th>pnl</th></tr>{_table(df, 'symbol')}</table></div>
</div>
</body></html>"""


# ─── entry points ──────────────────────────────────────────────────────────
def plot_result(res, out="logs/equity_curve.html", initial=None):
    initial = initial if initial is not None else res.initial_capital
    df = _trades_to_frame(res.trades)
    return _write(df, initial, out)


def plot_csv(csv_path, out="logs/equity_curve.html", initial=None):
    initial = initial if initial is not None else settings.INITIAL_CAPITAL
    df = _trades_to_frame(pd.read_csv(csv_path))
    return _write(df, initial, out)


def _write(df, initial, out):
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render_html(df, initial))
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(__file__), "..", "logs", "bt_trades.csv")
    if not os.path.exists(path):
        print(f"No trades file at {path}. Run `python -m backtest.run` first.")
    else:
        plot_csv(path)
