import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function People() {
  const [people, setPeople] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    username: "",
    department: "",
    password: "emp123",
  });

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
    const { ok, data } = await api("/api/people", {
      method: "POST",
      body: JSON.stringify(form),
    });
    if (!ok) {
      setError(data.error || "Could not create that person.");
      return;
    }
    setForm({ name: "", username: "", department: "", password: "emp123" });
    load();
  }

  function set(field) {
    return (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  }

  return (
    <>
      <header className="page">
        <div>
          <h1>People</h1>
          <p className="muted">
            Add employees here, or they can create their own account from the sign-in page.
          </p>
        </div>
      </header>
      <section className="split">
        <form className="card" onSubmit={submit}>
          <h2>Add employee</h2>
          {error ? <p className="error">{error}</p> : null}
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
