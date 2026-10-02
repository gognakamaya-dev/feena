#!/usr/bin/env python3
"""Verify that the failing correct-behaviour tests are exactly the bugs in the hidden manifests."""
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
subprocess.run([sys.executable, "-m", "benchmark.build_manifests"], cwd=ROOT, check=True)
xml = Path(tempfile.mkdtemp()) / "r.xml"
subprocess.run([sys.executable, "-m", "pytest", "apps", "-q", "--tb=no", "-p", "no:cacheprovider", f"--junitxml={xml}"], cwd=ROOT, capture_output=True)
failed, happy_failed = set(), []
for tc in ET.parse(xml).getroot().iter("testcase"):
    bad = tc.find("failure") is not None or tc.find("error") is not None
    m = re.match(r"test_([A-Z]+)_(\d{3})_", tc.get("name"))
    if m and bad:
        failed.add(f"{m[1]}-{m[2]}")
    elif bad:
        happy_failed.append(tc.get("classname") + "::" + tc.get("name"))
expected = {b["id"] for f in (ROOT / "benchmark/manifests").glob("*.json") for b in json.loads(f.read_text())["bugs"]}
print(f"manifest bugs: {len(expected)}  failing bug tests: {len(failed)}")
print("bugs without a failing test:", sorted(expected - failed) or "none")
print("failing tests without a manifest entry:", sorted(failed - expected) or "none")
print("failing non-bug tests:", happy_failed or "none")
sys.exit(0 if failed == expected and not happy_failed else 1)
