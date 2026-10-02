def order(c, pid, qty):
    return c.ok("POST", "/api/orders", {"items": [{"product_id": pid, "qty": qty}]})


def test_happy_path(h):
    c = h.admin()
    o = order(c, 1, 10)
    c.ok("POST", f"/api/orders/{o['id']}/confirm")
    assert c.ok("GET", "/api/products")["items"][0]["available"] == 30
    c.ok("POST", f"/api/orders/{o['id']}/ship")
    assert c.ok("GET", "/api/products")["items"][0]["on_hand"] == 30
    assert c.post("/api/products/1/adjust", {"delta": -999})[0] == 409


def test_SP_001_sku_unique_per_org(h):
    assert h.admin().post("/api/products", {"sku": "WID-001", "name": "Dup"})[0] == 409


def test_SP_002_low_stock_boundary_in_summary(h):
    assert h.fe("summarize", "products", [{"on_hand": 10, "reorder_level": 10}, {"on_hand": 20, "reorder_level": 10}]) == "Low stock: 1"


def test_SP_003_low_stock_uses_available(h):
    c = h.admin()
    o = order(c, 1, 35)  # on_hand 40, reorder 10: reserving 35 leaves 5 available
    c.ok("POST", f"/api/orders/{o['id']}/confirm")
    assert 1 in [p["id"] for p in c.ok("GET", "/api/reports/low-stock")["items"]]


def test_SP_004_viewer_cannot_adjust_stock(h):
    assert h.viewer().post("/api/products/1/adjust", {"delta": 5})[0] == 403


def test_SP_005_cancel_releases_reservation(h):
    c = h.admin()
    o = order(c, 1, 10)
    c.ok("POST", f"/api/orders/{o['id']}/confirm")
    c.ok("POST", f"/api/orders/{o['id']}/cancel")
    assert c.ok("GET", "/api/products")["items"][0]["available"] == 40


def test_SP_006_adjust_cannot_dip_below_reserved(h):
    c = h.admin()
    o = order(c, 1, 30)
    c.ok("POST", f"/api/orders/{o['id']}/confirm")
    assert c.post("/api/products/1/adjust", {"delta": -35})[0] == 409
