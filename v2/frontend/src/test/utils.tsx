import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { ToastProvider } from "../components/ds";
import type { Employee, Flag, RunDetail, RunItem, User } from "../api/types";

export interface Req { method: string; path: string; params: URLSearchParams; body: unknown; form?: FormData; headers: Record<string, string> }
export type Handler = (r: Req) => { status?: number; json?: unknown } | undefined;

export const VIEWER_PERMS = ["employees:read", "payroll:read", "analytics:read", "payslips:read"];
export const HR_PERMS = [...VIEWER_PERMS, "employees:write", "employees:import", "payroll:run", "reports:export"];
export const user = (role: string, permissions: string[]): User => ({ id: 1, username: role, full_name: `Test ${role}`, role, permissions });
export const hrUser = user("hr_editor", HR_PERMS);
export const viewerUser = user("viewer", VIEWER_PERMS);

export const emp = (o: Partial<Employee> = {}): Employee => ({
  id: 1, employee_code: "E001", name: "Priya Sharma", department: "Engineering", designation: "Developer", joining_date: "2023-04-03",
  status: "active", basic_salary: "50000.00", bonus: "5000.00", deductions: "2500.50", overtime_hours: "10.00", attendance_days: 22,
  is_sample: false, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", ...o,
});
export const pageOf = <T,>(items: T[], total = items.length, page = 1, page_size = 25) => ({ items, total, page, page_size });

