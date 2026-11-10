# Project Decisions & Architecture Log

## Decision 1: Idle vs. Seated Time Bounded to Active Sessions
- **Date:** 2026-10-19
- **Problem:** Idle time was previously inflated to an arbitrary 9-hour workday even for employees who only clocked in for an hour.
- **Decision:** All metrics (`seated`, `idle`, `break`, `presence %`) are strictly bounded between Clock In and Clock Out (`total_clocked = elapsed`).
- **Files Affected:** `analytics.py`, `models.py`.

---

## Decision 2: Self-Contained 1-Click Workstation Auto-Connector
- **Date:** 2026-10-19
- **Problem:** The `.bat` file previously relied on `more +7` temporary file extraction and HTTP downloads from the server, causing device errors and 404s.
- **Decision:** Direct payload embedding into `.bat` using `findstr` marker extraction. The agent code is packaged directly inside the file, requiring 0 external HTTP downloads to start tracking.
- **Files Affected:** `main.py`, `agent/desktrack_agent.py`.

---

## Decision 3: Break Calculation Tied to Actual Away / Idle Time
- **Date:** 2026-10-19
- **Problem:** When employees took a 15-minute break and their screen locked/slept, gaps > 7 minutes only credited 3 seconds to `away`. Consequently, `Break left` remained stuck at ~24m instead of deducting the 15-minute break.
- **Decision:** Break deduction is tied directly to total time away from desk (`max(away, idle_s)`), and gap intervals are properly credited to away time when no face was detected.
- **Files Affected:** `analytics.py`.

---

## Decision 4: Away-on-Task / Room Movement Approval Workflow
- **Date:** 2026-10-19
- **Problem:** Employees leaving their desk for legitimate work (e.g. conference room meetings, client calls in phone booths, hardware/lab tasks) were being penalized as "Idle" or having their personal 30-minute break burned.
- **Decision:**
  1. Add a `TaskRequest` model in `models.py` tracking: `user_id`, `reason`, `location`, `expected_minutes`, `status` (`pending`, `approved`, `rejected`, `completed`), `started_at`, `ended_at`, `approver_id`.
  2. Provide a quick **"Step Away on Task"** button in **My desk** for employees.
  3. Real-time Lead/HR approval with a dedicated badge and quick **[Approve]** / **[Reject]** actions.
  4. Time spent on approved tasks is credited to **Productive Work** (`task_work_seconds`), does **NOT** count as Idle, and does **NOT** consume personal break allowance.
- **Files Affected:** `models.py`, `main.py`, `analytics.py`, `frontend/src/pages/Desk.jsx`, `frontend/src/pages/Live.jsx`.

---

## Decision 5: Self-Healing Task Tables & Universal Role Authorization for Desk Actions
- **Date:** 2026-10-19
- **Problem:** When employees or leads tested "Step Away on Official Task", the modal displayed `"Failed to submit request."`
  1. `Base.metadata.create_all()` was previously only invoked on server startup, meaning running production servers without an explicit restart or migration lacked the `task_requests` table in SQLite.
  2. `require(request, db, *roles)` rejected any user if `roles` was not provided (`user.role not in ()`), and strictly restricted desk task submission to `role == "employee"`, blocking testing by HR/admin accounts.
  3. API errors returning plain text or non-JSON (like 500 or 404) resulted in empty JSON objects in frontend `api()`, falling back to a vague generic error string.
- **Decision:**
  1. Auto-create missing database tables dynamically on endpoint access (`Base.metadata.create_all(bind=db.get_bind())`) so existing production databases self-heal automatically.
  2. Fix `require()` to allow any authenticated session when no specific role filter is given, and allow both employees and admins/leads to submit task requests from their desk.
  3. Update `api()` and `Desk.jsx` to parse and render explicit server errors (`data.error`, `data.detail`, or HTTP status) so error reasons are immediately transparent.
- **Files Affected:** `main.py`, `frontend/src/api.js`, `frontend/src/pages/Desk.jsx`, `DECISIONS.md`.

---

