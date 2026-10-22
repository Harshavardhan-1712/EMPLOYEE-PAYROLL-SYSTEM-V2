import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { createContext, useCallback, useContext, useId, useState, type ButtonHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type InputHTMLAttributes } from "react";
import { Link } from "react-router-dom";

/* ---- Button ---- */
type Variant = "default" | "primary" | "danger" | "ghost";
export function Button({ variant = "default", size, className = "", type = "button", ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" }) {
  const cls = ["btn", variant !== "default" && `btn--${variant}`, size && `btn--${size}`, className].filter(Boolean).join(" ");
  return <button type={type} className={cls} {...p} />;
}
export function LinkButton({ to, variant = "default", children }: { to: string; variant?: Variant; children: ReactNode }) {
  return <Link to={to} className={`btn${variant !== "default" ? ` btn--${variant}` : ""}`}>{children}</Link>;
}

/* ---- Form field: label + control + hint + error, wired with aria ---- */
interface FieldProps { label: string; required?: boolean; hint?: string; error?: string; className?: string }
export function Field({ label, required, hint, error, className = "", children }: FieldProps & { children: (a: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode }) {
  const id = useId();
  const desc = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  return (
    <div className={`field ${className}`}>
      <label className="field__label" htmlFor={id}>{label}{required && <span className="field__req" aria-hidden="true">*</span>}</label>
      {children({ id, "aria-describedby": desc, "aria-invalid": error ? true : undefined })}
      {error ? <span className="field__error" id={`${id}-err`} role="alert">{error}</span>
        : hint ? <span className="field__hint" id={`${id}-hint`}>{hint}</span> : null}
    </div>
  );
}
export function TextField({ label, required, hint, error, className, numeric, ...input }: FieldProps & { numeric?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  return <Field {...{ label, required, hint, error, className }}>{(a) => <input className={`input${numeric ? " input--num" : ""}`} required={required} {...a} {...input} />}</Field>;
}
export function SelectField({ label, hint, error, className, children, ...sel }: FieldProps & SelectHTMLAttributes<HTMLSelectElement>) {
  return <Field {...{ label, hint, error, className }}>{(a) => <select className="select" {...a} {...sel}>{children}</select>}</Field>;
}

/* ---- Badge ---- */
export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "success" | "warning" | "danger"; children: ReactNode }) {
  return <span className={`badge${tone !== "neutral" ? ` badge--${tone}` : ""}`}>{children}</span>;
}

/* ---- Alerts & states ---- */
const ICON = { danger: AlertTriangle, warning: AlertTriangle, success: CheckCircle2, info: Info } as const;
export function Alert({ tone = "info", children, action }: { tone?: keyof typeof ICON; children: ReactNode; action?: ReactNode }) {
  const Icon = ICON[tone];
  return (
    <div className={`alert alert--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={16} aria-hidden="true" style={{ flex: "none", marginTop: 2 }} />
      <div style={{ flex: 1 }}>{children}</div>{action}
    </div>
  );
}
export const Spinner = ({ label = "Loading" }: { label?: string }) => <span className="spinner" role="status" aria-label={label} />;
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="state"><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>;
}
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="state" role="alert"><h3>Something went wrong</h3><p>{message}</p>{onRetry && <Button onClick={onRetry}>Retry</Button>}</div>;
}

/* ---- Page header + breadcrumbs ---- */
export function PageHeader({ title, subtitle, actions, crumbs }: { title: string; subtitle?: ReactNode; actions?: ReactNode; crumbs?: { label: string; to?: string }[] }) {
  return (
    <>
      {crumbs && <nav className="breadcrumbs" aria-label="Breadcrumb">{crumbs.map((c, i) => (
        <span key={i}>{i > 0 && " / "}{c.to ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}</span>))}</nav>}
      <div className="page-header">
        <div><h1>{title}</h1>{subtitle && <p className="page-header__sub">{subtitle}</p>}</div>
        {actions && <div className="page-header__actions">{actions}</div>}
      </div>
    </>
  );
}

/* ---- Confirm dialog (Radix: focus trap, Esc to close, aria roles) ---- */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, tone = "primary", busy, onConfirm }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description: ReactNode; confirmLabel: string;
  tone?: "primary" | "danger"; busy?: boolean; onConfirm: () => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" aria-describedby="confirm-desc">
          <Dialog.Title asChild><h2>{title}</h2></Dialog.Title>
          <Dialog.Description asChild><p id="confirm-desc">{description}</p></Dialog.Description>
          <div className="form-actions">
            <Button onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
            <Button variant={tone} onClick={onConfirm} disabled={busy}>{busy ? "Working…" : confirmLabel}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ---- Modal for forms (same Radix primitives as ConfirmDialog) ---- */
export function Modal({ open, onOpenChange, title, description, children, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: ReactNode; children: ReactNode; wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog" style={wide ? { width: "min(620px, calc(100vw - 32px))" } : undefined} aria-describedby={description ? "modal-desc" : undefined}>
          <Dialog.Title asChild><h2>{title}</h2></Dialog.Title>
          {description && <Dialog.Description asChild><p id="modal-desc">{description}</p></Dialog.Description>}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export const STATUS_TONE = { draft: "neutral", reviewed: "warning", finalized: "success", reversed: "danger" } as const;
export const STATUS_LABEL = { draft: "Draft", reviewed: "Reviewed", finalized: "Finalized", reversed: "Reversed" } as const;

/* ---- Toasts (polite live region) ---- */
const ToastCtx = createContext<(msg: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string }[]>([]);
  const push = useCallback((msg: string) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, msg }]);
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">{items.map((t) => <div key={t.id} className="toast">{t.msg}</div>)}</div>
    </ToastCtx.Provider>
  );
}
