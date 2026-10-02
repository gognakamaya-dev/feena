INV = {"customer_id": 1, "due_date": "2026-04-01", "tax_pct": 10, "discount_pct": 20,
       "items": [{"description": "Work", "qty": 10, "unit_cents": 1000}]}


def mk(c, **kw):
    return c.ok("POST", "/api/invoices", {**INV, **kw})


def test_happy_path_lifecycle(h):
    c = h.admin()
    inv = mk(c, discount_pct=0, tax_pct=0)
    assert inv["status"] == "draft" and inv["total_cents"] == 10000
    c.ok("POST", f"/api/invoices/{inv['id']}/send")
    paid = c.ok("POST", f"/api/invoices/{inv['id']}/payments", {"amount_cents": 4000})
    assert paid["status"] == "partially_paid" and paid["balance_cents"] == 6000
    assert c.ok("POST", f"/api/invoices/{inv['id']}/payments", {"amount_cents": 6000})["status"] == "paid"


def test_roles_and_auth(h):
    assert h.anon().get("/api/invoices")[0] == 401
    assert h.viewer().post("/api/invoices", INV)[0] == 403


def test_INV_001_tax_applies_after_discount(h):
    inv = mk(h.admin())
    # 10000 - 20% = 8000; 10% tax on 8000 = 800
    assert inv["total_cents"] == 8800


def test_INV_002_last_partial_page_reachable(h):
    assert h.fe("pageCount", 23, 10) == 3


def test_INV_003_invoice_requires_items(h):
    assert h.admin().post("/api/invoices", {**INV, "items": []})[0] == 400


def test_INV_004_invoice_tenant_isolation(h):
    assert h.other().get("/api/invoices/1")[0] == 404


def test_INV_005_refund_reopens_invoice(h):
    c = h.admin()
    inv = mk(c, discount_pct=0, tax_pct=0)
    c.ok("POST", f"/api/invoices/{inv['id']}/send")
    p = c.ok("POST", f"/api/invoices/{inv['id']}/payments", {"amount_cents": 10000})
    assert p["status"] == "paid"
    pid = h.sql("SELECT id FROM payments WHERE invoice_id=?", [inv["id"]])[0]["id"]
    r = c.ok("POST", f"/api/invoices/{inv['id']}/payments/{pid}/refund")
    assert r["balance_cents"] == 10000 and r["status"] == "sent"


def test_INV_006_revenue_includes_last_day_of_month(h):
    c = h.admin()
    inv = mk(c, discount_pct=0, tax_pct=0)
    c.ok("POST", f"/api/invoices/{inv['id']}/send")
    c.ok("POST", f"/api/invoices/{inv['id']}/payments", {"amount_cents": 2500, "paid_on": "2026-02-28"})
    assert c.ok("GET", "/api/reports/revenue?month=2026-02")["revenue_cents"] == 2500
