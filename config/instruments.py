"""
config/instruments.py — per-instrument specifications.

Two sources, in priority order:
  1. Live from MT5 (build_specs_from_mt5) — authoritative; cached to specs.json.
  2. FALLBACK_SPECS below — documented approximations for ICMarkets-style feeds,
     used only for offline development/planning. NOT accurate enough for live P&L.

Always refresh from MT5 before trusting backtest currency figures.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_SPECS_FILE = os.path.join(os.path.dirname(__file__), "specs.json")


@dataclass
class SymbolSpec:
    symbol: str
    category: str            # fx_majors / metals / indices / energy / crypto
    digits: int
    point: float             # smallest price increment
    pip: float               # conventional "pip" (10 * point for 3/5-digit FX)
    tick_size: float         # for P&L: profit = move/tick_size * tick_value * lot
    tick_value: float        # account-currency value of one tick per 1.0 lot
    contract_size: float
    min_lot: float
    lot_step: float
    max_lot: float
    typical_spread_points: float

    def price_to_pips(self, price_move: float) -> float:
        return price_move / self.pip if self.pip else 0.0

    def pnl(self, price_move: float, volume: float) -> float:
        """Account-currency P&L for a directional price move at `volume` lots."""
        if self.tick_size <= 0:
            return 0.0
        return (price_move / self.tick_size) * self.tick_value * volume


# ─── Fallback approximations (offline only) ───────────────────────────────────
# category, digits, point, pip, tick_size, tick_value($/lot), contract, min, step, max, spread(pts)
_FB = [
    # FX majors — 5-digit, 1 pip = 0.0001, tick 0.00001 ≈ $1/lot
    ("EURUSD", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 1.0,  100_000, 0.01, 0.01, 100, 8),
    ("GBPUSD", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 1.0,  100_000, 0.01, 0.01, 100, 10),
    ("AUDUSD", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 1.0,  100_000, 0.01, 0.01, 100, 9),
    ("NZDUSD", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 1.0,  100_000, 0.01, 0.01, 100, 12),
    # USD-base pairs: tick_value depends on quote ccy; ~$1/lot is a rough stand-in
    ("USDCHF", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 1.1,  100_000, 0.01, 0.01, 100, 12),
    ("USDCAD", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 0.75, 100_000, 0.01, 0.01, 100, 12),
    # JPY quote — 3-digit, 1 pip = 0.01, tick 0.001 ≈ $0.67/lot (varies w/ USDJPY)
    ("USDJPY", "fx_majors", 3, 1e-3, 1e-2, 1e-3, 0.67, 100_000, 0.01, 0.01, 100, 10),
    # FX crosses (range-prone MR candidates) — tick_value ~quote ccy, MT5 overrides live
    ("EURGBP", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 1.27, 100_000, 0.01, 0.01, 100, 12),
    ("EURCHF", "fx_majors", 5, 1e-5, 1e-4, 1e-5, 1.10, 100_000, 0.01, 0.01, 100, 15),
    # Metals — XAUUSD 2-digit, 1.00 move = $100/lot (contract 100 oz)
    ("XAUUSD", "metals",    2, 1e-2, 1e-2, 1e-2, 1.0,  100,     0.01, 0.01, 50,  20),
    # Indices — US30 contract 1, tick_value = tick_size*contract = 0.1  (1.0 pt = $1/lot)
    ("US30",   "indices",   1, 1e-1, 1e-1, 1e-1, 0.1,  1,       0.1,  0.1,  50,  200),
    # Energy — USOIL contract 1000, 0.01 move = $10/lot
    ("USOIL",  "energy",    2, 1e-2, 1e-2, 1e-2, 10.0, 1_000,   0.01, 0.01, 50,  30),
    # Crypto — BTCUSD contract 1, tick_value = tick_size*contract = 0.01  (1.00 move = $1/lot)
    ("BTCUSD", "crypto",    2, 1e-2, 1e-2, 1e-2, 0.01, 1,       0.01, 0.01, 10,  5000),
]

FALLBACK_SPECS: Dict[str, SymbolSpec] = {
    r[0]: SymbolSpec(
        symbol=r[0], category=r[1], digits=r[2], point=r[3], pip=r[4],
        tick_size=r[5], tick_value=r[6], contract_size=r[7],
        min_lot=r[8], lot_step=r[9], max_lot=r[10], typical_spread_points=r[11],
    )
    for r in _FB
}

_CATEGORY_OF = {s.symbol: s.category for s in FALLBACK_SPECS.values()}


def _pip_for(digits: int, point: float) -> float:
    """Conventional pip: 10x point for 3/5-digit FX, else the point itself."""
    return point * 10 if digits in (3, 5) else point


def _category_for(sym: str) -> str:
    """Match a broker symbol (possibly suffixed, e.g. EURUSDm) to a category."""
    for base, cat in _CATEGORY_OF.items():
        if sym == base or sym.startswith(base):
            return cat
    return "unknown"


def build_specs_from_mt5(symbols, get_symbol_spec_fn, save: bool = True
                         ) -> Dict[str, SymbolSpec]:
    """
    Query MT5 for each symbol and build authoritative SymbolSpecs.
    `get_symbol_spec_fn` is mt5io.connection.get_symbol_spec.
    Falls back to FALLBACK_SPECS for any symbol MT5 can't resolve.
    """
    specs: Dict[str, SymbolSpec] = {}
    for sym in symbols:
        raw = get_symbol_spec_fn(sym)
        if raw is None:
            if sym in FALLBACK_SPECS:
                logger.warning(f"{sym}: using FALLBACK spec (MT5 lookup failed).")
                specs[sym] = FALLBACK_SPECS[sym]
            continue
        specs[sym] = SymbolSpec(
            symbol=raw["symbol"],
            category=_category_for(sym),
            digits=raw["digits"],
            point=raw["point"],
            pip=_pip_for(raw["digits"], raw["point"]),
            tick_size=raw["tick_size"],
            tick_value=raw["tick_value"],
            contract_size=raw["contract_size"],
            min_lot=raw["min_lot"],
            lot_step=raw["lot_step"],
            max_lot=raw["max_lot"],
            typical_spread_points=raw["spread_points"],
        )
    if save and specs:
        merged = {}
        if os.path.exists(_SPECS_FILE):
            with open(_SPECS_FILE) as f:
                merged = json.load(f)
        merged.update({k: asdict(v) for k, v in specs.items()})
        with open(_SPECS_FILE, "w") as f:
            json.dump(merged, f, indent=2)
        logger.info(f"Saved {len(specs)} specs (merged; {len(merged)} total) to {_SPECS_FILE}")
    return specs


def load_specs() -> Dict[str, SymbolSpec]:
    """Load cached specs.json if present, else fall back to approximations."""
    if os.path.exists(_SPECS_FILE):
        with open(_SPECS_FILE) as f:
            data = json.load(f)
        return {k: SymbolSpec(**v) for k, v in data.items()}
    logger.warning("specs.json not found — using FALLBACK_SPECS (offline mode).")
    return dict(FALLBACK_SPECS)
