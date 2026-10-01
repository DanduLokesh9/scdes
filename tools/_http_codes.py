"""What the server has actually been answering. Read-only.

A 500 nobody reported is still a bug; a burst of 404s usually means an asset
never shipped. Counts the status codes in the access log and lists the paths
behind anything that is not a success or a redirect.

Usage:  python3 _http_codes.py <access.log> [how many lines]
"""

from __future__ import annotations

import collections
import re
import sys

#: Combined log format: the status is the field after the quoted request.
LINE = re.compile(r'"(?:[A-Z]+) ([^"]*?) HTTP/[^"]*" (\d{3})')


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = argv[0]
    keep = int(argv[1]) if len(argv) > 1 else 4000

    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()[-keep:]
    except OSError as why:
        print(f"could not read {path}: {why}")
        return 1

    codes: collections.Counter[str] = collections.Counter()
    bad: collections.Counter[tuple[str, str]] = collections.Counter()
    for line in lines:
        found = LINE.search(line)
        if not found:
            continue
        request, status = found.group(1), found.group(2)
        codes[status] += 1
        if status[0] in "45":
            # Query strings differ per call and would fragment the count.
            bad[(status, request.split("?")[0])] += 1

    print(f"{sum(codes.values())} requests in the last {len(lines)} lines\n")
    for status, count in sorted(codes.items()):
        print(f"  {status}  {count:>6}")

    if bad:
        print("\nfailures, by path")
        for (status, request), count in bad.most_common(20):
            print(f"  {status}  {count:>4}  {request}")
    else:
        print("\nno 4xx or 5xx at all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
