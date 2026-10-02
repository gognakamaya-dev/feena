#!/usr/bin/env bash
# Reset database + seed data of every running app (or the ids given as arguments).
cd "$(dirname "$0")/.." || exit 1
python3 - "$@" <<'PY'
import json, sys, urllib.request
only = set(sys.argv[1:])
for a in json.load(open("benchmark/apps.json"))["apps"]:
    if only and a["id"] not in only:
        continue
    req = urllib.request.Request(a["reset"]["url"], method="POST", headers=a["reset"]["headers"], data=b"{}")
    try:
        urllib.request.urlopen(req, timeout=10); print("reset", a["id"])
    except Exception as e:
        print("FAIL ", a["id"], e)
PY
