"""What the audit log actually records, so recovery is not written on a guess.

Prints the distinct actions, the field names inside `detail`, and a couple of
whole events for any action that mentions an answer. Read-only.

Usage:  python3 _log_keys.py <log.jsonl> [key-to-search-for]
"""

from __future__ import annotations

import json
import sys
from collections import Counter


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = argv[0]
    wanted = argv[1] if len(argv) > 1 else ""

    actions: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    samples: dict[str, dict] = {}
    hits: list[dict] = []

    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            action = str(event.get("action") or "")
            actions[action] += 1
            detail = event.get("detail") or {}
            if isinstance(detail, dict):
                for name in detail:
                    fields[name] += 1
            if "answer" in action.lower() and action not in samples:
                samples[action] = event
            if wanted and wanted in json.dumps(event):
                hits.append(event)

    print("actions, most common first")
    for action, count in actions.most_common(24):
        print(f"  {count:>6}  {action}")

    print("\nfield names inside detail")
    for name, count in fields.most_common(28):
        print(f"  {count:>6}  {name}")

    print(f"\n{len(samples)} distinct answer actions; one of each:")
    for action, event in list(samples.items())[:6]:
        print(f"\n-- {action}")
        print(json.dumps(event.get("detail"), indent=2)[:520])

    if wanted:
        print(f"\n{len(hits)} events mention {wanted!r}. The last two:")
        for event in hits[-2:]:
            print(json.dumps(event, indent=2)[:700])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
