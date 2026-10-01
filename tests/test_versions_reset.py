"""Versions, adoption, and starting over.

Three client rulings are under test here:

  · a version increments when someone deliberately saves one, not on every edit;
  · draft becomes adopted through an act performed in the platform, against a
    specific version number, by whoever holds the authority;
  · "start over" wipes the agency's configuration and the audit log survives.

That last one gets the most attention it deserves. A log the audited party can
clear is not a log, and the reset is the one operation in this application whose
job is deletion — so the guarantee is asserted rather than believed.
"""

from __future__ import annotations

import json

import pytest

from app import decider, reset as reset_mod, versions
from app.authz import Actor, Role

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")
OPERATOR = Actor("liz.operator", "Operator", Role.OPERATOR, title="Analyst")
COUNCIL = Actor("council.cto", "Council member", Role.COUNCIL, title="Chair")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Redirect every file these tests can write.

    `versions.adopt()` writes two files, not one: the version record, and
    `framework.ADOPTION_FILE`, which it keeps in step so the Framework screen
    cannot disagree with the version history. Patching only the first left the
    second pointing at the real corpus, so running the suite recorded a genuine
    adoption for SCDES — signed "Council member, Chair, Minute 2026-14".

    That reached staging. `setup_server.sh` runs pytest as a deploy check, so
    the deployment tested itself into claiming its framework was adopted, which
    takes the DRAFT stamp off every exported document. A test that writes
    outside tmp_path is not merely untidy here; it is a test that can forge a
    governance record.
    """
    from app import framework
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "versions.json")
    monkeypatch.setattr(decider, "DECIDER_FILE", tmp_path / "decider.json")
    monkeypatch.setattr(framework, "ADOPTION_FILE", tmp_path / "adoption.json")
    decider.invalidate()
    yield
    decider.invalidate()


# --------------------------------------------------------- deliberate versions

def test_answering_questions_does_not_move_the_version_number() -> None:
    """"Otherwise they'll be on v47 by lunchtime.\""""
    for i in range(12):
        versions.answer(f"q.{i}", f"answer {i}", OT)
    assert versions.current() is None, "no version exists until one is saved"
    assert versions.unsaved_changes() == 12


def test_saving_cuts_exactly_one_version() -> None:
    versions.answer("agency.identity", "Anderson County", OT)
    result = versions.save_version(OT, note="First pass with the leadership team")
    assert result["ok"]
    assert result["version"]["number"] == 1
    assert result["version"]["label"] == "DRAFT VERSION 1"
    assert versions.unsaved_changes() == 0


def test_saving_an_unchanged_document_is_refused() -> None:
    versions.answer("agency.identity", "Anderson County", OT)
    versions.save_version(OT)
    again = versions.save_version(OT)
    assert not again["ok"]
    assert "nothing has changed" in again["error"].lower()


def test_the_number_advances_only_when_something_changed() -> None:
    versions.answer("a", "one", OT)
    versions.save_version(OT)
    versions.answer("b", "two", OT)
    second = versions.save_version(OT)
    assert second["version"]["number"] == 2


def test_a_saved_version_is_frozen() -> None:
    """What you exported as DRAFT VERSION 1 is what version 1 will always hold."""
    versions.answer("scope.units", "All departments", OT)
    versions.save_version(OT)
    versions.answer("scope.units", "Only the technology office", OT)
    versions.save_version(OT)

    v1 = next(v for v in versions.history() if v["number"] == 1)
    assert v1["answers"]["scope.units"] == "All departments"


def test_a_version_records_who_cut_it() -> None:
    versions.answer("a", "one", OT)
    v = versions.save_version(OT, note="Reviewed with Legal")["version"]
    assert v["created_by"] == "Office of Technology"
    assert v["created_title"] == "CTO"
    assert v["note"] == "Reviewed with Legal"
    assert v["digest"], "a version needs a fingerprint to be checkable"


def test_nothing_answered_means_nothing_to_save() -> None:
    assert not versions.save_version(OT)["ok"]


# ------------------------------------------------------------- risk acceptance

def test_an_answer_that_gives_something_up_records_what_and_who() -> None:
    versions.answer(
        "definitions.autonomous", "Some decisions may be made by the system alone",
        OT, accepted_risk={"warning": "Human accountability claims stop being true.",
                           "abrogates": ["The human-in-authority principle"]})
    state = versions.state()
    assert len(state["acceptances"]) == 1
    accepted = state["acceptances"][0]
    assert accepted["accepted_by"] == "Office of Technology"
    assert accepted["gave_up"] == ["The human-in-authority principle"]


