"""Mallory regression test. Generated; safe to commit.

Finding : SQL injection auth bypass at /login
Kind    : sql_injection   Severity: critical   Fingerprint: 5b7f2c038423

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : MALLORY_BASE_URL=http://localhost:3000 pytest test_5b7f2c038423.py
          (add MALLORY_USER1_EMAIL / MALLORY_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _mallory_support as S  # noqa: F401


def test_5b7f2c038423():
    with S.client(follow=False) as c:
        r = S.login_attempt(c, '/login', "' OR 1=1 -- ", "x", 'form')
    assert r is None or S.login_rejected(r), (
        "REGRESSION: an injection probe in the login form authenticates at /login")
