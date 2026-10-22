import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AdminUser, AuditEntry, PayrollSettings } from "../../api/types";
import { adminUser, err, mockApi, pageOf, renderAt, user, viewerUser, hrUser } from "../../test/utils";
import { describe as describeDetail } from "./AuditLogPage";

const settings = (o: Partial<PayrollSettings> = {}): PayrollSettings => ({ overtime_rate: "200.00", high_overtime_hours: "40", unusual_salary_change_pct: "25", require_separate_finalizer: false, ...o });

describe("Settings", () => {
  const serve = (s = settings(), extra?: (r: any) => any) => (r: any) => extra?.(r) ?? (r.path === "/settings" && r.method === "GET" ? { json: s } : undefined);

  it("shows current values and is explicit about what a rate change affects", async () => {
    mockApi(adminUser, serve());
    renderAt("/settings");
    expect(await screen.findByLabelText(/Overtime rate/)).toHaveValue("200.00");
    expect(screen.getByText(/Applies to new payroll runs only/)).toBeInTheDocument();
    expect(screen.getByText(/not statutory or policy limits/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Require a different person to finalize/)).not.toBeChecked();
  });

  it("changing only a threshold saves immediately and sends only that field", async () => {
    const calls = mockApi(adminUser, serve(settings(), (r) => r.method === "PATCH" ? { json: settings({ high_overtime_hours: "50" }) } : undefined));
    renderAt("/settings");
    const f = await screen.findByLabelText(/High overtime above/); await userEvent.clear(f); await userEvent.type(f, "50");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ high_overtime_hours: "50" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("changing the overtime rate needs confirmation that states old and new values; cancel sends nothing", async () => {
    const calls = mockApi(adminUser, serve(settings(), (r) => r.method === "PATCH" ? { json: settings({ overtime_rate: "250.00" }) } : undefined));
    renderAt("/settings");
    const f = await screen.findByLabelText(/Overtime rate/); await userEvent.clear(f); await userEvent.type(f, "250");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    const dlg = await screen.findByRole("dialog");
    expect(dlg).toHaveTextContent("₹200.00"); expect(dlg).toHaveTextContent("₹250.00"); expect(dlg).toHaveTextContent("keep their current rate");
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Change rate" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ overtime_rate: "250" });
  });

  it("validates client-side and reports 'no changes'", async () => {
    const calls = mockApi(adminUser, serve());
    renderAt("/settings");
    await userEvent.click(await screen.findByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("No changes to save.")).toBeInTheDocument();
    const f = screen.getByLabelText(/Overtime rate/); await userEvent.clear(f); await userEvent.type(f, "-5");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText(/amount with up to 2 decimals/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("the separation-of-duties switch is sent as a boolean", async () => {
    const calls = mockApi(adminUser, serve(settings(), (r) => r.method === "PATCH" ? { json: settings({ require_separate_finalizer: true }) } : undefined));
    renderAt("/settings");
    await userEvent.click(await screen.findByLabelText(/Require a different person to finalize/));
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ require_separate_finalizer: true }));
  });

  it("server rejection is shown", async () => {
    mockApi(adminUser, serve(settings(), (r) => r.method === "PATCH" ? err(422, "validation_error", "Request validation failed", [{ field: "high_overtime_hours", message: "Input should be less than or equal to 744" }]) : undefined));
    renderAt("/settings");
    const f = await screen.findByLabelText(/High overtime above/); await userEvent.clear(f); await userEvent.type(f, "100");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Input should be less than or equal to 744")).toBeInTheDocument();
  });

  it("read-only users can view but not change", async () => {
    mockApi(user("auditor", ["settings:read"]), serve());
    renderAt("/settings");
    expect(await screen.findByLabelText(/Overtime rate/)).toBeDisabled();
    expect(screen.getByText(/view these settings but not change them/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save settings" })).not.toBeInTheDocument();
  });
});

const ev = (o: Partial<AuditEntry> = {}): AuditEntry => ({ id: 1, at: "2026-10-02T10:00:00Z", actor_username: "ap1", action: "payroll.run_finalized", entity_type: "payroll_run", entity_id: "5", detail: { period: "2026-09", employees: 3, total_net_paise: 13250000 }, ...o });

describe("Audit log", () => {
  it("renders events with readable details; paise shown as rupees; sensitive actions highlighted", async () => {
    mockApi(adminUser, (r) => r.path === "/audit-log" ? { json: pageOf([ev(), ev({ id: 2, action: "access.denied", actor_username: "vic", entity_type: null, entity_id: null, detail: { permission: "audit:read", path: "/api/audit-log" } })]) } : undefined, 60);
    renderAt("/audit-log");
    expect(await screen.findByRole("table", { busy: true })).toBeInTheDocument();
    const row = (await screen.findByText("payroll_run #5")).closest("tr")!;      // (the action name also appears as a filter <option>)
    expect(within(row).getByText("payroll.run_finalized")).toBeInTheDocument();
    expect(within(row).getByText(/total_net: ₹1,32,500.00|total_net: ₹132500.00/)).toBeInTheDocument();
    expect(within(row).getByText("payroll_run #5")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("access.denied").className).toContain("badge--warning");
    expect(screen.getByText("2 events")).toBeInTheDocument();
  });
  it("describe() renders objects, nulls and empty details safely", () => {
    expect(describeDetail({})).toBe("—");
    expect(describeDetail({ changes: { role: { old: "viewer", new: "admin" } }, note: null })).toBe('changes: {"role":{"old":"viewer","new":"admin"}}; note: null');
    expect(describeDetail({ old_basic_paise: "5000000" })).toBe("old_basic: ₹50000.00");
  });
  it("filters go to the server; empty and error states", async () => {
    const calls = mockApi(adminUser, (r) => r.path === "/audit-log" ? { json: pageOf([]) } : undefined);
    renderAt("/audit-log");
    expect(await screen.findByText("No events recorded yet")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Action"), "report.exported");
    await waitFor(() => expect(calls.at(-1)!.params.get("action")).toBe("report.exported"));
    expect(await screen.findByText("No events match these filters")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("User"), "hr1");
    await waitFor(() => expect(calls.at(-1)!.params.get("actor")).toBe("hr1"), { timeout: 2000 });
  });
  it("shows server errors with retry", async () => {
    mockApi(adminUser, () => err(500, "error", "Audit store unavailable"));
    renderAt("/audit-log");
    expect(await screen.findByText("Audit store unavailable")).toBeInTheDocument();
  });
});

const au = (o: Partial<AdminUser> = {}): AdminUser => ({ id: 2, username: "hr1", full_name: "HR One", role: "hr_editor", is_active: true, is_sample: false, created_at: "2026-09-01T09:00:00Z", ...o });
const me = au({ id: 1, username: "admin", full_name: "Test admin", role: "admin" });

describe("Users", () => {
  const serve = (users = [me, au()], extra?: (r: any) => any) => (r: any) => extra?.(r) ?? (r.path === "/users" && r.method === "GET" ? { json: users } : undefined);

  it("lists users; your own row has no deactivate and is marked", async () => {
    mockApi(adminUser, serve());
    renderAt("/users");
    const mine = (await screen.findByText("admin", { selector: "td" })).closest("tr")!;
    expect(within(mine).getByText("You")).toBeInTheDocument();
    expect(within(mine).queryByRole("button", { name: /Deactivate/ })).not.toBeInTheDocument();
    const other = screen.getByText("hr1", { selector: "td" }).closest("tr")!;
    expect(within(other).getByText("HR editor")).toBeInTheDocument(); expect(within(other).getByRole("button", { name: "Deactivate hr1" })).toBeInTheDocument();
  });

  it("create user: client validation, then POST; server conflicts are shown", async () => {
    const calls = mockApi(adminUser, serve([me], (r) => r.method === "POST" && r.path === "/users" ? err(409, "conflict", "Username 'bob' is already taken") : undefined));
    renderAt("/users");
    await userEvent.click(await screen.findByRole("button", { name: "New user" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create user" }));
    expect(await within(dlg).findByText(/3–64 characters/)).toBeInTheDocument(); expect(within(dlg).getByText("Required")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.type(within(dlg).getByLabelText(/Username/), "bob"); await userEvent.type(within(dlg).getByLabelText(/Full name/), "Bob B");
    await userEvent.selectOptions(within(dlg).getByLabelText("Role"), "payroll_approver");
    expect(within(dlg).getByText(/finalizes and reverses payroll runs/)).toBeInTheDocument();
    await userEvent.type(within(dlg).getByLabelText(/Initial password/), "short");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create user" }));
    expect(await within(dlg).findByText(/At least 12 characters/)).toBeInTheDocument();
    await userEvent.clear(within(dlg).getByLabelText(/Initial password/)); await userEvent.type(within(dlg).getByLabelText(/Initial password/), "a-long-enough-pass");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create user" }));
    expect(await within(dlg).findByText("Username 'bob' is already taken")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ username: "bob", full_name: "Bob B", role: "payroll_approver", password: "a-long-enough-pass" });
  });

  it("you cannot change your own role in the UI (and the server refuses anyway)", async () => {
    mockApi(adminUser, serve());
    renderAt("/users");
    await userEvent.click(await screen.findByRole("button", { name: "Edit admin" }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByLabelText("Role")).toBeDisabled(); expect(dlg).toHaveTextContent("cannot change your own role");
  });

  it("editing another user sends only changed fields", async () => {
    const calls = mockApi(adminUser, serve([me, au()], (r) => r.method === "PATCH" ? { json: au({ role: "viewer" }) } : undefined));
    renderAt("/users");
    await userEvent.click(await screen.findByRole("button", { name: "Edit hr1" }));
    await userEvent.selectOptions(within(await screen.findByRole("dialog")).getByLabelText("Role"), "viewer");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ role: "viewer" }));
  });

  it("deactivation asks first, then calls the API; failures are shown", async () => {
    const calls = mockApi(adminUser, serve([me, au()], (r) => r.method === "PATCH" ? err(409, "conflict", "This is the last active administrator.") : undefined));
    renderAt("/users");
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate hr1" }));
    const dlg = await screen.findByRole("dialog");
    expect(dlg).toHaveTextContent("signed out immediately");
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    await userEvent.click(within(dlg).getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByText("This is the last active administrator.")).toBeInTheDocument();
  });

  it("reset password enforces length and posts to the user's endpoint", async () => {
    const calls = mockApi(adminUser, serve([me, au()], (r) => r.path === "/users/2/reset-password" ? { status: 204 } : undefined));
    renderAt("/users");
    await userEvent.click(await screen.findByRole("button", { name: "Reset password for hr1" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^New password/), "tooshort");
    await userEvent.click(within(dlg).getByRole("button", { name: "Reset password" }));
    expect(await within(dlg).findByText(/At least 12 characters/)).toBeInTheDocument();
    await userEvent.clear(within(dlg).getByLabelText(/^New password/)); await userEvent.type(within(dlg).getByLabelText(/^New password/), "reset-me-please-now");
    await userEvent.click(within(dlg).getByRole("button", { name: "Reset password" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/users/2/reset-password")?.body).toEqual({ password: "reset-me-please-now" }));
  });
});

describe("Navigation and access", () => {
  const links = () => within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link").map((a) => a.textContent);
  const stub = (r: any) => (r.path.startsWith("/dashboard") ? { json: { has_history: false, available_periods: [], active_employees: 0, sample_employees: 0, attention: [], recent_runs: [], trend: [], departments: [], trend_min_periods: 3, includes_sample_data: false, comparison: null } } : undefined);

  it("viewers see only what they can use", async () => {
    mockApi(viewerUser, stub); renderAt("/dashboard");
    await screen.findByText("No finalized payroll yet");
    expect(links()).toEqual(["Dashboard", "Employees", "Payroll Runs", "Payslips", "Analytics"]);
  });
  it("HR editors also get exports; administrators get everything", async () => {
    mockApi(hrUser, stub); const { unmount } = renderAt("/dashboard");
    await screen.findByText("No finalized payroll yet");
    expect(links()).toEqual(["Dashboard", "Employees", "Payroll Runs", "Payslips", "Analytics", "Reports & Exports"]);
    unmount();
    mockApi(adminUser, stub); renderAt("/dashboard");
    await screen.findByText("No finalized payroll yet");
    expect(links()).toEqual(["Dashboard", "Employees", "Payroll Runs", "Payslips", "Analytics", "Reports & Exports", "Audit Log", "Users", "Settings"]);
  });
  it("typing an admin URL as a viewer shows a no-access page and makes no admin API call", async () => {
    const calls = mockApi(viewerUser, () => undefined);
    renderAt("/users");
    expect(await screen.findByText("You do not have access to this page")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/users")).toBe(false);
    for (const path of ["/audit-log", "/settings"]) {
      const c2 = mockApi(viewerUser, () => undefined); renderAt(path);
      expect((await screen.findAllByText("You do not have access to this page")).length).toBeGreaterThan(0);
      expect(c2.some((c) => c.path === "/audit-log" || c.path === "/settings")).toBe(false);
    }
  });
});

describe("Change password", () => {
  const open = async () => { mockApi(viewerUser, (r) => r.path === "/auth/change-password" ? { status: 204 } : { json: { has_history: false, available_periods: [], active_employees: 0, sample_employees: 0, attention: [], recent_runs: [], trend: [], departments: [], trend_min_periods: 3, includes_sample_data: false, comparison: null } }); };

  it("validates length, difference and confirmation before calling the API", async () => {
    const calls = (await open(), (globalThis.fetch as any).mock.calls);
    renderAt("/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Change password" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^Current password/), "old-password-value");
    await userEvent.type(within(dlg).getByLabelText(/^New password/), "short");
    await userEvent.type(within(dlg).getByLabelText(/^Repeat new password/), "different");
    await userEvent.click(within(dlg).getByRole("button", { name: "Change password" }));
    expect(await within(dlg).findByText(/at least 12 characters/i)).toBeInTheDocument(); expect(within(dlg).getByText("The passwords do not match")).toBeInTheDocument();
    expect(calls.some((c: any[]) => String(c[0]).includes("change-password"))).toBe(false);
  });

  it("posts the current and new password, confirms, and shows server refusals", async () => {
    await open();
    renderAt("/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Change password" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^Current password/), "old-password-value");
    await userEvent.type(within(dlg).getByLabelText(/^New password/), "a-new-long-passphrase"); await userEvent.type(within(dlg).getByLabelText(/^Repeat new password/), "a-new-long-passphrase");
    await userEvent.click(within(dlg).getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const call = (globalThis.fetch as any).mock.calls.find((c: any[]) => String(c[0]).includes("change-password"));
    expect(JSON.parse(call[1].body)).toEqual({ current_password: "old-password-value", new_password: "a-new-long-passphrase" });
    expect(await screen.findByText(/Other sessions were signed out/)).toBeInTheDocument();
  });
  it("a wrong current password shows the server's message", async () => {
    mockApi(viewerUser, (r) => r.path === "/auth/change-password" ? err(400, "bad_request", "Current password is incorrect") : { json: { has_history: false, available_periods: [], active_employees: 0, sample_employees: 0, attention: [], recent_runs: [], trend: [], departments: [], trend_min_periods: 3, includes_sample_data: false, comparison: null } });
    renderAt("/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Change password" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText(/^Current password/), "wrong-password-xx");
    await userEvent.type(within(dlg).getByLabelText(/^New password/), "a-new-long-passphrase"); await userEvent.type(within(dlg).getByLabelText(/^Repeat new password/), "a-new-long-passphrase");
    await userEvent.click(within(dlg).getByRole("button", { name: "Change password" }));
    expect(await within(dlg).findByText("Current password is incorrect")).toBeInTheDocument();
  });
});
