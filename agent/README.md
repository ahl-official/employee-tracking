# DeskTrack Windows Agent

Background webcam tracker. Presence counts only when **your enrolled face** is at the desk.

## Why “Enroll face” is missing on the website

The VPS must be updated first:

```bash
cd /opt/desktrack
git pull
docker compose up -d --build
```

Then hard-refresh the site (`Ctrl+F5`). On **My desk** you should see **Your face (identity)** and an **Enroll face** button. It is not a separate browser popup — click the button.

## Employee setup (no Git / no full project needed)

### Option A — one installer (easiest)

1. HR downloads this file from the repo and shares it (email / shared drive):  
   `agent/Install-DeskTrack-Agent.bat`
2. Employee needs **Python 3** installed ([python.org](https://www.python.org/downloads/) — tick *Add to PATH*).
3. Employee double-clicks **Install-DeskTrack-Agent.bat**.
4. Enter server URL (default is fine) + username + password.
5. Installer downloads the agent, installs packages, creates a Desktop shortcut.

Then:

1. Open https://desktrack.hairscalptradingco.com → log in → **Enroll face**
2. Start **DeskTrack Agent** from the Desktop and leave it open while working

### Option B — zip folder

1. HR zips the `agent` folder from the project (or from GitHub → Code → Download ZIP → take the `agent` folder).
2. Copy zip to the employee PC, unzip.
3. Run `Install-DeskTrack-Agent.bat` **or** copy `config.example.ini` → `config.ini`, edit login, then `pip install -r requirements.txt` and `Start DeskTrack Agent.bat`.

Employees do **not** need the full codebase, Docker, or VPS access.

## What the agent does

- Uses the PC webcam
- Blocks Windows sleep while running
- Queues frames if Wi‑Fi drops, uploads later
- Server checks identity against enrolled face
