# DeskTrack Windows Agent

Background webcam tracker for **one employee**. Works with sleep-block and offline queue. Presence counts only when **your enrolled face** is at the desk.

## 1. Enroll your face (website)

1. Open https://desktrack.hairscalptradingco.com (or your server URL)
2. Log in as the employee
3. On **My desk**, use **Enroll face** — look at the camera until it says ready (about 5 samples)
4. Only after enrollment will “someone else at your desk” **not** count as you

## 2. Install agent on the PC

```bat
cd agent
copy config.example.ini config.ini
notepad config.ini
python -m pip install -r requirements.txt
```

Edit `config.ini`:

```ini
[server]
url = https://desktrack.hairscalptradingco.com

[auth]
username = your_username
password = your_password
```

## 3. Run

Double-click `Start DeskTrack Agent.bat`  
or:

```bat
python desktrack_agent.py
```

Keep the window open while working. The agent:

- Opens the webcam
- Clocks you in (if `auto_clock_in = true`)
- Blocks Windows sleep while running
- Sends frames every ~2s
- If Wi‑Fi drops, queues frames and uploads later

## 4. Stop

Press `Ctrl+C` in the agent window (sleep is allowed again).

## Notes

- PC **fully shut down** still cannot track (nothing is running).
- Use camera index `1` in config if the wrong webcam opens.
- Face models are stored on the **server** under `face_models/`.
