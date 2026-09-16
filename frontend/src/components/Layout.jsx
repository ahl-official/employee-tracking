import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Layout({ user, onLogout, children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const desk = location.pathname === "/me";
  const [facePhoto, setFacePhoto] = useState(null);

  useEffect(() => {
    if (user?.role !== "employee") {
      setFacePhoto(null);
      return;
    }
    let alive = true;
    async function load() {
      try {
        const res = await fetch("/api/me/face/photo", { credentials: "include", cache: "no-store" });
        if (!alive) return;
        if (res.status === 200) {
          const blob = await res.blob();
          const next = URL.createObjectURL(blob);
          setFacePhoto((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return next;
          });
        } else {
          setFacePhoto((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return null;
          });
        }
      } catch {
        /* ignore */
      }
    }
    load();
    const onFace = () => load();
    window.addEventListener("desktrack-face", onFace);
    const t = setInterval(load, 20000);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener("desktrack-face", onFace);
      setFacePhoto((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [user?.role, location.pathname]);

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
          {facePhoto ? (
            <img className="nav-face" src={facePhoto} alt="" width={48} height={48} />
          ) : null}
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
