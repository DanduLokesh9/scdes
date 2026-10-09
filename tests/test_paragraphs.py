"""How the framework's sentences are gathered into paragraphs.

The document used to print one numbered sentence per line after its first two
sections. `prose.paragraphs` is what replaced that, and these pin its rules:
the parts of one obligation stay together, single-sentence answers are run
together up to a ceiling, and nothing is ever reordered — a reader checking
the document against their own answers finds them in the order given.
"""

from __future__ import annotations

from app import prose
from app.prose import Clause, Section


def _section(*sources: str) -> Section:
    return Section("6", "Operating principles",
                   clauses=[Clause(f"Sentence from {s}.", s) for s in sources])


def _shape(section: Section) -> list[list[str]]:
    return [[c.source for c in group] for group in prose.paragraphs(section)]


def test_the_parts_of_one_obligation_share_a_paragraph() -> None:
    """6.2a to 6.2d are four parts of the register obligation."""
    shape = _shape(_section("6.2a", "6.2b", "6.2c", "6.2d"))
    assert shape == [["6.2a", "6.2b", "6.2c", "6.2d"]]


def test_two_obligations_are_two_paragraphs() -> None:
    shape = _shape(_section("6.1a", "6.1b", "6.2a", "6.2b"))
    assert shape == [["6.1a", "6.1b"], ["6.2a", "6.2b"]]


def test_single_sentences_are_run_together_up_to_the_ceiling() -> None:
    shape = _shape(_section("4.1", "4.2", "4.3", "4.4", "4.5", "4.6"))
    assert shape == [["4.1", "4.2", "4.3"], ["4.4", "4.5", "4.6"]]


def test_a_lone_last_sentence_joins_the_paragraph_before_it() -> None:
    """Standing alone it reads as an afterthought."""
    shape = _shape(_section("4.1", "4.2", "4.3", "4.4"))
    assert shape == [["4.1", "4.2", "4.3", "4.4"]]


def test_a_lone_sentence_is_not_attached_to_a_different_obligation() -> None:
    """Joining it to 6.8's paragraph would say something the organization
    did not."""
    shape = _shape(_section("6.8a", "6.8b", "6.9"))
    assert shape == [["6.8a", "6.8b"], ["6.9"]]


def test_a_long_run_breaks_on_length_as_well_as_count() -> None:
    long = "x" * (prose.PARAGRAPH_CHARS + 10)
    section = Section("2", "Scope", clauses=[Clause(long, "3.1"),
                                              Clause("Short.", "3.2")])
    assert [[c.source for c in g] for g in prose.paragraphs(section)] \
        in ([["3.1"], ["3.2"]], [["3.1", "3.2"]])
    first = prose.paragraphs(section)[0]
    assert first[0].source == "3.1"


def test_the_order_is_never_changed() -> None:
    sources = ("6.1b", "6.1a", "6.2a", "6.3a", "6.3b", "6.6", "6.7",
               "6.8a", "6.8b", "6.9")
    flat = [c for group in prose.paragraphs(_section(*sources))
            for c in group]
    assert tuple(c.source for c in flat) == sources


def test_nothing_is_dropped_or_duplicated() -> None:
    sources = ("3.1", "3.2", "3.3", "3.4", "1.5", "1.6", "1.7")
    flat = [c.source for group in prose.paragraphs(_section(*sources))
            for c in group]
    assert sorted(flat) == sorted(sources)


def test_every_section_flows() -> None:
    for spec in prose.SECTIONS:
        assert spec["number"] in prose.FLOWING, spec["title"]


def test_an_empty_section_has_no_paragraphs() -> None:
    assert prose.paragraphs(Section("8", "Procurement")) == []
