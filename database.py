from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import config
from models import Alert, Base, Heartbeat, User, WorkSession, engine


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def purge_old_data(db: Session | None = None) -> dict:
    """Drop old heartbeats/alerts so SQLite stays small. Images are never stored."""
    own = db is None
    if own:
        db = Session(engine)
    n_hb = n_al = 0
    try:
        hb_days = max(3, int(getattr(config, "HEARTBEAT_KEEP_DAYS", 14)))
        al_days = max(7, int(getattr(config, "ALERT_KEEP_DAYS", 30)))
        hb_cut = utc_now() - timedelta(days=hb_days)
        al_cut = utc_now() - timedelta(days=al_days)
        n_hb = (
            db.query(Heartbeat)
            .filter(Heartbeat.created_at < hb_cut)
            .delete(synchronize_session=False)
        )
        n_al = (
            db.query(Alert)
            .filter(Alert.seen.is_(True), Alert.created_at < al_cut)
            .delete(synchronize_session=False)
        )
        db.commit()
    finally:
        if own:
            db.close()
    if own and (n_hb or 0) + (n_al or 0) > 500:
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("VACUUM")
                conn.commit()
        except Exception:
            pass
    return {"heartbeats": int(n_hb or 0), "alerts": int(n_al or 0)}


def init_db() -> None:
    Base.metadata.create_all(engine)
    db = Session(engine)
    try:
        purge_old_data(db)
        if db.query(User).count() == 0:
            from passwords import hash_password

            users = [
                User(
                    username="hr",
                    password=hash_password("hr123"),
                    name="HR Desk",
                    role="hr",
                    department="People Ops",
                ),
            ]
            if config.SEED_DEMO:
                users.extend(
                    [
                        User(
                            username="saniya",
                            password=hash_password("emp123"),
                            name="Saniya",
                            role="employee",
                            department="Engineering",
                        ),
                        User(
                            username="riya",
                            password=hash_password("emp123"),
                            name="Riya Sharma",
                            role="employee",
                            department="Engineering",
                        ),
                        User(
                            username="arjun",
                            password=hash_password("emp123"),
                            name="Arjun Mehta",
                            role="employee",
                            department="Design",
                        ),
                    ]
                )
            db.add_all(users)
            db.commit()
        _rename_saniya(db)
        for row in db.query(User).filter(User.on_break.is_(True)).all():
            row.on_break = False
        db.commit()
        if config.SEED_DEMO:
            _seed_demo(db)
            _seed_yesterday(db)
            _keep_demo_fresh(db)
    finally:
        db.close()


def _rename_saniya(db: Session) -> None:
    vinitt = db.query(User).filter_by(username="vinitt").first()
    saniya = db.query(User).filter_by(username="saniya").first()
    if vinitt and saniya is None:
        vinitt.username = "saniya"
        vinitt.name = "Saniya"
        db.commit()
        return
    if saniya:
        saniya.name = "Saniya"
        db.commit()


def _seed_demo(db: Session) -> None:
    if not config.SEED_DEMO:
        return
    if db.query(Heartbeat).count() >= 80:
        return
    now = utc_now()
    patterns = {
        "riya": [
            ("Code.exe", "desktrack — app.py", 1, False),
            ("chrome.exe", "Stack Overflow — FastAPI", 1, False),
            ("slack.exe", "engineering", 1, False),
            ("chrome.exe", "YouTube", 1, False),
        ],
        "arjun": [
            ("figma.exe", "Dashboard redesign", 1, False),
            ("ms-teams.exe", "Standup", 1, False),
            ("chrome.exe", "Dribbble", 1, False),
            ("notepad.exe", "copy.txt", 1, True),
        ],
    }
    for username, pattern in patterns.items():
        user = db.query(User).filter_by(username=username).first()
        if not user:
            continue
        if db.query(Heartbeat).filter_by(user_id=user.id).count():
            continue
        db.add(WorkSession(user_id=user.id, clock_in=now - timedelta(hours=3)))
        t = now - timedelta(hours=2)
        i = 0
        while t < now - timedelta(minutes=2):
            app, title, present, idle = pattern[i % len(pattern)]
            if username == "riya" and t > now - timedelta(minutes=8):
                present, idle, app, title = 0, True, "LockApp.exe", "Windows lock"
            db.add(
                Heartbeat(
                    user_id=user.id,
                    present=present,
                    idle=idle,
                    idle_seconds=90 if idle else 3,
                    app=app,
                    window_title=title,
                    device="laptop",
                    created_at=t,
                )
            )
            t += timedelta(seconds=config.HEARTBEAT_SECONDS * 3)
            i += 1
        if username == "riya":
            db.add(
                Alert(
                    user_id=user.id,
                    message="Riya Sharma has been away from the desk for 8 min.",
                    created_at=utc_now(),
                    seen=False,
                )
            )
    db.commit()


