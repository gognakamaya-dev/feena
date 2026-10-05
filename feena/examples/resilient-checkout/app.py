"""Small local checkout used to exercise safe retries in browser simulations."""
from __future__ import annotations

import uuid
import os
from collections import defaultdict

from flask import Flask, jsonify, make_response, request

app = Flask(__name__)
ORDERS: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Resilient checkout</title>
<style>
body{font:16px system-ui,sans-serif;max-width:38rem;margin:4rem auto;padding:0 1rem;color:#182230}
main{border:1px solid #d7dee8;border-radius:12px;padding:2rem}button{padding:.7rem 1.1rem;cursor:pointer}
#status{min-height:1.5rem;margin-top:1rem}#count{font-variant-numeric:tabular-nums}
</style></head><body><main><h1>Resilient checkout</h1>
<p>Demo item — $12.00</p><p>Payment is simulated; no external service is contacted.</p>
<button id="checkout" type="button">Place order</button>
<p id="status" role="status" aria-live="polite">Ready to check out.</p>
<p>Orders placed: <strong id="count">0</strong></p></main><script>
const params = new URLSearchParams(location.search);
const orderKey = crypto.randomUUID();
const button = document.querySelector('#checkout');
const status = document.querySelector('#status');
async function refreshCount() {
  const response = await fetch('/api/state');
  const state = await response.json();
  document.querySelector('#count').textContent = state.orders;
}
button.addEventListener('click', async () => {
  button.disabled = true;
  status.textContent = 'Submitting order…';
  try {
    const response = await fetch('/api/orders' + (params.get('broken') === '1' ? '?broken=1' : ''), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({idempotency_key: orderKey})
    });
    if (!response.ok) throw new Error('Order could not be confirmed');
    status.textContent = 'Order confirmed.';
    await refreshCount();
  } catch (_) {
    status.textContent = 'We could not confirm the order. Retry safely.';
  } finally {
    button.disabled = false;
  }
});
refreshCount();
</script></body></html>"""


@app.get("/")
def home():
    response = make_response(PAGE)
    if not request.cookies.get("checkout_session"):
        response.set_cookie("checkout_session", uuid.uuid4().hex, httponly=True, samesite="Lax")
    return response


def _session_key() -> str:
    return request.cookies.get("checkout_session", "")


@app.post("/api/orders")
def place_order():
    payload = request.get_json(silent=True) or {}
    key = payload.get("idempotency_key")
    if not isinstance(key, str) or not key:
        return jsonify(error="idempotency_key is required"), 400

    session_orders = ORDERS[_session_key()]
    if request.args.get("broken") == "1":
        order_id = uuid.uuid4().hex
        session_orders[order_id] = {
            "idempotency_key": key, "payment": "mock", "status": "paid"
        }
        return jsonify(session_orders[order_id]), 201
    if key not in session_orders:
        session_orders[key] = {"idempotency_key": key, "payment": "mock", "status": "paid"}
    return jsonify(session_orders[key]), 201


@app.get("/api/state")
def state():
    return jsonify(orders=len(ORDERS.get(_session_key(), {})))


@app.post("/test/reset")
def reset_test_data():
    # Only opt in on a disposable demo instance dedicated to this worker slot.
    if os.environ.get("FEENA_DEMO_RESET") != "1":
        return jsonify(error="Not found"), 404
    ORDERS.clear()
    return jsonify(reset=True)


@app.get("/api/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055)