## Decision 6: WhatsApp Movement & Task Approval Integration via WAHA
- **Date:** 2026-10-21
- **Problem:** Leads and managers may not always be actively viewing the DeskTrack dashboard when an employee steps away for a meeting, client call, or lab task. They need real-time mobile notifications via WhatsApp with one-tap approval.
- **Decision:**
  1. **Integration Engine:** Use **WAHA (WhatsApp HTTP API)**, a self-hosted lightweight REST API running as a companion Docker container on the VPS alongside DeskTrack.
  2. **Outbound Dispatch:** When an employee submits a `TaskRequest`, DeskTrack invokes `WAHA /api/sendText` delivering a formatted notification to the assigned Lead/HR phone number.
  3. **1-Tap Approval Link:** Include HMAC-signed quick links (`/api/tasks/{id}/quick-approve?token=...` and `quick-reject`) allowing Leads to instantly approve/reject directly from WhatsApp without needing to log into the dashboard first.
  4. **Optional Inbound Webhook:** Support WAHA incoming message webhook (`/api/webhooks/waha`) so Leads can also simply reply with `APPROVE <id>` or `REJECT <id>`.
  6. **Static Code Verification:** Verified with `pyflakes` to ensure all imports (including `timezone`, `re`, `waha`) and dependencies are strictly defined across all application modules.
