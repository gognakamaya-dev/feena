#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1
for f in .run/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null; rm -f "$f"; done; echo stopped
