import { BarChart3, Download, FileText, KeyRound, LayoutDashboard, LogOut, ScrollText, Settings, ShieldCheck, Users, WalletCards } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Button } from "../ds";
import { ChangePasswordModal } from "./ChangePasswordModal";

const ROLE_LABEL: Record<string, string> = { viewer: "Viewer", hr_editor: "HR editor", payroll_approver: "Payroll approver", admin: "Administrator" };

// Only sections whose functionality exists are listed, and only those the signed-in role may use
// (the server enforces the same permissions on every request).
const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, perm: "analytics:read" },
  { to: "/employees", label: "Employees", icon: Users, perm: "employees:read" },
  { to: "/payroll-runs", label: "Payroll Runs", icon: WalletCards, perm: "payroll:read" },
  { to: "/payslips", label: "Payslips", icon: FileText, perm: "payslips:read" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, perm: "analytics:read" },
  { to: "/reports", label: "Reports & Exports", icon: Download, perm: "reports:export" },
  { to: "/audit-log", label: "Audit Log", icon: ScrollText, perm: "audit:read" },
  { to: "/users", label: "Users", icon: ShieldCheck, perm: "users:manage" },
  { to: "/settings", label: "Settings", icon: Settings, perm: "settings:read" },
];

export function AppShell() {
  const { user, logout, can } = useAuth();
  const [pw, setPw] = useState(false);
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar__brand"><span>Payroll Management</span></div>
        <nav aria-label="Primary">
          {NAV.filter((n) => can(n.perm)).map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className="nav-link" title={label}>
              <Icon size={16} aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <header className="topbar">
        <span className="muted" style={{ fontSize: "var(--fs-sm)" }}>Employee Payroll Management System V2</span>
        <div className="topbar__user">
          <span>{user?.full_name}</span><Badge>{ROLE_LABEL[user?.role ?? ""] ?? user?.role}</Badge>
          <Button size="sm" variant="ghost" onClick={() => setPw(true)} aria-label="Change password"><KeyRound size={14} aria-hidden="true" /> Password</Button>
          <Button size="sm" variant="ghost" onClick={() => void logout()} aria-label="Sign out"><LogOut size={14} aria-hidden="true" /> Sign out</Button>
        </div>
      </header>
      <main className="main" id="main"><div className="page"><Outlet /></div></main>
      {pw && <ChangePasswordModal onClose={() => setPw(false)} />}
    </div>
  );
}
