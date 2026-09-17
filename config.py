"""DeskTrack settings — local defaults, override with env / .env for production."""

from __future__ import annotations

import os
from pathlib import Path

import tzdata  # noqa: F401 — Windows needs IANA zones
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


ENV = os.getenv("DESKTRACK_ENV", "development").strip().lower()
PRODUCTION = ENV in {"production", "prod"}

SECRET_KEY = os.getenv("SECRET_KEY", "desk-track-local-dev")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "desk-local")


def _resolve_database_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    default = f"sqlite:///{(ROOT / 'office.db').as_posix()}"
    if not raw:
        return default
    # Docker-only absolute path from .env.example — ignore on Windows / non-Docker hosts
    if raw.startswith("sqlite:////app/") and not Path("/app").exists():
        return default
    if raw.startswith("sqlite:///"):
        # sqlite:///office.db  → relative to project root
        # sqlite:////abs/path  → absolute (four slashes)
        rest = raw[len("sqlite:///") :]
        if rest.startswith("/") or (len(rest) > 1 and rest[1] == ":"):
            db_path = Path(rest)
        else:
            db_path = ROOT / rest
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.resolve().as_posix()}"
    return raw


DATABASE_URL = _resolve_database_url()
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))

HEARTBEAT_SECONDS = _int("HEARTBEAT_SECONDS", 4)
IDLE_AFTER_SECONDS = _int("IDLE_AFTER_SECONDS", 60)
AWAY_ALERT_SECONDS = _int("AWAY_ALERT_SECONDS", 900)
BREAK_ALLOWANCE_SECONDS = _int("BREAK_ALLOWANCE_SECONDS", 30 * 60)
OFFLINE_AFTER_SECONDS = _int("OFFLINE_AFTER_SECONDS", 25)
# Treat heartbeat gaps longer than this as laptop sleep (Idle KPI)
SLEEP_GAP_SECONDS = _int("SLEEP_GAP_SECONDS", 45)
# Keep "present" briefly if face briefly leaves frame / looks away
IDENTITY_HOLD_SECONDS = _int("IDENTITY_HOLD_SECONDS", 450)
# Delete heartbeats older than this (keeps SQLite small). Reports only need recent days.
HEARTBEAT_KEEP_DAYS = _int("HEARTBEAT_KEEP_DAYS", 14)
# Delete acknowledged alerts older than this
ALERT_KEEP_DAYS = _int("ALERT_KEEP_DAYS", 30)
# Min seconds between stored heartbeats per user (dedupe browser pings)
TRACK_MIN_INTERVAL = float(os.getenv("TRACK_MIN_INTERVAL", "3"))
# Optional: POST JSON alerts to Slack/Teams/Discord/custom webhook when HR is offline
HR_ALERT_WEBHOOK = os.getenv("HR_ALERT_WEBHOOK", "").strip()
HR_ALERT_EMAIL = os.getenv("HR_ALERT_EMAIL", "").strip()

WORK_START_HOUR = _int("WORK_START_HOUR", 9)
WORK_END_HOUR = _int("WORK_END_HOUR", 19)

HOST = os.getenv("HOST", "127.0.0.1" if not PRODUCTION else "0.0.0.0")
PORT = _int("PORT", 8000)
RELOAD = _bool("RELOAD", not PRODUCTION)
HTTPS_ONLY = _bool("HTTPS_ONLY", PRODUCTION)
SEED_DEMO = _bool("SEED_DEMO", not PRODUCTION)
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
SERVER_URL = PUBLIC_URL

_cors = os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
CORS_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]

WORK_APPS = {
    "code.exe",
    "code - insiders.exe",
    "cursor.exe",
    "devenv.exe",
    "pycharm64.exe",
    "idea64.exe",
    "excel.exe",
    "winword.exe",
    "powerpnt.exe",
    "outlook.exe",
    "olk.exe",
    "slack.exe",
    "teams.exe",
    "ms-teams.exe",
    "zoom.exe",
    "notepad.exe",
    "notepad++.exe",
    "windowsterminal.exe",
    "powershell.exe",
    "cmd.exe",
    "python.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "figma.exe",
}

DISTRACTION_WORDS = (
    "youtube",
    "instagram",
    "facebook",
    "netflix",
    "hotstar",
    "prime video",
    "reddit",
    "twitter",
    "x.com",
    "game",
)

# Friendly labels for Apps today / live board
APP_DISPLAY_NAMES = {
    "browser": "Browser",
    "chrome": "Chrome",
    "msedge": "Edge",
    "edge": "Edge",
    "firefox": "Firefox",
    "safari": "Safari",
    "opera": "Opera",
    "brave": "Brave",
    "chromium": "Chromium",
    "cursor": "Cursor",
    "code": "VS Code",
    "code - insiders": "VS Code Insiders",
    "devenv": "Visual Studio",
    "lockapp": "Lock screen",
    "logonui": "Lock screen",
    "lockapp.exe": "Lock screen",
    "logonui.exe": "Lock screen",
    "pycharm64": "PyCharm",
    "idea64": "IntelliJ IDEA",
    "excel": "Excel",
    "winword": "Word",
    "powerpnt": "PowerPoint",
    "outlook": "Outlook",
    "olk": "Outlook",
    "slack": "Slack",
    "teams": "Teams",
    "ms-teams": "Teams",
    "zoom": "Zoom",
    "notepad": "Notepad",
    "notepad++": "Notepad++",
    "windowsterminal": "Terminal",
    "powershell": "PowerShell",
    "cmd": "Command Prompt",
    "python": "Python",
    "figma": "Figma",
    "explorer": "File Explorer",
    "searchhost": "Windows Search",
    "applicationframehost": "Windows App",
    "shellhost": "Windows Shell",
    "lockapp": "Lock screen",
    "snippingtool": "Snipping Tool",
    "spotify": "Spotify",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
}


def validate_production() -> None:
    if not PRODUCTION:
        return
    weak = {"desk-track-local-dev", "change-me", "", "secret"}
    if SECRET_KEY in weak or len(SECRET_KEY) < 24:
        raise RuntimeError(
            "Set a strong SECRET_KEY in .env before running in production (24+ random chars)."
        )
    if AGENT_TOKEN in {"desk-local", "change-me", ""}:
        raise RuntimeError("Set AGENT_TOKEN in .env before running in production.")
