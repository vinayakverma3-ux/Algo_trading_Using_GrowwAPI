#!/usr/bin/env bash
pkill -f run_bot.py  && echo "bot stopped"      || echo "bot was not running"
pkill -f watchdog.py && echo "watchdog stopped" || echo "watchdog was not running"
