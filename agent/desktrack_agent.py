"""
DeskTrack Windows agent — background camera tracking for one employee.

Features:
  - Uses the PC webcam (OpenCV)
  - Blocks Windows sleep while clocked in
  - Queues frames when offline, uploads when back online
  - Server matches YOUR enrolled face only (person-specific presence)

Setup:
  1. Copy config.example.ini → config.ini and fill server + login
  2. pip install -r requirements.txt
  3. Enroll your face once on the website (My desk → Enroll face)
  4. python desktrack_agent.py

Or double-click: "Start DeskTrack Agent.bat"
"""

from __future__ import annotations

import base64
import configparser
import sqlite3
import sys
import time
import ctypes
from datetime import datetime, timezone
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.ini"
QUEUE_DB = ROOT / "offline_queue.db"

# Windows: prevent sleep / display off while tracking
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def prevent_sleep(on: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        if on:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass


def load_config() -> configparser.ConfigParser:
    if not CONFIG_PATH.is_file():
        print(f"Missing {CONFIG_PATH}")
        print("Copy config.example.ini to config.ini and edit it.")
        sys.exit(1)
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def init_queue() -> None:
    con = sqlite3.connect(QUEUE_DB)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            image_b64 TEXT NOT NULL,
            idle_seconds INTEGER NOT NULL,
            app TEXT,
            window_title TEXT
        )
        """
    )
    con.commit()
    con.close()


def queue_add(image_b64: str, idle_seconds: int, app: str, title: str) -> None:
    con = sqlite3.connect(QUEUE_DB)
    # Cap queue so disk does not grow forever (~200 frames)
    count = con.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    if count >= 200:
        con.execute("DELETE FROM queue WHERE id IN (SELECT id FROM queue ORDER BY id LIMIT 50)")
    con.execute(
        "INSERT INTO queue (created_at, image_b64, idle_seconds, app, window_title) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), image_b64, idle_seconds, app, title),
    )
    con.commit()
    con.close()


def queue_flush(session: requests.Session, base: str) -> int:
    con = sqlite3.connect(QUEUE_DB)
    rows = con.execute(
        "SELECT id, image_b64, idle_seconds, app, window_title FROM queue ORDER BY id LIMIT 30"
    ).fetchall()
    sent = 0
    for row_id, image_b64, idle_seconds, app, title in rows:
        try:
            res = session.post(
                f"{base}/api/me/track",
                json={
                    "image": image_b64,
                    "idle_seconds": idle_seconds,
                    "app": app or "DeskTrack Agent",
                    "window_title": title or "Agent",
                    "device": "laptop",
                },
                timeout=20,
            )
            if res.status_code == 200:
                con.execute("DELETE FROM queue WHERE id = ?", (row_id,))
                sent += 1
            elif res.status_code in (401, 400):
                # clocked out / auth — drop stale
                con.execute("DELETE FROM queue WHERE id = ?", (row_id,))
            else:
                break
        except requests.RequestException:
            break
    con.commit()
    con.close()
    return sent


def login(session: requests.Session, base: str, username: str, password: str) -> dict:
    res = session.post(
        f"{base}/api/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    data = res.json() if res.content else {}
    if res.status_code != 200 or not data.get("ok"):
        raise RuntimeError(data.get("error") or f"Login failed ({res.status_code})")
    return data["user"]


def ensure_clocked_in(session: requests.Session, base: str) -> bool:
    res = session.get(f"{base}/api/me", timeout=15)
    if res.status_code != 200:
        return False
    data = res.json()
    if data.get("clocked_in"):
        return True
    res = session.post(f"{base}/api/clock", json={"action": "in"}, timeout=15)
    return res.status_code == 200 and res.json().get("clocked_in", True)


def main() -> None:
    cfg = load_config()
    base = cfg.get("server", "url", fallback="http://127.0.0.1:8000").rstrip("/")
    username = cfg.get("auth", "username", fallback="").strip()
    password = cfg.get("auth", "password", fallback="")
    camera_index = cfg.getint("agent", "camera_index", fallback=0)
    interval = cfg.getfloat("agent", "interval_seconds", fallback=2.0)
    auto_clock_in = cfg.getboolean("agent", "auto_clock_in", fallback=True)

    if not username or not password:
        print("Set username and password in config.ini")
        sys.exit(1)

    init_queue()
    session = requests.Session()
    print(f"Logging in as {username} → {base}")
    user = login(session, base, username, password)
    if user.get("role") != "employee":
        print("Agent is for employee accounts only.")
        sys.exit(1)
    print(f"Hello {user.get('name')}. Face must be enrolled on the website (My desk).")

    if auto_clock_in:
        if ensure_clocked_in(session, base):
            print("Clocked in.")
        else:
            print("Could not clock in — check the website.")

    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW if sys.platform == "win32" else 0)
    if not cap.isOpened():
        cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Cannot open camera index {camera_index}")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

    prevent_sleep(True)
    print("Tracking started. Keep this window open. Ctrl+C to stop.")
    print("Windows sleep is blocked while the agent runs.")

    last_input = time.time()
    last_status = ""
    try:
        while True:
            # Flush offline queue when possible
            try:
                n = queue_flush(session, base)
                if n:
                    print(f"Uploaded {n} queued frame(s).")
            except Exception:
                pass

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(1)
                continue

            # Simple idle: no keyboard activity API in headless agent → use 0 when sending live
            idle_seconds = 0
            ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
            if not ok_enc:
                time.sleep(interval)
                continue
            image_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

            try:
                res = session.post(
                    f"{base}/api/me/track",
                    json={
                        "image": image_b64,
                        "idle_seconds": idle_seconds,
                        "app": "DeskTrack Agent",
                        "window_title": "DeskTrack Agent",
                        "device": "laptop",
                    },
                    timeout=20,
                )
                if res.status_code == 400 and "clocked out" in (res.text or "").lower():
                    if auto_clock_in and ensure_clocked_in(session, base):
                        print("Re-clocked in.")
                    else:
                        print("Clocked out on server. Waiting…")
                        prevent_sleep(False)
                        time.sleep(5)
                        prevent_sleep(True)
                        continue
                if res.status_code == 401:
                    print("Session expired — logging in again…")
                    login(session, base, username, password)
                    continue
                if res.status_code != 200:
                    raise requests.RequestException(f"HTTP {res.status_code}")
                data = res.json()
                present = data.get("present")
                identity = data.get("identity") or {}
                msg = f"present={present}"
                if identity.get("required"):
                    msg += f" identity={identity.get('reason')} score={identity.get('score')}"
                if msg != last_status:
                    print(time.strftime("%H:%M:%S"), msg)
                    last_status = msg
            except requests.RequestException as exc:
                queue_add(image_b64, idle_seconds, "DeskTrack Agent", "Offline queue")
                print(f"{time.strftime('%H:%M:%S')} offline — queued ({exc})")

            time.sleep(max(1.0, interval))
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        prevent_sleep(False)
        cap.release()
        print("Agent stopped. Sleep allowed again.")


if __name__ == "__main__":
    main()
