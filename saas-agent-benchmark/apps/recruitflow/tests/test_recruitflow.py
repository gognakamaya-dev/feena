def apply(h, job, n):
    return h.anon().post(f"/api/public/jobs/{job}/apply", {"name": f"N{n}", "email": f"n{n}@x.test"})


def test_happy_path(h):
    s, a = apply(h, 1, 1)
    assert s == 201 and apply(h, 1, 1)[0] == 409
    c = h.admin()
    assert c.ok("POST", f"/api/applications/{a['id']}/stage", {"stage": "screen"})["stage"] == "screen"
    assert c.ok("GET", "/api/jobs/1/pipeline")["stages"]["screen"] == 2
    assert c.post(f"/api/applications/5/stage", {"stage": "screen"})[0] == 409


def test_RF_001_closed_jobs_reject_applications(h):
    assert apply(h, 3, 1)[0] == 409


def test_RF_002_active_candidate_summary(h):
    items = [{"stage": "applied"}, {"stage": "rejected"}, {"stage": "hired"}, {"stage": "offer"}]
    assert h.fe("summarize", "applications", items) == "Active candidates: 2"


def test_RF_003_stages_cannot_be_skipped(h):
    _, a = apply(h, 1, 1)
    assert h.admin().post(f"/api/applications/{a['id']}/stage", {"stage": "offer"})[0] == 409


def test_RF_004_application_scoped_to_org(h):
    assert h.admin().get("/api/applications/7")[0] == 404


def test_RF_005_hiring_closes_the_job(h):
    _, a = apply(h, 1, 1)
    c = h.admin()
    for st in ["screen", "interview", "offer", "hired"]:
        c.ok("POST", f"/api/applications/{a['id']}/stage", {"stage": st})
    assert c.ok("GET", "/api/jobs/1/pipeline")["job"]["status"] == "closed"


def test_RF_006_average_ignores_unscored_interviews(h):
    c = h.admin()
    i1 = c.ok("POST", "/api/applications/1/interviews", {"scheduled_at": "2026-03-20T10:00"})
    c.ok("POST", "/api/applications/1/interviews", {"scheduled_at": "2026-03-21T10:00"})
    c.ok("POST", f"/api/interviews/{i1['id']}/feedback", {"score": 5})
    assert c.ok("GET", "/api/applications/1")["average_score"] == 5
