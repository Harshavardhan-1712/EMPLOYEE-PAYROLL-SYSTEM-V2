import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type { PayrollSettings } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, ConfirmDialog, ErrorState, PageHeader, Spinner, TextField, useToast } from "../../components/ds";
import { money } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

const MONEY = /^\d{1,7}(\.\d{1,2})?$/, DEC2 = /^\d{1,4}(\.\d{1,2})?$/;

export function SettingsPage() {
  const q = useQuery((signal) => api<PayrollSettings>("/settings", { signal }), []);
  if (q.loading && !q.data) return <div className="state"><Spinner /></div>;
  if (q.error && !q.data) return <ErrorState message={q.error.message} onRetry={q.reload} />;
  return <SettingsForm key={JSON.stringify(q.data)} initial={q.data!} onSaved={q.reload} />;
}

function SettingsForm({ initial, onSaved }: { initial: PayrollSettings; onSaved: () => void }) {
  const { can } = useAuth(); const toast = useToast();
  const editable = can("settings:write");
  const [v, setV] = useState({ overtime_rate: initial.overtime_rate, high_overtime_hours: initial.high_overtime_hours, unusual_salary_change_pct: initial.unusual_salary_change_pct });
  const [sep, setSep] = useState(initial.require_separate_finalizer);
  const [errs, setErrs] = useState<Record<string, string>>({}); const [banner, setBanner] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false); const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV((s) => ({ ...s, [k]: e.target.value }));

  const changed: Record<string, string | boolean> = {};
  (Object.keys(v) as (keyof typeof v)[]).forEach((k) => { if (Number(v[k]) !== Number(initial[k])) changed[k] = v[k].trim(); });
  if (sep !== initial.require_separate_finalizer) changed.require_separate_finalizer = sep;

  function validate() {
    const e: Record<string, string> = {};
    if (!MONEY.test(v.overtime_rate.trim())) e.overtime_rate = "Enter an amount with up to 2 decimals";
    if (!DEC2.test(v.high_overtime_hours.trim()) || Number(v.high_overtime_hours) > 744) e.high_overtime_hours = "0–744 hours, up to 2 decimals";
    if (!DEC2.test(v.unusual_salary_change_pct.trim()) || Number(v.unusual_salary_change_pct) > 1000) e.unusual_salary_change_pct = "0–1000 percent, up to 2 decimals";
    setErrs(e); return Object.keys(e).length === 0;
  }
  function submit(ev: FormEvent) {
    ev.preventDefault(); setBanner(null);
    if (!validate()) return;
    if (!Object.keys(changed).length) { setBanner("No changes to save."); return; }
    if ("overtime_rate" in changed) setConfirm(true); else void save();
  }
  async function save() {
    setBusy(true); setBanner(null);
    try { await api<PayrollSettings>("/settings", { method: "PATCH", body: changed }); toast("Settings saved"); setConfirm(false); onSaved(); }
    catch (x) {
      setConfirm(false);
      if (x instanceof ApiError) { const m: Record<string, string> = {}; x.details.forEach((d) => (m[d.field] = d.message)); setErrs(m); setBanner(x.details.length ? "The server rejected some values." : x.message); } else setBanner("Unexpected error");
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} noValidate>
      <PageHeader title="Settings" subtitle="Payroll configuration. Every change is recorded in the audit log." actions={<Link className="btn" to="/audit-log">View audit log</Link>} />
      {banner && <Alert tone="danger">{banner}</Alert>}
      {!editable && <Alert tone="info">You can view these settings but not change them.</Alert>}
      <section className="form-section" aria-labelledby="s-pay">
        <h2 id="s-pay">Overtime</h2>
        <span className="field__hint">V1 used a fixed rate of ₹200 per hour; it is now configurable.</span>
        <div className="form-grid">
          <TextField label="Overtime rate (₹ per hour)" numeric inputMode="decimal" value={v.overtime_rate} onChange={set("overtime_rate")} error={errs.overtime_rate} disabled={!editable}
            hint="Applies to new payroll runs only. Existing runs, including finalized ones, keep the rate they were calculated with." />
        </div>
      </section>
      <section className="form-section" aria-labelledby="s-flags">
        <h2 id="s-flags">Review flag thresholds</h2>
        <span className="field__hint">These only decide which items are flagged for a human check. They are starting values chosen for this system, not statutory or policy limits.</span>
        <div className="form-grid">
          <TextField label="High overtime above (hours / month)" numeric inputMode="decimal" value={v.high_overtime_hours} onChange={set("high_overtime_hours")} error={errs.high_overtime_hours} disabled={!editable} />
          <TextField label="Unusual basic-salary change above (%)" numeric inputMode="decimal" value={v.unusual_salary_change_pct} onChange={set("unusual_salary_change_pct")} error={errs.unusual_salary_change_pct} disabled={!editable}
            hint="Compared with the employee's last finalized run." />
        </div>
      </section>
      <section className="form-section" aria-labelledby="s-ctl">
        <h2 id="s-ctl">Approval control</h2>
        <label className="check"><input type="checkbox" checked={sep} onChange={(e) => setSep(e.target.checked)} disabled={!editable} />
          <span><strong>Require a different person to finalize.</strong> The user who created a payroll run cannot finalize it, including administrators. Recommended when more than one approver is available.</span></label>
      </section>
      {editable && <div className="form-actions"><Button type="submit" variant="primary" disabled={busy}>{busy ? "Saving…" : "Save settings"}</Button></div>}
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} busy={busy} title="Change the overtime rate?" confirmLabel="Change rate" onConfirm={() => void save()}
        description={`The rate changes from ${money(initial.overtime_rate)} to ${money(String(changed.overtime_rate ?? v.overtime_rate))} per hour for new payroll runs. Runs already created keep their current rate.`} />
    </form>
  );
}
