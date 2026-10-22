import { Pencil } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { Employee } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, ConfirmDialog, ErrorState, LinkButton, PageHeader, Spinner, useToast } from "../../components/ds";
import { dateOnly, money } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

export function EmployeeDetailPage() {
  const { id } = useParams();
  const { can } = useAuth(); const toast = useToast();
  const q = useQuery((signal) => api<Employee>(`/employees/${id}`, { signal }), [id]);
  const [confirm, setConfirm] = useState(false); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);

  if (q.loading && !q.data) return <div className="state"><Spinner /></div>;
  if (q.error) return <ErrorState message={q.error.status === 404 ? "This employee does not exist." : q.error.message} onRetry={q.error.status === 404 ? undefined : q.reload} />;
  const e = q.data!;
  const active = e.status === "active";

  async function toggle() {
    setBusy(true); setErr(null);
    try {
      await api<Employee>(`/employees/${e.id}/${active ? "deactivate" : "reactivate"}`, { method: "POST" });
      toast(active ? "Employee deactivated" : "Employee reactivated"); setConfirm(false); q.reload();
    } catch (x) { setErr(x instanceof ApiError ? x.message : "Unexpected error"); setConfirm(false); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title={e.name} crumbs={[{ label: "Employees", to: "/employees" }, { label: e.employee_code }]}
        subtitle={<><span className="mono">{e.employee_code}</span> · {e.designation}, {e.department}</>}
        actions={<>
          <Badge tone={active ? "success" : "neutral"}>{active ? "Active" : "Inactive"}</Badge>
          {can("employees:write") && <>
            <LinkButton to={`/employees/${e.id}/edit`}><Pencil size={14} aria-hidden="true" /> Edit</LinkButton>
            <Button variant={active ? "danger" : "default"} onClick={() => setConfirm(true)}>{active ? "Deactivate" : "Reactivate"}</Button></>}
        </>} />
      {err && <Alert tone="danger">{err}</Alert>}
      {e.is_sample && <Alert tone="warning">This is sample data, not a real employee record.</Alert>}
      {!active && <Alert tone="info">Inactive employees are left out of new payroll runs. Their past payroll records are kept.</Alert>}
      <div className="detail-grid">
        <section className="panel"><div className="card-title">Employment</div><div className="card-pad"><dl className="dl">
          <dt>Employee ID</dt><dd className="mono">{e.employee_code}</dd><dt>Name</dt><dd>{e.name}</dd>
          <dt>Department</dt><dd>{e.department}</dd><dt>Designation</dt><dd>{e.designation}</dd>
          <dt>Joining date</dt><dd>{dateOnly(e.joining_date)}</dd><dt>Status</dt><dd>{active ? "Active" : "Inactive"}</dd>
        </dl></div></section>
        <section className="panel"><div className="card-title">Standing payroll inputs</div><div className="card-pad"><dl className="dl">
          <dt>Basic salary</dt><dd className="num">{money(e.basic_salary)}</dd><dt>Bonus</dt><dd className="num">{money(e.bonus)}</dd>
          <dt>Deductions</dt><dd className="num">{money(e.deductions)}</dd><dt>Overtime hours</dt><dd className="num">{e.overtime_hours}</dd>
          <dt>Attendance</dt><dd className="num">{e.attendance_days} days</dd>
        </dl><p className="field__hint" style={{ marginTop: 12 }}>These are defaults for new payroll runs. Pay actually issued comes from finalized runs.</p></div></section>
      </div>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} busy={busy} tone={active ? "danger" : "primary"}
        title={active ? `Deactivate ${e.name}?` : `Reactivate ${e.name}?`} confirmLabel={active ? "Deactivate" : "Reactivate"} onConfirm={() => void toggle()}
        description={active ? "They will be excluded from new payroll runs. The record and all historical payroll data are kept, and you can reactivate at any time."
          : "They will be included in new payroll runs again."} />
    </>
  );
}
