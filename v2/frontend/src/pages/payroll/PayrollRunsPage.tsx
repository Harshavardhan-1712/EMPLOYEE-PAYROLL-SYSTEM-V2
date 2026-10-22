import { Plus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, qs } from "../../api/client";
import type { Page, RunDetail, RunSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, EmptyState, ErrorState, Modal, PageHeader, SelectField, Spinner, STATUS_LABEL, STATUS_TONE, TextField } from "../../components/ds";
import { dateTime, money, periodLabel } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

const currentMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

export function PayrollRunsPage() {
  const { can } = useAuth();
  const [sp, setSp] = useSearchParams();
  const status = sp.get("status") ?? ""; const page = Number(sp.get("page") ?? 1);
  const list = useQuery((signal) => api<Page<RunSummary>>(`/payroll-runs${qs({ status, page, page_size: 25 })}`, { signal }), [status, page]);
  const [creating, setCreating] = useState(false);
  const data = list.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); if (k !== "page") n.delete("page"); setSp(n, { replace: true }); };

  return (
    <>
      <PageHeader title="Payroll runs" subtitle="One run per month. A finalized run is a permanent record."
        actions={can("payroll:run") && <Button variant="primary" onClick={() => setCreating(true)}><Plus size={14} aria-hidden="true" /> New payroll run</Button>} />
      <div className="toolbar">
        <SelectField label="Status" value={status} onChange={(e) => set("status", e.target.value)}>
          <option value="">All</option><option value="draft">Draft</option><option value="reviewed">Reviewed</option><option value="finalized">Finalized</option><option value="reversed">Reversed</option>
        </SelectField>
      </div>
      <div className="panel">
        {list.error && !data ? <ErrorState message={list.error.message} onRetry={list.reload} /> : (
          <>
            <div className={`table-wrap${list.loading && data ? " is-refreshing" : ""}`}>
              <table className="table" aria-busy={list.loading}>
                <caption className="sr-only">Payroll runs</caption>
                <thead><tr><th scope="col">Period</th><th scope="col">Status</th><th scope="col" className="num">Employees</th><th scope="col" className="num">Gross</th>
                  <th scope="col" className="num">Deductions</th><th scope="col" className="num">Net</th><th scope="col">Review flags</th><th scope="col">Created</th></tr></thead>
                <tbody>
                  {!data && list.loading && Array.from({ length: 4 }, (_, i) => <tr key={i} className="skeleton">{Array.from({ length: 8 }, (_, j) => <td key={j}><span /></td>)}</tr>)}
                  {data?.items.map((r) => (
                    <tr key={r.id}>
                      <td><Link to={`/payroll-runs/${r.id}`}>{periodLabel(r.period)}</Link> <span className="muted mono">#{r.id}</span>{r.is_sample && <> <Badge tone="warning">Sample</Badge></>}</td>
                      <td><Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge></td>
                      <td className="num">{r.employee_count}</td><td className="num">{money(r.total_gross)}</td><td className="num">{money(r.total_deductions)}</td>
                      <td className={`num${r.total_net.startsWith("-") ? " neg" : ""}`}>{money(r.total_net)}</td>
                      <td>{r.error_flag_items ? <Badge tone="danger">{r.error_flag_items} error</Badge> : null}{r.warning_flag_items ? <> <Badge tone="warning">{r.warning_flag_items} warning</Badge></> : null}
                        {!r.error_flag_items && !r.warning_flag_items && <span className="muted">None</span>}</td>
                      <td>{dateTime(r.created_at)}</td>
                    </tr>))}
                </tbody>
              </table>
            </div>
            {!list.loading && data?.total === 0 && (status
              ? <EmptyState title="No runs with this status">Choose another status to see other runs.</EmptyState>
              : <EmptyState title="No payroll runs yet" action={can("payroll:run") ? <Button variant="primary" onClick={() => setCreating(true)}>Create the first run</Button> : undefined}>
                  {can("payroll:run") ? "Create a run for a month to calculate payroll for all active employees." : "An HR editor or payroll approver needs to create the first run."}</EmptyState>)}
            <div className="table-foot">
              <span>{list.loading && data ? <Spinner label="Refreshing" /> : null} {data ? `${data.total} run${data.total === 1 ? "" : "s"}` : ""}</span>
              <div className="pager"><Button size="sm" disabled={page <= 1} onClick={() => set("page", String(page - 1))}>Previous</Button><span>Page {page} of {pages}</span>
                <Button size="sm" disabled={page >= pages} onClick={() => set("page", String(page + 1))}>Next</Button></div>
            </div>
          </>)}
      </div>
      {creating && <NewRunModal onClose={() => setCreating(false)} />}
    </>
  );
}

function NewRunModal({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const max = currentMonth();
  const [period, setPeriod] = useState(max);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<ApiError | null>(null); const [fieldErr, setFieldErr] = useState<string>();
  const idemKey = useMemo(() => crypto.randomUUID(), []);   // a double-click or retry can never create two runs
  const existing = err?.message.match(/run #(\d+)/)?.[1];

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null);
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) { setFieldErr("Choose a month"); return; }
    if (period > max) { setFieldErr("The period cannot be in the future"); return; }
    setFieldErr(undefined); setBusy(true);
    try {
      const run = await api<RunDetail>("/payroll-runs", { method: "POST", body: { period }, headers: { "Idempotency-Key": idemKey } });
      nav(`/payroll-runs/${run.id}`);
    } catch (x) { setErr(x instanceof ApiError ? x : new ApiError(0, "error", "Unexpected error")); }
    finally { setBusy(false); }
  }
  return (
    <Modal open onOpenChange={(o) => !busy && !o && onClose()} title="New payroll run"
      description="Calculates pay for all active employees using their current standing inputs. You can review and adjust each line before finalizing.">
      <form onSubmit={submit} noValidate>
        {err && <Alert tone="danger">{err.message}{existing && <> <Link to={`/payroll-runs/${existing}`}>Open run #{existing}</Link></>}</Alert>}
        <TextField label="Payroll period" type="month" required value={period} max={max} onChange={(e) => setPeriod(e.target.value)} error={fieldErr} hint="Calendar month (YYYY-MM). Future months are not allowed." />
        <div className="form-actions" style={{ marginTop: 16 }}>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={busy}>{busy ? "Calculating…" : "Create draft run"}</Button>
        </div>
      </form>
    </Modal>
  );
}
