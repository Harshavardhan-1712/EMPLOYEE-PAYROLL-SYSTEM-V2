import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { dash, err, hrUser, mockApi, renderAt } from "../../test/utils";

const serve = (d = dash()) => (r: { path: string; params: URLSearchParams }) => (r.path === "/dashboard/summary" ? { json: d } : undefined);

describe("Dashboard", () => {
  it("shows real figures for the selected period with formatted money", async () => {
    mockApi(hrUser, serve(), 80);
    renderAt("/dashboard");
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    const strip = await screen.findByRole("group", { name: /Totals for August 2026/ }).catch(() => screen.findByLabelText(/Totals for August 2026/));
    expect(within(strip).getByText("₹12,50,000.00")).toBeInTheDocument();
    expect(within(strip).getByText("₹11,49,999.50")).toBeInTheDocument();
    expect(within(strip).getByText("₹1,04,545.41")).toBeInTheDocument();
    expect(within(strip).getByText("12")).toBeInTheDocument();                            // active employees
    expect(screen.getByText(/Figures for/)).toHaveTextContent("August 2026");
  });

  it("explains the calculation and states that nothing is estimated", async () => {
    mockApi(hrUser, serve());
    renderAt("/dashboard");
    await screen.findByText("How these figures are calculated");
    await userEvent.click(screen.getByText("How these figures are calculated"));
    expect(screen.getByText(/never included/)).toBeInTheDocument();
    expect(screen.getByText(/No values are estimated or filled in/)).toBeInTheDocument();
  });

  it("shows the comparison only when the API provides one, and discloses a gap", async () => {
    mockApi(hrUser, serve());
    renderAt("/dashboard");
    expect(await screen.findByText(/Net payroll vs July 2026/)).toHaveTextContent("+₹1,49,999.50 (+15.0%)");
    expect(screen.queryByText(/not the adjacent month/)).not.toBeInTheDocument();
  });
  it("no comparison line without an earlier period (nothing invented)", async () => {
    mockApi(hrUser, serve(dash({ comparison: null })));
    renderAt("/dashboard");
    await screen.findByText("How these figures are calculated");
    expect(screen.queryByText(/Net payroll vs/)).not.toBeInTheDocument();
  });
  it("states clearly when the comparison period is not the adjacent month", async () => {
    mockApi(hrUser, serve(dash({ comparison: { period: "2026-05", employee_count: 9, total_net: "900000.00", net_change: "-50000.00", net_change_pct: "-5.6", adjacent_month: false } })));
    renderAt("/dashboard");
    const p = await screen.findByText(/Net payroll vs May 2026/);
    expect(p).toHaveTextContent("-₹50,000.00 (-5.6%)"); expect(p).toHaveTextContent("not the adjacent month");
  });

  it("empty state when no payroll has been finalized", async () => {
    mockApi(hrUser, serve(dash({ has_history: false, selected_period: null, available_periods: [], run_id: null, employee_count: 0, total_net: "0.00", departments: [], trend: [], comparison: null, average_net: null, recent_runs: [], attention: [], active_employees: 3 })));
    renderAt("/dashboard");
    expect(await screen.findByText("No finalized payroll yet")).toBeInTheDocument();
    expect(screen.getByText(/3 active employees on record/)).toBeInTheDocument();
    expect(screen.queryByText("Total net")).not.toBeInTheDocument();
  });

  it("trend chart needs enough history; otherwise says so instead of drawing one", async () => {
    mockApi(hrUser, serve(dash({ trend: dash().trend.slice(0, 2) })));
    renderAt("/dashboard");
    expect(await screen.findByText(/needs at least 3 finalized periods; there are 2 so far/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Monthly gross and net payroll" })).not.toBeInTheDocument();
  });
  it("draws the trend with 3+ periods and offers the data as a table", async () => {
    mockApi(hrUser, serve());
    renderAt("/dashboard");
    expect(await screen.findByRole("img", { name: "Monthly gross and net payroll" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Net payroll by department" })).toBeInTheDocument();
    const dept = screen.getByRole("region", { name: "Payroll by department" });
    await userEvent.click(within(dept).getByText("View data as a table"));
    const row = within(within(dept).getByRole("table", { name: "Payroll by department" })).getByText("Engineering").closest("tr")!;
    expect(within(row).getByText("₹8,30,000.00")).toBeInTheDocument();
  });

  it("period selector reloads the dashboard for the chosen period", async () => {
    const calls = mockApi(hrUser, (r) => r.path === "/dashboard/summary" ? { json: dash({ selected_period: r.params.get("period") || "2026-08" }) } : undefined);
    renderAt("/dashboard");
    await userEvent.selectOptions(await screen.findByLabelText("Payroll period"), "2026-06");
    await waitFor(() => expect(calls.filter((c) => c.path === "/dashboard/summary").at(-1)!.params.get("period")).toBe("2026-06"));
    expect(await screen.findByText(/Figures for/)).toHaveTextContent("June 2026");
  });

  it("links recent runs and review items to their records; shows status badges", async () => {
    mockApi(hrUser, serve());
    renderAt("/dashboard");
    const recent = (await screen.findByRole("table", { name: "Recent payroll runs" }));
    expect(within(recent).getByRole("link", { name: "August 2026" })).toHaveAttribute("href", "/payroll-runs/8");
    expect(within(recent).getByText("Draft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /2026-09 payroll is draft/ })).toHaveAttribute("href", "/payroll-runs/9");
  });

  it("distinguishes sample data from real data", async () => {
    mockApi(hrUser, serve(dash({ includes_sample_data: true })));
    renderAt("/dashboard");
    expect(await screen.findByText(/built from sample data: these figures are not real payroll/)).toBeInTheDocument();
  });

  it("shows the server error with retry when the request fails", async () => {
    mockApi(hrUser, () => err(500, "error", "Database is unavailable"));
    renderAt("/dashboard");
    expect(await screen.findByText("Database is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
