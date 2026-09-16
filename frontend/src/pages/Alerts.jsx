import { useCallback, useEffect, useState } from "react";
import { api, prettyTime } from "../api";

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);

  const refresh = useCallback(async () => {
    const { ok, data } = await api("/api/team");
    if (ok) setAlerts(data.alerts || []);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  async function ack(id) {
    await api(`/api/alerts/${id}/seen`, { method: "POST", body: "{}" });
    refresh();
  }

  return (
    <>
      <header className="page">
        <div>
          <h1>HR pings</h1>
          <p className="muted">
            Away-after-break alerts, and face-mismatch pings when someone else sits at an enrolled desk.
            Set <code>HR_ALERT_WEBHOOK</code> on the server (Slack/Teams/Discord) so HR is notified even when
            not on this page.
          </p>
        </div>
      </header>
      <div className="stack">
        {alerts.length ? (
          alerts.map((a) => (
            <article className={`card alert-row ${a.seen ? "seen" : ""}`} key={a.id}>
              <div>
                <strong>{a.name}</strong>
                <p>{a.message}</p>
                <p className="muted">{prettyTime(a.created_at)}</p>
              </div>
              {a.seen ? (
                <span className="muted">Seen</span>
              ) : (
                <button type="button" onClick={() => ack(a.id)}>
                  Acknowledge
                </button>
              )}
            </article>
          ))
        ) : (
          <p className="muted">No pings yet.</p>
        )}
      </div>
    </>
  );
}
