"""What each state's environmental agency uses for email, and what is owed.

Every state is open for registration, and an address is checked against the
domain recorded for the agency it claims. This prints that table so somebody
can confirm it — which is the whole point of the exercise, because for
forty-nine of the fifty-one the domain is this application's own reading and
nobody at the agency has been asked.

Two columns decide how much the check is worth.

**Whose domain it is.** `agency` means the domain belongs to the agency, so
an address ending in it is somebody who works there. `statewide` means it is
shared with every other department in the state: a `@pa.gov` address is a
Pennsylvania state employee and says nothing about which department they
work in. Most states turn out to be the second kind.

**Whether anyone checked.** `checked` means the domain was verified against
addresses the agency itself publishes. `unconfirmed` means it was not.

    python -m tools.agency_domains              everything, worst first
    python -m tools.agency_domains --owed       only what needs confirming
    python -m tools.agency_domains --csv        to send to somebody
"""

from __future__ import annotations

import sys

from app import states


def rows() -> list[dict[str, str]]:
    out = []
    for code in sorted(states.STATE_AGENCIES):
        for a in states.STATE_AGENCIES[code]:
            out.append({**a, "state": code})
    # Worst first: an unchecked statewide domain is the weakest row in the
    # table, because it admits a whole state government and no person has
    # looked at it.
    out.sort(key=lambda a: (a.get("domain_source") == states.DOMAIN_STATED,
                            a.get("domain_source")
                            != states.DOMAIN_UNCONFIRMED,
                            a.get("scope") != states.STATEWIDE_DOMAIN,
                            a["state"]))
    return out


def main(argv: list[str]) -> int:
    owed_only = "--owed" in argv
    as_csv = "--csv" in argv
    listed = states.needs_confirming() if owed_only else rows()

    if as_csv:
        print("state,agency,abbrev,domain,whose_domain,domain_source,"
              "local_part_rule")
        for a in listed:
            print(",".join([
                a["state"], '"' + a["name"] + '"', a["abbrev"], a["domain"],
                a.get("scope", ""), a.get("domain_source", ""),
                a.get("convention", "any")]))
        return 0

    print(f"{'':<4}{'AGENCY':<52}{'DOMAIN':<24}{'WHOSE':<11}WHO SAYS")
    for a in listed:
        print(f"{a['state']:<4}{a['name'][:50]:<52}{a['domain']:<24}"
              f"{a.get('scope', ''):<11}{a.get('domain_source', '')}")

    owed = states.needs_confirming()
    statewide = [a for a in owed
                 if a.get("scope") == states.STATEWIDE_DOMAIN]
    unchecked = [a for a in owed
                 if a.get("domain_source") == states.DOMAIN_UNCONFIRMED]

    print(f"\n{len(rows())} agencies, one per state and the District.")
    print(f"{len(owed)} still to confirm with the agency.")
    print(f"{len(unchecked)} carry a domain nobody has verified.")
    print(f"{len(statewide)} sit on a statewide domain, which admits every "
          f"department in that state.")
    print("\nNo local-part convention is set for any state outside South "
          "Carolina, so the local part is not checked anywhere else. A "
          "guessed rule that refuses a real deputy director is worse than "
          "no rule.")
    print("Every registration is approved by a person. On a statewide "
          "domain that approval is doing all the work, and the approver is "
          "told so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
