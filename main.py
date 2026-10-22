#!/usr/bin/env python3
# ============================================================
# main.py — Employee Payroll Management System
# Entry point: menu-driven console interface
# ============================================================

import os
import sys

# Ensure the project directory is in the import path
sys.path.insert(0, os.path.dirname(__file__))

import database as db
import payroll   as pr
import analytics as an
import export    as ex
from tabulate import tabulate


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def clear():
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def pause():
    """Wait for the user to press Enter before continuing."""
    input("\n  Press Enter to return to menu...")


def get_float(prompt, allow_zero=True):
    """Prompt the user until they enter a valid non-negative number."""
    while True:
        try:
            val = float(input(prompt))
            if val < 0:
                print("  ❌  Value cannot be negative. Try again.")
                continue
            if not allow_zero and val == 0:
                print("  ❌  Value must be greater than zero. Try again.")
                continue
            return val
        except ValueError:
            print("  ❌  Invalid input. Please enter a number.")


def get_int(prompt, allow_zero=True):
    """Prompt the user until they enter a valid non-negative integer."""
    while True:
        try:
            val = int(input(prompt))
            if val < 0:
                print("  ❌  Value cannot be negative. Try again.")
                continue
            if not allow_zero and val == 0:
                print("  ❌  Value must be greater than zero. Try again.")
                continue
            return val
        except ValueError:
            print("  ❌  Invalid input. Please enter an integer.")


def get_str(prompt):
    """Prompt until the user enters a non-empty string."""
    while True:
        val = input(prompt).strip()
        if val:
            return val
        print("  ❌  This field cannot be empty.")


def banner():
    print("""
╔══════════════════════════════════════════════════════╗
║       🏢  EMPLOYEE PAYROLL MANAGEMENT SYSTEM         ║
║              Python + SQLite  |  v1.0                ║
╚══════════════════════════════════════════════════════╝""")


def main_menu():
    print("""
  ┌─────────────────────────────────────┐
  │            MAIN  MENU               │
  ├─────────────────────────────────────┤
  │  1. ➕  Add Employee                │
  │  2. 📋  View All Employees          │
  │  3. ✏️   Update Employee            │
  │  4. 🗑️   Delete Employee            │
  │  5. 💵  Generate Payroll (All)      │
  │  6. 🧾  View Employee Payslip       │
  │  7. 🏢  Department Payroll Report   │
  │  8. 📊  Analytics Dashboard        │
  │  9. 💾  Export Report              │
  │  0. 🚪  Exit                        │
  └─────────────────────────────────────┘""")


# ──────────────────────────────────────────────
# Feature Handlers
# ──────────────────────────────────────────────

def handle_add_employee():
    clear(); banner()
    print("\n  ── ADD NEW EMPLOYEE ──\n")
    emp_id      = get_int("  Employee ID       : ", allow_zero=False)
    name        = get_str("  Full Name         : ")
    department  = get_str("  Department        : ")
    designation = get_str("  Designation       : ")
    basic       = get_float("  Basic Salary (₹)  : ", allow_zero=False)
    bonus       = get_float("  Bonus (₹)         : ")
    deductions  = get_float("  Deductions (₹)    : ")
    attendance  = get_int("  Attendance Days   : ")
    overtime    = get_int("  Overtime Hours    : ")

    db.add_employee(emp_id, name, department, designation,
                    basic, bonus, deductions, attendance, overtime)


def handle_view_employees():
    clear(); banner()
    employees = db.get_all_employees()
    if not employees:
        print("\n  ⚠️  No employees in the database yet.")
        return

    headers = ["ID", "Name", "Department", "Designation",
               "Basic Salary", "Bonus", "Deductions", "Attend.", "OT Hrs"]
    rows = [
        [e["emp_id"], e["name"], e["department"], e["designation"],
         f"₹{e['basic_salary']:,.0f}", f"₹{e['bonus']:,.0f}",
         f"₹{e['deductions']:,.0f}", e["attendance"], e["overtime"]]
        for e in employees
    ]
    print(f"\n  Total employees: {len(employees)}\n")
    print(tabulate(rows, headers=headers, tablefmt="fancy_grid"))


def handle_update_employee():
    clear(); banner()
    print("\n  ── UPDATE EMPLOYEE ──\n")
    emp_id = get_int("  Enter Employee ID to update: ", allow_zero=False)

    emp = db.get_employee_by_id(emp_id)
    if not emp:
        print(f"\n  ❌  Employee ID {emp_id} not found.")
        return

    print(f"\n  Found: {emp['name']} | {emp['department']} | {emp['designation']}")
    print("  (Press Enter to keep existing value)\n")

    def keep_or_update_str(prompt, current):
        val = input(f"  {prompt} [{current}]: ").strip()
        return val if val else current

    def keep_or_update_float(prompt, current):
        val = input(f"  {prompt} [{current}]: ").strip()
        if val:
            try:
                return float(val)
            except ValueError:
                print("  ⚠️  Invalid — keeping old value.")
        return current

    def keep_or_update_int(prompt, current):
        val = input(f"  {prompt} [{current}]: ").strip()
        if val:
            try:
                return int(val)
            except ValueError:
                print("  ⚠️  Invalid — keeping old value.")
        return current

    name        = keep_or_update_str("Name",         emp["name"])
    department  = keep_or_update_str("Department",   emp["department"])
    designation = keep_or_update_str("Designation",  emp["designation"])
    basic       = keep_or_update_float("Basic Salary", emp["basic_salary"])
    bonus       = keep_or_update_float("Bonus",        emp["bonus"])
    deductions  = keep_or_update_float("Deductions",   emp["deductions"])
    attendance  = keep_or_update_int("Attendance Days", emp["attendance"])
    overtime    = keep_or_update_int("Overtime Hours",  emp["overtime"])

    db.update_employee(emp_id, name, department, designation,
                       basic, bonus, deductions, attendance, overtime)


