import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api";

const iso = (d) => d.toLocaleDateString("en-CA");
const RANGES = [[7, "7 days"], [30, "30 days"], [90, "90 days"]];
const DOW = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const short = (day) => new Date(day + "T00:00:00").toLocaleDateString([], { day: "numeric", month: "short" });
const hourLabel = (h) => `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`;

// Change vs the previous period. `goodWhenUp` decides whether a rise is green or red.
function change(cur, prev, { pct = false, goodWhenUp = true } = {}) {
  if (prev == null) return null;
  const diff = pct ? (prev ? ((cur - prev) / prev) * 100 : null) : cur - prev;
  if (diff == null) return null;
  const r = Math.round(diff * 10) / 10;
  return { text: `${r > 0 ? "+" : ""}${r}${pct ? "%" : " pts"}`, tone: r === 0 ? "flat" : r > 0 === goodWhenUp ? "good" : "bad" };
}

function Kpi({ label, value, delta }) {
  return (
    <div className="kpi">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {delta ? <span className={`delta ${delta.tone}`}>{delta.text} <span className="muted">vs previous period</span></span>
             : <span className="delta flat">&nbsp;</span>}
    </div>
  );
}

function DailyChart({ daily }) {
  const W = 720, H = 220, pad = { l: 40, r: 8, t: 10, b: 26 };
  const max = Math.max(1, ...daily.map((d) => d.total));
  const step = max <= 10 ? 5 : max <= 50 ? 10 : max <= 200 ? 50 : 100;
  const top = Math.ceil(max / step) * step;
  const bw = (W - pad.l - pad.r) / daily.length;
  const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / top);
  const every = Math.ceil(daily.length / 6);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Appointments per day, with no-shows highlighted">
      {[0, top / 2, top].map((t) => (
        <g key={t}><line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="grid" />
          <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" className="axis">{t}</text></g>
      ))}
      {daily.map((d, i) => {
        const x = pad.l + i * bw + bw * 0.15, w = bw * 0.7;
        return (
          <g key={d.day}>
            <rect x={x} y={y(d.total)} width={w} height={y(0) - y(d.total)} rx="2" className="bar-total">
              <title>{`${short(d.day)}: ${d.total} appointments, ${d.no_show} no-shows`}</title>
            </rect>
            <rect x={x} y={y(d.no_show)} width={w} height={y(0) - y(d.no_show)} rx="2" className="bar-noshow" />
            {i % every === 0 && <text x={x + w / 2} y={H - 8} textAnchor="middle" className="axis">{short(d.day)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

function Heatmap({ cells }) {
  const days = [1, 2, 3, 4, 5, ...[6, 7].filter((d) => cells.some((c) => c.dow === d))];
  const hours = [...new Set(cells.map((c) => c.hour))].sort((a, b) => a - b);
  const count = new Map(cells.map((c) => [`${c.dow}-${c.hour}`, c.n]));
  const max = Math.max(1, ...cells.map((c) => c.n));
  return (
    <div className="heat" style={{ gridTemplateColumns: `52px repeat(${days.length}, 1fr)` }}>
      <span />{days.map((d) => <span key={d} className="heat-h">{DOW[d]}</span>)}
      {hours.map((h) => (
        <Fragment key={h}>
          <span className="heat-h left">{hourLabel(h)}</span>
          {days.map((d) => {
            const n = count.get(`${d}-${h}`) || 0, a = n / max;
            return <span key={d} className="heat-cell" title={`${DOW[d]} ${hourLabel(h)}: ${n} appointments`}
              style={{ background: `rgba(11,122,117,${0.08 + 0.92 * a})`, color: a > 0.55 ? "#fff" : "var(--text)" }}>{n}</span>;
          })}
        </Fragment>
      ))}
    </div>
  );
}

const Meter = ({ value, red }) => (
  <div className={red ? "meter red" : "meter"}><b>{value}%</b><span><i style={{ width: `${Math.min(100, value)}%` }} /></span></div>
);

export default function Dashboard() {
  const [days, setDays] = useState(30);
  const [doctors, setDoctors] = useState([]);
  const [doctorId, setDoctorId] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => { api("/doctors/").then(setDoctors).catch(() => {}); }, []);
  useEffect(() => {
    let live = true;
    setData(null); setError("");
    const to = new Date(), from = new Date();
    from.setDate(to.getDate() - (days - 1));
    const q = new URLSearchParams({ from: iso(from), to: iso(to), ...(doctorId && { doctor: doctorId }) });
    api(`/analytics/overview/?${q}`).then((d) => live && setData(d)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [days, doctorId]);

  const busiest = useMemo(() => {
    if (!data?.heatmap.length) return null;
    const b = data.heatmap.reduce((m, c) => (c.n > m.n ? c : m));
    return `${DOW[b.dow]} ${hourLabel(b.hour)}`;
  }, [data]);

  const cur = data?.kpis.current, prev = data?.kpis.previous;

  return (
    <>
      <header className="page-head">
        <div><h1>Dashboard</h1><p className="muted">How the clinic is running, compared with the period before.</p></div>
        <div className="controls">
          <div className="seg" role="group" aria-label="Time range">
            {RANGES.map(([n, label]) => <button key={n} className={days === n ? "on" : ""} onClick={() => setDays(n)}>{label}</button>)}
          </div>
          <label className="field-inline">Doctor
            <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
              <option value="">All doctors</option>
              {doctors.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
        </div>
      </header>

      {error && <p className="form-error" role="alert">{error}</p>}
      {!data && !error && <p className="muted">Loading figures…</p>}
      {data && cur.total === 0 && <p className="empty-note">No appointments in this period.</p>}
      {data && cur.total > 0 && (
        <>
          {busiest && <p className="headline">Busiest time: <strong>{busiest}</strong>. {cur.total.toLocaleString()} appointments in the last {days} days.</p>}
          <dl className="kpis">
            <Kpi label="Appointments" value={cur.total.toLocaleString()} delta={change(cur.total, prev.total, { pct: true })} />
            <Kpi label="No-show rate" value={`${cur.no_show_rate}%`} delta={change(cur.no_show_rate, prev.no_show_rate, { goodWhenUp: false })} />
            <Kpi label="Cancellation rate" value={`${cur.cancel_rate}%`} delta={change(cur.cancel_rate, prev.cancel_rate, { goodWhenUp: false })} />
            <Kpi label="Slot utilization" value={`${cur.utilization}%`} />
          </dl>

          <div className="dash-grid">
            <section className="panel">
              <h3>Appointments per day</h3>
              <span className="muted">Darker part of each bar = no-shows.</span>
              <DailyChart daily={data.daily} />
              <div className="legend"><span><i style={{ background: "#8fcbc6" }} />Appointments</span><span><i style={{ background: "#c4554f" }} />No-shows</span></div>
            </section>
            <section className="panel">
              <h3>When patients come in</h3>
              <span className="muted">Appointments by weekday and hour, cancelled ones excluded.</span>
              <Heatmap cells={data.heatmap} />
            </section>
          </div>

          <section className="panel">
            <h3>By doctor</h3>
            <span className="muted">Utilization is booked slots out of weekday capacity.</span>
            <div className="table-wrap flat">
              <table>
                <thead><tr><th>Doctor</th><th>Appointments</th><th>Utilization</th><th>No-show rate</th></tr></thead>
                <tbody>{data.doctors.map((d) => (
                  <tr key={d.doctor}>
                    <td><strong>{d.doctor}</strong></td><td className="num">{d.total.toLocaleString()}</td>
                    <td><Meter value={d.utilization} /></td><td><Meter value={d.no_show_rate} red /></td>
                  </tr>))}</tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
