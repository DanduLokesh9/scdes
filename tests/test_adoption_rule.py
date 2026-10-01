"""Who may record that a framework was adopted — one rule, both ways in.

Before this, recording an adoption was unreachable by construction. The
Framework screen drew the button only for the Council capacity; its endpoint
checked `Target.CONFIG`, which admits the Office of Technology in
configuration mode and the Council in no mode at all. The builder's endpoint
was Council-only, and the launcher signs every registrant in as the Office of
Technology. No person who had signed in could ever adopt anything.

Recording an adoption records being told: the vote or the signature happened
outside the software. So the rule is about who may tell it — the Council
capacity, or a verified, active member of the organization whose framework it
is. These tests pin that, and pin that nobody else gets through.
"""

from __future__ import annotations

from app import authz, module_one, server
from app.authz import Actor, Role, Target


class _Recorder:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, **entry) -> None:
        self.entries.append(entry)


OT = Actor("sean.ot", "Brett", Role.OT, title="Principal",
           email="brett@iiac.ai")
COUNCIL = Actor("council.cto", "Jordan Doe", Role.COUNCIL, title="Director")
READONLY = Actor("sean.ot", "Viewer", Role.OT, readonly=True,
                 email="viewer@iiac.ai")


def _decide(actor, action, verified):
    return authz.guard(actor, Target.FRAMEWORK, action, audit=_Recorder(),
                       verified_member=verified)


# ------------------------------------------------------------------ the rule

def test_the_council_capacity_may_record_either_way() -> None:
    for action in authz.ADOPTION_ACTIONS:
        assert _decide(COUNCIL, action, verified=False).allowed, action


def test_a_verified_member_may_record_either_way() -> None:
    """The person who registered the organization and proved their address
    owns its container. Telling the application it was adopted is theirs."""
    for action in authz.ADOPTION_ACTIONS:
        assert _decide(OT, action, verified=True).allowed, action


def test_an_unverified_request_is_refused_either_way() -> None:
    for action in authz.ADOPTION_ACTIONS:
        decision = _decide(OT, action, verified=False)
        assert not decision.allowed, action
        assert "verified member" in decision.reason


def test_read_only_is_refused_even_when_verified() -> None:
    for action in authz.ADOPTION_ACTIONS:
        assert not _decide(READONLY, action, verified=True).allowed


def test_both_ways_in_share_one_rule() -> None:
    """The contradiction was two rules. There is now one set of actions,
    and both endpoints name an action in it."""
    assert authz.ADOPTION_ACTIONS == {"record_framework_adoption",
                                      "adopt_framework_version"}


def test_the_rule_does_not_depend_on_the_mode() -> None:
    """`Target.CONFIG` flipped with the mode. Adoption must not."""
    from app import mode
    for current in mode.Mode:
        decision = authz._decide(OT, Target.FRAMEWORK,
                                 "record_framework_adoption", None, current,
                                 verified_member=True)
        assert decision.allowed, current


def test_the_audit_entry_says_on_what_basis() -> None:
    log = _Recorder()
    authz.guard(OT, Target.FRAMEWORK, "record_framework_adoption",
                audit=log, verified_member=True)
    detail = log.entries[-1]["detail"]
    assert detail["verified_member"] is True
    assert detail["actor_email"] == "brett@iiac.ai"
    assert log.entries[-1]["outcome"] == "allowed"


def test_a_refusal_is_audited_too() -> None:
    log = _Recorder()
    authz.guard(OT, Target.FRAMEWORK, "adopt_framework_version",
                audit=log, verified_member=False)
    assert log.entries[-1]["outcome"] == "denied"


def test_other_framework_writes_are_still_council_only() -> None:
    """The exception is for recording an adoption and nothing else."""
    decision = _decide(OT, "edit_framework_text", verified=True)
    assert not decision.allowed


# --------------------------------------------------- who counts as verified

def test_nobody_without_a_proven_address_is_a_verified_member() -> None:
    nobody = Actor("sean.ot", "Someone", Role.OT)
    assert server._verified_member(nobody) is False


def test_a_member_of_another_organization_is_not_verified_here(
        monkeypatch) -> None:
    from app import tenancy, tenant
    monkeypatch.setattr(tenancy, "access_for", lambda email: {
        "allowed": True, "state": "tx.env"})
    token = tenant.set_current("pa.env")
    try:
        assert server._verified_member(OT) is False
    finally:
        tenant.reset(token)


def test_an_active_member_of_this_organization_is_verified(
        monkeypatch) -> None:
    from app import tenancy, tenant
    monkeypatch.setattr(tenancy, "access_for", lambda email: {
        "allowed": True, "state": "pa.env"})
    token = tenant.set_current("pa.env")
    try:
        assert server._verified_member(OT) is True
    finally:
        tenant.reset(token)


def test_a_member_of_a_container_not_yet_approved_is_not_verified(
        monkeypatch) -> None:
    from app import tenancy, tenant
    monkeypatch.setattr(tenancy, "access_for", lambda email: {
        "allowed": False, "state": "pa.env"})
    token = tenant.set_current("pa.env")
    try:
        assert server._verified_member(OT) is False
    finally:
        tenant.reset(token)


def test_an_anonymous_request_is_never_verified(monkeypatch) -> None:
    from app import tenancy, tenant
    monkeypatch.setattr(tenancy, "access_for", lambda email: {
        "allowed": True, "state": tenant.ANONYMOUS})
    token = tenant.set_current(tenant.ANONYMOUS)
    try:
        assert server._verified_member(OT) is False
    finally:
        tenant.reset(token)


# ------------------------------------------------ the completeness gate

def test_optional_questions_do_not_hold_up_adoption() -> None:
    """A framework with every decision made could not be adopted until
    somebody answered an optional question."""
    optional = [q for s in module_one.STEPS for q in s.questions
                if getattr(q, "optional", False)]
    assert optional, "no optional questions to test against"
    _, total = module_one.policy_progress({})
    everything = sum(1 for s in module_one.STEPS for q in s.questions
                     if module_one.visible(q, {}))
    assert total < everything


def test_how_the_document_reads_does_not_hold_up_adoption() -> None:
    """Whether the language is formal is a download preference, not a
    decision in the framework."""
    for key in module_one.DOCUMENT_PREFERENCES:
        assert module_one.by_key(key) is not None, key
    answered_before, total = module_one.policy_progress({})
    answers = {k: "formal" for k in module_one.DOCUMENT_PREFERENCES}
    answered_after, total_after = module_one.policy_progress(answers)
    assert (answered_after, total_after) == (answered_before, total)


def test_only_the_gaius_team_in_the_test_container_may_skip_the_gate(
        monkeypatch) -> None:
    """The client's rule — adoption after completion — holds for every real
    organization. The exception is for showing the adopted state in IIA's
    own DEMO."""
    from app import admin, tenancy, tenant
    monkeypatch.setattr(admin, "is_admin",
                        lambda email: email == "brett@iiac.ai")
    for container, who, expected in (
            ("iia.test", OT, True),
            ("iia.test", Actor("sean.ot", "X", Role.OT,
                               email="someone@iiac.ai"), False),
            ("pa.env", OT, False),
            ("nm.env", OT, False)):
        token = tenant.set_current(container)
        try:
            assert server._may_record_incomplete(who) is expected, \
                (container, who.email)
        finally:
            tenant.reset(token)
    assert tenancy.is_shared_test_container("iia.test")
