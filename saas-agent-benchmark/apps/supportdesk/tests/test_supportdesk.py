def test_happy_path(h):
    c = h.viewer()
    t = c.ok("POST", "/api/tickets", {"subject": "Help", "body": "Please"})
    assert h.admin().ok("POST", f"/api/tickets/{t['id']}/status", {"status": "resolved"})["status"] == "resolved"
    assert h.member().get(f"/api/tickets/{t['id']}")[0] == 200
    assert h.other().get(f"/api/tickets/{t['id']}")[0] == 404


def test_SD_001_priority_validated(h):
    assert h.viewer().post("/api/tickets", {"subject": "x", "body": "y", "priority": "banana"})[0] == 400


def test_SD_002_whitespace_subject_rejected(h):
    assert h.fe("validate", "ticket", {"subject": "   ", "body": "x"}) != []


def test_SD_003_customer_cannot_see_internal_notes(h):
    t = h.viewer().ok("GET", "/api/tickets/1")
    assert all(not r["internal"] for r in t["replies"])


def test_SD_004_search_matches_body_case_insensitively(h):
    items = h.admin().ok("GET", "/api/tickets?q=DETAILS ABOUT: EXPORT")["items"]
    assert len(items) >= 1


def test_SD_005_internal_note_is_not_first_response(h):
    c = h.admin()
    t = c.ok("POST", "/api/tickets", {"subject": "S", "body": "B"})
    c.ok("POST", f"/api/tickets/{t['id']}/replies", {"body": "note to self", "internal": True})
    assert c.ok("GET", f"/api/tickets/{t['id']}")["first_response_at"] is None


def test_SD_006_reopened_ticket_not_counted_resolved(h):
    c = h.viewer()
    t = c.ok("POST", "/api/tickets", {"subject": "S", "body": "B"})
    h.admin().ok("POST", f"/api/tickets/{t['id']}/status", {"status": "resolved"})
    before = h.admin().ok("GET", "/api/reports/summary")["resolved"]
    c.ok("POST", f"/api/tickets/{t['id']}/replies", {"body": "still broken"})
    assert h.admin().ok("GET", "/api/reports/summary")["resolved"] == before - 1