def test_going_back_to_the_safe_answer_withdraws_the_acceptance() -> None:
    """A stale "we accept this risk" attached to a document that no longer takes
    it is a false record."""
    versions.answer("definitions.autonomous", "system alone", OT,
                    accepted_risk={"warning": "w", "abrogates": ["x"]})
    versions.answer("definitions.autonomous", "a person reviews every decision", OT)
    assert versions.state()["acceptances"] == []


def test_acceptances_travel_with_the_version() -> None:
    versions.answer("definitions.autonomous", "system alone", OT,
                    accepted_risk={"warning": "w", "abrogates": ["x"]})
    v = versions.save_version(OT)["version"]
    assert len(v["acceptances"]) == 1, (
        "a version that dropped human review is a different document and has to "
        "carry that with it")


# ------------------------------------------------------------------- adoption

def test_a_draft_is_watermarked_and_an_adopted_version_is_not() -> None:
    decider.answer(decider.GROUP, OT, noun="Council", quorum=3)
    versions.answer("a", "one", OT)
    versions.save_version(OT)
    assert versions.watermark() == "DRAFT"
    assert versions.export_label() == "DRAFT VERSION 1"

    result = versions.adopt(1, COUNCIL, adopted_on="2026-08-20")
    assert result["ok"], result.get("error")
    assert versions.watermark() == ""
    assert "adopted 2026-08-20" in versions.export_label()


def test_answering_again_after_adoption_puts_the_draft_stamp_back() -> None:
    """An adopted document that someone has since edited is not adopted."""
    versions.answer("a", "one", OT)
    versions.save_version(OT)
    versions.adopt(1, COUNCIL)
    assert versions.watermark() == ""

    versions.answer("b", "two", OT)
    assert versions.watermark() == "DRAFT"
    label = versions.export_label()
    assert label.startswith("DRAFT"), label
    assert "adopted" not in label, "an edited document must not claim adoption"


def test_only_the_decider_may_adopt() -> None:
    """Recording an adoption is the act the DRAFT label exists to withhold."""
    versions.answer("a", "one", OT)
    versions.save_version(OT)

    refused = versions.adopt(1, OT)
    assert not refused["ok"]
    assert versions.watermark() == "DRAFT", "the refusal must not have applied"

    assert versions.adopt(1, COUNCIL)["ok"]


def test_adopting_a_version_that_does_not_exist_is_refused() -> None:
    assert not versions.adopt(9, COUNCIL)["ok"]


def test_a_version_cannot_be_adopted_twice() -> None:
    versions.answer("a", "one", OT)
    versions.save_version(OT)
    versions.adopt(1, COUNCIL, adopted_on="2026-08-01")
    again = versions.adopt(1, COUNCIL)
    assert not again["ok"]
    assert "already adopted" in again["error"].lower()


def test_the_adoption_names_a_person_and_a_date() -> None:
    versions.answer("a", "one", OT)
    versions.save_version(OT)
    v = versions.adopt(1, COUNCIL, adopted_on="2026-08-20",
                       note="Minute 2026-14")["version"]
    assert v["adopted_by"] == "Council member"
    assert v["adopted_title"] == "Chair"
    assert v["adopted_on"] == "2026-08-20"
    assert v["adoption_note"] == "Minute 2026-14"


def test_the_watermark_claim_is_honest() -> None:
    """The client asked for "non-removable". It cannot honestly be called that,
    and the platform says so rather than overstating what a watermark does."""
    note = versions.state()["watermark_note"].lower()
    assert "not tamper-proof" in note or "tamper-proof" in note
    assert "stripped" in note


