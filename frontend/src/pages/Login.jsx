import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const emptySignup = {
  name: "",
  username: "",
  department: "",
  password: "",
  confirm: "",
};

export default function Login({ onLogin }) {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [signup, setSignup] = useState(emptySignup);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function goHome(user) {
    onLogin(user);
    navigate(user.role === "hr" ? "/hr" : "/me");
  }

  function switchMode(next) {
    setMode(next);
    setError("");
  }

  async function submitLogin(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        setError(res.data.error || "Wrong username or password.");
        return;
      }
      goHome(res.data.user);
    } finally {
      setBusy(false);
    }
  }

  async function submitSignup(e) {
    e.preventDefault();
    setError("");
    if (signup.password !== signup.confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const res = await api("/api/signup", {
        method: "POST",
        body: JSON.stringify({
          name: signup.name,
          username: signup.username,
          department: signup.department,
          password: signup.password,
        }),
      });
      if (!res.ok) {
        setError(res.data.error || "Could not create account.");
        return;
      }
      goHome(res.data.user);
    } finally {
      setBusy(false);
    }
  }

  function setField(field) {
    return (e) => setSignup((prev) => ({ ...prev, [field]: e.target.value }));
  }

  return (
    <div className="auth-shell">
      <div className="auth-brand">
        <p className="auth-logo">DeskTrack</p>
        <h1>Know who is at their desk — without recording video.</h1>
        <p className="auth-lead">
          Employees clock in from the browser, allow the camera once, and keep that tab open. HR gets a live board,
          daily totals, and alerts when someone stays away past break time.
        </p>
        <ul className="auth-points">
          <li>Live desk view while clocked in — frames stay in memory, nothing saved as video</li>
          <li>30 minutes of away time counts as break during work hours</li>
          <li>Clock out for lunch so longer absences do not page HR</li>
        </ul>
      </div>

      <div className="auth-panel card">
        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            className={mode === "login" ? "active" : ""}
            aria-selected={mode === "login"}
            onClick={() => switchMode("login")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            className={mode === "signup" ? "active" : ""}
            aria-selected={mode === "signup"}
            onClick={() => switchMode("signup")}
          >
            Create account
          </button>
        </div>

        {mode === "login" ? (
          <form className="login" onSubmit={submitLogin}>
            <p className="auth-sub">Sign in with your DeskTrack username.</p>
            {error ? <p className="error">{error}</p> : null}
            <label>
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <button type="submit" className="full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
            <p className="auth-switch">
              New here?{" "}
              <button type="button" className="linkish" onClick={() => switchMode("signup")}>
                Create an employee account
              </button>
            </p>
          </form>
        ) : (
          <form className="login" onSubmit={submitSignup}>
            <p className="auth-sub">Create an employee account. HR accounts are set up by your admin.</p>
            {error ? <p className="error">{error}</p> : null}
            <label>
              Full name
              <input value={signup.name} onChange={setField("name")} autoComplete="name" required />
            </label>
            <label>
              Username
              <input
                value={signup.username}
                onChange={setField("username")}
                autoComplete="username"
                placeholder="e.g. saniya"
                required
              />
            </label>
            <label>
              Department
              <input value={signup.department} onChange={setField("department")} autoComplete="organization-title" />
            </label>
            <label>
              Password
              <input
                type="password"
                value={signup.password}
                onChange={setField("password")}
                autoComplete="new-password"
                minLength={6}
                required
              />
            </label>
            <label>
              Confirm password
              <input
                type="password"
                value={signup.confirm}
                onChange={setField("confirm")}
                autoComplete="new-password"
                minLength={6}
                required
              />
            </label>
            <button type="submit" className="full" disabled={busy}>
              {busy ? "Creating…" : "Create account"}
            </button>
            <p className="auth-switch">
              Already have an account?{" "}
              <button type="button" className="linkish" onClick={() => switchMode("login")}>
                Sign in
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
