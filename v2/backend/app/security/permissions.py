"""Role -> permission matrix. Enforced server-side by deps.require()."""
ROLES = ("viewer", "hr_editor", "payroll_approver", "admin")

_VIEW = {"employees:read", "payroll:read", "analytics:read", "payslips:read"}
_HR = _VIEW | {"employees:write", "employees:import", "payroll:run", "reports:export"}
_APPROVER = _VIEW | {"payroll:run", "payroll:review", "payroll:finalize", "payroll:reverse", "reports:export"}
_ADMIN = _HR | _APPROVER | {"audit:read", "settings:read", "settings:write", "users:manage"}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(_VIEW),
    "hr_editor": frozenset(_HR),
    "payroll_approver": frozenset(_APPROVER),
    "admin": frozenset(_ADMIN),
}


def has_permission(role: str, perm: str) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())
