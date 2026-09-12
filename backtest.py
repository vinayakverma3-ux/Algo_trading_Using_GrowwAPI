#!/usr/bin/env python
"""Replay a strategy over historical intraday bars, after real costs.

Honest simulation: entries fill at the bar close, stops/targets check the
NEXT bar's high/low, and every position is force-closed at session end.
"""
import argparse
import statistics as st
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

from bot.clock import IST
from bot.data import MarketData
from groww_client import connect
from strategies.rules import REGISTRY

BROKERAGE_CAP = 20.0


def round_trip_cost(buy_val: float, sell_val: float) -> float:
    brok = min(BROKERAGE_CAP, 0.001 * buy_val) + min(BROKERAGE_CAP, 0.001 * sell_val)
    stt = 0.00025 * sell_val
    stamp = 0.00003 * buy_val
    exch = 0.0000297 * (buy_val + sell_val)
    sebi = 0.000001 * (buy_val + sell_val)
    gst = 0.18 * (brok + exch + sebi)
    return brok + stt + stamp + exch + sebi + gst


def run_symbol(bars, strat, capital):
    """Simulate one symbol. Returns a list of closed trades."""
    by_day = defaultdict(list)
    for b in bars:
        by_day[b.ts.date()].append(b)

    trades = []
    for day, day_bars in sorted(by_day.items()):
        pos = None
        for i in range(len(day_bars)):
            bar = day_bars[i]
            if pos:
                # stop checked before target: assume the worse fill when both are touched
                if bar.low <= pos["stop"]:
                    trades.append(close(pos, pos["stop"], bar.ts, "stop"))
                    pos = None
                elif bar.high >= pos["target"]:
                    trades.append(close(pos, pos["target"], bar.ts, "target"))
                    pos = None
                continue
            entry = strat.decide(day_bars[: i + 1])
            if entry:
                price = bar.close
                qty = int(capital / price)
                if qty:
                    pos = {"entry": price, "qty": qty, "stop": entry.stop,
                           "target": entry.target, "ts": bar.ts, "reason": entry.reason}
        if pos:  # force square-off at session close
            trades.append(close(pos, day_bars[-1].close, day_bars[-1].ts, "eod"))
    return trades


def close(pos, exit_price, ts, why):
    buy_val = pos["entry"] * pos["qty"]
    sell_val = exit_price * pos["qty"]
    cost = round_trip_cost(buy_val, sell_val)
    return {
        "entry": pos["entry"], "exit": exit_price, "qty": pos["qty"],
        "gross": sell_val - buy_val, "cost": cost,
        "net": sell_val - buy_val - cost, "why": why, "ts": ts,
    }


def report(name, all_trades, capital):
    if not all_trades:
        print(f"\n{name}: no trades triggered.")
        return
    nets = [t["net"] for t in all_trades]
    wins = [n for n in nets if n > 0]
    total = sum(nets)
    gross = sum(t["gross"] for t in all_trades)
    costs = sum(t["cost"] for t in all_trades)
    exits = defaultdict(int)
    for t in all_trades:
        exits[t["why"]] += 1

    # equity curve max drawdown
    peak = cum = dd = 0.0
    for n in nets:
        cum += n
        peak = max(peak, cum)
        dd = min(dd, cum - peak)

    print(f"\n{'=' * 58}\n{name}\n{'=' * 58}")
    print(f"  trades            {len(all_trades)}")
    print(f"  win rate          {len(wins) / len(nets) * 100:.1f}%")
    print(f"  gross P&L         Rs {gross:>12,.2f}")
    print(f"  costs             Rs {costs:>12,.2f}")
    print(f"  NET P&L           Rs {total:>12,.2f}   ({total / capital * 100:+.2f}% on Rs {capital:,.0f})")
    print(f"  avg trade         Rs {st.mean(nets):>12,.2f}")
    print(f"  best / worst      Rs {max(nets):>12,.2f} / Rs {min(nets):,.2f}")
    print(f"  max drawdown      Rs {dd:>12,.2f}")
    print(f"  exits             " + ", ".join(f"{k}={v}" for k, v in sorted(exits.items())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="orb", choices=list(REGISTRY))
    ap.add_argument("--symbols", nargs="+", default=["TCS", "HCLTECH", "TECHM", "BAJFINANCE", "VEDL"])
    ap.add_argument("--capital", type=float, default=200_000)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--interval", default="MIN_15")
    ap.add_argument("--target", type=float, default=1.0)
    ap.add_argument("--stop", type=float, default=0.5)
    a = ap.parse_args()

    strat = REGISTRY[a.strategy](target_pct=a.target, stop_pct=a.stop)
    md = MarketData(connect())

    print(f"Backtest: {strat.name} | {a.interval} | {a.days}d | "
          f"target {a.target}% stop {a.stop}% | Rs {a.capital:,.0f} per trade")

    everything = []
    for sym in a.symbols:
        bars = md.history(sym, a.interval, a.days)
        if len(bars) < 20:
            print(f"  {sym}: only {len(bars)} bars, skipped", file=sys.stderr)
            continue
        trades = run_symbol(bars, strat, a.capital)
        everything += trades
        net = sum(t["net"] for t in trades)
        wr = (sum(1 for t in trades if t["net"] > 0) / len(trades) * 100) if trades else 0
        print(f"  {sym:<12} {len(bars):>4} bars  {len(trades):>3} trades  "
              f"win {wr:>5.1f}%  net Rs {net:>10,.2f}")

    report(f"{strat.name} — all symbols combined", everything, a.capital)
    print("\nOne symbol at a time, one position each. Past behaviour is not a forecast.")


if __name__ == "__main__":
    main()
