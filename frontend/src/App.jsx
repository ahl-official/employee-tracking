import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import Layout from "./components/Layout";
import Alerts from "./pages/Alerts";
import Desk from "./pages/Desk";
import Employee from "./pages/Employee";
import Live from "./pages/Live";
import Login from "./pages/Login";
import People from "./pages/People";
import Reports from "./pages/Reports";

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api("/api/session").then(({ ok, data }) => {
      if (ok) setUser(data.user);
      setReady(true);
    });
  }, []);

  if (!ready) return null;

  const home = user?.role === "hr" ? "/hr" : "/me";

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to={home} replace /> : <Login onLogin={setUser} />}
      />
      <Route
        path="/*"
        element={
          user ? (
            <Layout user={user} onLogout={() => setUser(null)}>
              {user.role === "hr" ? (
                <Routes>
                  <Route path="/hr" element={<Live />} />
                  <Route path="/hr/reports" element={<Reports />} />
                  <Route path="/hr/alerts" element={<Alerts />} />
                  <Route path="/hr/people" element={<People />} />
                  <Route path="/hr/employee/:id" element={<Employee />} />
                  <Route path="*" element={<Navigate to="/hr" replace />} />
                </Routes>
              ) : (
                <Routes>
                  <Route path="/me" element={<Desk />} />
                  <Route path="*" element={<Navigate to="/me" replace />} />
                </Routes>
              )}
            </Layout>
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
    </Routes>
  );
}
