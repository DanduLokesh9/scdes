"""An organization's framework answers, as a PDF — question by question.

Asked for (Oct 2026): when an organization passes 70% of its framework, the
5 PM technical report should carry "their answers as a report — for which
question they put which answer", as a PDF attached to the email.

Each step, each question the organization was asked, and what it answered,
read back in the labels it clicked or the words it typed — the same reading
the framework document uses (module_one.describe). "We don't know" is printed
as the stated gap it is, with its owner; a question not reached yet says so.

This sends an organization's own answers out of GAIUS, to IIA's inboxes. It
was decided by the team knowing the Terms of Use (Section 4) and the rule that
no one reaches another organization's work; each PDF sent is recorded on the
GAIUS team's side of the audit log (techreport.send).
"""

from __future__ import annotations

from typing import Any

from app.pdfwriter import Document

CONFIDENTIAL = "Confidential — GAIUS team only"


def _answers(org: str) -> dict[str, Any]:
    from app import tenant, versions
    held = tenant.set_current(org)
    try:
        return dict(versions.state().get("working") or {})
    finally:
        tenant.reset(held)


def build_pdf(org: str, organization: str, *, percent: int = 0,
              answered: int = 0, asked: int = 0, stamp: str = "") -> bytes:
    from app import module_one as m1
    answers = _answers(org)
    doc = Document(f"Framework answers — {organization}", footer_note=CONFIDENTIAL)
    doc.text("GoverningAI.US · Framework answers", size=9, gray=True)
    doc.text(organization, size=17, bold=True, before=4)
    doc.text(f"{percent}% of the framework answered — {answered} of {asked} questions"
             + (f" · as of {stamp}" if stamp else ""), size=10.5, before=2)
    doc.text("Every question this organization has been asked, and what it answered, in its "
             "own words or the choices it made. A draft until whoever holds the authority "
             "adopts it.", size=9, gray=True, before=4)
    doc.rule()

    for step in m1.STEPS:
        shown = [q for q in step.questions if m1.visible(q, answers)]
        if not shown:
            continue
        doc.text(f"Step {step.number} · {step.title}", size=13, bold=True, before=10,
                 keep_with_next=30)
        for q in shown:
            said = m1.describe(q, answers)
            doc.text(f"{q.number}  {q.prompt}", size=10, bold=True, before=7, keep_with_next=14)
            if said["state"] == "answered" or said.get("lines"):
                for line in said["lines"]:
                    doc.text(line, size=10, indent=16)
            elif said["state"] == "gap":
                owner = said.get("owner") or ""
                doc.text("We don't know yet" + (f" — owner: {owner}" if owner else
                         " — no owner named yet"), size=10, indent=16, gray=True)
            else:
                doc.text("Not answered yet", size=10, indent=16, gray=True)
    return doc.build()


def filename(organization: str, stamp: str = "") -> str:
    safe = "".join(c if c.isalnum() else "-" for c in organization).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return f"Framework-answers-{safe[:60]}{('-' + stamp) if stamp else ''}.pdf"
