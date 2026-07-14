"""
live/bot.py — paper-trading forward test of the validated v2 system.

Runs the EXACT same router/strategies/params as the backtest, on live MT5 data.
Acts once per newly-closed H1 bar. Defaults to DRY_RUN (logs signals, places no
orders) so you can confirm behavior before letting it trade the demo account.

    python -m live.bot          # DRY_RUN per settings (safe: no orders)

To place real demo orders, set DRY_RUN = False in config/settings.py.
Stop with Ctrl+C (graceful).

Prereqs: the MT5 desktop terminal must be OPEN and logged into the demo account
(the bot attaches to it). Requires cached specs.json (run data.loader once).
"""

import csv
import logging
import os
import signal
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.engine import calc_volume
from config import settings
from config.instruments import load_specs
from ensemble.router import EnsembleRouter
from mt5io.connection import connect, disconnect, get_ohlcv, get_account_info
from mt5io.execution import place_market_order, has_open_position, open_positions
from regime.detector import RegimeConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(os.path.join(os.path.dirname(__file__), "..", "logs", "live.log"))],
)
log = logging.getLogger("bot")

_running = True


def _stop(sig, frame):
    global _running
    log.info("Shutdown requested — finishing current cycle...")
    _running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def _build_router() -> EnsembleRouter:
    cfg = RegimeConfig(adx_trend=settings.ADX_TREND)
    return EnsembleRouter(
        regime_cfg=cfg, atr_sl_mult=settings.ATR_SL_MULT,
        atr_tp_mult=settings.ATR_TP_MULT, min_rr=settings.MIN_RR_RATIO,
        strategy_by_category=settings.STRATEGY_BY_CATEGORY,
        require_confluence=settings.REQUIRE_CONFLUENCE,
        category_overrides=settings.CATEGORY_PARAMS)


