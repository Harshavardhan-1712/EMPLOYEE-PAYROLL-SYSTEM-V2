import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ImportResult } from "../../api/types";
import { err, hrUser, mockApi, renderAt } from "../../test/utils";

const preview: ImportResult = {
  committed: false, total_rows: 4, valid: 1, duplicates: 2, errors: 1, imported: 0,
  rows: [
    { line: 2, status: "valid", errors: [], employee_code: "A1", name: "Meera Iyer" },
    { line: 3, status: "error", errors: ["basic_salary: Input should be greater than or equal to 0"], employee_code: null, name: null },
    { line: 4, status: "duplicate", errors: ["Duplicate of line 2 in this file"], employee_code: "A1", name: "Dup" },
    { line: 5, status: "duplicate", errors: ["Employee ID already exists (row skipped, not overwritten)"], employee_code: "A3", name: "Divya" },
  ],
};
const csv = () => new File(["employee_code,name\nA1,x"], "emps.csv", { type: "text/csv" });

describe("CSV import", () => {
  it("previews with row-level results and writes nothing until confirmed", async () => {
    const calls = mockApi(hrUser, (r) => (r.path === "/employees/import" ? { json: preview } : undefined));
    renderAt("/employees/import");
    await userEvent.upload(await screen.findByLabelText("CSV file"), csv());
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("1 valid")).toBeInTheDocument();
    expect(screen.getByText("2 duplicate")).toBeInTheDocument(); expect(screen.getByText("1 with errors")).toBeInTheDocument();
    expect(screen.getByText(/basic_salary: Input should be/)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/employees/import")!.params.get("commit")).toBe("false");
    await userEvent.click(screen.getByLabelText(/Show only rows with problems/));
    expect(screen.queryByText("Meera Iyer")).not.toBeInTheDocument();
  });

  it("commit needs confirmation, then sends commit=true and reports the result", async () => {
    const calls = mockApi(hrUser, (r) => (r.path === "/employees/import" ? { json: r.params.get("commit") === "true" ? { ...preview, committed: true, imported: 1 } : preview } : undefined));
    renderAt("/employees/import");
    await userEvent.upload(await screen.findByLabelText("CSV file"), csv());
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    await userEvent.click(await screen.findByRole("button", { name: "Import 1 valid row" }));
    expect(calls.filter((c) => c.params.get("commit") === "true")).toHaveLength(0);            // not yet
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText(/3 other row\(s\) will be skipped/)).toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("button", { name: "Import" }));
    expect(await screen.findByText(/1 employee\(s\) imported; 3 row\(s\) skipped/)).toBeInTheDocument();
    expect(calls.filter((c) => c.params.get("commit") === "true")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();                    // cannot re-submit the same import
  });

  it("disables import when no row is valid", async () => {
    mockApi(hrUser, () => ({ json: { ...preview, valid: 0, rows: preview.rows.slice(1) } }));
    renderAt("/employees/import");
    await userEvent.upload(await screen.findByLabelText("CSV file"), csv());
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByRole("button", { name: "Import 0 valid rows" })).toBeDisabled();
  });

  it("surfaces file-level server errors", async () => {
    mockApi(hrUser, () => err(422, "validation_error", "Missing required column(s): basic_salary"));
    renderAt("/employees/import");
    await userEvent.upload(await screen.findByLabelText("CSV file"), csv());
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByText("Missing required column(s): basic_salary")).toBeInTheDocument();
  });
});