- **Files Affected:** `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `config.py`, `models.py`, `main.py`, `waha.py`, `DECISIONS.md`.

---

## Decision 7: Complete Task Idle Exemption, Single Daily Clock-Out Enforce, and WhatsApp Auto-Match
- **Date:** 2026-10-22
- **Problem:**
  1. When an employee was away on an approved task, raw away seconds were not deducted from `away`, causing `max(away, idle_s)` to consume their 30-minute break allowance. Also, tasks only started from `started_at` (when lead approved), penalizing the elapsed time since `requested_at`.
  2. After clocking out for the day, the UI reverted to "Clock in", allowing accidental or unauthorized re-clocking in.
  3. WAHA webhook required exact syntax (`APPROVE <id>`), failing on natural replies like `approve`, `approved`, `yes`, or `ok`. Also, session `ahlaiteam` in WAHA did not have DeskTrack's webhook registered.
- **Decision:**
  1. **Idle & Break Immunity:** In `analytics.py`, official task time starts from `tr.requested_at` (the moment the employee stepped away). Both `idle_s` and `away` have `task_seconds` subtracted, and `presence` % credits official task time so break allowance is never consumed.
  2. **Single Daily Shift Enforce:** Once an employee clocks out for the day, the UI displays a disabled `✅ Shift Completed` button. The backend rejects any re-clock-in on the same calendar day with HTTP 400.
  3. **Natural WhatsApp Replies:** In `main.py`, the webhook supports natural single-word replies (`approve`, `approved`, `ok`, `yes`, `reject`, `no`). When no task ID is specified, it automatically matches and resolves the most recent pending task.
---

## Decision 8: WhatsApp Single Message with Native Approve/Decline Buttons & Zero Links
- **Date:** 2026-10-22
- **Problem:**
  1. Sending HTTP links in WhatsApp messages caused WhatsApp server link-preview crawlers to pre-fetch the URL with GET requests, prematurely approving tasks before the Lead saw them.
  2. The Lead received multi-part messages and unwanted follow-up confirmation spam.
  3. Meta deprecated interactive MD buttons (`/api/sendButtons`) on web protocols in 2022 (returning HTTP 501 on WAHA GOWS engine).
- **Decision:**
  1. **Native WhatsApp Interactive Buttons via Polls:** Use WAHA's `/api/sendPoll` (`WhatsappSessionGoWSCore.sendPoll`) to render native clickable action buttons (`[ ✅ Approve ]` and `[ ❌ Decline ]`) directly within a single WhatsApp message.
  2. **Zero Links:** Completely eliminate all HTTP URLs from the WhatsApp message, eliminating link preview crawler bugs.
  3. **No Follow-up Spam:** `notify_task_resolution_async` is silenced to guarantee exactly one crisp message in the chat.
  4. **Immediate Webhook Resolution:** WAHA's `poll.vote` event delivers the button click directly to `/api/webhooks/waha`, instantly updating the task to `approved` or `rejected` in real time.
- **Files Affected:** `waha.py`, `main.py`, `DECISIONS.md`.

---

## Decision 9: Rigorous Time Partitioning & Mutual Exclusivity for Seated, Active Apps, Tasks, and Idle
- **Date:** 2026-10-22
- **Problem:**
  1. **Seated & Task Double Counting:** When testing tasks while sitting in front of the webcam, the camera credited seated time, and the task simultaneously credited task time. `task_seconds` was deducted from `idle_s`, which erased the employee's morning idle time (dropping idle from 1h 12m to 28m 47s), falsely refunded personal break allowance (`break_left` jumped from 0s to 47s), and inflated `presence %` from 78% to 92%.
  2. **Phantom Active (Apps) Accumulation:** When an employee walked away or left the screen idle without Win+L (`present == 0`), the background desktop agent's foreground app was still added to `Active (apps)` across long gap intervals. This caused `Active (apps)` (6h 08m) to exceed total clocked shift time (~5h 50m).
- **Decision:**
  1. **Strict Partition of Clocked Shift:** At any second during a clocked-in shift, time is partitioned into 3 mutually exclusive components:
     $$T_{\text{clocked}} = T_{\text{seated}} + T_{\text{task\_away}} + T_{\text{idle}}$$
  2. **Seated Time Priority:** Any time the employee's face is detected in front of the webcam is credited to $T_{\text{seated}}$.
  3. **Away-on-Task Exemption:** Official tasks ONLY credit time when the employee was actually away from their desk camera ($T_{\text{task\_away}} = \max(0, T_{\text{task\_total}} - T_{\text{task\_seated}})$). Testing while seated does not double-count or erase prior morning idle.
  4. **Active Apps Bounded:** `add_app_bucket()` is strictly suppressed when `row.present == 0` or locked (empty desk). Total active app time is capped at $T_{\text{clocked}}$.
  5. **Auto-Complete on Clock Out:** When an employee clocks out, any unended approved task is automatically finalized at clock-out time.
- **Files Affected:** `analytics.py`, `main.py`, `DECISIONS.md`.

---

## Decision 10: 2-Sample Face Enrollment, Auto-Dismissing Banners & 50+ Concurrent Employee Architecture
- **Date:** 2026-10-22
- **Problem:**
  1. Face enrollment previously demanded 5 separate camera samples (`MIN_ENROLL_SAMPLES = 5`), causing employees to click repeatedly and experience multiple enrollment prompts.
  2. The green camera status banner and face enrollment banner permanently occupied vertical space at the top of the desk screen.
  3. Scaling to 50+ concurrent employees required evaluating SQLite concurrency (`database is locked`), uvicorn CPU load from YuNet face inference, and bandwidth.
- **Decision:**
  1. **2-Sample Quick Face Enrollment:** Lowered `MIN_ENROLL_SAMPLES = 2` in `face_id.py` and `Desk.jsx`. Enrollment now completes in 2 snapshots.
  2. **Auto-Dismissing Desk Banners:** Banners auto-fade after 6 seconds with manual `×` dismiss buttons. A persistent `Re-enroll face` button is placed neatly in the Live monitoring header.
  3. **SQLite WAL & Busy Timeout:** Configured `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=10000;` on connection in `models.py`. Concurrent writes no longer block reads or trigger lock errors.
  4. **Optimized Client Polling:** Decoupled heavy background `/api/me` poll from 3s to 10s (since `/api/me/track` already streams metrics), reducing HTTP request volume by 60% across 50 employees.
- **Files Affected:** `face_id.py`, `models.py`, `frontend/src/pages/Desk.jsx`, `frontend/src/index.css`, `frontend/dist/`, `DECISIONS.md`.

---

## Decision 11: Eliminate Flash of Uninitialized Clocked-Out / Face Enrollment State
- **Date:** 2026-10-31
- **Problem:**
  1. When an active clocked-in employee navigated between "Account" and "My desk", or refreshed the page, the screen briefly flashed into the "Clocked Out" view for 400ms.
  2. The button flashed "Clock in", the banner showed "Clocked out...", and the large "Face enrollment required" card appeared before vanishing as soon as the API response arrived.
- **Decision:**
  1. **Session Storage Persistence:** Cache `desktrack_me` and `desktrack_face` in `sessionStorage` so the page renders the active clocked-in state and metrics immediately on mount without awaiting HTTP roundtrips.
  2. **Face Guard:** Added `loaded` flag so the "Face enrollment required" prompt ONLY renders when the server explicitly confirms `face.loaded && !face.enrolled`.
  3. **Instant Camera Startup:** If `me.clocked_in` is already true from cache, `startCamera` initiates immediately on mount instead of delaying until after network polling completes.
- **Files Affected:** `frontend/src/pages/Desk.jsx`, `DECISIONS.md`.

---

## Decision 12: Bundle Agent Directory into Docker Container to Fix 1-Click Workstation Installer
- **Date:** 2026-11-04
- **Problem:**
  1. When Saniya (or any employee) downloaded and ran the 1-click workstation connector `.bat` file, the installer failed with `"Failed to obtain tracker from server."`
  2. The server generates a self-contained `.bat` file with the agent script embedded as base64 (`$agentB64`). However, `Dockerfile` never copied the `agent/` folder into `/app` in the container.
  3. Consequently, `agent_path.is_file()` was `False`, `$agentB64` was empty, and the fallback URLs failed (the server endpoint returned 404 because `agent/` was missing, and the raw GitHub URL failed because the repo is private).
- **Decision:**
  1. Updated `Dockerfile` to explicitly copy `agent/`, `static/`, and `templates/` into the Docker image.
  2. Verified `main.py` embeds the full base64 agent payload directly inside the `.bat` file, making it 100% self-contained with zero external download requirements.
- **Files Affected:** `Dockerfile`, `DECISIONS.md`.

---

## Decision 13: Date-Based Historical Tracked Apps & Activity Inspection for HR
- **Date:** 2026-11-07
- **Problem:**
  1. HR could only view tracked apps for the current day ("today"). When viewing an employee's profile (`/hr/employee/:id`), there was no date picker to view past days.
  2. The Daily Report table (`/hr/reports`) did not display the actual apps used by employees for that day.
  3. Clicking an employee link from the Daily Report did not pass the selected date, resetting the view back to today.
  4. CSV export did not include the specific tracked apps and duration breakdown.
- **Decision:**
  1. **Date Picker on Employee Detail View:** Added date selector, "Today" quick button, and `?day=YYYY-MM-DD` query parameter sync in `Employee.jsx`. HR can inspect all tracked apps, time bars, metrics, and activity timeline for any past date.
  2. **Tracked Apps Column in Daily Report:** Added a "Tracked apps" column in `Reports.jsx` showing top apps used by each employee with time badges and "+N more" overflow.
  3. **Date Preservation:** Preserved `?day=${day}` when clicking an employee from the Daily Report table.
  4. **Historical Mode Camera Guard:** Replaced live webcam stream polling on historical dates with a clean informational notice, saving VPS CPU and bandwidth.
  5. **CSV Export Apps Column:** Added `tracked_apps` column to `/hr/export.csv` containing semicolon-separated apps and durations for that date.
- **Files Affected:** `frontend/src/pages/Employee.jsx`, `frontend/src/pages/Reports.jsx`, `frontend/src/index.css`, `main.py`, `DECISIONS.md`.

---

## Decision 14: Tracked Applications Interactive List Popup Modal in Daily Report
- **Date:** 2026-11-07
- **Problem:**
  1. In the Daily Report table (`/hr/reports`), when an employee has more than 3 tracked apps, an overflow badge (`+N more`) is displayed.
  2. Previously, the badge only showed a browser native title tooltip on hover, but users expected an interactive click popup modal to review the full detailed list of tracked apps and durations directly on the page without navigating away.
- **Decision:**
  1. Converted `+N more` and app tags into interactive buttons with cursor pointer and hover effects.
  2. Clicking `+N more` (or any app tag) launches an accessible modal dialog popup (`apps-modal`).
  3. The popup displays:
     - Employee name & the chosen report date
     - Total active working time for that day
     - Complete list of tracked apps with proportional duration progress bars and formatted time badges
     - Scrollable list with custom scrollbar for long app lists
     - Dismissal via the '✕' button, clicking the backdrop, pressing `Escape`, or clicking 'Close'.
- **Files Affected:** `frontend/src/pages/Reports.jsx`, `frontend/src/index.css`, `DECISIONS.md`.

---

## Decision 15: Multiple HR Phone Numbers for WhatsApp Step-Away Approvals, 15-Minute Presence Buffer, 1-Hour Break Allowance & Idle Time Partitioning
- **Date:** 2026-11-09
- **Problem:**
  1. WAHA step-away/movement approval was restricted to a single phone number (`LEAD_WHATSAPP_PHONE`). When entering multiple HR numbers separated by commas, the parser failed to normalize them.
  2. The face absence buffer was previously 7 minutes (`IDENTITY_HOLD_SECONDS = 420`), causing employees stepping away briefly for water/restroom to flip into Break/Away too quickly.
  3. The daily break allowance was 30 minutes (`BREAK_ALLOWANCE_SECONDS = 1800`), whereas company policy requires a 1-hour (60 minute) break budget.
  4. Unapproved absence was previously categorized directly into Idle regardless of available break balance. The expected policy is:
     - Absences up to 15 minutes are buffered as present (not counted against idle or break).
     - Absences exceeding 15 minutes mark the employee as Away.
     - The away time is charged against their 1-hour daily Break Allowance (`break_used` increases, `break_left` decreases).
     - Only when the 1-hour break allowance is completely exhausted does additional unapproved away time get accumulated into Idle time.
- **Decision:**
  1. **Multiple HR Numbers Dispatch:** Added `get_lead_phone_numbers()` in `waha.py` to parse comma/space/semicolon-separated numbers from `LEAD_WHATSAPP_PHONE` and `HR_WHATSAPP_PHONES`. Dispatches interactive WhatsApp approval polls (`[ ✅ Approve ]` and `[ ❌ Decline ]`) to all configured HR numbers simultaneously. Webhook commands and poll votes authenticate any authorized HR sender.
  2. **15-Minute Presence Buffer:** Increased `IDENTITY_HOLD_SECONDS` and `PRESENCE_GAP_GRACE_SECONDS` from 420 to 900 seconds (15 minutes). If the face is not visible for up to 15 minutes, the employee remains counted as seated/present.
  3. **1-Hour Break Allowance:** Increased `BREAK_ALLOWANCE_SECONDS` from 1800 to 3600 seconds (60 minutes).
  4. **Strict Break vs. Idle Partitioning:** Updated `analytics.py` so that unapproved away time first consumes the 1-hour break allowance (`break_used = min(away, 3600)`). Any excess away time beyond the 1-hour allowance is placed into `idle_s`.
  5. **UI Consistency:** Updated default placeholder in `Desk.jsx` to `1h` break left and refined tooltips across `Reports.jsx`, `Employee.jsx`, and `Desk.jsx`.
- **Files Affected:** `config.py`, `waha.py`, `main.py`, `detector.py`, `face_id.py`, `analytics.py`, `frontend/src/pages/Desk.jsx`, `frontend/src/pages/Reports.jsx`, `frontend/src/pages/Employee.jsx`, `DECISIONS.md`.

---

## Decision 16: Automatic Weekly WhatsApp Report for HR with Screen Time and Top Applications
- **Date:** 2026-11-09
- **Problem:**
  1. HR and leadership needed an automated summary of each employee's screen time, seated/idle breakdown, and main applications used, sent automatically to HR every Sunday.
  2. Previously, reports were only visible inside the web dashboard on a day-by-day basis.
- **Decision:**
  1. **Weekly Metric Aggregation:** Created `weekly_report.py` with `build_weekly_report()`, which iterates over the past 7 calendar days for all active employees, aggregating screen time, seated time, idle/away time, active application time, presence percentage, and top 3 apps used with their exact durations.
  2. **WhatsApp Formatting:** Styled message with clean Markdown and an ASCII progress bar (`████░░░░░░ 39%`).
  3. **Automated Scheduler:** Built a background scheduler thread that runs during the application lifespan and checks every minute. Automatically dispatches the weekly summary to all HR phone numbers in `LEAD_WHATSAPP_PHONE` every Sunday at 09:00 AM IST (configurable via `WEEKLY_REPORT_DAY`, `WEEKLY_REPORT_HOUR`, `WEEKLY_REPORT_MINUTE`).
  4. **HR Dashboard UI & Manual Trigger:** Added endpoints `GET /api/hr/weekly-report/preview` and `POST /api/hr/weekly-report/send`. Added a `📱 Weekly Report` interactive modal to `Reports.jsx` allowing HR to preview the report in real-time, copy the text, or trigger a manual dispatch.
- **Files Affected:** `weekly_report.py`, `config.py`, `main.py`, `.env.example`, `.gitignore`, `frontend/src/pages/Reports.jsx`, `HANDOVER.md`, `DECISIONS.md`.

---

## Decision 17: Guaranteed Workstation Auto-Connector Startup Folder Persistence
- **Date:** 2026-11-09
- **Problem:**
  1. Employees who set up the workstation `.bat` on Saturday saw tracking stop on Monday after rebooting because the Windows Registry `HKCU\...\Run` command used bare `pythonw.exe` without an absolute path, which failed on Windows startup.
  2. When employees only had their browser open, Chrome's security sandbox prevented tracking external apps, resulting in only `DeskTrack` appearing in the HR report.
- **Decision:**
  1. **Dual Startup Persistence:** In the `.bat` installer, resolved the full absolute path to `pythonw.exe` (or `python.exe`) and installed a silent VBScript launcher into the **Windows Startup folder** (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DeskTrackAgent.vbs`) alongside the registry key, guaranteeing the agent starts invisibly every time Windows boots.
  2. **Employee Self-Service Download:** Kept connector `.bat` download exclusive to the employee portal.
