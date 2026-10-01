"""Open-core seam: third-party check packs register via Python entry points.

The open-source runner ships the built-in checks. A separate package (e.g. a proprietary
``mallory-pro`` pack built from the corpus) adds checks without forking, by declaring:

    [project.entry-points."mallory.checks"]
    graphql_introspection = "mallory_pro.checks:graphql_introspection"

Each entry point resolves to ``callable(cfg, sandbox) -> list[Finding]``, the same contract as
the built-ins. Plugin checks run under the same sandbox guard as everything else.
"""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Callable

GROUP = "mallory.checks"


def load_plugin_checks() -> list[tuple[str, Callable]]:
    out = []
    for ep in entry_points(group=GROUP):
        try:
            out.append((ep.name, ep.load()))
        except Exception:
            continue  # a broken plugin must never break the run
    return out
