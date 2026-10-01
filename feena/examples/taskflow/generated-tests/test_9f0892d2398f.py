"""Feena regression test. Generated; safe to commit.

Finding : IDOR: /api/tasks/2 returns an object owned by another user
Kind    : access_control   Severity: critical   Fingerprint: 9f0892d2398f

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : FEENA_BASE_URL=http://localhost:3000 pytest test_9f0892d2398f.py
          (add FEENA_USER1_EMAIL / FEENA_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _feena_support as S  # noqa: F401


def test_9f0892d2398f():
    with S.client() as c:
        S.login(c, 1)
        own = S.own_id(c)
        if own is None:
            pytest.skip("could not determine the logged-in user's own id (needs /api/me)")
        r = c.get('/api/tasks/2')
    if not S.looks_like_data(r):
        return  # the endpoint no longer hands this object to this user: fixed
    owner = S.owner_of(r)
    assert not (owner and owner != own), (
        f"REGRESSION: /api/tasks/2 returned an object owned by user {owner} to user {own}")
