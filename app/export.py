"""The framework as a document the agency can take away.

The client's instruction was one sentence: get sections 4–13 built out "and
capable of generating a draft docx". This is the second half.

It matters more than an export usually would, because this document *is* the
free offering. The pitch is that step 1 — writing your framework — is free and
stays yours, and the rest is a subscription. Without a document, step 1 ends at
a screen and there is nothing to hand anybody.

What this does and does not claim
--------------------------------

It assembles. It does not write the agency's prose, and it does not pretend to:
every decision recorded in the register appears under its section, in order,
with the question that prompted it and the answer given. That is a draft in the
sense a consultant means it — complete in structure, with the wording left to
the people whose framework it is. Claiming more would produce confident
sentences nobody chose.

**Gaps are printed, not skipped.** An unanswered question appears as "Not yet
decided". A document that silently omits what has not been settled reads as
finished, and this one has to be readable as a work in progress by someone who
was not in the room.

**No other agency's words appear in it.** Every register row carries a
`source_phrase` quoted from the reference framework — SCDES's own sentences —
and the builder shows it on screen to explain why a question is being asked.
None of it is exported. Putting SCDES's text inside the Department of
Education's framework would be exactly the leak the client has drawn the
hardest line around, arriving by a route nobody was watching.

The watermark
-------------

`versions.watermark()` decides whether this is a draft; this draws what it says.
A real diagonal Word watermark, via the VML shape Word itself uses, rather than
a line of text at the top pretending to be one.

**It is not trying to be unremovable, and it should not be.** That was the first
reading of the requirement and it was wrong. Research bore out that no format
can deliver it — Word's own guidance is that its protections "keep honest people
honest"; a PDF watermark is one menu item to delete; the only technique that
truly fuses the mark to the page is rasterizing every page to a bitmap, which
would leave a state agency publishing a governance framework that a screen
reader cannot read, in breach of the accessibility principle printed inside it.

The client's actual intent, once stated, is better than the thing that could not
be built:

    "I do not want it to be unalterable upon downloading it, only that what they
     download is a draft form. If they download it and have to click to remove
     the watermark to make it final, that's perfect bc it requires a human to
     take that action... That's human in authority and matches everything the
     framework requires."

So the friction is the feature. A person has to reach into the header and
delete the mark, and that deliberate act is exactly what the framework means by
a human in authority — demonstrated rather than asserted. The document says as
much on its first page, and names the act that actually counts: recording the
adoption here, against a name, a title and a date. Do that and the next export
carries no mark at all.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import io
from datetime import date, datetime, timezone
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor

from app import module_one, prose, versions

GREY = RGBColor(0x60, 0x6C, 0x72)
INK = RGBColor(0x12, 0x22, 0x2A)
ALERT = RGBColor(0xB3, 0x26, 0x1E)

#: Measured off the client's own adopted framework, not chosen here. He sent
#: both the .docx and the .pdf: "Final output/draft needs to look like this in
#: style, structure, and tone. FWIW PDF is better version."
#:
#: A serif body at 11pt, headings in a dark navy at 14/12/11 bold. The
#: generator was set in Calibri, which is what makes a document look like it
#: came out of a web application — the single most visible difference between
#: the two files side by side.
BODY_FONT = "Times New Roman"
HEAD_COLOUR = RGBColor(0x1F, 0x38, 0x64)
HEAD_SIZES = {1: 14, 2: 12, 3: 11}

#: Their page setup: Letter, and margins that are not all the same.
MARGIN_TOP = 0.81
MARGIN_BOTTOM = 0.94
MARGIN_SIDE = 1.0

#: The reference framework's own front matter, measured off it rather than
#: chosen here — see `tools/_read_structure.py`. Letter, one-inch margins, the
#: organisation's name in caps at 18pt, the title at 22pt over two lines, a
#: subtitle at 13pt, then who it is for, who prepared it, and the status.
#:
#: The client, with two photographs of an adopted framework attached: "The
#: questions we are asking should provide the inputs needed to create a draft
#: that matches this." So these are not aesthetic decisions.
COVER_ORG_PT = 18
COVER_TITLE_PT = 22
COVER_SUB_PT = 13

#: Body and note sizes. The notes were 8pt, which is below what anybody should
#: have to read off a printed policy and fails the accessibility principle the
#: document itself commits its owner to.
BODY_PT = 11
NOTE_PT = 10


def _default_font(doc: Document) -> None:
    """Set the font at the document's root, not just on Normal.

    Styles that declare no font of their own — List Bullet, the table styles —
    fall through to `docDefaults`, which in python-docx's template is Calibri.
    Setting Normal alone left Calibri in the finished PDF's font list, in the
    table header cells, which is exactly the kind of detail that reads as
    "produced by software" beside a document set entirely in one serif.
    """
    root = doc.styles.element
    found = root.findall(f".//{qn('w:rFonts')}")

    defaults = root.find(qn("w:docDefaults"))
    if defaults is not None:
        run_props = defaults.find(f"{qn('w:rPrDefault')}/{qn('w:rPr')}")
        if run_props is not None and run_props.find(qn("w:rFonts")) is None:
            fonts = parse_xml(f'<w:rFonts {nsdecls("w")}/>')
            run_props.insert(0, fonts)
            found.append(fonts)

    for fonts in found:
        # The theme attributes have to go, not just be overridden. Word
        # resolves `w:asciiTheme="minorHAnsi"` in preference to a `w:ascii`
        # sitting on the same element, so setting the explicit font left the
        # theme's Calibri winning — visible as one stray Calibri-Bold in the
        # finished PDF's font list, in the table header cells.
        for attribute in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme",
                          "w:eastAsiaTheme"):
            if fonts.get(qn(attribute)) is not None:
                del fonts.attrib[qn(attribute)]
        for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            fonts.set(qn(attribute), BODY_FONT)


def _use_real_headings(doc: Document) -> None:
    """Make the document's headings actual Word headings.

    They were bold Normal paragraphs at 15pt. They *looked* like headings and
    were not: no navigation pane, no PDF bookmarks, no table of contents that
    Word can build, and — the one that matters most here — nothing for a
    screen reader to announce as a heading. A governance framework that
    commits its owner to WCAG 2.1 AA cannot be delivered as a wall of
    undifferentiated paragraphs.

    Restyled rather than accepted as Word ships them: the stock Heading 1 is
    a blue sans-serif, which does not belong on an adopted instrument.
    """
    for level, size in HEAD_SIZES.items():
        style = doc.styles[f"Heading {level}"]
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.italic = False
        style.font.color.rgb = HEAD_COLOUR
        style.paragraph_format.space_before = Pt(16 if level == 1 else 12)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True


def _page_number_footer(paragraph) -> None:
    """A real page-number field, so it counts rather than saying "Page 1".

    The reference framework's footer is a page number and nothing else. This
    adds the document's own identity beside it, because a draft in
    circulation needs to say what it is on every sheet.
    """
    run = paragraph.add_run()
    run.font.size = Pt(9)
    run.font.color.rgb = GREY
    for xml in (f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>',
                f'<w:instrText {nsdecls("w")} xml:space="preserve">PAGE'
                f'</w:instrText>',
                f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'):
        run._r.append(parse_xml(xml))


def _watermark_xml(text: str) -> str:
    """The VML shape Word uses for a watermark.

    Verbose because it is Word's own definition — the shapetype with its
    fourteen formulas is what makes the text follow the path and scale to the
    box. Emitting the shape without the shapetype renders in some readers and
    not in Word, which is the one reader that matters here.
    """
    return (
        f'<w:p {nsdecls("w", "r")} '
        f'xmlns:v="urn:schemas-microsoft-com:vml" '
        f'xmlns:o="urn:schemas-microsoft-com:office:office">'
        f'<w:r><w:pict>'
        f'<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136"'
        f' adj="10800" path="m@7,l@8,m@5,21600l@6,21600e">'
        f'<v:formulas>'
        f'<v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/>'
        f'<v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/>'
        f'<v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/>'
        f'<v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/>'
        f'<v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/>'
        f'<v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/>'
        f'<v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/>'
        f'</v:formulas>'
        f'<v:path textpathok="t" o:connecttype="custom"'
        f' o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800"'
        f' o:connectangles="270,180,90,0"/>'
        f'<v:textpath on="t" fitshape="t"/>'
        f'</v:shapetype>'
        f'<v:shape id="GaiusWatermark" type="#_x0000_t136"'
        f' style="position:absolute;margin-left:0;margin-top:0;'
        f'width:452pt;height:113pt;rotation:315;z-index:-251658752;'
        f'mso-position-horizontal:center;'
        f'mso-position-horizontal-relative:margin;'
        f'mso-position-vertical:center;'
        f'mso-position-vertical-relative:margin"'
        f' fillcolor="#d8dde0" stroked="f">'
        f'<v:textpath style="font-family:&quot;Calibri&quot;;font-size:1pt"'
        f' string="{text}"/>'
        f'</v:shape>'
        f'</w:pict></w:r></w:p>')


def _small(paragraph, text: str, colour: RGBColor = GREY,
           italic: bool = False, bold: bool = False,
           size: float = 9.5) -> None:
    """Secondary text — table cells, captions, footers.

    The default was 8.5pt and it was being used for whole paragraphs of the
    front matter. Table cells can carry it; body copy cannot, so the callers
    that print sentences now pass NOTE_PT.
    """
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = colour
    run.italic = italic
    run.bold = bold


def _answered(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return state.get("working") or {}


def _adopted_title(adopted: dict[str, Any]) -> str:
    """The adopter's job title, from whichever record wrote it.

    Two modules record an adoption and they do not agree on the key:
    `versions.adopt` writes `adopted_title`, and the older single-record file in
    `framework.record_adoption` writes `adopted_by_title`. Reading only one of
    them silently dropped the title from the document — which matters, because
    "who adopted this, and in what capacity" is the whole content of the block.
    """
    return str(adopted.get("adopted_title")
               or adopted.get("adopted_by_title") or "").strip()


def _why_it_says_draft(doc: Document, stamp: str) -> None:
    """The mark, and the act that takes it off.

    This block used to apologize. It explained that the watermark could be
    deleted by anyone with Word, as though that were a defect being owned up to.
    The client corrected the premise: the mark is not trying to be a lock, and
    the fact that a person has to reach in and remove it is the *point*. It
    demonstrates two things — that nothing here was adopted without somebody
    doing it, and what "a human in authority" looks like when it is an action
    rather than a sentence in a policy.

    So it says what the mark is for, and names the act. A reader who deletes it
    by hand has done something deliberate, which is what was wanted; and the
    document tells them plainly that the deliberate act which actually counts
    is recorded here, not performed in Word.
    """
    doc.add_paragraph()
    _heading(doc, f"Why this says {stamp}", level=2)

    for text in (
        f"Nobody with authority has adopted this text. The {stamp} mark says so "
        f"on every page, and it stays there until somebody does.",

        "Taking it off is a deliberate act, and that is the point of it. This "
        "framework requires that decisions affecting the public rest with a "
        "person, not with a process running on its own — and its own adoption "
        "is the first place that has to be true. A document does not become "
        "final because it was finished. It becomes final because someone with "
        "the authority to do so said it was.",

        "The act that counts is recording the adoption here, against a named "
        "person, a title and a date. Do that and the next document you export "
        "carries no mark, and the record shows who stood behind it. Deleting "
        "the mark in Word instead is possible — it takes a few clicks in the "
        "header — but it changes only the paper, and the paper will then "
        "disagree with the record.",
    ):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        _small(p, text, size=NOTE_PT)


def _who_adopted_it(doc: Document, adopted: dict[str, Any], label: str) -> None:
    """The counterpart. No mark, because there is a person to name instead."""
    doc.add_paragraph()
    _heading(doc, "Adopted", level=2)

    who = adopted.get("adopted_by") or "an unnamed person"
    title = _adopted_title(adopted)
    when = adopted.get("adopted_on") or "an unstated date"
    # `adoption_note`, not `note` — `note` on this record is what was written
    # when the *version* was saved, which is a different sentence by a
    # different person.
    note = (adopted.get("adoption_note") or "").strip()
    number = adopted.get("number")

    p = doc.add_paragraph()
    _small(p, (f"Version {number}" if number else "This framework")
              + f" was adopted on {when} by {who}"
              + (f", {title}" if title else "") + ".", INK)
    if note:
        _small(doc.add_paragraph(), f"They recorded: {note}")
    _small(doc.add_paragraph(),
           "This carries no draft mark because there is a person to name "
           "instead. What that person attested to is that they hold the "
           "authority to adopt it — the platform recorded the claim and the "
           "date; it did not verify the authority.")


def _centred(doc: Document, text: str, size: int, *, bold: bool = False,
             colour: RGBColor = INK) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = colour


def _cover(doc: Document, state: dict[str, Any], agency: str,
           answers: dict[str, Any], today: date) -> None:
    """A title page, laid out as the reference framework lays one out.

    This was three lines at the top of page one, immediately above the
    contents of section 1 — which is how a form's output looks, not how an
    instrument looks. An adopted policy opens on a page that carries nothing
    but what the document is, who it is for, and whether it is signed.
    """
    adopted = state.get("adopted") or {}
    label = state.get("export_label") or versions.export_label()
    stamp = state.get("watermark") or ""

    for _ in range(4):
        doc.add_paragraph()

    # Their own name, in caps, as the reference has it. Split on a comma or a
    # dash so a long name breaks where its author would break it rather than
    # wherever the margin falls.
    for line in _cover_name(agency):
        _centred(doc, line.upper(), COVER_ORG_PT, bold=True)

    doc.add_paragraph()
    _centred(doc, "Artificial Intelligence", COVER_TITLE_PT, bold=True)
    _centred(doc, "Governance Framework", COVER_TITLE_PT, bold=True)
    _centred(doc, "Policy and Operating Authority", COVER_SUB_PT, colour=GREY)

    doc.add_paragraph()
    # Who it is for is their own answer at —.2 where they gave one: the person
    # or body that signs is the person or body it is put to.
    for line in _cover_lines(answers, state, agency, today):
        _centred(doc, line, NOTE_PT, colour=GREY)

    if stamp:
        doc.add_paragraph()
        _centred(doc, label, BODY_PT, bold=True, colour=ALERT)
    elif adopted.get("adopted_on"):
        doc.add_paragraph()
        _centred(doc, f"Adopted {adopted['adopted_on']}", BODY_PT, bold=True)

    doc.add_page_break()


def _cover_name(agency: str) -> list[str]:
    """The organization's name over one or two lines.

    The reference puts "SOUTH CAROLINA" above "DEPARTMENT OF ENVIRONMENTAL
    SERVICES" — the jurisdiction, then the body. Long names are broken at the
    same joint where one exists, and left alone where it does not, rather than
    being wrapped by the margin mid-word at 18pt.
    """
    name = " ".join((agency or "").split())
    if not name:
        return ["This organization"]
    if len(name) <= 34:
        return [name]
    for joint in (" Department of ", " Office of ", " Division of ",
                  " District ", " Authority ", " Commission "):
        if joint in name:
            head, _, tail = name.partition(joint)
            return [head, (joint + tail).strip()]
    words = name.split()
    middle = len(words) // 2
    return [" ".join(words[:middle]), " ".join(words[middle:])]


def _cover_lines(answers: dict[str, Any], state: dict[str, Any],
                 agency: str, today: date) -> list[str]:
    """Prepared for, prepared by, and the status line.

    "Prepared by" is the organization itself, and says so. Naming a person
    would be inventing an author; naming us would claim authorship of
    somebody else's policy. The framework was assembled from their answers,
    which is what the line says.
    """
    adopted = state.get("adopted") or {}
    lines = []

    signs = module_one.by_key("done.signs")
    said = module_one.describe(signs, answers) if signs else {"state": "blank"}
    if said.get("state") == "answered" and said.get("lines"):
        lines.append(f"Prepared for: {said['lines'][0]}")
    else:
        lines.append("Prepared for: the body or officer with authority to "
                     "adopt it")

    lines.append(f"Prepared by: {agency or 'this organization'}, from its own "
                 f"recorded decisions")

    if adopted.get("adopted_on"):
        who = adopted.get("adopted_by") or "unstated"
        title = _adopted_title(adopted)
        lines.append(f"Status: Adopted {adopted['adopted_on']} by {who}"
                     + (f", {title}" if title else ""))
    else:
        lines.append(f"Status: Draft for review · "
                     f"{today.strftime('%d %B %Y')}")
    return lines


def _provenance(doc: Document, state: dict[str, Any], agency: str,
                total: int, answered: int, today: date,
                tidied: Any = None) -> None:
    """The page after the cover: what this is, and what it is not.

    Kept off the instrument's own pages. The reference framework has no such
    note, and it should not — an explanation of how a document was produced is
    not one of its clauses. It goes here, once, under its own heading, and
    then the framework starts on a clean page at section 1.
    """
    adopted = state.get("adopted") or {}
    stamp = state.get("watermark") or ""
    label = state.get("export_label") or versions.export_label()

    doc.add_page_break()
    _heading(doc, "About this draft, and how it was produced", level=1)

    facts = [
        ("Assembled", today.strftime("%d %B %Y")),
        ("Decisions recorded", f"{answered} of {total}"),
        ("Version", label),
    ]
    if adopted.get("adopted_on"):
        who = adopted.get("adopted_by") or "unstated"
        title = _adopted_title(adopted)
        facts.append(("Adopted", f"{adopted['adopted_on']} by {who}"
                                 + (f", {title}" if title else "")))
    else:
        facts.append(("Adopted", "No — nobody with authority has adopted this"))

    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for name, value in facts:
        cells = table.add_row().cells
        p = cells[0].paragraphs[0]
        _small(p, name, INK, bold=True)
        _small(cells[1].paragraphs[0], value, INK)

    doc.add_paragraph()
    _heading(doc, "How to read this document", level=2)

    notes = [
        "This document is in two parts. The first is the framework itself, "
        "written as the statements your organization has decided on — that is "
        "the part put forward for adoption. The second, at the back, is the "
        "record of how each statement was arrived at: every question, the "
        "answer given, and who gave it.",
        "Nothing in the framework was written on your behalf. Every sentence "
        "is assembled from an answer you recorded, and a question nobody has "
        "answered yet produces no sentence — it appears in “What is not "
        "settled yet” instead, with the person who owns settling it. A "
        "framework that hides its gaps reads as finished when it is not.",
        "The wording is yours to change. It is drafted to be adoptable as it "
        "stands, not to be final.",
    ]
    for text in notes:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        _small(p, text, INK, size=NOTE_PT)

    # Whether a writing tool has been over the wording, and what it did.
    #
    # Said out loud because a reader is entitled to know whether the
    # sentences in front of them are the ones the answers assembled or a
    # tidied version of them — and because the rejection count is the honest
    # measure of how much the checks caught.
    if tidied is not None and getattr(tidied, "ran", False):
        doc.add_paragraph()
        _heading(doc, "How the wording was produced", level=2)

        # The warning first, and in the document rather than only on the
        # screen they clicked through twenty minutes ago.
        #
        # "We need to flash a disclaimer that the polished version uses an
        # LLM which may adjust or alter their statements (trying to address
        # the non-deterministic nature) and that additional scrutiny should
        # be provided when reviewing the output."
        #
        # This paragraph is emphasised because the person who most needs it
        # is not the person who chose Polished — it is whoever is handed the
        # file afterwards and asked to sign it.
        warning = doc.add_paragraph()
        warning.paragraph_format.space_after = Pt(8)
        run = warning.add_run(
            "Read this document carefully before relying on it. ")
        run.bold = True
        run.font.size = Pt(NOTE_PT)
        run.font.color.rgb = INK
        _small(warning,
               "The wording below was rewritten by an AI writing tool. It "
               "does not produce the same wording twice: asking for this "
               "again would give you a differently worded document holding "
               "you to the same rules. The checks described below are "
               "thorough and they are not a substitute for a person reading "
               "what this says.", INK, size=NOTE_PT)

        for text in (
            f"You asked for the language to be polished. An AI writing tool "
            f"({tidied.provider}) rewrote the wording of the clauses below, "
            f"one clause at a time. {tidied.summary()}",

            "It was not permitted to add a requirement, remove one, or change "
            "what any clause requires — and every rewrite was checked against "
            "the original for changed numbers, changed obligations, changed "
            "deadlines and dropped names before it was kept. A rewrite that "
            "failed any of those checks was discarded and the original "
            "sentence used instead.",

            "Sentences you typed yourself were not sent anywhere and were not "
            "rewritten. Where a plain misspelling was found in one it was "
            "corrected, and the words corrected are named above; nothing else "
            "in your own writing was touched. The version before polishing is "
            "kept in your version history, so the two can be compared.",
        ):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            _small(p, text, INK, size=NOTE_PT)
    elif (tidied is not None and getattr(tidied, "note", "")
            and module_one.language_of(_answered(state))
            == module_one.POLISHED):
        # Asked for, and could not be done. Better said than silently not
        # happening — the document would otherwise look as though polishing
        # had run and achieved nothing.
        doc.add_paragraph()
        _heading(doc, "How the wording was produced", level=2)
        p = doc.add_paragraph()
        _small(p, f"You asked for the language to be polished, and it was "
                  f"not. {tidied.note} What follows is exactly what your "
                  f"answers assemble into.", INK, size=NOTE_PT)

    if stamp:
        _why_it_says_draft(doc, stamp)
    elif adopted.get("adopted_on"):
        _who_adopted_it(doc, adopted, label)

    doc.add_page_break()


def _update_fields_on_open(doc: Document) -> None:
    """Ask Word to refresh its fields when the document opens.

    This is what makes the table of contents real. Without it a TOC field
    renders empty until somebody knows to press F9, and a policy that arrives
    looking broken is worse than one with no contents page at all. With it,
    Word fills in the headings, the dot leaders and the page numbers on open —
    which is exactly how the client's own PDF was produced.
    """
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is None:
        settings.append(parse_xml(
            f'<w:updateFields {nsdecls("w")} w:val="true"/>'))


def _contents(doc: Document, sections: list[Any], tail: list[str]) -> None:
    """A contents page, as the client's own framework has one.

    A real Word TOC field over levels 1–3, so it carries the dot leaders and
    the page numbers his does — a typed list of titles cannot know what page
    anything lands on. The static list underneath it is not a fallback: it is
    what a reader sees in a viewer that does not evaluate fields, and Word
    replaces it wholesale when it evaluates the field, so the two can never
    both be shown.
    """
    # Bold text, not a heading — which is how his own contents page is set,
    # and the reason it does not appear as the first entry in its own list.
    title = doc.add_paragraph()
    run = title.add_run("Table of Contents")
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = HEAD_COLOUR

    holder = doc.add_paragraph()
    run = holder.add_run()
    # \o "1-2"  headings one and two only
    # \h        each entry a hyperlink
    # \z        hide tab leader and page numbers in a web view
    # \u        use the applied paragraph outline level
    #
    # Levels one and two, not three: the appendix's thirteen step headings are
    # level three, and listing them ran the contents onto a second page and
    # pushed the instrument back to page five. A contents page is for finding
    # a clause, not for enumerating the audit trail.
    for xml in (f'<w:fldChar {nsdecls("w")} w:fldCharType="begin" '
                f'w:dirty="true"/>',
                f'<w:instrText {nsdecls("w")} xml:space="preserve">'
                f'TOC \\o "1-2" \\h \\z \\u</w:instrText>',
                f'<w:fldChar {nsdecls("w")} w:fldCharType="separate"/>'):
        run._r.append(parse_xml(xml))

    # What a field-less viewer shows, and what Word overwrites on open.
    for number_and_title in ([f"{s.number}. {s.title}" for s in sections]
                             + list(tail)):
        line = doc.add_paragraph()
        line.paragraph_format.space_after = Pt(3)
        number, _, title = number_and_title.partition(". ")
        run = line.add_run(f"{number}.  ")
        run.bold = True
        run.font.size = Pt(BODY_PT)
        run.font.color.rgb = GREY
        run = line.add_run(title)
        run.font.size = Pt(BODY_PT)
        run.font.color.rgb = INK

    closing = doc.add_paragraph()
    run = closing.add_run()
    run._r.append(parse_xml(
        f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'))

    doc.add_page_break()

    # Their framework leaves page 3 blank so the body opens on page 4, and
    # says so on it rather than leaving a reader wondering whether something
    # failed to print.
    for _ in range(4):
        doc.add_paragraph()
    _centred(doc, "Page intentionally left blank.", BODY_PT, colour=GREY)
    doc.add_page_break()


def _heading(doc: Document, text: str, level: int = 1) -> None:
    """A section heading, as a heading — see `_use_real_headings`."""
    paragraph = doc.add_paragraph(style=f"Heading {level}")
    paragraph.add_run(text)


def _body(doc: Document, text: str, italic: bool = False) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(8)
    run = paragraph.add_run(text)
    run.font.size = Pt(BODY_PT)
    run.font.color.rgb = INK
    run.italic = italic


def _table(doc: Document, head: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=0, cols=len(head))
    table.style = "Table Grid"
    if any(h for h in head):
        cells = table.add_row().cells
        for cell, name in zip(cells, head):
            _small(cell.paragraphs[0], name, INK, bold=True)
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            _small(cell.paragraphs[0], str(value), INK)


def _the_framework(doc: Document, answers: dict[str, Any],
                   built: list[Any]) -> None:
    """Part one: the document somebody adopts.

    Statements, not questions. "A board does not adopt a transcript" is the
    whole of the client's note, and it is right — the question-and-answer form
    invites a reader to audit the process instead of the policy.
    """
    formal = module_one.register_of(answers) == module_one.FORMAL
    # The sections are built once, in `build`, and handed down. They used to
    # be built here as well as there — harmless while assembling was pure,
    # and wrong the moment a polish pass could rewrite them, because the
    # copy that was numbered would not have been the copy that was printed.
    for section in built:
        _heading(doc, f"{section.number}. {section.title}")

        # The signpost under each heading is an editor's note, and the
        # reference framework has none — its sections open on their substance.
        # Kept in the simplified register, where a plain-English lead-in is
        # the point of that register, and dropped from the formal one.
        if not formal:
            _small(doc.add_paragraph(), section.purpose, GREY, italic=True,
                   size=NOTE_PT)

        if section.empty:
            # A section with nothing decided in it is named and left open,
            # rather than dropped. A reader has to be able to tell the
            # difference between "we decided nothing here" and "this framework
            # has no procurement rules".
            #
            # Bracketed, so that on a page of clauses it cannot be misread as
            # one of them.
            run = doc.add_paragraph().add_run(
                "[Not yet decided. Listed in the section on matters not yet "
                "settled, with the person who owns settling it.]")
            run.italic = True
            run.font.size = Pt(BODY_PT)
            run.font.color.rgb = ALERT
            doc.add_paragraph()
            continue

        # A definitions clause: the term in bold at the head of its own
        # paragraph, which is how the reference framework sets its own. The
        # term is what a reader cites — "as defined, a final action" — so it
        # carries no number of its own, like every other paragraph now.
        if section.terms:
            _body(doc, "The following terms carry specific meaning throughout "
                       "this framework. Where a term is used and is not "
                       "defined here, it carries its ordinary meaning.")
            for term, meaning in section.terms:
                paragraph = doc.add_paragraph()
                paragraph.paragraph_format.space_after = Pt(8)
                run = paragraph.add_run(f"{term}. ")
                run.bold = True
                run.font.size = Pt(BODY_PT)
                run.font.color.rgb = INK
                run = paragraph.add_run(meaning)
                run.font.size = Pt(BODY_PT)
                run.font.color.rgb = INK
            doc.add_paragraph()
            continue

        # Paragraphs, in both registers, under a numbered section heading.
        #
        # This rendered sections 1 and 2 as prose in the formal register and
        # everything else — every section, in the simplified one — as one
        # numbered sentence per line. The client: "Improved initial output on
        # first couple of pages, but then returns to numbered sequential
        # output." A numbered line per sentence reads as the answers with the
        # questions removed; a policy reads as paragraphs. How sentences are
        # gathered is in `prose.paragraphs`, and never changes their order.
        if section.number in prose.FLOWING:
            for group in prose.paragraphs(section):
                _body(doc, " ".join(c.text for c in group))

        for table in section.tables:
            doc.add_paragraph()
            _small(doc.add_paragraph(), table["title"], INK, bold=True,
                   size=NOTE_PT)
            _table(doc, table["head"], table["rows"])

        if section.own_words:
            doc.add_paragraph()
            _small(doc.add_paragraph(), "In this organization's own words",
                   INK, bold=True, size=NOTE_PT)
            for line in section.own_words.splitlines():
                if line.strip():
                    _body(doc, line.strip(), italic=True)

        doc.add_paragraph()


def _not_settled(doc: Document, answers: dict[str, Any], number: int,
                 built: list[Any] | None = None) -> None:
    """Its own section, so a reader deciding whether to adopt sees the whole
    list at once rather than meeting the holes one at a time.

    Numbered from the sections that precede it rather than hardcoded. It said
    "10." while the last generated section was also "10.", so the instrument
    had two section tens — which is the first thing anybody checking a policy
    for formality would find.
    """
    # The same sections the document printed, so a section shown as "not yet
    # decided" is always listed here.
    found = prose.gaps(answers, built)
    _heading(doc, f"{number}. Matters not yet settled")
    _small(doc.add_paragraph(),
           "Recorded rather than left blank. A framework that says where its "
           "holes are can be audited; one that hides them cannot.",
           GREY, italic=True, size=NOTE_PT)
    if not found:
        _body(doc, "Nothing. Every question this framework asked has an "
                   "answer.")
        doc.add_paragraph()
        return
    _table(doc, ["Question", "Who will settle it"],
           [[f"{g['number']}  {g['question']}",
             g["owner"] or ("Not answered yet — nobody named"
                            if g.get("unanswered") else "Nobody named yet")]
            for g in found])
    doc.add_paragraph()


def _signature_block(doc: Document, answers: dict[str, Any],
                     state: dict[str, Any], number: int) -> None:
    """Where a person signs.

    Laid out as the reference Adoption Directive lays it out: a clause saying
    what signing does, then a signature rule with the role and the date under
    it. A four-row bordered table headed "Signed / Name / Title / Date" is a
    form to be filled in; a ruled line above a printed role is what somebody
    actually signs, and it survives being printed.
    """
    _heading(doc, f"{number}. Adoption")
    signs = module_one.by_key("done.signs") or module_one.by_key("who.signs")
    said = module_one.describe(signs, answers) if signs else {"state": "blank"}
    who = said["lines"][0] if said.get("state") == "answered" else ""

    if who:
        # One paragraph, unnumbered, like every other section's body. This
        # carried "13.1" and "13.2" by its own hand after the rest of the
        # document had stopped numbering sentences.
        said_here = (f"This framework is adopted by {prose.mid_sentence(who)}. "
                     f"On signature below it is binding on this organization, "
                     f"and remains in effect until amended or superseded under "
                     f"the section on amendment and review.")
        effective = str(module_one.value_of(answers, "done.signs")[1]
                        .get("effective", "")).strip()
        if effective:
            said_here += f" It takes effect {prose.mid_sentence(effective)}."
        _body(doc, said_here)
    else:
        _body(doc, "[Who adopts this framework has not been recorded. Until "
                   "it is, there is nobody for this page to be signed by.]",
              italic=True)

    doc.add_paragraph()
    _heading(doc, "Approval", level=2)
    doc.add_paragraph()

    # The rule, then what sits under it. Two paragraphs rather than a table:
    # a signature line is a line.
    rule = doc.add_paragraph()
    rule.paragraph_format.space_after = Pt(2)
    run = rule.add_run("_" * 56 + "    " + "_" * 18)
    run.font.size = Pt(BODY_PT)
    run.font.color.rgb = INK

    under = doc.add_paragraph()
    run = under.add_run((who or "Signature") + " " * 34 + "Date")
    run.font.size = Pt(NOTE_PT)
    run.font.color.rgb = GREY

    doc.add_paragraph()
    _small(doc.add_paragraph(),
           "Signature makes this framework binding on the organization. "
           "Once signed, scan this page and upload it as the Active "
           "Framework — that upload, not this file, is what removes the "
           "draft mark.", GREY, italic=True, size=NOTE_PT)
    doc.add_paragraph()


def _the_audit_trail(doc: Document, answers: dict[str, Any]) -> None:
    """Part two, at the back, exactly where he asked for it.

    "It is fine to keep it as a log with each question asked/answered... I
    would think the download would have the 'good' version that could be
    adopted with the question audit trail at the end."
    """
    doc.add_page_break()
    _heading(doc, "Appendix — How this framework was decided", level=1)
    _small(doc.add_paragraph(),
           "Every question this organization was asked, the answer it gave, "
           "and who gave it. The framework above is assembled from these; "
           "this is how to check it.", GREY, italic=True)
    doc.add_paragraph()

    for step in module_one.STEPS:
        _step(doc, step, answers)


def _stamp_for(raw: Any) -> str:
    """"Recorded by X on Y", from the wrapper `versions.answer` puts on.

    The value itself is unwrapped for printing; this reads the outer record,
    which is where who-and-when lives.
    """
    if not isinstance(raw, dict):
        return ""
    who = str(raw.get("by") or "").strip()
    when = str(raw.get("at") or "")[:10]
    if not who and not when:
        return ""
    return ("Recorded by " + (who or "an unnamed user")
            + (f" on {when}" if when else ""))


def _step(doc: Document, step: Any,
          answers: dict[str, Any]) -> tuple[int, int]:
    """One step of the module. Returns (answered, asked) for its questions.

    Only the questions this organization was actually asked. A step's questions
    branch on earlier answers — 5.1 does not offer the delegated-program factor
    to an organization that runs no delegated program — and printing a question
    that was never on screen would put a hole in the document that nobody left.
    """
    asked = [q for q in step.questions if module_one.visible(q, answers)]
    if not asked:
        return 0, 0

    # Level three, so these nest under the appendix in the navigation pane and
    # stay out of the contents page, which lists levels one and two.
    #
    # "Step 04", not "04.", so an appendix heading cannot be misread as clause
    # 4 of the framework: the interview's step numbers and the document's
    # section numbers are different numbering, and they used to look identical.
    _heading(doc, f"Step {step.number} — {step.title}", level=3)

    if step.writes:
        intro = doc.add_paragraph()
        _small(intro, step.writes, GREY, italic=True)

    answered = 0
    for question in asked:
        label = doc.add_paragraph()
        run = label.add_run(f"{question.number}  "
                            + module_one._fill(question.prompt, answers))
        run.bold = True
        run.font.size = Pt(10.5)
        run.font.color.rgb = INK

        said = module_one.describe(question, answers)

        if said["state"] == "answered":
            answered += 1
            for line in said["lines"]:
                body = doc.add_paragraph(
                    style="List Bullet" if len(said["lines"]) > 1 else None)
                run = body.add_run(line)
                run.font.size = Pt(11)
                run.font.color.rgb = INK
            stamp = _stamp_for(answers.get(question.key))
            if stamp:
                _small(doc.add_paragraph(), stamp)

        elif said["state"] == "gap":
            # His rule, and the reason this is not just "not answered": a
            # framework with holes that says so is auditable; one with holes it
            # does not mention is not.
            body = doc.add_paragraph()
            run = body.add_run(
                "Not yet known. " + (f"{said['owner']} to find out and record "
                                     f"the answer here."
                                     if said["owner"]
                                     else "No one has been named to find out."))
            run.italic = True
            run.font.size = Pt(11)
            run.font.color.rgb = ALERT

        else:
            body = doc.add_paragraph()
            run = body.add_run("Not yet decided.")
            run.italic = True
            run.font.size = Pt(11)
            run.font.color.rgb = ALERT

    # Their own paragraph, verbatim and unlabelled as anything but theirs.
    # "Text goes in verbatim" — nothing here rewrites, summarises or tidies it.
    said = str(module_one.value_of(
        answers, module_one.own_words_key(step.number))[0] or "").strip()
    if said:
        head = doc.add_paragraph()
        _small(head, "In your own words", INK, bold=True)
        for line in said.splitlines():
            if line.strip():
                run = doc.add_paragraph().add_run(line.strip())
                run.font.size = Pt(11)
                run.font.color.rgb = INK

    doc.add_paragraph()
    return answered, len(asked)


def _the_floor(doc: Document, answers: dict[str, Any]) -> None:
    """The eight, and how strictly each was set.

    "A short checklist showing all eight requirements are addressed, and how
    strictly. If the user weakened one, it's shown, not hidden." Printed as
    well as shown on screen, because the person who reads this document is
    usually not the person who filled it in.
    """
    floors = module_one.floor_state(answers)
    if not floors:
        return
    _heading(doc, "Annex A — The floor, as this organization set it", level=1)

    for floor in floors:
        p = doc.add_paragraph()
        mark = "Set" if floor["settled"] else (
            f"{floor['answered']} of {floor['asked']} answered")
        run = p.add_run(f"{floor['number']} · {floor['title']} — {mark}")
        run.font.size = Pt(10.5)
        run.font.color.rgb = INK if floor["settled"] else ALERT
        if floor["weakened"]:
            _small(doc.add_paragraph(),
                   f"Made less strict: {floor['weakened_note']}", ALERT,
                   bold=True)
    doc.add_paragraph()


def _what_disagrees(doc: Document, answers: dict[str, Any]) -> None:
    """Two answers that cannot both be operated, named rather than resolved.

    Which of them is right is not something a document can decide, so it says
    what it found and hands the choice back.
    """
    found = module_one.contradictions(answers)
    if not found:
        return
    _heading(doc, "Annex B — Answers that disagree with each other", level=1)
    _small(doc.add_paragraph(),
           "Nothing here is blocked. These are places where two answers "
           "cannot both be followed, and somebody has to choose.", GREY,
           italic=True)
    for item in found:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(item["line"])
        run.font.size = Pt(11)
        run.font.color.rgb = ALERT
        _small(doc.add_paragraph(), "See " + ", ".join(item["at"]))
    doc.add_paragraph()


def _measure(step: Any, answers: dict[str, Any]) -> tuple[int, int]:
    """(answered, asked) for one step, without drawing anything."""
    asked = [q for q in step.questions if module_one.visible(q, answers)]
    done = sum(1 for q in asked
               if module_one.describe(q, answers)["state"] != "blank")
    return done, len(asked)


def _still_to_come(doc: Document) -> None:
    """The parts of the framework this document does not cover yet.

    Named rather than omitted, for the same reason gaps are printed: a reader
    who was not in the room has to be able to tell a finished framework from a
    partial one, and a document that simply stops looks finished.
    """
    if not module_one.PENDING:
        return
    _heading(doc, "Annex C — Sections not written yet", level=1)
    _small(doc.add_paragraph(),
           "These sections are part of the framework and are not written yet. "
           "They are listed so this document can be read for what it is.",
           GREY, italic=True)
    for number, title, writes in module_one.PENDING:
        p = doc.add_paragraph(style="List Bullet")
        _small(p, f"{number} — {title}. Writes: {writes}.", INK)
    doc.add_paragraph()


def _record_of_changes(doc: Document, state: dict[str, Any]) -> None:
    """The document-control page, last, as the client's framework has it.

    His carries the header row and a worked example — "Example - 1 | 1.0 |
    1/2/26 | Jane Doe | Section 1, removed email address" — because a blank
    template has to show somebody what to write. This one has the real thing
    instead: every version cut, who cut it, when, and what they said it
    changed. That is the whole content of `versions.py`, and printing it here
    is what turns a version history into a document-control page.

    The example row is kept only when there is nothing else, so the page is
    never a bare header nobody knows how to fill in.
    """
    doc.add_page_break()
    _heading(doc, "Record of Changes", level=1)
    _small(doc.add_paragraph(),
           "Every version of this framework, and what its author said it "
           "changed. Maintained automatically — each row was written when "
           "the version was saved, not afterward.", GREY, italic=True,
           size=NOTE_PT)

    head = ["Change No.", "Version", "Date", "Posted By",
            "Change location and content"]
    rows: list[list[str]] = []
    for i, version in enumerate(state.get("versions") or [], start=1):
        who = str(version.get("created_by") or "").strip() or "unnamed"
        title = str(version.get("created_title") or "").strip()
        when = str(version.get("created_at") or "")[:10]
        note = str(version.get("note") or "").strip()
        adopted = str(version.get("adopted_on") or "").strip()
        if adopted:
            note = (note + " " if note else "") + f"Adopted {adopted}."
        rows.append([
            str(i),
            str(version.get("label") or version.get("number") or i),
            when,
            who + (f", {title}" if title else ""),
            note or "No note recorded.",
        ])

    if not rows:
        rows.append(["Example — 1", "1.0", "", "A named person",
                     "What this version changed, and where."])

    _table(doc, head, rows)
    doc.add_paragraph()


def build(agency: str, *, today: date | None = None) -> bytes:
    """The whole framework, as a .docx, for the agency on this request."""
    today = today or clock.today()
    state = versions.state()
    answers = _answered(state)

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(BODY_PT)
    normal.paragraph_format.space_after = Pt(6)
    _default_font(doc)
    _use_real_headings(doc)
    _update_fields_on_open(doc)

    # His page setup, which is not symmetrical. python-docx defaults to 1.25
    # left and right, which is a letter's measure rather than a policy
    # document's.
    page = doc.sections[0]
    page.left_margin = page.right_margin = Inches(MARGIN_SIDE)
    page.top_margin = Inches(MARGIN_TOP)
    page.bottom_margin = Inches(MARGIN_BOTTOM)

    stamp = state.get("watermark") or ""
    if stamp:
        # Into the header, which is what puts it behind every page rather than
        # once at the top of the first.
        header = doc.sections[0].header
        header.is_linked_to_previous = False
        header.paragraphs[0]._p.addnext(parse_xml(_watermark_xml(stamp)))

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _small(footer, f"{agency} · Artificial Intelligence Governance Framework"
                   f"{' · ' + stamp if stamp else ''}  ·  ", size=9)
    _page_number_footer(footer)

    # Counted the same way the document prints them: only the questions this
    # organisation was asked. A denominator that includes branches they never
    # saw makes a finished framework look two-thirds done.
    counts = [_measure(s, answers) for s in module_one.STEPS]
    given = sum(a for a, _ in counts)
    total = sum(t for _, t in counts)

    # The instrument's own numbering, in one place. The two closing sections
    # used to carry the literals "10." and "11.", which collided with the last
    # generated section as soon as the section list changed length.
    written = prose.sections(answers)
    settled_no = len(written) + 1
    adoption_no = len(written) + 2

    # "How would you like the language to appear: As written or Polished."
    # Polishing rewrites the wording of these clauses and nothing else — see
    # app/polish.py for what it is not allowed to do, and for the checks each
    # rewrite has to pass before it is kept. Unavailable, refused or failed,
    # it returns the assembled text unchanged.
    from app import polish
    tidied = polish.Outcome()
    if module_one.language_of(answers) == module_one.POLISHED:
        tidied = polish.sections(written, answers)

    # Front matter, in his order: cover, contents, a blank leaf, then the
    # instrument. "About this draft" used to sit between the cover and the
    # contents, which pushed section 1 to page six and made the first thing a
    # reader met an explanation of the software. It is real and it stays —
    # moved to the back, in front of the appendix, where a note about how a
    # document was produced belongs.
    _cover(doc, state, agency, answers, today)
    _contents(doc, written,
              [f"{settled_no}. Matters not yet settled",
               f"{adoption_no}. Adoption"])

    # Part one: the framework, as statements somebody can adopt. It ends at
    # the signature, because that is what makes it an instrument — anything
    # after the page somebody signs is annexed to it, not part of it. These
    # three used to sit between the signature and the appendix, which read as
    # three more sections of policy that nobody had signed for.
    _the_framework(doc, answers, written)
    _not_settled(doc, answers, settled_no, written)
    _signature_block(doc, answers, state, adoption_no)

    # Part two: the annexes, the note on how this was produced, then how each
    # statement was arrived at, then the document-control page.
    doc.add_page_break()
    _the_floor(doc, answers)
    _what_disagrees(doc, answers)
    _still_to_come(doc)
    _provenance(doc, state, agency, total, given, today, tidied)
    _the_audit_trail(doc, answers)
    _record_of_changes(doc, state)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def filename(agency_abbrev: str, *, today: date | None = None) -> str:
    """A name that says whose it is, what it is, and that it is a draft.

    Stripped to alphanumerics because this reaches a Content-Disposition and
    then somebody's filesystem — `../../etc/passwd` as an abbreviation must not
    become a path.
    """
    today = today or clock.today()
    stem = "".join(c for c in (agency_abbrev or "")
                   if c.isalnum() or c in "-_")
    draft = "-DRAFT" if versions.watermark() else ""
    # No abbreviation is a real case — an agency the registry does not name.
    # "Framework-AI-Governance-Framework" reads as a bug, so it drops the
    # duplicate rather than repeating the word.
    if not stem:
        return f"AI-Governance-Framework{draft}-{today.isoformat()}.docx"
    return f"{stem}-AI-Governance-Framework{draft}-{today.isoformat()}.docx"
