def submit(h, slug, email, answers):
    return h.anon().post(f"/api/public/{slug}/submit", {"email": email, "answers": answers})


def test_response_limit_enforced(h):
    for i in range(3):
        assert submit(h, "signup", f"p{i}@x.test", {"3": "n", "4": "veg"})[0] == 201
    assert submit(h, "signup", "p9@x.test", {"3": "n", "4": "veg"})[0] == 409


def test_happy_path(h):
    assert submit(h, "feedback", "new@example.test", {"1": 5})[0] == 201
    assert h.admin().ok("GET", "/api/forms/1/summary")["responses"] == 13
    assert submit(h, "draft-survey", "a@b.test", {})[0] == 404


def test_FS_001_email_validation_requires_domain(h):
    assert h.fe("validate", "submit", {"email": "bob@"}) != []


def test_FS_002_required_number_accepts_zero(h):
    assert submit(h, "feedback", "zero@example.test", {"1": 0})[0] == 201


def test_FS_003_form_open_through_closing_day(h):
    c = h.admin()
    f = c.ok("POST", "/api/forms", {"title": "Today", "slug": "today", "closes_at": "2026-03-15"})
    c.ok("POST", f"/api/forms/{f['id']}/fields", {"label": "Q", "type": "text"})
    c.ok("POST", f"/api/forms/{f['id']}/publish")
    assert submit(h, "today", "a@x.test", {})[0] == 201


def test_FS_004_responses_scoped_to_org(h):
    assert h.other().get("/api/forms/1/responses")[0] == 404


def test_FS_005_deleted_responses_free_capacity(h):
    for i in range(3):
        submit(h, "signup", f"p{i}@x.test", {"3": "n", "4": "veg"})
    rid = h.sql("SELECT id FROM responses WHERE form_id=2 LIMIT 1")[0]["id"]
    h.admin().ok("DELETE", f"/api/responses/{rid}")
    assert submit(h, "signup", "late@x.test", {"3": "n", "4": "veg"})[0] == 201


def test_FS_006_duplicate_email_is_case_insensitive(h):
    assert submit(h, "feedback", "Dup@Example.test", {"1": 4})[0] == 201
    assert submit(h, "feedback", "dup@example.test", {"1": 4})[0] == 409
