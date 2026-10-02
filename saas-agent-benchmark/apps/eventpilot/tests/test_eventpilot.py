def reg(h, eid, n, **kw):
    return h.anon().post(f"/api/public/events/{eid}/register", {"name": f"N{n}", "email": f"n{n}@x.test", **kw})


def test_happy_path(h):
    s, r = reg(h, 1, 1, promo_code="SAVE10")
    assert s == 201 and r["status"] == "confirmed" and r["paid_cents"] == 17999
    assert reg(h, 1, 1)[0] == 409
    assert reg(h, 3, 1)[0] == 404


def test_EP_001_email_validated(h):
    assert h.anon().post("/api/public/events/1/register", {"name": "A", "email": "nope"})[0] == 400


def test_EP_002_money_shows_cents(h):
    assert h.fe("formatMoney", 1999) == "$19.99"


def test_EP_003_capacity_not_exceeded(h):
    assert [reg(h, 2, i)[1]["status"] for i in range(3)] == ["confirmed", "confirmed", "waitlisted"]


def test_EP_004_promo_codes_case_insensitive(h):
    assert reg(h, 1, 1, promo_code="save10")[1]["paid_cents"] == 17999


def fill_event_two(h):
    ids = []
    for i, st in enumerate(["confirmed", "confirmed", "waitlisted", "waitlisted"]):
        ids.append(h.app.db.exec("INSERT INTO registrations VALUES(NULL,2,?,?,?,NULL,?,'2026-03-10')", (f"S{i}", f"s{i}@x.test", st, 4900 if st == "confirmed" else 0)))
    return ids


def test_EP_005_waitlist_is_first_come_first_served(h):
    ids = fill_event_two(h)
    h.admin().ok("POST", f"/api/registrations/{ids[0]}/cancel")
    states = {r["id"]: r["status"] for r in h.admin().ok("GET", "/api/events/2/registrations")["items"]}
    assert states[ids[2]] == "confirmed" and states[ids[3]] == "waitlisted"


def test_EP_006_double_cancel_promotes_once(h):
    ids = fill_event_two(h)
    a = h.admin()
    a.ok("POST", f"/api/registrations/{ids[0]}/cancel")
    a.post(f"/api/registrations/{ids[0]}/cancel")
    assert a.ok("GET", "/api/events/2/stats")["confirmed"] == 2
