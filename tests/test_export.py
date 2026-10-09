"""The framework, as a document somebody can be handed.

This is the free offering. The client's model is that step 1 — writing your
framework — is free and stays yours, and steps 2–7 are the subscription. If the
export is wrong, the free tier demonstrates nothing.

Most of what is asserted here is restraint: that the document says how much is
unanswered, that it does not claim to be adopted, and above all that it carries
none of another agency's sentences. The register this once exported quoted a
`source_phrase` from the reference framework under every question; exporting
those would have put SCDES's text inside the Department of Education's
framework, which is the one rule the client has stated in capitals.

It now exports Module One — his own ten steps — rather than the mined register.
That was not cosmetic: the builder wrote Module One answers under Module One
keys, and the export looked for register keys, so a person could answer every
question on screen and download a document that said "Not yet decided" under
every one of them.
"""

from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO

import pytest
from docx import Document

from app import export, module_one, versions
from app.authz import Actor, Role

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")
#: Adoption is the deciding body's act, so it needs an actor who holds it.
DIRECTOR = Actor("council.cto", "Jordan Doe", Role.COUNCIL,
                 title="Agency Director")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "versions.json")
    yield


def visible(blob: bytes) -> str:
    """Everything a reader sees — body, tables, header, footer."""
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


# ------------------------------------------------------------------ the shape

def test_it_is_a_document_word_can_open() -> None:
    blob = export.build("Anderson County")
    assert len(blob) > 10_000
    assert zipfile.is_zipfile(BytesIO(blob))
    Document(BytesIO(blob))               # raises if the XML is malformed


def test_every_step_appears_in_order() -> None:
    body = visible(export.build("Anderson County"))
    # 00 asks nothing, so it has nothing to print.
    #
    # "Step 04 — Who decides", not "04. Who decides": the interview's step
    # numbers and the instrument's section numbers are different numbering,
    # and printed the same way an appendix heading read as a clause.
    positions = [body.index(f"Step {s.number} — {s.title}")
                 for s in module_one.STEPS if s.asks]
    assert positions == sorted(positions), "steps are out of order"


def test_any_step_not_written_yet_is_named(monkeypatch) -> None:
    """Same reason gaps are printed. A document that simply stops looks
    finished to a reader who was not in the room.

    Module One is whole, so `PENDING` is empty and the block does not appear —
    which is correct, and would make this test vacuous. It is asserted against
    a pending step instead, so the behavior is still guarded for the next
    module rather than quietly rotting away.
    """
    body = visible(export.build("Anderson County"))
    assert "Annex C" not in body, "nothing is pending today"

    monkeypatch.setattr(module_one, "PENDING",
                        [("11", "Something later", "A section")])
    later = visible(export.build("Anderson County"))
    # An annex, not a section. Anything after the page somebody signs is
    # annexed to the instrument rather than part of it.
    assert "Annex C — Sections not written yet" in later
    assert "Something later" in later


def test_it_names_the_agency_and_not_another() -> None:
    body = visible(export.build("Anderson County"))
    assert "Anderson County" in body
    assert "SCDES" not in body


# ----------------------------------------------------------------- the answers

def test_a_recorded_answer_reaches_the_page() -> None:
    versions.answer("who.tiebreak", "The Town Administrator.", OT)
    body = visible(export.build("Anderson County"))
    assert "The Town Administrator." in body


def test_a_choice_is_printed_as_the_words_they_clicked() -> None:
    """The answer is stored as an option value — "district" — which is the
    right thing to store and the wrong thing to print. Their document should
    read back the label they chose, not this platform's vocabulary."""
    versions.answer("org.kind", "district", OT)
    body = visible(export.build("Anderson County"))
    label = next(o.label for o in module_one.by_key("org.kind").options
                 if o.value == "district")
    assert label in body
    assert "\ndistrict\n" not in body


def test_a_grid_is_printed_row_by_row() -> None:
    """5.3 stores a dict of dicts. Printed raw it is unreadable; printed at all
    it is the operating core of their risk process."""
    versions.answer("risk.levels", "two", OT)
    versions.answer("risk.tiers",
                    {"routine": {"reviews": "The user's supervisor"},
                     "elevated": {"nomeeting": "no"}}, OT)
    body = visible(export.build("Anderson County"))
    assert "Routine · Who reviews it: The user's supervisor" in body
    assert "Elevated · Can it be approved without a meeting: No" in body


