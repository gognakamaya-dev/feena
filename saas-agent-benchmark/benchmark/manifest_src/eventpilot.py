from ._b import B
APP, PREFIX = "EventPilot", "EP"
BUGS = [
    B(1, "backend", "easy", "low", "registration_validation", "Attendee email is not validated.", "Malformed email", "Register with email 'nope'", "400", "201"),
    B(2, "frontend", "easy", "low", "price_display", "Prices are rounded to whole dollars in the UI.", "Price with cents", "Open Events tab with price 4900/19999", "$199.99", "$200"),
    B(3, "business_logic", "medium", "high", "capacity", "Capacity check allows one more confirmed registration than capacity.", "Event at capacity", "Register 3 attendees for capacity-2 event", "Third waitlisted", "Third confirmed"),
    B(4, "backend", "medium", "medium", "promo_codes", "Promo codes are case-sensitive and silently ignored when case differs.", "Lowercase promo", "Register with promo_code 'save10'", "10% discount", "Full price"),
    B(5, "business_logic", "hard", "high", "waitlist", "Waitlist promotion is LIFO instead of FIFO.", "Two waitlisted attendees", "Fill capacity > Add two waitlisted > Cancel a confirmed registration", "Earliest waitlisted confirmed", "Latest waitlisted confirmed", True),
    B(6, "business_logic", "very_hard", "high", "cancellation", "Cancelling an already cancelled registration promotes another waitlisted attendee, exceeding capacity.", "Repeated cancel call", "Fill capacity + 2 waitlisted > Cancel registration > Cancel same registration again > Read stats", "confirmed stays at capacity", "confirmed exceeds capacity", True),
]
