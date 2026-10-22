import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Alert, Button, TextField } from "../components/ds";

export function LoginPage() {
  const { status, login } = useAuth();
  const loc = useLocation() as { state?: { from?: string } };
  const [username, setU] = useState(""); const [password, setP] = useState("");
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  if (status === "authed") return <Navigate to={loc.state?.from ?? "/dashboard"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { await login(username.trim(), password); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Sign-in failed"); }
    finally { setBusy(false); }
  }
  return (
    <div className="login">
      <div className="login__box">
        <h1>Payroll Management</h1>
        <p className="muted" style={{ fontSize: "var(--fs-sm)" }}>Sign in with your account.</p>
        <form className="login__form" onSubmit={submit} noValidate>
          {error && <Alert tone="danger">{error}</Alert>}
          <TextField label="Username" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus required />
          <TextField label="Password" type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required />
          <Button type="submit" variant="primary" disabled={busy || !username || !password}>{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
      </div>
    </div>
  );
}