def test_who_answered_is_recorded_on_the_page() -> None:
    """A framework nobody signed is a draft, and the document should say who
    put each decision in it."""
    versions.answer("who.tiebreak", "The Administrator.", OT)
    body = visible(export.build("Anderson County"))
    assert "Office of Technology" in body or "CTO" in body


def test_the_count_of_answered_questions_is_stated() -> None:
    versions.answer("who.tiebreak", "The Administrator.", OT)
    # Only what this organisation was asked — a denominator that counts
    # branches they never saw makes a finished framework look unfinished.
    working = versions.state()["working"]
    total = sum(export._measure(s, working)[1] for s in module_one.STEPS)
    assert f"1 of {total}" in visible(export.build("Anderson County"))


# -------------------------------------------------------------------- the gaps

def test_unanswered_questions_are_printed_not_skipped() -> None:
    """A document that omits what is unsettled reads as finished."""
    body = visible(export.build("Anderson County"))
    assert "Not yet decided" in body


def test_a_reference_setting_is_not_printed_at_all() -> None:
    """This test was originally the other way round.

    The export printed each unanswered question's reference default, labeled
    "Reference setting, not adopted", on the reasoning that showing the
    reference was more use than showing nothing. Two tests below caught what
    that actually did: `agency.identity` defaults to a string naming SCDES and
    describing the reader as a "state environmental regulatory agency", so a
    document handed to Anderson County contained South Carolina's identity
    under a heading about its own.

    The label was not enough. A reference setting sitting under a question, in
    a document with the agency's name on the cover, is something a reader can
    take for policy — and the one place it is genuinely useful is the screen
    where somebody is choosing an answer. So it is not exported.

    The register that carried those defaults is gone — the export reads Module
    One now, which has none. The guard stays as a guard: nothing in the
    document may describe the reader as somebody else.
    """
    body = visible(export.build("Anderson County"))
    for phrase in ("state environmental regulatory agency",
                   "Reference setting", "Department of Environmental"):
        assert phrase not in body, phrase


def test_internal_cross_references_are_not_printed() -> None:
    """`propagates` describes this platform's own structures — "Appendix C
    registry entries", "the gate map" — not the agency's framework, and some
    entries carry the reference corpus's phrasing. Useful in the builder."""
    body = visible(export.build("Anderson County"))
    assert "Also governs" not in body
    assert "Appendix C registry" not in body


def test_the_questions_themselves_are_carried() -> None:
    """The draft has to be readable by someone who was not in the room, which
    means the question, not just the answer."""
    body = visible(export.build("Anderson County"))
    assert module_one.by_key("who.shape").prompt in body


def test_a_gap_is_printed_with_its_owner_rather_than_left_blank() -> None:
    """"'We don't know' is a valid answer and appears in the document as a
    stated gap with an owner — NO BLANKS." """
    versions.answer("scope.arbiter",
                    {"value": module_one.UNKNOWN, "owner": "Town Attorney"},
                    OT)
    body = visible(export.build("Anderson County"))
    assert "Not yet known" in body
    assert "Town Attorney to find out" in body


def test_a_gap_with_nobody_against_it_says_so() -> None:
    """Silently the same as a blank is exactly what it must not be."""
    versions.answer("scope.arbiter", module_one.UNKNOWN, OT)
    body = visible(export.build("Anderson County"))
    assert "No one has been named to find out." in body


def test_their_own_words_go_in_verbatim() -> None:
    """"Text goes in verbatim." Nothing rewrites, summarizes or tidies it —
    it is the one place in the module where the document takes dictation."""
    said = "Our board asked for this in April, after the audit."
    versions.answer(module_one.own_words_key("03"), said, OT)
    body = visible(export.build("Anderson County"))
    assert "In your own words" in body
    assert said in body


