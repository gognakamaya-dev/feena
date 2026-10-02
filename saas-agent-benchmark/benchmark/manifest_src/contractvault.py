from ._b import B
APP, PREFIX = "ContractVault", "CV"
BUGS = [
    B(1, "frontend", "easy", "low", "contract_form", "Contract form validation does not check end date against start date.", "end_date before start_date", "Enter start 2026-05-01 end 2026-04-01 in New contract form", "Validation error", "Form passes validation"),
    B(2, "backend", "medium", "medium", "expiring_report", "Expiring report excludes contracts ending exactly on the last day of the window.", "end_date == today + days", "GET /api/reports/expiring?days=91 (contract 6 ends day 91)", "Contract included", "Contract missing"),
    B(3, "security", "medium", "critical", "contract_access", "Contract detail endpoint is not scoped to organization.", "Foreign contract id", "As Acme admin GET /api/contracts/7", "404", "200 Globex contract"),
    B(4, "database", "medium", "medium", "versioning", "Changing only the value does not create a new version, so the history misses edits.", "PUT with only value_cents", "GET versions > PUT value_cents > GET versions", "Version count + 1", "Unchanged", True),
    B(5, "business_logic", "hard", "critical", "approvals", "Editing a contract in review leaves previous approvals intact, so a modified contract can be signed.", "Edit after approval", "Request approval > Approver approves > Edit body > Admin signs", "409 re-approval required", "Contract signed", True),
    B(6, "business_logic", "very_hard", "medium", "auto_renewal", "Auto-renew extends from today's date instead of the previous end date.", "Overdue auto-renew contract", "Create auto-renew contract ending 2026-01-31 > Mark signed > Run expire job", "end_date 2027-01-31", "end_date 2027-03-15", True),
]
