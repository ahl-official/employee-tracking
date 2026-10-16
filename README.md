# DeskTrack

Workplace presence and productivity tracking for small teams.

Employees **clock in** from the browser with the webcam on for face/presence. A lightweight **Windows agent** reports which desktop app is focused. HR gets a live board, daily totals, break usage, and alerts — without storing video.

---

## How it works

| Piece | Role |
|--------|------|
| **Browser (Chrome) → My desk** | Camera, face identity, seated / away / break |
| **Windows agent** | Foreground app name + window title (no camera) |
| **Server (FastAPI)** | Auth, heartbeats, analytics, HR dashboard |
| **SQLite** | Users, sessions, heartbeats, alerts |

**Split mode:** the browser owns the webcam; the agent only sends apps. That avoids camera conflicts on Windows.

Frames are processed in memory for presence. **Video is not saved.**

---

## Features

### Employees
- Create account or sign in
- Enroll face once, then clock in with camera allowed
- Live desk view (desk zone overlay)
- Today’s **Seated**, **Idle**, **Active (apps)**, **Break**, **Presence %**
- **Apps today** — desktop apps and browser tabs (e.g. Figma, Gmail, YouTube)
- Account page to change name / username / password
- Reset credentials on the login page (needs current password)

### HR
- Live board of who is present / away / on break / offline
- Daily report (IST calendar day) with CSV export
- People — add employees, reset website login
- Alerts when away past break allowance during work hours
- Optional webhook for HR pings (`HR_ALERT_WEBHOOK`)

### Metrics (while clocked in)

| Metric | Meaning |
|--------|---------|
| **Seated** | Face visible at the desk |
| **Idle** | Clocked in but face not seen (away, lock, sleep, no camera) |
| **Seated + Idle** | Time from clock-in → clock-out (capped at 9h workday target) |
| **Presence %** | Seated ÷ 9h workday |
| **Active** | Time apps were in use (excludes lock screen) |
| **Work apps %** | Share of app time in work apps vs other (e.g. YouTube in title) |
| **Break used** | Away / lock time, capped at 30 minutes |

Website **Reset login** changes only the website password. The agent keeps a separate frozen **agent password**, so app tracking does not break when HR resets login.

---

## Stack

- **Backend:** Python 3, FastAPI, SQLAlchemy, SQLite  
- **Vision:** OpenCV, YuNet / YOLO (desk presence + face match)  
- **Frontend:** React + Vite  
- **Agent:** Python on Windows (`agent/`)  
- **Deploy:** Docker Compose (see [DEPLOY.md](DEPLOY.md))

---

## Quick start (local)

### 1. Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
python -c "from database import init_db; init_db()"
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Fresh local DB demo logins (change in production):

| Role | Username | Password |
|------|----------|----------|
| HR | `hr` | `hr123` |
| Employee (if seeded) | `saniya` | `emp123` |

### 2. Frontend (dev)

```bash
cd frontend
npm install
npm run dev
```

Vite proxies to the API. For production, `npm run build` writes to `frontend/dist` (served by FastAPI).

### 3. Windows agent (employee PC)

See [agent/README.md](agent/README.md).

1. Install Python 3 (add to PATH)  
2. Run `agent/Install-DeskTrack-Agent.bat`  
3. Enter server URL, username, and password  
4. Employee enrolls face → **Clock in** → keep **My desk** open in Chrome  

The agent starts hidden and on Windows login. It self-updates its script from GitHub on start (keeps `config.ini`).

---

## Production deploy

Use a VPS (not serverless): camera/YOLO and SQLite need a persistent host.

```bash
cp .env.example .env
# Set DESKTRACK_ENV=production, SECRET_KEY, AGENT_TOKEN, PUBLIC_URL, HTTPS_ONLY, …

docker compose up -d --build
```

Full steps (disk size, Nginx/HTTPS, first login): **[DEPLOY.md](DEPLOY.md)**.

Camera in Chrome requires **HTTPS** (or localhost). Use a domain + reverse proxy (`deploy/nginx.conf`).

---

## Project layout

```
├── main.py              # FastAPI routes (auth, track, apps, HR APIs)
├── analytics.py         # Seated / idle / apps / presence summaries
├── face_id.py           # Face enrollment + match
├── detector.py          # Desk-zone presence (YuNet / YOLO)
├── config.py            # Settings (env / .env)
├── database.py          # SQLite init + cleanup
├── models.py            # Users, heartbeats, sessions, alerts
├── frontend/            # React UI (HR + employee)
├── agent/               # Windows apps-only agent + installer
├── deploy/              # Nginx, systemd examples
├── docs/                # Identity & alerts notes
└── DEPLOY.md            # VPS / Docker guide
```

---

## Configuration (high level)

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Session signing (strong value in production) |
| `AGENT_TOKEN` | Shared secret for agent-facing endpoints |
| `PUBLIC_URL` | Public base URL of the app |
| `HTTPS_ONLY` | Secure cookies when behind HTTPS |
| `WORKDAY_SECONDS` | Presence denominator (default 9 hours) |
| `BREAK_ALLOWANCE_SECONDS` | Break budget (default 30 minutes) |
| `WORK_START_HOUR` / `WORK_END_HOUR` | When away alerts apply |
| `HR_ALERT_WEBHOOK` | Optional Slack/Teams/Discord webhook |

See `.env.example` for the full list.

---

## Typical employee day

1. Open DeskTrack in **Chrome** → sign in → **My desk**  
2. Allow camera → enroll face (first time) → **Clock in**  
3. Leave the tab open (can be in background)  
4. Windows agent sends apps in the background  
5. **Clock out** when done (e.g. lunch / end of day)

HR watches **Live board** and **Daily report**.

---

## Docs

- [DEPLOY.md](DEPLOY.md) — VPS / Docker / HTTPS  
- [agent/README.md](agent/README.md) — agent install  
- [docs/IDENTITY_AND_ALERTS.md](docs/IDENTITY_AND_ALERTS.md) — face identity and HR alerts  

---

## License

Private / internal use unless otherwise specified by the repository owner.
