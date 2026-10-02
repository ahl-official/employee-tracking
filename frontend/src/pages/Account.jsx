import { useState } from "react";
import { api } from "../api";

export default function Account({ user, onUser }) {
  const [name, setName] = useState(user?.name || "");
  const [newUsername, setNewUsername] = useState(user?.username || "");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setOkMsg("");
    if (newPassword && newPassword !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const body = { password };
      if (name.trim() !== user.name) body.name = name.trim();
      if (newUsername.trim() && newUsername.trim().toLowerCase() !== user.username) {
        body.new_username = newUsername.trim();
      }
      if (newPassword) body.new_password = newPassword;
      const res = await api("/api/me/account", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        setError(res.data.error || "Could not update account.");
        return;
      }
      onUser?.(res.data.user);
      setPassword("");
      setNewPassword("");
      setConfirm("");
      setNewUsername(res.data.user.username);
      setName(res.data.user.name);
      setOkMsg("Account updated.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page">
        <div>
          <h1>Account</h1>
          <p className="muted">Change your display name, username, or password.</p>
        </div>
      </header>
      <section className="card" style={{ maxWidth: 420 }}>
        <form className="login" onSubmit={submit}>
          {error ? <p className="error">{error}</p> : null}
          {okMsg ? <p className="ok">{okMsg}</p> : null}
          <label>
            Full name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Username
            <input value={newUsername} onChange={(e) => setNewUsername(e.target.value)} required />
          </label>
          <label>
            Current password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <label>
            New password <span className="muted">(optional)</span>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              minLength={6}
            />
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              minLength={6}
              disabled={!newPassword}
            />
          </label>
          <button type="submit" className="full" disabled={busy}>
            {busy ? "Saving…" : "Save changes"}
          </button>
        </form>
      </section>
    </>
  );
}
