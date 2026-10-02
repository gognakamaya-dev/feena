def new(c, amount=1000, receipt=None, on="2026-03-10", cat="meals"):
    return c.ok("POST", "/api/expenses", {"category": cat, "amount_cents": amount, "incurred_on": on, "receipt_url": receipt})


def test_happy_path(h):
    m, a = h.member(), h.admin()
    e = new(m)
    m.ok("POST", f"/api/expenses/{e['id']}/submit")
    assert a.ok("POST", f"/api/expenses/{e['id']}/approve")["status"] == "approved"
    assert a.ok("POST", f"/api/expenses/{e['id']}/reimburse")["status"] == "reimbursed"
    assert m.post(f"/api/expenses/{e['id']}/approve")[0] == 403


def test_EX_001_zero_amount_rejected_in_form(h):
    assert h.fe("validate", "expense", {"amount_cents": 0}) != []


def test_EX_002_receipt_required_at_threshold(h):
    m = h.member()
    e = new(m, amount=5000)
    assert m.post(f"/api/expenses/{e['id']}/submit")[0] == 400


def test_EX_003_members_cannot_read_colleagues_expenses(h):
    own = new(h.admin())
    assert h.member().get(f"/api/expenses/{own['id']}")[0] == 404


def test_EX_004_cannot_approve_own_expense(h):
    a = h.admin()
    e = new(a)
    a.ok("POST", f"/api/expenses/{e['id']}/submit")
    assert a.post(f"/api/expenses/{e['id']}/approve")[0] == 403


def test_EX_005_rejected_expenses_leave_budget(h):
    m, a = h.member(), h.admin()
    before = a.ok("GET", "/api/budgets/status")["meals"]["spent_cents"]
    e = new(m, amount=4000)
    m.ok("POST", f"/api/expenses/{e['id']}/submit")
    a.ok("POST", f"/api/expenses/{e['id']}/reject", {"reason": "personal"})
    assert a.ok("GET", "/api/budgets/status")["meals"]["spent_cents"] == before


def test_EX_006_report_includes_month_end(h):
    m, a = h.member(), h.admin()
    e = new(m, amount=2000, on="2026-03-31", cat="software")
    m.ok("POST", f"/api/expenses/{e['id']}/submit")
    a.ok("POST", f"/api/expenses/{e['id']}/approve")
    base = h.sql("SELECT COALESCE(SUM(amount_cents),0) AS s FROM expenses WHERE org_id=1 AND category='software' AND status IN ('approved','reimbursed') AND incurred_on LIKE '2026-03%'")[0]["s"]
    assert a.ok("GET", "/api/reports/by-category?month=2026-03")["categories"]["software"] == base
