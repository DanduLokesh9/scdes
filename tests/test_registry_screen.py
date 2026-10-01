"""The Registry screen: the catalog, searched in hierarchy order.

The catalog record is pinned in test_catalog.py. These pin what the screen
needed on top: editing by any hat, the bands in the spine's order with
nothing ranked inside them, the finding that reads Vendors, the seeding that
is an offer rather than a write on opening, and the rule that cost lives on
Vendors and is only shown here.
"""

from __future__ import annotations

import pytest

from app import catalog, server
from app.authz import Actor, Role

USER = Actor("u", "Pat Lee", Role.OPERATOR, title="Clerk")

ANSWERS = {"org.size": "100-500", "org.functions": {"it": "dedicated"},
           "proc.cooperative": "sometimes", "proc.reuse": "yes",
           "have.software": ["gis", "transcription"],
           "data.never": ["personal"]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "_file", lambda: tmp_path / "c.json")
    monkeypatch.setattr(catalog, "_record", lambda *a, **k: None)
    monkeypatch.setattr(server, "_framework_answers", lambda: dict(ANSWERS))
    yield


def _add(**body):
    body.setdefault("name", "Summarizer")
    return server.api_catalog_save(USER, body, {})


def test_only_the_name_is_required_and_any_hat_may_add() -> None:
    assert not _add(name=" ")["ok"]
    assert _add()["ok"]


def test_editing_keeps_what_it_was_given_and_drops_the_rest() -> None:
    ref = _add()["tool"]["ref"]
    out = server.api_catalog_save(USER, {
        "ref": ref, "does": "Summarizes permit files",
        "standing": "Available to us on an agreement",
        "availability": ["cooperative", "invented"], "score": 5,
        "held_by": [{"unit": "Planning", "used_for": "permit summaries"},
                    {"unit": "planning", "used_for": "dupe"}]}, {})
    tool = out["tool"]
    assert tool["availability"] == ["cooperative"]
    assert [h["unit"] for h in tool["held_by"]] == ["Planning"]
    assert "score" not in tool


def test_the_bands_come_back_in_the_hierarchy_order() -> None:
    mine = _add(name="Mine")["tool"]["ref"]
    catalog.update(mine, USER, held_by=[{"unit": "Planning"}])
    theirs = _add(name="Theirs")["tool"]["ref"]
    catalog.update(theirs, USER, held_by=[{"unit": "Water"}])
    coop = _add(name="Coop")["tool"]["ref"]
    catalog.update(coop, USER, availability=["cooperative"])
    _add(name="Buy")
    found = catalog.surface(answers=ANSWERS, unit="Planning")
    assert [b["band"] for b in found["bands"]] == list(catalog.BANDS)
    assert [b["step"] for b in found["bands"]] == [2, 3, 4, 6]
    assert [len(b["tools"]) for b in found["bands"]] == [1, 1, 1, 1]


def test_nothing_in_a_band_is_ranked_or_scored() -> None:
    _add(name="One")
    blob = str(catalog.surface(answers=ANSWERS)).lower()
    for word in ("score", "rating", "recommended", "stars"):
        assert word not in blob, word


def test_a_small_organisation_sees_no_cross_unit_band() -> None:
    small = {**ANSWERS, "org.size": "u25"}
    found = catalog.surface(answers=small)
    assert catalog.BAND_ANOTHER_UNIT not in [b["band"] for b in found["bands"]]
    assert "held_by_more_than_one" not in found["counters"]


def test_built_here_is_offered_only_where_something_could_be_built() -> None:
    assert catalog.framework_inputs(ANSWERS)["can_build"] is True
    none = {**ANSWERS, "org.functions": {"it": "none"}}
    assert catalog.framework_inputs(none)["can_build"] is False


def test_a_paid_tool_with_ai_and_no_catalog_entry_is_named() -> None:
    vendors = [{"id": "VN-1", "name": "Northbridge", "product": "CaseNote",
                "status": "in_use", "involvement": "core"}]
    said = [f["says"] for f in catalog.surface(answers=ANSWERS,
                                               vendors_rows=vendors)["raised"]
            if f["id"] == "finding.rg.paid_not_listed"]
    assert said == ["CaseNote is on your Vendors list as in use with AI in "
                    "it. Nothing here says what job it does."]
    _add(name="CaseNote", vendor="VN-1")
    assert not any(f["id"] == "finding.rg.paid_not_listed" for f in
                   catalog.surface(answers=ANSWERS,
                                   vendors_rows=vendors)["raised"])


def test_cost_is_shown_from_vendors_and_never_stored_here() -> None:
    ref = _add(name="CaseNote", vendor="VN-1")["tool"]["ref"]
    vendors = [{"id": "VN-1", "name": "Northbridge", "amount": 41500.0,
                "basis_label": "a year"}]
    row = next(t for t in catalog.surface(answers=ANSWERS,
                                          vendors_rows=vendors)["tools"]
               if t["ref"] == ref)
    assert row["vendor_money"] == "$41,500 a year"
    assert "amount" not in catalog.one(ref)


def test_seeding_is_an_offer_and_writes_only_when_accepted() -> None:
    found = catalog.surface(answers=ANSWERS)
    assert found["seed_offer"] == ["Mapping or GIS",
                                   "Meeting transcription or notes"]
    assert catalog.all_tools() == []
    server.api_catalog_seed(USER, {}, {})
    assert len(catalog.all_tools()) == 2
    assert catalog.surface(answers=ANSWERS)["seed_offer"] == []


def test_a_holding_they_said_never_goes_into_a_tool_is_echoed() -> None:
    ref = _add(name="Chat", needs_holdings=["H1"])["tool"]["ref"]
    row = next(t for t in catalog.surface(
        answers=ANSWERS, holdings=[{"id": "H1", "name": "Permit files",
                                    "sensitive": ["personal"]}])["tools"]
        if t["ref"] == ref)
    assert row["never_hits"] and "you said never" in row["never_hits"][0]


def test_the_routes_are_registered() -> None:
    assert ("GET", "/api/catalog") in server.ROUTES
    assert ("POST", "/api/catalog") in server.ROUTES
    assert ("POST", "/api/catalog/seed") in server.ROUTES
