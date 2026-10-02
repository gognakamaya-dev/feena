from ._b import B
APP, PREFIX = "SupportDesk", "SD"
BUGS = [
    B(1, "backend", "easy", "low", "ticket_validation", "Ticket priority is not validated.", "priority outside low/normal/high/urgent", "POST ticket priority 'banana'", "400", "201"),
    B(2, "frontend", "easy", "low", "ticket_form_validation", "Subject validation accepts whitespace-only subjects.", "Subject of spaces", "Enter '   ' as subject", "Validation error", "Passes"),
    B(3, "security", "medium", "critical", "internal_notes", "Customers (viewer role) can read internal notes on their tickets.", "Customer opens ticket with internal reply", "Login as viewer > GET /api/tickets/1", "Only public replies", "Internal note visible"),
    B(4, "backend", "medium", "medium", "ticket_search", "Search only matches subject and is case-sensitive in effect.", "Query text only present in body or different case", "GET /api/tickets?q=DETAILS ABOUT: EXPORT", "Matches body text case-insensitively", "No results"),
    B(5, "business_logic", "hard", "high", "sla_first_response", "Internal notes count as first response.", "Internal note before public reply", "Create ticket > Add internal note > Read first_response_at", "first_response_at stays null", "Timestamp set", True),
    B(6, "business_logic", "very_hard", "medium", "resolved_report", "Reopened tickets still counted as resolved because resolved_at is not cleared on customer reopen.", "Customer replies to resolved ticket", "Resolve ticket > Read report > Customer replies > Read report", "Resolved count decreases", "Resolved count unchanged", True),
]
