import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ago, api } from "../api";
import { Badge } from "../components/Badge";

function emptyFeedText(p) {
  if (!p.clocked_in) return "Clocked out — camera off";
  if (p.on_task || p.status === "task") {
    const reason = p.active_task?.reason || "Official Task";
    const loc = p.active_task?.location ? ` in ${p.active_task.location}` : "";
    return `📋 On Task: ${reason}${loc}`;
  }
  if (p.status === "inactive") return "Inactive — laptop sleep or tab paused";
  if (p.camera_blocked) return "Camera blocked on their PC";
  if (!p.agent_live) return "Waiting for camera";
  return "Waiting for camera";
}

export default function Live() {
  const [data, setData] = useState(null);
  const [feeds, setFeeds] = useState({});
  const [pendingTasks, setPendingTasks] = useState([]);
  const teamRef = useRef([]);

  const fetchPendingTasks = useCallback(async () => {
    const { ok, data: res } = await api("/api/tasks/pending");
    if (ok && res.pending) {
      setPendingTasks(res.pending);
    }
  }, []);

  const refresh = useCallback(async () => {
    const { ok, data: next } = await api("/api/team");
    if (ok) {
      teamRef.current = next.team || [];
      setData(next);
    }
    fetchPendingTasks();
  }, [fetchPendingTasks]);

  const approveTask = async (id) => {
    await api(`/api/tasks/${id}/approve`, { method: "POST" });
    fetchPendingTasks();
    refresh();
  };

  const rejectTask = async (id) => {
    await api(`/api/tasks/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: "Declined by lead" }),
    });
    fetchPendingTasks();
    refresh();
  };


  useEffect(() => {
    function refreshFeeds() {
      if (document.visibilityState !== "visible") return;
      teamRef.current.forEach((p) => {
        const url = `/api/hr/preview/${p.id}?` + Date.now();
        const probe = new Image();
        probe.onload = () => setFeeds((prev) => ({ ...prev, [p.id]: url }));
        probe.onerror = () =>
          setFeeds((prev) => {
            if (!prev[p.id]) return prev;
            const copy = { ...prev };
            delete copy[p.id];
            return copy;
          });
        probe.src = url;
      });
    }
    refresh();
    const t1 = setInterval(refresh, 3000);
    const t2 = setInterval(refreshFeeds, 600);
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, [refresh]);

  async function ack(id) {
    await api(`/api/alerts/${id}/seen`, { method: "POST", body: "{}" });
    refresh();
  }

  const c = data?.counts || {};
  const unseen = (data?.alerts || []).filter((a) => !a.seen);

  return (
    <>
      <header className="page">
        <div>
          <h1>Live board</h1>
          <p className="muted">
            Live camera overlay for each clocked-in employee, plus today’s seated time. Totals reset at midnight IST.
          </p>
        </div>
      </header>
      <p className="banner" hidden={!data || data.work_hours}>
        Outside work hours — away pings are paused.
      </p>
      <div className="kpis">
        <div className="kpi">
          <span>Present</span>
          <strong>{c.present || 0}</strong>
        </div>
        <div className="kpi">
          <span>Away</span>
          <strong>{c.away || 0}</strong>
        </div>
        <div className="kpi">
          <span>Idle (sleep)</span>
          <strong>{c.inactive || 0}</strong>
        </div>
        <div className="kpi">
          <span>Break</span>
          <strong>{c.break || 0}</strong>
        </div>
        <div className="kpi">
          <span>On Task</span>
          <strong style={{ color: "#6366f1" }}>{c.task || 0}</strong>
        </div>
        <div className="kpi">
          <span>Clocked out</span>
          <strong>{c["clocked-out"] || 0}</strong>
        </div>
        <div className="kpi">
          <span>Offline</span>
          <strong>{c.offline || 0}</strong>
        </div>
      </div>

      {pendingTasks.length > 0 && (
        <section className="card pending-tasks-card">
          <div className="pending-tasks-header">
            <div>
              <h2>📋 Movement &amp; Task Approvals</h2>
              <p className="hint" style={{ margin: "0.15rem 0 0" }}>
                Employees requesting to leave their seat for meetings, client calls, or room tasks.
              </p>
            </div>
            <span className="badge-pending-count">{pendingTasks.length} pending</span>
          </div>
          <div className="pending-tasks-list">
            {pendingTasks.map((t) => (
              <div key={t.id} className="pending-task-item">
                <div className="pending-task-details">
                  <div className="pending-emp-line">
                    <strong className="pending-emp-name">{t.employee_name}</strong>
                    <span className="pending-dept">{t.department ? `· ${t.department}` : ""}</span>
                  </div>
                  <div className="pending-task-info">
                    <span className="pending-tag">Task: {t.reason}</span>
                    {t.location ? <span className="pending-loc">📍 {t.location}</span> : null}
                    <span className="pending-duration">⏱️ {t.expected_minutes}m</span>
                    <span className="pending-time muted">Requested {ago(t.requested_at)}</span>
                  </div>
                </div>
                <div className="pending-task-actions">
                  <button
                    type="button"
                    className="btn-approve-task"
                    onClick={(e) => { e.preventDefault(); approveTask(t.id); }}
                  >
                    ✓ Approve
                  </button>
                  <button
                    type="button"
                    className="ghost btn-decline-task"
                    onClick={(e) => { e.preventDefault(); rejectTask(t.id); }}
                  >
                    ✕ Decline
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid">
        {(data?.team || []).map((p) => (
          <Link className="card person" to={`/hr/employee/${p.id}`} key={p.id}>
            <header>
              <div>
                <h2>{p.name}</h2>
                <p className="muted person-dept">
                  {p.department} · {p.device || "no device"}
                </p>
              </div>
              <Badge status={p.status} />
            </header>
            <div className="person-feed-wrap">
              {feeds[p.id] ? (
                <img className="person-feed on" alt="Live desk overlay" src={feeds[p.id]} />
              ) : null}
              <p className="person-feed-empty" style={{ display: feeds[p.id] ? "none" : "flex" }}>
                {emptyFeedText(p)}
              </p>
            </div>
            <div className="person-rows">
              <div className="now-row">
                <span>App</span>
                <b title={p.app || ""}>{p.app || "—"}</b>
              </div>
              <div className="now-row">
                <span>Today</span>
                <b>
                  seated {p.today.seated} · idle {p.today.idle} · {p.today.presence_pct ?? 0}%
                </b>
              </div>
            </div>
            <p className="now-ago">{ago(p.updated)}</p>
          </Link>
        ))}
      </div>
    </>
  );
}
