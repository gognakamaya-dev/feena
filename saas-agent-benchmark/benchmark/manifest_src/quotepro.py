from ._b import B
APP, PREFIX = "QuotePro", "QP"
BUGS = [
    B(1, "frontend", "easy", "low", "quote_form", "Quote form accepts a valid-until date in the past.", "valid_until in the past", "Enter valid_until 2000-01-01 in New quote form", "Validation error", "Passes client validation"),
    B(2, "backend", "medium", "medium", "quote_items", "Quote items accept zero or negative quantities.", "qty <= 0", "POST /api/quotes with qty 0 or -2", "400", "201 with zero/negative totals"),
    B(3, "security", "medium", "high", "discount_authorization", "Members can apply discounts above the 20% member limit (up to 50%).", "Member role with discount_pct 40", "As member POST quote discount_pct 40", "403", "201"),
    B(4, "business_logic", "medium", "medium", "tier_discount", "Volume tier threshold is exclusive: a subtotal of exactly 100000 gets no 5% discount.", "Subtotal exactly on tier boundary", "POST quote with one item 100000 cents", "tier 5%, total 95000", "tier 0%, total 100000"),
    B(5, "business_logic", "hard", "high", "revisions", "Revising a sent quote leaves the previous version acceptable through its public link.", "Old public link used after revision", "Create and send quote > Revise > Accept using original token", "409 superseded", "200 accepted outdated quote", True),
    B(6, "business_logic", "very_hard", "high", "optional_items", "Tier discount is computed from all items including unselected optional add-ons.", "Mandatory subtotal below a tier but with optionals above it", "Create quote with 90000 mandatory + 20000 optional (unselected) > Read tier discount", "tier 0%", "tier 5% applied", True),
]
