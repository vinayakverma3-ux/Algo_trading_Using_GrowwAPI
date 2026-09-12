#!/usr/bin/env python
"""Side-by-side results for every strategy instance that has run."""
import csv
import json
import warnings

warnings.filterwarnings("ignore")

from bot import paths
from bot.heartbeat import read_all


def main():
    beats = {d["instance"]: d for d in read_all()}
    # include live instances that have not traded yet, so an idle-but-healthy
    # bot shows as running rather than as "never started"
    instances = {f.name.replace("_state.json", "")
                 for f in paths.LOGS.glob("*_state.json")} | set(beats)
    rows = []
    for inst in sorted(instances):
        state_file = paths.state(inst)
        st = (json.loads(state_file.read_text()) if state_file.exists()
              else {"cash": beats.get(inst, {}).get("equity", 0.0), "positions": {}})
        tf = paths.trades(inst)
        trades = list(csv.DictReader(tf.open())) if tf.exists() else []
        buys = [t for t in trades if t["side"] == "BUY"]
        sells = [t for t in trades if t["side"] == "SELL"]
        equity = beats.get(inst, {}).get("equity")
        rows.append({
            "instance": inst,
            "cash": st["cash"],
            "open_pos": len(st["positions"]),
            "buys": len(buys),
            "sells": len(sells),
            "equity": equity,
            "hb_age": beats.get(inst, {}).get("age_s"),
        })

    if not rows:
        print("No strategy instances found.")
        print("Start them with:  ./start_trading.sh")
        return

    print(f"{'INSTANCE':<12}{'EQUITY':>13}{'CASH':>13}{'OPEN':>6}"
          f"{'BUYS':>6}{'SELLS':>7}{'LAST CYCLE':>12}")
    print("-" * 69)
    for r in rows:
        eq = f"{r['equity']:,.2f}" if r["equity"] is not None else "-"
        age = f"{r['hb_age']:.0f}s ago" if r["hb_age"] is not None else "never"
        print(f"{r['instance']:<12}{eq:>13}{r['cash']:>13,.2f}{r['open_pos']:>6}"
              f"{r['buys']:>6}{r['sells']:>7}{age:>12}")
    print("\nEquity = cash + open positions marked to market.")


if __name__ == "__main__":
    main()
