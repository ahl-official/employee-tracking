# DeskTrack Windows Agent

Background webcam + desktop-app tracker. Presence counts only when **your enrolled face** is at the desk.

## Employee setup (once)

1. Install [Python 3](https://www.python.org/downloads/) — tick **Add to PATH**.
2. Run `Install-DeskTrack-Agent.bat` (share this one file from HR).
3. Enter username / password (server URL default is fine).
4. Installer downloads the agent, starts it **hidden** (no terminal), and adds a **Windows Startup** shortcut.

You do **not** run the installer every day. After Windows login, tracking starts by itself.

Then once on the website: log in → **Enroll face** → done. The agent auto clock-ins and reports apps + presence.

## Why seated / active looked wrong

Seated = time your face is present. Active = seated and moving the mouse/keyboard. Idle = seated but inactive. **Active + Idle = Seated.**

## Apps today

The website alone can only see the browser name. With the agent running, **Apps today** lists real desktop apps (Chrome, VS Code, Slack, etc.).

## Face enrollment

Enroll once on **My desk**. After that the big enroll box is replaced by a short “Face enrolled” message, and your photo appears in the left sidebar.
