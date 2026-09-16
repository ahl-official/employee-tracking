"""
DeskTrack — FastAPI workplace presence app.

Dev:
    python main.py
    cd frontend && npm run dev

Production: see DEPLOY.md
"""

import base64
import csv
import io
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from fastapi import Body, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

import analytics
import config
import detector
import face_id
from database import init_db, purge_old_data, utc_now, _keep_demo_fresh
from models import Alert, Heartbeat, SessionLocal, User, WorkSession

PREVIEW_FRAMES: dict[int, bytes] = {}
PREVIEW_META: dict[int, dict] = {}
_DETECT_NET = None
_DETECT_FACE = None
_cleanup_stop = threading.Event()
AGENT_FG_DIR = Path(__file__).resolve().parent / "face_models"


def _agent_fg_path(user_id: int) -> Path:
    AGENT_FG_DIR.mkdir(parents=True, exist_ok=True)
    return AGENT_FG_DIR / f"agent_fg_{user_id}.json"


def save_agent_foreground(user_id: int, app: str, title: str) -> None:
    """File-backed so all Gunicorn/uvicorn workers see the same desktop app."""
    payload = {"app": app, "title": title, "at": time.time()}
    try:
        _agent_fg_path(user_id).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def load_agent_foreground(user_id: int, max_age: float = 90.0) -> dict:
    path = _agent_fg_path(user_id)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(data.get("at") or 0) > max_age:
            return {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_detector():
    global _DETECT_NET, _DETECT_FACE
    if _DETECT_NET is None:
        _DETECT_NET, _DETECT_FACE = detector.load_net()
    return _DETECT_NET, _DETECT_FACE


def _cleanup_loop():
    while not _cleanup_stop.wait(6 * 3600):
        try:
            purge_old_data()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _cleanup_stop.clear()
    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()
    yield
    _cleanup_stop.set()


app = FastAPI(
    title="DeskTrack",
    lifespan=lifespan,
    docs_url=None if config.PRODUCTION else "/docs",
    redoc_url=None if config.PRODUCTION else "/redoc",
)
config.validate_production()
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    https_only=config.HTTPS_ONLY,
    same_site="lax",
    max_age=14 * 24 * 3600,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
DIST = Path(__file__).resolve().parent / "frontend" / "dist"


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "department": user.department,
    }


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require(request: Request, db: Session, *roles: str) -> User | None:
    user = current_user(request, db)
    if not user or user.role not in roles:
        return None
    return user


def iso(value) -> str | None:
    dt = analytics.as_dt(value)
    return dt.isoformat() if dt else None


def latest_beat(db: Session, user_id: int) -> Heartbeat | None:
    return (
        db.query(Heartbeat)
        .filter(Heartbeat.user_id == user_id)
        .order_by(Heartbeat.id.desc())
        .first()
    )


def last_beat_in_range(db: Session, user_id: int, start: datetime, end: datetime) -> Heartbeat | None:
    return (
        db.query(Heartbeat)
        .filter(
            Heartbeat.user_id == user_id,
            Heartbeat.created_at >= start,
            Heartbeat.created_at < end,
        )
        .order_by(Heartbeat.id.desc())
        .first()
    )


