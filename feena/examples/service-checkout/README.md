# Checkout across two services

This disposable fixture demonstrates a payment committed before a timeout response, an
explicit checkout retry, and a webhook delivered later (then delivered again). Feena checks
both services: exactly one order and exactly one charge. The payment timeout is an HTTP 504
fixture response, not a simulated TCP timeout. All calls stay local.

From `feena/`, start the services:

```bash
python examples/service-checkout/app.py
```

In another terminal:

```bash
export FEENA_SERVICE_ORDERS_URL=http://127.0.0.1:5057
export FEENA_SERVICE_PAYMENTS_URL=http://127.0.0.1:5056
feena integrate --config examples/service-checkout/feena.yaml
pytest examples/service-checkout/.feena/tests
```

Both commands should pass. Stop the fixture and restart it with `--broken`; both commands
should fail because the delayed webhook creates a second order. This gives the same exported
test a known failing and passing implementation. No LLM is involved in either execution.

Each run substitutes a fresh `${run_id}` into paths, request bodies, and expected values.
Setup and cleanup isolate fixture data. Cleanup runs even after assertion/transport failures;
cleanup failure cannot produce a passing result. Every step asserts an HTTP status and a
nonempty JSON subset. GET assertions may poll for up to ten seconds; mutations are retried
only when an explicit step requests them.

Reports and exports are under `examples/service-checkout/.feena/`. Copy the entire `tests/`
directory to another project, or use `feena adopt --all --from <that tests directory>`.
The exported suite requires only pytest and httpx, plus the same service URL variables.
Keep credentials in the environment; do not embed secrets in scenario payloads or assertions.
Result JSON contains expected/actual response data and should stay private.
