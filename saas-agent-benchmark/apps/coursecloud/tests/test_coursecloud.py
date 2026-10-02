def enroll(c, cid):
    return c.post(f"/api/courses/{cid}/enroll")


def lesson_ids(h, cid):
    return [r["id"] for r in h.sql("SELECT id FROM lessons WHERE course_id=? AND required=1 ORDER BY id", [cid])]


def test_happy_path(h):
    s = h.member()
    st, e = enroll(s, 2)
    assert st == 201 and enroll(s, 2)[0] == 409
    for lid in lesson_ids(h, 2):
        p = s.ok("POST", f"/api/lessons/{lid}/complete")
    assert p["percent"] == 100


def test_CC_001_cannot_enroll_in_draft_course(h):
    assert enroll(h.viewer(), 3)[0] in (404, 409)


def test_CC_002_published_count_summary(h):
    assert h.fe("summarize", "courses", [{"status": "published"}, {"status": "draft"}]) == "Published courses: 1"


def test_CC_003_progress_counts_required_lessons_only(h):
    s = h.viewer()  # enrolled in course 1 (3 required + 1 optional lesson)
    optional = h.sql("SELECT id FROM lessons WHERE course_id=1 AND required=0")[0]["id"]
    first = lesson_ids(h, 1)[0]
    s.ok("POST", f"/api/lessons/{first}/complete")
    assert s.ok("POST", f"/api/lessons/{optional}/complete")["percent"] == 33


def test_CC_004_students_cannot_read_gradebook(h):
    assert h.viewer().get("/api/courses/1/gradebook")[0] == 403


def test_CC_005_completing_a_lesson_twice_counts_once(h):
    s = h.viewer()
    first = lesson_ids(h, 1)[0]
    s.ok("POST", f"/api/lessons/{first}/complete")
    assert s.ok("POST", f"/api/lessons/{first}/complete")["completed"] == 1


def test_CC_006_pass_mark_not_rounded_up(h):
    s = h.viewer()
    for lid in lesson_ids(h, 1):
        s.ok("POST", f"/api/lessons/{lid}/complete")
    h.app.db.exec("DELETE FROM grades WHERE course_id=1")
    h.app.db.exec("INSERT INTO grades VALUES(NULL,1,3,139,200)")  # 69.5%
    assert s.post("/api/enrollments/1/certificate")[0] == 409
