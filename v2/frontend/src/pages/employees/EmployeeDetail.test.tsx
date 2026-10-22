import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { emp, err, hrUser, mockApi, renderAt, viewerUser } from "../../test/utils";

describe("Employee detail", () => {
  it("renders formatted details; viewers get no edit/deactivate actions", async () => {
    mockApi(viewerUser, (r) => r.path === "/employees/1" ? { json: emp() } : undefined);
    renderAt("/employees/1");
    expect(await screen.findByRole("heading", { name: "Priya Sharma" })).toBeInTheDocument();
    expect(screen.getByText("₹2,500.50")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Edit/ })).not.toBeInTheDocument();
  });

  it("deactivation requires confirmation; cancelling sends nothing", async () => {
    const calls = mockApi(hrUser, (r) => r.path === "/employees/1" ? { json: emp() } : undefined);
    renderAt("/employees/1");
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate" }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText(/historical payroll data are kept/)).toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("confirming deactivates via the API and refreshes the status", async () => {
    let status: "active" | "inactive" = "active";
    const calls = mockApi(hrUser, (r) => {
      if (r.path === "/employees/1/deactivate") { status = "inactive"; return { json: emp({ status }) }; }
      if (r.path === "/employees/1") return { json: emp({ status }) };
      return undefined;
    });
    renderAt("/employees/1");
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByRole("button", { name: "Reactivate" })).toBeInTheDocument();
    expect(screen.getByText(/left out of new payroll runs/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/employees/1/deactivate")).toBe(true);
  });

  it("shows the backend error if the action fails", async () => {
    mockApi(hrUser, (r) => r.path === "/employees/1/deactivate" ? err(403, "forbidden", "You do not have permission to perform this action") : { json: emp() });
    renderAt("/employees/1");
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Deactivate" }));
    expect(await screen.findByText("You do not have permission to perform this action")).toBeInTheDocument();
  });

  it("flags sample data distinctly", async () => {
    mockApi(hrUser, () => ({ json: emp({ is_sample: true }) }));
    renderAt("/employees/1");
    expect(await screen.findByText(/sample data, not a real employee record/)).toBeInTheDocument();
  });
});