def test_the_floor_is_printed_with_anything_they_softened() -> None:
    """"If the user weakened one, it's shown, not hidden." The person who
    reads this document is usually not the person who filled it in."""
    versions.answer("floor.ai_finalises", "some", OT)
    body = visible(export.build("Anderson County"))
    assert "Annex A — The floor, as this organization set it" in body
    assert "Made less strict" in body
    assert "finalized by AI without a person" in body


def test_answers_that_disagree_are_named_in_the_document() -> None:
    """Reported, never blocked. Which of two answers is right is not something
    a document can decide, so it says what it found and hands it back."""
    versions.answer("risk.revisit", ["vendor_change"], OT)
    versions.answer("proc.added_ai", "nothing", OT)
    body = visible(export.build("Anderson County"))
    assert "Annex B — Answers that disagree with each other" in body
    assert "Which wins?" in body
    assert "Nothing here is blocked" in body


def test_a_consistent_framework_gets_no_disagreement_section() -> None:
    body = visible(export.build("Anderson County"))
    assert "Annex B — Answers that disagree" not in body


def test_a_question_they_were_never_asked_is_not_printed() -> None:
    """5.1's delegated-program factor appears only if 1.5 is yes. Printing the
    branch they never saw would put a hole in the document nobody left."""
    versions.answer("org.delegated", "no", OT)
    body = visible(export.build("Anderson County"))
    assert "And for the offices you don't have" not in body


# --------------------------------------------------------------- the watermark

def test_an_unadopted_framework_carries_a_real_word_watermark() -> None:
    xml = header_xml(export.build("Anderson County"))
    assert "GaiusWatermark" in xml
    assert 'string="DRAFT"' in xml
    # Without the shapetype Word draws nothing at all, which is the failure
    # mode that looks like success everywhere else.
    assert "_x0000_t136" in xml


def test_the_document_says_what_the_mark_is_for() -> None:
    """It used to apologize for the mark being removable, as though that were a
    defect. The client's intent is the opposite:

        "If they download it and have to click to remove the watermark to make
         it final, that's perfect bc it requires a human to take that action...
         That's human in authority."

    So the page explains the purpose and names the act, rather than confessing
    a limitation nobody asked about.
    """
    body = visible(export.build("Anderson County"))
    assert "Why this says DRAFT" in body
    assert "deliberate act" in body
    assert "does not become final because it was finished" in body


def test_it_names_the_act_that_actually_counts() -> None:
    """Purpose two: teach what human-in-authority looks like. A reader has to
    finish this page knowing what to do, not just what the mark means."""
    body = visible(export.build("Anderson County"))
    assert "a named person, a title and a date" in body
    assert "carries no mark" in body


def test_it_says_plainly_that_nobody_has_adopted_it() -> None:
    body = visible(export.build("Anderson County"))
    assert "nobody with authority has adopted this" in body


def test_an_adopted_framework_names_the_person_instead_of_marking_the_page() -> None:
    """The other half of the same idea. The mark comes off because there is
    somebody to name — that is what removed it, not a click in Word."""
    versions.answer("scope.units", "Everything.", OT)
    saved = versions.save_version(OT, note="Ready")
    assert saved["ok"], saved
    # The name and title come from the actor, not from arguments — the point of
    # adoption is that a person did it, so it is not something a caller states.
    adopted = versions.adopt(saved["version"]["number"], DIRECTOR,
                             adopted_on="2026-08-26",
                             note="Signed at the September meeting.")
    assert adopted["ok"], adopted

    blob = export.build("Anderson County")
    body = visible(blob)
    assert "Jordan Doe" in body
    assert "Agency Director" in body
    assert "2026-08-26" in body
    assert "Signed at the September meeting." in body
    # No mark, and no "why this says DRAFT" block either.
    assert "GaiusWatermark" not in header_xml(blob)
    assert "Why this says" not in body
    # Still honest about what was and was not checked.
    assert "did not verify the authority" in body


def test_the_watermark_follows_the_versions_module() -> None:
    """One source of truth for "is this a draft" — not two that can disagree."""
    assert versions.watermark() == "DRAFT"
    assert 'string="DRAFT"' in header_xml(export.build("A"))


# ------------------------------------------- nobody else's words on the page

