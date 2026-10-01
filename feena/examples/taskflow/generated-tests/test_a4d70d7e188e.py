"""Feena regression test. Generated; safe to commit.

Finding : User input reflected in rendered DOM at /search
Kind    : input_handling   Severity: medium   Fingerprint: a4d70d7e188e

PASSES when the bug is fixed. FAILS if it is (re)introduced.
Run     : FEENA_BASE_URL=http://localhost:3000 pytest test_a4d70d7e188e.py
          (add FEENA_USER1_EMAIL / FEENA_USER1_PASSWORD for tests that log in)
"""
import pytest  # noqa: F401

import _feena_support as S  # noqa: F401


def test_a4d70d7e188e():
    marker = S.new_marker()
    with S.browser_page() as page:
        html = S.rendered_html(page, '/search', {'q': S.probe(marker)})
    assert not S.is_unescaped(html, marker), (
        "REGRESSION: /search renders the q value as raw HTML in the DOM")