def _seed_yesterday(db: Session) -> None:
    """Keep one previous calendar day so HR can open history without mixing it into today."""
    if not config.SEED_DEMO:
        return
    import analytics

    yesterday = analytics.local_now().date() - timedelta(days=1)
    start, end = analytics.day_range(yesterday)
    if db.query(Heartbeat).filter(Heartbeat.created_at >= start, Heartbeat.created_at < end).first():
        return
    samples = {
        "riya": ("Code.exe", "desktrack — app.py", 1, False),
        "arjun": ("figma.exe", "Dashboard redesign", 1, False),
    }
    for username, (app, title, present, idle) in samples.items():
        user = db.query(User).filter_by(username=username).first()
        if not user:
            continue
        db.add(
            WorkSession(
                user_id=user.id,
                clock_in=start + timedelta(hours=3, minutes=30),
                clock_out=start + timedelta(hours=10),
            )
        )
        t = start + timedelta(hours=4)
        while t < start + timedelta(hours=6):
            db.add(
                Heartbeat(
                    user_id=user.id,
                    present=present,
                    idle=idle,
                    idle_seconds=4,
                    app=app,
                    window_title=title,
                    device="laptop",
                    created_at=t,
                )
            )
            t += timedelta(minutes=8)
    db.commit()


def _keep_demo_fresh(db: Session) -> None:
    """Keep demo employees visible on the live board before anyone runs the agent."""
    if not config.SEED_DEMO:
        return
    import analytics

    now = utc_now()
    start, _ = analytics.day_range()
    specs = {
        "riya": (0, True, "LockApp.exe", "Windows lock", "laptop"),
        "arjun": (1, False, "figma.exe", "Dashboard redesign", "laptop"),
    }
    for username, (present, idle, app, title, device) in specs.items():
        user = db.query(User).filter_by(username=username).first()
        if not user:
            continue
        analytics.close_overnight_sessions(db, user.id)
        last = (
            db.query(Heartbeat)
            .filter_by(user_id=user.id)
            .order_by(Heartbeat.id.desc())
            .first()
        )
        last_dt = analytics.as_dt(last.created_at) if last else None
        from_today = last_dt is not None and last_dt >= start
        age = analytics.seconds_ago(last.created_at) if last else None
        if from_today and age is not None and age < config.OFFLINE_AFTER_SECONDS:
            continue
        if analytics.open_session(db, user.id) is None:
            clock_in = now - timedelta(hours=3)
            if clock_in < start:
                clock_in = start + timedelta(minutes=5)
            db.add(WorkSession(user_id=user.id, clock_in=clock_in))
        fields = dict(
            present=present,
            idle=idle,
            idle_seconds=180 if idle else 4,
            app=app,
            window_title=title,
            device=device,
            created_at=now - timedelta(seconds=2),
        )
        if from_today and last is not None:
            for key, value in fields.items():
                setattr(last, key, value)
        else:
            db.add(Heartbeat(user_id=user.id, **fields))
    db.commit()