def test_nothing_in_the_module_quotes_another_agency() -> None:
    """The register this replaced quoted the reference framework under every
    question to explain why it was asked. On screen that was the product
    working; in the document it was one agency's sentences inside another's
    framework, and the route by which it got there was an export nobody had
    checked. Module One carries no such quotes at all — asserted at the source,
    so no future export can leak what is not there.
    """
    assert not hasattr(module_one.Question, "source_phrase")
    blob = repr(module_one.summary({}))
    for marker in ("SCDES", "South Carolina", "Appendix",
                   "Operations Manual"):
        assert marker not in blob, marker


def test_the_reference_agency_is_never_named() -> None:
    body = visible(export.build("Anderson County"))
    for marker in ("SCDES", "South Carolina Department of Environmental",
                   "AI Governance Council of SCDES"):
        assert marker not in body


# ---------------------------------------------------------------- the filename

def test_the_filename_says_whose_what_and_that_it_is_a_draft() -> None:
    name = export.filename("ACO", today=date(2026, 8, 26))
    assert name == "ACO-AI-Governance-Framework-DRAFT-2026-08-26.docx"


def test_the_filename_cannot_escape_a_directory() -> None:
    """It goes into a Content-Disposition and onto somebody's disk."""
    name = export.filename("../../etc/passwd")
    assert "/" not in name and "\\" not in name and ".." not in name


def test_a_missing_abbreviation_does_not_repeat_the_word() -> None:
    """An agency the registry cannot name is a real case. It produced
    "Framework-AI-Governance-Framework-DRAFT-…", which reads as a bug."""
    name = export.filename("", today=date(2026, 8, 26))
    assert name == "AI-Governance-Framework-DRAFT-2026-08-26.docx"


# ------------------------------------- the framework reads as a framework

def test_the_document_states_rather_than_asks(tmp_path, monkeypatch) -> None:
    """The client, on the first export: "Is the intent to additionally create
    a unified, proper document upon completion? I would think the download
    would have the 'good' version that could be adopted with the question
    audit trail at the end."

    So the adoptable part carries none of the module's questions. Asserted
    against the questions themselves rather than a pattern, because a pattern
    for "looks like a question" also matches a numbered clause.
    """
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    for key, value in (("org.kind", "district"), ("who.shape", "existing"),
                       ("risk.levels", "two"), ("who.tiebreak", "The Clerk")):
        versions.answer(key, value, OT)
    body = visible(export.build("Anderson County"))
    front = body.split("Appendix — How this framework was decided")[0]
    leaked = [q.prompt for q in module_one.all_questions()
              if q.prompt in front]
    assert not leaked, leaked[:2]


def test_a_choice_becomes_a_clause_not_a_row(tmp_path, monkeypatch) -> None:
    """"Responsibility for AI decisions sits with A group you already have
    takes it on" is what happens when an option label written for a radio
    button is dropped into a sentence. Each such option carries a prose form.
    """
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    versions.answer("who.shape", "existing", OT)
    front = visible(export.build("Anderson County")).split("Appendix —")[0]
    assert "sits with a group this organization already has" in front
    assert "sits with A group you already have" not in front


def test_the_audit_trail_is_behind_the_framework(tmp_path,
                                                 monkeypatch) -> None:
    """"…with the question audit trail at the end." Not instead of, and not
    in front of."""
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    versions.answer("who.tiebreak", "The Clerk", OT)
    body = visible(export.build("Anderson County"))
    assert "Appendix — How this framework was decided" in body
    framework_at = body.index("1. Purpose")
    trail_at = body.index("Appendix — How this framework was decided")
    assert framework_at < trail_at
    # And the trail still carries the questions, which is its whole job.
    assert module_one.by_key("who.tiebreak").prompt in body[trail_at:]


def test_an_unanswered_section_is_named_not_dropped(tmp_path,
                                                    monkeypatch) -> None:
    """A reader has to be able to tell "we decided nothing here" from "this
    framework has no procurement rules"."""
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    body = visible(export.build("Anderson County"))
    # Found by title rather than by number. Inserting the Definitions clause
    # at 3 moved Procurement from 7 to 8, and a literal here was the only
    # thing that broke — the document was right.
    from app import prose
    number = next(s["number"] for s in prose.SECTIONS
                  if s["title"] == "Procurement")
    assert f"{number}. Procurement" in body
    # Bracketed, so that on a page of numbered clauses it cannot be read as
    # one of them.
    assert "[Not yet decided." in body


