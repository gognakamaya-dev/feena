"""Score agent bug reports against the hidden bug manifests.

Matching is lexical (IDF-weighted token overlap between a report and a manifest bug) and one-to-one.
Pass --matches to override automatic matching, e.g. with an LLM or human adjudication.
"""
import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}
DIFFICULTIES = ["easy", "medium", "hard", "very_hard"]
CATEGORIES = ["frontend", "backend", "database", "security", "business_logic"]
STOP = set("""the a an and or of to in on at is are was were be been it its this that these those with without for from by as not no
when then than but if else can could should would will may might must does did done has have had into out over under after before
user users via any all each per also only more most some such which while their there here what where who whom how why let get got""".split())
DEFAULT_THRESHOLD = 0.25


def tokens(text):
    out = set()
    for w in re.findall(r"[a-z0-9]+", (text or "").lower().replace("_", " ")):
        if len(w) < 3 or w in STOP:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return out


def norm_id(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_manifests(path):
    manifests = {}
    for f in sorted(Path(path).glob("*.json")):
        m = json.loads(f.read_text())
        manifests[norm_id(m.get("application_id") or m["application"])] = m
    return manifests


def validate_report(rep):
    if not isinstance(rep, dict) or not isinstance(rep.get("application"), str) or not isinstance(rep.get("bugs_found"), list):
        raise ValueError("report needs string 'application' and list 'bugs_found'")
    for i, b in enumerate(rep["bugs_found"]):
        if not isinstance(b, dict) or not b.get("title") or not b.get("description"):
            raise ValueError(f"bugs_found[{i}] needs 'title' and 'description'")


def bug_tokens(b):
    return tokens(" ".join([b["description"], b["affected_component"], b["expected_behavior"], b["actual_result"]]))


def report_tokens(r):
    return tokens(" ".join(str(r.get(k, "")) for k in ("title", "description", "expected", "actual")))


def steps_tokens(steps):
    return tokens(" ".join(steps if isinstance(steps, list) else [str(steps or "")]))


def score_matrix(bugs, reports):
    btoks = [bug_tokens(b) for b in bugs]
    df = defaultdict(int)
    for t in btoks:
        for w in t:
            df[w] += 1
    idf = {w: math.log(1 + len(bugs) / n) for w, n in df.items()}
    vocab = set(idf)
    scores = []
    for r in reports:
        rt = report_tokens(r) & vocab
        row = []
        for b, bt in zip(bugs, btoks):
            common = rt & bt
            cov = sum(idf[w] for w in common) / (sum(idf[w] for w in bt) or 1)
            foc = sum(idf[w] for w in common) / (sum(idf[w] for w in rt) or 1)
            s = 2 * cov * foc / (cov + foc) if cov + foc else 0.0
            if s and (r.get("category") or "").lower() == b["category"]:
                s += 0.05
            row.append(s)
        scores.append(row)
    return scores


def match(bugs, reports, threshold=DEFAULT_THRESHOLD, overrides=None):
    """Return ({report_idx: bug_idx}, duplicates{report_idx: bug_idx})."""
    scores = score_matrix(bugs, reports)
    ids = {b["id"]: i for i, b in enumerate(bugs)}
    assigned, taken = {}, set()
    if overrides is not None:
        for ri, bid in overrides.items():
            ri = int(ri)
            if bid in ids and ids[bid] not in taken and ri < len(reports):
                assigned[ri] = ids[bid]
                taken.add(ids[bid])
        dup = {}
        return assigned, dup
    pairs = sorted(((s, ri, bi) for ri, row in enumerate(scores) for bi, s in enumerate(row) if s >= threshold), reverse=True)
    for s, ri, bi in pairs:
        if ri not in assigned and bi not in taken:
            assigned[ri] = bi
            taken.add(bi)
    dup = {}
    for ri, row in enumerate(scores):
        if ri not in assigned:
            best = max(range(len(bugs)), key=lambda i: row[i])
            if row[best] >= threshold and best in taken:
                dup[ri] = best
    return assigned, dup


def repro_score(bug, report):
    want = steps_tokens(bug["reproduction_steps"]) | tokens(bug["trigger_conditions"][0] if bug["trigger_conditions"] else "")
    have = steps_tokens(report.get("reproduction_steps")) | report_tokens(report)
    return len(want & have) / len(want) if want else 0.0


def evaluate_app(manifest, report, threshold=DEFAULT_THRESHOLD, overrides=None, repro_threshold=0.3):
    validate_report(report)
    bugs, reports = manifest["bugs"], report["bugs_found"]
    assigned, dup = match(bugs, reports, threshold, overrides)
    found = {bi: ri for ri, bi in assigned.items()}
    fp = [ri for ri in range(len(reports)) if ri not in assigned and ri not in dup]
    details, times = [], {}
    for bi, b in enumerate(bugs):
        d = {"id": b["id"], "category": b["category"], "difficulty": b["difficulty"], "severity": b["severity"], "found": bi in found}
        if bi in found:
            r = reports[found[bi]]
            d["report_index"] = found[bi]
            d["reproduction_score"] = round(repro_score(b, r), 3)
            d["reproduced"] = d["reproduction_score"] >= repro_threshold and bool(r.get("reproduction_steps"))
            t = r.get("discovered_at_seconds")
            if isinstance(t, (int, float)):
                d["discovered_at_seconds"] = t
                times[b["id"]] = t
        details.append(d)
    tp = len(found)
    weights = {b["id"]: SEVERITY_WEIGHT.get(b["severity"], 2) for b in bugs}
    reproduced = sum(1 for d in details if d.get("reproduced"))

    def coverage(key, values):
        out = {}
        for v in values:
            total = [d for d in details if d[key] == v]
            if total:
                out[v] = {"found": sum(d["found"] for d in total), "total": len(total), "rate": round(sum(d["found"] for d in total) / len(total), 3)}
        return out

    return {
        "application": manifest["application"], "application_id": manifest["application_id"],
        "bugs_total": len(bugs), "bugs_discovered": tp, "bugs_missed": len(bugs) - tp,
        "missed_ids": [d["id"] for d in details if not d["found"]], "false_positives": len(fp), "duplicate_reports": len(dup),
        "reports_submitted": len(reports),
        "precision": round(tp / (tp + len(fp)), 3) if tp + len(fp) else 0.0,
        "recall": round(tp / len(bugs), 3),
        "severity_weighted_recall": round(sum(weights[d["id"]] for d in details if d["found"]) / sum(weights.values()), 3),
        "time_to_first_discovery_seconds": min(times.values()) if times else None, "time_to_discover_seconds": times,
        "coverage_by_category": coverage("category", CATEGORIES), "coverage_by_difficulty": coverage("difficulty", DIFFICULTIES),
        "reproduction_accuracy": round(reproduced / tp, 3) if tp else None,
        "false_positive_reports": [{"index": ri, "title": reports[ri]["title"]} for ri in fp], "bugs": details,
    }


def aggregate(results):
    tp = sum(r["bugs_discovered"] for r in results)
    total = sum(r["bugs_total"] for r in results)
    fp = sum(r["false_positives"] for r in results)
    sev_num = sum(sum(SEVERITY_WEIGHT.get(d["severity"], 2) for d in r["bugs"] if d["found"]) for r in results)
    sev_den = sum(sum(SEVERITY_WEIGHT.get(d["severity"], 2) for d in r["bugs"]) for r in results)
    out = {"apps_evaluated": len(results), "bugs_total": total, "bugs_discovered": tp, "false_positives": fp,
           "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0, "recall": round(tp / total, 3) if total else 0.0,
           "severity_weighted_recall": round(sev_num / sev_den, 3) if sev_den else 0.0}
    for key, values in (("coverage_by_category", CATEGORIES), ("coverage_by_difficulty", DIFFICULTIES)):
        out[key] = {}
        for v in values:
            f = sum(r[key].get(v, {}).get("found", 0) for r in results)
            t = sum(r[key].get(v, {}).get("total", 0) for r in results)
            if t:
                out[key][v] = {"found": f, "total": t, "rate": round(f / t, 3)}
    firsts = [r["time_to_first_discovery_seconds"] for r in results if r["time_to_first_discovery_seconds"] is not None]
    out["time_to_first_discovery_seconds"] = min(firsts) if firsts else None
    repro = [d["reproduced"] for r in results for d in r["bugs"] if d["found"]]
    out["reproduction_accuracy"] = round(sum(repro) / len(repro), 3) if repro else None
    return out


def load_reports(path):
    """Return {agent: [report, ...]}. A directory of agent sub-directories, a directory of reports, or one file."""
    p = Path(path)
    read = lambda f: json.loads(f.read_text())
    if p.is_file():
        d = read(p)
        return {"default": d if isinstance(d, list) else [d]}
    agents = {}
    for sub in sorted(x for x in p.iterdir() if x.is_dir()):
        agents[sub.name] = [r for f in sorted(sub.glob("*.json")) for r in (lambda d: d if isinstance(d, list) else [d])(read(f))]
    loose = [r for f in sorted(p.glob("*.json")) for r in (lambda d: d if isinstance(d, list) else [d])(read(f))]
    if loose:
        agents["default"] = loose
    return agents


def evaluate_agent(manifests, reports, threshold=DEFAULT_THRESHOLD, matches=None, agent="default"):
    results, unknown = [], []
    for rep in reports:
        key = norm_id(rep.get("application"))
        m = manifests.get(key) or next((v for k, v in manifests.items() if norm_id(v["application"]) == key), None)
        if not m:
            unknown.append(rep.get("application"))
            continue
        results.append(evaluate_app(m, rep, threshold, (matches or {}).get(agent, {}).get(m["application_id"])))
    missing = sorted(set(manifests) - {r["application_id"] for r in results})
    return {"agent": agent, "summary": aggregate(results), "apps": results, "apps_without_report": missing, "unknown_applications": unknown}


def render(res):
    s = res["summary"]
    lines = [f"Agent: {res['agent']}  apps={s['apps_evaluated']}  found {s['bugs_discovered']}/{s['bugs_total']}  FP={s['false_positives']}  "
             f"precision={s['precision']}  recall={s['recall']}  sev-weighted recall={s['severity_weighted_recall']}  "
             f"repro={s['reproduction_accuracy']}  first-find={s['time_to_first_discovery_seconds']}s"]
    for key in ("coverage_by_difficulty", "coverage_by_category"):
        lines.append("  " + key.replace("_", " ") + ": " + ", ".join(f"{k} {v['found']}/{v['total']}" for k, v in s[key].items()))
    for r in res["apps"]:
        lines.append(f"  {r['application_id']:<18} {r['bugs_discovered']}/{r['bugs_total']} found, FP {r['false_positives']}, missed {', '.join(r['missed_ids']) or '-'}")
    if res["apps_without_report"]:
        lines.append("  no report for: " + ", ".join(res["apps_without_report"]))
    return "\n".join(lines)


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports", required=True, help="report file, directory of reports, or directory of per-agent directories")
    ap.add_argument("--manifests", default=str(root / "manifests"))
    ap.add_argument("--matches", help="JSON {agent: {application_id: {report_index: bug_id}}} overriding automatic matching")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--output", help="write full JSON results here")
    a = ap.parse_args(argv)
    manifests = load_manifests(a.manifests)
    matches = json.loads(Path(a.matches).read_text()) if a.matches else None
    results = [evaluate_agent(manifests, reps, a.threshold, matches, agent) for agent, reps in load_reports(a.reports).items()]
    for r in results:
        print(render(r))
    if a.output:
        Path(a.output).write_text(json.dumps({"agents": results}, indent=2))
    return 0
