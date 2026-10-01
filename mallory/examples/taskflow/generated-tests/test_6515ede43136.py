"""Mallory regression test. Generated; safe to commit.

Finding : Missing response header: x-frame-options
Kind    : weak_headers   Severity: low   Fingerprint: 6515ede43136

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : MALLORY_BASE_URL=http://localhost:3000 pytest test_6515ede43136.py
          (add MALLORY_USER1_EMAIL / MALLORY_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _mallory_support as S  # noqa: F401


def test_6515ede43136():
    with S.client() as c:
        r = c.get('/')
    assert 'x-frame-options' in {k.lower() for k in r.headers}, (
        "REGRESSION: response is missing the x-frame-options header")