def test_their_words_are_not_re_cased(tmp_path, monkeypatch) -> None:
    """Lower-casing a free-text answer to make it fit a sentence turned
    "District Manager" into "district Manager". The module does not edit what
    they typed; it only lowers a leading article."""
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    versions.answer("who.tiebreak", "The District Manager", OT)
    front = visible(export.build("Anderson County")).split("Appendix —")[0]
    assert "the District Manager has the final say" in front
    assert "district Manager" not in front.replace("The District Manager", "")


def test_there_is_somewhere_to_sign(tmp_path, monkeypatch) -> None:
    """An unadopted framework is a draft, and drafts do not govern
    anything."""
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    body = visible(export.build("Anderson County"))
    # Numbered from the sections in front of it, so this is asserted by
    # position rather than by literal — see the numbering test below.
    from app import prose
    last = len(prose.sections(versions.state().get("working") or {}))
    assert f"{last + 2}. Adoption" in body
    assert "Approval" in body
    assert "Signature makes this framework binding" in body
    assert "upload it as the Active Framework" in body


def test_a_label_dropped_into_the_adoption_clause_is_not_left_capitalised(
        tmp_path, monkeypatch) -> None:
    """"This framework is adopted by An elected board or council, by vote."

    Every other sentence in the document lowers an option label to fit
    mid-sentence; the signature clause dropped one in raw.
    """
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    versions.answer("done.signs", "board", OT)
    body = visible(export.build("Anderson County"))
    assert "adopted by An " not in body
    assert "takes effect On " not in body


# --------------------------------------------------------------- the numbering

def _section_numbers(blob: bytes) -> list[int]:
    """The numbered top-level headings, in the order they appear."""
    doc = Document(BytesIO(blob))
    found = []
    for para in doc.paragraphs:
        if para.style.name != "Heading 1":
            continue
        head = para.text.split(".", 1)[0].strip()
        if head.isdigit():
            found.append(int(head))
    return found


def test_the_sections_are_numbered_once_each_and_in_order() -> None:
    """The two closing sections carried the literals "10." and "11.".

    `prose.SECTIONS` ends at 10, so the finished document had two section
    tens — "10. Amendment, review and publication" followed by "10. What is
    not settled yet" — which is the first thing anybody checking a policy for
    formality would find. They are numbered from the sections in front of them
    now, and this asserts the property rather than the numbers, so the same
    fault cannot come back when a section is added.
    """
    numbers = _section_numbers(export.build("Anderson County"))
    assert numbers, "no numbered sections at all"
    assert len(numbers) == len(set(numbers)), f"a number repeats: {numbers}"
    assert numbers == list(range(1, len(numbers) + 1)), numbers


def _framework_body(blob: bytes) -> list[str]:
    """The paragraphs of the adoptable part — from Purpose to the start of
    the annex and appendices, which have their own reasons to cite
    questions by number."""
    doc = Document(BytesIO(blob))
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    start = lines.index("1. Purpose")
    stop = next((i for i, t in enumerate(lines)
                 if i > start and t.startswith(("Annex", "Appendix",
                                                "About this draft"))),
                len(lines))
    return lines[start:stop]


@pytest.mark.parametrize("register", ["simplified", "formal"])
def test_no_sentence_is_numbered_in_the_framework(register) -> None:
    """The client, on the DEMO export: "Improved initial output on first
    couple of pages, but then returns to numbered sequential output."

    Purpose and Scope were prose; every section after them was one numbered
    sentence per line, and in the simplified register every section was.
    That reads as the answers with the questions taken out. Sections keep
    their numbers; sentences do not get one each.
    """
    import re
    for key, value in (("done.register", register),
                       ("who.shape", "existing"), ("who.tiebreak", "The Clerk"),
                       ("who.cadence", "quarterly"), ("risk.levels", "two")):
        versions.answer(key, value, OT)
    body = _framework_body(export.build("Anderson County"))
    numbered = [line for line in body if re.match(r"^\d+\.\d+[a-z]?\s", line)]
    assert not numbered, numbered[:3]


