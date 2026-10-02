from ._b import B
APP, PREFIX = "FormStacker", "FS"
BUGS = [
    B(1, "frontend", "easy", "low", "email_validation", "Client email validation only checks for '@'.", "Email like 'bob@'", "Submit form with email 'bob@'", "Validation error", "Accepted client-side"),
    B(2, "backend", "medium", "medium", "required_validation", "Required number fields reject the value 0 as missing.", "Required number field answered with 0", "Submit feedback form with rating 0", "201 accepted", "400 'Rating is required'"),
    B(3, "backend", "medium", "medium", "form_deadline", "Form is closed on its closing day instead of after it.", "Submission on closes_at date", "Create+publish form closing today > Submit", "Accepted until end of closing day", "410 form closed"),
    B(4, "security", "medium", "critical", "response_access", "Responses endpoint is not scoped to the caller's organization.", "Admin of another org", "Login as globex admin > GET /api/forms/1/responses", "404", "Returns Acme responses incl. emails"),
    B(5, "database", "hard", "high", "response_limit", "Soft-deleted responses still count toward max_responses.", "Form at capacity with a deleted response", "Fill form to its limit > Delete one response > Submit again", "Submission accepted", "409 limit reached", True),
    B(6, "backend", "very_hard", "medium", "duplicate_detection", "Duplicate-submission check is case-sensitive on email.", "Same email in different case", "Submit as Dup@Example.test > Submit as dup@example.test", "409 already submitted", "Second response stored", True),
]
