export interface ApiErrorDetail { field: string; message: string }

export interface User { id: number; username: string; full_name: string; role: string; permissions: string[] }

export interface Employee {
  id: number; employee_code: string; name: string; department: string; designation: string;
  joining_date: string | null; status: "active" | "inactive";
  basic_salary: string; bonus: string; deductions: string; overtime_hours: string; attendance_days: number;
  is_sample: boolean; created_at: string; updated_at: string;
}

export interface EmployeeInput {
  employee_code: string; name: string; department: string; designation: string; joining_date: string | null;
  basic_salary: string; bonus: string; deductions: string; overtime_hours: string; attendance_days: number;
}

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export interface ImportRow { line: number; status: "valid" | "duplicate" | "error"; errors: string[]; employee_code: string | null; name: string | null }
export interface ImportResult { committed: boolean; total_rows: number; valid: number; duplicates: number; errors: number; imported: number; rows: ImportRow[] }

export interface Flag { code: string; severity: "error" | "warning"; message: string }
export type RunStatus = "draft" | "reviewed" | "finalized" | "reversed";
export interface RunSummary {
  id: number; period: string; status: RunStatus; is_sample: boolean; overtime_rate: string; employee_count: number;
  total_gross: string; total_deductions: string; total_net: string; error_flag_items: number; warning_flag_items: number;
  created_at: string; reviewed_at: string | null; finalized_at: string | null; reversed_at: string | null; reversal_reason: string | null;
  totals_source: "snapshot" | "live";
}
export interface RunItem {
  id: number; employee_id: number; employee_code: string; employee_name: string; department: string; designation: string;
  basic_salary: string; bonus: string; overtime_hours: string; overtime_rate: string; overtime_pay: string; gross_salary: string;
  deductions: string; net_salary: string; attendance_days: number; flags: Flag[];
}
export interface RunDetail extends RunSummary { items: RunItem[] }
export interface ItemPatch { bonus?: string; deductions?: string; overtime_hours?: string; attendance_days?: number }

export interface PayslipRow {
  run_id: number; employee_id: number; period: string; employee_code: string; employee_name: string; department: string;
  gross_salary: string; deductions: string; net_salary: string;
}
export interface Payslip {
  run_id: number; period: string; period_label: string; employee_id: number; employee_code: string; employee_name: string;
  department: string; designation: string; basic_salary: string; bonus: string; overtime_hours: string; overtime_rate: string;
  overtime_pay: string; gross_salary: string; deductions: string; net_salary: string; attendance_days: number;
  finalized_at: string | null; company_name: string;
}

export interface DeptRow { department: string; employees: number; gross: string; deductions: string; net: string }
export interface TrendPoint { period: string; employees: number; gross: string; deductions: string; net: string; bonus: string; overtime_pay: string; overtime_hours: string }
export interface Comparison { period: string; employee_count: number; total_net: string; net_change: string; net_change_pct: string | null; adjacent_month: boolean }
export interface AttentionItem { kind: string; message: string; severity: "info" | "warning" | "error"; link: string }
export interface RunBrief { id: number; period: string; status: RunStatus; employee_count: number; total_net: string; is_sample: boolean; created_at: string }
export interface DashboardSummary {
  active_employees: number; inactive_employees: number; sample_employees: number; available_periods: string[]; selected_period: string | null;
  has_history: boolean; run_id: number | null; employee_count: number; total_gross: string; total_deductions: string; total_net: string;
  average_net: string | null; total_bonus: string; total_overtime_pay: string; comparison: Comparison | null; departments: DeptRow[]; trend: TrendPoint[];
  trend_min_periods: number; recent_runs: RunBrief[]; attention: AttentionItem[]; includes_sample_data: boolean;
}
export interface Extreme { employee_code: string; employee_name: string; period: string; net: string }
export interface AnalyticsSummary {
  from_period: string | null; to_period: string | null; department: string | null; available_periods: string[]; departments: string[];
  periods_in_scope: number; record_count: number; includes_sample_data: boolean; totals: Record<string, string>; average_net: string | null;
  highest_net: Extreme | null; lowest_net: Extreme | null; distribution: { start: string; end: string; count: number }[]; by_department: DeptRow[];
  trend: TrendPoint[];
  changes: { period: string; prior_period: string; employee_count: number; employee_count_change: number; net: string; net_change: string; net_change_pct: string | null }[];
  attendance: { average: string | null; min: number | null; max: number | null; records: number };
  overtime_records: number; overtime_avg_hours: string | null;
  overtime_top: { employee_code: string; employee_name: string; period: string; hours: string; pay: string }[];
  overtime_by_department: { department: string; hours: string; pay: string }[];
  flag_counts: Record<string, number>;
  flagged_records: { run_id: number; period: string; employee_code: string; employee_name: string; code: string; severity: "error" | "warning"; message: string }[];
  employee_checks: { code: string; count: number; message: string }[]; thresholds: Record<string, string>;
}

export interface PayrollSettings { overtime_rate: string; high_overtime_hours: string; unusual_salary_change_pct: string; require_separate_finalizer: boolean }
export interface AdminUser { id: number; username: string; full_name: string; role: string; is_active: boolean; is_sample: boolean; created_at: string }
export interface AuditEntry { id: number; at: string; actor_username: string | null; action: string; entity_type: string | null; entity_id: string | null; detail: Record<string, unknown> }
