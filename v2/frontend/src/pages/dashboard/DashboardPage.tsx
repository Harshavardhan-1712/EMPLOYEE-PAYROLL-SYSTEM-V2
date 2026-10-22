import { Link, useSearchParams } from "react-router-dom";
import { api, qs } from "../../api/client";
import type { DashboardSummary } from "../../api/types";
import { Alert, Badge, EmptyState, ErrorState, LinkButton, PageHeader, SelectField, Spinner, STATUS_LABEL, STATUS_TONE } from "../../components/ds";
import { ChartCard, MoneyBars, MoneyLines } from "../../components/charts";
import { dateTime, money, periodLabel } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

export function DashboardPage() {
  const [sp, setSp] = useSearchParams();
  const period = sp.get("period") ?? "";
  const q = useQuery((signal) => api<DashboardSummary>(`/dashboard/summary${qs({ period })}`, { signal }), [period]);
  if (q.loading && !q.data) return <div className="state"><Spinner /></div>;
  if (q.error && !q.data) return <ErrorState message={q.error.message} onRetry={q.reload} />;
  const d = q.data!;
  const periods = [...d.available_periods].reverse();

  return (
    <>
      <PageHeader title="Dashboard" subtitle={d.has_history ? <>Figures for <strong>{periodLabel(d.selected_period!)}</strong>, from the finalized payroll record</> : "Payroll overview"}
        actions={d.has_history && (
          <SelectField label="Payroll period" value={d.selected_period ?? ""} onChange={(e) => setSp(e.target.value ? { period: e.target.value } : {}, { replace: true })}>
            {periods.map((p) => <option key={p} value={p}>{periodLabel(p)}</option>)}
          </SelectField>)} />
      {q.error && <ErrorState message={q.error.message} onRetry={q.reload} />}
      {(d.includes_sample_data || d.sample_employees > 0) && <Alert tone="warning">
        {d.includes_sample_data ? "The selected period was built from sample data: these figures are not real payroll." : `${d.sample_employees} employee record(s) are sample data.`}</Alert>}

      {!d.has_history ? (
        <div className="panel">
          <EmptyState title="No finalized payroll yet" action={<LinkButton to="/payroll-runs" variant="primary">Go to payroll runs</LinkButton>}>
            {d.active_employees} active employee{d.active_employees === 1 ? "" : "s"} on record. Payroll totals, department spend and trends appear here once a payroll run has been finalized.</EmptyState>
          {d.attention.length > 0 && <Attention items={d.attention} />}
        </div>
      ) : (
        <>
          <dl className="summary-strip stat-strip" aria-label={`Totals for ${periodLabel(d.selected_period!)}`}>
            <div><dt>Active employees</dt><dd>{d.active_employees}<small>current headcount</small></dd></div>
            <div><dt>Employees paid</dt><dd>{d.employee_count}<small>in this period</small></dd></div>
            <div><dt>Total gross</dt><dd>{money(d.total_gross)}</dd></div>
            <div><dt>Total deductions</dt><dd>{money(d.total_deductions)}</dd></div>
            <div><dt>Total net</dt><dd className={d.total_net.startsWith("-") ? "neg" : undefined}>{money(d.total_net)}</dd></div>
            <div><dt>Average net</dt><dd>{money(d.average_net)}</dd></div>
          </dl>
          {d.comparison && (
            <p className="delta">Net payroll vs {periodLabel(d.comparison.period)} ({money(d.comparison.total_net)}): <strong>{d.comparison.net_change.startsWith("-") ? "" : "+"}{money(d.comparison.net_change)}</strong>
              {d.comparison.net_change_pct !== null && <> ({d.comparison.net_change.startsWith("-") ? "" : "+"}{d.comparison.net_change_pct}%)</>}
              {!d.comparison.adjacent_month && " — the most recent earlier finalized period, not the adjacent month"}.</p>)}

          <details className="how"><summary>How these figures are calculated</summary><ul>
            <li>Totals sum the saved payroll lines of the finalized run for the selected period; drafts, reviewed and reversed runs are never included.</li>
            <li>Gross = basic + bonus + overtime pay. Net = gross − deductions. Average net = total net ÷ employees paid (rounded to the paisa).</li>
            <li>Active employees is today's headcount from the employee directory, not the period's.</li>
            <li>The comparison appears only when an earlier finalized period exists. No values are estimated or filled in.</li></ul></details>

          <div className="grid-2">
            <ChartCard title="Payroll by department" note={`Net payroll for ${periodLabel(d.selected_period!)}.`}
              table={{ head: ["Department", "Employees", "Gross", "Deductions", "Net"], rows: d.departments.map((x) => [x.department, x.employees, money(x.gross), money(x.deductions), money(x.net)]) , numFrom: 1 }}>
              <MoneyBars label="Net payroll by department" rows={d.departments as never} xKey="department" series={[{ key: "net", label: "Net" }]} />
            </ChartCard>
            <ChartCard title="Monthly payroll trend" note="Gross and net across all finalized periods."
              table={d.trend.length ? { head: ["Period", "Employees", "Gross", "Net"], rows: d.trend.map((t) => [t.period, t.employees, money(t.gross), money(t.net)]) } : undefined}>
              {d.trend.length >= d.trend_min_periods
                ? <MoneyLines label="Monthly gross and net payroll" rows={d.trend as never} xKey="period" series={[{ key: "gross", label: "Gross" }, { key: "net", label: "Net" }]} />
                : <p className="muted" style={{ padding: "24px 0" }}>A trend needs at least {d.trend_min_periods} finalized periods; there {d.trend.length === 1 ? "is" : "are"} {d.trend.length} so far. Nothing is estimated in the meantime.</p>}
            </ChartCard>
          </div>

          <div className="grid-2">
            <section className="panel"><div className="card-title">Recent payroll runs</div>
              <div className="table-wrap"><table className="table"><caption className="sr-only">Recent payroll runs</caption>
                <thead><tr><th scope="col">Period</th><th scope="col">Status</th><th scope="col" className="num">Employees</th><th scope="col" className="num">Net</th><th scope="col">Created</th></tr></thead>
                <tbody>{d.recent_runs.map((r) => (
                  <tr key={r.id}><td><Link to={`/payroll-runs/${r.id}`}>{periodLabel(r.period)}</Link>{r.is_sample && <> <Badge tone="warning">Sample</Badge></>}</td>
                    <td><Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge></td><td className="num">{r.employee_count}</td><td className="num">{money(r.total_net)}</td><td>{dateTime(r.created_at)}</td></tr>))}
                  {d.recent_runs.length === 0 && <tr><td colSpan={5} className="muted">No runs yet.</td></tr>}</tbody></table></div></section>
            <section className="panel"><div className="card-title">Needs review</div>
              {d.attention.length ? <Attention items={d.attention} /> : <p className="card-pad muted">Nothing needs review right now.</p>}</section>
          </div>
        </>)}
    </>
  );
}

function Attention({ items }: { items: DashboardSummary["attention"] }) {
  return (
    <ul className="attention">{items.map((a, i) => (
      <li key={i}><Badge tone={a.severity === "error" ? "danger" : a.severity === "warning" ? "warning" : "neutral"}>{a.severity === "error" ? "Error" : a.severity === "warning" ? "Warning" : "Info"}</Badge>
        <Link to={a.link}>{a.message}</Link></li>))}</ul>
  );
}
