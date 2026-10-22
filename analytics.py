"""Seated / idle / app-time summaries from heartbeats."""

from datetime import datetime, timedelta, timezone

import config
from models import Heartbeat, WorkSession, TaskRequest


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
    title = (title or "").lower()
    if any(word in title for word in config.DISTRACTION_WORDS):
        return "other"
    # Agent sends "chrome"; WORK_APPS may list "chrome.exe" — compare stems
    key = app_key(app)
    work_keys = {app_key(name) for name in config.WORK_APPS}
    if key in work_keys:
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


_BROWSER_KEYS = {
    "chrome",
    "msedge",
    "edge",
    "firefox",
    "brave",
    "opera",
    "chromium",
    "browser",
    "iexplore",
}

_BROWSER_TITLE_SUFFIXES = (
    " - Google Chrome",
    " - Chrome",
    " - Microsoft​ Edge",
    " - Microsoft Edge",
    " - Edge",
    " - Mozilla Firefox",
    " - Firefox",
    " - Brave",
    " - Opera",
    " — Mozilla Firefox",
)


def clean_window_title(title: str | None) -> str:
    text = (title or "").strip()
    if not text:
        return ""
    for suffix in _BROWSER_TITLE_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text[:120]


def activity_bucket(app: str | None, title: str | None) -> tuple[str, str]:
    """
    Bucket key + display label for Apps today.
    Browsers are split by tab title so Figma/YouTube/etc. show separately from bare Chrome.
    """
    key = app_key(app)
    cleaned = clean_window_title(title)
    low_title = cleaned.lower()
    low_key = key.lower()

    # Desktop Figma (and similar) — process name variants
    if "figma" in low_key:
        return "app:figma", "Figma"

    # Browser tab → show the page/file name (and name known web apps)
    if key in _BROWSER_KEYS:
        if "figma" in low_title:
            return "web:figma", "Figma (browser)"
        if any(w in low_title for w in ("youtube", "youtu.be")):
            return "web:youtube", "YouTube"
        if "instagram" in low_title:
            return "web:instagram", "Instagram"
        if cleaned:
            return f"tab:{low_title[:100]}", cleaned[:80]
        return f"app:{key}", pretty_app_name(app)

    # Store / UWP host — prefer window title when we have one
    if key in {"applicationframehost", "wwahost", "textinputhost"} and cleaned:
        if "figma" in low_title:
            return "app:figma", "Figma"
        return f"uwp:{low_title[:100]}", cleaned[:80]

    return f"app:{key}", pretty_app_name(app)


