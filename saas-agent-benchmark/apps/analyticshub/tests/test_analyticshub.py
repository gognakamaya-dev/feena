def ev(c, name, user=None, ts="2026-03-14T10:00:00"):
    return c.post("/api/events", {"name": name, "user_key": user, "ts": ts})


def test_happy_path(h):
    c = h.member()
    assert ev(c, "signup", "z")[0] == 201
    assert c.ok("GET", "/api/metrics/count?event=signup")["count"] == 21
    assert c.post("/api/events/batch", {"events": [{"name": "a"}, {"name": ""}]})[0] == 400
    assert c.ok("GET", "/api/dashboards/1/data")["widgets"][0]["value"] == 21


def test_AH_001_event_name_required(h):
    assert h.member().post("/api/events", {"name": "  ", "user_key": "u"})[0] == 400


def test_AH_002_total_events_sums_counts(h):
    assert h.fe("summarize", "metrics", [{"event": "a", "count": 3}, {"event": "b", "count": 4}]) == "Total events: 7"


def test_AH_003_to_date_includes_whole_day(h):
    assert h.member().ok("GET", "/api/metrics/count?event=signup&from=2026-03-02&to=2026-03-02")["count"] == 2


def test_AH_004_dashboards_scoped_to_org(h):
    assert h.admin().get("/api/dashboards/2/data")[0] == 404


def test_AH_005_unique_users_ignore_anonymous_events(h):
    assert h.member().ok("GET", "/api/metrics/unique-users?event=pageview")["unique_users"] == 0


def test_AH_006_funnel_respects_step_order(h):
    c = h.member()
    ev(c, "checkout", "late", "2026-03-14T12:00:00")
    ev(c, "cart", "late", "2026-03-14T13:00:00")  # cart AFTER checkout: not a valid funnel pass
    steps = c.ok("GET", "/api/metrics/funnel?steps=cart,checkout")["steps"]
    assert steps[1]["users"] == 0
