#!/usr/bin/env bash
# Quarterly momentum rebalance — mid-cap universe.
#
# Decided 3 Sep 2026: switch from NIFTY 100 monthly 6-1 top-10
# to NIFTY Midcap 100, 12-1 lookback, top 15, on 1 Oct 2026.
#
#   ./rebalance.sh            show the plan (safe, places nothing)
#   ./rebalance.sh --execute  place real orders (asks for confirmation)
set -euo pipefail
cd "$(dirname "$0")"

.venv/bin/python -m momentum.live \
  --universe midcap \
  --lookback 12 \
  --skip 1 \
  --top 15 \
  --max-sector 4 \
  --max-group 2 \
  "$@"
