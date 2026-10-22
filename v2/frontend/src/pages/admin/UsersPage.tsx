import { useState, type FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import type { AdminUser } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, ConfirmDialog, ErrorState, Modal, PageHeader, SelectField, Spinner, TextField, useToast } from "../../components/ds";
import { dateTime } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

export const ROLE_LABEL: Record<string, string> = { viewer: "Viewer", hr_editor: "HR editor", payroll_approver: "Payroll approver", admin: "Administrator" };
const ROLE_HELP: Record<string, string> = {
  viewer: "Read-only access to employees, payroll, payslips and analytics.", hr_editor: "Manages employees and creates and adjusts payroll runs; can export. Cannot review or finalize.",
  payroll_approver: "Creates, reviews, finalizes and reverses payroll runs; can export.", admin: "Everything, plus settings, users and the audit log.",
};
const MIN_PASSWORD = 12;

export function UsersPage() {
  const { user: me } = useAuth(); const toast = useToast();
  const q = useQuery((signal) => api<AdminUser[]>("/users", { signal }), []);
  const [modal, setModal] = useState<null | { kind: "create" } | { kind: "edit" | "reset"; u: AdminUser }>(null);
  const [toggle, setToggle] = useState<AdminUser | null>(null); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);

  async function flipActive(u: AdminUser) {
    setBusy(true); setErr(null);
    try { await api(`/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }); toast(u.is_active ? "User deactivated" : "User reactivated"); setToggle(null); q.reload(); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Unexpected error"); setToggle(null); }
    finally { setBusy(false); }
  }

  if (q.loading && !q.data) return <div className="state"><Spinner /></div>;
  if (q.error && !q.data) return <ErrorState message={q.error.message} onRetry={q.reload} />;
  const users = q.data!;
  return (
    <>
      <PageHeader title="Users" subtitle="Who can sign in, and what they can do. Roles are enforced by the server on every request." actions={<Button variant="primary" onClick={() => setModal({ kind: "create" })}>New user</Button>} />
      {err && <Alert tone="danger">{err}</Alert>}
      <div className="panel"><div className="table-wrap"><table className="table"><caption className="sr-only">Users</caption>
        <thead><tr><th scope="col">Username</th><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{users.map((u) => (
          <tr key={u.id}><td className="mono">{u.username}{u.id === me?.id && <> <Badge>You</Badge></>}{u.is_sample && <> <Badge tone="warning">Sample</Badge></>}</td><td>{u.full_name}</td>
            <td>{ROLE_LABEL[u.role] ?? u.role}</td><td><Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</Badge></td><td>{dateTime(u.created_at)}</td>
            <td style={{ whiteSpace: "nowrap" }}>
              <Button size="sm" onClick={() => setModal({ kind: "edit", u })} aria-label={`Edit ${u.username}`}>Edit</Button>{" "}
              <Button size="sm" onClick={() => setModal({ kind: "reset", u })} aria-label={`Reset password for ${u.username}`}>Reset password</Button>{" "}
              {u.id !== me?.id && <Button size="sm" variant={u.is_active ? "danger" : "default"} onClick={() => setToggle(u)} aria-label={`${u.is_active ? "Deactivate" : "Reactivate"} ${u.username}`}>{u.is_active ? "Deactivate" : "Reactivate"}</Button>}</td></tr>))}</tbody></table></div></div>
      {modal?.kind === "create" && <CreateModal onClose={() => setModal(null)} onDone={() => { setModal(null); toast("User created"); q.reload(); }} />}
      {modal?.kind === "edit" && <EditModal u={modal.u} self={modal.u.id === me?.id} onClose={() => setModal(null)} onDone={() => { setModal(null); toast("User updated"); q.reload(); }} />}
      {modal?.kind === "reset" && <ResetModal u={modal.u} onClose={() => setModal(null)} onDone={() => { setModal(null); toast("Password reset. The user was signed out everywhere."); }} />}
      <ConfirmDialog open={!!toggle} onOpenChange={(o) => !o && setToggle(null)} busy={busy} tone={toggle?.is_active ? "danger" : "primary"} confirmLabel={toggle?.is_active ? "Deactivate" : "Reactivate"}
        title={toggle?.is_active ? `Deactivate ${toggle?.username}?` : `Reactivate ${toggle?.username}?`} onConfirm={() => toggle && void flipActive(toggle)}
        description={toggle?.is_active ? "They are signed out immediately and cannot sign in. Their history stays in the audit log." : "They will be able to sign in again with their current password."} />
    </>
  );
}

function useSubmit(done: () => void) {
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null); const [fe, setFe] = useState<Record<string, string>>({});
  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setErr(null); setFe({});
    try { await fn(); done(); }
    catch (x) { if (x instanceof ApiError) { const m: Record<string, string> = {}; x.details.forEach((d) => (m[d.field] = d.message)); setFe(m); setErr(x.details.length ? "The server rejected some values." : x.message); } else setErr("Unexpected error"); }
    finally { setBusy(false); }
  }
  return { busy, err, fe, setFe, run };
}

function CreateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [v, setV] = useState({ username: "", full_name: "", role: "viewer", password: "" });
  const s = useSubmit(onDone);
  function submit(e: FormEvent) {
    e.preventDefault();
    const f: Record<string, string> = {};
    if (!/^[A-Za-z0-9._-]{3,64}$/.test(v.username.trim())) f.username = "3–64 characters: letters, numbers, . _ -";
    if (!v.full_name.trim()) f.full_name = "Required";
    if (v.password.length < MIN_PASSWORD) f.password = `At least ${MIN_PASSWORD} characters`;
    s.setFe(f); if (Object.keys(f).length) return;
    void s.run(() => api("/users", { method: "POST", body: { ...v, username: v.username.trim(), full_name: v.full_name.trim() } }));
  }
  return (
    <Modal open onOpenChange={(o) => !s.busy && !o && onClose()} title="New user" description="Share the initial password through a secure channel; the user can change it after signing in.">
      <form onSubmit={submit} noValidate style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {s.err && <Alert tone="danger">{s.err}</Alert>}
        <TextField label="Username" required value={v.username} onChange={(e) => setV({ ...v, username: e.target.value })} error={s.fe.username} autoComplete="off" />
        <TextField label="Full name" required value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} error={s.fe.full_name} />
        <SelectField label="Role" value={v.role} onChange={(e) => setV({ ...v, role: e.target.value })} hint={ROLE_HELP[v.role]} error={s.fe.role}>
          {Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</SelectField>
        <TextField label="Initial password" type="password" required value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} error={s.fe.password} autoComplete="new-password" hint={`At least ${MIN_PASSWORD} characters`} />
        <div className="form-actions"><Button onClick={onClose} disabled={s.busy}>Cancel</Button><Button type="submit" variant="primary" disabled={s.busy}>{s.busy ? "Creating…" : "Create user"}</Button></div>
      </form>
    </Modal>
  );
}

function EditModal({ u, self, onClose, onDone }: { u: AdminUser; self: boolean; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState(u.full_name); const [role, setRole] = useState(u.role);
  const s = useSubmit(onDone);
  function submit(e: FormEvent) {
    e.preventDefault();
    const body: Record<string, string> = {};
    if (name.trim() !== u.full_name) body.full_name = name.trim();
    if (role !== u.role) body.role = role;
    if (!name.trim()) { s.setFe({ full_name: "Required" }); return; }
    if (!Object.keys(body).length) { onClose(); return; }
    void s.run(() => api(`/users/${u.id}`, { method: "PATCH", body }));
  }
  return (
    <Modal open onOpenChange={(o) => !s.busy && !o && onClose()} title={`Edit ${u.username}`} description={self ? "You cannot change your own role. Ask another administrator." : "Role changes apply on the user's next request."}>
      <form onSubmit={submit} noValidate style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {s.err && <Alert tone="danger">{s.err}</Alert>}
        <TextField label="Full name" required value={name} onChange={(e) => setName(e.target.value)} error={s.fe.full_name} />
        <SelectField label="Role" value={role} onChange={(e) => setRole(e.target.value)} disabled={self} hint={ROLE_HELP[role]}>{Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</SelectField>
        <div className="form-actions"><Button onClick={onClose} disabled={s.busy}>Cancel</Button><Button type="submit" variant="primary" disabled={s.busy}>{s.busy ? "Saving…" : "Save"}</Button></div>
      </form>
    </Modal>
  );
}

function ResetModal({ u, onClose, onDone }: { u: AdminUser; onClose: () => void; onDone: () => void }) {
  const [pw, setPw] = useState(""); const s = useSubmit(onDone);
  function submit(e: FormEvent) { e.preventDefault(); if (pw.length < MIN_PASSWORD) { s.setFe({ password: `At least ${MIN_PASSWORD} characters` }); return; } void s.run(() => api(`/users/${u.id}/reset-password`, { method: "POST", body: { password: pw } })); }
  return (
    <Modal open onOpenChange={(o) => !s.busy && !o && onClose()} title={`Reset password for ${u.username}`} description="They are signed out of every device immediately. Share the new password through a secure channel.">
      <form onSubmit={submit} noValidate style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {s.err && <Alert tone="danger">{s.err}</Alert>}
        <TextField label="New password" type="password" required value={pw} onChange={(e) => setPw(e.target.value)} error={s.fe.password} autoComplete="new-password" hint={`At least ${MIN_PASSWORD} characters`} />
        <div className="form-actions"><Button onClick={onClose} disabled={s.busy}>Cancel</Button><Button type="submit" variant="danger" disabled={s.busy}>{s.busy ? "Resetting…" : "Reset password"}</Button></div>
      </form>
    </Modal>
  );
}
