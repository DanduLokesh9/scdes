"""Print the parts of Module One that are ours rather than his, for review.

Most of the module is his wording, transcribed. A handful of places asked for
judgment he did not make explicitly — the pre-filled levels at 5.3 and 9.3,
the contradiction rules behind the review screen, and what counts as making one
of the eight floors less strict. Those are the ones worth putting in front of
him, so this prints exactly what is in the build rather than a description of
it.

Usage:  python -m tools._dump_for_sme
"""

from __future__ import annotations

from app import module_one as m1


def _tiers(key: str, answers: dict) -> None:
    question = m1.by_key(key)
    shown = question.as_dict(answers)
    for tier in shown["rows"]:
        print(f"  {tier['label']}")
        for spec in shown["tier_fields"]:
            held = spec["defaults"].get(tier["value"], "")
            labels = {o["value"]: o["label"] for o in spec.get("options", [])}
            print(f"    {spec['label']}: {labels.get(held, held)}")


def main() -> int:
    # With offices, and without: the pre-fills name legal and IT only where
    # 1.4 said they exist, and the lowest level goes to whoever can approve
    # rather than to whoever will use it.
    has = {"risk.levels": "three", "who.shape": "group",
           "org.functions": {"it": "dedicated", "legal": "dedicated"}}
    hasnt = {"risk.levels": "three", "who.shape": "one",
             "org.functions": {"it": "none", "legal": "none"}}

    print("5.3 — three levels, an organization with IT and legal\n")
    _tiers("risk.tiers", has)

    print("\n5.3 — three levels, an organization with neither\n")
    _tiers("risk.tiers", hasnt)

    print("\n5.3 — two levels\n")
    _tiers("risk.tiers", {**has, "risk.levels": "two"})

    print("\n9.3 — how often it is checked, per level\n")
    _tiers("watch.cadence", {"risk.levels": "three"})

    print("\nThe contradiction rules\n")
    for i, rule in enumerate(m1.CONTRADICTIONS, start=1):
        print(f"  {i}. ({', '.join(rule['at'])}) {rule['line']}")

    print("\nWhat counts as making a floor less strict\n")
    floors = {g["key"]: g["title"] for g in m1.by_number("06").groups}
    for key, (_, why) in m1.WEAKENED.items():
        print(f"  {floors.get(key, key)}\n    {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
