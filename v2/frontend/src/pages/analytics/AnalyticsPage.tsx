import { Download } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api, apiUrl, qs } from "../../api/client";
import type { AnalyticsSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, EmptyState, ErrorState, PageHeader, SelectField, Spinner } from "../../components/ds";
import { ChartCard, MoneyBars, MoneyLines } from "../../components/charts";
import { money, periodLabel } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

const FLAG_LABEL: Record<string, string> = { high_overtime: "High overtime", unusual_salary_change: "Unusual salary change", negative_net: "Negative net pay", attendance_exceeds_period: "Attendance exceeds period", missing_joining_date: "Missing joining date" };

export function AnalyticsPage() {
  const { can } = useAuth();
  const [sp, setSp] = useSearchParams();
  const from = sp.get("from") ?? "", to = sp.get("to") ?? "", department = sp.get("department") ?? "";
  const q = useQuery((signal) => api<AnalyticsSummary>(`/analytics/summary${qs({ from, to, department })}`, { signal }), [from, to, department]);
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); setSp(n, { replace: true }); };

  if (q.loading && !q.data) return <div className="state"><Spinner /></div>;
  if (q.error && !q.data) return <ErrorState message={q.error.message} onRetry={q.reload} />;
  const a = q.data!;
  const filtered = !!(from || to || department);
  const exportHref = apiUrl(`/reports/analytics.csv${qs({ from, to, department })}`);
  const scope = `${from ? periodLabel(from) : "first period"} to ${to ? periodLabel(to) : "latest period"}${department ? `, ${department}` : ""}`;

  return (
    <>
      <PageHeader title="Analytics" subtitle="Computed from finalized payroll records only"
        actions={can("reports:export") && a.record_count > 0 && <a className="btn" href={exportHref}><Download size={14} aria-hidden="true" /> Export filtered data (CSV)</a>} />
      <div className="toolbar" role="group" aria-label="Filters">
        <SelectField label="From" value={from} onChange={(e) => set("from", e.target.value)}><option value="">First period</option>{a.available_periods.map((p) => <option key={p} value={p}>{periodLabel(p)}</option>)}</SelectField>
        <SelectField label="To" value={to} onChange={(e) => set("to", e.target.value)}><option value="">Latest period</option>{a.available_periods.map((p) => <option key={p} value={p}>{periodLabel(p)}</option>)}</SelectField>
        <SelectField label="Department" value={department} onChange={(e) => set("department", e.target.value)}><option value="">All departments</option>{a.departments.map((d) => <option key={d} value={d}>{d}</option>)}</SelectField>
        {filtered && <Button variant="ghost" onClick={() => setSp({}, { replace: true })}>Clear filters</Button>}
      </div>
      {q.error && <ErrorState message={q.error.message} onRetry={q.reload} />}
      {a.includes_sample_data && <Alert tone="warning">The selected data includes sample runs. These are not real payroll figures.</Alert>}

      {a.available_periods.length === 0 ? (
        <div className="panel"><EmptyState title="No finalized payroll yet">Analytics are calculated from finalized payroll runs. <Link to="/payroll-runs">Go to payroll runs</Link>.</EmptyState></div>
      ) : a.record_count === 0 ? (
        <div className="panel"><EmptyState title="No payroll records match these filters" action={<Button onClick={() => setSp({}, { replace: true })}>Clear filters</Button>}>Try a wider period range or another department.</EmptyState></div>
      ) : (
        <>
          <dl className="summary-strip stat-strip" aria-label="Summary statistics">
            <div><dt>Pay records</dt><dd>{a.record_count}<small>{a.periods_in_scope} period{a.periods_in_scope === 1 ? "" : "s"}</small></dd></div>
            <div><dt>Average net</dt><dd>{money(a.average_net)}</dd></div>
            <div><dt>Highest net</dt><dd>{money(a.highest_net?.net)}<small>{a.highest_net?.employee_name}, {a.highest_net && periodLabel(a.highest_net.period)}</small></dd></div>
            <div><dt>Lowest net</dt><dd className={a.lowest_net?.net.startsWith("-") ? "neg" : undefined}>{money(a.lowest_net?.net)}<small>{a.lowest_net?.employee_name}, {a.lowest_net && periodLabel(a.lowest_net.period)}</small></dd></div>
            <div><dt>Total bonus</dt><dd>{money(a.totals.bonus)}</dd></div>
            <div><dt>Total deductions</dt><dd>{money(a.totals.deductions)}</dd></div>
          </dl>
          <p className="help">Scope: {scope}. A "pay record" is one employee in one finalized month.</p>

          <div className="grid-2">
            <ChartCard title="Net salary distribution" note="Number of pay records in each net-salary range."
              table={{ head: ["Range", "Pay records"], rows: a.distribution.map((b) => [`${money(b.start)} – ${money(b.end)}`, b.count]) }}>
              <MoneyBars label="Net salary distribution" asMoney={false} rows={a.distribution.map((b) => ({ range: `${money(b.start).replace(".00", "")}`, count: b.count }))} xKey="range" series={[{ key: "count", label: "Pay records" }]} />
            </ChartCard>
            <ChartCard title="Payroll expenditure by department" table={{ head: ["Department", "Pay records", "Gross", "Deductions", "Net"], rows: a.by_department.map((d) => [d.department, d.employees, money(d.gross), money(d.deductions), money(d.net)]) }}>
              <MoneyBars label="Gross and net by department" rows={a.by_department as never} xKey="department" series={[{ key: "gross", label: "Gross" }, { key: "net", label: "Net" }]} />
            </ChartCard>
          </div>

          <ChartCard title="Monthly payroll" note={a.periods_in_scope < 2 ? "Only one period is in scope, so there is no trend to draw." : undefined}
            table={{ head: ["Period", "Employees", "Gross", "Deductions", "Net", "Bonus", "Overtime pay"], rows: a.trend.map((t) => [t.period, t.employees, money(t.gross), money(t.deductions), money(t.net), money(t.bonus), money(t.overtime_pay)]) }}>
            {a.periods_in_scope >= 2 && <MoneyLines label="Monthly gross and net payroll" rows={a.trend as never} xKey="period" series={[{ key: "gross", label: "Gross" }, { key: "net", label: "Net" }]} />}
          </ChartCard>

          <section className="panel" style={{ margin: "16px 0" }}><div className="card-title">Change over time</div>
            <p className="help card-pad" style={{ paddingBottom: 0 }}>Only compared where the previous calendar month is also finalized in this scope; gaps in history are not bridged.</p>
            {a.changes.length === 0 ? <p className="card-pad muted">No consecutive finalized months in this scope.</p> : (
              <div className="table-wrap"><table className="table"><caption className="sr-only">Change over time</caption>
                <thead><tr><th scope="col">Period</th><th scope="col">Compared with</th><th scope="col" className="num">Employees</th><th scope="col" className="num">Change</th><th scope="col" className="num">Net payroll</th><th scope="col" className="num">Change</th><th scope="col" className="num">%</th></tr></thead>
                <tbody>{a.changes.map((c) => (<tr key={c.period}><td>{periodLabel(c.period)}</td><td>{periodLabel(c.prior_period)}</td><td className="num">{c.employee_count}</td>
                  <td className="num">{c.employee_count_change > 0 ? "+" : ""}{c.employee_count_change}</td><td className="num">{money(c.net)}</td><td className="num">{money(c.net_change)}</td><td className="num">{c.net_change_pct === null ? "—" : `${c.net_change_pct}%`}</td></tr>))}</tbody></table></div>)}</section>

          <div className="grid-2">
            <section className="panel"><div className="card-title">Overtime</div><div className="card-pad">
              <p className="help">{a.overtime_records} pay record{a.overtime_records === 1 ? "" : "s"} with overtime · {a.totals.overtime_hours} hours · {money(a.totals.overtime_pay)}{a.overtime_avg_hours && <> · average {a.overtime_avg_hours} h where worked</>}</p>
              {a.overtime_top.length === 0 ? <p className="muted">No overtime recorded in this scope.</p> : (
                <div className="table-wrap"><table className="table"><caption className="sr-only">Highest overtime records</caption>
                  <thead><tr><th scope="col">Employee</th><th scope="col">Period</th><th scope="col" className="num">Hours</th><th scope="col" className="num">Pay</th></tr></thead>
                  <tbody>{a.overtime_top.map((o, i) => <tr key={i}><td>{o.employee_name} <span className="mono muted">{o.employee_code}</span></td><td>{periodLabel(o.period)}</td><td className="num">{o.hours}</td><td className="num">{money(o.pay)}</td></tr>)}</tbody></table></div>)}
              {a.overtime_by_department.length > 0 && <p className="help" style={{ marginTop: 12 }}>By department: {a.overtime_by_department.map((d) => `${d.department} ${d.hours} h`).join(" · ")}</p>}
            </div></section>
            <section className="panel"><div className="card-title">Attendance</div><div className="card-pad"><dl className="dl">
              <dt>Average days present</dt><dd className="num">{a.attendance.average ?? "—"}</dd><dt>Lowest</dt><dd className="num">{a.attendance.min ?? "—"}</dd>
              <dt>Highest</dt><dd className="num">{a.attendance.max ?? "—"}</dd><dt>Pay records</dt><dd className="num">{a.attendance.records}</dd></dl>
              <p className="help" style={{ marginTop: 12 }}>Attendance is the day count entered for each period. No working-day calendar is defined, so no attendance percentage is shown.</p></div></section>
          </div>

          <section className="panel" aria-labelledby="dq"><div className="card-title" id="dq">Data quality and review flags</div>
            <p className="help card-pad" style={{ paddingBottom: 0 }}>These are review indicators, not proof of an error or of misconduct. Flags show what was raised when each run was calculated. Current thresholds: overtime above {a.thresholds.high_overtime_hours} h; basic salary change above {a.thresholds.unusual_salary_change_pct}% between finalized runs.</p>
            <div className="card-pad" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {Object.keys(a.flag_counts).length === 0 && a.employee_checks.length === 0 && <span className="muted">No flags raised in this scope.</span>}
              {Object.entries(a.flag_counts).map(([code, n]) => <Badge key={code} tone="warning">{FLAG_LABEL[code] ?? code}: {n}</Badge>)}
              {a.employee_checks.map((c) => <Badge key={c.code} tone="warning">{c.message}: {c.count}</Badge>)}
            </div>
            {a.flagged_records.length > 0 && <div className="table-wrap"><table className="table"><caption className="sr-only">Flagged records</caption>
              <thead><tr><th scope="col">Period</th><th scope="col">Employee</th><th scope="col">Severity</th><th scope="col">Explanation</th></tr></thead>
              <tbody>{a.flagged_records.map((f, i) => (<tr key={i}><td><Link to={`/payroll-runs/${f.run_id}`}>{periodLabel(f.period)}</Link></td><td>{f.employee_name} <span className="mono muted">{f.employee_code}</span></td>
                <td><Badge tone={f.severity === "error" ? "danger" : "warning"}>{f.severity === "error" ? "Error" : "Warning"}</Badge></td><td>{f.message}</td></tr>))}</tbody></table></div>}
          </section>
        </>)}
    </>
  );
}
