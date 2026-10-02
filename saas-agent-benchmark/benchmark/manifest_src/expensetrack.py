from ._b import B
APP, PREFIX = "ExpenseTrack", "EX"
BUGS = [
    B(1, "frontend", "easy", "low", "expense_form", "Expense form validation accepts an amount of zero.", "Amount 0", "Enter amount 0 in New expense form", "Validation error", "Passes client validation"),
    B(2, "business_logic", "medium", "medium", "receipt_policy", "Receipt policy off by one: exactly $50.00 does not require a receipt.", "amount_cents == 5000 without receipt", "Create expense 5000 without receipt > Submit", "400 receipt required", "Submitted"),
    B(3, "security", "medium", "high", "expense_access", "Members can read colleagues' expenses by id.", "Direct id access", "Admin creates expense > Member GET /api/expenses/<id>", "404/403", "200"),
    B(4, "business_logic", "medium", "high", "approvals", "Admins can approve their own expenses.", "Admin submitter approves own expense", "Admin creates+submits > Admin approves", "403 separation of duties", "Approved"),
    B(5, "business_logic", "hard", "medium", "budget_status", "Budget status keeps counting rejected expenses.", "Rejected expense", "Submit expense > Reject > GET /api/budgets/status", "spent unchanged after rejection", "spent includes rejected amount", True),
    B(6, "backend", "very_hard", "medium", "category_report", "Monthly report ends at day 30 and drops expenses on the 31st.", "Expense incurred_on the 31st", "Create expense 2026-03-31 > Submit > Approve > GET report month=2026-03", "Included", "Excluded", True),
]
