"""Per-instance file paths so multiple strategies can run side by side."""
from pathlib import Path

LOGS = Path(__file__).parent.parent / "logs"


def _p(instance: str, suffix: str) -> Path:
    LOGS.mkdir(exist_ok=True)
    return LOGS / f"{instance}_{suffix}"


def state(instance: str) -> Path:
    return _p(instance, "state.json")


def trades(instance: str) -> Path:
    return _p(instance, "trades.csv")


def heartbeat(instance: str) -> Path:
    return _p(instance, "heartbeat.json")


def session_log(instance: str) -> Path:
    return _p(instance, "session.out")


def all_heartbeats() -> list[Path]:
    return sorted(LOGS.glob("*_heartbeat.json")) if LOGS.exists() else []
