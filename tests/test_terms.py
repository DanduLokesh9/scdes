"""The Terms of Use and License Agreement at registration (Brett, Oct 2026).

Accept is refused unless the text was scrolled, the authority box ticked and
the acceptor identified; the record keeps the exact version; no code is sent
before acceptance; the signed-form route pauses registration until the GAIUS
team marks the executed copy received; and a signed-in person who has not
accepted cannot change anything.
"""

from __future__ import annotations

import html
import json
import re

import pytest

from app import server, tenancy, terms
from app.authz import Actor, Role

FORM = dict(email="jane.smith@des.sc.gov", name="Jane Smith", title="Director",
            unit="South Carolina Department of Environmental Services",
            agency="sc.des", authority=True, scrolled=True)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(terms, "STORE", tmp_path / "terms.json")
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    from app import mailer
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, html=None:
                        sent.append((to, subject, text)) or {"sent": True})
    monkeypatch.setattr(mailer, "send_code", lambda *a, **k: {"sent": False, "reason": "test"})
    monkeypatch.setattr(mailer, "may_show_code_to", lambda address: True)
    monkeypatch.setattr(mailer, "note_for", lambda d: "test")

    class Now:
        def __init__(self, target, name, daemon):
            self.target = target

        def start(self):
            self.target()
    monkeypatch.setattr(terms.threading, "Thread", Now)
    yield sent


# ----------------------------------------------------------- the document

def test_the_agreement_is_word_for_word_the_click_through_docx():
    import docx
    d = docx.Document(str(terms.LEGAL / "GoverningAI_Terms_of_Use_and_License_v1.0.docx"))
    want = " ".join(p.text for p in d.paragraphs if p.text.strip())
    shown = re.sub(r"</(p|li|h3|ol)>", " ", terms.TEXT.read_text(encoding="utf-8"))
    shown = html.unescape(re.sub(r"<[^>]+>", "", shown))
    norm = lambda s: re.sub(r"\s+", " ", s).strip()                  # noqa: E731
    assert norm(want) == norm(shown)


def test_the_document_carries_its_fingerprint_and_both_forms():
    doc = terms.document()
    assert doc["available"] and len(doc["sha256"]) == 64 and doc["version"] == "v1.0"
    for url in (doc["download_url"], doc["signed_form_url"]):
        assert (terms.ROOT / "app" / "web" / url.lstrip("/")).is_file(), url


# ----------------------------------------------------------- accepting

@pytest.mark.parametrize("missing", ["name", "title", "unit"])
def test_every_field_is_required(missing):
    assert terms.accept(**{**FORM, missing: ""})["ok"] is False


def test_the_authority_box_and_the_scroll_are_required():
    assert "authorized" in terms.accept(**{**FORM, "authority": False})["error"]
    assert "end" in terms.accept(**{**FORM, "scrolled": False})["error"]


def test_a_stale_page_is_told_to_reload():
    out = terms.accept(**FORM, sha256="0" * 64)
    assert out["ok"] is False and out["stale"]


def test_the_acceptance_record_is_kept_with_the_version():
    out = terms.accept(**FORM, user_agent="Edge")
    assert out["ok"]
    held = json.loads(terms.STORE.read_text())["people"]["jane.smith@des.sc.gov"]
    assert held["sha256"] == terms.document()["sha256"]
    assert held["accepted_by"] == {"name": "Jane Smith", "title": "Director",
                                   "email": "jane.smith@des.sc.gov"}
    assert held["authority_affirmed"] and held["scrolled_to_end"]
    assert held["method"] == "click-wrap" and held["version"] == "v1.0"
    assert terms.status("jane.smith@des.sc.gov")["accepted"]


def test_a_changed_agreement_is_asked_again(monkeypatch):
    terms.accept(**FORM)
    monkeypatch.setattr(terms, "document", lambda: {"available": True, "sha256": "new"})
    assert terms.status("jane.smith@des.sc.gov")["accepted"] is False


# ----------------------------------------------------------- the code waits for it

