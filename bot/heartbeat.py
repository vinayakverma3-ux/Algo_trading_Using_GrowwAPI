"""Liveness file the engine touches each cycle; the watchdog reads it."""
import json
from datetime import datetime
from pathlib import Path

from bot import paths
from bot.clock import IST


def write(instance: str, mode: str, strategy: str, equity: float, positions: int) -> None:
    paths.heartbeat(instance).write_text(json.dumps({
        "ts": datetime.now(IST).isoformat(),
        "instance": instance,
        "mode": mode,
        "strategy": strategy,
        "equity": equity,
        "positions": positions,
    }))


def read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
        d["age_s"] = (datetime.now(IST) - datetime.fromisoformat(d["ts"])).total_seconds()
        return d
    except Exception:
        return None


def read_all() -> list[dict]:
    return [d for d in (read(p) for p in paths.all_heartbeats()) if d]
