def answer(h, sid, token, answers):
    return h.anon().post(f"/api/public/surveys/{sid}/responses", {"token": token, "answers": answers})


def test_happy_path(h):
    assert answer(h, 1, "new", {"1": 5, "2": "Chat"})[0] == 201
    assert answer(h, 1, "new", {"1": 5})[0] == 409
    assert answer(h, 1, "bad", {})[0] == 400
    assert answer(h, 2, "x", {})[0] == 404
    assert h.admin().ok("GET", "/api/surveys/1/analytics")["responses"] == 7


def test_SL_001_rating_range_enforced(h):
    assert answer(h, 1, "r", {"1": 11})[0] == 400


def test_SL_002_average_rating_keeps_decimals(h):
    assert h.fe("summarize", "ratings", [{"value": 4}, {"value": 5}, {"value": 4}]) == "Avg rating: 4.33"


def test_SL_003_closed_surveys_reject_responses(h):
    assert answer(h, 3, "late", {"4": 5})[0] in (403, 409, 410)


def test_SL_004_choice_percentages_use_answered_count(h):
    pct = h.admin().ok("GET", "/api/surveys/1/analytics")["questions"]["2"]["percentages"]
    assert pct == {"Email": 50, "Phone": 25, "Chat": 25}


def test_SL_005_analytics_scoped_to_org(h):
    assert h.admin().get("/api/surveys/4/analytics")[0] == 404


def test_SL_006_no_new_required_questions_after_launch(h):
    assert h.admin().post("/api/surveys/1/questions", {"text": "Mandatory", "type": "text", "required": True})[0] == 409
