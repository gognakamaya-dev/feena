def new(c, **kw):
    return c.ok("POST", "/api/contracts", {"title": "T", "counterparty": "X", "start_date": "2026-01-01", "end_date": "2026-12-31", "body": "v1", **kw})


def test_happy_path(h):
    a = h.admin()
    c = new(a)
    a.ok("POST", f"/api/contracts/{c['id']}/request-approval", {"approver_ids": [2]})
    assert a.post(f"/api/contracts/{c['id']}/sign")[0] == 409
    h.member().ok("POST", f"/api/contracts/{c['id']}/approve")
    assert a.ok("POST", f"/api/contracts/{c['id']}/sign")["status"] == "signed"
    assert a.put(f"/api/contracts/{c['id']}", {"body": "x"})[0] == 409
    assert a.post("/api/contracts", {"title": "T", "counterparty": "X", "start_date": "2026-05-01", "end_date": "2026-01-01"})[0] == 400


def test_CV_001_form_rejects_end_before_start(h):
    assert h.fe("validate", "contract", {"title": "T", "counterparty": "X", "start_date": "2026-05-01", "end_date": "2026-04-01"}) != []


def test_CV_002_expiring_window_is_inclusive(h):
    # contract 6 ends 2026-06-14 = today (2026-03-15) + 91 days
    ids = [x["id"] for x in h.admin().ok("GET", "/api/reports/expiring?days=91")["items"]]
    assert 6 in ids


def test_CV_003_contract_access_scoped_to_org(h):
    assert h.admin().get("/api/contracts/7")[0] == 404


def test_CV_004_value_changes_are_versioned(h):
    a = h.admin()
    before = len(a.ok("GET", "/api/contracts/3/versions")["items"])
    a.ok("PUT", "/api/contracts/3", {"value_cents": 999})
    assert len(a.ok("GET", "/api/contracts/3/versions")["items"]) == before + 1


def test_CV_005_edit_resets_approvals(h):
    a = h.admin()
    c = new(a)
    a.ok("POST", f"/api/contracts/{c['id']}/request-approval", {"approver_ids": [2]})
    h.member().ok("POST", f"/api/contracts/{c['id']}/approve")
    a.ok("PUT", f"/api/contracts/{c['id']}", {"body": "v2 with new liability clause"})
    assert a.post(f"/api/contracts/{c['id']}/sign")[0] == 409


def test_CV_006_auto_renew_extends_from_old_end_date(h):
    a = h.admin()
    c = new(a, start_date="2025-02-01", end_date="2026-01-31", auto_renew=True)
    h.app.db.exec("UPDATE contracts SET status='signed' WHERE id=?", [c["id"]])
    a.ok("POST", "/api/jobs/expire")
    assert a.ok("GET", f"/api/contracts/{c['id']}")["end_date"] == "2027-01-31"
