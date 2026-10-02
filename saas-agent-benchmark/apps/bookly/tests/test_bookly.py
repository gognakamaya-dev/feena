def book(c, start, svc=3, staff=1, name="Zed"):
    return c.post("/api/appointments", {"service_id": svc, "staff_id": staff, "start": start, "customer_name": name, "customer_email": "z@x.test"})


def test_happy_path(h):
    c = h.admin()
    s, a = book(c, "2026-03-20T09:00")
    assert s == 201 and a["end"] == "2026-03-20T10:00"
    assert book(c, "2026-03-20T09:30")[0] == 409
    assert "09:00" not in c.ok("GET", "/api/availability?staff_id=1&service_id=3&date=2026-03-20")["slots"]
    assert book(c, "2026-03-20T08:00")[0] == 400


def test_BK_001_cannot_book_in_the_past(h):
    assert book(h.admin(), "2026-03-10T09:00")[0] == 400


def test_BK_002_summary_ignores_cancelled(h):
    items = [{"status": "booked", "price_cents": 5000}, {"status": "cancelled", "price_cents": 3000}]
    assert h.fe("summarize", "appointments", items) == "Revenue: $50.00"


def test_BK_003_back_to_back_allowed(h):
    c = h.admin()
    assert book(c, "2026-03-20T09:00")[0] == 201
    assert book(c, "2026-03-20T10:00")[0] == 201


def test_BK_004_cancelled_slot_is_available(h):
    c = h.admin()
    _, a = book(c, "2026-03-20T09:00")
    c.ok("POST", f"/api/appointments/{a['id']}/cancel")
    assert "09:00" in c.ok("GET", "/api/availability?staff_id=1&service_id=3&date=2026-03-20")["slots"]


def test_BK_005_cannot_cancel_other_orgs_appointment(h):
    other_id = h.sql("SELECT id FROM appointments WHERE org_id=2")[0]["id"]
    assert h.admin().post(f"/api/appointments/{other_id}/cancel")[0] == 404


def test_BK_006_reschedule_checks_conflicts(h):
    c = h.admin()
    book(c, "2026-03-20T09:00")
    _, b = book(c, "2026-03-20T11:00")
    assert c.post(f"/api/appointments/{b['id']}/reschedule", {"start": "2026-03-20T09:30"})[0] == 409
