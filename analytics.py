# ============================================================
# analytics.py — Data Analytics & Charts
# Handles: matplotlib charts, KPI summaries, attendance analysis
# ============================================================

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os
import database as db
import payroll as pr

# Folder to save chart images
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── Chart style ──────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "#1e1e2e",
    "axes.facecolor":   "#2a2a3e",
    "axes.edgecolor":   "#555577",
    "axes.labelcolor":  "#ccccdd",
    "xtick.color":      "#aaaacc",
    "ytick.color":      "#aaaacc",
    "text.color":       "#ffffff",
    "grid.color":       "#3a3a55",
    "grid.linestyle":   "--",
    "grid.alpha":       0.5,
})

COLORS = ["#7c6af7", "#4ecdc4", "#ff6b6b", "#ffd166", "#06d6a0",
          "#118ab2", "#ef476f", "#ffd166", "#26547c", "#adb5bd"]


# ──────────────────────────────────────────────
# Helper — get payroll data
# ──────────────────────────────────────────────

def _get_payroll_data():
    """Return payroll list or None if empty."""
    employees = db.get_all_employees()
    if not employees:
        print("\n⚠️  No employee data to analyse.")
        return None
    return [pr.compute_payroll_for_employee(emp) for emp in employees]


def _save_and_show(fig, filename):
    path = os.path.join(REPORTS_DIR, filename)
    fig.savefig(path, bbox_inches="tight", dpi=120)
    print(f"\n📁 Chart saved → {path}")
    plt.show()
    plt.close(fig)


# ──────────────────────────────────────────────
# 1. Salary Distribution (horizontal bar)
# ──────────────────────────────────────────────

def salary_distribution_chart():
    """Bar chart showing Net Salary for each employee."""
    data = _get_payroll_data()
    if not data:
        return

    names  = [p["name"] for p in data]
    salaries = [p["net_salary"] for p in data]
    bar_colors = [COLORS[i % len(COLORS)] for i in range(len(names))]

    fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.55)))
    bars = ax.barh(names, salaries, color=bar_colors, height=0.55, edgecolor="#ffffff22")

    for bar, sal in zip(bars, salaries):
        ax.text(bar.get_width() + max(salaries) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"₹{sal:,.0f}", va="center", fontsize=8, color="#ccccdd")

    ax.set_xlabel("Net Salary (₹)")
    ax.set_title("💰 Employee Net Salary Distribution", fontsize=14, pad=12)
    ax.grid(axis="x")
    fig.tight_layout()
    _save_and_show(fig, "salary_distribution.png")


# ──────────────────────────────────────────────
# 2. Department Payroll Comparison (pie + bar)
# ──────────────────────────────────────────────

def department_payroll_chart():
    """Pie chart + bar chart comparing department-wise payroll."""
    data = _get_payroll_data()
    if not data:
        return

    dept_totals = {}
    for p in data:
        dept = p["department"]
        dept_totals[dept] = dept_totals.get(dept, 0) + p["net_salary"]

    depts  = list(dept_totals.keys())
    totals = list(dept_totals.values())
    colors = [COLORS[i % len(COLORS)] for i in range(len(depts))]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("🏢 Department-wise Payroll Comparison", fontsize=14)

    # Pie
    wedges, texts, autotexts = ax1.pie(
        totals, labels=depts, colors=colors,
        autopct="%1.1f%%", startangle=140,
        pctdistance=0.82,
        wedgeprops={"edgecolor": "#1e1e2e", "linewidth": 2}
    )
    for at in autotexts:
        at.set_fontsize(8)
    ax1.set_title("Share of Total Payroll")

    # Bar
    bars = ax2.bar(depts, totals, color=colors, edgecolor="#ffffff22", width=0.55)
    for bar, total in zip(bars, totals):
        ax2.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + max(totals) * 0.01,
                 f"₹{total:,.0f}", ha="center", fontsize=8, color="#ccccdd")
    ax2.set_ylabel("Total Net Payroll (₹)")
    ax2.set_title("Total Expense per Department")
    ax2.grid(axis="y")

    fig.tight_layout()
    _save_and_show(fig, "department_payroll.png")


# ──────────────────────────────────────────────
# 3. Attendance Analysis (bar chart)
# ──────────────────────────────────────────────

