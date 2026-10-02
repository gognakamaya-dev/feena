def upload(c, name, folder=1, size=1000):
    return c.post("/api/assets", {"name": name, "size_bytes": size, "folder_id": folder})


def test_happy_path(h):
    c = h.admin()
    s, a = upload(c, "new.png")
    assert s == 201 and a["mime"] == "image/png"
    assert upload(c, "new.png")[0] == 409
    assert upload(c, "evil.exe")[0] == 400
    sh = c.ok("POST", f"/api/assets/{a['id']}/share", {"expires_in_days": 1})
    assert h.anon().get(f"/api/public/share/{sh['token']}")[0] == 200


def test_AM_001_size_limit_enforced(h):
    assert upload(h.admin(), "huge.mp4", size=60 * 1024 * 1024)[0] == 400


def test_AM_002_size_summary_uses_mebibytes(h):
    assert h.fe("summarize", "assets", [{"size_bytes": 5242880}]) == "Total: 5.0 MB"


def test_AM_003_storage_excludes_deleted_assets(h):
    c = h.admin()
    before = c.ok("GET", "/api/storage")["used_bytes"]
    c.ok("DELETE", "/api/assets/4")
    assert c.ok("GET", "/api/storage")["used_bytes"] == before - 40_000_000


def test_AM_004_revoked_share_stops_working(h):
    c = h.admin()
    sh = c.ok("POST", "/api/assets/1/share")
    c.ok("POST", f"/api/shares/{sh['id']}/revoke")
    assert h.anon().get(f"/api/public/share/{sh['token']}")[0] == 404


def test_AM_005_move_respects_name_uniqueness(h):
    c = h.admin()
    upload(c, "dup.png", folder=1)
    _, b = upload(c, "dup.png", folder=2)
    assert c.patch(f"/api/assets/{b['id']}", {"folder_id": 1})[0] == 409


def test_AM_006_deleted_asset_share_link_is_dead(h):
    c = h.admin()
    sh = c.ok("POST", "/api/assets/1/share")
    c.ok("DELETE", "/api/assets/1")
    assert h.anon().get(f"/api/public/share/{sh['token']}")[0] == 404
