"""Feena regression test. Generated; safe to commit.

Finding : Missing response header: x-content-type-options
Kind    : weak_headers   Severity: low   Fingerprint: 53e6852fce35

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : FEENA_BASE_URL=http://localhost:3000 pytest test_53e6852fce35.py
          (add FEENA_USER1_EMAIL / FEENA_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _feena_support as S  # noqa: F401


def test_53e6852fce35():
    with S.client() as c:
        r = c.get('/')
    assert 'x-content-type-options' in {k.lower() for k in r.headers}, (
        "REGRESSION: response is missing the x-content-type-options header")
