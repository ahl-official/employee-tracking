"""Seated / idle / app-time summaries from heartbeats."""

from datetime import datetime, timedelta, timezone

import config
from models import Heartbeat, WorkSession


def local_now():
    return datetime.now(config.TIMEZONE)


def parse_day(value=None):
    if value is None or value == "":
        return local_now().date()
    if hasattr(value, "year") and hasattr(value, "month"):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def day_range(day=None):
    day = parse_day(day)
    start = datetime(day.year, day.month, day.day, tzinfo=config.TIMEZONE).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def is_today(day=None) -> bool:
    return parse_day(day) == local_now().date()


def activity_days(db, user_id=None, limit=60) -> list[str]:
    from models import Heartbeat

    q = db.query(Heartbeat.created_at)
    if user_id is not None:
        q = q.filter(Heartbeat.user_id == user_id)
    dates = set()
    for (ts,) in q.all():
        dt = as_dt(ts)
        if dt:
            dates.add(dt.astimezone(config.TIMEZONE).date())
    dates.add(local_now().date())
    return [d.isoformat() for d in sorted(dates, reverse=True)[:limit]]


def inside_work_hours(moment=None) -> bool:
    moment = moment or local_now()
    return config.WORK_START_HOUR <= moment.hour < config.WORK_END_HOUR


def as_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def seconds_ago(value) -> float | None:
    dt = as_dt(value)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def classify_app(app: str | None, title: str | None) -> str:
    app = (app or "").lower()
    title = (title or "").lower()
    if any(word in title for word in config.DISTRACTION_WORDS):
        return "other"
    if app in {name.lower() for name in config.WORK_APPS}:
        return "work"
    return "other"


def app_key(app: str | None) -> str:
    name = (app or "unknown").strip()
    lower = name.lower()
    if lower.endswith(".exe"):
        name = name[:-4]
    return name.strip().lower() or "unknown"


def pretty_app_name(app: str | None) -> str:
    """Human label for Apps today / live board (Chrome, not chrome.exe)."""
    key = app_key(app)
    if key in config.APP_DISPLAY_NAMES:
        return config.APP_DISPLAY_NAMES[key]
    cleaned = key.replace("_", " ").replace("-", " ").strip()
    return cleaned.title() if cleaned else "Unknown"


def live_status(beat: Heartbeat | None, clocked_in=True, break_left=0, ignore_stale=False) -> str:
    stale = (
        not ignore_stale
        and (
            beat is None
            or beat.created_at is None
            or (seconds_ago(beat.created_at) or 999) > config.OFFLINE_AFTER_SECONDS
        )
    )
    if not clocked_in:
        return "offline" if stale or beat is None else "clocked-out"
    # Still clocked in but no pings (laptop sleep, closed lid, tab frozen) → inactive (= Idle/sleep)
    if stale or beat is None:
        return "inactive"
    if beat.present == 0:
        return "break" if break_left > 0 else "away"
    # Present at desk while PC is awake → always Active (ignore mouse-idle flag)
    return "present"


def fmt_hours(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def open_session(db, user_id: int) -> WorkSession | None:
    return (
        db.query(WorkSession)
        .filter(WorkSession.user_id == user_id, WorkSession.clock_out.is_(None))
        .order_by(WorkSession.id.desc())
        .first()
    )


def close_overnight_sessions(db, user_id: int | None = None) -> None:
    """Clock out leftover sessions at local midnight so a new day starts clean."""
    start, _ = day_range()
    q = db.query(WorkSession).filter(WorkSession.clock_out.is_(None))
    if user_id is not None:
        q = q.filter(WorkSession.user_id == user_id)
    for row in q.all():
        if as_dt(row.clock_in) is not None and as_dt(row.clock_in) < start:
            row.clock_out = start


def auto_clock_in_if_needed(db, user_id: int) -> bool:
    """Clock in on the first heartbeat of the day. Never undo a clock-out (lunch)."""
    close_overnight_sessions(db, user_id)
    if open_session(db, user_id) is not None:
        return True
    start, end = day_range()
    already = (
        db.query(WorkSession)
        .filter(
            WorkSession.user_id == user_id,
            WorkSession.clock_in >= start,
            WorkSession.clock_in < end,
        )
        .first()
    )
    if already:
        return False
    db.add(WorkSession(user_id=user_id, clock_in=datetime.now(timezone.utc)))
    return True


def summarize(db, user_id: int, start: datetime, end: datetime) -> dict:
    rows = (
        db.query(Heartbeat)
        .filter(
            Heartbeat.user_id == user_id,
            Heartbeat.created_at >= start,
            Heartbeat.created_at < end,
        )
        .order_by(Heartbeat.id)
        .all()
    )
    seated = active = idle = work = other = away = 0.0
    apps: dict[str, float] = {}
    sleep_gap = float(getattr(config, "SLEEP_GAP_SECONDS", 45))
    # Cap awake segments just under sleep threshold so seated/apps accumulate
    cap = sleep_gap
    now = datetime.now(timezone.utc)

    def credit(row, delta: float) -> None:
        nonlocal seated, active, idle, work, other, away
        if delta <= 0:
            return
        raw_app = (row.app or "").strip() or "unknown"
        key = app_key(raw_app)
        if row.present == 1:
            seated += delta
            active += delta
            apps[key] = apps.get(key, 0) + delta
            if classify_app(raw_app, row.window_title) == "work":
                work += delta
            else:
                other += delta
        elif row.present == 0:
            away += delta
            # Away time does not count as app-use for "Apps today"
        else:
            apps[key] = apps.get(key, 0) + delta

    for i, row in enumerate(rows):
        if i + 1 < len(rows):
            gap = (as_dt(rows[i + 1].created_at) - as_dt(row.created_at)).total_seconds()
        else:
            # Live tail until now (or day end) so counters move while you work
            gap = (min(now, end) - as_dt(row.created_at)).total_seconds()
            gap = max(gap, float(config.HEARTBEAT_SECONDS))
        if gap > sleep_gap:
            # PC sleep / offline — Idle only; do not credit seated/apps across the nap
            idle += min(gap, 4 * 3600)
            credit(row, float(config.HEARTBEAT_SECONDS))
        else:
            credit(row, min(max(gap, 0), cap))

    all_apps = sorted(apps.items(), key=lambda item: item[1], reverse=True)
    useful = (work / (work + other) * 100) if (work + other) else 0
    allowance = config.BREAK_ALLOWANCE_SECONDS
    break_used = min(away, allowance)
    break_left = max(0.0, allowance - away)
    return {
        "samples": len(rows),
        "seated": fmt_hours(seated),
        "active": fmt_hours(active),
        "idle": fmt_hours(idle),
        "away": fmt_hours(away),
        "work": fmt_hours(work),
        "other": fmt_hours(other),
        "useful_pct": round(useful),
        "break_used": fmt_hours(break_used),
        "break_left": fmt_hours(break_left),
        "break_left_seconds": int(break_left),
        "away_seconds": int(away),
        "apps": [
            {"app": pretty_app_name(name), "seconds": sec, "label": fmt_hours(sec)}
            for name, sec in all_apps
            if sec >= 1
        ],
    }