- **Files Affected:** `main.py`, `agent/desktrack_agent.py`, `DECISIONS.md`.

---

## Decision 18: Configurable Work Week Baseline (6-Day Working Week Default)
- **Date:** 2026-11-09
- **Problem:**
  1. The weekly report previously hardcoded a 5-day work week baseline (`{days_worked}/5`).
  2. The organization follows a 6-day working week (Monday through Saturday).
- **Decision:**
  1. Added `WORK_DAYS_PER_WEEK = _int("WORK_DAYS_PER_WEEK", 6)` in `config.py` with environment variable override support.
  2. Updated `weekly_report.py` to use `f"📅 Days active : {days_worked}/{config.WORK_DAYS_PER_WEEK}"`.
  3. Updated `.env.example` to document `WORK_DAYS_PER_WEEK=6`.
- **Files Affected:** `config.py`, `weekly_report.py`, `.env.example`, `DECISIONS.md`.

---

## Decision 19: Case-Insensitive Agent Auth, Dedicated dt_ Tokens & Workstation PID Tracking
- **Date:** 2026-11-09
- **Problem:**
  1. Employees with mixed/capitalized usernames (e.g. `Priyanka`, `Hisham`) failed agent login with `401 Unauthorized` because SQLite's default case-sensitive `filter_by(username=username)` did not match lowercased input.
  2. If an employee's `agent_password` was initialized with the PBKDF2 website password hash (`pbkdf2:sha256:...`), the `.bat` generator failed to replace it because it only checked `startswith("$")`. The embedded hash contained `$` characters, which PowerShell evaluated as empty variables in double quotes, corrupting the token.
  3. When an agent was already running in a retry loop with bad credentials, re-running the `.bat` did not terminate the old process because PowerShell 5.1's `Get-Process` lacks a `.CommandLine` property.
