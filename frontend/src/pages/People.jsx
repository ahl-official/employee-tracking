import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function People() {
  const [people, setPeople] = useState([]);
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [form, setForm] = useState({
    name: "",
    username: "",
    department: "",
    password: "emp123",
  });
  const [resetId, setResetId] = useState(null);
  const [resetForm, setResetForm] = useState({ username: "", password: "emp123" });
  const [resetBusy, setResetBusy] = useState(false);

  async function load() {
    const { ok, data } = await api("/api/people");
    if (ok) setPeople(data.people || []);
  }

  useEffect(() => {
    load();
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setOkMsg("");
    const { ok, data } = await api("/api/people", {
      method: "POST",
      body: JSON.stringify(form),
    });
    if (!ok) {
      setError(data.error || "Could not create that person.");
      return;
    }
    setForm({ name: "", username: "", department: "", password: "emp123" });
    setOkMsg("Employee created.");
    load();
  }

  function openReset(person) {
    setError("");
    setOkMsg("");
    setResetId(person.id);
    setResetForm({ username: person.username, password: "emp123" });
  }

  function closeReset() {
    setResetId(null);
    setResetForm({ username: "", password: "emp123" });
  }

  async function submitReset(e) {
    e.preventDefault();
    setError("");
    setOkMsg("");
    setResetBusy(true);
    try {
      const { ok, data } = await api(`/api/people/${resetId}/reset`, {
        method: "POST",
        body: JSON.stringify({
          username: resetForm.username.trim(),
          password: resetForm.password,
        }),
      });
      if (!ok) {
        setError(data.error || "Could not reset credentials.");
        return;
      }
      setOkMsg(
        `Updated ${data.user.name}: username “${data.user.username}”` +
          (resetForm.password ? ` · password set to “${resetForm.password}”` : "")
      );
      closeReset();
      load();
    } finally {
      setResetBusy(false);
    }
  }

  function set(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  const resetting = people.find((p) => p.id === resetId);

  return (
    <>
      <header className="page">
        <div>
          <h1>People</h1>
          <p className="muted">
            Add employees here, or they can create their own account from the sign-in page. Reset username/password if
            someone is locked out.
          </p>
        </div>
      </header>
      <section className="split">
        <form className="card" onSubmit={submit}>
          <h2>Add employee</h2>
          {error ? <p className="error">{error}</p> : null}
          {okMsg ? <p className="ok">{okMsg}</p> : null}
          <label>
            Full name <input value={form.name} onChange={set("name")} required />
          </label>
          <label>
            Username <input value={form.username} onChange={set("username")} required placeholder="e.g. riya" />
          </label>
          <label>
            Department <input value={form.department} onChange={set("department")} />
          </label>
          <label>
            Temp password <input value={form.password} onChange={set("password")} />
          </label>
          <button type="submit" className="full">
            Create
          </button>
        </form>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Username</th>
                <th>Role</th>
                <th>Dept</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {people.map((p) => (
                <tr key={p.id}>
                  <td>
                    {p.role === "employee" ? <Link to={`/hr/employee/${p.id}`}>{p.name}</Link> : p.name}
                  </td>
                  <td>
                    <code>{p.username}</code>
                  </td>
                  <td>{p.role}</td>
                  <td>{p.department}</td>
                  <td>
                    {p.role === "employee" ? (
                      <button type="button" className="linkish" onClick={() => openReset(p)}>
                        Reset login
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {resetting ? (
        <div className="modal-backdrop" onClick={closeReset} role="presentation">
          <form
            className="card modal-card"
            onSubmit={submitReset}
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Reset login — {resetting.name}</h2>
            <p className="muted">Sets a new username and/or password. Share the new password with them once.</p>
            {error ? <p className="error">{error}</p> : null}
            <label>
              Username
              <input
                value={resetForm.username}
                onChange={(e) => setResetForm((prev) => ({ ...prev, username: e.target.value }))}
                required
              />
            </label>
            <label>
              New password
              <input
                value={resetForm.password}
                onChange={(e) => setResetForm((prev) => ({ ...prev, password: e.target.value }))}
                minLength={6}
                required
              />
            </label>
            <div className="row-actions">
              <button type="button" className="ghost" onClick={closeReset}>
                Cancel
              </button>
              <button type="submit" disabled={resetBusy}>
                {resetBusy ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
