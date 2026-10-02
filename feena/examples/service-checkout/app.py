"""Two disposable services: a checkout app and a payment provider fixture."""
import argparse
import threading

import httpx
from flask import Flask, jsonify, request
from werkzeug.serving import make_server


def payment_app():
    app = Flask("payments")
    charges = {}
    attempts = {}

    @app.post("/charge/<key>")
    def charge(key):
        charges[key] = 1  # provider deduplicates the idempotency key
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] == 1:
            return jsonify(error="timeout_after_charge"), 504
        return jsonify(charged=True)

    @app.get("/state/<key>")
    def state(key):
        return jsonify(charges=charges.get(key, 0))

    @app.delete("/state/<key>")
    def clear(key):
        charges.pop(key, None)
        attempts.pop(key, None)
        return jsonify(cleared=True)

    return app


def order_app(payment_url, broken=False):
    app = Flask("orders")
    orders = {}
    events = set()

    @app.post("/checkout/<key>")
    def checkout(key):
        response = httpx.post(f"{payment_url}/charge/{key}", timeout=3, trust_env=False)
        if response.status_code == 504:
            return jsonify(error="payment_pending"), 504
        orders.setdefault(key, 1)
        return jsonify(accepted=True)

    @app.post("/webhook/<key>")
    def webhook(key):
        event = (key, request.json["event_id"])
        if event not in events:
            events.add(event)
            if broken:
                orders[key] = orders.get(key, 0) + 1
            else:
                orders.setdefault(key, 1)
        return jsonify(received=True)

    @app.get("/state/<key>")
    def state(key):
        return jsonify(orders=orders.get(key, 0))

    @app.delete("/state/<key>")
    def clear(key):
        orders.pop(key, None)
        events.difference_update({event for event in events if event[0] == key})
        return jsonify(cleared=True)

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--broken", action="store_true")
    args = parser.parse_args()
    payments = make_server("127.0.0.1", 5056, payment_app(), threaded=True)
    threading.Thread(target=payments.serve_forever, daemon=True).start()
    order_app("http://127.0.0.1:5056", args.broken).run(host="127.0.0.1", port=5057)
