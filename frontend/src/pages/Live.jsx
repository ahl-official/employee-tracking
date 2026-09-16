import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ago, api } from "../api";
import { Badge } from "../components/Badge";

function emptyFeedText(p) {
  if (!p.clocked_in) return "Clocked out — camera off";
  if (p.status === "inactive") return "Inactive — laptop sleep or tab paused";
  if (p.camera_blocked) return "Camera blocked on their PC";
  if (!p.agent_live) return "Waiting for camera";
  return "Waiting for camera";
}

export default function Live() {
  const [data, setData] = useState(null);
  const [feeds, setFeeds] = useState({});
  const teamRef = useRef([]);

  const refresh = useCallback(async () => {
    const { ok, data: next } = await api("/api/team");
    if (ok) {
      teamRef.current = next.team || [];
      setData(next);
    }
  }, []);

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
          <span>Clocked out</span>
          <strong>{c["clocked-out"] || 0}</strong>
        </div>
        <div className="kpi">
          <span>Offline</span>
          <strong>{c.offline || 0}</strong>
        </div>
      </div>
      <div className="alerts">
        {unseen.map((a) => (
          <div className="alert" key={a.id}>
            <div>
              <strong>HR ping</strong> {a.message}
            </div>
            <button type="button" onClick={() => ack(a.id)}>
              Got it
            </button>
          </div>
        ))}
      </div>
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
                  seated {p.today.seated} · break {p.today.break_left || "30m"}
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
