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
