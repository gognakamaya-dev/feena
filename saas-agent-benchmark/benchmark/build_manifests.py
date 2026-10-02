"""Compile benchmark/manifest_src/*.py into benchmark/manifests/<app>.json (the hidden bug manifests)."""
import collections
import importlib
import json
import pkgutil
from pathlib import Path

HERE = Path(__file__).parent
CATS = {"frontend", "backend", "database", "security", "business_logic"}


def main():
    (HERE / "manifests").mkdir(exist_ok=True)
    diff, multi_hard = collections.Counter(), [0, 0]
    for m in sorted(pkgutil.iter_modules([str(HERE / "manifest_src")]), key=lambda m: m.name):
        if m.name.startswith("_"):
            continue
        src = importlib.import_module(f"benchmark.manifest_src.{m.name}")
        bugs = []
        for b in src.BUGS:
            b = dict(b)
            b["id"] = f"{src.PREFIX}-{b.pop('n'):03d}"
            assert b["category"] in CATS, b
            diff[b["difficulty"]] += 1
            if b["difficulty"] in ("hard", "very_hard"):
                multi_hard[0] += 1
                multi_hard[1] += b["multi_step"]
            bugs.append({"id": b.pop("id"), **b})
        assert 5 <= len(bugs) <= 10, (m.name, len(bugs))
        (HERE / "manifests" / f"{m.name}.json").write_text(json.dumps(
            {"application": src.APP, "application_id": m.name, "bugs": bugs}, indent=2) + "\n")
    total = sum(diff.values())
    print(f"{total} bugs:", {k: f"{v} ({100 * v // total}%)" for k, v in diff.items()},
          f"multi-step among hard/very_hard: {multi_hard[1]}/{multi_hard[0]}")


if __name__ == "__main__":
    main()
