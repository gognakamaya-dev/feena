from ._b import B
APP, PREFIX = "Bookly", "BK"
BUGS = [
    B(1, "backend", "easy", "medium", "booking_validation", "Appointments can be booked in the past.", "start earlier than current date", "POST appointment for 2026-03-10", "400", "201"),
    B(2, "frontend", "easy", "low", "revenue_summary", "Revenue summary includes cancelled appointments.", "List with cancelled appointments", "Cancel an appointment > View Appointments tab summary", "Revenue only for non-cancelled", "Cancelled prices included"),
    B(3, "business_logic", "medium", "high", "conflict_detection", "Conflict detection treats back-to-back appointments as overlapping (inclusive boundary).", "Second appointment starting exactly when the first ends", "Book 09:00-10:00 > Book 10:00 same staff", "Second booking allowed", "409 time slot unavailable"),
    B(4, "backend", "medium", "medium", "availability", "Availability still hides slots of cancelled appointments.", "Cancelled appointment", "Book 09:00 > Cancel > GET availability", "09:00 available", "09:00 missing"),
    B(5, "security", "medium", "high", "cancel_authorization", "Cancel endpoint is not org scoped; any user can cancel another org's appointment.", "Known appointment id of another org", "As Acme admin POST /api/appointments/<globex id>/cancel", "404", "200 and appointment cancelled"),
    B(6, "business_logic", "hard", "high", "reschedule", "Rescheduling skips conflict detection.", "Move appointment onto another booking", "Book A 09:00 > Book B 11:00 > Reschedule B to 09:30", "409", "200 double booking", True),
]