- **Decision:**
  1. **Case-Insensitive Auth:** Used SQLAlchemy `func.lower(User.username) == username.lower()` in both `/api/agent/login` and `/api/login`.
  2. **Dedicated Token Enforcement:** Updated `_build_connector_bat` to enforce `if not target_user.agent_password or not target_user.agent_password.startswith("dt_"):`, guaranteeing clean urlsafe alphanumeric tokens (`dt_<token>`).
  3. **Verbatim PowerShell Strings:** Enclosed `$ServerUrl`, `$Username`, and `$AgentPassword` in single quotes (`'...'`) in the generated connector script.
  4. **Workstation PID File Tracking:** Added `desktrack_agent.pid` management in `desktrack_agent.py` and the `.bat` script, reliably terminating old background instances before launching updated ones.
- **Files Affected:** `main.py`, `agent/desktrack_agent.py`, `DECISIONS.md`.

---

## Decision 20: SQLite Concurrency Hardening (30s Driver Timeout & Idempotent Schema Creation)
- **Date:** 2026-11-09
- **Problem:**
  1. Multiple employee machines sending concurrent `/api/me/track` heartbeats occasionally triggered `sqlite3.OperationalError: database is locked`.
  2. Python's `sqlite3` driver defaulted to a short 5-second busy timeout.
  3. Multiple task endpoints repeatedly called `Base.metadata.create_all()` on live HTTP requests, executing heavy DDL schema queries that acquired exclusive SQLite table locks.
