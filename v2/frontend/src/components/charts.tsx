import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money } from "../lib/format";

// Restrained palette: navy first, then neutral slates. No decorative gradients.
export const SERIES_COLORS = ["#1f3a5f", "#7a8aa3", "#b0aa9e", "#4d5b6e"];
const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const axisMoney = (v: number) => `₹${compact.format(v)}`;

export interface Series { key: string; label: string }
type Row = Record<string, string | number>;

function MoneyTooltip({ active, payload, label, asMoney }: { active?: boolean; payload?: { name?: string; value?: number | string; color?: string }[]; label?: string | number; asMoney: boolean }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip" role="tooltip">
      <div className="chart-tip__title">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="chart-tip__row"><span className="chart-tip__swatch" style={{ background: p.color }} aria-hidden="true" />{p.name}: <strong>{asMoney ? money(String(p.value)) : p.value}</strong></div>))}
    </div>
  );
}

/** Values arrive as decimal strings; they are converted to numbers for plotting only. */
const plot = (rows: Row[], series: Series[]): Row[] => rows.map((r) => ({ ...r, ...Object.fromEntries(series.map((s) => [s.key, Number(r[s.key])])) }));

export function MoneyBars({ rows, xKey, series, asMoney = true, height = 260, label }: { rows: Row[]; xKey: string; series: Series[]; asMoney?: boolean; height?: number; label: string }) {
  return (
    <div role="img" aria-label={label} style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={plot(rows, series)} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#dedbd5" vertical={false} />
          <XAxis dataKey={xKey} tick={{ fontSize: 12, fill: "#5f636c" }} tickLine={false} axisLine={{ stroke: "#c2beb5" }} />
          <YAxis tick={{ fontSize: 12, fill: "#5f636c" }} tickLine={false} axisLine={false} tickFormatter={asMoney ? axisMoney : undefined} width={asMoney ? 64 : 40} allowDecimals={false} />
          <Tooltip content={<MoneyTooltip asMoney={asMoney} />} cursor={{ fill: "rgba(31,58,95,.06)" }} />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {series.map((s, i) => <Bar key={s.key} dataKey={s.key} name={s.label} fill={SERIES_COLORS[i % SERIES_COLORS.length]} radius={[2, 2, 0, 0]} isAnimationActive={false} />)}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MoneyLines({ rows, xKey, series, height = 260, label }: { rows: Row[]; xKey: string; series: Series[]; height?: number; label: string }) {
  return (
    <div role="img" aria-label={label} style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={plot(rows, series)} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#dedbd5" vertical={false} />
          <XAxis dataKey={xKey} tick={{ fontSize: 12, fill: "#5f636c" }} tickLine={false} axisLine={{ stroke: "#c2beb5" }} />
          <YAxis tick={{ fontSize: 12, fill: "#5f636c" }} tickLine={false} axisLine={false} tickFormatter={axisMoney} width={64} />
          <Tooltip content={<MoneyTooltip asMoney />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {series.map((s, i) => <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={SERIES_COLORS[i % SERIES_COLORS.length]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Chart panel with a built-in text alternative: the same numbers as a table (keyboard / screen-reader friendly). */
export function ChartCard({ title, note, children, table }: { title: string; note?: ReactNode; children: ReactNode; table?: { head: string[]; rows: (string | number)[][]; numFrom?: number } }) {
  return (
    <section className="panel chart-card" aria-label={title}>
      <div className="card-title">{title}</div>
      <div className="card-pad">
        {note && <p className="help">{note}</p>}
        {children}
        {table && (
          <details className="chart-data">
            <summary>View data as a table</summary>
            <div className="table-wrap"><table className="table">
              <caption className="sr-only">{title}</caption>
              <thead><tr>{table.head.map((h, i) => <th key={h} scope="col" className={i >= (table.numFrom ?? 1) ? "num" : undefined}>{h}</th>)}</tr></thead>
              <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={j >= (table.numFrom ?? 1) ? "num" : undefined}>{c}</td>)}</tr>)}</tbody>
            </table></div>
          </details>)}
      </div>
    </section>
  );
}
