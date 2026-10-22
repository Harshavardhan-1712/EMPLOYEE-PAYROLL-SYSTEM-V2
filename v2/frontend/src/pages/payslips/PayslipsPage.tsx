import { Download, Eye } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, apiUrl, qs } from "../../api/client";
import type { Page, PayslipRow, RunSummary } from "../../api/types";
import { Button, EmptyState, ErrorState, LinkButton, PageHeader, SelectField, Spinner, TextField } from "../../components/ds";
import { money, periodLabel } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

export function PayslipsPage() {
  const [sp, setSp] = useSearchParams();
  const runId = sp.get("run_id") ?? ""; const q = sp.get("q") ?? ""; const page = Number(sp.get("page") ?? 1);
  const runs = useQuery((signal) => api<Page<RunSummary>>("/payroll-runs?status=finalized&page_size=100", { signal }), []);
  const list = useQuery((signal) => api<Page<PayslipRow>>(`/payslips${qs({ run_id: runId, q, page, page_size: 25 })}`, { signal }), [runId, q, page]);
  const [qInput, setQInput] = useState(q);
  useEffect(() => setQInput(q), [q]);
  useEffect(() => { if (qInput === q) return; const t = setTimeout(() => set({ q: qInput, page: "" }), 300); return () => clearTimeout(t); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [qInput]);
  function set(p: Record<string, string>) { const n = new URLSearchParams(sp); for (const [k, v] of Object.entries(p)) v ? n.set(k, v) : n.delete(k); setSp(n, { replace: true }); }

  const data = list.data; const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const noFinalized = runs.data && runs.data.total === 0;

  return (
    <>
      <PageHeader title="Payslips" subtitle="Generated from finalized payroll records only. The PDF always matches the stored figures." />
      {noFinalized ? (
        <div className="panel"><EmptyState title="No finalized payroll runs yet" action={<LinkButton to="/payroll-runs" variant="primary">Go to payroll runs</LinkButton>}>Payslips appear here once a payroll run has been finalized.</EmptyState></div>
      ) : (
        <>
          <div className="toolbar" role="search">
            <SelectField label="Payroll run" value={runId} onChange={(e) => set({ run_id: e.target.value, page: "" })}>
              <option value="">All finalized runs</option>
              {runs.data?.items.map((r) => <option key={r.id} value={r.id}>{periodLabel(r.period)} (#{r.id})</option>)}
            </SelectField>
            <TextField className="field--grow" label="Search" type="search" placeholder="Name, ID or department" value={qInput} onChange={(e) => setQInput(e.target.value)} />
          </div>
          <div className="panel">
            {list.error && !data ? <ErrorState message={list.error.message} onRetry={list.reload} /> : (
              <>
                <div className={`table-wrap${list.loading && data ? " is-refreshing" : ""}`}>
                  <table className="table" aria-busy={list.loading}>
                    <caption className="sr-only">Payslips</caption>
                    <thead><tr><th scope="col">Period</th><th scope="col">ID</th><th scope="col">Employee</th><th scope="col">Department</th><th scope="col" className="num">Gross</th>
                      <th scope="col" className="num">Deductions</th><th scope="col" className="num">Net</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                    <tbody>
                      {!data && list.loading && Array.from({ length: 5 }, (_, i) => <tr key={i} className="skeleton">{Array.from({ length: 8 }, (_, j) => <td key={j}><span /></td>)}</tr>)}
                      {data?.items.map((r) => (
                        <tr key={`${r.run_id}-${r.employee_id}`}>
                          <td>{periodLabel(r.period)}</td><td className="mono">{r.employee_code}</td><td>{r.employee_name}</td><td>{r.department}</td>
                          <td className="num">{money(r.gross_salary)}</td><td className="num">{money(r.deductions)}</td><td className={`num${r.net_salary.startsWith("-") ? " neg" : ""}`}>{money(r.net_salary)}</td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <Link className="btn btn--sm" to={`/payslips/${r.employee_id}/${r.run_id}`} aria-label={`View payslip for ${r.employee_name}, ${periodLabel(r.period)}`}><Eye size={12} aria-hidden="true" /> View</Link>{" "}
                            <a className="btn btn--sm" href={apiUrl(`/payslips/${r.employee_id}/${r.run_id}.pdf?download=true`)} aria-label={`Download PDF for ${r.employee_name}, ${periodLabel(r.period)}`}><Download size={12} aria-hidden="true" /> PDF</a></td>
                        </tr>))}
                    </tbody>
                  </table>
                </div>
                {!list.loading && data?.total === 0 && <EmptyState title="No payslips match">Try another run or clear the search.</EmptyState>}
                <div className="table-foot"><span>{list.loading && data ? <Spinner label="Refreshing" /> : null} {data ? `${data.total} payslip${data.total === 1 ? "" : "s"}` : ""}</span>
                  <div className="pager"><Button size="sm" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>Previous</Button><span>Page {page} of {pages}</span>
                    <Button size="sm" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>Next</Button></div></div>
              </>)}
          </div>
        </>)}
    </>
  );
}
