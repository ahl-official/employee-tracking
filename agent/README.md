# DeskTrack Windows Agent (apps only)

Split mode:
- **Chrome / My desk** — webcam, face identity, presence (smooth live view)
- **This agent** — reports which desktop app is focused (Cursor, Slack, etc.)

No camera in the agent. No frames uploaded. Heartbeats on the server are cleaned up after 14 days.

## Install once

1. Python 3 with PATH  
2. Run `Install-DeskTrack-Agent.bat`  
3. Enroll face on the website, Clock in, keep My desk open  
4. Agent starts hidden and on Windows login  

You do not run the installer daily.
