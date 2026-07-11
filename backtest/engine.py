"""
backtest/engine.py — multi-instrument, portfolio-level backtester.

All symbols trade against ONE shared equity curve, so risk limits
(max_open_trades, daily loss, drawdown halt) apply at the account level the way
they would live. P&L and position sizing use SymbolSpec.pnl(), so gold, indices,
oil, BTC and JPY pairs are all correct — not just FX.

Signal source is the EnsembleRouter. Entries are throttled: one open position
per symbol, a global max, and a per-symbol cooldown (raw signals are chatty).

Event model (no look-ahead):
  * a signal on bar i is computed from the CLOSE of bar i and entered at that
    close (+ spread);
  * exits are only evaluated on later bars, because at each timestamp we check
    exits on already-open positions BEFORE opening any new position.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.instruments import SymbolSpec
from ensemble.router import EnsembleRouter


@dataclass
class Trade:
    symbol:      str
    strategy:    str
    regime:      str
    direction:   str
    entry_time:  object
    entry_price: float
    sl:          float
    tp:          float
    volume:      float
    risk_usd:    float
    exit_time:   object = None
    exit_price:  float = None
    pnl:         float = 0.0
    status:      str = "OPEN"      # OPEN / TP_HIT / SL_HIT / CLOSED_EOD
    mae:         float = 0.0       # worst adverse price excursion
    mfe:         float = 0.0       # best favorable price excursion
    bars_held:   int = 0


@dataclass
class PortfolioResult:
    initial_capital: float
    final_equity:    float
    total_return_pct: float
    total_trades:    int
    win_rate:        float
    profit_factor:   float
    max_drawdown_pct: float
    sharpe:          float
    sortino:         float
    calmar:          float
    expectancy:      float
    trades:          List[Trade] = field(default_factory=list)
    equity_curve:    List[float] = field(default_factory=list)
    per_symbol:      Dict[str, dict] = field(default_factory=dict)
    per_strategy:    Dict[str, dict] = field(default_factory=dict)
    halted:          bool = False


def calc_volume(equity: float, risk_pct: float, entry: float, sl: float,
                spec: SymbolSpec) -> float:
    """Lot size so that hitting SL loses ~risk_pct of equity. Uses spec.pnl."""
    risk_usd = equity * risk_pct / 100.0
    dist = abs(entry - sl)
    loss_per_lot = spec.pnl(dist, 1.0)
    if loss_per_lot <= 0:
        return spec.min_lot
    raw = risk_usd / loss_per_lot
    steps = round(raw / spec.lot_step) if spec.lot_step else raw
    vol = steps * spec.lot_step if spec.lot_step else raw
    return round(min(max(vol, spec.min_lot), spec.max_lot), 8)


class PortfolioBacktestEngine:
    def __init__(self, initial_capital: float = 10_000.0, risk_pct: float = 1.0,
                 max_open_trades: int = 5, daily_loss_limit: float = 3.0,
                 max_drawdown_halt: float = 25.0, commission_per_lot: float = 3.5,
                 cooldown_bars: int = 6):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.max_open_trades = max_open_trades
        self.daily_loss_limit = daily_loss_limit
        self.max_drawdown_halt = max_drawdown_halt
        self.commission_per_lot = commission_per_lot
        self.cooldown_bars = cooldown_bars

    # ------------------------------------------------------------------
    def run(self, symbol_data: Dict[str, dict], router: EnsembleRouter,
            entry_start=None, entry_end=None) -> PortfolioResult:
        """
        symbol_data: {symbol: {"h1": df, "h4": df, "spec": SymbolSpec}}
        Prepares each symbol, generates signals, then runs one shared simulation.

        entry_start / entry_end (timestamps, optional): only OPEN positions whose
        bar time falls in [entry_start, entry_end]. Any position still open on the
        first bar after entry_end is force-closed, so a window is self-contained
        (essential for honest walk-forward: no trade leaks across the boundary).
        Indicators/regime are still computed on the FULL frame, so a windowed run
        has proper warm-up rather than 200 dead bars at the window start.
        """
        entry_start = pd.Timestamp(entry_start) if entry_start is not None else None
        entry_end = pd.Timestamp(entry_end) if entry_end is not None else None
        prepared: Dict[str, pd.DataFrame] = {}
        specs:    Dict[str, SymbolSpec] = {}
        signals_by_i: Dict[str, Dict[int, object]] = {}
        events: List[tuple] = []   # (time, symbol, i)

        for sym, d in symbol_data.items():
            spec = d["spec"]
            df = router.prepare(d["h1"], d["h4"]).reset_index(drop=True)
            prepared[sym] = df
            specs[sym] = spec
            sig_map = {i: sig for i, sig in router.generate_all(df, sym, spec)}
            signals_by_i[sym] = sig_map
            for i in range(len(df)):
                events.append((df.at[i, "time"], sym, i))

        # chronological event stream across all symbols
        events.sort(key=lambda e: (e[0], e[1]))

        equity = self.initial_capital
        peak = equity
        equity_curve = [equity]
        trades: List[Trade] = []
        open_pos: Dict[str, Trade] = {}
        last_entry_i: Dict[str, int] = {}
        daily_pnl: Dict[str, float] = {}
        halted = False

        for ts, sym, i in events:
            df = prepared[sym]
            spec = specs[sym]
            row = df.iloc[i]
            day = str(ts)[:10]

            # ── 1. manage an open position on this symbol at this bar ──
            if sym in open_pos:
                t = open_pos[sym]
                t.bars_held += 1
                high, low = row["high"], row["low"]
                closed = False
                if t.direction == "BUY":
                    t.mae = min(t.mae, low - t.entry_price)
                    t.mfe = max(t.mfe, high - t.entry_price)
                    if low <= t.sl:
                        t.exit_price, t.status, closed = t.sl, "SL_HIT", True
                    elif high >= t.tp:
                        t.exit_price, t.status, closed = t.tp, "TP_HIT", True
                else:  # SELL
                    t.mae = min(t.mae, t.entry_price - high)
                    t.mfe = max(t.mfe, t.entry_price - low)
                    if high >= t.sl:
                        t.exit_price, t.status, closed = t.sl, "SL_HIT", True
                    elif low <= t.tp:
                        t.exit_price, t.status, closed = t.tp, "TP_HIT", True

                # force-close at the window boundary if not hit by SL/TP
                if not closed and entry_end is not None and ts > entry_end:
                    t.exit_price, t.status, closed = row["close"], "CLOSED_EOD", True

                if closed:
                    move = (t.exit_price - t.entry_price) if t.direction == "BUY" \
                        else (t.entry_price - t.exit_price)
                    t.pnl = spec.pnl(move, t.volume) - self.commission_per_lot * t.volume
                    t.exit_time = ts
                    equity += t.pnl
                    peak = max(peak, equity)
                    daily_pnl[day] = daily_pnl.get(day, 0.0) + t.pnl
                    equity_curve.append(equity)
                    trades.append(t)
                    del open_pos[sym]

            # ── 2. drawdown halt (blocks new entries, lets opens finish) ──
            if not halted and peak > 0 and (peak - equity) / peak * 100 >= self.max_drawdown_halt:
                halted = True
            if halted:
                continue

            # ── 3. entry gates ──
            # outside the entry window? (after window with nothing open -> done)
            if entry_end is not None and ts > entry_end:
                if not open_pos:
                    break
                continue
            if entry_start is not None and ts < entry_start:
                continue
            if sym in open_pos:
                continue
            if len(open_pos) >= self.max_open_trades:
                continue
            # daily loss limit
            if abs(min(daily_pnl.get(day, 0.0), 0.0)) / max(equity, 1) * 100 >= self.daily_loss_limit:
                continue
            # cooldown
            if sym in last_entry_i and (i - last_entry_i[sym]) < self.cooldown_bars:
                continue

            sig = signals_by_i[sym].get(i)
            if sig is None:
                continue

            # ── 4. open position (apply spread to entry) ──
            spread_px = spec.typical_spread_points * spec.point
            entry = sig.entry + spread_px if sig.direction == "BUY" else sig.entry - spread_px
            vol = calc_volume(equity, self.risk_pct, entry, sig.sl, spec)
            risk_usd = spec.pnl(abs(entry - sig.sl), vol)

            open_pos[sym] = Trade(
                symbol=sym, strategy=sig.strategy, regime=sig.regime,
                direction=sig.direction, entry_time=ts, entry_price=entry,
                sl=sig.sl, tp=sig.tp, volume=vol, risk_usd=risk_usd,
            )
            last_entry_i[sym] = i

        # ── force-close leftovers at their last available close ──
        for sym, t in list(open_pos.items()):
            df = prepared[sym]
            last = df.iloc[-1]
            move = (last["close"] - t.entry_price) if t.direction == "BUY" \
                else (t.entry_price - last["close"])
            t.pnl = specs[sym].pnl(move, t.volume) - self.commission_per_lot * t.volume
            t.exit_price, t.exit_time, t.status = last["close"], last["time"], "CLOSED_EOD"
            equity += t.pnl
            equity_curve.append(equity)
            trades.append(t)

        return self._compile(trades, equity_curve, halted)

    # ------------------------------------------------------------------
    def _compile(self, trades, equity_curve, halted) -> PortfolioResult:
        cap = self.initial_capital
        if not trades:
            return PortfolioResult(cap, cap, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                   trades=[], equity_curve=equity_curve, halted=halted)

        def stats(ts_list):
            wins = [t for t in ts_list if t.pnl > 0]
            losses = [t for t in ts_list if t.pnl <= 0]
            gp = sum(t.pnl for t in wins)
            gl = abs(sum(t.pnl for t in losses))
            wr = len(wins) / len(ts_list) * 100 if ts_list else 0
            pf = gp / gl if gl > 0 else float("inf")
            avg_w = np.mean([t.pnl for t in wins]) if wins else 0
            avg_l = np.mean([t.pnl for t in losses]) if losses else 0
            exp = (wr / 100 * avg_w) + ((1 - wr / 100) * avg_l)
            return dict(trades=len(ts_list), pnl=round(sum(t.pnl for t in ts_list), 2),
                        win_rate=round(wr, 1), profit_factor=round(pf, 3),
                        expectancy=round(exp, 2))

        eq = np.array(equity_curve, dtype=float)
        peak = np.maximum.accumulate(eq)
        dd = (peak - eq)
        max_dd_pct = round((dd / peak).max() * 100, 2) if len(eq) else 0
        rets = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([0.0])
        sharpe = round(rets.mean() / rets.std() * np.sqrt(252), 3) if rets.std() > 0 else 0
        neg = rets[rets < 0]
        sortino = round(rets.mean() / neg.std() * np.sqrt(252), 3) if len(neg) and neg.std() > 0 else 0
        ret_pct = (eq[-1] / cap - 1) * 100
        calmar = round(ret_pct / max_dd_pct, 3) if max_dd_pct > 0 else 0

        overall = stats(trades)
        per_symbol, per_strategy = {}, {}
        for key in {t.symbol for t in trades}:
            per_symbol[key] = stats([t for t in trades if t.symbol == key])
        for key in {t.strategy for t in trades}:
            per_strategy[key] = stats([t for t in trades if t.strategy == key])

        return PortfolioResult(
            initial_capital=cap, final_equity=round(eq[-1], 2),
            total_return_pct=round(ret_pct, 2), total_trades=overall["trades"],
            win_rate=overall["win_rate"], profit_factor=overall["profit_factor"],
            max_drawdown_pct=max_dd_pct, sharpe=sharpe, sortino=sortino,
            calmar=calmar, expectancy=overall["expectancy"],
            trades=trades, equity_curve=equity_curve,
            per_symbol=per_symbol, per_strategy=per_strategy, halted=halted,
        )
