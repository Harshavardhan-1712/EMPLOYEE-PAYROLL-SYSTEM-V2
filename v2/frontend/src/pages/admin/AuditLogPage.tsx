import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, qs } from "../../api/client";
import type { AuditEntry, Page } from "../../api/types";
import { Badge, Button, EmptyState, ErrorState, PageHeader, SelectField, Spinner, TextField } from "../../components/ds";
import { dateTime } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

const ACTIONS = ["access.denied", "auth.login", "auth.login_failed", "auth.password_changed", "auth.password_change_failed", "employee.created", "employee.updated", "employee.salary_changed",
  "employee.deactivated", "employee.reactivated", "employee.imported", "payroll.run_created", "payroll.item_edited", "payroll.run_reviewed", "payroll.run_reopened", "payroll.run_finalized",
  "payroll.run_reversed", "payroll.run_deleted", "payslip.viewed", "payslip.downloaded", "report.exported", "settings.changed", "user.created", "user.updated", "user.password_reset"];
const SENSITIVE = new Set(["access.denied", "auth.login_failed", "auth.password_change_failed", "payroll.run_reversed", "user.password_reset", "employee.salary_changed", "settings.changed"]);

/** Readable one-line rendering of an event's detail. Paise amounts are shown in rupees (display only). */
export function describe(detail: Record<string, unknown>): string {
  const parts = Object.entries(detail).map(([k, v]) => {
    if (k.endsWith("_paise") && v !== null && v !== "" && !Number.isNaN(Number(v))) return `${k.replace(/_paise$/, "")}: ₹${(Number(v) / 100).toFixed(2)}`;
    if (v !== null && typeof v === "object") return `${k}: ${JSON.stringify(v)}`;
    return `${k}: ${String(v)}`;
  });
  return parts.join("; ") || "—";
}

export function AuditLogPage() {
  const [sp, setSp] = useSearchParams();
  const action = sp.get("action") ?? "", actor = sp.get("actor") ?? "", entityType = sp.get("entity_type") ?? "", page = Number(sp.get("page") ?? 1);
  const [actorInput, setActorInput] = useState(actor);
  useEffect(() => setActorInput(actor), [actor]);
  useEffect(() => { if (actorInput === actor) return; const t = setTimeout(() => set({ actor: actorInput, page: "" }), 400); return () => clearTimeout(t); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [actorInput]);
  function set(p: Record<string, string>) { const n = new URLSearchParams(sp); for (const [k, v] of Object.entries(p)) v ? n.set(k, v) : n.delete(k); setSp(n, { replace: true }); }

  const q = useQuery((signal) => api<Page<AuditEntry>>(`/audit-log${qs({ action, actor, entity_type: entityType, page, page_size: 50 })}`, { signal }), [action, actor, entityType, page]);
  const d = q.data; const pages = d ? Math.max(1, Math.ceil(d.total / d.page_size)) : 1;
  const filtered = !!(action || actor || entityType);

  return (
    <>
      <PageHeader title="Audit log" subtitle="Append-only record of sign-ins, changes, finalizations, reversals, exports and denied actions. Passwords and tokens are never recorded." />
      <div className="toolbar" role="search">
        <SelectField label="Action" value={action} onChange={(e) => set({ action: e.target.value, page: "" })}>
          <option value="">All actions</option>{[...ACTIONS].sort().map((a) => <option key={a} value={a}>{a}</option>)}</SelectField>
        <TextField label="User" type="search" value={actorInput} onChange={(e) => setActorInput(e.target.value)} placeholder="Exact username" />
        <SelectField label="Record type" value={entityType} onChange={(e) => set({ entity_type: e.target.value, page: "" })}>
          <option value="">All</option>{["employee", "payroll_run", "report", "settings", "user"].map((t) => <option key={t} value={t}>{t}</option>)}</SelectField>
        {filtered && <Button variant="ghost" onClick={() => { setActorInput(""); setSp({}, { replace: true }); }}>Clear filters</Button>}
      </div>
      <div className="panel">
        {q.error && !d ? <ErrorState message={q.error.message} onRetry={q.reload} /> : (
          <>
            <div className={`table-wrap${q.loading && d ? " is-refreshing" : ""}`}>
              <table className="table" aria-busy={q.loading}>
                <caption className="sr-only">Audit events, newest first</caption>
                <thead><tr><th scope="col">When</th><th scope="col">User</th><th scope="col">Action</th><th scope="col">Record</th><th scope="col">Details</th></tr></thead>
                <tbody>
                  {!d && q.loading && Array.from({ length: 6 }, (_, i) => <tr key={i} className="skeleton">{Array.from({ length: 5 }, (_, j) => <td key={j}><span /></td>)}</tr>)}
                  {d?.items.map((e) => (
                    <tr key={e.id}>
                      <td style={{ whiteSpace: "nowrap" }}>{dateTime(e.at)}</td><td>{e.actor_username ?? <span className="muted">system</span>}</td>
                      <td><Badge tone={SENSITIVE.has(e.action) ? "warning" : "neutral"}>{e.action}</Badge></td>
                      <td className="mono">{e.entity_type ? `${e.entity_type}${e.entity_id ? ` #${e.entity_id}` : ""}` : "—"}</td><td style={{ maxWidth: 520, overflowWrap: "anywhere" }}>{describe(e.detail)}</td>
                    </tr>))}
                </tbody>
              </table>
            </div>
            {!q.loading && d?.total === 0 && <EmptyState title={filtered ? "No events match these filters" : "No events recorded yet"} />}
            <div className="table-foot"><span>{q.loading && d ? <Spinner label="Refreshing" /> : null} {d ? `${d.total} event${d.total === 1 ? "" : "s"}` : ""}</span>
              <div className="pager"><Button size="sm" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>Previous</Button><span>Page {page} of {pages}</span>
                <Button size="sm" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>Next</Button></div></div>
          </>)}
      </div>
    </>
  );
}
