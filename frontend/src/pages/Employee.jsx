import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { Badge } from "../components/Badge";

export default function Employee() {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [feed, setFeed] = useState("");
  const wrapRef = useRef(null);

  const refresh = useCallback(async () => {
    const { ok, data } = await api(`/api/employee/${id}`);
    if (ok) setP(data);
  }, [id]);

  useEffect(() => {
    setFeed("");
    refresh();
    const t1 = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 5000);
    const t2 = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      const url = `/api/hr/preview/${id}?` + Date.now();
      const probe = new Image();
      probe.onload = () => setFeed(url);
      probe.onerror = () => setFeed("");
      probe.src = url;
    }, 600);
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, [id, refresh]);

  function toggleFullscreen() {
    const wrap = wrapRef.current;
    if (!wrap) return;
    if (!document.fullscreenElement) {
      (wrap.requestFullscreen || wrap.webkitRequestFullscreen).call(wrap);
    } else {
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    }
  }

  const today = p?.today || { apps: [] };
  const max = Math.max(...(today.apps || []).map((a) => a.seconds), 1);
  const groups = [];
  for (const row of p?.timeline || []) {
    const seat = row.present === 1 ? "in seat" : row.present === 0 ? "away" : "unknown";
    const app = row.app || "—";
    const t = (row.created_at || "").slice(11, 19);
    const last = groups[groups.length - 1];
    if (last && last.app === app && last.seat === seat) {
      last.count += 1;
      last.from = t;
    } else {
      groups.push({ app, seat, from: t, to: t, count: 1 });
    }
  }

  return (
    <>
      <header className="page">
        <div>
          <p className="eyebrow">
            <Link className="back" to="/hr">
              ← Live board
            </Link>
          </p>
          <h1>{p?.name || "Employee"}</h1>
          <p className="muted">
            {p?.department || ""} · today’s live desk view, seated time, and apps. Past days are on Daily report.
          </p>
        </div>
      </header>
      <div className="kpis">
        <div className="kpi">
          <span>Status</span>
          <strong>
            <Badge status={p?.status} />
          </strong>
        </div>
        <div className="kpi">
          <span>Seated</span>
          <strong>{today.seated || "—"}</strong>
        </div>
        <div className="kpi">
          <span>Active</span>
          <strong>{today.active || "—"}</strong>
        </div>
        <div className="kpi">
          <span>Idle (sleep)</span>
          <strong>{today.idle || "—"}</strong>
        </div>
        <div className="kpi">
          <span>Break used</span>
          <strong>{today.break_used || "0m"}</strong>
        </div>
      </div>
      <section className="monitor-card card">
        <h2>Live monitoring</h2>
        <div className="video-wrap" ref={wrapRef} title="Click for fullscreen" onClick={toggleFullscreen}>
          {feed ? <img id="feed" alt="Live camera overlay" src={feed} style={{ display: "block" }} /> : null}
          {!feed ? (
            <p className="muted">No live camera. The employee must be clocked in with the camera allowed in the browser.</p>
          ) : null}
          <span className="fs-hint">Click for fullscreen</span>
        </div>
        <p className="legend">
          <span className="leg">
            <span className="dot green" />
            Desk zone
          </span>
          <span className="leg">
            <span className="dot red" />
            At desk
          </span>
          <span className="leg">
            <span className="dot blue" />
            Outside
          </span>
          <span className="leg hint">Same overlay the employee sees · click for fullscreen</span>
        </p>
      </section>
      <section className="split">
        <article className="card split-card">
          <h2>Apps today</h2>
          <div className="split-scroll">
            <ul className="apps">
              {(today.apps || []).length ? (
                today.apps.map((a) => (
                  <li key={a.app}>
                    <div>
                      <span>{a.app}</span>
                      <span className="bar">
                        <i style={{ width: `${Math.round((a.seconds / max) * 100)}%` }} />
                      </span>
                    </div>
                    <span>{a.label}</span>
                  </li>
                ))
              ) : (
                <li>No app time yet today</li>
              )}
            </ul>
          </div>
        </article>
        <article className="card split-card">
          <h2>Recent activity</h2>
          <div className="split-scroll">
            <ol className="timeline">
              {groups.length ? (
                groups.map((g, i) => {
                  const when = g.count > 1 ? `${g.to} – ${g.from}` : g.to;
                  const extra = g.count > 1 ? ` · ${g.count} samples` : "";
                  return (
                    <li key={`${g.app}-${g.seat}-${i}`}>
                      <em>{when}</em>
                      <span>
                        {g.app} · {g.seat}
                        {extra}
                      </span>
                    </li>
                  );
                })
              ) : (
                <li className="muted">No samples yet</li>
              )}
            </ol>
          </div>
        </article>
      </section>
    </>
  );
}
