import { Download } from "lucide-react";
import { useParams } from "react-router-dom";
import { api, apiUrl } from "../../api/client";
import type { Payslip } from "../../api/types";
import { Alert, ErrorState, PageHeader, Spinner } from "../../components/ds";
import { dateTime, money } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

export function PayslipViewPage() {
  const { employeeId, runId } = useParams();
  const q = useQuery((signal) => api<Payslip>(`/payslips/${employeeId}/${runId}`, { signal }), [employeeId, runId]);
  if (q.loading && !q.data) return <div className="state"><Spinner /></div>;
  if (q.error) return (
    <>
      <PageHeader title="Payslip" crumbs={[{ label: "Payslips", to: "/payslips" }, { label: "Unavailable" }]} />
      {q.error.status === 409 ? <Alert tone="warning">{q.error.message}</Alert> : <ErrorState message={q.error.message} onRetry={q.error.status === 404 ? undefined : q.reload} />}
    </>);
  const p = q.data!;
  const pdf = `/payslips/${p.employee_id}/${p.run_id}.pdf`;
  return (
    <>
      <PageHeader title={`Payslip — ${p.employee_name}`} crumbs={[{ label: "Payslips", to: "/payslips" }, { label: `${p.employee_code} · ${p.period_label}` }]}
        subtitle={<>{p.period_label} · finalized {dateTime(p.finalized_at)}</>}
        actions={<a className="btn btn--primary" href={apiUrl(`${pdf}?download=true`)}><Download size={14} aria-hidden="true" /> Download PDF</a>} />
      <div className="split">
        <section className="panel"><div className="card-title">Breakdown</div><div className="card-pad"><dl className="dl" style={{ gridTemplateColumns: "1fr auto" }}>
          <dt>Basic salary</dt><dd className="num">{money(p.basic_salary)}</dd><dt>Bonus</dt><dd className="num">{money(p.bonus)}</dd>
          <dt>Overtime ({p.overtime_hours} h × {money(p.overtime_rate)})</dt><dd className="num">{money(p.overtime_pay)}</dd>
          <dt><strong>Gross salary</strong></dt><dd className="num"><strong>{money(p.gross_salary)}</strong></dd>
          <dt>Deductions (as entered)</dt><dd className="num">{money(p.deductions)}</dd>
          <dt><strong>Net salary</strong></dt><dd className={`num${p.net_salary.startsWith("-") ? " neg" : ""}`}><strong>{money(p.net_salary)}</strong></dd>
        </dl><p className="help" style={{ marginTop: 12 }}>Figures are read from the finalized payroll record, not recalculated. Statutory deductions (PF, ESI, TDS) are not calculated by this system.</p></div></section>
        <iframe className="preview-frame" title={`Payslip PDF preview for ${p.employee_name}, ${p.period_label}`} src={apiUrl(pdf)} />
      </div>
    </>
  );
}