def _journal(row: dict):
    path = os.path.abspath(settings.TRADE_JOURNAL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


class PaperBot:
    def __init__(self):
        self.router = _build_router()
        self.specs = load_specs()
        self.symbols = settings.ALL_SYMBOLS
        self.last_bar = {}   # symbol -> last processed H1 bar time

    def start(self):
        mode = "DRY-RUN (no orders)" if settings.DRY_RUN else "LIVE ORDERS (demo)"
        log.info("=" * 58)
        log.info(f"  PAPER BOT STARTING — {mode}")
        log.info(f"  Symbols: {self.symbols}")
        log.info(f"  Map: {settings.STRATEGY_BY_CATEGORY}")
        log.info("=" * 58)
        if not connect(settings.MT5_LOGIN, settings.MT5_PASSWORD,
                       settings.MT5_SERVER, settings.MT5_PATH):
            log.critical("Could not connect/attach to MT5. Is the terminal open & logged in?")
            sys.exit(1)
        acc = get_account_info()
        if acc:
            log.info(f"Account {acc['login']} | {acc['balance']} {acc['currency']} "
                     f"| equity {acc['equity']}")
            self._sizing_check(acc["equity"])

    def _sizing_check(self, equity: float):
        """
        Warn if the account is too small for clean risk sizing: if the minimum
        lot (0.01) on any symbol would risk more than RISK_PER_TRADE% of equity,
        the bot is forced to over-risk. Uses live ATR x the category's SL multiple
        to estimate a typical stop distance.
        """
        target = equity * settings.RISK_PER_TRADE / 100.0
        log.info(f"Sizing check — target risk/trade = {settings.RISK_PER_TRADE}% "
                 f"(~{target:.2f}) at equity {equity:.2f}")
        any_warn = False
        for sym in self.symbols:
            spec = self.specs.get(sym)
            if spec is None:
                continue
            h1 = get_ohlcv(sym, settings.SIGNAL_TF, 60)
            if h1 is None or len(h1) < 15:
                log.warning(f"  {sym}: no data for sizing check — skipped")
                continue
            hi, lo, cl = h1["high"], h1["low"], h1["close"]
            tr = pd.concat([hi - lo, (hi - cl.shift()).abs(),
                            (lo - cl.shift()).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            if not atr or atr <= 0:
                continue
            sl_mult = settings.CATEGORY_PARAMS.get(spec.category, {}).get(
                "atr_sl_mult", settings.ATR_SL_MULT)
            sl_dist = sl_mult * atr
            min_risk = spec.pnl(sl_dist, spec.min_lot)
            pct = min_risk / equity * 100 if equity else 0
            if min_risk > target + 1e-9:
                any_warn = True
                need = min_risk * 100 / settings.RISK_PER_TRADE
                log.warning(f"  {sym}: min-lot ({spec.min_lot}) risks ~{min_risk:.2f} "
                            f"({pct:.2f}% > {settings.RISK_PER_TRADE}%) — needs equity "
                            f">= ~{need:.0f} for clean sizing")
            else:
                log.info(f"  {sym}: OK — min-lot risk ~{min_risk:.2f} "
                         f"({pct:.2f}% <= {settings.RISK_PER_TRADE}%)")
        if any_warn:
            log.warning("Some symbols OVER-RISK at min lot on this balance — "
                        "raise the balance or drop those symbols.")

    def run(self):
        self.start()
        while _running:
            try:
                self._cycle()
            except Exception as e:
                log.error(f"cycle error: {e}", exc_info=True)
            for _ in range(settings.LOOP_SECONDS):
                if not _running:
                    break
                time.sleep(1)
        disconnect()
        log.info("Bot stopped.")

    def _cycle(self):
        acc = get_account_info()
        if not acc:
            log.warning("no account info — skipping cycle")
            return
        equity = acc["equity"]
        positions = open_positions(settings.MAGIC_NUMBER)
        open_count = len(positions)

        for sym in self.symbols:
            spec = self.specs.get(sym)
            if spec is None:
                continue
            h1 = get_ohlcv(sym, settings.SIGNAL_TF, settings.LIVE_BARS)
            h4 = get_ohlcv(sym, settings.BIAS_TF, settings.LIVE_BARS)
            if h1 is None or h4 is None or len(h1) < 250:
                continue

            h1 = h1.iloc[:-1]    # drop the still-forming bar → completed bars only
            bar_time = h1["time"].iloc[-1]
            if self.last_bar.get(sym) == bar_time:
                continue          # already handled this bar
            self.last_bar[sym] = bar_time

            df = self.router.prepare(h1, h4, category=spec.category)
            sig = self.router.route(len(df) - 1, df, sym, spec)
            if sig is None:
                continue

            log.info(f"SIGNAL {sym} {sig.direction} [{sig.strategy}/{sig.regime}] "
                     f"entry={sig.entry:.5f} sl={sig.sl:.5f} tp={sig.tp:.5f} "
                     f"rr={sig.rr} | {sig.reasons[0] if sig.reasons else ''}")

            # ── gates ──
            if has_open_position(sym, settings.MAGIC_NUMBER):
                log.info(f"  skip {sym}: already have an open position")
                continue
            if open_count >= settings.MAX_OPEN_TRADES:
                log.info(f"  skip {sym}: max open trades ({open_count})")
                continue

            vol = calc_volume(equity, settings.RISK_PER_TRADE, sig.entry, sig.sl, spec)

            record = {
                "time": str(bar_time), "symbol": sym, "direction": sig.direction,
                "strategy": sig.strategy, "regime": sig.regime,
                "entry_ref": round(sig.entry, 5), "sl": round(sig.sl, 5),
                "tp": round(sig.tp, 5), "volume": vol, "rr": sig.rr,
                "dry_run": settings.DRY_RUN, "ticket": "", "result": "",
            }

            if settings.DRY_RUN:
                log.info(f"  [DRY-RUN] would {sig.direction} {vol} {sym}")
                record["result"] = "DRY_RUN"
            else:
                res = place_market_order(
                    sym, sig.direction, vol, sig.sl, sig.tp,
                    settings.MAGIC_NUMBER, settings.ORDER_COMMENT,
                    settings.DEVIATION_POINTS)
                if res["success"]:
                    open_count += 1
                    record["ticket"] = res.get("ticket", "")
                    record["result"] = "FILLED"
                    log.info(f"  ORDER FILLED {sym} {sig.direction} {vol} @ {res.get('price')}")
                else:
                    record["result"] = f"REJECTED:{res.get('retcode', res.get('error'))}"
                    log.warning(f"  ORDER FAILED {sym}: {record['result']}")

            _journal(record)


if __name__ == "__main__":
    PaperBot().run()