- **Decision:**
  1. Configured `connect_args={"check_same_thread": False, "timeout": 30}` in `models.py` and set `PRAGMA busy_timeout=30000;`.
  2. Replaced repetitive `Base.metadata.create_all` calls in `main.py` with an idempotent `ensure_tables()` function that runs at most once per process lifetime, eliminating DDL lock contention.
- **Files Affected:** `models.py`, `main.py`, `DECISIONS.md`.

---

## Decision 21: System-Wide Performance Optimizations (Indexes, In-Memory Caching & AI Pass Deduping)
- **Date:** 2026-11-09
- **Problem:**
  1. **Missing Database Indexes:** `heartbeats` and `work_sessions` had no indexes. As tens of thousands of rows accumulated, every single heartbeat query in `analytics.summarize` triggered a full sequential table scan on SQLite, locking the database and causing multi-second delays.
  2. **Memory Overload in `activity_days`:** `db.query(Heartbeat.created_at).all()` loaded every single heartbeat timestamp across company history into Python memory on every 5-second `/api/report` poll, pushing memory near the 1GB Docker limit.
  3. **Redundant Recalculations:** `api_me_track` recalculated the entire day's summary for each employee on every 2.5s video frame even when the employee was normally seated.
  4. **Dual Face Detection Inference & Disk I/O:** `detect_faces` ran twice on each frame (in `detector.annotate` and `face_id.verify`), and face embeddings were re-read and decompressed from disk on every frame.
  5. **Uncached Frontend Bundles:** Web assets had no `Cache-Control` headers, forcing full bundle re-downloads.