def live_status(beat: Heartbeat | None, clocked_in=True, break_left=0, ignore_stale=False, on_task=False) -> str:
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
    if on_task:
        return "task"
    # Still clocked in but no pings (laptop sleep, closed lid, tab frozen)
    if stale or beat is None:
        return "break" if break_left > 0 else "inactive"
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
    """Clock out leftover sessions so past days do not stretch overnight into hours of fake idle."""
    start, _ = day_range()
    q = db.query(WorkSession).filter(WorkSession.clock_out.is_(None))
    if user_id is not None:
        q = q.filter(WorkSession.user_id == user_id)
    for row in q.all():
        cin = as_dt(row.clock_in)
        if cin is not None and cin < start:
            # Find the user's last heartbeat for that session before start of current day
            last_hb = (
                db.query(Heartbeat.created_at)
                .filter(
                    Heartbeat.user_id == row.user_id,
                    Heartbeat.created_at >= cin,
                    Heartbeat.created_at < start,
                )
                .order_by(Heartbeat.created_at.desc())
                .first()
            )
            if last_hb and last_hb[0]:
                last_dt = as_dt(last_hb[0])
                row.clock_out = min(last_dt + timedelta(minutes=5), start)
            else:
                row.clock_out = min(cin + timedelta(minutes=30), start)


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
    """Clock-in → clock-out ranges for this day (open session capped at now or last activity)."""
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
        if row.clock_out is not None:
            cout = as_dt(row.clock_out)
            # If clock_out was artificially closed at midnight/day_end for a past day,
            # trim it to the employee's actual last recorded activity.
            if cout >= day_end and day_end <= now:
                last_hb = (
                    db.query(Heartbeat.created_at)
                    .filter(
                        Heartbeat.user_id == user_id,
                        Heartbeat.created_at >= cin,
                        Heartbeat.created_at < day_end,
                    )
                    .order_by(Heartbeat.created_at.desc())
                    .first()
                )
                if last_hb and last_hb[0]:
                    last_hb_dt = as_dt(last_hb[0])
                    if (day_end - last_hb_dt).total_seconds() > 1800:
                        cout = min(last_hb_dt + timedelta(minutes=5), day_end)
        else:
            # Open session: if past day left unclosed, cap at last activity
            if day_end <= now:
                last_hb = (
                    db.query(Heartbeat.created_at)
                    .filter(
                        Heartbeat.user_id == user_id,
                        Heartbeat.created_at >= cin,
                        Heartbeat.created_at < day_end,
                    )
                    .order_by(Heartbeat.created_at.desc())
                    .first()
                )
                if last_hb and last_hb[0]:
                    cout = min(as_dt(last_hb[0]) + timedelta(minutes=5), day_end)
                else:
                    cout = min(cin + timedelta(minutes=30), day_end)
            else:
                cout = min(now, day_end)
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
    app_labels: dict[str, str] = {}
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
        locked = is_lock_screen(raw_app, row.window_title)

        def add_app_bucket(seconds: float) -> None:
            nonlocal work, other
            if seconds <= 0 or locked:
                return
            bkey, label = activity_bucket(raw_app, row.window_title)
            apps[bkey] = apps.get(bkey, 0) + seconds
            app_labels[bkey] = label
            if classify_app(raw_app, row.window_title) == "work":
                work += seconds
            else:
                other += seconds

        # Explicit no-face / lock = away (break). Unknown present = idle only (via elapsed - seated).
        if locked or row.present == 0:
            away += use
            add_app_bucket(use)
            return
        if row.present == 1:
            seated += use
            add_app_bucket(use)
            return
        # present is None / unknown — still count app time while clocked in
        add_app_bucket(use)

    grace = float(getattr(config, "PRESENCE_GAP_GRACE_SECONDS", 420))

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
            # Chrome often throttles the My desk tab to ~60s or more.
            # Keep last face/away state through gaps up to grace (7 mins).
            if gap <= grace:
                credit(row, gap, t0, t1)
            else:
                # Long gap (> 7 min, e.g. disconnect, sleep, camera off):
                # If face was present at t0, credit up to grace hold (7 mins); rest is Idle/Away.
                if row.present == 1:
                    credit(row, grace, t0, t0 + timedelta(seconds=grace))
                else:
                    # Explicit away/no-face before the gap -> entire gap is away time
                    credit(row, gap, t0, t1)
        else:
            credit(row, min(max(gap, 0), cap), t0, t1)

    active = sum(apps.values())
    all_apps = sorted(apps.items(), key=lambda item: item[1], reverse=True)
    useful = (work / (work + other) * 100) if (work + other) else 0

    # Seated = face visible while clocked in (with 7m hold).
    # Idle = clocked-in time with no face (away, lock, sleep, no camera, long gap).
    # Bounded strictly to the time between Clock In and Clock Out.
    if not intervals or elapsed <= 0:
        seated_s = 0.0
        idle_s = 0.0
        presence = 0
        total_clocked = 0.0
        task_seconds = 0.0
    else:
        total_clocked = elapsed
        seated_s = min(float(seated), total_clocked)
        idle_s = max(0.0, total_clocked - seated_s)
        presence = int(round(100.0 * seated_s / total_clocked)) if total_clocked > 0 else 0

        # Account for approved tasks away from desk (meetings, other room, etc.)
        task_rows = (
            db.query(TaskRequest)
            .filter(
                TaskRequest.user_id == user_id,
                TaskRequest.status.in_(["approved", "completed"]),
                TaskRequest.requested_at < end,
                (TaskRequest.ended_at == None) | (TaskRequest.ended_at >= start),
            )
            .all()
        )
        task_seconds = 0.0
        for tr in task_rows:
            # Time spent on task starts from when employee requested to step away
            t_start = as_dt(tr.requested_at or tr.started_at)
            t_end = as_dt(tr.ended_at) if tr.ended_at else min(now, end)
            if t_end > t_start:
                task_seconds += overlap_intervals(max(t_start, start), min(t_end, end), intervals)

        # Official tasks count toward productive work
        work += task_seconds
        # Remove approved task time from idle and away so neither idle time nor break allowance is deducted
        idle_s = max(0.0, idle_s - task_seconds)
        away = max(0.0, away - task_seconds)
        # Credit approved on-task time to employee's daily presence percentage
        presence = int(round(100.0 * min(total_clocked, seated_s + task_seconds) / total_clocked)) if total_clocked > 0 else 0

    allowance = config.BREAK_ALLOWANCE_SECONDS
    # Away time that consumes personal break excludes approved official task time
    away_total = max(0.0, max(float(away), float(idle_s)))
    break_used = min(away_total, allowance)
    break_left = max(0.0, allowance - away_total)

    return {
        "samples": len(rows),
        "seated": fmt_hours(seated_s),
        "active": fmt_hours(active),
        "idle": fmt_hours(idle_s),
        "away": fmt_hours(away_total),
        "work": fmt_hours(work),
        "other": fmt_hours(other),
        "task_seconds": int(task_seconds),
        "task_time": fmt_hours(task_seconds),
        "useful_pct": round(useful),
        "presence_pct": presence,
        "workday_seconds": int(workday_full),
        "clocked_seconds": int(total_clocked),
        "seated_seconds": int(seated_s),
        "idle_seconds": int(idle_s),
        "break_used": fmt_hours(break_used),
        "break_left": fmt_hours(break_left),
        "break_left_seconds": int(break_left),
        "away_seconds": int(away_total),
        "apps": [
            {
                "app": app_labels.get(name, pretty_app_name(name)),
                "seconds": sec,
                "label": fmt_hours(sec),
            }
            for name, sec in all_apps
            if sec >= 1
        ],
    }
