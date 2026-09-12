#!/usr/bin/env python
"""Monthly rebalance runner for the cross-sectional momentum strategy.

Default is a dry run: it prints the plan and places nothing. Real orders
require --execute plus a typed confirmation.

    python -m momentum.live                    # show the plan
    python -m momentum.live --execute          # place real CNC orders
"""
import argparse
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bot.clock import IST, is_open
from bot.notify import build as build_notifier
from groww_client import connect
import momentum.backtest as mb
from momentum.backtest import select
from momentum.quality import screen
from momentum.universes import UNIVERSES, load as load_universe
from momentum.costs import buy_cost, sell_cost
from momentum.groups import group_of

STATE = Path(__file__).parent / "live_state.json"


def target_picks(px, lookback_m, skip_m, top_n, max_sector, max_group,
                 min_price=0.0):
    monthly = px.resample("ME").last()
    end_i = len(monthly) - 1 - skip_m
    start_i = end_i - lookback_m
    if start_i < 0:
        raise SystemExit("not enough price history")
    mom = (monthly.iloc[end_i] / monthly.iloc[start_i] - 1).dropna()
    current = monthly.iloc[-1].dropna()
    mom = mom[mom.index.isin(current.index)]
    ranked = list(mom.sort_values(ascending=False).index)
    bad = screen(px, px.index[-1], min_price=min_price) if min_price else set()
    picks = select(ranked, top_n, max_sector, max_group, excluded=bad)
    return picks, mom, bad


def current_holdings(g) -> dict[str, int]:
    raw = g.get_holdings_for_user()
    out = {}
    for h in raw.get("holdings") or []:
        qty = int(h.get("quantity") or 0)
        if qty:
            out[h.get("trading_symbol")] = qty
    return out