- **Decision:**
  1. **SQLite Database Indexes:** Added indexes on `heartbeats(user_id, created_at)`, `heartbeats(created_at)`, and `work_sessions(user_id, clock_in)` with automatic `_ensure_indexes()` on startup.
  2. **Optimized Activity Days with 60s Cache:** Refactored `activity_days` to scan `work_sessions` (which has only 1-2 rows per user/day) over the last 90 days and cached the result for 60 seconds.
  3. **Summary Caching in Camera Pipeline:** Introduced an 8-second in-memory summary cache (`_USER_SUMMARY_CACHE`) in `main.py` for normal seated frames, only forcing recalculation on absent frames for alert evaluation.
  4. **In-Memory Embeddings & Single-Pass Detection:** Added `_EMBEDS_CACHE` in `face_id.py` and passed pre-detected face boxes from `detector.annotate` into `face_id.verify`, cutting YuNet inference by 50%.
  5. **Static Asset Caching:** Added `public, max-age=31536000, immutable` headers for Vite hashed static assets in `/assets/`.
- **Files Affected:** `models.py`, `database.py`, `analytics.py`, `face_id.py`, `main.py`, `DECISIONS.md`.

---

## Decision 22: Fix Connecting Freeze, Activity Days NameError & Instant Clock-Out State Transition
- **Date:** 2026-11-10
- **Problem:**
  1. **HTTP 500 Crash on `/api/me`:** In `analytics.py`, `cut = utc_now() - timedelta(...)` threw `NameError: name 'utc_now' is not defined` because `utc_now` was not imported. Because every `/api/me` call failed with HTTP 500, `Desk.jsx` never received user state.
  2. **Page Stuck on "Connecting...":** In `Desk.jsx`, `refresh()` had `if (!ok) return;` before `setInitialLoading(false)`. Any API error or 401 left `initialLoading` permanently `true`, locking the UI on "Connecting to desk..." and "Connecting...".
  3. **Clock-Out State Desynchronization:** Clocking out called `refresh()` without immediately applying the local clocked-out state. When `refresh()` failed, the screen did not update to `✅ Shift Completed` or save the summary.
