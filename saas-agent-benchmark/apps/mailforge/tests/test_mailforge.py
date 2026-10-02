def test_happy_path(h):
    c = h.admin()
    camp = c.ok("POST", "/api/campaigns", {"list_id": 1, "subject": "S", "body": "B"})
    sent = c.ok("POST", f"/api/campaigns/{camp['id']}/send")
    assert sent["status"] == "sent" and c.post(f"/api/campaigns/{camp['id']}/send")[0] == 409
    assert h.anon().post("/api/track/open/%d/1" % camp["id"])[0] == 200
    assert c.ok("GET", f"/api/campaigns/{camp['id']}/stats")["opens"] == 1


def test_MF_001_email_format_validated(h):
    assert h.admin().post("/api/lists/1/subscribers", {"email": "not-an-email"})[0] == 400


def test_MF_002_total_recipients_summary(h):
    assert h.fe("summarize", "campaigns", [{"recipient_count": 10}, {"recipient_count": 5}]) == "Total recipients: 15"


def test_MF_003_send_skips_unsubscribed(h):
    c = h.admin()
    camp = c.ok("POST", "/api/campaigns", {"list_id": 1, "subject": "S", "body": "B"})
    assert c.ok("POST", f"/api/campaigns/{camp['id']}/send")["recipient_count"] == 6


def test_MF_004_stats_scoped_to_org(h):
    assert h.admin().get("/api/campaigns/3/stats")[0] == 404


def test_MF_005_unsubscribed_contacts_stay_unsubscribed(h):
    c = h.admin()
    s = c.ok("POST", "/api/lists/1/subscribers", {"email": "new@example.test"})
    c.ok("POST", f"/api/subscribers/{s['id']}/unsubscribe")
    c.post("/api/lists/1/subscribers", {"email": "new@example.test"})
    assert h.sql("SELECT status FROM subscribers WHERE id=?", [s["id"]])[0]["status"] == "unsubscribed"


def test_MF_006_scheduler_honours_utc_offsets(h):
    c = h.admin()
    camp = c.ok("POST", "/api/campaigns", {"list_id": 1, "subject": "S", "body": "B"})
    # 11:00+02:00 == 09:00Z, which is before the fixed clock (10:00Z)
    c.ok("POST", f"/api/campaigns/{camp['id']}/schedule", {"scheduled_at": "2026-03-15T11:00:00+02:00"})
    assert camp["id"] in c.ok("POST", "/api/scheduler/run")["sent"]
