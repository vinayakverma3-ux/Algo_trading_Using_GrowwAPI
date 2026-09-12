#!/usr/bin/env python
"""Entrypoint. Paper mode by default; live requires an explicit flag."""
import argparse
import logging
import sys
from pathlib import Path

from bot.config import Config
from bot.engine import Engine
from groww_client import connect
from strategies.live import LiveRule


def main() -> int:
    # line-buffer stdout so redirected logs stay current on disk
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description="Groww automated trading bot")
    ap.add_argument("--live", action="store_true", help="send REAL orders (real money)")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    ap.add_argument("--symbols", nargs="+", help="override the universe")
    ap.add_argument("--test-alert", action="store_true", help="send a test alert and exit")
    ap.add_argument("--strategy", default="vwap", choices=["orb", "vwap", "sma", "delta"])
    ap.add_argument("--name", help="instance name (default: the strategy name)")
    ap.add_argument("--target", type=float, default=1.0, help="target %%")
    ap.add_argument("--stop", type=float, default=0.5, help="stop-loss %%")
    ap.add_argument("--min-ratio", type=float,
                    help="vwap only: require pending buy/sell qty ratio above this")
    ap.add_argument("--entry-z", type=float, help="delta only: z-score to trigger a buy")
    ap.add_argument("--exit-z", type=float, help="delta only: z-score to exit early")
    ap.add_argument("--stream", action="store_true",
                    help="use the WebSocket depth feed instead of REST polling")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-12s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    if args.test_alert:
        from bot.notify import build
        n = build()
        ok = n.send("\U0001f514 <b>Test alert</b>\nGroww bot alert channel is working.")
        print("alert sent" if ok and n.enabled else
              "no Telegram configured — check logs/ (run setup_telegram.py first)")
        return 0 if ok else 1

    cfg = Config(paper=not args.live, instance=args.name or args.strategy,
                 stream_depth=args.stream)
    if args.symbols:
        cfg.universe = args.symbols

    if args.live:
        print("\n*** LIVE MODE — this places REAL orders with REAL money ***")
        print(f"    universe={cfg.universe} product={cfg.product}")
        print(f"    strategy={args.strategy} target={args.target}% stop={args.stop}%")
        print(f"    max {cfg.max_open_positions} positions, "
              f"{cfg.risk_per_trade_pct}% risk/trade, "
              f"halt at -{cfg.max_daily_loss_pct}% daily")
        if input("\nType LIVE to confirm: ").strip() != "LIVE":
            print("aborted")
            return 1

    params = {"target_pct": args.target, "stop_pct": args.stop}
    if args.min_ratio is not None:
        if args.strategy != "vwap":
            print("--min-ratio only applies to the vwap strategy")
            return 1
        params["min_buy_sell_ratio"] = args.min_ratio
    for flag, key in (("entry_z", "entry_z"), ("exit_z", "exit_z")):
        val = getattr(args, flag)
        if val is not None:
            if args.strategy != "delta":
                print(f"--{flag.replace('_', '-')} only applies to the delta strategy")
                return 1
            params[key] = val
    strat = LiveRule(args.strategy, instance=cfg.instance, **params)
    Engine(cfg, connect(), strat).run(once=args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
