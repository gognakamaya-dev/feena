def new(c, items, **kw):
    return c.post("/api/quotes", {"customer_name": "Acme", "valid_until": "2026-05-01", "items": items, **kw})


def item(unit, qty=1, **kw):
    return {"name": "Thing", "unit_cents": unit, "qty": qty, **kw}


def test_happy_path(h):
    c = h.member()
    s, q = new(c, [item(10000, 2)], discount_pct=10)
    assert s == 201 and q["total_cents"] == 18000
    c.ok("POST", f"/api/quotes/{q['id']}/send")
    r = h.anon().post(f"/api/public/quotes/{q['token']}/accept")
    assert r[0] == 200 and h.anon().post(f"/api/public/quotes/{q['token']}/accept")[0] == 409
    assert new(c, [])[0] == 400


def test_QP_001_form_rejects_past_valid_until(h):
    assert h.fe("validate", "quote", {"customer_name": "X", "valid_until": "2000-01-01"}) != []


def test_QP_002_quantity_must_be_positive(h):
    assert new(h.member(), [item(1000, qty=0)])[0] == 400


def test_QP_003_members_limited_to_20_percent_discount(h):
    assert new(h.member(), [item(10000)], discount_pct=40)[0] == 403


def test_QP_004_tier_threshold_is_inclusive(h):
    _, q = new(h.member(), [item(100000)])
    assert q["tier_discount_pct"] == 5 and q["total_cents"] == 95000


def test_QP_005_revised_quote_supersedes_old_link(h):
    c = h.member()
    _, q = new(c, [item(5000)])
    c.ok("POST", f"/api/quotes/{q['id']}/send")
    c.ok("POST", f"/api/quotes/{q['id']}/revise")
    assert h.anon().post(f"/api/public/quotes/{q['token']}/accept")[0] == 409


def test_QP_006_tier_ignores_unselected_optionals(h):
    c = h.member()
    _, q = new(c, [item(90000), item(20000, optional=True)])
    assert q["subtotal_cents"] == 90000 and q["tier_discount_pct"] == 0
