import importlib
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("BENCH_DATA_DIR", tempfile.mkdtemp(prefix="bench-"))
from common.testkit import Harness  # noqa: E402

_cache = {}


@pytest.fixture
def h(request):
    app_id = Path(request.fspath).parent.parent.name
    if app_id not in _cache:
        _cache[app_id] = Harness(importlib.import_module(f"apps.{app_id}.app").app)
    _cache[app_id].reset()
    return _cache[app_id]
