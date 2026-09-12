#!/usr/bin/env python
"""Cross-sectional momentum backtest on NSE, with realistic delivery costs.

Rule: each month, rank the universe by return over the lookback window
(skipping the most recent month to avoid short-term reversal), hold the top N
equal-weighted, rebalance monthly.
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

import json

from momentum.costs import buy_cost, sell_cost
from momentum.groups import group_of
from momentum.universe import NIFTY100

CACHE = Path(__file__).parent / "prices.parquet"
SECTORS = json.loads((Path(__file__).parent / "sectors.json").read_text()) \
    if (Path(__file__).parent / "sectors.json").exists() else {}


def select(ranked, top_n, max_per_sector=None, max_per_group=None, excluded=None):
    """Walk the ranked list, taking names until full, respecting caps.

    `excluded` drops names that failed a quality screen (penny prices, thin
    turnover) before ranking is applied.
    """
    excluded = excluded or set()
    picks, sec_count, grp_count = [], {}, {}
    for sym in ranked:
        if sym in excluded:
            continue
        if len(picks) >= top_n:
            break
        sec = SECTORS.get(sym, "Unknown")
        grp = group_of(sym)
        if max_per_sector and sec != "Unknown" and sec_count.get(sec, 0) >= max_per_sector:
            continue
        if max_per_group and grp_count.get(grp, 0) >= max_per_group:
            continue
        picks.append(sym)
        sec_count[sec] = sec_count.get(sec, 0) + 1
        grp_count[grp] = grp_count.get(grp, 0) + 1
    return picks


def load_prices(start="2013-01-01", end=None, refresh=False) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    tickers = [f"{s}.NS" for s in NIFTY100]
    print(f"downloading {len(tickers)} tickers from {start}...", file=sys.stderr)
    df = yf.download(tickers, start=start, end=end, progress=False, auto_adjust=True)["Close"]
    df.columns = [c.replace(".NS", "") for c in df.columns]
    df = df.dropna(axis=1, how="all")
    df.to_parquet(CACHE)
    return df


def backtest(px, lookback_m=6, skip_m=1, top_n=10, capital=200_000, min_history_m=12,
             max_per_sector=None, max_per_group=None):
    monthly = px.resample("ME").last()
    rets, dates, holdings_log = [], [], []
    equity = capital
    held: dict[str, float] = {}          # symbol -> rupee value at last rebalance

    lb, sk = lookback_m, skip_m
    for i in range(min_history_m, len(monthly) - 1):
        date = monthly.index[i]
        # momentum measured to `skip` months ago, over `lookback` months
        end_idx, start_idx = i - sk, i - sk - lb
        if start_idx < 0:
            continue
        window_end = monthly.iloc[end_idx]
        window_start = monthly.iloc[start_idx]
        mom = (window_end / window_start - 1).dropna()
        # only names with a valid current price
        current = monthly.iloc[i].dropna()
        mom = mom[mom.index.isin(current.index)]
        if len(mom) < top_n:
            continue
        ranked = list(mom.sort_values(ascending=False).index)
        picks = select(ranked, top_n, max_per_sector, max_per_group)
        if len(picks) < top_n:
            continue

        # --- costs of moving from `held` to `picks` ---
        target_value = equity / top_n
        cost = 0.0
        for sym in held:
            if sym not in picks:
                cost += sell_cost(held[sym])
        for sym in picks:
            if sym not in held:
                cost += buy_cost(target_value)
        equity -= cost

        # --- forward one month ---
        nxt = monthly.iloc[i + 1]
        fwd = []
        for sym in picks:
            if sym in nxt.index and not np.isnan(nxt[sym]) and not np.isnan(current[sym]):
                fwd.append(nxt[sym] / current[sym] - 1)
        if not fwd:
            continue
        period_ret = float(np.mean(fwd))
        equity *= (1 + period_ret)

        held = {s: equity / top_n for s in picks}
        rets.append(period_ret)
        dates.append(monthly.index[i + 1])
        holdings_log.append({"date": str(date.date()), "picks": picks})

    return pd.Series(rets, index=dates), equity, holdings_log


def metrics(rets: pd.Series, label: str, capital: float):
    if len(rets) < 12:
        return None
    cum = (1 + rets).cumprod()
    years = len(rets) / 12
    cagr = cum.iloc[-1] ** (1 / years) - 1
    vol = rets.std() * np.sqrt(12)
    sharpe = (rets.mean() * 12) / vol if vol else 0
    dd = float((cum / cum.cummax() - 1).min())
    wins = (rets > 0).mean()
    return {"label": label, "months": len(rets), "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "maxdd": dd, "win": wins,
            "final": capital * float(cum.iloc[-1])}


def show(m):
    if not m:
        print("  insufficient data"); return
    print(f"  {m['label']:<22}{m['months']:>5}mo  CAGR {m['cagr']*100:>6.2f}%  "
          f"vol {m['vol']*100:>5.1f}%  Sharpe {m['sharpe']:>5.2f}  "
          f"maxDD {m['maxdd']*100:>6.1f}%  win {m['win']*100:>4.0f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=6)
    ap.add_argument("--skip", type=int, default=1)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--capital", type=float, default=200_000)
    ap.add_argument("--max-sector", type=int, help="max holdings per sector")
    ap.add_argument("--max-group", type=int, help="max holdings per promoter group")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    px = load_prices(refresh=a.refresh)
    print(f"\nuniverse: {px.shape[1]} stocks, {px.index[0].date()} -> {px.index[-1].date()}")

    rets, final, log = backtest(px, a.lookback, a.skip, a.top, a.capital,
                                max_per_sector=a.max_sector, max_per_group=a.max_group)
    print(f"\nMomentum {a.lookback}-{a.skip}, top {a.top}, monthly rebalance, "
          f"Rs {a.capital:,.0f} start\n")
    show(metrics(rets, "STRATEGY (net)", a.capital))

    # benchmark: NIFTY 50
    bench = yf.download("^NSEI", start=str(px.index[0].date()), progress=False,
                        auto_adjust=True)["Close"]
    bm = bench.resample("ME").last().pct_change().dropna()
    bm = bm[bm.index.isin(rets.index)]
    if hasattr(bm, "columns"):
        bm = bm.iloc[:, 0]
    show(metrics(bm, "NIFTY 50 (buy & hold)", a.capital))

    # split-sample
    mid = len(rets) // 2
    print()
    show(metrics(rets.iloc[:mid], "  first half", a.capital))
    show(metrics(rets.iloc[mid:], "  second half", a.capital))

    print(f"\nfinal value: Rs {final:,.0f} from Rs {a.capital:,.0f}")
    print(f"latest picks: {', '.join(log[-1]['picks'])}" if log else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
