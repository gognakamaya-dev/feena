from pathlib import Path

from common.framework import App, HttpError, created

SCHEMA = """
CREATE TABLE products(id INTEGER PRIMARY KEY, org_id INT, sku TEXT, name TEXT, on_hand INT DEFAULT 0, reserved INT DEFAULT 0,
  reorder_level INT DEFAULT 5, unit_cost_cents INT DEFAULT 0);
CREATE TABLE stock_moves(id INTEGER PRIMARY KEY, product_id INT REFERENCES products(id), delta INT, reason TEXT, created_at TEXT);
CREATE TABLE orders(id INTEGER PRIMARY KEY, org_id INT, status TEXT DEFAULT 'draft', customer TEXT);
CREATE TABLE order_items(order_id INT REFERENCES orders(id), product_id INT REFERENCES products(id), qty INT);
"""


def seed(db):
    for i, (sku, n, oh, rl, cost) in enumerate([("WID-001", "Widget", 40, 10, 250), ("GAD-002", "Gadget", 12, 12, 1800), ("BOL-003", "Bolt 10mm", 500, 100, 8),
                                               ("SPR-004", "Spring", 6, 10, 40), ("CAS-005", "Case", 25, 5, 700)], 1):
        db.exec("INSERT INTO products VALUES(?,?,?,?,?,0,?,?)", (i, 1, sku, n, oh, rl, cost))
    db.exec("INSERT INTO products VALUES(6,2,'GLX-001','Globex Part',9,0,5,100)")


app = App("stockpilot", "StockPilot", 9105, SCHEMA, seed, static_dir=Path(__file__).parent / "static",
          description="Inventory management with stock reservations, orders and low-stock reports.")


@app.route("GET", "/api/products")
def products(ctx):
    res = ctx.page("SELECT * FROM products WHERE org_id=%d ORDER BY id" % ctx.user["org_id"])
    for p in res["items"]:
        p["available"] = p["on_hand"] - p["reserved"]
    return res


@app.route("POST", "/api/products", roles=["admin", "member"])
def add_product(ctx):
    sku, name = ctx.need("sku", "name")
    pid = ctx.exec("INSERT INTO products VALUES(NULL,?,?,?,?,0,?,?)", (ctx.user["org_id"], sku, name, ctx.body.get("on_hand", 0), ctx.body.get("reorder_level", 5), ctx.body.get("unit_cost_cents", 0)))
    return created(ctx.get("products", pid))


@app.route("POST", "/api/products/<id>/adjust")
def adjust(ctx):
    """Manual stock adjustment {delta, reason}."""
    p = ctx.get("products", ctx.params["id"])
    delta = ctx.need("delta")[0]
    if not isinstance(delta, int):
        raise HttpError(400, "delta must be an integer")
    if p["on_hand"] + delta < 0:
        raise HttpError(409, "stock cannot go negative")
    ctx.exec("UPDATE products SET on_hand=on_hand+? WHERE id=?", (delta, p["id"]))
    ctx.exec("INSERT INTO stock_moves VALUES(NULL,?,?,?,?)", (p["id"], delta, ctx.body.get("reason", "adjustment"), ctx.now))
    return ctx.get("products", p["id"])


def order(ctx, oid):
    o = ctx.get("orders", oid)
    o["items"] = ctx.q("SELECT * FROM order_items WHERE order_id=?", [oid])
    return o


@app.route("POST", "/api/orders", roles=["admin", "member"])
def add_order(ctx):
    items = ctx.body.get("items") or []
    if not items:
        raise HttpError(400, "order needs items")
    oid = ctx.exec("INSERT INTO orders VALUES(NULL,?,'draft',?)", (ctx.user["org_id"], ctx.body.get("customer", "walk-in")))
    for it in items:
        ctx.get("products", it["product_id"])
        ctx.exec("INSERT INTO order_items VALUES(?,?,?)", (oid, it["product_id"], it["qty"]))
    return created(order(ctx, oid))


@app.route("POST", "/api/orders/<id>/confirm", roles=["admin", "member"])
def confirm(ctx):
    o = order(ctx, ctx.params["id"])
    if o["status"] != "draft":
        raise HttpError(409, "only draft orders can be confirmed")
    for it in o["items"]:
        p = ctx.get("products", it["product_id"])
        if p["on_hand"] - p["reserved"] < it["qty"]:
            raise HttpError(409, f"insufficient stock for {p['sku']}")
    for it in o["items"]:
        ctx.exec("UPDATE products SET reserved=reserved+? WHERE id=?", (it["qty"], it["product_id"]))
    ctx.exec("UPDATE orders SET status='confirmed' WHERE id=?", [o["id"]])
    return order(ctx, o["id"])


@app.route("POST", "/api/orders/<id>/ship", roles=["admin", "member"])
def ship(ctx):
    o = order(ctx, ctx.params["id"])
    if o["status"] != "confirmed":
        raise HttpError(409, "only confirmed orders can ship")
    for it in o["items"]:
        ctx.exec("UPDATE products SET on_hand=on_hand-?, reserved=reserved-? WHERE id=?", (it["qty"], it["qty"], it["product_id"]))
        ctx.exec("INSERT INTO stock_moves VALUES(NULL,?,?,?,?)", (it["product_id"], -it["qty"], f"order {o['id']}", ctx.now))
    ctx.exec("UPDATE orders SET status='shipped' WHERE id=?", [o["id"]])
    return order(ctx, o["id"])


@app.route("POST", "/api/orders/<id>/cancel", roles=["admin", "member"])
def cancel(ctx):
    o = order(ctx, ctx.params["id"])
    if o["status"] in ("shipped", "cancelled"):
        raise HttpError(409, f"cannot cancel a {o['status']} order")
    ctx.exec("UPDATE orders SET status='cancelled' WHERE id=?", [o["id"]])
    return order(ctx, o["id"])


@app.route("GET", "/api/reports/low-stock")
def low_stock(ctx):
    """Products whose available stock is at or below the reorder level."""
    rows = ctx.q("SELECT * FROM products WHERE org_id=? AND on_hand<=reorder_level ORDER BY id", [ctx.user["org_id"]])
    return {"items": rows, "total": len(rows)}


@app.route("GET", "/api/reports/valuation", roles=["admin"])
def valuation(ctx):
    rows = ctx.q("SELECT on_hand, unit_cost_cents FROM products WHERE org_id=?", [ctx.user["org_id"]])
    return {"value_cents": sum(r["on_hand"] * r["unit_cost_cents"] for r in rows)}
