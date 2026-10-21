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


