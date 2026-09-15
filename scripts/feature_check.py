"""One-shot feature check against a running DeskTrack server."""
from __future__ import annotations

import base64
import http.cookiejar
import json
import urllib.error
import urllib.request

import cv2
import numpy as np

BASE = "http://127.0.0.1:8000"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, f"{'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else "")))


def req(method: str, path: str, data=None, expect: int | None = None):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=60) as res:
            raw = res.read()
            ctype = res.headers.get("Content-Type", "")
            if "json" in ctype or (raw[:1] in (b"{", b"[")):
                payload = json.loads(raw.decode())
            else:
                payload = raw
            if expect is not None:
                check(res.status == expect, f"{method} {path}", f"status={res.status}")
            return res.status, payload
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw.decode())
        except Exception:
            payload = raw[:200]
        if expect is not None:
            check(e.code == expect, f"{method} {path}", f"status={e.code}")
        return e.code, payload


def main() -> None:
    global cj, opener

    st, health = req("GET", "/health", expect=200)
    check(health.get("ok") is True, "health ok")

    st, html = req("GET", "/login", expect=200)
    check(isinstance(html, bytes) and b"DeskTrack" in html, "SPA serves index.html")

    req("GET", "/api/session", expect=401)
    req("GET", "/api/team", expect=401)

    st, data = req("POST", "/api/login", {"username": "hr", "password": "hr123"}, expect=200)
    check(data.get("user", {}).get("role") == "hr", "HR login")
    req("GET", "/api/session", expect=200)
    st, team = req("GET", "/api/team", expect=200)
    check(isinstance(team.get("team"), list), "HR live team API", f"employees={len(team.get('team', []))}")
    req("GET", "/api/report", expect=200)
    req("GET", "/api/people", expect=200)
    st, csvb = req("GET", "/hr/export.csv", expect=200)
    check(isinstance(csvb, bytes) and b"day," in csvb[:50], "CSV export")

    req("POST", "/api/logout", {}, expect=200)

    uname = "qa_emp_check"
    st, su = req(
        "POST",
        "/api/signup",
        {"name": "QA Employee", "username": uname, "password": "test1234", "department": "QA"},
    )
    if st == 409:
        st, su = req("POST", "/api/login", {"username": uname, "password": "test1234"}, expect=200)
        check(True, "employee login (existing QA user)")
    else:
        check(st == 200 and su.get("user", {}).get("role") == "employee", "employee signup", f"status={st}")

    req("GET", "/api/me", expect=200)
    req("POST", "/api/clock", {"action": "in"}, expect=200)

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(frame, (80, 40), (240, 200), (40, 40, 200), -1)
    ok, buf = cv2.imencode(".jpg", frame)
    b64 = base64.b64encode(buf.tobytes()).decode()
    st, track = req(
        "POST",
        "/api/me/track",
        {"image": b64, "idle_seconds": 2, "app": "Browser", "window_title": "QA", "device": "laptop"},
        expect=200,
    )
    check("present" in track and "marks" in track, "camera track / YOLO", f"keys={list(track) if isinstance(track, dict) else track}")

    req("POST", "/api/clock", {"action": "out"}, expect=200)
    req("POST", "/api/logout", {}, expect=200)

    req("POST", "/api/login", {"username": "hr", "password": "hr123"}, expect=200)
    st, people = req("GET", "/api/people", expect=200)
    emps = [p for p in people.get("people", []) if p["role"] == "employee"]
    check(any(p["username"] == uname for p in emps), "HR people lists employee")
    eid = next(p["id"] for p in emps if p["username"] == uname)
    req("GET", f"/api/employee/{eid}", expect=200)
    st, _ = req("GET", f"/api/hr/preview/{eid}")
    check(st in (200, 204), "HR preview endpoint", f"status={st}")

    # mark alert seen if any
    st, team = req("GET", "/api/team", expect=200)
    for alert in team.get("alerts", [])[:1]:
        req("POST", f"/api/alerts/{alert['id']}/seen", {}, expect=200)
        check(True, "alert acknowledge")
        break
    else:
        check(True, "alert acknowledge (none to ack)")

    req("POST", "/api/logout", {}, expect=200)
    req("POST", "/api/login", {"username": "hr", "password": "wrong"}, expect=401)
    check(True, "bad password rejected")

    # cleanup QA employee
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from models import Alert, Heartbeat, SessionLocal, User, WorkSession

    db = SessionLocal()
    user = db.query(User).filter_by(username=uname).first()
    if user:
        db.query(Heartbeat).filter_by(user_id=user.id).delete()
        db.query(Alert).filter_by(user_id=user.id).delete()
        db.query(WorkSession).filter_by(user_id=user.id).delete()
        db.delete(user)
        db.commit()
        check(True, "cleanup QA employee")
    db.close()

    print("=== DeskTrack feature check ===")
    fails = 0
    for ok, line in results:
        print(line)
        if not ok:
            fails += 1
    print(f"\n{len(results) - fails}/{len(results)} checks passed")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
