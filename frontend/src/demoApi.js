// In-browser stand-in for the Django API. Used ONLY by the Netlify demo build (`npm run build:demo`).
// It re-implements the same rules in plain JavaScript on generated sample data. Nothing is stored on a
// server: refreshing the page regenerates the data relative to today, so the demo never looks stale.
const STEP = 20, MIN = 60000, DAY = 86400000;
const SPEC = ["General Medicine", "Pediatrics", "Cardiology", "Dermatology", "Orthopedics", "ENT"];
const M1 = "Suresh Ramesh Rajesh Karthik Vignesh Arun Ashok Balaji Bharath Chandran Dinesh Ganesh Gokul Hari Harish Kannan Kishore Lokesh Madhavan Mahesh Manoj Mohan Murali Murugan Muthu Naveen Prakash Pradeep Praveen Prabhu Ravi Saravanan Sathish Selvam Senthil Shankar Siva Sriram Sundar Surya Vasanth Venkat Vijay Vikram Vinoth Vivek Anand Gowtham Santhosh".split(" ");
const F1 = "Priya Divya Anitha Lakshmi Meena Kavitha Deepa Swathi Pooja Nisha Sneha Anjali Bhavana Chitra Gayathri Harini Indira Janani Kalpana Keerthana Latha Nandhini Padma Radha Revathi Saranya Shanthi Sowmya Sudha Suganya Sunitha Uma Vaishnavi Vidya Yamini Aarthi Bharathi Dhivya Jayanthi Kaveri Malini Pavithra Shruthi Sangeetha Rekha Geetha Mythili Nithya Malathi Banu Kala Jaya".split(" ");
const M2 = "Prem Senthil Arun Ravi Siva Muthu Vijay Mohan Suresh Ram Raja Anand Dinesh Karthik Santhosh Ganesh Naveen Vinoth Saravana Bala Hari Vasanth Gopi Mahesh".split(" ");
const M3 = "Kumar Raj Prasad Babu Mani Nathan Shankar Chandran Anand Kannan".split(" ");
const F2 = "Anitha Kavitha Meena Radha Tamil Priya Deepa Revathi Geetha Sangeetha Lakshmi Saranya Divya Nithya Gayathri Malathi Uma Jaya Sudha Latha Banu Rekha Kala Mythili".split(" ");
const F3 = "Devi Kumari Rani Selvi Priya Lakshmi".split(" ");
const ADMIN = "admin", DOCTOR = "doctor", RECEPTION = "receptionist", ALL = [ADMIN, DOCTOR, RECEPTION];
const ACCOUNTS = { admin: { role: ADMIN }, reception1: { role: RECEPTION }, doctor1: { role: DOCTOR, doctor_id: 1 } };

