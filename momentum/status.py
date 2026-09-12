#!/usr/bin/env python
"""Portfolio status: what you hold, what it's worth, how it's doing."""
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from bot.clock import IST
from groww_client import connect
from momentum.backtest import SECTORS


def main():
    g = connect()
    holdings = {}
    for h in g.get_holdings_for_user().get("holdings") or []:
        q = int(h.get("quantity") or 0)
        if q:
            holdings[h["trading_symbol"]] = (q, float(h.get("average_price") or 0))
    for p in g.get_positions_for_user().get("positions") or []:
        q = int(p.get("quantity") or p.get("net_quantity") or 0)
        sym = p.get("trading_symbol")
        if q and sym not in holdings:
            holdings[sym] = (q, float(p.get("net_price") or p.get("avg_price") or 0))

    if not holdings:
        print("No positions or holdings.")
        return 0

    syms = sorted(holdings)
    ltps = {}
    for chunk in [syms[i:i+25] for i in range(0, len(syms), 25)]:
        raw = g.get_ltp(exchange_trading_symbols=tuple(f"NSE_{s}" for s in chunk),
                        segment="CASH")
        ltps.update({k.split("_", 1)[1]: v for k, v in raw.items() if v})

    cash = float(g.get_available_margin_details().get("clear_cash") or 0)
    print(f"\nPORTFOLIO  {datetime.now(IST):%Y-%m-%d %H:%M}\n")
    print(f"{'STOCK':<13}{'SECTOR':<20}{'QTY':>5}{'AVG':>10}{'LTP':>10}"
          f"{'VALUE':>11}{'P&L':>10}{'P&L%':>8}")
    print("-"*87)
    tot_cost = tot_val = 0.0
    for s in syms:
        q, avg = holdings[s]
        ltp = ltps.get(s, avg)
        cost, val = q * avg, q * ltp
        tot_cost += cost; tot_val += val
        pl = val - cost
        print(f"{s:<13}{SECTORS.get(s,'?')[:19]:<20}{q:>5}{avg:>10,.1f}{ltp:>10,.1f}"
              f"{val:>11,.0f}{pl:>+10,.0f}{(pl/cost*100 if cost else 0):>+7.2f}%")
    print("-"*87)
    pl = tot_val - tot_cost
    print(f"{'TOTAL':<58}{tot_val:>11,.0f}{pl:>+10,.0f}"
          f"{(pl/tot_cost*100 if tot_cost else 0):>+7.2f}%")
    print(f"\ninvested Rs {tot_cost:,.0f} | cash Rs {cash:,.0f} | "
          f"portfolio Rs {tot_val + cash:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
