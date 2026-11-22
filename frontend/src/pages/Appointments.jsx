import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const SLOTS = Array.from({ length: 24 }, (_, i) => {
  const m = 9 * 60 + i * 20;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
});
const LABEL = { scheduled: "Scheduled", completed: "Completed", cancelled: "Cancelled", no_show: "No-show" };

export default function Appointments({ notify, user }) {
  const [doctors, setDoctors] = useState([]);
  const [doctorId, setDoctorId] = useState("");
  const [date, setDate] = useState(today());
  const [rows, setRows] = useState(null);
  const [booking, setBooking] = useState(false);
  const canBook = ["admin", "receptionist"].includes(user.role);

  useEffect(() => { api("/doctors/").then(setDoctors); }, []);

  const load = useCallback(() => {
    const q = new URLSearchParams({ date, ...(doctorId && { doctor: doctorId }) });
    api(`/appointments/?${q}`).then(setRows).catch((e) => notify(e.message, "err"));
  }, [date, doctorId, notify]);
  useEffect(() => { setRows(null); load(); }, [load]);

  const run = async (path, body, done) => {
    try { await api(path, { method: "POST", body }); notify(done); load(); }
    catch (e) { notify(e.message, "err"); }
  };

  return (
    <>
      <header className="page-head">
        <div><h1>Appointments</h1><p className="muted">Check patients in as they arrive.</p></div>
        {canBook && <button className="btn primary" onClick={() => setBooking(true)}>New appointment</button>}
      </header>

      <div className="filters">
        <label className="field-inline">Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        {user.role !== "doctor" && (
          <label className="field-inline">Doctor
            <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
              <option value="">All doctors</option>
              {doctors.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
        )}
      </div>

      <div className="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>Patient</th><th>Doctor</th><th>Status</th><th>Token</th><th><span className="sr">Actions</span></th></tr></thead>
          <tbody>
            {rows === null && <tr><td colSpan="6" className="muted">Loading…</td></tr>}
            {rows?.length === 0 && <tr><td colSpan="6" className="empty-note">No appointments on this date. Pick another day or create one.</td></tr>}
            {rows?.map((a) => (
              <tr key={a.id}>
                <td className="num">{clock(a.start)}–{clock(a.end)}</td>
                <td><strong>{a.patient_name}</strong></td>
                <td>{a.doctor_name}</td>
                <td><span className={`pill ${a.queue_entry?.status === "waiting" ? "waiting" : a.queue_entry?.status === "in_consultation" ? "inside" : a.status}`}>
                  {a.queue_entry?.status === "waiting" ? "Waiting" : a.queue_entry?.status === "in_consultation" ? "In consultation" : LABEL[a.status]}</span></td>
                <td className="num">{a.queue_entry ? `#${a.queue_entry.token}` : ""}</td>
                <td>
                  <div className="actions">
                    {canBook && a.status === "scheduled" && !a.queue_entry && (
                      <>
                        <button className="btn ghost" onClick={() => run("/queue/check-in/", { appointment: a.id }, "Patient checked in.")}>Check in</button>
                        <button className="btn ghost danger" onClick={() => run(`/appointments/${a.id}/cancel/`, null, "Appointment cancelled.")}>Cancel</button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {booking && <BookingModal doctors={doctors} defaultDate={date} onClose={() => setBooking(false)}
        onBooked={() => { setBooking(false); notify("Appointment booked."); load(); }} />}
    </>
  );
}

function BookingModal({ doctors, defaultDate, onClose, onBooked }) {
  const [form, setForm] = useState({ doctor: doctors[0]?.id ?? "", date: defaultDate, time: "09:00", minutes: 20 });
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState([]);
  const [patient, setPatient] = useState(null);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    if (!query.trim() || patient) return setMatches([]);
    const t = setTimeout(() => api(`/patients/?q=${encodeURIComponent(query)}`).then(setMatches), 250);
    return () => clearTimeout(t);
  }, [query, patient]);

  const submit = async (e) => {
    e.preventDefault();
    if (!patient) return setError("Choose a patient from the search results.");
    const start = new Date(`${form.date}T${form.time}`);
    try {
      await api("/appointments/", { method: "POST", body: {
        doctor: Number(form.doctor), patient: patient.id, start: start.toISOString(),
        end: new Date(start.getTime() + form.minutes * 60000).toISOString() } });
      onBooked();
    } catch (err) { setError(err.status === 409 ? "That time is already booked for this doctor. Pick another slot." : err.message); }
  };

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="modal" onSubmit={submit} role="dialog" aria-modal="true" aria-label="New appointment">
        <h2>New appointment</h2>
        <label>Patient
          {patient ? (
            <div className="selected"><span>{patient.name}</span><button type="button" className="link" onClick={() => { setPatient(null); setQuery(""); }}>Change</button></div>
          ) : <input autoFocus placeholder="Search by name" value={query} onChange={(e) => setQuery(e.target.value)} />}
        </label>
        {matches.length > 0 && <ul className="matches">{matches.map((p) => <li key={p.id}><button type="button" onClick={() => setPatient(p)}>{p.name}<span className="muted">{p.phone}</span></button></li>)}</ul>}
        <label>Doctor<select value={form.doctor} onChange={set("doctor")}>{doctors.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
        <div className="two">
          <label>Date<input type="date" value={form.date} onChange={set("date")} required /></label>
          <label>Start<select value={form.time} onChange={set("time")}>{SLOTS.map((s) => <option key={s}>{s}</option>)}</select></label>
          <label>Length<select value={form.minutes} onChange={(e) => setForm({ ...form, minutes: Number(e.target.value) })}><option value="20">20 min</option><option value="40">40 min</option><option value="60">60 min</option></select></label>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="modal-actions"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn primary">Book appointment</button></div>
      </form>
    </div>
  );
}
