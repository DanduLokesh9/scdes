"""Upload a realistic county policy and see which questions it answers.

The claim being tested is the one that matters: an agency that already has an
acceptable use policy should not be retyping what is in it. So this uploads a
short but real-shaped policy and prints, per framework question, which passage
of the agency's own document was matched to it.

A match is a suggestion with its source attached — nothing here answers
anything. What this checks is that the suggestions land on the right questions
and, just as importantly, that they do not land on the wrong ones.

    python -m tools.check_intake
"""

from __future__ import annotations

import base64
import json
import urllib.request

BASE = "http://127.0.0.1:8765"

POLICY = """Anderson County Acceptable Use Policy

1. Purpose
This policy governs the acceptable use of information technology resources by
all programs, departments and offices within Anderson County, including any use
of artificial intelligence tools.

2. Human review of decisions
No automated or artificial intelligence system may issue a final determination
affecting a member of the public, a regulated entity, or a County employee. A
County employee with delegated authority must review and be accountable for any
such decision before it takes effect.

3. Scope of covered technology
This policy applies to software developed internally, procured from external
vendors, embedded within third-party platforms, or acquired through cooperative
purchasing agreements and platform upgrades. Conventional statistical analysis
and deterministic automation without predictive capability are excluded.

4. Conflicting requirements
Where this policy imposes requirements more stringent than state or federal
policy, the more stringent standard controls.

5. Determination of scope
The Chief Information Officer determines whether a given tool falls within
scope, subject to review by the County Administrator.
"""


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path + "?user=sean.ot",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request))


def get(path: str) -> dict:
    return json.load(urllib.request.urlopen(BASE + path))


def main() -> int:
    name = "Anderson_County_Acceptable_Use_Policy.txt"
    result = post("/api/intake/upload", {
        "filename": name,
        "kind": "Acceptable use policy",
        "content": base64.b64encode(POLICY.encode("utf-8")).decode("ascii"),
    })
    print(f"upload      : ok={result.get('ok')} "
          f"readable={result.get('readable')} "
          f"paragraphs={result.get('paragraphs')} "
          f"{result.get('error', '')}")
    if not result.get("ok"):
        return 1

    print("\nquestions this policy appears to answer:\n")
    matched = 0
    total = 0
    for number in ("1", "2", "3"):
        section = get(f"/api/discretion?section={number}")
        for row in section.get("rows", []):
            if not row.get("configurable"):
                continue
            total += 1
            for hit in row.get("evidence", []):
                matched += 1
                print(f"  §{number}  {row['key']}")
                print(f"      score {hit['score']}  ·  {hit['file']}")
                print(f"      “{hit['quote'][:120]}…”")
                print(f"      on: {', '.join(hit['matched'][:6])}\n")

    print(f"{matched} suggestion(s) across {total} questions")
    print("\nremoving the upload again:")
    gone = post("/api/intake/remove", {"filename": name})
    print(f"  removed={gone.get('ok')}  documents now={gone['state']['count']}")

    after = sum(len(r.get("evidence", []))
                for n in ("1", "2", "3")
                for r in get(f"/api/discretion?section={n}").get("rows", []))
    print(f"  suggestions after removal: {after}  "
          f"{'OK' if after == 0 else 'STILL SHOWING — stale'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
