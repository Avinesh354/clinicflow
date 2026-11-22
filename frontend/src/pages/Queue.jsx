import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const minutesSince = (iso) => (iso ? Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000)) : 0);

export default function Queue({ notify, user }) {
  const [doctors, setDoctors] = useState([]);
  const [doctorId, setDoctorId] = useState("");
  const [snap, setSnap] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/doctors/").then((d) => { setDoctors(d); if (d[0]) setDoctorId(String(d[0].id)); });
  }, []);

  const load = useCallback(() => {
    if (doctorId) api(`/queue/doctor/${doctorId}/`).then(setSnap).catch(() => {});
  }, [doctorId]);

  useEffect(() => {
    setSnap(null); load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  const act = async (entryId, action) => {
    setBusy(true);
    try { await api(`/queue/${entryId}/${action}/`, { method: "POST" }); await load(); }
    catch (e) { notify(e.message, "err"); }
    finally { setBusy(false); }
  };

  const next = snap?.waiting[0];
  const canConsult = ["admin", "doctor"].includes(user.role); // receptionists can only check in / mark no-show

  return (
    <>
      <header className="page-head">
        <div><h1>Live queue</h1><p className="muted">Refreshes every 5 seconds.</p></div>
        <label className="field-inline">Doctor
          <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
            {doctors.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.specialty}</option>)}
          </select>
        </label>
      </header>

      {!snap ? <p className="muted">Loading queue…</p> : (
        <div className="queue-grid">
          <section className="serving" aria-live="polite">
            <p className="serving-label">Now serving</p>
            {snap.serving ? (
              <>
                <div className="token">{snap.serving.token}</div>
                <h2>{snap.serving.patient}</h2>
                <p className="serving-meta">In consultation for {minutesSince(snap.serving.started_at)} min</p>
                {canConsult && <button className="btn light" disabled={busy} onClick={() => act(snap.serving.entry_id, "complete")}>Complete consultation</button>}
              </>
            ) : (
              <>
                <div className="token empty">–</div>
                <h2>Nobody is inside</h2>
                <p className="serving-meta">{next ? `Token ${next.token} is next.` : "No one is waiting."}</p>
                {canConsult && <button className="btn light" disabled={busy || !next} onClick={() => act(next.entry_id, "start")}>Call next patient</button>}
              </>
            )}
          </section>

          <section className="waiting">
            <dl className="stats">
              <div><dt>Waiting</dt><dd>{snap.waiting_count}</dd></div>
              <div><dt>Seen today</dt><dd>{snap.completed_count}</dd></div>
              <div><dt>Avg consultation</dt><dd>{snap.avg_consult_minutes} min</dd></div>
            </dl>
            <h3>Waiting room</h3>
            {snap.waiting.length === 0 ? (
              <p className="empty-note">No one is waiting. Check patients in from the Appointments page.</p>
            ) : (
              <ul className="rows">
                {snap.waiting.map((w) => (
                  <li key={w.entry_id}>
                    <span className="chip">{w.token}</span>
                    <div className="grow"><strong>{w.patient}</strong><span className="muted">Waiting {minutesSince(w.checked_in_at)} min</span></div>
                    {canConsult && <button className="btn ghost" disabled={busy || !!snap.serving} onClick={() => act(w.entry_id, "start")}>Call in</button>}
                    <button className="btn ghost danger" disabled={busy} onClick={() => act(w.entry_id, "no-show")}>No-show</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  );
}
