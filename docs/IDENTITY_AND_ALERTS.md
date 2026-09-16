# How identity + HR alerts work

## How the agent knows it’s you (not someone else)

1. You enroll once on **My desk** (several face samples saved as a face model).
2. Every ~2s the agent sends a webcam frame to the server.
3. The server finds faces in the frame and compares them to **your** enrolled model (cosine similarity).
4. Results:
   - **matched / hold** → you are **PRESENT** (Active). Brief look-aways keep PRESENT for ~12s.
   - **no_face** (empty/black camera) → does **not** instantly mark Break; holds last good present.
   - **mismatch** → another face that is not you → **ABSENT** + HR ping: *“Someone else may be at … desk”*.

Apps come from the Windows foreground window (Chrome, Cursor, Slack…), not from the website.

## Why you saw Break / Idle while sitting there

- The browser tab and the agent both tried to use the camera. The agent often got **black frames** → `no_face` → counted as away → status **Break**.
- **Idle** used to mean “no mouse/keyboard for 60s”. It now means **laptop sleep** (long gaps in heartbeats). While you are present and the PC is awake → **Active**.

**Fix for employees:** install agent once, then prefer closing/pausing the website camera (agent tracks in background). Rebuild the VPS so server logic updates.

## How HR gets pings today

| Channel | What happens |
|--------|----------------|
| **HR → HR pings** page | Alerts stored in DB (away after 30m break used, and face mismatch). |
| **Live board** | Status shows break / away / inactive / present. |

If HR is **not** on the website, they currently will **not** get a phone/desktop notification unless you configure a webhook.

## Plan: alert HR when they are offline

1. **Slack / Teams / Discord webhook (recommended, already supported)**  
   On the VPS `.env` add:
   ```env
   HR_ALERT_WEBHOOK=https://hooks.slack.com/services/...
   ```
   DeskTrack POSTs `{ "text": "DeskTrack: …" }` on mismatch and long-away alerts.

2. **Email (next step)**  
   Set `HR_ALERT_EMAIL` + SMTP and send the same message (can be added when you pick a mail provider).

3. **Optional later**  
   SMS (Twilio), mobile push, or WhatsApp Business API for urgent mismatch only.

Until webhook/email is set, HR must open **HR pings** or the Live board.
