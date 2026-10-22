import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { Employee } from "../../api/types";
import { Alert, Button, ErrorState, PageHeader, Spinner, TextField, useToast } from "../../components/ds";
import { changedFields, emptyValues, validateEmployee, type FieldErrors, type FormValues } from "../../lib/validation";
import { useQuery } from "../../lib/useQuery";

const toValues = (e: Employee): FormValues => ({
  employee_code: e.employee_code, name: e.name, department: e.department, designation: e.designation,
  joining_date: e.joining_date ?? "", basic_salary: e.basic_salary, bonus: e.bonus, deductions: e.deductions,
  overtime_hours: e.overtime_hours, attendance_days: String(e.attendance_days),
});

export function EmployeeFormPage({ mode }: { mode: "create" | "edit" }) {
  const { id } = useParams();
  const emp = useQuery((signal) => (mode === "edit" ? api<Employee>(`/employees/${id}`, { signal }) : Promise.resolve(undefined)), [mode, id]);
  const depts = useQuery((signal) => api<string[]>("/employees/departments", { signal }), []);

  if (mode === "edit" && emp.loading && !emp.data) return <div className="state"><Spinner /></div>;
  if (mode === "edit" && emp.error) return <ErrorState message={emp.error.message} onRetry={emp.reload} />;
  return <EmployeeForm key={emp.data?.id ?? "new"} mode={mode} employee={emp.data} departments={depts.data ?? []} />;
}

function EmployeeForm({ mode, employee, departments }: { mode: "create" | "edit"; employee?: Employee; departments: string[] }) {
  const nav = useNavigate(); const toast = useToast();
  const initial = employee ? toValues(employee) : emptyValues();
  const [v, setV] = useState<FormValues>(initial);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof FormValues) => (e: { target: { value: string } }) => setV((s) => ({ ...s, [k]: e.target.value }));
  const field = (k: keyof FormValues) => ({ value: v[k], onChange: set(k), error: errors[k] });

  async function submit(ev: FormEvent) {
    ev.preventDefault(); setBanner(null);
    const errs = validateEmployee(v, mode); setErrors(errs);
    if (Object.keys(errs).length) { setBanner("Fix the highlighted fields and try again."); return; }
    const payload = {
      name: v.name.trim(), department: v.department.trim(), designation: v.designation.trim(),
      joining_date: v.joining_date || null, basic_salary: v.basic_salary.trim(), bonus: v.bonus.trim() || "0",
      deductions: v.deductions.trim() || "0", overtime_hours: v.overtime_hours.trim() || "0", attendance_days: Number(v.attendance_days || 0),
    };
    setBusy(true);
    try {
      if (mode === "create") {
        const created = await api<Employee>("/employees", { method: "POST", body: { employee_code: v.employee_code.trim(), ...payload } });
        toast(`Employee ${created.employee_code} created`); nav(`/employees/${created.id}`);
      } else if (employee) {
        const changed = changedFields(toValues(employee), payload);
        if (!Object.keys(changed).length) { setBanner("No changes to save."); setBusy(false); return; }
        await api<Employee>(`/employees/${employee.id}`, { method: "PATCH", body: changed });
        toast("Employee updated"); nav(`/employees/${employee.id}`);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        const fe: FieldErrors = {};
        for (const d of err.details) fe[d.field as keyof FieldErrors] = d.message;
        if (err.status === 409 && mode === "create") fe.employee_code = err.message;
        setErrors(fe);
        setBanner(Object.keys(fe).length ? "The server rejected some values — see the highlighted fields." : err.message);
      } else setBanner("Unexpected error");
    } finally { setBusy(false); }
  }

  const title = mode === "create" ? "New employee" : `Edit ${employee?.name}`;
  return (
    <form onSubmit={submit} noValidate>
      <PageHeader title={title} crumbs={[{ label: "Employees", to: "/employees" }, ...(employee ? [{ label: employee.name, to: `/employees/${employee.id}` }] : []), { label: mode === "create" ? "New" : "Edit" }]} />
      {banner && <Alert tone="danger">{banner}</Alert>}
      <section className="form-section" aria-labelledby="sec-id">
        <h2 id="sec-id">Identity</h2>
        <div className="form-grid">
          <TextField label="Employee ID" required {...field("employee_code")} disabled={mode === "edit"} className="mono"
            hint={mode === "edit" ? "The ID cannot be changed: payroll history refers to it." : "Letters, numbers, . - _ (unique, not case-sensitive)"} maxLength={32} />
          <TextField label="Full name" required {...field("name")} maxLength={120} />
          <TextField label="Department" required {...field("department")} list="dept-list" maxLength={80} />
          <TextField label="Designation" required {...field("designation")} maxLength={80} />
          <TextField label="Joining date" type="date" {...field("joining_date")} hint="Employees are excluded from periods ending before this date." />
          <datalist id="dept-list">{departments.map((d) => <option key={d} value={d} />)}</datalist>
        </div>
      </section>
      <section className="form-section" aria-labelledby="sec-pay">
        <h2 id="sec-pay">Standing payroll inputs</h2>
        <span className="field__hint">Defaults copied into each new payroll run (₹). They can be adjusted per run before finalizing; finalized runs are never changed.</span>
        <div className="form-grid">
          <TextField label="Basic salary (₹)" required numeric inputMode="decimal" {...field("basic_salary")} />
          <TextField label="Bonus (₹)" numeric inputMode="decimal" {...field("bonus")} />
          <TextField label="Deductions (₹)" numeric inputMode="decimal" {...field("deductions")} hint="Entered amount only. Statutory deductions (PF, ESI, TDS) are not calculated." />
          <TextField label="Overtime hours" numeric inputMode="decimal" {...field("overtime_hours")} hint="Paid at the configured overtime rate." />
          <TextField label="Attendance (days)" numeric inputMode="numeric" {...field("attendance_days")} />
        </div>
      </section>
      <div className="form-actions">
        <Button onClick={() => nav(-1)} disabled={busy}>Cancel</Button>
        <Button type="submit" variant="primary" disabled={busy}>{busy ? "Saving…" : mode === "create" ? "Create employee" : "Save changes"}</Button>
      </div>
    </form>
  );
}
