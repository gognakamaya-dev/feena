def entry(c, start, end, project="Apollo"):
    return c.post("/api/entries", {"project": project, "start_at": start, "end_at": end})


def test_happy_path(h):
    m = h.member()
    s, e = entry(m, "2026-03-16T09:00", "2026-03-16T12:30")
    assert s == 201 and e["minutes"] == 210
    assert entry(m, "2026-03-17T00:00", "2026-03-17T20:00")[0] == 400
    m.ok("POST", "/api/clock-in")
    assert m.post("/api/clock-in")[0] == 409
    assert h.admin().ok("GET", "/api/reports/weekly?week_start=2026-03-09")["users"]["2"]["overtime"] == 0


def test_TT_001_end_must_follow_start(h):
    assert entry(h.member(), "2026-03-16T12:00", "2026-03-16T09:00")[0] == 400


def test_TT_002_total_hours_keeps_fraction(h):
    assert h.fe("summarize", "entries", [{"minutes": 90}, {"minutes": 60}]) == "Total hours: 2.5"


def test_TT_003_manual_entries_cannot_overlap(h):
    m = h.member()
    assert entry(m, "2026-03-16T09:00", "2026-03-16T11:00")[0] == 201
    assert entry(m, "2026-03-16T10:00", "2026-03-16T12:00")[0] == 409


def test_TT_004_only_admins_approve_timesheets(h):
    m = h.member()
    m.ok("POST", "/api/timesheets/submit", {"week_start": "2026-03-09"})
    assert m.post("/api/timesheets/approve", {"user_id": 2, "week_start": "2026-03-09"})[0] == 403


def test_TT_005_approved_weeks_are_locked(h):
    m = h.member()
    m.ok("POST", "/api/timesheets/submit", {"week_start": "2026-03-09"})
    h.admin().ok("POST", "/api/timesheets/approve", {"user_id": 2, "week_start": "2026-03-09"})
    eid = h.sql("SELECT id FROM entries WHERE user_id=2 LIMIT 1")[0]["id"]
    assert m.put(f"/api/entries/{eid}", {"end_at": "2026-03-09T23:00"})[0] == 409


def test_TT_006_overnight_entries_split_across_weeks(h):
    m = h.member()
    entry(m, "2026-03-15T22:00", "2026-03-16T04:00")  # Sunday night into Monday: 2h + 4h
    assert h.admin().ok("GET", "/api/reports/weekly?week_start=2026-03-16")["users"]["2"]["hours"] == 4