def attendance_analysis_chart():
    """Bar chart of attendance days per employee."""
    data = _get_payroll_data()
    if not data:
        return

    names      = [p["name"] for p in data]
    attendance = [p["attendance"] for p in data]
    max_days   = max(attendance) if attendance else 30

    bar_colors = ["#06d6a0" if a >= max_days * 0.9
                  else "#ffd166" if a >= max_days * 0.7
                  else "#ef476f"
                  for a in attendance]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(names, attendance, color=bar_colors, edgecolor="#ffffff22", width=0.6)

    for bar, days in zip(bars, attendance):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.3,
                str(days), ha="center", fontsize=8, color="#ccccdd")

    ax.set_ylabel("Attendance (Days)")
    ax.set_title("📅 Employee Attendance Analysis", fontsize=14, pad=12)
    ax.set_ylim(0, max_days + max_days * 0.15)
    ax.grid(axis="y")

    # Legend
    legend_patches = [
        mpatches.Patch(color="#06d6a0", label="Excellent (≥90%)"),
        mpatches.Patch(color="#ffd166", label="Average (70-89%)"),
        mpatches.Patch(color="#ef476f", label="Poor (<70%)"),
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=8)

    plt.xticks(rotation=20, ha="right")
    fig.tight_layout()
    _save_and_show(fig, "attendance_analysis.png")


# ──────────────────────────────────────────────
# 4. Bonus vs Deduction Comparison
# ──────────────────────────────────────────────

def bonus_vs_deduction_chart():
    """Grouped bar chart comparing bonus and deductions per employee."""
    data = _get_payroll_data()
    if not data:
        return

    names      = [p["name"] for p in data]
    bonuses    = [p["bonus"] for p in data]
    deductions = [p["deductions"] for p in data]

    x = range(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    b1 = ax.bar([i - width/2 for i in x], bonuses,    width, label="Bonus",      color="#4ecdc4", edgecolor="#ffffff22")
    b2 = ax.bar([i + width/2 for i in x], deductions, width, label="Deductions", color="#ff6b6b", edgecolor="#ffffff22")

    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=20, ha="right")
    ax.set_ylabel("Amount (₹)")
    ax.set_title("🎯 Bonus vs Deduction per Employee", fontsize=14, pad=12)
    ax.legend()
    ax.grid(axis="y")

    fig.tight_layout()
    _save_and_show(fig, "bonus_vs_deduction.png")


# ──────────────────────────────────────────────
# 5. KPI Summary Dashboard (text)
# ──────────────────────────────────────────────

def kpi_summary():
    """Print key payroll KPIs to the console."""
    data = _get_payroll_data()
    if not data:
        return

    total_emp      = len(data)
    total_payroll  = sum(p["net_salary"] for p in data)
    avg_salary     = total_payroll / total_emp
    highest        = max(data, key=lambda x: x["net_salary"])
    lowest         = min(data, key=lambda x: x["net_salary"])
    total_bonus    = sum(p["bonus"] for p in data)
    total_deduct   = sum(p["deductions"] for p in data)
    avg_attendance = sum(p["attendance"] for p in data) / total_emp

    # Department totals
    dept_totals = {}
    for p in data:
        dept = p["department"]
        dept_totals[dept] = dept_totals.get(dept, 0) + p["net_salary"]

    print("\n" + "=" * 55)
    print("         📊 PAYROLL ANALYTICS — KPI SUMMARY")
    print("=" * 55)
    print(f"  👥 Total Employees         : {total_emp}")
    print(f"  💰 Total Payroll Expense   : ₹ {total_payroll:>12,.2f}")
    print(f"  📈 Average Net Salary      : ₹ {avg_salary:>12,.2f}")
    print(f"  🏆 Highest Paid            : {highest['name']}  (₹ {highest['net_salary']:,.2f})")
    print(f"  📉 Lowest Paid             : {lowest['name']}  (₹ {lowest['net_salary']:,.2f})")
    print(f"  🎁 Total Bonuses Paid      : ₹ {total_bonus:>12,.2f}")
    print(f"  ✂️  Total Deductions        : ₹ {total_deduct:>12,.2f}")
    print(f"  📅 Avg Attendance          : {avg_attendance:.1f} days")
    print("-" * 55)
    print("  🏢 Department-wise Expense:")
    for dept, total in sorted(dept_totals.items(), key=lambda x: -x[1]):
        print(f"       {dept:<20} ₹ {total:>10,.2f}")
    print("=" * 55)