def employee_card(db: Session, emp: User, day=None) -> dict:
    day = analytics.parse_day(day)
    start, end = analytics.day_range(day)
    viewing_today = analytics.is_today(day)
    analytics.close_overnight_sessions(db, emp.id)
    summary = analytics.summarize(db, emp.id, start, end)
    if viewing_today:
        beat = latest_beat(db, emp.id)
        session_row = analytics.open_session(db, emp.id)
        status = analytics.live_status(
            beat,
            clocked_in=session_row is not None,
            break_left=summary["break_left_seconds"],
        )
        clocked_in = session_row is not None
    else:
        beat = last_beat_in_range(db, emp.id, start, end)
        clocked_in = False
        status = (
            analytics.live_status(
                beat,
                clocked_in=True,
                break_left=summary["break_left_seconds"],
                ignore_stale=True,
            )
            if beat
            else "offline"
        )
    fg = load_agent_foreground(emp.id)
    agent_apps = bool(fg)
    # Prefer live desktop app from agent over stale heartbeat app label
    live_app = beat.app if beat else None
    live_title = beat.window_title if beat else None
    live_device = beat.device if beat else None
    if agent_apps:
        live_app = fg.get("app") or live_app
        live_title = fg.get("title") or live_title
        live_device = "laptop"
    return {
        "id": emp.id,
        "name": emp.name,
        "username": emp.username,
        "department": emp.department,
        "status": status,
        "on_break": status == "break",
        "break_left": summary["break_left"],
        "break_used": summary["break_used"],
        "clocked_in": clocked_in,
        "present": None if beat is None else beat.present,
        "idle": None if beat is None else beat.idle,
        "idle_seconds": 0 if beat is None else beat.idle_seconds,
        "app": None if live_app is None else analytics.pretty_app_name(live_app),
        "window_title": live_title,
        "device": live_device,
        "updated": iso(None if beat is None else beat.created_at),
        "agent_live": False,
        "agent_apps": viewing_today and agent_apps,
        "camera_blocked": bool(PREVIEW_META.get(emp.id, {}).get("blocked")),
        "has_preview": emp.id in PREVIEW_FRAMES,
        "face_enrolled": face_id.has_enrollment(emp.id),
        "day": day.isoformat(),
        "is_today": viewing_today,
        "today": summary,
    }


