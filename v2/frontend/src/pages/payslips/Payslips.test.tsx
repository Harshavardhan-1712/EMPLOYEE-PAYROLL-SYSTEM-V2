import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Payslip, PayslipRow } from "../../api/types";
import { err, mockApi, pageOf, renderAt, run, viewerUser } from "../../test/utils";

const row = (o: Partial<PayslipRow> = {}): PayslipRow => ({ run_id: 5, employee_id: 1, period: "2026-09", employee_code: "E001", employee_name: "Priya Sharma", department: "Engineering", gross_salary: "57000.00", deductions: "2000.00", net_salary: "55000.00", ...o });
const slip: Payslip = { run_id: 5, period: "2026-09", period_label: "September 2026", employee_id: 1, employee_code: "E001", employee_name: "Priya Sharma", department: "Engineering", designation: "Developer",
  basic_salary: "50000.00", bonus: "5000.00", overtime_hours: "10.00", overtime_rate: "200.00", overtime_pay: "2000.00", gross_salary: "57000.00", deductions: "2000.00", net_salary: "55000.00", attendance_days: 22, finalized_at: "2026-10-02T10:00:00Z", company_name: "Acme" };
const finRun = () => { const { items: _i, ...s } = run({ status: "finalized", totals_source: "snapshot" }); return s; };

describe("Payslips list", () => {
  it("explains the empty state when nothing is finalized", async () => {
    mockApi(viewerUser, (r) => r.path === "/payroll-runs" ? { json: pageOf([]) } : { json: pageOf([]) });
    renderAt("/payslips");
    expect(await screen.findByText("No finalized payroll runs yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to payroll runs" })).toHaveAttribute("href", "/payroll-runs");
  });

  it("lists payslips with view and PDF download links, filters by run and searches", async () => {
    const calls = mockApi(viewerUser, (r) => r.path === "/payroll-runs" ? { json: pageOf([finRun()]) } : r.path === "/payslips" ? { json: pageOf([row()]) } : undefined);
    renderAt("/payslips");
    const r = (await screen.findByText("Priya Sharma")).closest("tr")!;
    expect(within(r).getByText("₹55,000.00")).toBeInTheDocument();
    expect(within(r).getByRole("link", { name: /View payslip for Priya Sharma, September 2026/ })).toHaveAttribute("href", "/payslips/1/5");
    expect(within(r).getByRole("link", { name: /Download PDF for Priya Sharma/ })).toHaveAttribute("href", "/api/payslips/1/5.pdf?download=true");
    await userEvent.selectOptions(screen.getByLabelText("Payroll run"), "5");
    await waitFor(() => expect(calls.filter((c) => c.path === "/payslips").at(-1)!.params.get("run_id")).toBe("5"));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "pri");
    await waitFor(() => expect(calls.filter((c) => c.path === "/payslips").at(-1)!.params.get("q")).toBe("pri"), { timeout: 2000 });
  });

  it("shows server errors with retry", async () => {
    mockApi(viewerUser, (r) => r.path === "/payroll-runs" ? { json: pageOf([finRun()]) } : err(500, "error", "Payslip service down"));
    renderAt("/payslips");
    expect(await screen.findByText("Payslip service down")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("Payslip view", () => {
  it("shows the stored breakdown, previews the server PDF and offers download", async () => {
    mockApi(viewerUser, (r) => r.path === "/payslips/1/5" ? { json: slip } : undefined);
    renderAt("/payslips/1/5");
    expect(await screen.findByRole("heading", { name: "Payslip — Priya Sharma" })).toBeInTheDocument();
    expect(screen.getByText("₹57,000.00")).toBeInTheDocument(); expect(screen.getByText("₹55,000.00")).toBeInTheDocument();
    expect(screen.getByText(/not recalculated/)).toBeInTheDocument();
    expect(screen.getByTitle(/Payslip PDF preview for Priya Sharma/)).toHaveAttribute("src", "/api/payslips/1/5.pdf");
    expect(screen.getByRole("link", { name: /Download PDF/ })).toHaveAttribute("href", "/api/payslips/1/5.pdf?download=true");
  });
  it("explains why a payslip is unavailable (reversed run)", async () => {
    mockApi(viewerUser, () => err(409, "conflict", "This payroll run was reversed; its payslips are no longer valid"));
    renderAt("/payslips/1/5");
    expect(await screen.findByText(/payslips are no longer valid/)).toBeInTheDocument();
    expect(screen.queryByTitle(/PDF preview/)).not.toBeInTheDocument();
  });
});
