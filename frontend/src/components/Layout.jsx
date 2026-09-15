import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";

export default function Layout({ user, onLogout, children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const desk = location.pathname === "/me";

  async function logout() {
    await api("/api/logout", { method: "POST", body: "{}" });
    onLogout?.();
    navigate("/login");
  }

  return (
    <div className={`has-nav${desk ? " desk-page" : ""}`}>
      <aside className="nav">
        <div className="brand">DeskTrack</div>
        {user.role === "hr" ? (
          <>
            <NavLink to="/hr" end>
              Live board
            </NavLink>
            <NavLink to="/hr/reports">Daily report</NavLink>
            <NavLink to="/hr/alerts">HR pings</NavLink>
            <NavLink to="/hr/people">People</NavLink>
            <a href="/hr/export.csv">Export CSV</a>
          </>
        ) : (
          <NavLink to="/me">My desk</NavLink>
        )}
        <div className="nav-foot">
          <span>{user.name}</span>
          <span className="muted">{user.role}</span>
          <button type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </aside>
      <main>{children || <Outlet />}</main>
    </div>
  );
}
