#!/usr/bin/env python
"""Intraday feasibility screener.

Answers: for a given target %, which liquid stocks historically move enough
intraday to hit it, and how often. Does NOT predict direction.
"""
import argparse
import statistics as st
import sys
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

from bot.clock import IST
from groww_client import connect

# Liquid NSE large/mid caps commonly used for intraday
UNIVERSE = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK",
    "KOTAKBANK", "ITC", "LT", "BHARTIARTL", "HINDUNILVR", "MARUTI", "TITAN",
    "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "ADANIENT",
    "ADANIPORTS", "BAJFINANCE", "BAJAJFINSV", "WIPRO", "HCLTECH", "TECHM",
    "SUNPHARMA", "CIPLA", "DRREDDY", "ONGC", "COALINDIA", "NTPC", "POWERGRID",
    "GRASIM", "ULTRACEMCO", "SHRIRAMFIN", "INDUSINDBK", "BPCL", "IOC",
    "TATACONSUM", "ASIANPAINT", "NESTLEIND", "DIVISLAB", "EICHERMOT",
    "HEROMOTOCO", "BAJAJ-AUTO", "M&M", "APOLLOHOSP", "BRITANNIA", "SBILIFE",
]


def analyse(g, symbol, days, target_pct, capital):
    end = datetime.now(IST)
    start = end - timedelta(days=days)
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        raw = g.get_historical_candles(
            exchange="NSE", segment="CASH", groww_symbol=f"NSE-{symbol}",
            start_time=start.strftime(fmt), end_time=end.strftime(fmt),
            candle_interval="DAY",
        )
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc)[:40]}

    rows = [r for r in (raw.get("candles") or []) if r[4]]
    if len(rows) < 15:
        return {"symbol": symbol, "error": f"only {len(rows)} bars"}

    ranges, turnovers, closes = [], [], []
    for _, _o, h, l, c, v, *_ in rows:
        if not all(x is not None for x in (h, l, c)) or c <= 0:
            continue
        ranges.append((h - l) / c * 100)
        turnovers.append(c * (v or 0))
        closes.append(c)

    if not ranges:
        return {"symbol": symbol, "error": "no usable bars"}

    price = closes[-1]
    hit = sum(1 for r in ranges if r >= target_pct) / len(ranges) * 100
    med_turnover = st.median(turnovers)
    qty = int(capital / price)
    # capital as a share of median daily traded value — impact proxy
    impact_bps = (capital / med_turnover) * 10_000 if med_turnover else float("inf")

    return {
        "symbol": symbol,
        "price": price,
        "avg_range": st.mean(ranges),
        "med_range": st.median(ranges),
        "hit_rate": hit,
        "turnover_cr": med_turnover / 1e7,
        "qty": qty,
        "impact_bps": impact_bps,
        "bars": len(ranges),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=200_000)
    ap.add_argument("--target", type=float, default=1.0, help="target %% move")
    ap.add_argument("--days", type=int, default=85, help="lookback (API caps ~3 months)")
    a = ap.parse_args()

    g = connect()
    rows, errors = [], []
    for i, sym in enumerate(UNIVERSE, 1):
        r = analyse(g, sym, a.days, a.target, a.capital)
        (errors if "error" in r else rows).append(r)
        print(f"\r  scanning {i}/{len(UNIVERSE)} {sym:14}", end="", file=sys.stderr)
        time.sleep(0.15)
    print("\r" + " " * 40 + "\r", end="", file=sys.stderr)

    rows.sort(key=lambda r: r["hit_rate"], reverse=True)
    print(f"\nIntraday feasibility — capital Rs {a.capital:,.0f}, target {a.target}%, "
          f"{a.days}d lookback\n")
    print(f"{'SYMBOL':<13}{'PRICE':>9}{'DAYS>=T':>9}{'AVGRNG':>8}{'MEDRNG':>8}"
          f"{'TURNOVER':>10}{'QTY':>7}{'IMPACT':>8}")
    print(f"{'':13}{'':>9}{'%':>9}{'%':>8}{'%':>8}{'Rs cr':>10}{'':>7}{'bps':>8}")
    print("-" * 72)
    for r in rows:
        print(f"{r['symbol']:<13}{r['price']:>9,.1f}{r['hit_rate']:>9.0f}"
              f"{r['avg_range']:>8.2f}{r['med_range']:>8.2f}"
              f"{r['turnover_cr']:>10,.0f}{r['qty']:>7}{r['impact_bps']:>8.1f}")
    if errors:
        print(f"\nskipped: {', '.join(e['symbol'] for e in errors)}")
    print(f"\n{len(rows)} scanned. DAYS>=T = % of sessions whose high-low range "
          f"covered {a.target}%.")
    print("Range is not direction: it says a move was available, not which way.")


if __name__ == "__main__":
    main()
