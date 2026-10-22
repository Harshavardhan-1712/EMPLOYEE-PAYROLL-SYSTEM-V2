import { ArrowDown, ArrowUp, ChevronsUpDown, Plus, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, qs } from "../../api/client";
import type { Employee, Page } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, EmptyState, ErrorState, LinkButton, PageHeader, SelectField, Spinner, TextField } from "../../components/ds";
import { dateOnly, money } from "../../lib/format";
import { useQuery } from "../../lib/useQuery";

const COLS: { key: string; label: string; num?: boolean }[] = [
  { key: "employee_code", label: "ID" }, { key: "name", label: "Name" }, { key: "department", label: "Department" },
  { key: "designation", label: "Designation" }, { key: "joining_date", label: "Joined" }, { key: "basic_salary", label: "Basic salary", num: true },
];

export function EmployeesPage() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const q = sp.get("q") ?? "", department = sp.get("department") ?? "", status = sp.get("status") ?? "";
  const sort = sp.get("sort") ?? "employee_code", order = sp.get("order") ?? "asc";
  const page = Number(sp.get("page") ?? 1), pageSize = Number(sp.get("page_size") ?? 25);

  const [qInput, setQInput] = useState(q);
  useEffect(() => setQInput(q), [q]);
  useEffect(() => {  // debounce search input into the URL
    if (qInput === q) return;
    const t = setTimeout(() => update({ q: qInput, page: "" }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  function update(patch: Record<string, string>) {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) v ? next.set(k, v) : next.delete(k);
    setSp(next, { replace: true });
  }

  const list = useQuery((signal) => api<Page<Employee>>(`/employees${qs({ q, department, status, sort, order, page, page_size: pageSize })}`, { signal }),
    [q, department, status, sort, order, page, pageSize]);
  const depts = useQuery((signal) => api<string[]>("/employees/departments", { signal }), []);

  const data = list.data;
  const filtered = !!(q || department || status);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const first = data && data.total ? (data.page - 1) * data.page_size + 1 : 0;
  const last = data ? Math.min(data.total, data.page * data.page_size) : 0;

  function toggleSort(key: string) {
    update(sort === key ? { order: order === "asc" ? "desc" : "asc", page: "" } : { sort: key, order: "asc", page: "" });
  }

  return (
    <>
      <PageHeader title="Employees" subtitle="Directory of employees and their standing payroll inputs"
        actions={can("employees:write") && <>
          {can("employees:import") && <LinkButton to="/employees/import"><Upload size={14} aria-hidden="true" /> Import CSV</LinkButton>}
          <LinkButton to="/employees/new" variant="primary"><Plus size={14} aria-hidden="true" /> New employee</LinkButton></>} />

      <div className="toolbar" role="search">
        <TextField className="field--grow" label="Search" type="search" placeholder="Name, ID, department, designation" value={qInput} onChange={(e) => setQInput(e.target.value)} />
        <SelectField label="Department" value={department} onChange={(e) => update({ department: e.target.value, page: "" })}>
          <option value="">All departments</option>{depts.data?.map((d) => <option key={d} value={d}>{d}</option>)}
        </SelectField>
        <SelectField label="Status" value={status} onChange={(e) => update({ status: e.target.value, page: "" })}>
          <option value="">All</option><option value="active">Active</option><option value="inactive">Inactive</option>
        </SelectField>
        {filtered && <Button variant="ghost" onClick={() => { setQInput(""); setSp({}, { replace: true }); }}>Clear filters</Button>}
      </div>

      <div className="panel">
        {list.error && !data ? <ErrorState message={list.error.message} onRetry={list.reload} /> : (
          <>
            {list.error && <div className="card-pad"><ErrorState message={list.error.message} onRetry={list.reload} /></div>}
            <div className={`table-wrap${list.loading && data ? " is-refreshing" : ""}`}>
              <table className="table" aria-busy={list.loading}>
                <caption className="sr-only">Employees</caption>
                <thead><tr>
                  {COLS.map((c) => (
                    <th key={c.key} scope="col" className={c.num ? "num" : undefined} aria-sort={sort === c.key ? (order === "asc" ? "ascending" : "descending") : "none"}>
                      <button className="th-sort" onClick={() => toggleSort(c.key)}>{c.label}
                        {sort === c.key ? (order === "asc" ? <ArrowUp size={12} aria-hidden="true" /> : <ArrowDown size={12} aria-hidden="true" />) : <ChevronsUpDown size={12} aria-hidden="true" />}
                      </button>
                    </th>))}
                  <th scope="col">Status</th>
                </tr></thead>
                <tbody>
                  {!data && list.loading && Array.from({ length: 6 }, (_, i) => (
                    <tr key={i} className="skeleton">{Array.from({ length: 7 }, (_, j) => <td key={j}><span /></td>)}</tr>))}
                  {data?.items.map((e) => (
                    <tr key={e.id} onDoubleClick={() => nav(`/employees/${e.id}`)}>
                      <td className="mono">{e.employee_code}</td>
                      <td><Link to={`/employees/${e.id}`}>{e.name}</Link>{e.is_sample && <> <Badge tone="warning">Sample</Badge></>}</td>
                      <td>{e.department}</td><td>{e.designation}</td><td>{dateOnly(e.joining_date)}</td>
                      <td className="num">{money(e.basic_salary)}</td>
                      <td><Badge tone={e.status === "active" ? "success" : "neutral"}>{e.status === "active" ? "Active" : "Inactive"}</Badge></td>
                    </tr>))}
                </tbody>
              </table>
            </div>
            {!list.loading && data && data.total === 0 && (filtered
              ? <EmptyState title="No employees match these filters" action={<Button onClick={() => { setQInput(""); setSp({}, { replace: true }); }}>Clear filters</Button>}>Try a different search or clear the filters.</EmptyState>
              : <EmptyState title="No employees yet" action={can("employees:write") ? <LinkButton to="/employees/new" variant="primary">Add the first employee</LinkButton> : undefined}>
                  {can("employees:write") ? "Add an employee or import a CSV to get started." : "An HR editor needs to add employees before they appear here."}</EmptyState>)}
            <div className="table-foot">
              <span>{list.loading && data ? <Spinner label="Refreshing" /> : null} {data ? (data.total ? `${first}–${last} of ${data.total}` : "0 results") : ""}</span>
              <div className="pager">
                <label>Rows <select className="select" style={{ width: 64, height: 26 }} value={pageSize} onChange={(e) => update({ page_size: e.target.value, page: "" })}>
                  {[10, 25, 50, 100].map((n) => <option key={n}>{n}</option>)}</select></label>
                <Button size="sm" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>Previous</Button>
                <span>Page {page} of {pages}</span>
                <Button size="sm" disabled={page >= pages} onClick={() => update({ page: String(page + 1) })}>Next</Button>
              </div>
            </div>
          </>)}
      </div>
    </>
  );
}
