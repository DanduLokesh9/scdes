"""Search never reaches another organization's documents.

Reported (BUG-C1496D1E): signed in as the DEMO agency, a search for "Center of
Excellence" — written nowhere in that account — returned passages from
SCDES's documents. The search index is built from the reference agency's
corpus and was searched for everybody. Now only that agency searches it;
everyone else searches what they uploaded themselves.
"""

from __future__ import annotations

import json

import pytest

from app import agent, intake, server, tenant
from app.authz import Actor, Role

LEAKS = ("SCDES", "Environmental Services", "Appendix", "Operations Manual",
         "des.sc.gov", "Gate Review")


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    held = tenant.set_current("iia.test")
    yield tmp_path
    tenant.reset(held)


def _upload(paragraphs):
    store = intake._store()
    store.mkdir(parents=True, exist_ok=True)
    (store / intake.INDEX.name).write_text(json.dumps({"documents": [
        {"file": "our-policy.docx", "kind": "policy", "paragraphs": paragraphs}]}),
        encoding="utf-8")


def _said(result) -> str:
    return json.dumps(result if isinstance(result, dict) else result.as_dict())


def test_the_reported_search_returns_nothing_of_scdes(demo):
    assert not tenant.owns_corpus()
    out = agent.chat("Center of Excellence")
    assert out.citations == [] and out.in_scope is False
    assert "Nothing in your organization's own documents matches" in out.answer
    for leak in LEAKS:
        assert leak not in _said(out), leak


def test_a_search_finds_the_organizations_own_documents(demo):
    _upload(["Our AI Center of Excellence reviews every new tool before purchase.",
             "Unrelated paragraph about parking permits and office hours."])
    out = agent.chat("Center of Excellence")
    assert len(out.citations) == 1
    assert out.citations[0]["citation"] == "our-policy.docx · paragraph 1"
    assert "Center of Excellence reviews" in out.citations[0]["snippet"]
    assert out.provider == "local"


def test_what_ifs_and_project_drafts_are_not_run_on_the_reference_corpus(demo):
    for message in ("what if Data Sensitivity moved to 2.0?",
                    "we need help with our permit backlog"):
        out = agent.chat(message)
        assert out.citations == [] and out.scenario is None and out.draft_project is None
        for leak in LEAKS:
            assert leak not in _said(out), (message, leak)


def test_the_search_endpoint_is_scoped_the_same_way(demo):
    actor = Actor("u", "Someone", Role.OPERATOR, email="dev@iiac.ai")
    out = server.api_search(actor, {}, {"q": ["gate review risk category appendix"]})
    assert out["hits"] == []
    for leak in LEAKS:
        assert leak not in _said(out), leak


def test_a_browser_nobody_can_identify_gets_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    held = tenant.set_current(tenant.ANONYMOUS)
    try:
        out = agent.chat("gate review risk category")
        assert out.citations == []
    finally:
        tenant.reset(held)


def test_the_reference_agency_still_searches_its_corpus():
    held = tenant.set_current("")          # the CLI and the corpus owner
    try:
        hits = server.api_search(Actor("u", "S", Role.OPERATOR), {}, {"q": ["gate review"]})["hits"]
        assert hits and hits[0]["source"] != "your document"
    finally:
        tenant.reset(held)