def test_the_sections_still_carry_their_numbers() -> None:
    """What went is the number on every sentence. "Section 4" is still
    something a board can cite."""
    versions.answer("who.tiebreak", "The Clerk", OT)
    body = _framework_body(export.build("Anderson County"))
    assert "4. Authority and governance" in body


def test_single_sentences_are_gathered_into_paragraphs() -> None:
    """One sentence per paragraph is the transcript this replaced."""
    for key, value in (("who.shape", "existing"), ("who.tiebreak", "The Clerk"),
                       ("who.cadence", "quarterly")):
        versions.answer(key, value, OT)
    body = _framework_body(export.build("Anderson County"))
    at = body.index("4. Authority and governance")
    # Matched on the Clerk rather than on "final say", which the section's
    # own purpose line also contains.
    paragraph = next(line for line in body[at + 1:]
                     if "the Clerk has the final say" in line)
    # Three answers to three different questions, one paragraph.
    assert "sits with" in paragraph


def test_the_second_name_in_a_two_part_answer_loses_a_leading_capital() \
        -> None:
    """"Disclosure wording is written by the District Manager and approved
    by The board." The first name already had its article lowered; the
    second was pasted in raw."""
    from app import prose
    answers = {"floor.disclose_who": {"value": "The District Manager",
                                      "approver": "The board"}}
    clause = prose._clause_for("floor.disclose_who", answers)
    if clause is None:
        pytest.skip("not visible without earlier answers")
    assert "approved by the board" in clause.text
    assert "approved by The board" not in clause.text


def test_the_headings_are_real_headings() -> None:
    """Bold 15pt Normal paragraphs are not headings.

    They looked like them and gave Word no navigation pane, produced no PDF
    bookmarks, and — the one that decides it — left a screen reader with no
    way to announce a heading at all. The framework this document generates
    commits its owner to WCAG 2.1 AA; it cannot itself be a wall of
    undifferentiated paragraphs.
    """
    doc = Document(BytesIO(export.build("Anderson County")))
    levels = {p.style.name for p in doc.paragraphs
              if p.style.name.startswith("Heading")}
    assert "Heading 1" in levels
    assert len([p for p in doc.paragraphs
                if p.style.name == "Heading 1"]) >= 12


def test_it_opens_on_a_title_page() -> None:
    """The reference framework opens on a page carrying nothing but what the
    document is. This opened with three centered lines directly above the text
    of section 1, which is how a form's output looks."""
    doc = Document(BytesIO(export.build("Anderson County")))
    text = [p.text.strip() for p in doc.paragraphs]
    assert "ANDERSON COUNTY" in text
    assert "Governance Framework" in text
    assert "Policy and Operating Authority" in text
    # Nothing of the instrument itself before the break.
    upto = text.index("Governance Framework")
    assert not any(t.startswith("1. ") for t in text[:upto])


def test_there_is_a_contents_page() -> None:
    body = visible(export.build("Anderson County"))
    assert "Contents" in body
    front = body.split("1. Purpose")[0]
    assert "Adoption" in front, "the contents does not list the last section"


# -------------------------------------------------------------- the definitions

def test_a_definitions_clause_is_built_from_their_own_answers() -> None:
    """The section that separates a policy from a memo — and the one place an
    invention would do the most damage, because everything downstream is then
    read through it."""
    from app import prose
    versions.answer("scope.covered", ["writes", "predicts"], OT)
    versions.answer("floor.list_owner", "The Operations Lead", OT)
    versions.answer("data.never", ["personal"], OT)

    terms = dict(prose.definitions(versions.state()["working"]))
    assert "AI tool" in terms
    assert "The list of AI tools" in terms
    assert "Restricted information" in terms
    # "the Operations Lead", not "The" — a leading article is lowered to sit
    # mid-sentence, which is the module's own rule everywhere else.
    assert "kept by the Operations Lead" in terms["The list of AI tools"]

    body = visible(export.build("Anderson County"))
    number = next(s["number"] for s in prose.SECTIONS
                  if s["title"] == "Definitions")
    assert f"{number}. Definitions" in body
    assert "carries its ordinary meaning" in body


