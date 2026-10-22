import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { analytics, hrUser, mockApi, pageOf, renderAt, run, viewerUser } from "../../test/utils";

const fin = (id: number, period: string) => { const { items: _i, ...s } = run({ id, period, status: "finalized", totals_source: "snapshot", employee_count: 4 }); return s; };
const serve = (runs = [fin(9, "2026-09"), fin(8, "2026-08")]) => (r: { path: string }) =>
  r.path === "/payroll-runs" ? { json: pageOf(runs) } : r.path === "/employees/departments" ? { json: ["Engineering", "Finance"] } : r.path === "/analytics/summary" ? { json: analytics() } : undefined;

describe("Reports & exports", () => {
  it("defaults to the latest finalized run and links real downloads", async () => {
    mockApi(hrUser, serve());
    renderAt("/reports");
    expect(await screen.findByRole("link", { name: /Payroll register \(CSV\)/ })).toHaveAttribute("href", "/api/reports/payroll.csv?run_id=9");
    expect(screen.getByRole("link", { name: /Payroll workbook \(Excel\)/ })).toHaveAttribute("href", "/api/reports/payroll.xlsx?run_id=9");
    expect(screen.getByRole("link", { name: /Department report \(CSV\)/ })).toHaveAttribute("href", "/api/reports/department.csv?run_id=9");
    expect(screen.getByText(/4 employees/)).toBeInTheDocument();
  });

  it("changing the run changes every run-based link", async () => {
    mockApi(hrUser, serve());
    renderAt("/reports");
    await userEvent.selectOptions(await screen.findByLabelText("Payroll run"), "8");
    expect(screen.getByRole("link", { name: /Payroll workbook/ })).toHaveAttribute("href", "/api/reports/payroll.xlsx?run_id=8");
  });

  it("employee register link follows the filters", async () => {
    mockApi(hrUser, serve());
    renderAt("/reports");
    const sec = (await screen.findByText("Employee register")).closest("section")!;
    expect(within(sec).getByRole("link", { name: /Employee register \(CSV\)/ })).toHaveAttribute("href", "/api/reports/employees.csv");
    await userEvent.selectOptions(within(sec).getByLabelText("Status"), "inactive");
    await userEvent.selectOptions(within(sec).getByLabelText("Department"), "Finance");
    expect(within(sec).getByRole("link", { name: /Employee register \(CSV\)/ })).toHaveAttribute("href", "/api/reports/employees.csv?status=inactive&department=Finance");
  });

  it("analytics export link carries the range and department", async () => {
    mockApi(hrUser, serve());
    renderAt("/reports");
    const sec = (await screen.findByText("Analytics data")).closest("section")!;
    await userEvent.selectOptions(within(sec).getByLabelText("From"), "2026-07");
    await userEvent.selectOptions(within(sec).getByLabelText("Department"), "Engineering");
    expect(within(sec).getByRole("link", { name: /Analytics export/ })).toHaveAttribute("href", "/api/reports/analytics.csv?from=2026-07&department=Engineering");
  });

  it("with no finalized run, run reports are unavailable and explained", async () => {
    mockApi(hrUser, serve([]));
    renderAt("/reports");
    expect(await screen.findByText(/No payroll run has been finalized yet/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Payroll register/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Employee register \(CSV\)/ })).toBeInTheDocument();     // still available
  });

  it("viewers are told they cannot export, with no download links", async () => {
    mockApi(viewerUser, serve());
    renderAt("/reports");
    expect(await screen.findByText(/Your role cannot export reports/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /\(CSV\)|\(Excel\)/ })).not.toBeInTheDocument();
  });

  it("documents spreadsheet formula protection", async () => {
    mockApi(hrUser, serve());
    renderAt("/reports");
    expect(await screen.findByText(/cannot run anything/)).toBeInTheDocument();
  });
});
