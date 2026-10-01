"""Mallory regression test. Generated; safe to commit.

Finding : Missing response header: strict-transport-security
Kind    : weak_headers   Severity: low   Fingerprint: 3824a4be7ce8

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : MALLORY_BASE_URL=http://localhost:3000 pytest test_3824a4be7ce8.py
          (add MALLORY_USER1_EMAIL / MALLORY_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _mallory_support as S  # noqa: F401


def test_3824a4be7ce8():
    with S.client() as c:
        r = c.get('/')
    assert 'strict-transport-security' in {k.lower() for k in r.headers}, (
        "REGRESSION: response is missing the strict-transport-security header")
