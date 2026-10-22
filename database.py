# ============================================================
# database.py — SQLite Database Operations
# Handles: connection, table creation, CRUD for employees
# ============================================================

import sqlite3
import os

# Path to the database file
DB_PATH = os.path.join(os.path.dirname(__file__), "employee_data.db")


def get_connection():
    """Create and return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # allows dict-style access to rows
    return conn


def create_table():
    """Create the employees table if it doesn't already exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            emp_id      INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL,
            department  TEXT    NOT NULL,
            designation TEXT    NOT NULL,
            basic_salary REAL   NOT NULL,
            bonus        REAL   DEFAULT 0,
            deductions   REAL   DEFAULT 0,
            attendance   INTEGER DEFAULT 0,
            overtime     INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Table ready.")


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────
def add_employee(emp_id, name, department, designation,
                 basic_salary, bonus, deductions, attendance, overtime):
    """Insert a new employee record into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO employees
                (emp_id, name, department, designation,
                 basic_salary, bonus, deductions, attendance, overtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (emp_id, name, department, designation,
              basic_salary, bonus, deductions, attendance, overtime))
        conn.commit()
        print(f"\n✅  Employee '{name}' added successfully!")
        return True
    except sqlite3.IntegrityError:
        print(f"\n❌  Employee ID {emp_id} already exists.")
        return False
    finally:
        conn.close()


# ──────────────────────────────────────────────
# READ
# ──────────────────────────────────────────────
def get_all_employees():
    """Return a list of all employee rows."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM employees ORDER BY emp_id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_employee_by_id(emp_id):
    """Return a single employee row by ID, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM employees WHERE emp_id = ?", (emp_id,))
    row = cursor.fetchone()
    conn.close()
    return row


# ──────────────────────────────────────────────
# UPDATE
# ──────────────────────────────────────────────
def update_employee(emp_id, name, department, designation,
                    basic_salary, bonus, deductions, attendance, overtime):
    """Update all fields for an existing employee."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE employees
        SET name=?, department=?, designation=?,
            basic_salary=?, bonus=?, deductions=?,
            attendance=?, overtime=?
        WHERE emp_id=?
    """, (name, department, designation,
          basic_salary, bonus, deductions,
          attendance, overtime, emp_id))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    if updated:
        print(f"\n✅  Employee ID {emp_id} updated successfully!")
    else:
        print(f"\n❌  Employee ID {emp_id} not found.")
    return updated


# ──────────────────────────────────────────────
# DELETE
# ──────────────────────────────────────────────
def delete_employee(emp_id):
    """Delete an employee record by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM employees WHERE emp_id = ?", (emp_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    if deleted:
        print(f"\n✅  Employee ID {emp_id} deleted successfully!")
    else:
        print(f"\n❌  Employee ID {emp_id} not found.")
    return deleted


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def get_departments():
    """Return a list of distinct department names."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT department FROM employees ORDER BY department")
    depts = [row["department"] for row in cursor.fetchall()]
    conn.close()
    return depts


def employee_exists(emp_id):
    """Check whether an employee ID exists in the database."""
    return get_employee_by_id(emp_id) is not None
