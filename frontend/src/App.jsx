import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Queue from "./pages/Queue.jsx";
import Appointments from "./pages/Appointments.jsx";

const NAV = [["dashboard", "Dashboard"], ["queue", "Live queue"], ["appointments", "Appointments"]];

export default function App() {
  const [user, setUser] = useState(undefined);
  const [view, setView] = useState(null);
  const [toast, setToast] = useState(null);

  const notify = useCallback((text, kind = "ok") => {
    setToast({ text, kind });
    setTimeout(() => setToast(null), 3500);
  }, []);

  useEffect(() => {
    api("/auth/csrf/").then(() => api("/auth/me/")).then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) return <div className="boot">Loading…</div>;
  if (!user) return <Login onLogin={setUser} />;

  const signOut = async () => { await api("/auth/logout/", { method: "POST" }); setUser(null); };

  if (!user.role) return (
    <div className="boot"><div>
      <p>Your account has no role yet. Ask an administrator to make you a receptionist or link you to a doctor.</p>
      <button className="link" onClick={signOut}>Sign out</button>
    </div></div>
  );

  const items = NAV.filter(([key]) => key !== "dashboard" || user.role === "admin");
  const current = view ?? items[0][0]; // admins land on the dashboard, everyone else on the queue

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand"><span className="mark" aria-hidden="true">+</span>ClinicFlow</div>
        <nav aria-label="Main">
          {items.map(([key, label]) => (
            <button key={key} className={current === key ? "nav on" : "nav"} onClick={() => setView(key)}>{label}</button>
          ))}
        </nav>
        <div className="me">
          <div className="avatar" aria-hidden="true">{user.username[0].toUpperCase()}</div>
          <div><div className="who">{user.username}</div><div className="role">{user.role}</div><button className="link" onClick={signOut}>Sign out</button></div>
        </div>
      </aside>
      <main className="main">
        {current === "dashboard" ? <Dashboard /> : current === "queue" ? <Queue notify={notify} user={user} /> : <Appointments notify={notify} user={user} />}
      </main>
      {toast && <div className={`toast ${toast.kind}`} role="status">{toast.text}</div>}
    </div>
  );
}