function rng(seed) { // small deterministic generator (mulberry32)
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const pick = (arr, r) => arr[Math.floor(r() * arr.length)];
const r1 = (x) => Math.round(x * 10) / 10;
const iso = (ms) => new Date(ms).toISOString();
const dayKey = (ms) => new Date(ms).toLocaleDateString("en-CA");
const shift = (ms, days) => { const d = new Date(ms); d.setDate(d.getDate() + days); return d.getTime(); };
const midnight = (key) => new Date(key + "T00:00:00").getTime();
const fail = (status, detail) => { throw Object.assign(new Error(detail), { status }); };

let S = null;
let session = null;
try { session = JSON.parse(sessionStorage.getItem("demo-session")); } catch { /* not in a browser */ }
const saveSession = () => { try { sessionStorage.setItem("demo-session", JSON.stringify(session)); } catch { /* ignore */ } };
const need = (roles) => { if (!session || !roles.includes(session.role)) fail(403, "Your role is not allowed to do this."); };
const own = (doctorId, msg) => { if (session.role === DOCTOR && doctorId !== session.doctor_id) fail(403, msg); };

// ---------- sample data ----------
function genders(n, r) { // exactly 60% male / 40% female
  const m = Math.round(n * 0.6), g = Array(m).fill("M").concat(Array(n - m).fill("F"));
  for (let i = g.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [g[i], g[j]] = [g[j], g[i]]; }
  return g;
}
function makeName(g, r) {
  const [single, pre, suf] = g === "M" ? [M1, M2, M3] : [F1, F2, F3];
  if (r() < 0.4) for (;;) { const a = pick(pre, r), b = pick(suf, r); if (a !== b) return `${a} ${b}`; }
  return pick(single, r);
}
function addAppt(doctor, patient, start, status, mins = STEP) {
  const a = { id: S.nextAppt++, doctor, patient, start, end: start + mins * MIN, status, entry: null };
  S.appts.set(a.id, a);
  if (status !== "cancelled") for (let t = start; t < a.end; t += STEP * MIN) S.slots.set(`${doctor}|${t}`, { doctor, start: t });
  return a;
}
function makeEntry(a, checkedIn) {
  const date = dayKey(a.start);
  const token = 1 + Math.max(0, ...S.entries.filter((e) => e.doctor === a.doctor && e.date === date).map((e) => e.token));
  const e = { id: S.nextEntry++, appt: a.id, doctor: a.doctor, date, token, status: "waiting", checkedIn, started: null, ended: null };
  S.entries.push(e); a.entry = e;
  return e;
}
function build() {
  const r = rng(42), used = new Set();
  const doctors = genders(12, r).map((g, i) => {
    let n; do n = makeName(g, r); while (used.has(n)); used.add(n);
    return { id: i + 1, name: `Dr. ${n}`, specialty: SPEC[i % SPEC.length] };
  });
  const patients = genders(800, r).map((g, i) => ({
    id: i + 1, name: makeName(g, r),
    phone: `+91 ${pick(["6", "7", "8", "9"], r)}${String(Math.floor(r() * 1e4)).padStart(4, "0")} ${String(Math.floor(r() * 1e5)).padStart(5, "0")}`,
  }));
  S = { doctors, patients, appts: new Map(), slots: new Map(), entries: [], nextAppt: 1, nextEntry: 1 };
  const at = (off, k) => { const d = new Date(); d.setHours(9, k * STEP, 0, 0); d.setDate(d.getDate() + off); return d; };
  for (let back = 100; back >= 1; back--) { // history: weekdays only
    const wd = at(-back, 0).getDay();
    if (wd === 0 || wd === 6) continue;
    for (const d of doctors) for (let k = 0; k < 24; k++) {
      if (r() < 0.25) continue;
      const x = r(), st = x < 0.75 ? "completed" : x < 0.87 ? "no_show" : "cancelled";
      addAppt(d.id, 1 + Math.floor(r() * patients.length), at(-back, k).getTime(), st);
    }
  }
  for (const d of doctors.slice(0, 6)) for (let k = 0; k < 24; k++) { // today's schedule
    if (r() < 0.4) continue;
    addAppt(d.id, 1 + Math.floor(r() * patients.length), at(0, k).getTime(), "scheduled");
  }
  const now = Date.now(); // a few doctors already have a live queue
  for (const d of doctors.slice(0, 3)) {
    const todays = [...S.appts.values()].filter((a) => a.doctor === d.id && a.status === "scheduled" && a.start >= midnight(dayKey(now))).sort((x, y) => x.start - y.start).slice(0, 5);
    todays.forEach((a, i) => {
      const e = makeEntry(a, now - (40 - i * 5) * MIN);
      if (i === 0) { e.status = "completed"; e.started = now - 30 * MIN; e.ended = now - 18 * MIN; a.status = "completed"; }
      if (i === 1) { e.status = "in_consultation"; e.started = now - 6 * MIN; }
    });
  }
}

// ---------- JSON shapes (same as the Django API) ----------
const docName = (id) => S.doctors[id - 1].name;
const patName = (id) => S.patients[id - 1].name;
const apptJson = (a) => ({
  id: a.id, doctor: a.doctor, doctor_name: docName(a.doctor), patient: a.patient, patient_name: patName(a.patient),
  start: iso(a.start), end: iso(a.end), status: a.status, reason: "",
  queue_entry: a.entry ? { id: a.entry.id, token: a.entry.token, status: a.entry.status } : null,
});
const userJson = () => ({ username: session.username, is_staff: session.role === ADMIN, role: session.role, doctor_id: session.doctor_id ?? null });

// ---------- endpoints ----------
function login(b) {
  const acct = ACCOUNTS[b.username];
  if (!acct || b.password !== "demo") fail(400, "Incorrect username or password.");
  session = { username: b.username, ...acct }; saveSession();
  return userJson();
}
function listAppts(q) {
  need(ALL);
  let list = [...S.appts.values()];
  if (session.role === DOCTOR) list = list.filter((a) => a.doctor === session.doctor_id);
  else if (q.get("doctor")) list = list.filter((a) => a.doctor === +q.get("doctor"));
  if (q.get("date")) { const lo = midnight(q.get("date")), hi = shift(lo, 1); list = list.filter((a) => a.start >= lo && a.start < hi); }
  return list.sort((a, b) => a.start - b.start || a.id - b.id).slice(0, 300).map(apptJson);
}
function book(b) {
  need([ADMIN, RECEPTION]);
  const doc = S.doctors.find((d) => d.id === Number(b.doctor)), pat = S.patients.find((p) => p.id === Number(b.patient));
  const start = Date.parse(b.start), end = Date.parse(b.end);
  if (!doc || !pat) fail(400, "Choose a valid doctor and patient.");
  if (!(end > start)) fail(400, "end must be after start.");
  const d = new Date(start), mins = (end - start) / MIN;
  if (d.getSeconds() || d.getMilliseconds() || (d.getHours() * 60 + d.getMinutes()) % STEP) fail(400, `start must be on a ${STEP}-minute boundary.`);
  if (mins % STEP || mins > 120) fail(400, `duration must be a multiple of ${STEP} min, at most 120.`);
  for (let t = start; t < end; t += STEP * MIN) if (S.slots.has(`${doc.id}|${t}`)) fail(409, "That time overlaps an existing appointment.");
  return apptJson(addAppt(doc.id, pat.id, start, "scheduled", mins));
}
function cancel(id) {
  need([ADMIN, RECEPTION]);
  const a = S.appts.get(id); if (!a) fail(404, "Not found.");
  if (a.status !== "scheduled") fail(409, "Only scheduled appointments can be cancelled.");
  if (a.entry) fail(409, "Patient already checked in.");
  a.status = "cancelled";
  for (let t = a.start; t < a.end; t += STEP * MIN) S.slots.delete(`${a.doctor}|${t}`);
  return apptJson(a);
}
function checkIn(b) {
  need([ADMIN, RECEPTION]);
  const a = S.appts.get(Number(b.appointment)); if (!a) fail(404, "Not found.");
  if (a.status !== "scheduled") fail(409, "Only scheduled appointments can check in.");
  if (a.entry) fail(409, "Already checked in.");
  const e = makeEntry(a, Date.now());
  return { entry_id: e.id, token: e.token };
}
function consult(id, action) {
  need(action === "no-show" ? ALL : [ADMIN, DOCTOR]);
  const e = S.entries.find((x) => x.id === id); if (!e) fail(404, "Not found.");
  own(e.doctor, "This patient is not in your queue.");
  const a = S.appts.get(e.appt);
  if (action === "start") {
    if (e.status !== "waiting") fail(409, "Patient is not waiting.");
    if (S.entries.some((x) => x.doctor === e.doctor && x.status === "in_consultation")) fail(409, "Doctor already has a patient in consultation.");
    e.status = "in_consultation"; e.started = Date.now();
  } else if (action === "complete") {
    if (e.status !== "in_consultation") fail(409, `Cannot move from ${e.status}.`);
    e.status = "completed"; e.ended = Date.now(); a.status = "completed";
  } else {
    if (e.status !== "waiting") fail(409, `Cannot move from ${e.status}.`);
    e.status = "no_show"; e.ended = Date.now(); a.status = "no_show";
  }
  return { entry_id: e.id, status: e.status };
}
function snapshot(doctorId) {
  need(ALL); own(doctorId, "You can only view your own queue.");
  const today = dayKey(Date.now()), all = S.entries.filter((e) => e.doctor === doctorId);
  const todays = all.filter((e) => e.date === today);
  const row = (e) => ({ entry_id: e.id, token: e.token, patient: patName(S.appts.get(e.appt).patient), checked_in_at: iso(e.checkedIn), started_at: e.started && iso(e.started) });
  const serving = todays.find((e) => e.status === "in_consultation"), waiting = todays.filter((e) => e.status === "waiting");
  const done = all.filter((e) => e.status === "completed" && e.started && e.ended).sort((a, b) => b.ended - a.ended).slice(0, 50);
  return {
    now_serving: serving ? serving.token : null, serving: serving ? row(serving) : null,
    waiting_count: waiting.length, waiting: waiting.map(row),
    completed_count: todays.filter((e) => e.status === "completed").length,
    avg_consult_minutes: done.length ? r1(done.reduce((s, e) => s + (e.ended - e.started) / MIN, 0) / done.length) : 10,
  };
}
function totals(rows) {
  const n = (s) => rows.filter((a) => a.status === s).length;
  const t = { total: rows.length, completed: n("completed"), no_show: n("no_show"), cancelled: n("cancelled"), scheduled: n("scheduled") };
  const seen = t.completed + t.no_show;
  return { ...t, no_show_rate: seen ? r1((100 * t.no_show) / seen) : 0, cancel_rate: t.total ? r1((100 * t.cancelled) / t.total) : 0 };
}
function overview(q) {
  need([ADMIN]);
  const to = q.get("to") || dayKey(Date.now()), toMs = midnight(to);
  const from = q.get("from") || dayKey(shift(toMs, -89)), lo = midnight(from), hi = shift(toMs, 1);
  let span = 0, weekdays = 0;
  for (let t = lo; t < hi; t = shift(t, 1)) { span++; const w = new Date(t).getDay(); if (w > 0 && w < 6) weekdays++; }
  if (lo > toMs || span > 365) fail(400, "Choose a date range of at most one year.");
  const doctor = q.get("doctor") ? +q.get("doctor") : null;
  const win = (a, b) => [...S.appts.values()].filter((x) => x.start >= a && x.start < b && (!doctor || x.doctor === doctor));
  const rows = win(lo, hi), cur = totals(rows), prev = totals(win(shift(lo, -span), lo));
  const byDay = new Map();
  for (const a of rows) { const k = dayKey(a.start), d = byDay.get(k) || { day: k, total: 0, no_show: 0 }; d.total++; if (a.status === "no_show") d.no_show++; byDay.set(k, d); }
  const heat = new Map();
  for (const a of rows) if (a.status !== "cancelled") { const d = new Date(a.start), k = `${(d.getDay() + 6) % 7 + 1}-${d.getHours()}`; heat.set(k, (heat.get(k) || 0) + 1); }
  const capacity = Math.max(1, (480 / STEP) * weekdays), booked = new Map();
  for (const s of S.slots.values()) if (s.start >= lo && s.start < hi && (!doctor || s.doctor === doctor)) booked.set(s.doctor, (booked.get(s.doctor) || 0) + 1);
  const perDoc = new Map();
  for (const a of rows) { const d = perDoc.get(a.doctor) || { total: 0, completed: 0, no_show: 0 }; d.total++; if (a.status === "completed") d.completed++; if (a.status === "no_show") d.no_show++; perDoc.set(a.doctor, d); }
  const doctors = [...perDoc].sort((x, y) => y[1].total - x[1].total).map(([id, d]) => ({
    doctor: docName(id), total: d.total,
    no_show_rate: d.completed + d.no_show ? r1((100 * d.no_show) / (d.completed + d.no_show)) : 0,
    utilization: Math.min(100, r1((100 * (booked.get(id) || 0)) / capacity)),
  }));
  const sumBooked = [...booked.values()].reduce((s, n) => s + n, 0), nDocs = doctor ? 1 : S.doctors.length;
  return {
    range: { from, to, days: span },
    kpis: { current: { ...cur, utilization: Math.min(100, r1((100 * sumBooked) / (capacity * nDocs))) }, previous: prev },
    daily: [...byDay.values()].sort((a, b) => (a.day < b.day ? -1 : 1)),
    heatmap: [...heat].map(([k, n]) => { const [dow, hour] = k.split("-").map(Number); return { dow, hour, n }; }).sort((a, b) => a.dow - b.dow || a.hour - b.hour),
    doctors,
  };
}

export function demoRequest(path, method = "GET", body) {
  if (!S) build();
  const url = new URL(path, "http://demo"), p = url.pathname, q = url.searchParams, post = method === "POST";
  let m;
  if (p === "/auth/csrf/") return { ok: true };
  if (p === "/auth/login/" && post) return login(body || {});
  if (p === "/auth/logout/") { session = null; saveSession(); return null; }
  if (p === "/auth/me/") { need(ALL); return userJson(); }
  if (p === "/doctors/") { need(ALL); return S.doctors.filter((d) => session.role !== DOCTOR || d.id === session.doctor_id); }
  if (p === "/patients/") {
    need([ADMIN, RECEPTION]);
    const t = (q.get("q") || "").trim().toLowerCase();
    return t ? S.patients.filter((x) => x.name.toLowerCase().includes(t)).slice(0, 15) : [];
  }
  if (p === "/appointments/") return post ? book(body || {}) : listAppts(q);
  if ((m = p.match(/^\/appointments\/(\d+)\/cancel\/$/)) && post) return cancel(+m[1]);
  if (p === "/queue/check-in/" && post) return checkIn(body || {});
  if ((m = p.match(/^\/queue\/(\d+)\/(start|complete|no-show)\/$/)) && post) return consult(+m[1], m[2]);
  if ((m = p.match(/^\/queue\/doctor\/(\d+)\/$/))) return snapshot(+m[1]);
  if (p === "/analytics/overview/") return overview(q);
  return fail(404, "Not found.");
}
