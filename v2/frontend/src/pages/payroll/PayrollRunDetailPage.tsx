import { Pencil } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { RunDetail, RunItem } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, ConfirmDialog, ErrorState, LinkButton, Modal, PageHeader, Spinner, STATUS_LABEL, STATUS_TONE, TextField, useToast } from "../../components/ds";
import { dateTime, money, periodLabel } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

type Action = null | "review" | "reopen" | "finalize" | "reverse" | "delete";

export function PayrollRunDetailPage() {
  const { id } = useParams();
  const { can } = useAuth(); const toast = useToast(); const nav = useNavigate();
  const q = useQuery((signal) => api<RunDetail>(`/payroll-runs/${id}`, { signal }), [id]);
  const [action, setAction] = useState<Action>(null);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<RunItem | null>(null);

  if (q.loading && !q.data) return <div className="state"><Spinner /></div>;
  if (q.error && !q.data) return <ErrorState message={q.error.status === 404 ? "This payroll run does not exist." : q.error.message} onRetry={q.error.status === 404 ? undefined : q.reload} />;
  const run = q.data!;
  const draft = run.status === "draft", reviewed = run.status === "reviewed", final = run.status === "finalized";
  const flagged = run.items.filter((i) => i.flags.length);

  async function call(path: string, body?: unknown, done?: string) {
    setBusy(true); setErr(null);
    try { await api(`/payroll-runs/${run.id}${path}`, { method: "POST", body }); if (done) toast(done); setAction(null); q.reload(); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Unexpected error"); setAction(null); }
    finally { setBusy(false); }
  }
  async function del() {
    setBusy(true); setErr(null);
    try { await api(`/payroll-runs/${run.id}`, { method: "DELETE" }); toast("Draft run deleted"); nav("/payroll-runs"); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Unexpected error"); setAction(null); setBusy(false); }
  }

  return (
    <>
      <PageHeader title={`Payroll — ${periodLabel(run.period)}`} crumbs={[{ label: "Payroll runs", to: "/payroll-runs" }, { label: `${run.period} (#${run.id})` }]}
        subtitle={<>Overtime rate {money(run.overtime_rate)}/hour · created {dateTime(run.created_at)}</>}
        actions={<>
          <Badge tone={STATUS_TONE[run.status]}>{STATUS_LABEL[run.status]}</Badge>
          {draft && can("payroll:review") && <Button variant="primary" onClick={() => setAction("review")}>Mark as reviewed</Button>}
          {reviewed && can("payroll:review") && <Button onClick={() => setAction("reopen")}>Reopen for edits</Button>}
          {reviewed && can("payroll:finalize") && <Button variant="primary" onClick={() => setAction("finalize")}>Finalize…</Button>}
          {final && <LinkButton to={`/payslips?run_id=${run.id}`}>View payslips</LinkButton>}
          {final && can("payroll:reverse") && <Button variant="danger" onClick={() => setAction("reverse")}>Reverse…</Button>}
          {(draft || reviewed) && can("payroll:run") && <Button variant="ghost" onClick={() => setAction("delete")}>Delete run</Button>}
        </>} />
      {err && <Alert tone="danger">{err}</Alert>}
      {run.is_sample && <Alert tone="warning">This run was built from sample data.</Alert>}
      {run.status === "reversed" && <Alert tone="danger"><strong>Reversed {dateTime(run.reversed_at)}.</strong> Reason: {run.reversal_reason}. The figures below are kept for the record; payslips for this run are no longer valid, and a corrected run can be created for {run.period}.</Alert>}
      {final && <Alert tone="success">Finalized {dateTime(run.finalized_at)}. These figures are a permanent snapshot and cannot be edited. Corrections require an authorized reversal.</Alert>}
      {draft && <Alert tone="info">Draft: nothing is final. Adjust bonus, deductions, overtime or attendance per employee, then mark the run as reviewed.</Alert>}

      <dl className="summary-strip" aria-label="Run totals">
        <div><dt>Employees</dt><dd>{run.employee_count}</dd></div>
        <div><dt>Total gross</dt><dd>{money(run.total_gross)}</dd></div>
        <div><dt>Total deductions</dt><dd>{money(run.total_deductions)}</dd></div>
        <div><dt>Total net</dt><dd className={run.total_net.startsWith("-") ? "neg" : undefined}>{money(run.total_net)}</dd></div>
        <div className="src">{run.totals_source === "snapshot" ? "Recorded at finalization." : "Live totals: they change when items are edited."}
          {" "}Overtime pay = hours × rate. Gross = basic + bonus + overtime pay. Net = gross − deductions. No statutory deductions (PF, ESI, TDS) are calculated.</div>
      </dl>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="table-wrap"><table className="table">
          <caption className="sr-only">Payroll items for {run.period}</caption>
          <thead><tr><th scope="col">ID</th><th scope="col">Employee</th><th scope="col">Department</th><th scope="col" className="num">Basic</th><th scope="col" className="num">Bonus</th>
            <th scope="col" className="num">OT hrs</th><th scope="col" className="num">OT pay</th><th scope="col" className="num">Gross</th><th scope="col" className="num">Deductions</th>
            <th scope="col" className="num">Net</th><th scope="col">Flags</th>{draft && can("payroll:run") && <th scope="col"><span className="sr-only">Actions</span></th>}</tr></thead>
          <tbody>{run.items.map((i) => {
            const errs = i.flags.filter((f) => f.severity === "error").length, warns = i.flags.length - errs;
            return (
              <tr key={i.id}>
                <td className="mono">{i.employee_code}</td><td><Link to={`/employees/${i.employee_id}`}>{i.employee_name}</Link></td><td>{i.department}</td>
                <td className="num">{money(i.basic_salary)}</td><td className="num">{money(i.bonus)}</td><td className="num">{i.overtime_hours}</td><td className="num">{money(i.overtime_pay)}</td>
                <td className="num">{money(i.gross_salary)}</td><td className="num">{money(i.deductions)}</td>
                <td className={`num${i.net_salary.startsWith("-") ? " neg" : ""}`}>{money(i.net_salary)}</td>
                <td>{errs > 0 && <Badge tone="danger">{errs} error</Badge>}{warns > 0 && <> <Badge tone="warning">{warns} warning</Badge></>}{!i.flags.length && <span className="muted">—</span>}</td>
                {draft && can("payroll:run") && <td><Button size="sm" onClick={() => setEditing(i)} aria-label={`Edit ${i.employee_name}`}><Pencil size={12} aria-hidden="true" /> Edit</Button></td>}
              </tr>);
          })}</tbody>
        </table></div>
      </div>

      {flagged.length > 0 && (
        <section className="panel" aria-labelledby="flags-h">
          <div className="card-title" id="flags-h">Items to review ({flagged.length})</div>
          <p className="help card-pad" style={{ paddingBottom: 0 }}>Flags are review indicators based on thresholds an administrator can change. They are prompts for a human check, not findings of error or fraud. Errors must be acknowledged to finalize.</p>
          <ul className="flag-list">{flagged.flatMap((i) => i.flags.map((f) => (
            <li key={`${i.id}-${f.code}`}><Badge tone={f.severity === "error" ? "danger" : "warning"}>{f.severity === "error" ? "Error" : "Warning"}</Badge><strong>{i.employee_name}</strong> <span className="mono muted">{i.employee_code}</span><span>{f.message}</span></li>)))}</ul>
        </section>)}

      {editing && <EditItemModal run={run} item={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); toast("Item updated"); q.reload(); }} />}
      <ConfirmDialog open={action === "review"} onOpenChange={(o) => !o && setAction(null)} busy={busy} title="Mark this run as reviewed?" confirmLabel="Mark as reviewed"
        description="Items become read-only. An authorized approver can then finalize the run, or reopen it for further edits." onConfirm={() => void call("/review", undefined, "Run marked as reviewed")} />
      <ConfirmDialog open={action === "reopen"} onOpenChange={(o) => !o && setAction(null)} busy={busy} title="Reopen this run?" confirmLabel="Reopen"
        description="The run returns to draft so items can be edited again." onConfirm={() => void call("/reopen", undefined, "Run reopened")} />
      <ConfirmDialog open={action === "delete"} onOpenChange={(o) => !o && setAction(null)} busy={busy} tone="danger" title={`Delete the ${run.period} ${run.status} run?`} confirmLabel="Delete run"
        description="The unfinalized calculation is discarded. Nothing has been issued. You can create a new run for this month afterwards." onConfirm={() => void del()} />
      {action === "finalize" && <FinalizeModal run={run} busy={busy} onClose={() => setAction(null)} onConfirm={(ack, note) => void call("/finalize", { acknowledge_errors: ack, note: note || null }, "Run finalized")} />}
      {action === "reverse" && <ReverseModal run={run} busy={busy} onClose={() => setAction(null)} onConfirm={(reason) => void call("/reverse", { reason }, "Run reversed")} />}
    </>
  );
}

