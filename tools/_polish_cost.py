"""What a polished download actually costs, and how long it takes.

The client: "I don't imagine this enhancement would cost much." That is a
guess, and a guess about somebody else's bill. This measures the real thing
on a real full framework — every clause, in parallel, counting tokens from
the responses rather than estimating them — so the number he gets is the
number.

    python -m tools._polish_cost

Spends money: one whole framework's worth of polishing.
"""

from __future__ import annotations

import threading
import time

from app import env, polish, prose, versions
from tools.check_document import ANSWERS, WHO

env.load()

#: Claude Opus 5, per million tokens. Stated here so the arithmetic below can
#: be checked rather than trusted.
#:
#: Cached tokens are not free and an earlier version of this tool counted
#: them as though they were, which understated the bill by about 12%. Writing
#: to the cache costs a quarter more than plain input; reading from it costs a
#: tenth as much.
IN_PER_M = 5.00
OUT_PER_M = 25.00
CACHE_WRITE_PER_M = IN_PER_M * 1.25
CACHE_READ_PER_M = IN_PER_M * 0.10


def main() -> int:
    ok, why = polish.available()
    if not ok:
        print(f"Cannot run: {why}")
        return 2

    # The same sample answers the document check uses, so this measures a
    # whole realistic framework rather than a handful of clauses.
    for key, value in ANSWERS.items():
        versions.answer(key, value, WHO)
    answers = versions.working()

    built = prose.sections(answers)
    clauses = sum(len(s.clauses) for s in built)
    print(f"a full framework: {len(built)} sections, {clauses} clauses\n")

    # Count tokens by wrapping the SDK's own create, so every call the pass
    # makes is counted no matter which provider instance made it. A lock
    # because the pass runs these on several threads.
    from anthropic.resources.messages import Messages
    tally = {"in": 0, "out": 0, "cached": 0, "written": 0, "calls": 0}
    guard = threading.Lock()
    real = Messages.create

    def counted(self, **kwargs):
        response = real(self, **kwargs)
        usage = getattr(response, "usage", None)
        if usage:
            with guard:
                tally["in"] += getattr(usage, "input_tokens", 0) or 0
                tally["out"] += getattr(usage, "output_tokens", 0) or 0
                tally["cached"] += getattr(
                    usage, "cache_read_input_tokens", 0) or 0
                tally["written"] += getattr(
                    usage, "cache_creation_input_tokens", 0) or 0
                tally["calls"] += 1
        return response

    Messages.create = counted
    started = time.time()
    try:
        outcome = polish.sections(built, answers)
    finally:
        Messages.create = real
    took = time.time() - started

    print(outcome.summary())
    print()
    print(f"calls              : {tally['calls']}")
    print(f"input tokens       : {tally['in']:,}")
    print(f"cache writes       : {tally['written']:,}")
    print(f"cache reads        : {tally['cached']:,}")
    print(f"output tokens      : {tally['out']:,}")

    cost = (tally["in"] / 1_000_000 * IN_PER_M
            + tally["written"] / 1_000_000 * CACHE_WRITE_PER_M
            + tally["cached"] / 1_000_000 * CACHE_READ_PER_M
            + tally["out"] / 1_000_000 * OUT_PER_M)
    print(f"\ncost per polished document : ${cost:.3f}")
    print(f"wall clock                 : {took:.1f}s "
          f"({polish.AT_ONCE} at a time)")

    if outcome.rejections:
        print(f"\nwhat the checks rejected ({len(outcome.rejections)}):")
        for row in outcome.rejections:
            print(f"\n  · {row['why']}")
            print(f"    kept     : {row['clause']}")
            print(f"    refused  : {row['attempted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
