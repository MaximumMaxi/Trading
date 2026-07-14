# Trading System v2 — regime-switching multi-strategy bot

A multi-instrument trading system for MetaTrader 5. It detects each market's
**regime** (trending / ranging / volatile) and routes to the sub-strategy suited
to it, then backtests, walk-forward validates, and paper-trades the result.

Pipeline: **data → features → regime → strategies → router → backtest →
walk-forward → live/paper bot.**

## Validated edge (as of 2026-07)

Walk-forward on real Exness data left a small but genuinely out-of-sample edge:

| Instrument | Strategy | OOS avg R |
|---|---|---|
| US30 (Dow) | mean-reversion | +0.29 |
| AUDUSD | mean-reversion | +0.22 |
| BTCUSD | momentum | +0.07 (thin) |
| XAUUSD (Gold) | trend/momentum, strict H4 agreement | +0.26 |

S&P/Nasdaq mean-reversion was tested and **rejected** (never ranged). An
earlier plain-strategy gold-trend attempt was also rejected as an overfit
mirage; the strict-H4-agreement + wide-asymmetric-target variant above is a
different trade shape and holds up OOS (see `CLAUDE.md`). The locked universe
lives in `config/settings.py`.

## Who does what

- **Maxwell** — FX / strategy brain. Decides *what* to trade and *why*.
- **Melchi** — runs everything that touches real data or the broker: `data.loader`,
  backtests, walk-forwards, and the live bot. This is the machine with MT5 + the
  cached market data.
- The **GitHub repo is the shared source of truth.** Code flows via git; results
  and logs flow back via committed files or pasted output.

## Layout

```
config/       settings.py (locked config), instruments.py (per-symbol specs), secrets.py (git-ignored)
data/         loader.py — pull + cache OHLCV from MT5
mt5io/        connection.py (attach/login + data), execution.py (order placement)
regime/       detector.py — ADX + volatility regime labels
strategies/   trend / mean_reversion / breakout / momentum + shared indicators
ensemble/     router.py — regime + per-asset strategy gating
backtest/     engine.py (portfolio backtest), walk_forward.py, run.py, diagnose.py, plot.py
live/         bot.py — paper/live forward-test loop
```

## Setup (on the machine that will run it — Melchi's)

Requires **Windows** + the **MetaTrader 5 desktop terminal** installed and logged
into the account.

```powershell
git clone https://github.com/MaximumMaxi/Trading.git
cd Trading
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# credentials: copy the template and fill it in (git-ignored)
copy config\secrets.example.py config\secrets.py
notepad config\secrets.py
```

**Connecting to MT5:** easiest is to open the MT5 terminal and log into the
account manually, then leave `MT5_LOGIN = 0` in `secrets.py` — the bot will
*attach* to the running terminal (avoids the `-6 Authorization failed` you get
from re-logging-in over an active session). Or set real login/password/server to
have Python launch + log in itself.

## Quickstart

```powershell
python -m data.loader            # pull + cache OHLCV for all configured symbols
python -m backtest.run           # portfolio backtest on cached data
python -u -m backtest.walk_forward   # out-of-sample validation (-u = live output)
python backtest/diagnose.py logs/bt_trades.csv   # per-symbol/strategy edge (avg R)
python -m backtest.plot          # -> logs/equity_curve.html
python -m live.bot               # paper-trade (DRY_RUN=True by default: no orders)
```

Set `DRY_RUN = False` in `config/settings.py` to place real demo orders.

See **WORKFLOW.md** for how the team collaborates across two machines.

## Notes

- Broker symbols are Exness-style with an `m` suffix (`EURUSDm`, `XAUUSDm`, …).
- `secrets.py`, `specs.json`, `data/cache/*.csv`, and `*.log` are git-ignored —
  never commit credentials or broker data.
- P&L uses MT5 `tick_value`/`tick_size`, so gold/indices/oil/crypto/JPY all
  compute correctly, not just FX.
