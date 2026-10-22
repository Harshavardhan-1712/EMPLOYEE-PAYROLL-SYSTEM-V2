# ============================================================
# payroll.py — Salary Calculations
# Handles: overtime pay, gross salary, net salary, payroll table
# ============================================================

from tabulate import tabulate
import database as db

# Overtime rate per hour (in ₹ / currency unit)
OVERTIME_RATE = 200


# ──────────────────────────────────────────────
# Core Calculation Functions
# ──────────────────────────────────────────────

def calc_overtime_pay(overtime_hours):
    """Return overtime pay based on hours worked."""
    return overtime_hours * OVERTIME_RATE


def calc_gross_salary(basic_salary, bonus, overtime_hours):
    """
    Gross Salary = Basic Salary + Bonus + Overtime Pay
    """
    overtime_pay = calc_overtime_pay(overtime_hours)
    gross = basic_salary + bonus + overtime_pay
    return gross, overtime_pay


def calc_net_salary(gross_salary, deductions):
    """
    Net Salary = Gross Salary - Deductions
    """
    return gross_salary - deductions


def compute_payroll_for_employee(emp):
    """
    Given a database row (dict-like), return a dict with all computed fields.
    """
    gross, overtime_pay = calc_gross_salary(
        emp["basic_salary"], emp["bonus"], emp["overtime"]
    )
    net = calc_net_salary(gross, emp["deductions"])

    return {
        "emp_id":        emp["emp_id"],
        "name":          emp["name"],
        "department":    emp["department"],
        "designation":   emp["designation"],
        "basic_salary":  emp["basic_salary"],
        "bonus":         emp["bonus"],
        "overtime_pay":  overtime_pay,
        "gross_salary":  gross,
        "deductions":    emp["deductions"],
        "net_salary":    net,
        "attendance":    emp["attendance"],
        "overtime_hrs":  emp["overtime"],
    }


# ──────────────────────────────────────────────
# Single Employee Payslip
# ──────────────────────────────────────────────

def print_payslip(emp_id):
    """Print a formatted payslip for one employee."""
    emp = db.get_employee_by_id(emp_id)
    if not emp:
        print(f"\n❌  Employee ID {emp_id} not found.")
        return

    p = compute_payroll_for_employee(emp)

    print("\n" + "=" * 50)
    print("           EMPLOYEE PAYSLIP")
    print("=" * 50)
    print(f"  Employee ID   : {p['emp_id']}")
    print(f"  Name          : {p['name']}")
    print(f"  Department    : {p['department']}")
    print(f"  Designation   : {p['designation']}")
    print(f"  Attendance    : {p['attendance']} days")
    print(f"  Overtime Hrs  : {p['overtime_hrs']} hrs")
    print("-" * 50)
    print(f"  Basic Salary  : ₹ {p['basic_salary']:>10.2f}")
    print(f"  Bonus         : ₹ {p['bonus']:>10.2f}")
    print(f"  Overtime Pay  : ₹ {p['overtime_pay']:>10.2f}")
    print(f"  Gross Salary  : ₹ {p['gross_salary']:>10.2f}")
    print(f"  Deductions    : ₹ {p['deductions']:>10.2f}")
    print("-" * 50)
    print(f"  NET SALARY    : ₹ {p['net_salary']:>10.2f}")
    print("=" * 50)


# ──────────────────────────────────────────────
# Full Payroll Report
# ──────────────────────────────────────────────

def generate_full_payroll():
    """
    Compute payroll for every employee and print a summary table.
    Returns the list of payroll dicts (for use in analytics / export).
    """
    employees = db.get_all_employees()
    if not employees:
        print("\n⚠️  No employees found in the database.")
        return []

    payroll_list = [compute_payroll_for_employee(emp) for emp in employees]

    # Build table rows
    headers = ["ID", "Name", "Dept", "Basic", "Bonus",
               "OT Pay", "Gross", "Deduct", "Net Salary"]
    rows = []
    for p in payroll_list:
        rows.append([
            p["emp_id"],
            p["name"],
            p["department"],
            f"₹{p['basic_salary']:.0f}",
            f"₹{p['bonus']:.0f}",
            f"₹{p['overtime_pay']:.0f}",
            f"₹{p['gross_salary']:.0f}",
            f"₹{p['deductions']:.0f}",
            f"₹{p['net_salary']:.0f}",
        ])

    print("\n" + "=" * 80)
    print("                       PAYROLL REPORT — ALL EMPLOYEES")
    print("=" * 80)
    print(tabulate(rows, headers=headers, tablefmt="fancy_grid"))

    # Summary KPIs
    total_payroll   = sum(p["net_salary"] for p in payroll_list)
    avg_salary      = total_payroll / len(payroll_list)
    highest         = max(payroll_list, key=lambda x: x["net_salary"])

    print(f"\n  📊 Total Employees     : {len(payroll_list)}")
    print(f"  💰 Total Payroll Exp.  : ₹ {total_payroll:,.2f}")
    print(f"  📈 Average Net Salary  : ₹ {avg_salary:,.2f}")
    print(f"  🏆 Highest Paid        : {highest['name']}  (₹ {highest['net_salary']:,.2f})")

    return payroll_list


# ──────────────────────────────────────────────
# Department-wise Payroll
# ──────────────────────────────────────────────

def department_payroll_report():
    """Print a department-wise salary expense breakdown."""
    employees = db.get_all_employees()
    if not employees:
        print("\n⚠️  No employees found.")
        return

    # Aggregate by department
    dept_data = {}
    for emp in employees:
        p = compute_payroll_for_employee(emp)
        dept = p["department"]
        if dept not in dept_data:
            dept_data[dept] = {"count": 0, "total_net": 0.0}
        dept_data[dept]["count"]     += 1
        dept_data[dept]["total_net"] += p["net_salary"]

    rows = [
        [dept, data["count"], f"₹{data['total_net']:,.2f}",
         f"₹{data['total_net']/data['count']:,.2f}"]
        for dept, data in sorted(dept_data.items())
    ]

    print("\n" + "=" * 60)
    print("          DEPARTMENT-WISE PAYROLL SUMMARY")
    print("=" * 60)
    print(tabulate(rows,
                   headers=["Department", "Employees", "Total Payroll", "Avg Net Salary"],
                   tablefmt="fancy_grid"))