def live_prices(g, symbols):
    out = {}
    for chunk in [symbols[i:i+25] for i in range(0, len(symbols), 25)]:
        keys = tuple(f"NSE_{s}" for s in chunk)
        try:
            raw = g.get_ltp(exchange_trading_symbols=keys, segment="CASH")
            out.update({k.split("_", 1)[1]: v for k, v in raw.items() if v})
        except Exception as exc:
            print(f"  ! LTP fetch failed for {chunk[:3]}...: {exc}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=6)
    ap.add_argument("--skip", type=int, default=1)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--max-sector", type=int, default=3)
    ap.add_argument("--max-group", type=int, default=2)
    ap.add_argument("--capital", type=float,
                    help="portfolio size (default: available cash + holdings value)")
    ap.add_argument("--execute", action="store_true", help="place REAL orders")
    ap.add_argument("--universe", default="nifty100", choices=list(UNIVERSES),
                    help="which universe to rank")
    ap.add_argument("--regime-filter", action="store_true",
                    help="hold cash while NIFTY is below its 200-day average")
    ap.add_argument("--min-price", type=float, default=50.0,
                    help="exclude stocks below this price (0 disables)")
    ap.add_argument("--refresh", action="store_true", help="re-download price history")
    a = ap.parse_args()

    g = connect()
    notify = build_notifier()

    px, sectors = load_universe(a.universe)
    mb.SECTORS = sectors            # select() reads sector caps from here

    if a.regime_filter:
        import yfinance as yf
        n = yf.download("^NSEI", period="2y", progress=False, auto_adjust=True)["Close"]
        if hasattr(n, "columns"):
            n = n.iloc[:, 0]
        below = float(n.iloc[-1]) < float(n.rolling(200).mean().iloc[-1])
        if below:
            print(f"\nREGIME FILTER: NIFTY {float(n.iloc[-1]):,.0f} is BELOW its 200-day "
                  f"average {float(n.rolling(200).mean().iloc[-1]):,.0f}.")
            print("The rule says hold cash. Sell existing positions, buy nothing.")
            print("Re-run without --regime-filter to rebalance anyway.\n")
    picks, mom, screened = target_picks(px, a.lookback, a.skip, a.top,
                                        a.max_sector, a.max_group, a.min_price)

    held = current_holdings(g)
    prices = live_prices(g, sorted(set(picks) | set(held)))
    missing = [s for s in picks if s not in prices]
    if missing:
        print(f"! no live price for {missing} — they will be skipped\n")
        picks = [s for s in picks if s in prices]

    holdings_value = sum(q * prices.get(s, 0) for s, q in held.items())
    cash = float(g.get_available_margin_details().get("clear_cash") or 0)
    capital = a.capital if a.capital else cash + holdings_value
    per_slot = capital / max(len(picks), 1)

    print(f"\n{'='*70}")
    print(f"MOMENTUM REBALANCE  {datetime.now(IST):%Y-%m-%d %H:%M}  "
          f"({'LIVE' if a.execute else 'DRY RUN'})")
    print(f"{'='*70}")
    print(f"cash Rs {cash:,.2f} + holdings Rs {holdings_value:,.2f} "
          f"= capital Rs {capital:,.2f}")
    print(f"universe: {UNIVERSES[a.universe]['label']}")
    print(f"strategy: {a.lookback}-{a.skip} momentum, top {a.top}, "
          f"max {a.max_sector}/sector, {a.max_group}/group")
    print(f"target: {len(picks)} positions of ~Rs {per_slot:,.0f}\n")

    print(f"{'TARGET':<14}{'SECTOR':<22}{'MOM%':>8}{'PRICE':>10}{'QTY':>6}{'VALUE':>11}")
    print("-"*71)
    buys = {}
    for s in picks:
        p = prices[s]
        want = int(per_slot / p)
        have = held.get(s, 0)
        delta = want - have
        if delta > 0:
            buys[s] = delta
        print(f"{s:<14}{sectors.get(s,'?')[:21]:<22}{mom.get(s,0)*100:>7.1f}%"
              f"{p:>10,.1f}{want:>6}{want*p:>11,.0f}")

    sells = {s: q for s, q in held.items() if s not in picks}
    for s in picks:
        have, want = held.get(s, 0), int(per_slot / prices[s])
        if have > want:
            sells[s] = have - want

    print(f"\n{'ORDERS':<14}{'SIDE':<6}{'QTY':>6}{'PRICE':>10}{'VALUE':>11}{'COST':>9}")
    print("-"*57)
    total_cost = 0.0
    orders = []
    for s, q in sorted(sells.items()):
        v = q * prices.get(s, 0); c = sell_cost(v); total_cost += c
        orders.append((s, "SELL", q)); print(f"{s:<14}{'SELL':<6}{q:>6}{prices.get(s,0):>10,.1f}{v:>11,.0f}{c:>9,.0f}")
    for s, q in sorted(buys.items()):
        v = q * prices[s]; c = buy_cost(v); total_cost += c
        orders.append((s, "BUY", q)); print(f"{s:<14}{'BUY':<6}{q:>6}{prices[s]:>10,.1f}{v:>11,.0f}{c:>9,.0f}")

    if not orders:
        print("  (portfolio already matches target — nothing to do)")
        return 0
    print("-"*57)
    print(f"{'':<26}{len(orders)} orders{'':>14}{total_cost:>9,.0f}")
    print(f"\nestimated total cost: Rs {total_cost:,.2f} "
          f"({total_cost/capital*100:.3f}% of capital)")

    if not a.execute:
        print("\nDRY RUN — no orders placed. Re-run with --execute to trade.")
        return 0

    if not is_open():
        print("\n! Market is closed. Orders would be rejected. Aborting.")
        return 1

    print(f"\n*** This will place {len(orders)} REAL orders with REAL money ***")
    try:
        answer = input("Type REBALANCE to confirm: ").strip().upper()
    except EOFError:
        print("\n! No input available. Run this in an interactive terminal.")
        return 1
    if answer != "REBALANCE":
        print(f"aborted (you typed {answer!r}, expected 'REBALANCE')")
        return 1

    placed, failed = [], []
    for sym, side, qty in orders:
        try:
            r = g.place_order(trading_symbol=sym, transaction_type=side, quantity=qty,
                              order_type="MARKET", product="CNC", exchange="NSE",
                              segment="CASH", validity="DAY", price=0.0)
            oid = r.get("groww_order_id", "?")
            placed.append((sym, side, qty, oid))
            print(f"  OK   {side} {qty:>5} {sym:<14} order {oid}")
        except Exception as exc:
            failed.append((sym, side, qty, str(exc)[:60]))
            print(f"  FAIL {side} {qty:>5} {sym:<14} {exc}")

    msg = (f"\U0001f4c8 <b>Momentum rebalance</b>\n"
           f"{len(placed)} placed, {len(failed)} failed\n"
           + "\n".join(f"{s[1]} {s[2]} {s[0]}" for s in placed[:12]))
    notify.send(msg)
    STATE.write_text(pd.Series({"date": str(datetime.now(IST)), "picks": picks}).to_json())
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
