import type { EmployeeInput } from "../api/types";

export type FormValues = Record<keyof EmployeeInput, string>;
export type FieldErrors = Partial<Record<keyof EmployeeInput, string>>;

const MONEY = /^\d{1,7}(\.\d{1,2})?$/;
const HOURS = /^\d{1,3}(\.\d{1,2})?$/;
const CODE = /^[A-Za-z0-9._-]{1,32}$/;

/** Mirrors the server rules (the server remains the authority and its errors are always shown). */
export function validateEmployee(v: FormValues, mode: "create" | "edit"): FieldErrors {
  const e: FieldErrors = {};
  if (mode === "create") {
    if (!v.employee_code.trim()) e.employee_code = "Employee ID is required";
    else if (!CODE.test(v.employee_code.trim())) e.employee_code = "Use letters, numbers, dot, dash or underscore (max 32)";
  }
  for (const k of ["name", "department", "designation"] as const) {
    if (!v[k].trim()) e[k] = "Required";
    else if (v[k].trim().length > (k === "name" ? 120 : 80)) e[k] = `Too long (max ${k === "name" ? 120 : 80} characters)`;
  }
  if (!v.basic_salary.trim()) e.basic_salary = "Basic salary is required";
  for (const k of ["basic_salary", "bonus", "deductions"] as const) {
    if (v[k].trim() && !MONEY.test(v[k].trim())) e[k] = "Enter a non-negative amount with up to 2 decimals";
  }
  if (v.overtime_hours.trim()) {
    if (!HOURS.test(v.overtime_hours.trim())) e.overtime_hours = "Enter hours with up to 2 decimals";
    else if (Number(v.overtime_hours) > 744) e.overtime_hours = "Cannot exceed 744 hours";
  }
  if (v.attendance_days.trim()) {
    if (!/^\d+$/.test(v.attendance_days.trim())) e.attendance_days = "Enter a whole number of days";
    else if (Number(v.attendance_days) > 31) e.attendance_days = "Cannot exceed 31 days";
  }
  return e;
}

export const emptyValues = (): FormValues => ({
  employee_code: "", name: "", department: "", designation: "", joining_date: "",
  basic_salary: "", bonus: "0", deductions: "0", overtime_hours: "0", attendance_days: "0",
});

const NUMERIC = new Set(["basic_salary", "bonus", "deductions", "overtime_hours", "attendance_days"]);

/** Fields whose value differs from the stored employee. Numeric fields compare by value ("50000" == "50000.00"). */
export function changedFields(current: FormValues, payload: Record<string, string | number | null>): Record<string, string | number | null> {
  const out: Record<string, string | number | null> = {};
  for (const [k, val] of Object.entries(payload)) {
    const old = current[k as keyof FormValues];
    const same = NUMERIC.has(k) ? Number(val) === Number(old) : (val ?? "") === (old ?? "");
    if (!same) out[k] = val;
  }
  return out;
}
