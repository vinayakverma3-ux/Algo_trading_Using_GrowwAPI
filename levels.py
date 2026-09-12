#!/usr/bin/env python
"""Position planner: size, stop distance and key levels for each stock.

Sizing and stop distances are computed from each stock's own volatility.
This does NOT predict direction — it tells you how big to go and where the
structure is, once you have decided to trade something.
"""
import argparse
import statistics as st
import sys
import warnings

warnings.filterwarnings("ignore")

from bot.data import MarketData
from groww_client import connect


def atr(bars, n=14):
    """Average true range — the stock's typical daily movement in rupees."""
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return st.mean(trs[-n:]) if len(trs) >= n else (st.mean(trs) if trs else 0)


def analyse(md, sym, capital, risk_pct, cap_pct, target_pct):
    bars = md.history_daily(sym, days=90) if hasattr(md, "history_daily") else None
    bars = md.history(sym, "DAY", 90)
    if len(bars) < 20:
        return None
    price = bars[-1].close
    a = atr(bars)
    highs = [b.high for b in bars[-20:]]
    lows = [b.low for b in bars[-20:]]
    resistance, support = max(highs), min(lows)

    # stop one ATR below entry, floored at the 20-day low if that is nearer
    atr_stop = price - a
    stop = max(atr_stop, support) if support < price else atr_stop
    stop_pct = (price - stop) / price * 100

    risk_amt = capital * risk_pct / 100
    per_share = price - stop
    qty_risk = int(risk_amt / per_share) if per_share > 0 else 0
    qty_cap = int(capital * cap_pct / 100 / price)
    qty = min(qty_risk, qty_cap)

    target = price * (1 + target_pct / 100)
    rr = (target - price) / per_share if per_share > 0 else 0

    return {
        "sym": sym, "price": price, "atr": a, "atr_pct": a / price * 100,
        "support": support, "resistance": resistance,
        "stop": stop, "stop_pct": stop_pct,
        "qty": qty, "value": qty * price, "risk": qty * per_share,
        "target": target, "rr": rr,
        "capped": qty_cap < qty_risk,
        "room_to_resistance": (resistance - price) / price * 100,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+",
                    default=["TCS", "HCLTECH", "TECHM", "BAJFINANCE", "VEDL"])
    ap.add_argument("--capital", type=float, default=200_000)
    ap.add_argument("--risk", type=float, default=1.0, help="%% of capital risked")
    ap.add_argument("--max-position", type=float, default=20.0, help="%% cap per position")
    ap.add_argument("--target", type=float, default=1.0)
    a = ap.parse_args()

    md = MarketData(connect())
    rows = [r for r in (analyse(md, s, a.capital, a.risk, a.max_position, a.target)
                        for s in a.symbols) if r]
    if not rows:
        print("no data"); return 1

    print(f"\nPosition plan — capital Rs {a.capital:,.0f}, risk {a.risk}%/trade "
          f"(Rs {a.capital*a.risk/100:,.0f}), cap {a.max_position}%/position\n")
    print(f"{'STOCK':<12}{'PRICE':>9}{'ATR%':>7}{'STOP':>9}{'STOP%':>7}"
          f"{'QTY':>6}{'VALUE':>11}{'RISK':>8}{'TARGET':>9}{'R:R':>6}")
    print("-" * 84)
    for r in rows:
        flag = "*" if r["capped"] else " "
        print(f"{r['sym']:<12}{r['price']:>9,.1f}{r['atr_pct']:>7.2f}{r['stop']:>9,.1f}"
              f"{r['stop_pct']:>7.2f}{r['qty']:>6}{r['value']:>11,.0f}"
              f"{r['risk']:>8,.0f}{r['target']:>9,.1f}{r['rr']:>6.2f}{flag}")
    print("-" * 84)
    print("* = size limited by the position cap, not by risk\n")

    print(f"{'STOCK':<12}{'20D SUPPORT':>13}{'20D RESIST':>13}{'ROOM UP':>10}")
    print("-" * 48)
    for r in rows:
        print(f"{r['sym']:<12}{r['support']:>13,.1f}{r['resistance']:>13,.1f}"
              f"{r['room_to_resistance']:>9.1f}%")
    print("\nATR% = typical daily move. STOP = 1 ATR below price, or the 20-day")
    print("low if nearer. R:R below 1.0 means the target is closer than the stop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
