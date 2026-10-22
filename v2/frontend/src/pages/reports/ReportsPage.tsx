import { Download, FileSpreadsheet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, apiUrl, qs } from "../../api/client";
import type { Page, RunSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, ErrorState, PageHeader, SelectField, Spinner } from "../../components/ds";
import { periodLabel } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

export function ReportsPage() {
  const { can } = useAuth();
  const runs = useQuery((signal) => api<Page<RunSummary>>("/payroll-runs?status=finalized&page_size=100", { signal }), []);
  const depts = useQuery((signal) => api<string[]>("/employees/departments", { signal }), []);
  const periods = useQuery((signal) => api<{ available_periods: string[] }>("/analytics/summary", { signal }), []);
  const [runId, setRunId] = useState(""); const [status, setStatus] = useState(""); const [dept, setDept] = useState("");
  const [from, setFrom] = useState(""); const [to, setTo] = useState(""); const [aDept, setADept] = useState("");

  if (!can("reports:export")) return (<><PageHeader title="Reports & exports" /><Alert tone="info">Your role cannot export reports. Ask an HR editor, payroll approver or administrator.</Alert></>);
  if (runs.loading && !runs.data) return <div className="state"><Spinner /></div>;
  if (runs.error) return <ErrorState message={runs.error.message} onRetry={runs.reload} />;
  const finalized = runs.data!.items;                       // API returns newest period first
  const selected = runId || String(finalized[0]?.id ?? "");
  const sel = finalized.find((r) => String(r.id) === selected);

  const dl = (path: string, label: string, icon: "csv" | "xls" = "csv") => (
    <a className="btn" href={apiUrl(path)}>{icon === "xls" ? <FileSpreadsheet size={14} aria-hidden="true" /> : <Download size={14} aria-hidden="true" />} {label}</a>);

  return (
    <>
      <PageHeader title="Reports & exports" subtitle="Files are generated on the server from finalized payroll records. Each export is recorded in the audit log." />
      <section className="form-section" aria-labelledby="r-run">
        <h2 id="r-run">Payroll run reports</h2>
        <span className="field__hint">Available for finalized runs only. Totals are calculated from the exported rows and match the stored run totals.</span>
        {finalized.length === 0 ? <Alert tone="info">No payroll run has been finalized yet. <Link to="/payroll-runs">Go to payroll runs</Link>.</Alert> : (
          <div style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap", marginTop: 12 }}>
            <SelectField label="Payroll run" value={selected} onChange={(e) => setRunId(e.target.value)}>
              {finalized.map((r) => <option key={r.id} value={r.id}>{periodLabel(r.period)} (#{r.id})</option>)}</SelectField>
            <div className="btn-row">
              {dl(`/reports/payroll.csv?run_id=${selected}`, "Payroll register (CSV)")}
              {dl(`/reports/payroll.xlsx?run_id=${selected}`, "Payroll workbook (Excel)", "xls")}
              {dl(`/reports/department.csv?run_id=${selected}`, "Department report (CSV)")}
            </div>
            {sel && <span className="help" style={{ margin: 0 }}>{sel.employee_count} employees</span>}
          </div>)}
        <p className="help" style={{ marginTop: 12 }}>The Excel workbook has a summary sheet, the payroll register with totals, and a department sheet. Individual payslip PDFs are on the <Link to="/payslips">Payslips</Link> page.</p>
      </section>

      <section className="form-section" aria-labelledby="r-emp">
        <h2 id="r-emp">Employee register</h2>
        <span className="field__hint">Current employee directory (not payroll history).</span>
        <div style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap", marginTop: 12 }}>
          <SelectField label="Status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option value="active">Active</option><option value="inactive">Inactive</option></SelectField>
          <SelectField label="Department" value={dept} onChange={(e) => setDept(e.target.value)}><option value="">All departments</option>{depts.data?.map((d) => <option key={d}>{d}</option>)}</SelectField>
          {dl(`/reports/employees.csv${qs({ status, department: dept })}`, "Employee register (CSV)")}
        </div>
      </section>

      <section className="form-section" aria-labelledby="r-an">
        <h2 id="r-an">Analytics data</h2>
        <span className="field__hint">Period × department totals for the selected range (the same data as the Analytics page).</span>
        <div style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap", marginTop: 12 }}>
          <SelectField label="From" value={from} onChange={(e) => setFrom(e.target.value)}><option value="">First period</option>{periods.data?.available_periods.map((p) => <option key={p} value={p}>{periodLabel(p)}</option>)}</SelectField>
          <SelectField label="To" value={to} onChange={(e) => setTo(e.target.value)}><option value="">Latest period</option>{periods.data?.available_periods.map((p) => <option key={p} value={p}>{periodLabel(p)}</option>)}</SelectField>
          <SelectField label="Department" value={aDept} onChange={(e) => setADept(e.target.value)}><option value="">All departments</option>{depts.data?.map((d) => <option key={d}>{d}</option>)}</SelectField>
          {dl(`/reports/analytics.csv${qs({ from, to, department: aDept })}`, "Analytics export (CSV)")}
        </div>
      </section>
      <Alert tone="info">Spreadsheet safety: text that could be read as a formula (starting with = + - @) is prefixed with an apostrophe in every export, so opening a file cannot run anything.</Alert>
    </>
  );
}
