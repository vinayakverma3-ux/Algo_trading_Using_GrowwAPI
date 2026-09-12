"""Selectable universes for the momentum strategy."""
import json
from pathlib import Path

import pandas as pd

DIR = Path(__file__).parent

UNIVERSES = {
    "nifty100": {"prices": "prices.parquet", "sectors": "sectors.json",
                 "label": "NIFTY 100 (large cap)"},
    "midcap":   {"prices": "prices_mid100.parquet", "sectors": "sectors_mid.json",
                 "label": "NIFTY Midcap 100"},
}


def load(name: str):
    """Return (prices DataFrame, sector map) for a named universe."""
    if name not in UNIVERSES:
        raise SystemExit(f"unknown universe {name!r}; choose from {list(UNIVERSES)}")
    cfg = UNIVERSES[name]
    px = pd.read_parquet(DIR / cfg["prices"])
    sec_file = DIR / cfg["sectors"]
    sectors = json.loads(sec_file.read_text()) if sec_file.exists() else {}
    return px, sectors
