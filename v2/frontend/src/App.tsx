import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/layout/AppShell";
import { Spinner, ToastProvider } from "./components/ds";
import { AuditLogPage } from "./pages/admin/AuditLogPage";
import { SettingsPage } from "./pages/admin/SettingsPage";
import { UsersPage } from "./pages/admin/UsersPage";
import { LoginPage } from "./pages/LoginPage";
import { ReportsPage } from "./pages/reports/ReportsPage";
import { EmployeeDetailPage } from "./pages/employees/EmployeeDetailPage";
import { EmployeeFormPage } from "./pages/employees/EmployeeFormPage";
import { EmployeesPage } from "./pages/employees/EmployeesPage";
import { ImportPage } from "./pages/employees/ImportPage";
import { PayrollRunDetailPage } from "./pages/payroll/PayrollRunDetailPage";
import { PayrollRunsPage } from "./pages/payroll/PayrollRunsPage";
import { PayslipViewPage } from "./pages/payslips/PayslipViewPage";
import { PayslipsPage } from "./pages/payslips/PayslipsPage";

// Chart pages are code-split so the charting library is only downloaded when they are opened.
const DashboardPage = lazy(() => import("./pages/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const AnalyticsPage = lazy(() => import("./pages/analytics/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })));
const Fallback = <div className="state"><Spinner /></div>;

/** Friendly page for URLs the signed-in role cannot use. (The server rejects the API calls regardless.) */
function Guard({ perm, children }: { perm: string; children: ReactNode }) {
  const { can } = useAuth();
  if (!can(perm)) return <div className="panel"><div className="state"><h3>You do not have access to this page</h3><p>Your role does not include this function. Ask an administrator if you need it.</p></div></div>;
  return <>{children}</>;
}

function Protected() {
  const { status } = useAuth(); const loc = useLocation();
  if (status === "loading") return <div className="state" style={{ marginTop: 80 }}><Spinner /></div>;
  if (status === "anon") return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  return <AppShell />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Suspense fallback={Fallback}><DashboardPage /></Suspense>} />
        <Route path="/analytics" element={<Suspense fallback={Fallback}><AnalyticsPage /></Suspense>} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/employees" element={<EmployeesPage />} />
        <Route path="/employees/new" element={<EmployeeFormPage mode="create" />} />
        <Route path="/employees/import" element={<ImportPage />} />
        <Route path="/employees/:id" element={<EmployeeDetailPage />} />
        <Route path="/employees/:id/edit" element={<EmployeeFormPage mode="edit" />} />
        <Route path="/payroll-runs" element={<PayrollRunsPage />} />
        <Route path="/payroll-runs/:id" element={<PayrollRunDetailPage />} />
        <Route path="/payslips" element={<PayslipsPage />} />
        <Route path="/payslips/:employeeId/:runId" element={<PayslipViewPage />} />
        <Route path="/audit-log" element={<Guard perm="audit:read"><AuditLogPage /></Guard>} />
        <Route path="/users" element={<Guard perm="users:manage"><UsersPage /></Guard>} />
        <Route path="/settings" element={<Guard perm="settings:read"><SettingsPage /></Guard>} />
        <Route path="*" element={<div className="state"><h3>Page not found</h3></div>} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return <BrowserRouter><AuthProvider><ToastProvider><AppRoutes /></ToastProvider></AuthProvider></BrowserRouter>;
}
