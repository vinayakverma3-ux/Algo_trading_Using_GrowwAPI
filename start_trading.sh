#!/usr/bin/env bash
# Launch one or more paper strategies side by side, plus the watchdog.
#
#   ./start_trading.sh                  all three (orb, vwap, sma)
#   ./start_trading.sh vwap             just one
#   ./start_trading.sh vwap orb         a subset
#
# caffeinate holds the machine awake. Keep the lid OPEN and stay plugged in.
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
STRATS=("$@")
[ ${#STRATS[@]} -eq 0 ] && STRATS=(orb vwap sma)

mkdir -p logs

if ! pmset -g batt 2>/dev/null | grep -q "AC Power"; then
  echo "WARNING: running on BATTERY. macOS will sleep and freeze the bots."
  echo "         Plug in and keep the lid OPEN, or this will not survive the session."
  echo
fi

# Fail fast on a lapsed Groww session rather than starting bots that will
# crash on their first cycle. Groww approval-flow logins expire periodically.
echo "checking Groww auth..."
if ! $PY -c "
import warnings; warnings.filterwarnings('ignore')
from groww_client import connect
connect().get_ltp(exchange_trading_symbols=('NSE_TCS',), segment='CASH')
" > /dev/null 2>&1; then
  echo
  echo "AUTH FAILED - Groww session needs re-approval."
  echo "  Go to Groww -> Trading APIs -> re-approve the session, then retry."
  echo
  exit 1
fi
echo "auth ok"
echo

for s in "${STRATS[@]}"; do
  if pgrep -f "run_bot.py --strategy $s" > /dev/null; then
    echo "'$s' already running — stop it first (./stop_trading.sh)"
    exit 1
  fi
done

for s in "${STRATS[@]}"; do
  echo "starting $s..."
  nohup caffeinate -dims $PY run_bot.py --strategy "$s" > "logs/${s}_session.out" 2>&1 &
  sleep 7   # stagger API calls across bots
done

# watchdog last, so it never sees a half-started fleet
if ! pgrep -f watchdog.py > /dev/null; then
  echo "starting watchdog..."
  nohup $PY watchdog.py --expect "${STRATS[@]}" > logs/watchdog.out 2>&1 &
  sleep 1
fi

sleep 2
echo
pgrep -af "run_bot.py|watchdog.py" | sed 's|.*/Python ||;s|.*bin/python ||' || true
echo
echo "compare:  .venv/bin/python compare.py"
echo "stop:     ./stop_trading.sh"