def handle_delete_employee():
    clear(); banner()
    print("\n  ── DELETE EMPLOYEE ──\n")
    emp_id = get_int("  Enter Employee ID to delete: ", allow_zero=False)

    emp = db.get_employee_by_id(emp_id)
    if not emp:
        print(f"\n  ❌  Employee ID {emp_id} not found.")
        return

    print(f"\n  Found: {emp['name']} | {emp['department']}")
    confirm = input("  Are you sure you want to delete? (yes/no): ").strip().lower()
    if confirm == "yes":
        db.delete_employee(emp_id)
    else:
        print("  ↩️  Deletion cancelled.")


def handle_generate_payroll():
    clear(); banner()
    print("\n  ── PAYROLL REPORT — ALL EMPLOYEES ──")
    pr.generate_full_payroll()


def handle_payslip():
    clear(); banner()
    print("\n  ── EMPLOYEE PAYSLIP ──\n")
    emp_id = get_int("  Enter Employee ID: ", allow_zero=False)
    pr.print_payslip(emp_id)


def handle_department_report():
    clear(); banner()
    pr.department_payroll_report()


def handle_analytics():
    clear(); banner()
    print("""
  ── ANALYTICS DASHBOARD ──

  1. 💰 Salary Distribution Chart
  2. 🏢 Department Payroll Chart
  3. 📅 Attendance Analysis
  4. 🎯 Bonus vs Deduction Chart
  5. 📊 KPI Summary (text)
  6. 🔙 Back to Main Menu
""")
    choice = input("  Select chart: ").strip()
    if choice == "1":
        an.salary_distribution_chart()
    elif choice == "2":
        an.department_payroll_chart()
    elif choice == "3":
        an.attendance_analysis_chart()
    elif choice == "4":
        an.bonus_vs_deduction_chart()
    elif choice == "5":
        an.kpi_summary()
    elif choice == "6":
        return
    else:
        print("  ❌  Invalid option.")


def handle_export():
    clear(); banner()
    print("""
  ── EXPORT PAYROLL REPORT ──

  1. 📄 Export to CSV
  2. 📗 Export to Excel (.xlsx)
  3. 🔙 Back
""")
    choice = input("  Select export format: ").strip()
    if choice == "1":
        ex.export_to_csv()
    elif choice == "2":
        ex.export_to_excel()
    elif choice == "3":
        return
    else:
        print("  ❌  Invalid option.")


# ──────────────────────────────────────────────
# Sample Data Seeder (demo only)
# ──────────────────────────────────────────────

def seed_sample_data():
    """Insert sample employees if the table is empty (for demo purposes)."""
    employees = db.get_all_employees()
    if employees:
        return   # already has data

    sample = [
        (101, "Priya Sharma",   "Engineering",   "Senior Developer",    75000, 8000, 3500, 26, 10),
        (102, "Arjun Mehta",    "Engineering",   "Junior Developer",    45000, 3000, 2000, 24,  5),
        (103, "Sneha Kapoor",   "HR",            "HR Manager",          60000, 5000, 2500, 25,  0),
        (104, "Ravi Kumar",     "Finance",       "Accountant",          50000, 4000, 1500, 27,  2),
        (105, "Meera Iyer",     "Marketing",     "Marketing Lead",      55000, 6000, 2000, 23,  4),
        (106, "Karan Joshi",    "Engineering",   "DevOps Engineer",     68000, 7000, 3000, 26,  8),
        (107, "Ananya Pillai",  "Finance",       "Finance Analyst",     52000, 4500, 1800, 25,  3),
        (108, "Vikram Singh",   "HR",            "Recruiter",           42000, 2500, 1200, 22,  0),
        (109, "Divya Nair",     "Marketing",     "Content Strategist",  47000, 3500, 1500, 24,  2),
        (110, "Rohan Gupta",    "Engineering",   "QA Engineer",         49000, 3000, 2000, 26,  6),
    ]
    print("\n  🌱 Seeding sample data...")
    for emp in sample:
        db.add_employee(*emp)
    print("  ✅  Sample data loaded!\n")


# ──────────────────────────────────────────────
# Main Loop
# ──────────────────────────────────────────────

def main():
    # Initialise DB
    db.create_table()

    # Load demo data if DB is empty
    seed_sample_data()

    while True:
        clear()
        banner()
        main_menu()

        choice = input("\n  Enter your choice: ").strip()

        if choice == "1":
            handle_add_employee()
            pause()
        elif choice == "2":
            handle_view_employees()
            pause()
        elif choice == "3":
            handle_update_employee()
            pause()
        elif choice == "4":
            handle_delete_employee()
            pause()
        elif choice == "5":
            handle_generate_payroll()
            pause()
        elif choice == "6":
            handle_payslip()
            pause()
        elif choice == "7":
            handle_department_report()
            pause()
        elif choice == "8":
            handle_analytics()
            pause()
        elif choice == "9":
            handle_export()
            pause()
        elif choice == "0":
            clear()
            print("\n  👋  Thank you for using the Payroll System. Goodbye!\n")
            sys.exit(0)
        else:
            print("\n  ❌  Invalid option. Please choose 0–9.")
            pause()


if __name__ == "__main__":
    main()
