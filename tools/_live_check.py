"""Are today's fixes actually on this deployment?

Asserting "deployed" from memory is worth nothing. This asks the running
install about each ticket in turn, so the answer is the box's rather than
mine.

    cd /opt/governingai && sudo .venv/bin/python -m tools._live_check
"""

from __future__ import annotations

from app import module_one as m1, prose, states, tenancy

FAILURES: list[str] = []


def check(ref: str, what: str, ok: bool) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {ref:<14} {what}")
    if not ok:
        FAILURES.append(ref)


def options(number: str, answers: dict) -> list[str]:
    for step in m1.STEPS:
        for question in step.questions:
            if question.number == number:
                return [o["value"] for o in question.as_dict(answers)
                        ["options"]]
    return []


def asked(number: str, answers: dict) -> dict:
    for step in m1.STEPS:
        for question in step.questions:
            if question.number == number:
                return question.as_dict(answers)
    return {}


def main() -> int:
    two = {"risk.levels": {"value": "two"}}
    one = {"who.shape": {"value": "one"}}

    print("the ten from this morning")
    check("BUG-9BC45FF0", "6.5a offers two choices on a two-level framework",
          len([v for v in options("6.5a", two) if v != m1.UNKNOWN]) == 2)
    check("BUG-60400B65", "4.2 asks for one role where one person holds it",
          asked("4.2", one)["kind"] == "short")
    check("BUG-19BFF585", "4.3 asks about availability, not disagreement",
          "unavailable" in asked("4.3", one)["prompt"])
    check("BUG-DA3E8A6B", "2.1 is multi-select",
          asked("2.1", {})["kind"] == "multi")
    check("BUG-01326CF4", "11.5 / 11.5a / 11.5b exist",
          all(asked(n, {"why.has_units": {"value": "yes"}}).get("prompt")
              for n in ("11.5", "11.5a", "11.5b")))
    check("BUG-85CEBE6F", "6.8a offers No", "none" in options("6.8a", {}))
    check("BUG-8C3C816A", "7.6 option one starts with No",
          asked("7.6", {})["options"][0]["label"].startswith("No,"))
    check("BUG-25753D8D", "7.4 capitalizes the decider",
          asked("7.4", {"who.shape": {"value": "group"}})
          ["options"][0]["label"][:1].isupper())
    check("BUG-2AC1A6E5", "6.9 takes your own line items",
          bool(m1.by_key("floor.optional").can_add))
    check("BUG-08A219A6", "11.4 recommends the stricter rule",
          m1.recommended_for(m1.by_key("why.conflict"), {}) == "stricter")

    print("\nthe five from this evening")
    check("BUG-1BEA5EC5", "6.1b offers case-by-case",
          "case_by_case" in options("6.1b", {}))
    check("BUG-B949552A", "—.3 fills from 9.10 and offers on-request",
          m1.recommended_for(m1.by_key("done.where"),
                             {"watch.publish": {"value": ["framework"]}})
          == "public" and "request" in options("—.3", {}))
    check("BUG-CFD7131F", "the driver list is derived, not hand-written",
          len(m1.drivers()) > 15
          and "why.has_units" in m1.drivers()
          and "floor.plain_scope" in m1.drivers())
    check("BUG-EC53B047", "start over is reachable",
          bool(__import__("app.reset", fromlist=["preview"]).preview()))
    check("BUG-9FF9442B", "the Start Here pitch is conditional",
          "frameworkProgress" in (
              __import__("pathlib").Path("app/web/assets/app.js")
              .read_text(encoding="utf-8").split("fw-start")[0][-600:]))

    print("\nthe rest of today")
    check("polish", "the writing tool is configured",
          __import__("app.polish", fromlist=["available"]).available()[0])
    check("—.2c", "the language question is asked",
          bool(m1.by_key("done.language")))
    check("New Mexico", "open, with the domain gate",
          states.is_open("NM")
          and tenancy.check_identity("nm.env", "J D", "j@env.nm.gov").ok
          and not tenancy.check_identity("nm.env", "J D", "j@gmail.com").ok)
    check("naming", "one name for the agency everywhere",
          states.entry("NM").as_dict()["agency"]
          == states.agencies_for("NM")[0]["name"]
          == tenancy.CONFIRMED["nm.env"]["label"])
    check("terms", "the formal register says AI tool throughout",
          not any("artificial intelligence system" in s
                  for s in prose.FORMAL_SENTENCES.values()))
    check("launcher", "no corpus button",
          "lnchWhy" not in __import__("pathlib")
          .Path("app/web/assets/launcher.js").read_text(encoding="utf-8")
          .replace("There was a", ""))

    print(f"\n{len(FAILURES)} not deployed" if FAILURES
          else "\neverything above is live on this install")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
