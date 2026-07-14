# CLAUDE.md — project context for any Claude session

Read this first. It captures the decisions and gotchas so any Claude instance
(any machine/account that clones this repo) can continue the work. See also
`README.md` (setup) and `WORKFLOW.md` (team process).

## What this is
A regime-switching, multi-instrument MT5 trading system:
**data → features → regime → strategies → router → backtest → walk-forward →
live/paper bot.** Goal: combine trend / mean-reversion / breakout / momentum by
routing each asset to the strategy that fits its character, validated
out-of-sample, then paper-traded on a demo before anything real.

## Team model (see WORKFLOW.md)
- **Maxwell** = FX/strategy brain; this machine is the dev/repo hub where Claude runs.
- **Melchi** = runs ALL execution (data.loader, backtest, walk_forward, diagnose,
  live.bot) — his machine has MT5 + the real cached data.
- **Claude runs only on Maxwell's machine and cannot access Melchi's files** (separate
  computer, zero access). Bridge = this git repo (code) + Melchi pasting/committing results.
- To let Claude run real backtests on Maxwell's machine, manually copy `data/cache/`
  + `config/specs.json` over (kept out of git).

## Validated edge (out-of-sample, walk-forward)
The locked universe in `config/settings.py`:
| Instrument | Strategy | OOS avg R |
|---|---|---|
| US30m (Dow) | mean_reversion_bb | +0.29 |
| AUDUSDm | mean_reversion_bb | +0.22 |
| BTCUSDm | momentum_macd_roc | +0.07 (thin, asymmetric — works in downtrends) |

Locked params: `ATR_SL_MULT=2.0, ATR_TP_MULT=3.0, ADX_TREND=28.0,
REQUIRE_CONFLUENCE=False, MIN_RR=1.5`. Walk-forward: 4/4 folds profitable, OOS
PF ~1.25, ~46% win. **Treat +100% headline skeptically** — universe was chosen
with full-sample knowledge (selection bias); real expectation is lower.

## Rejected (don't redo these — already tested and failed OOS)
- **Gold (XAU) trend**: +0.26 in-sample → +0.02 OOS = overfit mirage.
- **S&P/Nasdaq (US500/USTEC) mean-reversion**: ~0 trades — they trend, rarely range.
- **Momentum on FX majors**: consistently negative; momentum is confirmation-grade,
  not a standalone FX entry.
- **Efficient FX majors (EUR/GBP/CHF/JPY/NZD)**: no edge even with confluence filter.
- **Breakout**: too few trades / noisy — parked.

## Gotchas (hard-won — respect these)
- **Broker = Exness demo; symbols carry an `m` suffix** (`EURUSDm`, `XAUUSDm`, `US30m`…).
- **MT5 connection: attach-first.** Open the terminal + log in manually, leave
  `MT5_LOGIN=0` → Python attaches. Passing creds over an already-logged-in session
  gives `-6 Authorization failed`. The MT5 terminal MUST be running for the Python API.
- **P&L uses MT5 `tick_value`/`tick_size`** → correct for gold/indices/oil/crypto/JPY,
  not just FX. Never hardcode pip value.
- **Dollar-PnL per strategy is confounded by the equity path** (size scales with
  equity). Use **avg R** (`pnl/risk_usd`, via `backtest/diagnose.py`) as the true
  size-independent edge metric.
- **Windows console is cp1252** — reports/print use ASCII only (no box-drawing chars).
- **stdout is block-buffered** off-TTY — use `python -u` to watch live progress.
- **partial `data.loader SYM` used to clobber specs.json** — now merges; still prefer
  full `python -m data.loader`.

## Current status & next steps
- Phase 1 complete + walk-forward validated. Live paper bot built (`live/bot.py`,
  `DRY_RUN=True` default = logs signals, no orders).
- **Now: forward-test on the demo** — run `live.bot`, confirm signals, flip
  `DRY_RUN=False`, collect weeks of demo fills vs backtest (~46% win / +0.25R).
- Later: Phase 2 ML meta-filter (needs scikit-learn); maybe broaden MR to
  range-bound FX crosses (EURGBP/EURCHF).

## Conventions
- Never commit `secrets.py`, `specs.json`, `data/cache/*`, or logs (gitignored).
- `config/settings.py` is the shared control panel — flag changes in commit messages.
- Melchi owns the `DRY_RUN` flag (flip to live only on his machine, intentionally).
