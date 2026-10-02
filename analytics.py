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


def is_lock_screen(app: str | None, title: str | None = None) -> bool:
    """Win+L / Windows lock screen — counts as away (break), not seated."""
    key = app_key(app)
    title_l = (title or "").lower()
    if key in {"lockapp", "logonui", "lock screen", "windows lock", "lockapp.exe"}:
        return True
    if "lock" in key and "screen" in key:
        return True
    if "windows lock" in title_l or title_l.strip() in {"lock screen", "locked"}:
        return True
    return False


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
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes and secs:
        return f"{minutes}m {secs:02d}s"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


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


def session_intervals(
    db,
    user_id: int,
    day_start: datetime,
    day_end: datetime,
    now: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Clock-in → clock-out ranges for this day (open session capped at now)."""
    now = now or datetime.now(timezone.utc)
    rows = (
        db.query(WorkSession)
        .filter(
            WorkSession.user_id == user_id,
            WorkSession.clock_in < day_end,
        )
        .order_by(WorkSession.clock_in)
        .all()
    )
    intervals: list[tuple[datetime, datetime]] = []
    for row in rows:
        cin = as_dt(row.clock_in)
        if cin is None:
            continue
        cout = as_dt(row.clock_out) if row.clock_out is not None else min(now, day_end)
        # Session must overlap this calendar day
        a = max(cin, day_start)
        b = min(cout, day_end)
        if b > a:
            intervals.append((a, b))
    return intervals


def overlap_intervals(t0: datetime, t1: datetime, intervals: list[tuple[datetime, datetime]]) -> float:
    """Seconds of [t0, t1) that fall inside any session interval."""
    t0, t1 = as_dt(t0), as_dt(t1)
    if t0 is None or t1 is None or t1 <= t0 or not intervals:
        return 0.0
    total = 0.0
    for a, b in intervals:
        lo = max(t0, a)
        hi = min(t1, b)
        if hi > lo:
            total += (hi - lo).total_seconds()
    return total


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
    seated = work = other = away = 0.0
    apps: dict[str, float] = {}
    sleep_gap = float(getattr(config, "SLEEP_GAP_SECONDS", 45))
    cap = sleep_gap
    now = datetime.now(timezone.utc)
    workday_full = float(getattr(config, "WORKDAY_SECONDS", 9 * 3600))
    intervals = session_intervals(db, user_id, start, end, now)
    elapsed = sum((b - a).total_seconds() for a, b in intervals)
    # Cap reported clocked time at one workday for presence math
    elapsed_capped = min(elapsed, workday_full)

    def credit(row, delta: float, t0: datetime, t1: datetime) -> None:
        """Only count time that overlaps a clocked-in session."""
        nonlocal seated, work, other, away
        if delta <= 0:
            return
        in_session = overlap_intervals(t0, t1, intervals)
        if in_session <= 0:
            return
        # Scale if the credited delta was capped shorter than [t0,t1]
        span = max((as_dt(t1) - as_dt(t0)).total_seconds(), 1e-6)
        scale = min(1.0, delta / span)
        use = in_session * scale
        if use <= 0:
            return
        raw_app = (row.app or "").strip() or "unknown"
        key = app_key(raw_app)
        locked = is_lock_screen(raw_app, row.window_title)
        # Explicit no-face / lock = away (break). Unknown present = idle only (via elapsed - seated).
        if locked or row.present == 0:
            away += use
            apps[key] = apps.get(key, 0) + use
            return
        if row.present == 1:
            seated += use
            apps[key] = apps.get(key, 0) + use
            if classify_app(raw_app, row.window_title) == "work":
                work += use
            else:
                other += use
            return
        # present is None / unknown — still count app time while clocked in
        apps[key] = apps.get(key, 0) + use
        if classify_app(raw_app, row.window_title) == "work":
            work += use
        else:
            other += use

    for i, row in enumerate(rows):
        t0 = as_dt(row.created_at)
        if i + 1 < len(rows):
            t1 = as_dt(rows[i + 1].created_at)
            gap = (t1 - t0).total_seconds()
        else:
            # Live tail while still clocked in
            t1 = min(now, end)
            gap = max((t1 - t0).total_seconds(), float(config.HEARTBEAT_SECONDS))
            t1 = t0 + timedelta(seconds=gap)
        if gap > sleep_gap:
            # Long gap while clocked in: cannot see face → idle via (elapsed - seated).
            # Only a short beat keeps last known app/away state.
            beat = float(config.HEARTBEAT_SECONDS)
            credit(row, beat, t0, t0 + timedelta(seconds=beat))
        else:
            credit(row, min(max(gap, 0), cap), t0, t1)

    active = sum(sec for name, sec in apps.items() if not is_lock_screen(name))
    all_apps = sorted(apps.items(), key=lambda item: item[1], reverse=True)
    useful = (work / (work + other) * 100) if (work + other) else 0
    allowance = config.BREAK_ALLOWANCE_SECONDS
    break_used = min(away, allowance)
    break_left = max(0.0, allowance - away)

    # Seated = face visible while clocked in.
    # Idle = clocked-in time with no face (away, sleep, offline, shutter).
    # Seated + Idle = time from clock-in to clock-out (capped at 9h).
    if elapsed_capped <= 0:
        seated_s = 0.0
        idle_s = 0.0
        presence = 0
    else:
        seated_s = min(float(seated), elapsed_capped)
        idle_s = max(0.0, elapsed_capped - seated_s)
        # Presence vs expected 9h day; also equals seated/(seated+idle) when fully clocked 9h
        presence = int(round(100.0 * seated_s / workday_full)) if workday_full > 0 else 0

    return {
        "samples": len(rows),
        "seated": fmt_hours(seated_s),
        "active": fmt_hours(active),
        "idle": fmt_hours(idle_s),
        "away": fmt_hours(away),
        "work": fmt_hours(work),
        "other": fmt_hours(other),
        "useful_pct": round(useful),
        "presence_pct": presence,
        "workday_seconds": int(workday_full),
        "clocked_seconds": int(elapsed_capped),
        "seated_seconds": int(seated_s),
        "idle_seconds": int(idle_s),
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
