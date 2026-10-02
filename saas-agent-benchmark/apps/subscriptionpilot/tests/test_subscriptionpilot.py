def sub(c, cust, plan, **kw):
    return c.post("/api/subscriptions", {"customer_id": cust, "plan_id": plan, **kw})


def test_happy_path(h):
    c = h.admin()
    s, r = sub(c, 5, 2)
    assert s == 201 and r["status"] == "active" and r["invoices"][0]["amount_cents"] == 3000
    assert r["period_end"] == "2026-04-15"
    r2 = c.ok("POST", f"/api/subscriptions/{r['id']}/cancel", {"at_period_end": False})
    assert r2["status"] == "canceled"
    assert c.ok("GET", "/api/reports/mrr")["mrr_cents"] == 1000 + 3000 + 2500


def test_SUB_001_no_duplicate_active_subscription(h):
    c = h.admin()
    sub(c, 5, 1)
    assert sub(c, 5, 1)[0] == 409


def test_SUB_002_mrr_normalises_annual_plans(h):
    items = [{"status": "active", "price_cents": 1200, "interval": "year"}, {"status": "active", "price_cents": 1000, "interval": "month"}]
    assert h.fe("summarize", "subscriptions", items) == "MRR: $11.00"


def test_SUB_003_coupon_redemption_limit(h):
    c = h.admin()
    assert sub(c, 4, 1, coupon_code="LAUNCH20")[0] == 201
    assert sub(c, 5, 1, coupon_code="LAUNCH20")[0] == 409


def test_SUB_004_trials_are_not_charged(h):
    s, r = sub(h.admin(), 5, 4)
    assert r["status"] == "trialing" and r["invoices"] == []


def test_SUB_005_upgrade_is_prorated(h):
    c = h.admin()
    _, r = sub(c, 5, 1)
    up = c.ok("POST", f"/api/subscriptions/{r['id']}/change-plan", {"plan_id": 2, "effective_on": "2026-03-31"})
    prorations = [i["amount_cents"] for i in up["invoices"] if i["kind"] == "proration"]
    assert prorations == [968]  # 2000 * 15/31


def test_SUB_006_cancel_at_period_end_stops_billing(h):
    c = h.admin()
    _, r = sub(c, 5, 1)
    c.ok("POST", f"/api/subscriptions/{r['id']}/cancel", {"at_period_end": True})
    c.ok("POST", "/api/jobs/renew", {"as_of": "2026-04-16"})
    final = c.ok("GET", f"/api/subscriptions/{r['id']}")
    assert final["status"] == "canceled" and len(final["invoices"]) == 1
