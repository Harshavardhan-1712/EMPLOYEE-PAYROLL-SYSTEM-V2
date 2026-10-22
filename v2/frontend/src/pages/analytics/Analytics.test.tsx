import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { analytics, err, hrUser, mockApi, renderAt, viewerUser } from "../../test/utils";

const serve = (a = analytics()) => (r: { path: string }) => (r.path === "/analytics/summary" ? { json: a } : undefined);

describe("Analytics", () => {
  it("summarises the scope with stats, extremes and a negative lowest net flagged", async () => {
    mockApi(hrUser, serve(), 60);
    renderAt("/analytics");
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    const strip = await screen.findByLabelText("Summary statistics");
    expect(within(strip).getByText("₹91,666.67")).toBeInTheDocument();
    expect(within(strip).getByText("₹2,50,000.00")).toBeInTheDocument(); expect(within(strip).getByText(/Vikram Rao, August 2026/)).toBeInTheDocument();
    expect(within(strip).getByText("-₹2,000.00")).toHaveClass("neg");
    expect(screen.getByText(/A "pay record" is one employee in one finalized month/)).toBeInTheDocument();
  });

  it("charts have accessible names and table alternatives with the same numbers", async () => {
    mockApi(hrUser, serve());
    renderAt("/analytics");
    for (const name of ["Net salary distribution", "Gross and net by department", "Monthly gross and net payroll"]) expect(await screen.findByRole("img", { name })).toBeInTheDocument();
    const dist = screen.getByRole("region", { name: "Net salary distribution" });
    await userEvent.click(within(dist).getByText("View data as a table"));
    const r = within(dist).getByText(/₹50,000.00 – ₹1,00,000.00/).closest("tr")!;
    expect(within(r).getByText("20")).toBeInTheDocument();
  });

  it("changes over time are explained as adjacent-month only", async () => {
    mockApi(hrUser, serve());
    renderAt("/analytics");
    const sec = (await screen.findByRole("table", { name: "Change over time" })).closest("section")!;
    expect(within(sec).getByText(/gaps in history are not bridged/)).toBeInTheDocument();
    const row = within(sec).getByText("July 2026", { selector: "td" }).closest("tr")!;
    expect(row).toHaveTextContent("June 2026"); expect(row).toHaveTextContent("+1"); expect(row).toHaveTextContent("5.9%");
  });
  it("no consecutive months: says so rather than inventing a comparison", async () => {
    mockApi(hrUser, serve(analytics({ changes: [] })));
    renderAt("/analytics");
    expect(await screen.findByText("No consecutive finalized months in this scope.")).toBeInTheDocument();
  });

  it("data-quality section frames flags as indicators and shows thresholds, counts and explanations", async () => {
    mockApi(hrUser, serve());
    renderAt("/analytics");
    const dq = (await screen.findByRole("region", { name: /Data quality and review flags/ }));
    expect(within(dq).getByText(/not proof of an error or of misconduct/)).toBeInTheDocument();
    expect(within(dq).getByText(/overtime above 40 h/)).toBeInTheDocument(); expect(within(dq).getByText(/above 25%/)).toBeInTheDocument();
    expect(within(dq).getByText("High overtime: 3")).toBeInTheDocument(); expect(within(dq).getByText("Negative net pay: 1")).toBeInTheDocument();
    expect(within(dq).getByText("Active employees without a joining date: 2")).toBeInTheDocument();
    expect(within(dq).getByText(/exceeds the review threshold of 40 h/)).toBeInTheDocument();
    expect(within(dq).getByRole("link", { name: "August 2026" })).toHaveAttribute("href", "/payroll-runs/8");
  });

  it("filters go to the server and can be cleared", async () => {
    const calls = mockApi(hrUser, (r) => r.path === "/analytics/summary" ? { json: analytics() } : undefined);
    renderAt("/analytics");
    await userEvent.selectOptions(await screen.findByLabelText("Department"), "Finance");
    await waitFor(() => expect(calls.at(-1)!.params.get("department")).toBe("Finance"));
    await userEvent.selectOptions(screen.getByLabelText("From"), "2026-07");
    await userEvent.selectOptions(screen.getByLabelText("To"), "2026-08");
    await waitFor(() => { const p = calls.at(-1)!.params; expect([p.get("from"), p.get("to"), p.get("department")]).toEqual(["2026-07", "2026-08", "Finance"]); });
    expect(screen.getByRole("link", { name: /Export filtered data/ }).getAttribute("href")).toBe("/api/reports/analytics.csv?from=2026-07&to=2026-08&department=Finance");
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(calls.at(-1)!.params.get("department")).toBeNull());
  });

  it("viewers see analytics but no export link", async () => {
    mockApi(viewerUser, serve());
    renderAt("/analytics");
    await screen.findByLabelText("Summary statistics");
    expect(screen.queryByRole("link", { name: /Export filtered data/ })).not.toBeInTheDocument();
  });

  it("empty states: no history vs no matches for the filters", async () => {
    mockApi(hrUser, serve(analytics({ available_periods: [], record_count: 0, departments: [] })));
    renderAt("/analytics");
    expect(await screen.findByText("No finalized payroll yet")).toBeInTheDocument();
  });
  it("no matches for filters offers to clear them", async () => {
    mockApi(hrUser, serve(analytics({ record_count: 0, distribution: [], highest_net: null, lowest_net: null, average_net: null })));
    renderAt("/analytics?department=Legal");
    expect(await screen.findByText("No payroll records match these filters")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Export filtered data/ })).not.toBeInTheDocument();
  });

  it("server error with retry", async () => {
    mockApi(hrUser, () => err(500, "error", "Analytics unavailable"));
    renderAt("/analytics");
    expect(await screen.findByText("Analytics unavailable")).toBeInTheDocument();
  });
});
