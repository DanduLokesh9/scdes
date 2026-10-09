#!/usr/bin/env bash
# Which agency containers exist on this box, and how much is in each.
#
# Run after a harness walk against staging: the browser checks answer real
# questions as a real registered address, so they leave answers in a real
# tenant. Knowing which one, and how many, is the difference between "that is
# the harness" and "somebody's work is missing".
set -u
cd /opt/governingai || exit 1
for dir in data/agencies/*/; do
  file="$dir/versions.json"
  if [ -f "$file" ]; then
    count=$(python3 - "$file" <<'PY'
import json, sys
try:
    held = json.load(open(sys.argv[1]))
except Exception:
    print("unreadable"); raise SystemExit
working = held.get("working") or {}
print(f"{len(working)} answers, version {held.get('current', '?')}")
PY
)
  else
    count="no versions file"
  fi
  printf '%-46s %s\n' "$dir" "$count"
done