def test_it_defines_nothing_nobody_decided() -> None:
    """An unanswered interview produces no definitions at all, rather than a
    page of plausible-sounding ones."""
    from app import prose
    assert prose.definitions({}) == []


def test_what_is_excluded_from_scope_is_carried_into_the_definition() -> None:
    from app import prose
    versions.answer("scope.covered", ["writes"], OT)
    versions.answer("scope.excluded", ["spellcheck"], OT)
    meaning = dict(prose.definitions(versions.state()["working"]))["AI tool"]
    assert "does not include" in meaning





# ------------------------------------------------- the words in the document

def test_no_jargon_reaches_the_document(monkeypatch) -> None:
    """"Never write model. Write tool."

    The same rule `test_no_jargon_reaches_the_user` holds over the questions,
    held over the thing people actually read. That test walks the module's
    copy, so it could not see the document — and a provenance paragraph
    reading "A language model rewrote the wording" shipped into the export
    and was caught by eye rather than by this suite.
    """
    from app import polish

    monkeypatch.setattr(
        polish, "sections",
        lambda built, answers: polish.Outcome(
            asked=9, changed=7, refused=1, skipped_their_words=2,
            provider="anthropic:claude-opus-5"))
    versions.answer("done.language", module_one.POLISHED, OT)
    versions.answer("scope.covered", ["writes"], OT)

    body = visible(export.build("Anderson County")).lower()
    assert "wording was produced" in body, "the polished branch did not run"
    offences = [word for word in module_one.BANNED if word in body]
    assert not offences, offences


def test_the_document_says_when_polishing_was_asked_for_and_could_not_run(
        monkeypatch) -> None:
    """Fails loudly rather than looking as though it ran and did nothing.

    On a server with no writing tool configured this is what the reader sees,
    and it has to be the truth: the wording is exactly what the answers
    assembled.
    """
    from app import polish

    monkeypatch.setattr(polish, "available",
                        lambda: (False, "No writing tool is configured."))
    versions.answer("done.language", module_one.POLISHED, OT)
    versions.answer("scope.covered", ["writes"], OT)

    body = visible(export.build("Anderson County"))
    assert "was not" in body
    assert "No writing tool is configured." in body


def test_as_written_says_nothing_about_polishing() -> None:
    """The default. A document nobody asked to polish should carry no
    paragraph about polishing at all."""
    versions.answer("scope.covered", ["writes"], OT)
    body = visible(export.build("Anderson County"))
    assert "wording was produced" not in body


# ------------------------------------------ nothing hidden in "not settled"

def test_an_empty_section_is_always_listed_as_not_settled() -> None:
    """Reported from a real export: section 10 read "Not yet decided. Listed
    in the section on matters not yet settled", and section 12 read "Nothing.
    Every question this framework asked has an answer." The list held only
    "We don't know" answers, never the questions nobody had reached."""
    versions.answer("who.amend", "same", OT)
    versions.answer("who.review", "annual", OT)
    body = visible(export.build("Anderson County"))
    assert "[Not yet decided." in body
    assert "Nothing. Every question this framework asked has an answer." \
        not in body
    asked = module_one.by_key("bad.report_to").prompt
    assert asked in body
    assert "Not answered yet — nobody named" in body


def test_nothing_answered_lists_every_open_section() -> None:
    body = visible(export.build("Anderson County"))
    assert "Nothing. Every question this framework asked has an answer." \
        not in body
    from app import prose
    listed = prose.gaps({})
    shown_empty = [s for s in prose.sections({}) if s.empty]
    # Every section printed as "not yet decided" has at least one line in
    # the list, so the sentence under its heading is true.
    for section in shown_empty:
        spec = next(x for x in prose.SECTIONS if x["number"] == section.number)
        keys = set(spec["keys"]) | {spec[n][0] for n in ("tiers", "matrix")
                                    if spec.get(n)}
        assert any(g["key"] in keys or g["key"] == f"section.{section.number}"
                   for g in listed), section.title
