#!/usr/bin/env python
"""Momentum backtest with share-level accounting and capital gains tax.

The plain backtest tracks equity as one number, which cannot model tax: tax
depends on when each lot was bought and sold. This version tracks shares,
cost basis and entry dates per position, realises gains on every sale, and
pays tax at each financial year end.
"""
import argparse
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from momentum.backtest import load_prices, metrics, select, show
from momentum.costs import buy_cost, sell_cost
from momentum.tax import LONG_TERM_DAYS, financial_year, tax_due


def run(px, lookback_m=6, skip_m=1, top_n=10, capital=200_000,
        max_sector=3, max_group=2, apply_tax=True, min_history_m=12,
        rebalance_every=1, offset=0):
    monthly = px.resample("ME").last()
    cash = capital
    pos: dict[str, dict] = {}      # sym -> {shares, cost, entry}
    stcg = ltcg = 0.0
    fy = None
    tax_paid = 0.0
    curve, dates = [], []

    for i in range(min_history_m, len(monthly)):
        date = monthly.index[i]
        price = monthly.iloc[i]

        # --- pay tax when the financial year rolls over ---
        this_fy = financial_year(date)
        if fy is None:
            fy = this_fy
        elif this_fy != fy:
            if apply_tax:
                t = tax_due(stcg, ltcg)
                cash -= t
                tax_paid += t
            stcg = ltcg = 0.0
            fy = this_fy

        held_value = sum(p["shares"] * price.get(s, np.nan) for s, p in pos.items()
                         if not np.isnan(price.get(s, np.nan)))
        equity = cash + held_value
        curve.append(equity)
        dates.append(date)

        if i >= len(monthly) - 1:
            break
        # only rebalance every Nth month; otherwise just mark to market
        if (i - min_history_m - offset) % rebalance_every != 0:
            continue

        end_i, start_i = i - skip_m, i - skip_m - lookback_m
        if start_i < 0:
            continue
        mom = (monthly.iloc[end_i] / monthly.iloc[start_i] - 1).dropna()
        valid = price.dropna()
        mom = mom[mom.index.isin(valid.index)]
        if len(mom) < top_n:
            continue
        picks = select(list(mom.sort_values(ascending=False).index),
                       top_n, max_sector, max_group)
        if len(picks) < top_n:
            continue
        target = equity / top_n

        # --- sell: full exits and trims down to target weight ---
        for s in list(pos):
            p_now = price.get(s)
            if p_now is None or np.isnan(p_now):
                continue
            cur_val = pos[s]["shares"] * p_now
            want = target if s in picks else 0.0
            if cur_val <= want + 1e-6:
                continue
            sell_val = cur_val - want
            frac = sell_val / cur_val
            cost_sold = pos[s]["cost"] * frac
            gain = sell_val - cost_sold
            if (date - pos[s]["entry"]).days > LONG_TERM_DAYS:
                ltcg += gain
            else:
                stcg += gain
            cash += sell_val - sell_cost(sell_val)
            pos[s]["shares"] *= (1 - frac)
            pos[s]["cost"] -= cost_sold
            if pos[s]["shares"] < 1e-9:
                del pos[s]

        # --- buy: top up to target weight ---
        for s in picks:
            p_now = price.get(s)
            if p_now is None or np.isnan(p_now):
                continue
            cur_val = pos[s]["shares"] * p_now if s in pos else 0.0
            need = target - cur_val
            if need <= 1e-6:
                continue
            spend = min(need, max(0.0, cash - buy_cost(need)))
            if spend <= 1:
                continue
            c = buy_cost(spend)
            cash -= spend + c
            if s in pos:
                pos[s]["shares"] += spend / p_now
                pos[s]["cost"] += spend
            else:
                pos[s] = {"shares": spend / p_now, "cost": spend, "entry": date}

    eq = pd.Series(curve, index=dates)
    return eq.pct_change().dropna(), eq.iloc[-1], tax_paid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=6)
    ap.add_argument("--skip", type=int, default=1)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--max-sector", type=int, default=3)
    ap.add_argument("--max-group", type=int, default=2)
    ap.add_argument("--capital", type=float, default=200_000)
    a = ap.parse_args()

    px = load_prices()
    print(f"\nMomentum {a.lookback}-{a.skip}, top {a.top}, "
          f"max {a.max_sector}/sector {a.max_group}/group, Rs {a.capital:,.0f}\n")

    for label, taxed in (("PRE-TAX  (as backtested before)", False),
                         ("POST-TAX (STCG 20% / LTCG 12.5%)", True)):
        rets, final, tax = run(px, a.lookback, a.skip, a.top, a.capital,
                               a.max_sector, a.max_group, apply_tax=taxed)
        m = metrics(rets, label, a.capital)
        show(m)
        print(f"  {'':<22}final Rs {final:,.0f}"
              + (f"   tax paid Rs {tax:,.0f}" if taxed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
