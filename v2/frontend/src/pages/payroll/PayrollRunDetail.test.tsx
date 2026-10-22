import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { approverUser, err, hrUser, item, mockApi, negFlag, otFlag, renderAt, run, viewerUser } from "../../test/utils";

const serve = (state: { run: ReturnType<typeof run> }, extra?: (r: any) => any) => (r: any) => {
  const e = extra?.(r); if (e) return e;
  if (r.path === "/payroll-runs/5" && r.method === "GET") return { json: state.run };
  if (r.path === "/payroll-runs") return { json: { items: [], total: 0, page: 1, page_size: 25 } };
  return undefined;
};

describe("Draft run", () => {
  it("shows live totals, the formula, and explainable flags", async () => {
    const st = { run: run({ error_flag_items: 1, warning_flag_items: 1, items: [item({ flags: [negFlag] }), item({ id: 12, employee_id: 2, employee_code: "E002", employee_name: "Arjun Mehta", flags: [otFlag] })], employee_count: 2 }) };
    mockApi(hrUser, serve(st));
    renderAt("/payroll-runs/5");
    expect(await screen.findByRole("heading", { name: /Payroll — September 2026/ })).toBeInTheDocument();
    expect(screen.getByText(/Live totals/)).toBeInTheDocument();
    expect(screen.getByText(/Overtime pay = hours × rate/)).toBeInTheDocument();
    expect(screen.getByText(/No statutory deductions/)).toBeInTheDocument();
    const flags = screen.getByRole("region", { name: /Items to review/ });
    expect(within(flags).getByText(/Net pay is negative/)).toBeInTheDocument();
    expect(within(flags).getByText(/not findings of error or fraud/)).toBeInTheDocument();
  });

  it("editing an item sends only strings, shows the server-recalculated result after reload", async () => {
    const st = { run: run() };
    const calls = mockApi(hrUser, serve(st, (r) => {
      if (r.method === "PATCH") { st.run = run({ total_net: "-33000.00", items: [item({ deductions: "90000.00", net_salary: "-33000.00", flags: [negFlag] })] }); return { json: st.run.items[0] }; }
    }));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Edit Priya Sharma" }));
    const dlg = await screen.findByRole("dialog");
    const ded = within(dlg).getByLabelText(/Deductions/); await userEvent.clear(ded); await userEvent.type(ded, "90000");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save and recalculate" }));
    await waitFor(() => expect(screen.getAllByText("-₹33,000.00").length).toBeGreaterThan(0));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ bonus: "5000.00", deductions: "90000", overtime_hours: "10.00", attendance_days: 22 });
    expect(screen.getByText(/Net pay is negative/)).toBeInTheDocument();
  });

  it("client-side validation blocks bad values; server field errors are displayed", async () => {
    const calls = mockApi(hrUser, serve({ run: run() }, (r) => r.method === "PATCH" ? err(422, "validation_error", "Request validation failed", [{ field: "attendance_days", message: "Input should be less than or equal to 31" }]) : undefined));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Edit Priya Sharma" }));
    const dlg = await screen.findByRole("dialog");
    const b = within(dlg).getByLabelText(/Bonus/); await userEvent.clear(b); await userEvent.type(b, "-5");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save and recalculate" }));
    expect(await within(dlg).findByText(/non-negative amount/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    await userEvent.clear(b); await userEvent.type(b, "5000");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save and recalculate" }));
    expect(await within(dlg).findByText("Input should be less than or equal to 31")).toBeInTheDocument();
  });

  it("only users with the right permissions see workflow actions", async () => {
    mockApi(hrUser, serve({ run: run() }));
    renderAt("/payroll-runs/5");
    await screen.findByRole("heading", { name: /Payroll — September 2026/ });
    expect(screen.queryByRole("button", { name: "Mark as reviewed" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete run" })).toBeInTheDocument();
  });
  it("viewers cannot edit or act", async () => {
    mockApi(viewerUser, serve({ run: run() }));
    renderAt("/payroll-runs/5");
    await screen.findByRole("heading", { name: /Payroll — September 2026/ });
    expect(screen.queryByRole("button", { name: /Edit Priya/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete run" })).not.toBeInTheDocument();
  });

  it("review needs confirmation then calls the API", async () => {
    const st = { run: run() };
    const calls = mockApi(approverUser, serve(st, (r) => { if (r.path === "/payroll-runs/5/review") { st.run = run({ status: "reviewed" }); return { json: st.run }; } }));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Mark as reviewed" }));
    expect(calls.some((c) => c.path.endsWith("/review"))).toBe(false);
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Mark as reviewed" }));
    expect(await screen.findByRole("button", { name: "Finalize…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit Priya/ })).not.toBeInTheDocument();     // reviewed = read-only
  });

  it("deleting a draft requires confirmation and returns to the list", async () => {
    const calls = mockApi(hrUser, serve({ run: run() }, (r) => r.method === "DELETE" ? { status: 204 } : undefined));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Delete run" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete run" }));
    expect(await screen.findByRole("heading", { name: "Payroll runs" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/payroll-runs/5")).toBe(true);
  });
});

describe("Finalize", () => {
  it("without error flags: no acknowledgement needed", async () => {
    const st = { run: run({ status: "reviewed" }) };
    const calls = mockApi(approverUser, serve(st, (r) => { if (r.path.endsWith("/finalize")) { st.run = run({ status: "finalized", totals_source: "snapshot", finalized_at: "2026-10-02T10:00:00Z" }); return { json: st.run }; } }));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Finalize…" }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText(/permanent record/)).toBeInTheDocument();
    expect(within(dlg).queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("button", { name: "Finalize run" }));
    expect(await screen.findByText(/permanent snapshot and cannot be edited/)).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/finalize"))!.body).toEqual({ acknowledge_errors: false, note: null });
    expect(screen.getByRole("link", { name: "View payslips" })).toHaveAttribute("href", "/payslips?run_id=5");
    expect(screen.queryByRole("button", { name: /Edit Priya/ })).not.toBeInTheDocument();
  });

  it("with error flags: finalize stays disabled until the approver acknowledges, and the note is sent", async () => {
    const st = { run: run({ status: "reviewed", error_flag_items: 1, items: [item({ flags: [negFlag] })] }) };
    const calls = mockApi(approverUser, serve(st, (r) => { if (r.path.endsWith("/finalize")) return { json: run({ status: "finalized", totals_source: "snapshot" }) }; }));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Finalize…" }));
    const dlg = await screen.findByRole("dialog");
    const btn = within(dlg).getByRole("button", { name: "Finalize run" });
    expect(btn).toBeDisabled();
    await userEvent.type(within(dlg).getByLabelText(/Note/), "CFO approved");
    await userEvent.click(within(dlg).getByRole("checkbox"));
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/finalize"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/finalize"))!.body).toEqual({ acknowledge_errors: true, note: "CFO approved" });
  });

  it("shows the server's refusal if finalization fails", async () => {
    mockApi(approverUser, serve({ run: run({ status: "reviewed" }) }, (r) => r.path.endsWith("/finalize") ? err(409, "conflict", "Integrity check failed for E001; run not finalized") : undefined));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Finalize…" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Finalize run" }));
    expect(await screen.findByText(/Integrity check failed/)).toBeInTheDocument();
  });
});

describe("Finalized and reversed runs", () => {
  const fin = () => run({ status: "finalized", totals_source: "snapshot", finalized_at: "2026-10-02T10:00:00Z" });

  it("reversal needs a reason of at least 10 characters and sends it", async () => {
    const calls = mockApi(approverUser, serve({ run: fin() }, (r) => r.path.endsWith("/reverse") ? { json: run({ status: "reversed", reversed_at: "2026-10-03T10:00:00Z", reversal_reason: "Bonus entered incorrectly" }) } : undefined));
    renderAt("/payroll-runs/5");
    await userEvent.click(await screen.findByRole("button", { name: "Reverse…" }));
    const dlg = await screen.findByRole("dialog");
    const go = within(dlg).getByRole("button", { name: "Reverse run" });
    expect(go).toBeDisabled();
    await userEvent.type(within(dlg).getByLabelText(/Reason/), "short");
    expect(go).toBeDisabled(); expect(within(dlg).getByText(/more characters/)).toBeInTheDocument();
    await userEvent.type(within(dlg).getByLabelText(/Reason/), " but now long enough");
    await userEvent.click(go);
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/reverse"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/reverse"))!.body).toEqual({ reason: "short but now long enough" });
  });

  it("HR editors cannot reverse a finalized run", async () => {
    mockApi(hrUser, serve({ run: fin() }));
    renderAt("/payroll-runs/5");
    await screen.findByText(/permanent snapshot/);
    expect(screen.queryByRole("button", { name: "Reverse…" })).not.toBeInTheDocument();
  });

  it("a reversed run shows who/why, keeps its figures, and offers no actions", async () => {
    mockApi(approverUser, serve({ run: run({ status: "reversed", totals_source: "snapshot", reversed_at: "2026-10-03T10:00:00Z", reversal_reason: "Bonus entered incorrectly" }) }));
    renderAt("/payroll-runs/5");
    expect(await screen.findByText(/Bonus entered incorrectly/)).toBeInTheDocument();
    expect(screen.getByText(/payslips for this run are no longer valid/)).toBeInTheDocument();
    expect(screen.getByText("Priya Sharma")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reverse|Finalize|Edit|Delete/ })).not.toBeInTheDocument();
  });

  it("missing run shows a not-found state", async () => {
    mockApi(approverUser, () => err(404, "not_found", "Payroll run not found"));
    renderAt("/payroll-runs/5");
    expect(await screen.findByText("This payroll run does not exist.")).toBeInTheDocument();
  });
});
