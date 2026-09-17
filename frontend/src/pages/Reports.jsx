import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, todayIST } from "../api";
import { Badge } from "../components/Badge";

export default function Reports() {
  const [day, setDay] = useState(todayIST());
  const [data, setData] = useState(null);

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
              <th title="Share of active time in work apps vs other apps">Work apps %</th>
              <th>Seated</th>
              <th>Idle</th>
              <th>Break used</th>
              <th title="Seated / (Seated + Idle)">Presence %</th>
            </tr>
          </thead>
          <tbody>
            {(data?.team || []).map((p) => (
              <tr key={p.id}>
                <td>
                  <Link to={`/hr/employee/${p.id}`}>{p.name}</Link>
                </td>
                <td>{p.department}</td>
                <td>
                  <Badge status={p.status} />
                </td>
                <td>{p.today.active}</td>
                <td>{p.today.useful_pct}%</td>
                <td>{p.today.seated}</td>
                <td>{p.today.idle}</td>
                <td>{p.today.break_used || "0m"}</td>
                <td>
                  {p.today.seated_seconds + p.today.idle_seconds > 0
                    ? Math.round(
                      (p.today.seated_seconds /
                        (p.today.seated_seconds + p.today.idle_seconds)) *
                      100
                    )
                    : 0}
                  %
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
