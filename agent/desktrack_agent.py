"""
DeskTrack Windows agent — background camera tracking for one employee.

Features:
  - Uses the PC webcam (OpenCV)
  - Reports the real foreground desktop app (not just the browser)
  - Blocks Windows sleep while clocked in
  - Queues frames when offline, uploads when back online
  - Server matches YOUR enrolled face only (person-specific presence)

Setup: run Install-DeskTrack-Agent.bat once. It installs, starts hidden, and
adds a Startup entry so you do not need to run it every day.
"""

from __future__ import annotations

import base64
import configparser
import ctypes
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.ini"
QUEUE_DB = ROOT / "offline_queue.db"
LOG_PATH = ROOT / "agent.log"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


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


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds_windows() -> int:
    if sys.platform != "win32":
        return 0
    try:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0
        tick = ctypes.windll.kernel32.GetTickCount()
        return max(0, int((tick - info.dwTime) / 1000))
    except Exception:
        return 0


def foreground_window() -> tuple[str, str]:
    """Return (app_name, window_title) for the active desktop window."""
    if sys.platform != "win32":
        return "DeskTrack Agent", "Agent"
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "Desktop", ""
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = (buf.value or "").strip()

    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    app = "Unknown"
    if handle:
        try:
            size = ctypes.c_ulong(260)
            path_buf = ctypes.create_unicode_buffer(260)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path_buf, ctypes.byref(size)):
                app = Path(path_buf.value).stem or "Unknown"
        finally:
            kernel32.CloseHandle(handle)
    return app[:80], title[:180]


def load_config() -> configparser.ConfigParser:
    if not CONFIG_PATH.is_file():
        log(f"Missing {CONFIG_PATH}")
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
        log("Set username and password in config.ini")
        sys.exit(1)

    init_queue()
    session = requests.Session()
    log(f"Logging in as {username} -> {base}")
    user = login(session, base, username, password)
    if user.get("role") != "employee":
        log("Agent is for employee accounts only.")
        sys.exit(1)
    log(f"Hello {user.get('name')}. Tracking in background.")

    if auto_clock_in:
        if ensure_clocked_in(session, base):
            log("Clocked in.")
        else:
            log("Could not clock in — check the website.")

    cap = None
    for idx in (camera_index, 0, 1, 2):
        trial = cv2.VideoCapture(idx, cv2.CAP_DSHOW if sys.platform == "win32" else 0)
        if not trial.isOpened():
            trial = cv2.VideoCapture(idx)
        if not trial.isOpened():
            continue
        ok, test = trial.read()
        if ok and test is not None and float(test.mean()) >= 12.0:
            cap = trial
            camera_index = idx
            log(f"Using camera index {idx}")
            break
        trial.release()
    if cap is None:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW if sys.platform == "win32" else 0)
        if not cap.isOpened():
            cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        log(f"Cannot open camera index {camera_index}")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

    prevent_sleep(True)
    log("Tracking started (silent). Sleep blocked while running.")

    last_status = ""
    try:
        while True:
            try:
                n = queue_flush(session, base)
                if n:
                    log(f"Uploaded {n} queued frame(s).")
            except Exception:
                pass

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(1)
                continue

            idle_seconds = idle_seconds_windows()
            app_name, win_title = foreground_window()
            ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
            if not ok_enc:
                time.sleep(interval)
                continue
            mean = float(frame.mean())
            if mean < 12.0:
                # Still upload so server can record apps + hold last present (browser often holds cam)
                if last_status != "dark_frame":
                    log("Camera frame is dark (browser may be using the webcam). Still sending apps.")
                    last_status = "dark_frame"
            image_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

            try:
                res = session.post(
                    f"{base}/api/me/track",
                    json={
                        "image": image_b64,
                        "idle_seconds": idle_seconds,
                        "app": app_name,
                        "window_title": win_title,
                        "device": "laptop",
                    },
                    timeout=20,
                )
                if res.status_code == 400 and "clocked out" in (res.text or "").lower():
                    if auto_clock_in and ensure_clocked_in(session, base):
                        log("Re-clocked in.")
                    else:
                        log("Clocked out on server. Waiting…")
                        prevent_sleep(False)
                        time.sleep(5)
                        prevent_sleep(True)
                        continue
                if res.status_code == 401:
                    log("Session expired — logging in again…")
                    login(session, base, username, password)
                    continue
                if res.status_code != 200:
                    raise requests.RequestException(f"HTTP {res.status_code}")
                data = res.json()
                present = data.get("present")
                identity = data.get("identity") or {}
                msg = f"present={present} app={app_name}"
                if identity.get("required"):
                    msg += f" identity={identity.get('reason')} score={identity.get('score')}"
                if msg != last_status:
                    log(msg)
                    last_status = msg
            except requests.RequestException as exc:
                queue_add(image_b64, idle_seconds, app_name, win_title or "Offline queue")
                log(f"offline — queued ({exc})")

            time.sleep(max(1.0, interval))
    except KeyboardInterrupt:
        log("Stopping…")
    finally:
        prevent_sleep(False)
        cap.release()
        log("Agent stopped. Sleep allowed again.")


if __name__ == "__main__":
    main()
