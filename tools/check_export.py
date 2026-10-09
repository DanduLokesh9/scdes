"""Does the framework export produce a document worth handing to anyone?

The client asked for the sections "capable of generating a draft docx", and
this is the half that could go wrong silently. A .docx is a zip of XML: it will
save, open in python-docx and look fine while containing none of the answers,
no watermark, or — the one that matters most — another agency's sentences.

So this checks the four things that would each make the export worse than not
having one:

  1. the answers are actually in it
  2. gaps are printed rather than skipped
  3. the DRAFT watermark is a real Word watermark, and disappears on adoption
  4. no `source_phrase` reaches the page — those are SCDES's own sentences,
     quoted in the register to explain each question, and putting them inside
     another agency's framework is the leak the client drew the hardest line
     around

Usage:  python -m tools.check_export
"""

from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO

from docx import Document

from app import export, module_one, versions


def text_of(blob: bytes) -> str:
    """Everything a reader would see: body, tables, header and footer."""
    doc = Document(BytesIO(blob))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(c.text for c in row.cells)
    for section in doc.sections:
        parts.extend(p.text for p in section.header.paragraphs)
        parts.extend(p.text for p in section.footer.paragraphs)
    return "\n".join(parts)


def header_xml(blob: bytes) -> str:
    z = zipfile.ZipFile(BytesIO(blob))
    return "\n".join(z.read(n).decode("utf-8") for n in z.namelist()
                     if "header" in n)


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<46} {detail}")
        if not ok:
            failures.append(label)

    def note(label: str, detail: str = "") -> None:
        """Something a person should know that is not a defect in the export."""
        print(f"  note  {label:<46} {detail}")

    state = versions.state()
    answers = state.get("working") or {}
    # Seeding rather than skipping when the store happens to be empty. The
    # point of this tool is to build a real document and read it; against an
    # empty store it would report a page of passes having exercised nothing.
    if not any(module_one.by_key(k) for k in answers):
        note("no answers on this machine, so a few were recorded",
             "run it again after using the builder for real")
        from app.authz import Actor, Role
        who = Actor("check.export", "Export check", Role.OT, title="Harness")
        for key, value in (("org.kind", "district"), ("org.size", "u25"),
                           ("who.tiebreak", "The Town Administrator."),
                           ("risk.levels", "two")):
            versions.answer(key, value, who)
        state = versions.state()
        answers = state.get("working") or {}

    blob = export.build("Innovative Infrastructure Advising",
                        today=date(2026, 8, 26))
    body = text_of(blob)

    print("the document")
    check("it is a readable .docx", len(blob) > 10_000, f"{len(blob):,} bytes")
    check("names the agency",
          "Innovative Infrastructure Advising" in body)
    check("says what it is", "AI Governance Framework" in body)
    check("every step that asks something is present",
          all(f"{s.number}. {s.title}" in body
              for s in module_one.STEPS if s.asks))
    # Module One is whole, so there is nothing pending and no block to print.
    # The claim follows what the module reports rather than assuming there is
    # always something outstanding.
    if module_one.PENDING:
        check("and the ones not written yet are named",
              "Still to come" in body
              and all(t in body for _, t, _ in module_one.PENDING))
    else:
        check("nothing is outstanding, and the document says nothing is",
              "Still to come" not in body, "Module One is complete")

    print("\nthe answers")
    # Split by whether the key is still a question. The export reads Module
    # One; answers recorded against the register it replaced are orphaned, and
    # they belong in the report rather than counted as a failure of the export
    # or quietly dropped from the store.
    live, orphaned = [], []
    for key, held in answers.items():
        value, _ = module_one.value_of({key: held}, key)
        if not str(value or "").strip() and not isinstance(value, (dict, list)):
            continue
        (live if module_one.by_key(key) else orphaned).append(key)

    check("there are answers to check against", bool(live), f"{len(live)}")
    missing = []
    for key in live:
        said = module_one.describe(module_one.by_key(key), answers)
        if said["state"] != "answered":
            continue
        if not all(line[:60] in body for line in said["lines"]):
            missing.append(key)
    check("every recorded answer appears", not missing,
          f"missing: {missing[:3]}" if missing else f"{len(live)} found")

    # A data condition, not a defect in the export: these are answers somebody
    # gave to the register Module One replaced. They are not printed, because
    # they answer questions this framework no longer asks. Reported rather than
    # failed, so nobody discovers them by wondering where an answer went.
    if orphaned:
        note("left over from the register this replaced",
             f"{len(orphaned)} not exported: {', '.join(orphaned[:4])}")
    else:
        check("nothing is left over from the register this replaced",
              True, "none")
    # Only what this organisation was asked. A denominator counting branches
    # they never saw makes a finished framework look two-thirds done.
    total = sum(export._measure(s, answers)[1] for s in module_one.STEPS)
    done = sum(export._measure(s, answers)[0] for s in module_one.STEPS)
    check("the count is stated", f"{done} of {total}" in body,
          f"{done} of {total}")

    print("\nthe gaps")
    check("unanswered questions are printed", "Not yet decided" in body)
    # Deliberately absent: the reference default is the source agency's own
    # answer and reads as policy under a heading about somebody else's. See
    # tests/test_export.py::test_a_reference_setting_is_not_printed_at_all.
    leaked_defaults = [p for p in ("state environmental regulatory agency",
                                   "Reference setting")
                       if p in body]
    check("no reference default reaches the page", not leaked_defaults,
          f"leaked: {leaked_defaults}" if leaked_defaults else "")
    check("no internal cross-references", "Also governs" not in body)

    print("\nthe watermark")
    xml = header_xml(blob)
    check("a real Word watermark shape", "GaiusWatermark" in xml)
    check("the shapetype is defined too", "_x0000_t136" in xml,
          "without it Word renders nothing")
    check("it says DRAFT", 'string="DRAFT"' in xml)
    # The page used to apologise for the mark being removable. The client's
    # intent is the opposite — a person having to reach in and delete it is a
    # demonstration of human-in-authority, not a weakness — so it now explains
    # the purpose and names the act that actually counts.
    check("the page explains what the mark is for",
          "Why this says DRAFT" in body and "deliberate act" in body)
    check("and names the act that removes it properly",
          "a named person, a title and a date" in body)

    print("\nno other agency's words")
    # There is nothing to leak any more: Module One quotes nobody. Checked at
    # the source as well as in the document, so a future export cannot start
    # carrying what is not there today.
    blob_repr = repr(module_one.summary(answers))
    check("the module itself quotes nobody",
          not any(m in blob_repr for m in ("SCDES", "South Carolina",
                                           "Appendix", "Operations Manual")))
    for marker in ("SCDES", "South Carolina Department of Environmental"):
        check(f"no mention of {marker[:22]}", marker not in body)

    print("\nthe filename")
    name = export.filename("IIA", today=date(2026, 8, 26))
    check("says whose, what and when", name.startswith("IIA-AI-Governance"),
          name)
    check("marked DRAFT while it is one",
          ("DRAFT" in name) == bool(versions.watermark()))

    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — the export carries the answers, the gaps and nobody else's text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

