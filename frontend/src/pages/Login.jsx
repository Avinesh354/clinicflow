import { useState } from "react";
import { api, DEMO } from "../api";

export default function Login({ onLogin }) {
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try { onLogin(await api("/auth/login/", { method: "POST", body: form })); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const quick = async (username) => {
    setError("");
    try { onLogin(await api("/auth/login/", { method: "POST", body: { username, password: "demo" } })); }
    catch (err) { setError(err.message); }
  };

  return (
    <div className="login">
      <section className="login-pitch">
        <div className="brand"><span className="mark" aria-hidden="true">+</span>ClinicFlow</div>
        <h1>Know who’s next, and how long they’ll wait.</h1>
        <p>Scheduling that can’t double-book and a live queue for every doctor, in one screen.</p>
      </section>
      <form className="login-form" onSubmit={submit}>
        <h2>Sign in</h2>
        <label>Username<input autoFocus required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
        <label>Password<input type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {DEMO && (
          <div className="quick">
            <p className="muted">Demo version: try a role in one click (password: demo)</p>
            <div>
              {[["admin", "Admin"], ["reception1", "Receptionist"], ["doctor1", "Doctor"]].map(([u, label]) => (
                <button type="button" key={u} className="btn ghost" onClick={() => quick(u)}>{label}</button>
              ))}
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
