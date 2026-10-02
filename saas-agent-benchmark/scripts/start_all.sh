#!/usr/bin/env bash
# Start every application in the background (pids/logs in .run/). Optional args: app ids.
cd "$(dirname "$0")/.." || exit 1
mkdir -p .run
ids=("$@"); [ ${#ids[@]} -eq 0 ] && mapfile -t ids < <(python3 -c "import json;print('\n'.join(a['id'] for a in json.load(open('benchmark/apps.json'))['apps']))")
for id in "${ids[@]}"; do
  port=$(python3 -c "import json,sys;print([a['port'] for a in json.load(open('benchmark/apps.json'))['apps'] if a['id']=='$id'][0])")
  nohup python3 -m common.run "$id" --port "$port" > ".run/$id.log" 2>&1 & echo $! > ".run/$id.pid"
done
for id in "${ids[@]}"; do
  port=$(python3 -c "import json;print([a['port'] for a in json.load(open('benchmark/apps.json'))['apps'] if a['id']=='$id'][0])")
  for _ in $(seq 50); do curl -fs "http://127.0.0.1:$port/health" >/dev/null && break; sleep 0.2; done
  curl -fs "http://127.0.0.1:$port/health" >/dev/null && echo "up   $id :$port" || echo "FAIL $id (see .run/$id.log)"
done