def maybe_alert(db: Session, user: User, present, clocked_in: bool, break_left: int):
    if not clocked_in or not analytics.inside_work_hours():
        return
    if present is not False:
        return
    if break_left > 0:
        return
    start, _ = analytics.day_range()
    rows = (
        db.query(Heartbeat)
        .filter(Heartbeat.user_id == user.id, Heartbeat.created_at >= start)
        .order_by(Heartbeat.id.desc())
        .limit(50)
        .all()
    )
    away_seconds = 0.0
    for row in rows:
        if row.present != 0:
            break
        away_seconds = max(away_seconds, analytics.seconds_ago(row.created_at) or 0)
    extra = away_seconds
    if extra < config.AWAY_ALERT_SECONDS:
        return
    open_alert = (
        db.query(Alert)
        .filter(Alert.user_id == user.id, Alert.seen.is_(False))
        .order_by(Alert.id.desc())
        .first()
    )
    if open_alert:
        return
    minutes = max(1, int(away_seconds // 60))
    message = f"{user.name} has been away from the desk for {minutes} min."
    db.add(Alert(user_id=user.id, message=message, created_at=utc_now(), seen=False))
    notify_hr_external_async(message)


def maybe_identity_alert(db: Session, user: User, identity: dict):
    """Ping HR when a different person is at this employee's desk."""
    if identity.get("reason") != "mismatch":
        return
    # Cooldown: one unread identity alert at a time
    recent = (
        db.query(Alert)
        .filter(
            Alert.user_id == user.id,
            Alert.seen.is_(False),
            Alert.message.like("%Someone else%"),
        )
        .first()
    )
    if recent:
        return
    # Also suppress duplicates within 10 minutes even if acknowledged
    cutoff = utc_now() - timedelta(minutes=10)
    dup = (
        db.query(Alert)
        .filter(
            Alert.user_id == user.id,
            Alert.message.like("%Someone else%"),
            Alert.created_at >= cutoff,
        )
        .first()
    )
    if dup:
        return
    score = identity.get("score")
    message = (
        f"Someone else may be at {user.name}'s desk "
        f"(face mismatch, score={score})."
    )
    db.add(Alert(user_id=user.id, message=message, created_at=utc_now(), seen=False))
    notify_hr_external_async(message)


def notify_hr_external(message: str) -> dict:
    """Best-effort push when HR is not watching the website. Returns {ok, detail}."""
    webhook = getattr(config, "HR_ALERT_WEBHOOK", "") or ""
    if not webhook:
        return {"ok": False, "detail": "HR_ALERT_WEBHOOK is not set on the server."}

    text = f"DeskTrack: {message}"
    # Slack Incoming Webhooks use "text"; Discord uses "content"
    if "discord.com/api/webhooks" in webhook or "discordapp.com/api/webhooks" in webhook:
        payload = {"content": text}
    else:
        payload = {"text": text}

    try:
        import urllib.error
        import urllib.request

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            return {"ok": True, "detail": f"Webhook HTTP {res.status}"}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "detail": f"Webhook HTTP {exc.code}: {exc.reason}"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


def notify_hr_external_async(message: str) -> None:
    import threading

    threading.Thread(target=lambda: notify_hr_external(message), daemon=True).start()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/session")
def api_session(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return {"ok": True, "user": user_payload(user)}


@app.post("/api/login")
def api_login(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    from passwords import hash_password, needs_rehash, verify_password

    username = str(payload.get("username") or "").strip().lower()
    password = str(payload.get("password") or "")
    user = db.query(User).filter_by(username=username).first()
    if not user or not verify_password(password, user.password):
        return JSONResponse({"ok": False, "error": "Wrong username or password."}, status_code=401)
    if needs_rehash(user.password):
        user.password = hash_password(password)
        db.commit()
    request.session["user_id"] = user.id
    return {"ok": True, "user": user_payload(user)}


@app.post("/api/signup")
def api_signup(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Employee self-registration. HR accounts are created by an existing HR user."""
    from passwords import hash_password

    name = str(payload.get("name") or "").strip()
    username = str(payload.get("username") or "").strip().lower()
    password = str(payload.get("password") or "")
    department = str(payload.get("department") or "Engineering").strip() or "Engineering"
    if len(name) < 2:
        return JSONResponse({"ok": False, "error": "Enter your full name."}, status_code=400)
    if len(username) < 3 or not username.replace("_", "").replace(".", "").isalnum():
        return JSONResponse(
            {"ok": False, "error": "Username must be at least 3 characters (letters, numbers, . or _)."},
            status_code=400,
        )
    if len(password) < 6:
        return JSONResponse({"ok": False, "error": "Password must be at least 6 characters."}, status_code=400)
    if db.query(User).filter_by(username=username).first():
        return JSONResponse({"ok": False, "error": "That username is already taken."}, status_code=409)
    user = User(
        username=username,
        password=hash_password(password),
        name=name,
        role="employee",
        department=department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["user_id"] = user.id
    return {"ok": True, "user": user_payload(user)}


@app.post("/api/logout")
def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.post("/api/heartbeat")
def api_heartbeat(payload: dict = Body(...), db: Session = Depends(get_db)):
    token = str(payload.get("token") or "")
    if token != config.AGENT_TOKEN:
        return JSONResponse({"ok": False, "error": "bad agent token"}, status_code=401)
    username = str(payload.get("username", "")).strip().lower()
    user = db.query(User).filter_by(username=username).first()
    if not user:
        return JSONResponse({"ok": False, "error": "unknown employee"}, status_code=404)
    present = payload.get("present")
    present_int = None if present is None else int(bool(present))
    clocked_in = analytics.auto_clock_in_if_needed(db, user.id)
    db.add(
        Heartbeat(
            user_id=user.id,
            present=present_int,
            idle=bool(payload.get("idle")),
            idle_seconds=int(payload.get("idle_seconds") or 0),
            app=str(payload.get("app") or "unknown")[:80],
            window_title=str(payload.get("window_title") or "")[:180],
            device=str(payload.get("device") or "unknown")[:20],
            created_at=utc_now(),
        )
    )
    db.flush()
    start, end = analytics.day_range()
    summary = analytics.summarize(db, user.id, start, end)
    maybe_alert(
        db,
        user,
        present if present is None else bool(present),
        clocked_in,
        summary["break_left_seconds"],
    )
    db.commit()
    return {"ok": True, "clocked_in": clocked_in}


@app.post("/api/preview")
def api_preview(payload: dict = Body(...), db: Session = Depends(get_db)):
    if str(payload.get("token") or "") != config.AGENT_TOKEN:
        return JSONResponse({"ok": False}, status_code=401)
    user = db.query(User).filter_by(username=str(payload.get("username", "")).strip().lower()).first()
    if not user:
        return JSONResponse({"ok": False}, status_code=404)
    try:
        PREVIEW_FRAMES[user.id] = base64.b64decode(payload.get("image") or "")
        PREVIEW_META[user.id] = {"blocked": bool(payload.get("blocked"))}
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    return {"ok": True}


@app.get("/api/me/preview")
def api_me_preview(request: Request, db: Session = Depends(get_db)):
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    jpeg = PREVIEW_FRAMES.get(user.id)
    if not jpeg:
        return Response(status_code=204)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/me/face")
def api_me_face_status(request: Request, db: Session = Depends(get_db)):
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    count = face_id.enrollment_count(user.id)
    ready = face_id.has_enrollment(user.id)
    return {
        "ok": True,
        "enrolled": ready,
        "count": count,
        "needed": max(0, face_id.MIN_ENROLL_SAMPLES - count),
        "min_samples": face_id.MIN_ENROLL_SAMPLES,
        "has_photo": face_id.thumb_path(user.id).is_file(),
    }


@app.get("/api/me/face/photo")
def api_me_face_photo(request: Request, db: Session = Depends(get_db)):
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    jpeg = face_id.read_thumbnail(user.id)
    if not jpeg:
        return Response(status_code=204)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/me/face/enroll")
def api_me_face_enroll(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Capture face samples for this employee only."""
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    try:
        raw = base64.b64decode(payload.get("image") or "")
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        frame = None
    if frame is None:
        return JSONResponse({"ok": False, "error": "bad image"}, status_code=400)
    _, yunet = get_detector()
    result = face_id.enroll_from_frame(user.id, frame, yunet)
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)


@app.delete("/api/me/face")
def api_me_face_clear(request: Request, db: Session = Depends(get_db)):
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    face_id.clear_enrollment(user.id)
    return {"ok": True}


@app.post("/api/me/apps")
def api_me_apps(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Windows agent: desktop app only (no camera). Merged into browser presence heartbeats."""
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    analytics.close_overnight_sessions(db, user.id)
    if analytics.open_session(db, user.id) is None:
        return JSONResponse({"ok": False, "error": "clocked out"}, status_code=400)
    app_name = str(payload.get("app") or "Unknown")[:80]
    window_title = str(payload.get("window_title") or "")[:180]
    locked = analytics.is_lock_screen(app_name, window_title)
    save_agent_foreground(user.id, app_name, window_title)
    last = (
        db.query(Heartbeat)
        .filter(Heartbeat.user_id == user.id)
        .order_by(Heartbeat.id.desc())
        .first()
    )
    min_gap = float(getattr(config, "TRACK_MIN_INTERVAL", 3))
    # Win+L: force away heartbeats so break allowance is consumed even if Chrome is frozen
    if locked:
        try:
            face_id._last_match_at.pop(user.id, None)
        except Exception:
            pass
        if last is not None and (analytics.seconds_ago(last.created_at) or 999) < min_gap:
            last.present = 0
            last.app = app_name
            last.window_title = window_title or "Lock screen"
            last.device = "laptop"
            last.idle = False
        else:
            db.add(
                Heartbeat(
                    user_id=user.id,
                    present=0,
                    idle=False,
                    idle_seconds=0,
                    app=app_name,
                    window_title=window_title or "Lock screen",
                    device="laptop",
                    created_at=utc_now(),
                )
            )
        db.commit()
        return {"ok": True, "app": "Lock screen", "locked": True}

    if last is not None and (analytics.seconds_ago(last.created_at) or 999) < 90:
        last.app = app_name
        last.window_title = window_title
        last.device = "laptop"
        db.commit()
    return {"ok": True, "app": analytics.pretty_app_name(app_name), "locked": False}


def _resolve_app_fields(user_id: int, payload: dict) -> tuple[str, str, str]:
    fg = load_agent_foreground(user_id, max_age=90.0)
    if fg.get("app"):
        return (
            str(fg.get("app") or "Unknown")[:80],
            str(fg.get("title") or "")[:180],
            "laptop",
        )
    return (
        str(payload.get("app") or "Browser")[:80],
        str(payload.get("window_title") or "My desk")[:180],
        str(payload.get("device") or "browser")[:20],
    )


@app.post("/api/me/track")
def api_me_track(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Browser camera frames while clocked in. Face identity + presence. Video is not stored."""
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    analytics.close_overnight_sessions(db, user.id)
    if analytics.open_session(db, user.id) is None:
        return JSONResponse({"ok": False, "error": "clocked out"}, status_code=400)
    try:
        raw = base64.b64decode(payload.get("image") or "")
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        frame = None
    if frame is None:
        return JSONResponse({"ok": False, "error": "bad image"}, status_code=400)

    app_name, window_title, device = _resolve_app_fields(user.id, payload)
    last = (
        db.query(Heartbeat)
        .filter(Heartbeat.user_id == user.id)
        .order_by(Heartbeat.id.desc())
        .first()
    )
    min_gap = float(getattr(config, "TRACK_MIN_INTERVAL", 3))

    # Camera shutter / covered lens (often not pure black) → ABSENT
    if float(np.mean(frame)) < 40.0:
        try:
            face_id._last_match_at.pop(user.id, None)
        except Exception:
            pass
        if last is not None and (analytics.seconds_ago(last.created_at) or 999) < min_gap:
            last.present = 0
            last.idle = False
            last.idle_seconds = 0
            last.app = app_name
            last.window_title = window_title
            last.device = device
            # keep created_at so time between samples still accumulates
        else:
            db.add(
                Heartbeat(
                    user_id=user.id,
                    present=0,
                    idle=False,
                    idle_seconds=0,
                    app=app_name,
                    window_title=window_title,
                    device=device,
                    created_at=utc_now(),
                )
            )
        db.flush()
        start, end = analytics.day_range()
        summary = analytics.summarize(db, user.id, start, end)
        maybe_alert(db, user, False, True, summary["break_left_seconds"])
        db.commit()
        return {
            "ok": True,
            "present": False,
            "marks": [],
            "identity": {
                "required": face_id.has_enrollment(user.id),
                "matched": False,
                "score": 0.0,
                "reason": "shutter_or_dark",
            },
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "skipped": "dark_frame",
        }

    net, yunet = get_detector()
    present, annotated, _score, marks = detector.annotate(frame, net, yunet)
    identity = {"required": False, "matched": True, "score": 0.0, "reason": "not_enrolled"}
    matched_box = None
    if face_id.has_enrollment(user.id):
        matched, score, reason, matched_box = face_id.verify(
            user.id, frame, yunet, require_desk_zone=True
        )
        identity = {"required": True, "matched": matched, "score": round(score, 3), "reason": reason}
        present = bool(matched)
        marks = face_id.mark_identity_boxes(marks, matched, matched_box)
        status = "Status: PRESENT (you)" if present else f"Status: ABSENT ({reason})"
        color = (0, 255, 0) if present else (0, 0, 255)
        cv2.putText(annotated, status, (12, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        maybe_identity_alert(db, user, identity)
    ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if ok:
        PREVIEW_FRAMES[user.id] = buf.tobytes()
        PREVIEW_META[user.id] = {"blocked": False}

    if (
        last is not None
        and last.present == 1
        and not present
        and identity.get("reason") in {"no_face", "hold"}
        and (analytics.seconds_ago(last.created_at) or 999) < float(config.IDENTITY_HOLD_SECONDS)
    ):
        present = True
        identity = {**identity, "matched": True, "reason": "hold"}

    # Win+L reported by agent overrides face hold — you are away on break
    if analytics.is_lock_screen(app_name, window_title):
        present = False
        try:
            face_id._last_match_at.pop(user.id, None)
        except Exception:
            pass

    if last is not None and (analytics.seconds_ago(last.created_at) or 999) < min_gap:
        # Refresh live fields only — do NOT bump created_at (that broke seated/apps timers)
        last.present = int(bool(present))
        last.idle = False
        last.idle_seconds = 0
        last.app = app_name
        last.window_title = window_title
        last.device = device
    else:
        db.add(
            Heartbeat(
                user_id=user.id,
                present=int(bool(present)),
                idle=False,
                idle_seconds=0,
                app=app_name,
                window_title=window_title,
                device=device,
                created_at=utc_now(),
            )
        )
    db.flush()
    start, end = analytics.day_range()
    summary = analytics.summarize(db, user.id, start, end)
    maybe_alert(db, user, bool(present), True, summary["break_left_seconds"])
    db.commit()
    return {
        "ok": True,
        "present": bool(present),
        "marks": marks,
        "identity": identity,
        "width": int(frame.shape[1]),
        "height": int(frame.shape[0]),
        "app": analytics.pretty_app_name(app_name),
        "today": {
            "seated": summary["seated"],
            "active": summary["active"],
            "idle": summary["idle"],
            "apps": summary["apps"],
            "break_left": summary["break_left"],
        },
    }


@app.get("/api/hr/preview/{user_id}")
def api_hr_preview(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not require(request, db, "hr"):
        return JSONResponse({"ok": False}, status_code=401)
    emp = db.get(User, user_id)
    if not emp or emp.role != "employee":
        return Response(status_code=404)
    jpeg = PREVIEW_FRAMES.get(user_id)
    if not jpeg:
        return Response(status_code=204)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/team")
def api_team(request: Request, db: Session = Depends(get_db)):
    if not require(request, db, "hr"):
        return JSONResponse({"ok": False}, status_code=401)
    if config.SEED_DEMO:
        _keep_demo_fresh(db)
    employees = db.query(User).filter_by(role="employee").order_by(User.name).all()
    team = [employee_card(db, emp) for emp in employees]
    db.commit()
    counts = {"present": 0, "away": 0, "idle": 0, "inactive": 0, "break": 0, "offline": 0, "clocked-out": 0}
    for person in team:
        counts[person["status"]] = counts.get(person["status"], 0) + 1
    alerts = (
        db.query(Alert, User.name)
        .join(User, User.id == Alert.user_id)
        .order_by(Alert.id.desc())
        .limit(30)
        .all()
    )
    return {
        "ok": True,
        "work_hours": analytics.inside_work_hours(),
        "away_minutes": config.AWAY_ALERT_SECONDS // 60,
        "break_minutes": config.BREAK_ALLOWANCE_SECONDS // 60,
        "team": team,
        "counts": counts,
        "alerts": [
            {
                "id": alert.id,
                "message": alert.message,
                "created_at": iso(alert.created_at),
                "seen": alert.seen,
                "name": name,
            }
            for alert, name in alerts
        ],
    }


def serialize_employee(db: Session, emp: User, day=None) -> dict:
    day = analytics.parse_day(day)
    start, end = analytics.day_range(day)
    timeline = (
        db.query(Heartbeat)
        .filter(Heartbeat.user_id == emp.id, Heartbeat.created_at >= start, Heartbeat.created_at < end)
        .order_by(Heartbeat.id.desc())
        .limit(80)
        .all()
    )
    card = employee_card(db, emp, day=day)
    card["days"] = analytics.activity_days(db, emp.id)
    card["timeline"] = [
        {
            "present": row.present,
            "idle": row.idle,
            "app": analytics.pretty_app_name(row.app),
            "window_title": row.window_title,
            "device": row.device,
            "created_at": iso(row.created_at),
        }
        for row in timeline
    ]
    return card


@app.get("/api/employee/{user_id}")
def api_employee(user_id: int, request: Request, day: str | None = None, db: Session = Depends(get_db)):
    viewer = current_user(request, db)
    if not viewer:
        return JSONResponse({"ok": False}, status_code=401)
    if viewer.role != "hr" and viewer.id != user_id:
        return JSONResponse({"ok": False}, status_code=403)
    emp = db.get(User, user_id)
    if not emp:
        return JSONResponse({"ok": False}, status_code=404)
    try:
        chosen = analytics.parse_day(day)
    except ValueError:
        return JSONResponse({"ok": False, "error": "bad date"}, status_code=400)
    payload = serialize_employee(db, emp, day=chosen)
    db.commit()
    return {"ok": True, **payload}


@app.get("/api/me")
def api_me(request: Request, db: Session = Depends(get_db)):
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    payload = serialize_employee(db, user)
    db.commit()
    return {"ok": True, **payload}


@app.post("/api/clock")
def api_clock(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    user = require(request, db, "employee")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    analytics.close_overnight_sessions(db, user.id)
    open_row = analytics.open_session(db, user.id)
    if payload.get("action") == "in" and open_row is None:
        db.add(WorkSession(user_id=user.id, clock_in=utc_now()))
    elif payload.get("action") == "out" and open_row is not None:
        open_row.clock_out = utc_now()
        PREVIEW_FRAMES.pop(user.id, None)
        PREVIEW_META.pop(user.id, None)
    db.commit()
    clocked_in = analytics.open_session(db, user.id) is not None
    return {"ok": True, "clocked_in": clocked_in}


@app.get("/api/agent/state")
def api_agent_state(username: str, token: str, db: Session = Depends(get_db)):
    if token != config.AGENT_TOKEN:
        return JSONResponse({"ok": False}, status_code=401)
    user = db.query(User).filter_by(username=username.strip().lower()).first()
    if not user:
        return JSONResponse({"ok": False}, status_code=404)
    analytics.close_overnight_sessions(db, user.id)
    return {
        "ok": True,
        "clocked_in": analytics.open_session(db, user.id) is not None,
    }


@app.get("/api/people")
def api_people_get(request: Request, db: Session = Depends(get_db)):
    if not require(request, db, "hr"):
        return JSONResponse({"ok": False}, status_code=401)
    rows = db.query(User).order_by(User.role, User.name).all()
    return {
        "ok": True,
        "people": [
            {
                "id": u.id,
                "username": u.username,
                "name": u.name,
                "role": u.role,
                "department": u.department,
            }
            for u in rows
        ],
    }


@app.post("/api/people")
def api_people_post(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    from passwords import hash_password

    if not require(request, db, "hr"):
        return JSONResponse({"ok": False}, status_code=401)
    username = str(payload.get("username") or "").strip().lower()
    name = str(payload.get("name") or "").strip()
    department = str(payload.get("department") or "Engineering").strip() or "Engineering"
    password = str(payload.get("password") or "emp123")
    if not username or not name:
        return JSONResponse({"ok": False, "error": "Name and username are required."}, status_code=400)
    if db.query(User).filter_by(username=username).first():
        return JSONResponse({"ok": False, "error": "That username is already taken."}, status_code=409)
    db.add(
        User(
            username=username,
            password=hash_password(password),
            name=name,
            role="employee",
            department=department,
        )
    )
    db.commit()
    return {"ok": True}


@app.post("/api/alerts/{alert_id}/seen")
def api_alert_seen(alert_id: int, request: Request, db: Session = Depends(get_db)):
    if not require(request, db, "hr"):
        return JSONResponse({"ok": False}, status_code=401)
    alert = db.get(Alert, alert_id)
    if alert:
        alert.seen = True
        db.commit()
    return {"ok": True}


@app.get("/api/report")
def api_report(request: Request, day: str | None = None, db: Session = Depends(get_db)):
    if not require(request, db, "hr"):
        return JSONResponse({"ok": False}, status_code=401)
    try:
        chosen = analytics.parse_day(day)
    except ValueError:
        return JSONResponse({"ok": False, "error": "bad date"}, status_code=400)
    employees = db.query(User).filter_by(role="employee").order_by(User.name).all()
    team = [employee_card(db, emp, day=chosen) for emp in employees]
    db.commit()
    return {
        "ok": True,
        "day": chosen.isoformat(),
        "is_today": analytics.is_today(chosen),
        "days": analytics.activity_days(db),
        "team": team,
    }


@app.get("/hr/export.csv")
def hr_export(request: Request, day: str | None = None, db: Session = Depends(get_db)):
    if not require(request, db, "hr"):
        return RedirectResponse("/login", status_code=302)
    try:
        chosen = analytics.parse_day(day)
    except ValueError:
        chosen = analytics.local_now().date()
    employees = db.query(User).filter_by(role="employee").order_by(User.name).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["day", "name", "department", "status", "seated", "active", "idle", "break_used", "work_apps", "other_apps", "useful_pct"]
    )
    for emp in employees:
        card = employee_card(db, emp, day=chosen)
        t = card["today"]
        writer.writerow(
            [
                chosen.isoformat(),
                card["name"],
                card["department"],
                card["status"],
                t["seated"],
                t["active"],
                t["idle"],
                t.get("break_used", "0m"),
                t["work"],
                t["other"],
                t["useful_pct"],
            ]
        )
    db.commit()
    stamp = chosen.isoformat()
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=desktrack-{stamp}.csv"},
    )


@app.get("/assets/{file_path:path}")
def spa_assets(file_path: str):
    root = (DIST / "assets").resolve()
    target = (root / file_path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return JSONResponse({"ok": False}, status_code=404)
    return FileResponse(target)


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("hr/export") or full_path.startswith("docs"):
        return JSONResponse({"ok": False}, status_code=404)
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse(
        {
            "ok": False,
            "error": "UI not built. In frontend/ run: npm install && npm run build",
            "dev": "http://127.0.0.1:5173",
        },
        status_code=503,
    )


if __name__ == "__main__":
    print(f"DeskTrack  {config.PUBLIC_URL}")
    if not config.PRODUCTION:
        print("UI (dev)   http://127.0.0.1:5173")
        print("HR         hr / hr123")
        print("Employee   saniya / emp123")
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
