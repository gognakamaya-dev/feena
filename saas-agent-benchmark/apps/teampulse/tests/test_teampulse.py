def test_happy_path(h):
    m = h.viewer()
    assert m.post("/api/pulse", {"score": 4})[0] == 201
    assert m.post("/api/pulse", {"score": 4})[0] == 409
    assert h.admin().ok("GET", "/api/analytics/engagement")["responses"] == 12


def test_TP_001_score_range_validated(h):
    assert h.viewer().post("/api/pulse", {"score": 9})[0] == 400


def test_TP_002_headcount_summary_excludes_terminated(h):
    assert h.fe("summarize", "employees", [{"status": "active"}, {"status": "terminated"}]) == "Headcount: 1"


def test_TP_003_team_filter_combines_with_search(h):
    items = h.admin().ok("GET", "/api/employees?team_id=1&q=Employee")["items"]
    assert items and all(e["team_id"] == 1 for e in items)


def test_TP_004_salary_band_hidden_from_non_admins(h):
    assert all("salary_band" not in e for e in h.member().ok("GET", "/api/employees")["items"])


def test_TP_005_response_rate_uses_active_headcount(h):
    r = h.admin().ok("GET", "/api/analytics/engagement")
    assert r["response_rate"] == round(11 / 17, 2)


def test_TP_006_rehire_restores_headcount(h):
    a = h.admin()
    before = a.ok("GET", "/api/analytics/headcount")["headcount"]
    a.ok("POST", "/api/employees/5/terminate")
    a.ok("POST", "/api/employees/5/rehire")
    assert a.ok("GET", "/api/analytics/headcount")["headcount"] == before
