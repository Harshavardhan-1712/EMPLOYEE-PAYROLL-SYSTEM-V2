import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { emp, err, hrUser, mockApi, renderAt } from "../../test/utils";

const base = (r: { path: string }) => (r.path === "/employees/departments" ? { json: ["Engineering"] } : undefined);
const fill = async (label: RegExp | string, value: string) => { const el = screen.getByLabelText(label); await userEvent.clear(el); await userEvent.type(el, value); };

async function fillValid() {
  await screen.findByLabelText(/Employee ID/);          // wait for auth check + form render
  await fill(/Employee ID/, "E100"); await fill(/Full name/, "Meera Iyer"); await fill(/Department/, "Finance");
  await fill(/Designation/, "Analyst"); await fill(/Basic salary/, "45000");
}

describe("Create employee form", () => {
  it("blocks submit and shows field errors when required fields are empty (no request sent)", async () => {
    const calls = mockApi(hrUser, base);
    renderAt("/employees/new");
    await userEvent.click(await screen.findByRole("button", { name: "Create employee" }));
    expect(await screen.findByText("Employee ID is required")).toBeInTheDocument();
    expect(screen.getByText("Basic salary is required")).toBeInTheDocument();
    expect(screen.getByLabelText(/Employee ID/)).toHaveAttribute("aria-invalid", "true");
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("rejects invalid money client-side", async () => {
    mockApi(hrUser, base);
    renderAt("/employees/new");
    await fillValid(); await fill(/Basic salary/, "12.345");
    await userEvent.click(screen.getByRole("button", { name: "Create employee" }));
    expect(await screen.findByText(/non-negative amount with up to 2 decimals/)).toBeInTheDocument();
  });

  it("posts exact decimal strings and lands on the new employee's page", async () => {
    const calls = mockApi(hrUser, (r) => {
      if (r.path === "/employees" && r.method === "POST") return { status: 201, json: emp({ id: 9, employee_code: "E100", name: "Meera Iyer", basic_salary: "45000.00" }) };
      if (r.path === "/employees/9") return { json: emp({ id: 9, employee_code: "E100", name: "Meera Iyer" }) };
      return base(r);
    });
    renderAt("/employees/new");
    await fillValid(); await fill(/Bonus/, "1000.50");
    await userEvent.click(screen.getByRole("button", { name: "Create employee" }));
    expect(await screen.findByRole("heading", { name: "Meera Iyer" })).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toMatchObject({ employee_code: "E100", basic_salary: "45000", bonus: "1000.50", deductions: "0", overtime_hours: "0", attendance_days: 0, joining_date: null });
    expect(typeof (post.body as { basic_salary: unknown }).basic_salary).toBe("string");   // never floats
  });

  it("shows the server's duplicate-ID error on the Employee ID field", async () => {
    mockApi(hrUser, (r) => r.method === "POST" ? err(409, "conflict", "Employee ID 'E100' already exists") : base(r));
    renderAt("/employees/new");
    await fillValid();
    await userEvent.click(screen.getByRole("button", { name: "Create employee" }));
    expect(await screen.findByText("Employee ID 'E100' already exists")).toBeInTheDocument();
    expect(screen.getByLabelText(/Employee ID/)).toHaveAttribute("aria-invalid", "true");
  });

  it("maps server-side validation details onto fields", async () => {
    mockApi(hrUser, (r) => r.method === "POST" ? err(422, "validation_error", "Request validation failed", [{ field: "department", message: "String should have at most 80 characters" }]) : base(r));
    renderAt("/employees/new");
    await fillValid();
    await userEvent.click(screen.getByRole("button", { name: "Create employee" }));
    expect(await screen.findByText("String should have at most 80 characters")).toBeInTheDocument();
  });
});

describe("Edit employee form", () => {
  const setup = (patchResp?: ReturnType<typeof emp>) => mockApi(hrUser, (r) => {
    if (r.path === "/employees/1" && r.method === "GET") return { json: emp() };
    if (r.path === "/employees/1" && r.method === "PATCH") return { json: patchResp ?? emp() };
    return base(r);
  });

  it("locks the ID, and sends only the fields that changed", async () => {
    const calls = setup(emp({ basic_salary: "60000.00" }));
    renderAt("/employees/1/edit");
    expect(await screen.findByLabelText(/Employee ID/)).toBeDisabled();
    await fill(/Basic salary/, "60000");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ basic_salary: "60000" });
  });

  it("does not send a request when nothing changed", async () => {
    const calls = setup();
    renderAt("/employees/1/edit");
    await screen.findByLabelText(/Full name/);
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("No changes to save.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("shows an error state for a missing employee", async () => {
    mockApi(hrUser, (r) => r.path === "/employees/77" ? err(404, "not_found", "Employee not found") : base(r));
    renderAt("/employees/77/edit");
    expect(await screen.findByText("Employee not found")).toBeInTheDocument();
  });
});