function EditItemModal({ run, item, onClose, onSaved }: { run: RunDetail; item: RunItem; onClose: () => void; onSaved: () => void }) {
  const [v, setV] = useState({ bonus: item.bonus, deductions: item.deductions, overtime_hours: item.overtime_hours, attendance_days: String(item.attendance_days) });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null); const [fe, setFe] = useState<Record<string, string>>({});
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV((s) => ({ ...s, [k]: e.target.value }));
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null);
    const money = /^\d{1,7}(\.\d{1,2})?$/, errs: Record<string, string> = {};
    if (!money.test(v.bonus.trim())) errs.bonus = "Enter a non-negative amount (max 2 decimals)";
    if (!money.test(v.deductions.trim())) errs.deductions = "Enter a non-negative amount (max 2 decimals)";
    if (!/^\d{1,3}(\.\d{1,2})?$/.test(v.overtime_hours.trim()) || Number(v.overtime_hours) > 744) errs.overtime_hours = "0–744 hours, max 2 decimals";
    if (!/^\d+$/.test(v.attendance_days.trim()) || Number(v.attendance_days) > 31) errs.attendance_days = "Whole number, 0–31";
    setFe(errs); if (Object.keys(errs).length) return;
    setBusy(true);
    try { await api(`/payroll-runs/${run.id}/items/${item.id}`, { method: "PATCH", body: { bonus: v.bonus.trim(), deductions: v.deductions.trim(), overtime_hours: v.overtime_hours.trim(), attendance_days: Number(v.attendance_days) } }); onSaved(); }
    catch (x) {
      if (x instanceof ApiError) { const m: Record<string, string> = {}; x.details.forEach((d) => (m[d.field] = d.message)); setFe(m); setErr(x.details.length ? "The server rejected some values." : x.message); } else setErr("Unexpected error");
    } finally { setBusy(false); }
  }
  return (
    <Modal open onOpenChange={(o) => !busy && !o && onClose()} title={`Adjust ${item.employee_name}`} wide
      description={`Changes apply to this ${run.period} run only. Basic salary (${money(item.basic_salary)}) comes from the employee record and is not editable here. Net pay and flags are recalculated by the server on save.`}>
      <form onSubmit={submit} noValidate>
        {err && <Alert tone="danger">{err}</Alert>}
        <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <TextField label="Bonus (₹)" numeric inputMode="decimal" value={v.bonus} onChange={set("bonus")} error={fe.bonus} />
          <TextField label="Deductions (₹)" numeric inputMode="decimal" value={v.deductions} onChange={set("deductions")} error={fe.deductions} />
          <TextField label="Overtime hours" numeric inputMode="decimal" value={v.overtime_hours} onChange={set("overtime_hours")} error={fe.overtime_hours} hint={`× ${money(item.overtime_rate)} per hour`} />
          <TextField label="Attendance (days)" numeric inputMode="numeric" value={v.attendance_days} onChange={set("attendance_days")} error={fe.attendance_days} />
        </div>
        <div className="form-actions" style={{ marginTop: 16 }}><Button onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? "Saving…" : "Save and recalculate"}</Button></div>
      </form>
    </Modal>
  );
}

