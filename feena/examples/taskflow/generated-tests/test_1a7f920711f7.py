"""Feena regression test. Generated; safe to commit.

Finding : Stored XSS: input persists unescaped at /tasks (rendered DOM)
Kind    : stored_xss   Severity: high   Fingerprint: 1a7f920711f7

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : FEENA_BASE_URL=http://localhost:3000 pytest test_1a7f920711f7.py
          (add FEENA_USER1_EMAIL / FEENA_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _feena_support as S  # noqa: F401


def test_1a7f920711f7():
    marker = S.new_marker()
    with S.browser_page(login_user=1) as page:
        S.rendered_html(page, '/tasks')
        S.submit_form(page, ['title'], S.probe(marker))
        html = S.rendered_html(page, '/tasks')
    assert not S.is_unescaped(html, marker), (
        "REGRESSION: stored input is rendered as raw HTML at /tasks")
