"""Permission catalogue and default role assignments (editable later in Settings)."""

PERMISSIONS: list[tuple[str, str, str]] = [
    # code, label, group
    ("dashboard.view", "View dashboard", "Dashboard"),
    ("sales.view", "View invoices", "Sales"),
    ("sales.create", "Create / edit draft invoices and credit notes", "Sales"),
    ("sales.post", "Post (finalise) invoices", "Sales"),
    ("sales.edit_posted", "Edit posted invoices (before period lock)", "Sales"),
    ("sales.cancel", "Cancel invoices and credit notes", "Sales"),
    ("purchases.view", "View purchase bills", "Purchases"),
    ("purchases.create", "Enter purchase bills and debit notes", "Purchases"),
    ("purchases.verify", "Verify and post purchase bills", "Purchases"),
    ("purchases.edit_posted", "Edit posted bills (before period lock)", "Purchases"),
    ("purchases.cancel", "Cancel bills and debit notes", "Purchases"),
    ("receipts.view", "View receipts", "Payments & Receipts"),
    ("receipts.create", "Record receipts from dealers", "Payments & Receipts"),
    ("receipts.cancel", "Cancel receipts", "Payments & Receipts"),
    ("payments.view", "View payments", "Payments & Receipts"),
    ("payments.create", "Record payments to suppliers", "Payments & Receipts"),
    ("payments.approve", "Approve payments above limit", "Payments & Receipts"),
    ("payments.cancel", "Cancel payments", "Payments & Receipts"),
    ("contra.create", "Record cash/bank transfers", "Payments & Receipts"),
    ("expenses.view", "View expenses", "Expenses"),
    ("expenses.create", "Enter expenses", "Expenses"),
    ("expenses.approve", "Approve / reject expenses above limit", "Expenses"),
    ("expenses.cancel", "Cancel expenses", "Expenses"),
    ("outstanding.view", "View outstanding and statements", "Outstanding"),
    ("reports.view", "View reports", "Reports"),
    ("reports.export", "Export reports (Excel / PDF / Tally)", "Reports"),
    ("masters.view", "View dealers, suppliers, products", "Masters"),
    ("masters.manage", "Add / edit dealers, suppliers, products, banks, categories", "Masters"),
    ("periods.lock", "Lock / unlock accounting months", "Settings"),
    ("settings.manage", "Company profile, numbering, tax and app settings", "Settings"),
    ("users.manage", "Users, roles and permissions", "Settings"),
    ("audit.view", "View audit log", "Settings"),
]

ALL = [p[0] for p in PERMISSIONS]
# audit.view is granted only to roles that should see the audit trail
_VIEW = [p for p in ALL if p.endswith(".view") and p != "audit.view"]

ROLES: dict[str, dict] = {
    "super_admin": {
        "name": "Super Admin",
        "description": "Full access including users, roles and company settings.",
        "permissions": ALL,
    },
    "accounts_manager": {
        "name": "Accounts Manager",
        "description": "Runs the accounts team: approves, verifies, edits posted entries, locks months.",
        "permissions": [p for p in ALL if p not in ("settings.manage", "users.manage")],
    },
    "accountant": {
        "name": "Accountant",
        "description": "Day-to-day entry of invoices, bills, receipts, payments and expenses.",
        "permissions": _VIEW + ["sales.create", "sales.post", "purchases.create", "receipts.create",
                                "payments.create", "contra.create", "expenses.create", "reports.export"],
    },
    "management": {
        "name": "Management (View)",
        "description": "CEO / directors: dashboard, reports, and approvals.",
        "permissions": _VIEW + ["reports.export", "payments.approve", "expenses.approve"],
    },
    "auditor": {
        "name": "Auditor",
        "description": "Read-only access to all records, reports and the audit log.",
        "permissions": _VIEW + ["reports.export", "audit.view"],
    },
}