- **Decision:**
  1. Defined `utc_now()` in `analytics.py` using `datetime.now(timezone.utc)`.
  2. Hardened `refresh()` in `Desk.jsx` to always clear `initialLoading` and redirect on 401.
  3. In `toggleClock()`, immediately updated React state and `sessionStorage` with `clocked_in: false, clocked_out_today: true` upon a successful clock-out response, showing the `✅ Shift Completed` button instantaneously.
- **Files Affected:** `analytics.py`, `frontend/src/pages/Desk.jsx`, `DECISIONS.md`.

---

## Decision 23: Bulletproof Python Detection, Direct Config Generation & Live Auth Verification in Connector
- **Date:** 2026-11-10
- **Problem:**
  1. **WindowsApps Python Alias Trap:** On modern Windows 10/11 machines without Python installed (standard non-developer workstations like CRM, Digital Marketing, Process Coordinators), Microsoft places a dummy 0-byte execution alias at `%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`. `Get-Command python` in the old launcher returned true, bypassing the auto-installer! When executed, it failed or opened the Windows Store silently in the background (`-WindowStyle Hidden`), leaving Python uninstalled.
  2. **Circular Dependency on Broken Python:** The launcher previously called `Start-Process $pyCmd "desktrack_agent.py" $ServerUrl $Username $AgentPassword` to write `config.ini`. When Python wasn't working, `config.ini` was never created.
  3. **Silent Failure & Premature Success Display:** The installer used `-WindowStyle Hidden` and printed `Connected Successfully!` even when Python was absent, requests failed to install, or the background process never started.
- **Decision:**
  1. **Filtered Python Detection:** Added `Find-Python` in `main.py`'s `_build_connector_bat` that tests `sys.version_info[0] == 3`, checks standard install directories (`LOCALAPPDATA\Programs\Python`, `C:\Python311`, etc.), and explicitly filters out any path containing `*WindowsApps*`. If missing, downloads and installs official Python 3.11 with `PrependPath=1`.
  2. **Direct Configuration Generation:** PowerShell directly writes UTF-8 `config.ini` before running Python, eliminating circular dependency on Python execution.
  3. **Live Authentication Verification:** Added a pre-launch verification check against `/api/agent/login` using Python and `requests`, providing immediate visual feedback: `[OK] Authenticated successfully with DeskTrack server!`.
  4. **Dual Persistence & Desktop Shortcut:** In addition to the Windows Registry `Run` entry and Startup folder `.vbs` runner, created a Desktop shortcut (`DeskTrack Agent.lnk`) for manual startup and easy verification.
- **Files Affected:** `main.py`, `DECISIONS.md`.
