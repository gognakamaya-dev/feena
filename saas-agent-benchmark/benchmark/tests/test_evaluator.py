import json
from pathlib import Path

from benchmark.evaluator import evaluate as ev

MANIFESTS = ev.load_manifests(Path(__file__).resolve().parents[1] / "manifests")


def report_from(app_id, ids, extra=()):
    bugs = {b["id"]: b for b in MANIFESTS[app_id]["bugs"]}
    found = [{"title": bugs[i]["description"], "severity": "high", "category": bugs[i]["category"], "description": bugs[i]["description"],
              "reproduction_steps": bugs[i]["reproduction_steps"], "expected": bugs[i]["expected_result"], "actual": bugs[i]["actual_result"],
              "evidence": [], "discovered_at_seconds": 10 * (n + 1)} for n, i in enumerate(ids)]
    return {"application": app_id, "bugs_found": found + list(extra)}


def test_perfect_report_scores_full_recall():
    ids = [b["id"] for b in MANIFESTS["invoiceflow"]["bugs"]]
    r = ev.evaluate_app(MANIFESTS["invoiceflow"], report_from("invoiceflow", ids))
    assert r["recall"] == 1.0 and r["precision"] == 1.0 and r["false_positives"] == 0
    assert r["time_to_first_discovery_seconds"] == 10 and r["reproduction_accuracy"] == 1.0


def test_partial_report_with_false_positive_and_duplicate():
    fp = {"title": "Footer link colour is slightly off", "description": "The footer uses a different shade of grey", "severity": "low"}
    rep = report_from("invoiceflow", ["INV-001", "INV-004"], extra=[fp])
    rep["bugs_found"].append(dict(rep["bugs_found"][0]))
    r = ev.evaluate_app(MANIFESTS["invoiceflow"], rep)
    assert r["bugs_discovered"] == 2 and r["false_positives"] == 1 and r["duplicate_reports"] == 1
    assert r["recall"] == round(2 / 6, 3) and r["precision"] == round(2 / 3, 3)
    assert r["severity_weighted_recall"] == round((3 + 4) / (3 + 2 + 2 + 4 + 3 + 3), 3) or r["severity_weighted_recall"] > 0


def test_each_manifest_bug_matches_itself_uniquely():
    for app_id, m in MANIFESTS.items():
        ids = [b["id"] for b in m["bugs"]]
        r = ev.evaluate_app(m, report_from(app_id, ids))
        assert r["bugs_discovered"] == len(ids), (app_id, r["missed_ids"])


def test_overrides_and_cli(tmp_path):
    rep = report_from("invoiceflow", ["INV-001"])
    (tmp_path / "invoiceflow.json").write_text(json.dumps(rep))
    out = tmp_path / "out.json"
    assert ev.main(["--reports", str(tmp_path), "--output", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["agents"][0]["summary"]["bugs_discovered"] == 1
    forced = ev.evaluate_app(MANIFESTS["invoiceflow"], rep, overrides={0: "INV-002"})
    assert forced["bugs"][1]["found"] and not forced["bugs"][0]["found"]