/** Installs a fetch mock. /auth/me answers with `me` (or 401 when null). Returns the call log. */
export function mockApi(me: User | null, handler: Handler, delayMs = 0) {
  const calls: Req[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const u = new URL(String(input), "http://test");
    const req: Req = {
      method: init?.method ?? "GET", path: u.pathname.replace(/^\/api/, ""), params: u.searchParams,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined, form: init?.body instanceof FormData ? init.body : undefined,
      headers: (init?.headers as Record<string, string>) ?? {},
    };
    calls.push(req);
    if (delayMs && req.path !== "/auth/me") await new Promise((r) => setTimeout(r, delayMs));
    let out: ReturnType<Handler>;
    if (req.path === "/auth/me") out = me ? { json: me } : { status: 401, json: { error: { code: "unauthenticated", message: "Not authenticated" } } };
    else out = handler(req);
    const { status = 200, json } = out ?? { status: 500, json: { error: { code: "unmocked", message: `unmocked ${req.method} ${req.path}` } } };
    return new Response(status === 204 ? null : JSON.stringify(json), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

export function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><ToastProvider><AppRoutes /></ToastProvider></AuthProvider></MemoryRouter>);
}
export const err = (status: number, code: string, message: string, details?: { field: string; message: string }[]) =>
  ({ status, json: { error: { code, message, ...(details ? { details } : {}) } } });

export const APPROVER_PERMS = [...VIEWER_PERMS, "payroll:run", "payroll:review", "payroll:finalize", "payroll:reverse", "reports:export"];
export const approverUser = user("payroll_approver", APPROVER_PERMS);

export const item = (o: Partial<RunItem> = {}): RunItem => ({
  id: 11, employee_id: 1, employee_code: "E001", employee_name: "Priya Sharma", department: "Engineering", designation: "Developer",
  basic_salary: "50000.00", bonus: "5000.00", overtime_hours: "10.00", overtime_rate: "200.00", overtime_pay: "2000.00",
  gross_salary: "57000.00", deductions: "2000.00", net_salary: "55000.00", attendance_days: 22, flags: [], ...o,
});
export const negFlag: Flag = { code: "negative_net", severity: "error", message: "Net pay is negative (-33000.00): deductions exceed gross pay." };
export const otFlag: Flag = { code: "high_overtime", severity: "warning", message: "Overtime of 50.00 h exceeds the review threshold of 40 h." };

export const run = (o: Partial<RunDetail> = {}): RunDetail => ({
  id: 5, period: "2026-09", status: "draft", is_sample: false, overtime_rate: "200.00", employee_count: 1, total_gross: "57000.00",
  total_deductions: "2000.00", total_net: "55000.00", error_flag_items: 0, warning_flag_items: 0, created_at: "2026-10-01T09:00:00Z",
  reviewed_at: null, finalized_at: null, reversed_at: null, reversal_reason: null, totals_source: "live", items: [item()], ...o,
});

import type { AnalyticsSummary, DashboardSummary } from "../api/types";
export const dash = (o: Partial<DashboardSummary> = {}): DashboardSummary => ({
  active_employees: 12, inactive_employees: 1, sample_employees: 0, available_periods: ["2026-06", "2026-07", "2026-08"], selected_period: "2026-08", has_history: true, run_id: 8,
  employee_count: 11, total_gross: "1250000.00", total_deductions: "100000.50", total_net: "1149999.50", average_net: "104545.41", total_bonus: "50000.00", total_overtime_pay: "12000.00",
  comparison: { period: "2026-07", employee_count: 10, total_net: "1000000.00", net_change: "149999.50", net_change_pct: "15.0", adjacent_month: true },
  departments: [{ department: "Engineering", employees: 7, gross: "900000.00", deductions: "70000.00", net: "830000.00" }, { department: "Finance", employees: 4, gross: "350000.00", deductions: "30000.50", net: "319999.50" }],
  trend: [{ period: "2026-06", employees: 10, gross: "1", deductions: "1", net: "900000.00", bonus: "0", overtime_pay: "0", overtime_hours: "0" },
          { period: "2026-07", employees: 10, gross: "1", deductions: "1", net: "1000000.00", bonus: "0", overtime_pay: "0", overtime_hours: "0" },
          { period: "2026-08", employees: 11, gross: "1250000.00", deductions: "1", net: "1149999.50", bonus: "0", overtime_pay: "0", overtime_hours: "0" }],
  trend_min_periods: 3,
  recent_runs: [{ id: 8, period: "2026-08", status: "finalized", employee_count: 11, total_net: "1149999.50", is_sample: false, created_at: "2026-09-01T09:00:00Z" },
                { id: 9, period: "2026-09", status: "draft", employee_count: 11, total_net: "1100000.00", is_sample: false, created_at: "2026-10-01T09:00:00Z" }],
  attention: [{ kind: "open_run", severity: "error", message: "2026-09 payroll is draft and not finalized. 1 item(s) with error flags.", link: "/payroll-runs/9" }],
  includes_sample_data: false, ...o,
});

export const analytics = (o: Partial<AnalyticsSummary> = {}): AnalyticsSummary => ({
  from_period: null, to_period: null, department: null, available_periods: ["2026-06", "2026-07", "2026-08"], departments: ["Engineering", "Finance"], periods_in_scope: 3, record_count: 30,
  includes_sample_data: false, totals: { gross: "3000000.00", deductions: "251000.00", net: "2750000.00", bonus: "90000.00", overtime_pay: "30000.00", overtime_hours: "150.00" },
  average_net: "91666.67", highest_net: { employee_code: "E009", employee_name: "Vikram Rao", period: "2026-08", net: "250000.00" }, lowest_net: { employee_code: "E031", employee_name: "Low Pay", period: "2026-07", net: "-2000.00" },
  distribution: [{ start: "0.00", end: "50000.00", count: 4 }, { start: "50000.00", end: "100000.00", count: 20 }, { start: "100000.00", end: "150000.00", count: 6 }],
  by_department: [{ department: "Engineering", employees: 20, gross: "2000000.00", deductions: "150000.00", net: "1850000.00" }, { department: "Finance", employees: 10, gross: "1000000.00", deductions: "100000.00", net: "900000.00" }],
  trend: [{ period: "2026-06", employees: 9, gross: "900000.00", deductions: "1", net: "850000.00", bonus: "0", overtime_pay: "0", overtime_hours: "0" }, { period: "2026-07", employees: 10, gross: "1000000.00", deductions: "1", net: "900000.00", bonus: "0", overtime_pay: "0", overtime_hours: "0" },
          { period: "2026-08", employees: 11, gross: "1100000.00", deductions: "1", net: "1000000.00", bonus: "0", overtime_pay: "0", overtime_hours: "0" }],
  changes: [{ period: "2026-07", prior_period: "2026-06", employee_count: 10, employee_count_change: 1, net: "900000.00", net_change: "50000.00", net_change_pct: "5.9" }],
  attendance: { average: "22.4", min: 15, max: 31, records: 30 }, overtime_records: 8, overtime_avg_hours: "18.75",
  overtime_top: [{ employee_code: "A2", employee_name: "Arun Das", period: "2026-08", hours: "45.00", pay: "9000.00" }], overtime_by_department: [{ department: "Engineering", hours: "150.00", pay: "30000.00" }],
  flag_counts: { high_overtime: 3, negative_net: 1 },
  flagged_records: [{ run_id: 8, period: "2026-08", employee_code: "A2", employee_name: "Arun Das", code: "high_overtime", severity: "warning", message: "Overtime of 45.00 h exceeds the review threshold of 40 h." }],
  employee_checks: [{ code: "missing_joining_date", count: 2, message: "Active employees without a joining date" }], thresholds: { high_overtime_hours: "40", unusual_salary_change_pct: "25" }, ...o,
});

export const ADMIN_PERMS = [...new Set([...APPROVER_PERMS, ...HR_PERMS, "audit:read", "settings:read", "settings:write", "users:manage"])];
export const adminUser = { ...user("admin", ADMIN_PERMS), id: 1, username: "admin", full_name: "Test admin" };
