"""Mallory regression test. Generated; safe to commit.

Finding : Missing response header: content-security-policy
Kind    : weak_headers   Severity: medium   Fingerprint: ac52387e62d9

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : MALLORY_BASE_URL=http://localhost:3000 pytest test_ac52387e62d9.py
          (add MALLORY_USER1_EMAIL / MALLORY_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _mallory_support as S  # noqa: F401


def test_ac52387e62d9():
    with S.client() as c:
        r = c.get('/')
    assert 'content-security-policy' in {k.lower() for k in r.headers}, (
        "REGRESSION: response is missing the content-security-policy header")
