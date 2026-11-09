"""
Weekly WhatsApp report for DeskTrack.

Runs every Sunday (or whichever day WEEKLY_REPORT_DAY is set to).
Sends one consolidated WhatsApp message per HR phone number with
a summary table of every employee's screen time and top apps for
the past 7 calendar days (Mon–Sun of the completed work week).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

import analytics
import config
import waha
from models import SessionLocal, User

logger = logging.getLogger("uvicorn.error")


# ── helpers ──────────────────────────────────────────────────────────────────

def _week_range() -> tuple[datetime, datetime]:
    """
    Return UTC start/end for the last 7 complete calendar days ending yesterday.
    e.g. if today is Sunday 2026-11-08, the range is Mon 2026-11-02 00:00 → Sun 2026-11-08 00:00 IST.
    """
    now_local = datetime.now(config.TIMEZONE)
    # End = start of today (midnight local)
    end_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # Start = 7 days before that
    start_local = end_local - timedelta(days=7)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _bar(pct: int, width: int = 10) -> str:
    """Simple text progress bar: ████░░░░░░  60%"""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_pct(pct: int) -> str:
    return f"{_bar(pct)} {pct}%"


def _top_apps(apps: list[dict], n: int = 3) -> str:
    """Return top N apps as a compact comma-separated string."""
    top = apps[:n]
    if not top:
        return "—"
    parts = []
    for a in top:
        parts.append(f"{a['app']} ({a['label']})")
    return ", ".join(parts)


# ── report builder ────────────────────────────────────────────────────────────

def build_weekly_report(db: SessionLocal | None = None) -> str:
    """
    Query every active employee, aggregate 7-day metrics, and format a
    WhatsApp-friendly plain-text report.
    Returns the full message string.
    """
    start_utc, end_utc = _week_range()

    # Localise for display
    start_local = start_utc.astimezone(config.TIMEZONE)
    end_local = end_utc.astimezone(config.TIMEZONE)
    week_label = (
        f"{start_local.strftime('%d %b')} – {(end_local - timedelta(seconds=1)).strftime('%d %b %Y')}"
    )

    own = db is None
    if own:
        db = SessionLocal()
    try:
        employees = (
            db.query(User)
            .filter(User.role == "employee")
            .order_by(User.name)
            .all()
        )

        if not employees:
            return (
                f"📊 *DeskTrack Weekly Report*\n"
                f"Week: {week_label}\n\n"
                "No employee data found."
            )

        lines: list[str] = [
            f"📊 *DeskTrack Weekly Report*",
            f"📅 Week: {week_label}",
            f"👥 Total employees: {len(employees)}",
            "",
        ]

        for emp in employees:
            # Aggregate daily summaries across the 7-day window
            # We iterate day-by-day so each day's session_intervals are
            # correctly bounded — mirrors how HR daily reports work.
            total_clocked = 0
            total_seated = 0
            total_idle = 0
            total_active = 0
            combined_apps: dict[str, float] = {}
            combined_app_labels: dict[str, str] = {}
            days_worked = 0

            current = start_utc
            while current < end_utc:
                next_day = current + timedelta(days=1)
                day_summary = analytics.summarize(db, emp.id, current, next_day)
                clocked = day_summary.get("clocked_seconds", 0)
                if clocked > 0:
                    days_worked += 1
                    total_clocked += clocked
                    total_seated += day_summary.get("seated_seconds", 0)
                    total_idle += day_summary.get("idle_seconds", 0)
                    # active seconds = sum of all app seconds (capped by clocked in summarize)
                    day_apps = day_summary.get("apps", [])
                    day_active = sum(a["seconds"] for a in day_apps)
                    total_active += day_active
                    for a in day_apps:
                        # Use the app display label as the key for de-dup
                        key = a["app"]
                        combined_apps[key] = combined_apps.get(key, 0.0) + a["seconds"]
                        combined_app_labels[key] = a["app"]
                current = next_day

            # Sort combined apps by time descending
            sorted_apps = sorted(
                [
                    {"app": k, "seconds": v, "label": analytics.fmt_hours(v)}
                    for k, v in combined_apps.items()
                ],
                key=lambda x: x["seconds"],
                reverse=True,
            )

            # Presence % for the week: seated / (days_worked × 9h) capped at 100
            week_target = days_worked * config.WORKDAY_SECONDS if days_worked else 1
            presence_pct = min(100, int(round(total_seated / week_target * 100))) if week_target else 0

            dept_str = f" | {emp.department}" if emp.department else ""

            lines.append(f"👤 *{emp.name}*{dept_str}")
            lines.append(f"   📅 Days active : {days_worked}/{config.WORK_DAYS_PER_WEEK}")
            lines.append(f"   🕐 Screen time : {analytics.fmt_hours(total_clocked)}")
            lines.append(f"   🟢 Seated      : {analytics.fmt_hours(total_seated)}")
            lines.append(f"   💤 Idle/Away   : {analytics.fmt_hours(total_idle)}")
            lines.append(f"   📱 App time    : {analytics.fmt_hours(total_active)}")
            lines.append(f"   📊 Presence    : {_fmt_pct(presence_pct)}")
            top = _top_apps(sorted_apps, n=3)
            lines.append(f"   🖥️  Top apps    : {top}")
            lines.append("")

        lines.append("— Sent by DeskTrack 🤖")
        return "\n".join(lines)

    finally:
        if own:
            db.close()


# ── sender ────────────────────────────────────────────────────────────────────

def send_weekly_report(db: SessionLocal | None = None) -> None:
    """Build the weekly report and dispatch it to all configured HR phones."""
    if not waha.is_waha_configured():
        logger.warning("[WeeklyReport] WAHA not configured — skipping weekly report dispatch.")
        return

    try:
        message = build_weekly_report(db)
    except Exception as exc:
        logger.error(f"[WeeklyReport] Failed to build weekly report: {exc}", exc_info=True)
        return

    phones = waha.get_lead_phone_numbers()
    logger.info(f"[WeeklyReport] Sending weekly report to {len(phones)} HR phone(s).")

    for phone in phones:
        try:
            result = waha.send_whatsapp_message(phone, message)
            if result.get("ok"):
                logger.info(f"[WeeklyReport] ✅ Sent to {phone}")
            else:
                logger.warning(f"[WeeklyReport] ⚠️  Failed to send to {phone}: {result.get('error')}")
        except Exception as exc:
            logger.error(f"[WeeklyReport] Error sending to {phone}: {exc}", exc_info=True)


# ── background scheduler ──────────────────────────────────────────────────────

_report_stop = threading.Event()


def _scheduler_loop() -> None:
    """
    Runs in a daemon thread. Checks every minute whether it's time to fire.
    Fires on WEEKLY_REPORT_DAY (0=Mon … 6=Sun, default 6=Sunday) at
    WEEKLY_REPORT_HOUR:WEEKLY_REPORT_MINUTE (default 09:00 IST).
    """
    target_day: int = getattr(config, "WEEKLY_REPORT_DAY", 6)       # Sunday
    target_hour: int = getattr(config, "WEEKLY_REPORT_HOUR", 9)      # 09:xx
    target_minute: int = getattr(config, "WEEKLY_REPORT_MINUTE", 0)  # xx:00

    # Track the last date the report was sent so we don't double-fire
    last_sent_date: datetime | None = None

    logger.info(
        f"[WeeklyReport] Scheduler started — fires every "
        f"{'Mon Tue Wed Thu Fri Sat Sun'.split()[target_day]} "
        f"at {target_hour:02d}:{target_minute:02d} {config.TIMEZONE}"
    )

    while not _report_stop.wait(60):   # wake up every minute
        now = datetime.now(config.TIMEZONE)

        # Is it the right weekday + hour + minute?
        if (
            now.weekday() == target_day
            and now.hour == target_hour
            and now.minute == target_minute
        ):
            today = now.date()
            if last_sent_date != today:
                logger.info("[WeeklyReport] Trigger matched — dispatching weekly report …")
                last_sent_date = today
                # Run in a separate thread so the scheduler loop is never blocked
                threading.Thread(target=send_weekly_report, daemon=True).start()


def start_weekly_report_scheduler() -> None:
    """Start the background scheduler thread. Call once from FastAPI lifespan."""
    _report_stop.clear()
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="weekly-report-scheduler")
    t.start()


def stop_weekly_report_scheduler() -> None:
    """Signal the scheduler thread to stop. Call from FastAPI shutdown."""
    _report_stop.set()
