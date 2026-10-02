def contact(c, name, email):
    return c.ok("POST", "/api/contacts", {"name": name, "email": email})


def deal(c, cid, amount, title="D"):
    return c.ok("POST", "/api/deals", {"contact_id": cid, "title": title, "amount_cents": amount})


def test_happy_path(h):
    c = h.admin()
    a = contact(c, "Zed", "zed@x.test")
    d = deal(c, a["id"], 5000)
    c.ok("POST", f"/api/deals/{d['id']}/stage", {"stage": "won"})
    assert c.ok("GET", f"/api/contacts/{a['id']}")["lifetime_value_cents"] == 5000
    assert c.post("/api/deals", {"contact_id": 9, "title": "x", "amount_cents": 1})[0] == 404


def test_CH_001_duplicate_email_rejected(h):
    assert h.admin().post("/api/contacts", {"name": "Dup", "email": "wile@example.test"})[0] == 409


def test_CH_002_open_pipeline_excludes_closed_deals(h):
    items = [{"stage": "proposal", "amount_cents": 1000}, {"stage": "won", "amount_cents": 5000}, {"stage": "lost", "amount_cents": 700}]
    assert h.fe("summarize", "deals", items) == "Open pipeline: $10.00"


def test_CH_003_search_excludes_deleted_contacts(h):
    names = [x["name"] for x in h.admin().ok("GET", "/api/contacts?q=Gavin")["items"]]
    assert names == []


def test_CH_004_deal_access_scoped_to_org(h):
    assert h.admin().get("/api/deals/100")[0] == 404


def test_CH_005_merge_moves_deals(h):
    c = h.admin()
    a, b = contact(c, "A", "a@x.test"), contact(c, "B", "b@x.test")
    d = deal(c, b["id"], 7000)
    c.ok("POST", f"/api/deals/{d['id']}/stage", {"stage": "won"})
    merged = c.ok("POST", "/api/contacts/merge", {"keep_id": a["id"], "merge_id": b["id"]})
    assert merged["lifetime_value_cents"] == 7000


def test_CH_006_reopened_deal_not_counted_as_won(h):
    c = h.admin()
    base = c.ok("GET", "/api/reports/pipeline")["won_cents"]
    a = contact(c, "A", "a@x.test")
    d = deal(c, a["id"], 9000)
    c.ok("POST", f"/api/deals/{d['id']}/stage", {"stage": "won"})
    c.ok("POST", f"/api/deals/{d['id']}/stage", {"stage": "proposal"})
    assert c.ok("GET", "/api/reports/pipeline")["won_cents"] == base
