import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, todayIST } from "../api";
import { Badge } from "../components/Badge";

export default function Reports() {
  const [day, setDay] = useState(todayIST());
  const [data, setData] = useState(null);
  const [selectedEmployeeApps, setSelectedEmployeeApps] = useState(null);

  // Weekly WhatsApp report modal state
  const [showWeeklyModal, setShowWeeklyModal] = useState(false);
  const [weeklyLoading, setWeeklyLoading] = useState(false);
  const [weeklyPreview, setWeeklyPreview] = useState("");
  const [weeklySendStatus, setWeeklySendStatus] = useState(null);
  const [isSending, setIsSending] = useState(false);

  const openWeeklyModal = async () => {
    setShowWeeklyModal(true);
    setWeeklyLoading(true);
    setWeeklySendStatus(null);
    const { ok, data } = await api("/api/hr/weekly-report/preview");
    if (ok && data?.message) {
      setWeeklyPreview(data.message);
    } else {
      setWeeklyPreview(data?.error || "Could not generate preview.");
    }
    setWeeklyLoading(false);
  };

  const sendWeeklyNow = async () => {
    setIsSending(true);
    setWeeklySendStatus(null);
    const { ok, data } = await api("/api/hr/weekly-report/send", { method: "POST" });
    if (ok) {
      setWeeklySendStatus({
        type: "success",
        text: data?.message || "Report dispatch initiated successfully!",
      });
    } else {
      setWeeklySendStatus({
        type: "error",
        text: data?.error || "Failed to trigger report send.",
      });
    }
    setIsSending(false);
  };

  const refresh = useCallback(async () => {
    const { ok, data: next } = await api(`/api/report?day=${encodeURIComponent(day)}`);
    if (ok) setData(next);
  }, [day]);

  useEffect(() => {
    refresh();
    const t = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!selectedEmployeeApps) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape") setSelectedEmployeeApps(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedEmployeeApps]);

  const csvDay = data?.day || day;

  return (
    <>
      <header className="page">
        <div>
          <h1>Daily report</h1>
          <p className="muted">
            One calendar day at a time (IST). Pick a previous day to review it — it is never mixed with today.
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn"
            style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
            onClick={openWeeklyModal}
            title="Preview or manually trigger the weekly WhatsApp report"
          >
            📱 Weekly Report
          </button>
          <label className="day-pick">
            Day{" "}
            <input type="date" value={day} max={todayIST()} onChange={(e) => setDay(e.target.value)} />
          </label>
          <a className="btn" href={`/hr/export.csv?day=${encodeURIComponent(csvDay)}`}>
            Download CSV
          </a>
        </div>
      </header>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Dept</th>
              <th>{data?.is_today ? "Now" : "Last that day"}</th>
              <th>Active</th>
              <th style={{ minWidth: "200px" }}>Tracked apps</th>
              <th title="Share of active time in work apps vs other apps">Work apps %</th>
              <th title="Face visible while clocked in">Seated</th>
              <th title="Unapproved away time exceeding the 1h daily break allowance (after 15m face buffer).">Idle</th>
              <th title="Personal break time used out of 1h daily allowance">Break used</th>
              <th title="Seated ÷ 9h workday">Presence %</th>
            </tr>
          </thead>
          <tbody>
            {(data?.team || []).map((p) => (
              <tr key={p.id}>
                <td>
                  <Link to={`/hr/employee/${p.id}?day=${encodeURIComponent(csvDay)}`}>{p.name}</Link>
                </td>
                <td>{p.department}</td>
                <td>
                  <Badge status={p.status} />
                </td>
                <td>{p.today.active}</td>
                <td>
                  {(p.today.apps || []).length ? (
                    <div className="report-apps-tags">
                      {p.today.apps.slice(0, 3).map((a) => (
                        <button
                          key={a.app}
                          type="button"
                          className="app-tag"
                          title={`${a.app}: ${a.label} — click to view all apps`}
                          onClick={() =>
                            setSelectedEmployeeApps({
                              employeeName: p.name,
                              apps: p.today.apps,
                              day: csvDay,
                              totalActive: p.today.active,
                            })
                          }
                        >
                          {a.app} <small>({a.label})</small>
                        </button>
                      ))}
                      {p.today.apps.length > 3 ? (
                        <button
                          type="button"
                          className="app-tag-more"
                          title="Click to view all tracked apps"
                          onClick={() =>
                            setSelectedEmployeeApps({
                              employeeName: p.name,
                              apps: p.today.apps,
                              day: csvDay,
                              totalActive: p.today.active,
                            })
                          }
                        >
                          +{p.today.apps.length - 3} more
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>{p.today.useful_pct}%</td>
                <td>{p.today.seated}</td>
                <td>{p.today.idle}</td>
                <td>{p.today.break_used || "0m"}</td>
                <td>{p.today.presence_pct ?? 0}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedEmployeeApps && (
        <div
          className="modal-backdrop"
          onClick={() => setSelectedEmployeeApps(null)}
          role="presentation"
        >
          <div
            className="card modal-card apps-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="apps-modal-title"
          >
            <div className="modal-head">
              <div>
                <h2 id="apps-modal-title" style={{ margin: 0, fontSize: "1.15rem" }}>
                  Tracked Applications
                </h2>
                <div className="muted" style={{ fontSize: "0.82rem", marginTop: "2px" }}>
                  <strong>{selectedEmployeeApps.employeeName}</strong> · {selectedEmployeeApps.day}
                </div>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setSelectedEmployeeApps(null)}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            <div className="apps-modal-summary">
              <span>Total Active Time:</span>
              <strong>{selectedEmployeeApps.totalActive}</strong>
            </div>

            <div className="apps-modal-scroll">
              <ul className="apps">
                {selectedEmployeeApps.apps.map((a) => {
                  const maxSec = Math.max(
                    ...selectedEmployeeApps.apps.map((x) => x.seconds),
                    1
                  );
                  const pct = Math.round((a.seconds / maxSec) * 100);
                  return (
                    <li key={a.app}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <span
                          style={{
                            fontWeight: 500,
                            fontSize: "0.88rem",
                            display: "block",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={a.app}
                        >
                          {a.app}
                        </span>
                        <span className="bar" style={{ marginTop: "4px" }}>
                          <i style={{ width: `${pct}%` }} />
                        </span>
                      </div>
                      <span
                        style={{
                          fontWeight: 600,
                          fontSize: "0.85rem",
                          color: "var(--muted)",
                          marginLeft: "1rem",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {a.label}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="modal-actions" style={{ marginTop: "1rem", display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="button secondary"
                onClick={() => setSelectedEmployeeApps(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      {showWeeklyModal && (
        <div
          className="modal-backdrop"
          onClick={() => setShowWeeklyModal(false)}
          role="presentation"
        >
          <div
            className="card modal-card"
            style={{ maxWidth: "560px", width: "95%" }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="modal-head">
              <div>
                <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Weekly WhatsApp Report</h2>
                <div className="muted" style={{ fontSize: "0.82rem", marginTop: "4px" }}>
                  ⏰ <strong>Auto-Schedule:</strong> Every Sunday at 09:00 AM IST
                </div>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowWeeklyModal(false)}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            <div
              style={{
                background: "var(--surface-hover, rgba(255, 255, 255, 0.04))",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "10px 14px",
                margin: "12px 0",
                fontSize: "0.83rem",
                lineHeight: "1.4",
              }}
            >
              <span>
                Dispatched automatically to all HR & Lead WhatsApp numbers configured in{" "}
                <code>LEAD_WHATSAPP_PHONE</code> on every Sunday.
              </span>
            </div>

            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <span style={{ fontSize: "0.84rem", fontWeight: 600 }}>WhatsApp Message Preview:</span>
                <button
                  type="button"
                  className="button secondary"
                  style={{ fontSize: "0.75rem", padding: "2px 8px" }}
                  onClick={() => {
                    navigator.clipboard.writeText(weeklyPreview);
                    alert("Report copied to clipboard!");
                  }}
                  disabled={!weeklyPreview || weeklyLoading}
                >
                  Copy Text
                </button>
              </div>

              {weeklyLoading ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "var(--muted)" }}>
                  Aggregating 7-day attendance & app metrics…
                </div>
              ) : (
                <pre
                  style={{
                    background: "rgba(0, 0, 0, 0.35)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    padding: "12px",
                    fontSize: "0.82rem",
                    lineHeight: "1.45",
                    whiteSpace: "pre-wrap",
                    maxHeight: "320px",
                    overflowY: "auto",
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  {weeklyPreview}
                </pre>
              )}
            </div>

            {weeklySendStatus && (
              <div
                style={{
                  marginTop: "12px",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  fontSize: "0.83rem",
                  background:
                    weeklySendStatus.type === "success"
                      ? "rgba(34, 197, 94, 0.15)"
                      : "rgba(239, 68, 68, 0.15)",
                  color:
                    weeklySendStatus.type === "success"
                      ? "var(--success, #22c55e)"
                      : "var(--danger, #ef4444)",
                  border: `1px solid ${
                    weeklySendStatus.type === "success"
                      ? "rgba(34, 197, 94, 0.3)"
                      : "rgba(239, 68, 68, 0.3)"
                  }`,
                }}
              >
                {weeklySendStatus.text}
              </div>
            )}

            <div
              className="modal-actions"
              style={{
                marginTop: "1rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <button
                type="button"
                className="btn btn-primary"
                style={{ fontSize: "0.85rem" }}
                onClick={sendWeeklyNow}
                disabled={isSending || weeklyLoading}
              >
                {isSending ? "Sending…" : "📤 Send to WhatsApp Now"}
              </button>
              <button
                type="button"
                className="button secondary"
                onClick={() => setShowWeeklyModal(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
