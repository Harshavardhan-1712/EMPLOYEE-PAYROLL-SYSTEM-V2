import { describe, expect, it } from "vitest";
import { changedFields, emptyValues, validateEmployee, type FormValues } from "./validation";

const ok = (o: Partial<FormValues> = {}): FormValues => ({ ...emptyValues(), employee_code: "E1", name: "A", department: "D", designation: "T", basic_salary: "1000", ...o });

describe("validateEmployee", () => {
  it("accepts a valid employee", () => expect(validateEmployee(ok(), "create")).toEqual({}));
  it("requires the key fields", () => {
    const e = validateEmployee(emptyValues(), "create");
    expect(Object.keys(e).sort()).toEqual(["basic_salary", "department", "designation", "employee_code", "name"]);
  });
  it("does not require or validate the code when editing", () => expect(validateEmployee(ok({ employee_code: "" }), "edit")).toEqual({}));
  it.each([["-1"], ["abc"], ["1.234"], ["12345678"], ["1e3"]])("rejects money %s", (v) => expect(validateEmployee(ok({ basic_salary: v }), "create").basic_salary).toBeTruthy());
  it("limits overtime hours and attendance", () => {
    expect(validateEmployee(ok({ overtime_hours: "745" }), "create").overtime_hours).toMatch(/744/);
    expect(validateEmployee(ok({ attendance_days: "32" }), "create").attendance_days).toMatch(/31/);
    expect(validateEmployee(ok({ attendance_days: "2.5" }), "create").attendance_days).toBeTruthy();
  });
  it("rejects bad employee ids", () => expect(validateEmployee(ok({ employee_code: "a b!" }), "create").employee_code).toBeTruthy());
});

describe("changedFields", () => {
  const cur = ok({ basic_salary: "50000.00", name: "Priya", joining_date: "" });
  it("treats numerically equal money as unchanged", () => expect(changedFields(cur, { basic_salary: "50000", name: "Priya" })).toEqual({}));
  it("returns only what changed", () => expect(changedFields(cur, { basic_salary: "60000", name: "Priya" })).toEqual({ basic_salary: "60000" }));
  it("compares text fields as text (numeric-looking names are not coerced)", () => expect(changedFields({ ...cur, name: "007" }, { name: "7" })).toEqual({ name: "7" }));
  it("handles cleared joining date", () => expect(changedFields({ ...cur, joining_date: "2020-01-01" }, { joining_date: null })).toEqual({ joining_date: null }));
});
