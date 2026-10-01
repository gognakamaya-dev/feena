"""Feena regression test. Generated; safe to commit.

Finding : Protected-looking endpoint served without auth: /api/projects
Kind    : missing_auth   Severity: high   Fingerprint: 10520c07d917

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : FEENA_BASE_URL=http://localhost:3000 pytest test_10520c07d917.py
          (add FEENA_USER1_EMAIL / FEENA_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _feena_support as S  # noqa: F401


def test_10520c07d917():
    with S.client() as c:  # deliberately NOT logged in
        r = c.get('/api/projects')
    assert not S.looks_like_data(r), (
        "REGRESSION: /api/projects serves data to a request with no session")
