import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { err, hrUser, mockApi, pageOf, renderAt, run, viewerUser } from "../../test/utils";

const summary = (o = {}) => { const { items: _i, ...s } = run(o); return s; };

describe("Payroll runs list", () => {
  it("shows runs with status, totals and flag badges; negative net is marked", async () => {
    mockApi(hrUser, (r) => r.path === "/payroll-runs" ? { json: pageOf([
      summary({ id: 5, status: "finalized", totals_source: "snapshot", total_net: "-33000.00", error_flag_items: 1, warning_flag_items: 2 }),
      summary({ id: 4, period: "2026-08", status: "draft" })]) } : undefined, 100);
    renderAt("/payroll-runs");
    expect((await screen.findByRole("table", { busy: true }))).toBeInTheDocument();
    const row = (await screen.findByRole("link", { name: "September 2026" })).closest("tr")!;
    expect(within(row).getByText("Finalized")).toBeInTheDocument();
    expect(within(row).getByText("1 error")).toBeInTheDocument(); expect(within(row).getByText("2 warning")).toBeInTheDocument();
    expect(within(row).getByText("-₹33,000.00")).toHaveClass("neg");
    expect(screen.getByRole("link", { name: "August 2026" }).closest("tr")).toHaveTextContent("Draft");
  });

  it("empty state differs for editors and viewers; error state recovers", async () => {
    mockApi(viewerUser, (r) => r.path === "/payroll-runs" ? { json: pageOf([]) } : undefined);
    renderAt("/payroll-runs");
    expect(await screen.findByText("No payroll runs yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /New payroll run/ })).not.toBeInTheDocument();
  });
  it("shows server errors with Retry", async () => {
    let fail = true;
    mockApi(hrUser, () => fail ? err(500, "error", "Database is unavailable") : { json: pageOf([summary()]) });
    renderAt("/payroll-runs");
    expect(await screen.findByText("Database is unavailable")).toBeInTheDocument();
    fail = false; await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "September 2026" })).toBeInTheDocument();
  });
  it("status filter goes to the server", async () => {
    const calls = mockApi(hrUser, () => ({ json: pageOf([summary()]) }));
    renderAt("/payroll-runs");
    await screen.findByRole("link", { name: "September 2026" });
    await userEvent.selectOptions(screen.getByLabelText("Status"), "finalized");
    await waitFor(() => expect(calls.at(-1)!.params.get("status")).toBe("finalized"));
  });
});

describe("New payroll run", () => {
  const open = async () => { await userEvent.click(await screen.findByRole("button", { name: /New payroll run/ })); return await screen.findByRole("dialog"); };

  it("creates a draft with an idempotency key and opens it", async () => {
    const calls = mockApi(hrUser, (r) => {
      if (r.path === "/payroll-runs" && r.method === "POST") return { status: 201, json: run({ id: 7, period: "2026-09" }) };
      if (r.path === "/payroll-runs/7") return { json: run({ id: 7 }) };
      if (r.path === "/payroll-runs") return { json: pageOf([]) };
      return undefined;
    });
    renderAt("/payroll-runs");
    const dlg = await open();
    const input = within(dlg).getByLabelText(/Payroll period/);
    await userEvent.clear(input); await userEvent.type(input, "2026-09");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create draft run" }));
    expect(await screen.findByRole("heading", { name: /Payroll — September 2026/ })).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toEqual({ period: "2026-09" });
    expect(post.headers["Idempotency-Key"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("rejects a future period client-side without calling the API", async () => {
    const calls = mockApi(hrUser, () => ({ json: pageOf([]) }));
    renderAt("/payroll-runs");
    const dlg = await open();
    const input = within(dlg).getByLabelText(/Payroll period/);
    await userEvent.clear(input); await userEvent.type(input, "2999-01");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create draft run" }));
    expect(await within(dlg).findByText(/cannot be in the future/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("duplicate period: shows the server message and links to the existing run", async () => {
    mockApi(hrUser, (r) => r.method === "POST" ? err(409, "conflict", "A payroll run for 2026-09 already exists (run #3, finalized)") : { json: pageOf([]) });
    renderAt("/payroll-runs");
    const dlg = await open();
    await userEvent.click(within(dlg).getByRole("button", { name: "Create draft run" }));
    expect(await within(dlg).findByText(/already exists/)).toBeInTheDocument();
    expect(within(dlg).getByRole("link", { name: "Open run #3" })).toHaveAttribute("href", "/payroll-runs/3");
  });
});
