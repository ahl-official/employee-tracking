"""
DeskTrack Windows agent — apps only (split mode).

Browser (Chrome) owns the webcam for face + presence.
This agent only reports the foreground desktop app to the server.

Setup: Install-DeskTrack-Agent.bat once (Startup + hidden).
"""

from __future__ import annotations

import configparser
import ctypes
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.ini"
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


def foreground_window() -> tuple[str, str]:
    if sys.platform != "win32":
        return "Unknown", ""
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
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
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
    if res.json().get("clocked_in"):
        return True
    res = session.post(f"{base}/api/clock", json={"action": "in"}, timeout=15)
    return res.status_code == 200


def main() -> None:
    cfg = load_config()
    base = cfg.get("server", "url", fallback="http://127.0.0.1:8000").rstrip("/")
    username = cfg.get("auth", "username", fallback="").strip()
    password = cfg.get("auth", "password", fallback="")
    interval = cfg.getfloat("agent", "interval_seconds", fallback=3.0)
    auto_clock_in = cfg.getboolean("agent", "auto_clock_in", fallback=True)

    if not username or not password:
        log("Set username and password in config.ini")
        sys.exit(1)

    session = requests.Session()
    log(f"Logging in as {username} -> {base}")
    user = login(session, base, username, password)
    if user.get("role") != "employee":
        log("Agent is for employee accounts only.")
        sys.exit(1)
    log(f"Hello {user.get('name')}. Apps-only agent (camera stays in Chrome).")

    if auto_clock_in:
        if ensure_clocked_in(session, base):
            log("Clocked in.")
        else:
            log("Could not clock in — open the website and Clock in.")

    prevent_sleep(True)
    log("Reporting desktop apps. Keep My desk open in Chrome for face/presence.")
    last = ""
    try:
        while True:
            app_name, win_title = foreground_window()
            try:
                res = session.post(
                    f"{base}/api/me/apps",
                    json={"app": app_name, "window_title": win_title},
                    timeout=15,
                )
                if res.status_code == 400 and "clocked out" in (res.text or "").lower():
                    if auto_clock_in and ensure_clocked_in(session, base):
                        log("Re-clocked in.")
                    else:
                        msg = "Clocked out — waiting…"
                        if msg != last:
                            log(msg)
                            last = msg
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
                msg = f"app={app_name}"
                if msg != last:
                    log(msg)
                    last = msg
            except requests.RequestException as exc:
                log(f"offline ({exc})")
            time.sleep(max(2.0, interval))
    except KeyboardInterrupt:
        log("Stopping…")
    finally:
        prevent_sleep(False)
        log("Agent stopped.")


if __name__ == "__main__":
    main()