def test_no_code_before_the_terms_are_accepted():
    body = {"agency": "sc.des", "name": "Jane Smith", "title": "Director",
            "email": "jane.smith@des.sc.gov", "attested": True}
    out = server.api_register_agency(None, body, {})
    assert out["ok"] is False and out["needs_terms"] and "code" not in out
    assert terms.accept(**FORM)["ok"]
    out = server.api_register_agency(None, body, {})
    assert out["ok"], out
    assert "code" in out


def test_the_phone_is_optional_but_checked_when_given():
    terms.accept(**FORM)
    base = {"agency": "sc.des", "name": "Jane Smith", "title": "Director",
            "email": "jane.smith@des.sc.gov", "attested": True}
    assert server.api_register_agency(None, {**base, "phone": "123"}, {})["ok"] is False
    assert server.api_register_agency(None, base, {})["ok"]


def test_verifying_confirms_the_acceptance():
    terms.accept(**FORM)
    reg = server.api_register_agency(None, {"agency": "sc.des", "name": "Jane Smith",
        "title": "Director", "email": "jane.smith@des.sc.gov", "attested": True}, {})
    server.api_verify_agency(None, {"email": "jane.smith@des.sc.gov", "code": reg["code"]}, {})
    held = json.loads(terms.STORE.read_text())["people"]["jane.smith@des.sc.gov"]
    assert held["status"] == terms.CONFIRMED


# ----------------------------------------------------------- the signed route

def test_the_signed_form_is_emailed_and_registration_waits(isolated):
    out = server.api_terms_signed(None, {**FORM}, {})
    assert out["ok"] and out["awaiting_signed"]
    recipients = sorted(t for t, _, _ in isolated)
    assert recipients == ["brett@iiac.ai", "jane.smith@des.sc.gov"]
    assert "SIGNED_FORM" in isolated[0][2]
    reg = server.api_register_agency(None, {"agency": "sc.des", "name": "Jane Smith",
        "title": "Director", "email": "jane.smith@des.sc.gov", "attested": True}, {})
    assert reg["ok"] is False and reg["awaiting_signed"]


def test_only_the_team_marks_it_received_and_then_the_code_goes():
    server.api_terms_signed(None, {**FORM}, {})
    stranger = Actor("u", "S", Role.OPERATOR, email="jane.smith@des.sc.gov")
    assert server.api_admin_terms_received(stranger, {"email": FORM["email"]}, {})["ok"] is False
    team = Actor("u", "S", Role.OPERATOR, email="lokesh@iiac.ai")
    out = server.api_admin_terms_received(team, {"email": FORM["email"]}, {})
    assert out["ok"], out
    assert terms.status(FORM["email"])["accepted"]
    assert terms.awaiting_signed() == []


def test_the_organizations_screen_lists_who_is_waiting():
    server.api_terms_signed(None, {**FORM}, {})
    team = Actor("u", "S", Role.OPERATOR, email="dev@iiac.ai")
    out = server.api_admin_organizations(team, {}, {})
    assert out["awaiting_signed"][0]["unit"] == FORM["unit"]


# ----------------------------------------------------------- the write gate

def test_a_signed_in_person_without_the_terms_cannot_change_anything():
    who = Actor("u", "S", Role.OPERATOR, email="jane.smith@des.sc.gov")
    refused = server._terms_gate("POST", "/api/versions/answer", who, None)
    assert refused and refused["needs_terms"]
    for open_door in ("/api/terms/accept", "/api/agency/verify", "/api/session/end",
                      "/api/bugs/report"):
        assert server._terms_gate("POST", open_door, who, None) is None
    assert server._terms_gate("GET", "/api/framework", who, None) is None
    terms.accept(**FORM)
    assert server._terms_gate("POST", "/api/versions/answer", who, None) is None


def test_the_team_and_a_view_as_session_are_not_gated():
    team = Actor("u", "S", Role.OPERATOR, email="brett@iiac.ai")
    assert server._terms_gate("POST", "/api/versions/answer", team, None) is None
    jane = Actor("u", "S", Role.OPERATOR, email="jane.smith@des.sc.gov")
    assert server._terms_gate("POST", "/api/versions/answer", jane, {"email": "x"}) is None
