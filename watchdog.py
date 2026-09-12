#!/usr/bin/env python
"""Independent watchdog. Alerts if the bot dies or stalls during market hours.

Runs as its own process — a bot that has crashed cannot report its own death.
"""
import argparse
import subprocess
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from bot import clock, heartbeat
from bot.notify import build

CHECK_SECONDS = 120


def running_instances() -> set[str]:
    """Instance names of live run_bot.py processes, read from their argv.

    Uses `ps`, not `pgrep -a`: BSD/macOS pgrep has no -a flag and prints only
    PIDs, so argv parsing silently found nothing.
    """
    r = subprocess.run(["ps", "-Ao", "command="], capture_output=True, text=True)
    out = set()
    for line in r.stdout.splitlines():
        if "run_bot.py" not in line:
            continue
        parts = line.split()
        name = None
        for flag in ("--name", "--strategy"):
            if flag in parts:
                cand = parts[parts.index(flag) + 1]
                name = cand if flag == "--name" else (name or cand)
        # ps can briefly show a shell's unexpanded argv during startup;
        # ignore anything that is not a plain instance name
        if name and name.replace("_", "").replace("-", "").isalnum():
            out.add(name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-seconds", type=int, default=300,
                    help="heartbeat older than this during market hours = stall")
    ap.add_argument("--expect", nargs="*", default=[],
                    help="instance names that MUST be running during market hours")
    ap.add_argument("--grace", type=int, default=90,
                    help="seconds to wait at startup before alerting (bots may still be booting)")
    ap.add_argument("--strikes", type=int, default=2,
                    help="consecutive failed checks before alerting")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    notify = build()
    sys.stdout.reconfigure(line_buffering=True)
    print(f"watchdog started, expecting {a.expect or '(auto-detect only)'}")
    notify.send("\U0001f415 <b>Watchdog started</b>\nMonitoring the trading bot.")

    alerted_dead: set[str] = set()
    alerted_stale: set[str] = set()
    strikes_dead: dict[str, int] = {}
    strikes_stale: dict[str, int] = {}
    started = time.monotonic()
    while True:
        if clock.is_open():
            live = running_instances()
            beats = {d["instance"]: d for d in heartbeat.read_all()}
            # include expected instances so a bot that died before its
            # first heartbeat is still detected as missing
            watched = set(beats) | live | set(a.expect)
            bits = []

            for inst in sorted(watched):
                hb = beats.get(inst)
                if inst not in live:
                    strikes_dead[inst] = strikes_dead.get(inst, 0) + 1
                    warming = (time.monotonic() - started) < a.grace
                    if (not warming and strikes_dead[inst] >= a.strikes
                            and inst not in alerted_dead):
                        notify.send(f"\U0001f6a8 <b>{inst}: NOT RUNNING</b>\n"
                                    "Market is open but this bot's process is gone.")
                        alerted_dead.add(inst)
                    bits.append(f"{inst}=DEAD" + ("(warming)" if warming else
                                f"({strikes_dead[inst]})"))
                    continue
                strikes_dead[inst] = 0
                alerted_dead.discard(inst)
                if hb and hb["age_s"] > a.stale_seconds:
                    strikes_stale[inst] = strikes_stale.get(inst, 0) + 1
                    if (strikes_stale[inst] >= a.strikes
                            and (time.monotonic() - started) >= a.grace
                            and inst not in alerted_stale):
                        notify.send(f"\u26a0\ufe0f <b>{inst}: stalled</b>\nNo cycle for "
                                    f"{hb['age_s'] / 60:.0f} min (process alive). "
                                    "Machine sleep or a hung request?")
                        alerted_stale.add(inst)
                else:
                    strikes_stale[inst] = 0
                    alerted_stale.discard(inst)
                bits.append(f"{inst}={hb['age_s']:.0f}s" if hb else f"{inst}=no-hb")

            print(f"{clock.now():%H:%M:%S} " + (" ".join(bits) or "nothing to watch"))
        else:
            print(f"{clock.now():%H:%M:%S} market closed")

        if a.once:
            return 0
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
