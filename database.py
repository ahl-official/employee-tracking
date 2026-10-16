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


def _ensure_agent_password_column() -> None:
    """SQLite: add agent_password for existing DBs (create_all does not alter tables)."""
    try:
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()
            cols = {r[1] for r in rows}
            if "agent_password" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN agent_password VARCHAR(120) DEFAULT ''"
                )
                conn.commit()
    except Exception:
        pass


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_agent_password_column()
    db = Session(engine)
    try:
        purge_old_data(db)
        if db.query(User).count() == 0:
            from passwords import hash_password

            users = [
                User(
                    username="hr",
                    password=hash_password("hr123"),
                    agent_password="",
                    name="HR Desk",
                    role="hr",
                    department="People Ops",
                ),
            ]
            db.add_all(users)
            db.commit()
        # Freeze current website password as agent password when missing (one-time)
        for u in db.query(User).filter(User.role == "employee").all():
            if not (u.agent_password or "").strip() and u.password:
                u.agent_password = u.password
        _rename_saniya(db)
        for row in db.query(User).filter(User.on_break.is_(True)).all():
            row.on_break = False
        db.commit()
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



