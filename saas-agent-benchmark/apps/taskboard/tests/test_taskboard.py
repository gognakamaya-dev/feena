def test_happy_path(h):
    c = h.admin()
    t = c.ok("POST", "/api/projects/1/tasks", {"title": "New one"})
    assert c.ok("PATCH", f"/api/tasks/{t['id']}", {"status": "doing"})["status"] == "doing"
    assert h.other().patch(f"/api/tasks/{t['id']}", {"status": "done"})[0] == 404


def test_TB_001_search_is_case_insensitive(h):
    assert len(h.fe("clientFilter", [{"title": "Fix Login"}], "login")) == 1


def test_TB_002_rejects_unknown_status(h):
    assert h.admin().patch("/api/tasks/1", {"status": "banana"})[0] == 400


def test_TB_003_stats_exclude_deleted_tasks(h):
    c = h.admin()
    t = c.ok("POST", "/api/projects/1/tasks", {"title": "Temp"})
    c.ok("DELETE", f"/api/tasks/{t['id']}")
    stats = c.ok("GET", "/api/projects/1/stats")
    assert stats["todo"] + stats["doing"] + stats["done"] == c.ok("GET", "/api/projects/1/tasks")["total"]


def test_TB_004_viewer_cannot_edit_tasks(h):
    assert h.viewer().patch("/api/tasks/1", {"title": "hacked"})[0] == 403


def test_TB_005_transfer_demotes_previous_owner(h):
    c = h.admin()
    pid = c.ok("POST", "/api/projects", {"name": "Side"})["id"]
    c.ok("POST", f"/api/projects/{pid}/members", {"user_id": 2})
    c.ok("POST", f"/api/projects/{pid}/transfer", {"user_id": 2})
    assert c.post(f"/api/projects/{pid}/archive")[0] == 403


def test_TB_006_parent_blocked_until_all_subtasks_done(h):
    c = h.admin()
    p = c.ok("POST", "/api/projects/1/tasks", {"title": "Parent"})["id"]
    s1 = c.ok("POST", "/api/projects/1/tasks", {"title": "s1", "parent_id": p})["id"]
    c.ok("POST", "/api/projects/1/tasks", {"title": "s2", "parent_id": p})
    c.ok("PATCH", f"/api/tasks/{s1}", {"status": "done"})
    assert c.patch(f"/api/tasks/{p}", {"status": "done"})[0] == 409
