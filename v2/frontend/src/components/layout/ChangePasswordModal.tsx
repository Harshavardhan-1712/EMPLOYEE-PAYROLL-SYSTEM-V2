import { useState, type FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { Alert, Button, Modal, TextField, useToast } from "../ds";

export const MIN_PASSWORD = 12;

export function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [cur, setCur] = useState(""); const [next, setNext] = useState(""); const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const [fe, setFe] = useState<{ next?: string; again?: string }>({});

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null);
    const f: typeof fe = {};
    if (next.length < MIN_PASSWORD) f.next = `Use at least ${MIN_PASSWORD} characters`;
    else if (next === cur) f.next = "The new password must differ from the current one";
    if (again !== next) f.again = "The passwords do not match";
    setFe(f); if (f.next || f.again) return;
    setBusy(true);
    try { await api("/auth/change-password", { method: "POST", body: { current_password: cur, new_password: next } }); toast("Password changed. Other sessions were signed out."); onClose(); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Unexpected error"); }
    finally { setBusy(false); }
  }
  return (
    <Modal open onOpenChange={(o) => !busy && !o && onClose()} title="Change password" description="Changing your password signs you out of every other device.">
      <form onSubmit={submit} noValidate style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {err && <Alert tone="danger">{err}</Alert>}
        <TextField label="Current password" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required />
        <TextField label="New password" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} error={fe.next} hint={`At least ${MIN_PASSWORD} characters`} required />
        <TextField label="Repeat new password" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} error={fe.again} required />
        <div className="form-actions"><Button onClick={onClose} disabled={busy}>Cancel</Button><Button type="submit" variant="primary" disabled={busy || !cur}>{busy ? "Saving…" : "Change password"}</Button></div>
      </form>
    </Modal>
  );
}