function FinalizeModal({ run, busy, onClose, onConfirm }: { run: RunDetail; busy: boolean; onClose: () => void; onConfirm: (ack: boolean, note: string) => void }) {
  const [ack, setAck] = useState(false); const [note, setNote] = useState("");
  const hasErr = run.error_flag_items > 0;
  return (
    <Modal open onOpenChange={(o) => !busy && !o && onClose()} title={`Finalize ${periodLabel(run.period)} payroll?`} wide
      description={`${run.employee_count} employees · total net ${money(run.total_net)}. This creates a permanent record and makes payslips available. It cannot be edited afterwards; corrections need an authorized, audited reversal.`}>
      {hasErr && <Alert tone="warning">{run.error_flag_items} item(s) have error-level flags (for example negative net pay). Review them before continuing.</Alert>}
      {hasErr && <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I have reviewed the {run.error_flag_items} item(s) with error flags and approve finalizing them as they are.</label>}
      <div className="field"><label className="field__label" htmlFor="fin-note">Note (optional, stored in the audit log)</label>
        <textarea id="fin-note" className="input" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <div className="form-actions" style={{ marginTop: 16 }}><Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="primary" disabled={busy || (hasErr && !ack)} onClick={() => onConfirm(ack, note.trim())}>{busy ? "Finalizing…" : "Finalize run"}</Button></div>
    </Modal>
  );
}

function ReverseModal({ run, busy, onClose, onConfirm }: { run: RunDetail; busy: boolean; onClose: () => void; onConfirm: (reason: string) => void }) {
  const [reason, setReason] = useState("");
  const ok = reason.trim().length >= 10;
  return (
    <Modal open onOpenChange={(o) => !busy && !o && onClose()} title={`Reverse the ${run.period} run?`} wide
      description="The original figures stay on record, its payslips become invalid, and a corrected run can then be created for this month. The reversal is recorded with your name and reason.">
      <div className="field"><label className="field__label" htmlFor="rev-reason">Reason (at least 10 characters)<span className="field__req" aria-hidden="true">*</span></label>
        <textarea id="rev-reason" className="input" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} aria-invalid={reason.length > 0 && !ok} />
        {reason.length > 0 && !ok && <span className="field__error">Please give a fuller reason ({10 - reason.trim().length} more characters).</span>}</div>
      <div className="form-actions" style={{ marginTop: 16 }}><Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="danger" disabled={busy || !ok} onClick={() => onConfirm(reason.trim())}>{busy ? "Reversing…" : "Reverse run"}</Button></div>
    </Modal>
  );
}
