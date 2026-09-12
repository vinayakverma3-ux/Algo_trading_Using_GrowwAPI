"""NSE market session helpers. All times IST."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 15)
CLOSE = time(15, 30)


def now() -> datetime:
    return datetime.now(IST)


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def is_open(dt: datetime | None = None) -> bool:
    dt = dt or now()
    return is_weekday(dt) and OPEN <= dt.time() < CLOSE


def seconds_until_open(dt: datetime | None = None) -> float:
    """Seconds until the next open. 0 if the market is already open."""
    dt = dt or now()
    if is_open(dt):
        return 0.0
    target = dt.replace(hour=OPEN.hour, minute=OPEN.minute, second=0, microsecond=0)
    if dt.time() >= OPEN:
        target += timedelta(days=1)
    while not is_weekday(target):
        target += timedelta(days=1)
    return (target - dt).total_seconds()


def minutes_to_close(dt: datetime | None = None) -> float:
    dt = dt or now()
    close_dt = dt.replace(hour=CLOSE.hour, minute=CLOSE.minute, second=0, microsecond=0)
    return (close_dt - dt).total_seconds() / 60