# --------------------------------------------------------------- starting over

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A whole corpus tree, so a real reset can run against real files."""
    corpus = tmp_path / "corpus"
    (corpus / "config").mkdir(parents=True)
    (corpus / "audit").mkdir(parents=True)
    (corpus / "framework").mkdir(parents=True)
    (corpus / "registry" / "AI-001").mkdir(parents=True)
    (tmp_path / "council").mkdir()
    (tmp_path / "data").mkdir()

    (corpus / "config" / "framework_versions.json").write_text('{"versions":[]}')
    (corpus / "config" / "decider.json").write_text('{"shape":"group"}')
    (corpus / "config" / "vocabulary.yaml").write_text("concepts: {}")
    (corpus / "registry" / "AI-001" / "Appendix_G.xlsx").write_text("x")
    (corpus / "framework" / "Framework.docx").write_text("the reference set")
    (corpus / "audit" / "log.jsonl").write_text(
        '{"seq":1}\n{"seq":2}\n{"seq":3}\n')
    (tmp_path / "council" / "decision_log.jsonl").write_text('{"d":1}\n')
    (tmp_path / "data" / "tenancy.json").write_text('{"agencies":{}}')

    monkeypatch.setattr(reset_mod, "CORPUS", corpus)
    monkeypatch.setattr(reset_mod, "ROOT", tmp_path)
    monkeypatch.setattr(reset_mod, "PROTECTED", (
        corpus / "audit", corpus / "framework", tmp_path / "data" / "tenancy.json"))
    return tmp_path


def test_a_reset_needs_the_phrase_typed(sandbox) -> None:
    """A button that has been clicked once is easy to click twice."""
    assert not reset_mod.reset(OT, confirm_phrase="")["ok"]
    assert not reset_mod.reset(OT, confirm_phrase="yes")["ok"]


def test_a_reset_clears_the_agencys_own_work(sandbox) -> None:
    result = reset_mod.reset(OT, confirm_phrase="START OVER",
                             reason="Trialled it alone, now doing it properly")
    assert result["ok"], result.get("error")
    assert not (sandbox / "corpus" / "config" / "framework_versions.json").exists()
    assert not (sandbox / "corpus" / "config" / "decider.json").exists()
    assert not (sandbox / "corpus" / "config" / "vocabulary.yaml").exists()
    assert not list((sandbox / "corpus" / "registry").iterdir())
    assert not list((sandbox / "council").iterdir())


def test_the_audit_log_survives_a_reset(sandbox) -> None:
    """"Log should survive absolutely." The one guarantee that cannot bend."""
    log = sandbox / "corpus" / "audit" / "log.jsonl"
    before = log.read_text(encoding="utf-8")
    reset_mod.reset(OT, confirm_phrase="START OVER")
    assert log.exists(), "the audit log was deleted by a reset"
    assert log.read_text(encoding="utf-8").startswith(before), (
        "existing entries must survive intact, not be rewritten")


def test_the_reset_is_itself_in_the_log(sandbox) -> None:
    """A previous attempt existing is a fact, and this is what records it."""
    from app.audit import JsonlAuditLog
    log = JsonlAuditLog(sandbox / "corpus" / "audit" / "reset_test.jsonl")
    import app.authz as authz
    authz._default_log = log
    try:
        reset_mod.reset(OT, confirm_phrase="START OVER", reason="fresh start")
        actions = [e.action for e in log.entries()]
        assert "reset_agency_configuration" in actions
        entry = next(e for e in log.entries()
                     if e.action == "reset_agency_configuration")
        assert entry.detail["why"] == "fresh start"
        assert entry.detail["cleared"]
    finally:
        authz._default_log = None


def test_the_registration_and_reference_documents_survive(sandbox) -> None:
    """They asked to start the work again, not to lose their account."""
    reset_mod.reset(OT, confirm_phrase="START OVER")
    assert (sandbox / "data" / "tenancy.json").exists()
    assert (sandbox / "corpus" / "framework" / "Framework.docx").exists()


def test_an_operator_cannot_wipe_the_agency(sandbox) -> None:
    result = reset_mod.reset(OPERATOR, confirm_phrase="START OVER")
    assert not result["ok"]
    assert (sandbox / "corpus" / "config" / "decider.json").exists()


def test_the_preview_lists_what_goes_and_what_stays(sandbox) -> None:
    """"Are you sure?" is not informed consent."""
    plan = reset_mod.preview()
    assert plan["audit_entries"] == 3
    labels = " ".join(c["label"] for c in plan["clears"]).lower()
    assert "version" in labels and "registry" in labels
    keeps = " ".join(k["label"] for k in plan["keeps"]).lower()
    assert "audit" in keeps and "registration" in keeps


def test_the_protected_paths_are_never_in_the_clear_list() -> None:
    """The list is explicit rather than a glob, and this is what keeps it so."""
    for target in reset_mod._targets():
        for guarded in reset_mod.PROTECTED:
            assert target.path != guarded
            assert guarded not in target.path.parents, (
                f"{target.label} would take {guarded} with it")


# ------------------------------------------------------------------ the guard

def test_adopting_writes_only_inside_the_test_directory(tmp_path) -> None:
    """The regression that reached staging, asserted directly.

    Both files adopt() touches must be the redirected ones. Checking the outcome
    is not enough — this checks that the real corpus was not what got written.
    """
    from app import framework
    versions.answer("a", "one", OT)
    versions.save_version(OT)
    versions.adopt(1, COUNCIL)

    assert versions.VERSIONS_FILE.parent == tmp_path
    assert framework.ADOPTION_FILE.parent == tmp_path
    assert framework.ADOPTION_FILE.exists(), (
        "adopt() should have written the adoption record here, not elsewhere")
