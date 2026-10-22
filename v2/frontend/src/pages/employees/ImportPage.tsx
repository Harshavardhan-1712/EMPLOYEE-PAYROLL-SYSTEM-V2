import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, qs } from "../../api/client";
import type { ImportResult } from "../../api/types";
import { Alert, Badge, Button, ConfirmDialog, PageHeader, useToast } from "../../components/ds";

export function ImportPage() {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<ImportResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const [confirm, setConfirm] = useState(false); const [onlyProblems, setOnly] = useState(false);

  async function send(commit: boolean) {
    if (!file) return;
    setBusy(true); setErr(null);
    const form = new FormData(); form.append("file", file);
    try {
      const r = await api<ImportResult>(`/employees/import${qs({ commit: commit ? "true" : "false" })}`, { method: "POST", form });
      setRes(r);
      if (commit) { toast(`${r.imported} employee(s) imported`); setConfirm(false); }
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Unexpected error"); setConfirm(false); if (!commit) setRes(null); }
    finally { setBusy(false); }
  }

  const rows = res?.rows.filter((r) => !onlyProblems || r.status !== "valid") ?? [];
  const tone = (s: string) => (s === "valid" ? "success" : s === "duplicate" ? "warning" : "danger") as "success" | "warning" | "danger";
  const done = res?.committed;

  return (
    <>
      <PageHeader title="Import employees" crumbs={[{ label: "Employees", to: "/employees" }, { label: "Import" }]}
        subtitle="Upload a CSV, review the preview, then confirm. Nothing is saved until you confirm." />
      {err && <Alert tone="danger">{err}</Alert>}
      <section className="form-section">
        <h2>1. Choose a file</h2>
        <span className="field__hint">UTF-8 CSV, up to 1 MB / 5,000 rows. Required columns: <span className="mono">employee_code, name, department, designation, basic_salary</span>.
          Optional: <span className="mono">joining_date, bonus, deductions, overtime_hours, attendance_days</span>. V1 headers <span className="mono">emp_id, overtime, attendance</span> are accepted.
          Existing IDs are skipped, never overwritten.</span>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 12 }}>
          <input ref={fileRef} type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setRes(null); setErr(null); }} />
          <Button variant="primary" disabled={!file || busy || !!done} onClick={() => void send(false)}>{busy && !res ? "Checking…" : "Preview"}</Button>
        </div>
      </section>

      {res && (
        <section className="panel">
          <div className="card-title">{done ? "Import complete" : "2. Review preview"}</div>
          <div className="card-pad" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <Badge tone="success">{res.valid} valid</Badge><Badge tone="warning">{res.duplicates} duplicate</Badge><Badge tone="danger">{res.errors} with errors</Badge>
            <span className="muted">of {res.total_rows} rows</span>
            <label style={{ marginLeft: "auto", fontSize: "var(--fs-sm)" }}><input type="checkbox" checked={onlyProblems} onChange={(e) => setOnly(e.target.checked)} /> Show only rows with problems</label>
          </div>
          {done && <div className="card-pad" style={{ paddingTop: 0 }}><Alert tone="success">{res.imported} employee(s) imported; {res.total_rows - res.imported} row(s) skipped. <Link to="/employees">Go to the directory</Link></Alert></div>}
          <div className="table-wrap"><table className="table">
            <caption className="sr-only">Import preview</caption>
            <thead><tr><th scope="col" className="num">Line</th><th scope="col">Employee ID</th><th scope="col">Name</th><th scope="col">Result</th><th scope="col">Details</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.line}><td className="num">{r.line}</td><td className="mono">{r.employee_code ?? "—"}</td><td>{r.name ?? "—"}</td>
                <td><Badge tone={tone(r.status)}>{r.status === "valid" ? "Valid" : r.status === "duplicate" ? "Duplicate" : "Error"}</Badge></td>
                <td>{r.errors.join("; ") || "—"}</td></tr>))}
              {rows.length === 0 && <tr><td colSpan={5} className="muted">No rows to show.</td></tr>}</tbody>
          </table></div>
          {!done && <div className="table-foot"><span>Rows with errors or duplicates will be skipped.</span>
            <Button variant="primary" disabled={res.valid === 0 || busy} onClick={() => setConfirm(true)}>Import {res.valid} valid row{res.valid === 1 ? "" : "s"}</Button></div>}
        </section>
      )}
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} busy={busy} title={`Import ${res?.valid ?? 0} employees?`} confirmLabel="Import"
        description={`${res?.valid ?? 0} new employee record(s) will be created in one transaction. ${(res?.duplicates ?? 0) + (res?.errors ?? 0)} other row(s) will be skipped.`}
        onConfirm={() => void send(true)} />
    </>
  );
}
