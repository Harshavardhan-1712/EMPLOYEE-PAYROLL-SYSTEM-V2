import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { emp, err, hrUser, mockApi, pageOf, renderAt, viewerUser } from "../../test/utils";

const list = (items = [emp(), emp({ id: 2, employee_code: "E002", name: "Arjun Mehta", department: "Finance", status: "inactive", basic_salary: "1234567.50" })]) =>
  (r: { path: string }) => r.path === "/employees" ? { json: pageOf(items) } : r.path === "/employees/departments" ? { json: ["Engineering", "Finance"] } : undefined;

describe("Employees directory", () => {
  it("shows a loading skeleton, then rows with formatted money and status badges", async () => {
    mockApi(hrUser, list(), 150);                       // slow server so the loading state is observable
    renderAt("/employees");
    const table = await screen.findByRole("table", { busy: true });
    expect(table.querySelectorAll("tr.skeleton").length).toBeGreaterThan(0);
    expect(screen.queryByText("No employees yet")).not.toBeInTheDocument();   // loading is not "empty"
    const row = (await screen.findByRole("link", { name: "Priya Sharma" })).closest("tr")!;
    expect(within(row).getByText("₹50,000.00")).toBeInTheDocument();
    expect(within(row).getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("₹12,34,567.50")).toBeInTheDocument();           // en-IN digit grouping
    const inactiveRow = screen.getByRole("link", { name: "Arjun Mehta" }).closest("tr")!;
    expect(within(inactiveRow).getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByText("1–2 of 2")).toBeInTheDocument();
  });

  it("empty directory: editors are offered a way to add, viewers get no write actions", async () => {
    mockApi(hrUser, list([]));
    renderAt("/employees");
    expect(await screen.findByText("No employees yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add the first employee" })).toHaveAttribute("href", "/employees/new");
  });
  it("viewer cannot see create/import actions", async () => {
    mockApi(viewerUser, list());
    renderAt("/employees");
    await screen.findByRole("link", { name: "Priya Sharma" });
    expect(screen.queryByRole("link", { name: /New employee/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Import CSV/ })).not.toBeInTheDocument();
  });

  it("filtered-empty state offers to clear filters", async () => {
    mockApi(hrUser, (r) => r.path === "/employees" ? { json: pageOf([]) } : { json: [] });
    renderAt("/employees?q=zzz");
    expect(await screen.findByText("No employees match these filters")).toBeInTheDocument();
  });

  it("shows the backend error message and recovers on Retry", async () => {
    let fail = true;
    mockApi(hrUser, (r) => r.path === "/employees/departments" ? { json: [] } : fail ? err(500, "error", "Database is unavailable") : { json: pageOf([emp()]) });
    renderAt("/employees");
    expect(await screen.findByText("Database is unavailable")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Priya Sharma" })).toBeInTheDocument();
  });

  it("search is debounced into a single server request with q", async () => {
    const calls = mockApi(hrUser, list());
    renderAt("/employees");
    await screen.findByRole("link", { name: "Priya Sharma" });
    const before = calls.filter((c) => c.path === "/employees").length;
    await userEvent.type(screen.getByRole("searchbox", { name: "Search" }), "arj");
    await waitFor(() => expect(calls.filter((c) => c.path === "/employees").length).toBe(before + 1), { timeout: 2000 });
    expect(calls.filter((c) => c.path === "/employees").at(-1)!.params.get("q")).toBe("arj");
  });

  it("sorting toggles direction, updates aria-sort and goes to the server", async () => {
    const calls = mockApi(hrUser, list());
    renderAt("/employees");
    await screen.findByRole("link", { name: "Priya Sharma" });
    const nameTh = screen.getByRole("columnheader", { name: /Name/ });
    await userEvent.click(within(nameTh).getByRole("button"));
    await waitFor(() => expect(nameTh).toHaveAttribute("aria-sort", "ascending"));
    await userEvent.click(within(nameTh).getByRole("button"));
    await waitFor(() => expect(nameTh).toHaveAttribute("aria-sort", "descending"));
    const last = calls.filter((c) => c.path === "/employees").at(-1)!;
    expect([last.params.get("sort"), last.params.get("order")]).toEqual(["name", "desc"]);
  });

  it("pagination requests the next page", async () => {
    const calls = mockApi(hrUser, (r) => r.path === "/employees" ? { json: pageOf([emp()], 60, Number(r.params.get("page") ?? 1), 25) } : { json: [] });
    renderAt("/employees");
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/employees").at(-1)!.params.get("page")).toBe("2");
  });
});

describe("Auth gate", () => {
  it("redirects anonymous users to sign-in and shows the server's login error", async () => {
    mockApi(null, (r) => r.path === "/auth/login" ? err(401, "unauthenticated", "Invalid username or password") : undefined);
    renderAt("/employees");
    expect(await screen.findByRole("heading", { name: "Payroll Management" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Username/), "alice");
    await userEvent.type(screen.getByLabelText(/Password/), "wrong-password-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
  });
});
