"""Critic suite: actively try to break each governance invariant.

Acceptance criterion 1 is not "the rules are written down" — it is that an
attacker cannot get around them. Every test here attempts a breach and asserts
both that it was refused *and* that the refusal was recorded.
"""

from __future__ import annotations

import json

import pytest

from app import mode as mode_mod
from app.audit import JsonlAuditLog
from app.authz import (CHAT_ACTOR, Actor, Decision, Denied, Role, Target,
                       guard, require)


@pytest.fixture
def log(tmp_path):
    return JsonlAuditLog(tmp_path / "log.jsonl")


@pytest.fixture
def configuring(tmp_path, monkeypatch):
    monkeypatch.setattr(mode_mod, "MODE_FILE", tmp_path / "mode.json")
    mode_mod.save(mode_mod.ModeRecord())
    return mode_mod.Mode.CONFIGURATION


@pytest.fixture
def operating(tmp_path, monkeypatch, log):
    monkeypatch.setattr(mode_mod, "MODE_FILE", tmp_path / "mode.json")
    mode_mod.save(mode_mod.ModeRecord())
    mode_mod.adopt_operating(
        members=["council.a", "council.b", "council.c"],
        parameter_set_hash="abc123", audit=log, actor="council.a",
    )
    return mode_mod.Mode.OPERATING


OPERATOR = Actor("liz.operator", "Liz (Water Bureau)", Role.OPERATOR, bureau="Water")
OT = Actor("sean.ot", "Sean (OT)", Role.OT)
COUNCIL = Actor("council.a", "Council Member A", Role.COUNCIL)


# --------------------------------------------------- chat / scenarios are inert

@pytest.mark.parametrize("target", [
    Target.CONFIG, Target.FRAMEWORK, Target.REGISTRY,
    Target.COUNCIL_LOG, Target.MODE, Target.APPENDIX_INSTANCE,
])
def test_chat_cannot_write_anything(configuring, log, target):
    decision = guard(CHAT_ACTOR, target, "edit", audit=log)
    assert not decision, f"chat was allowed to write {target.value}"
    assert "read-only" in decision.reason


def test_scenario_refusal_is_recorded(configuring, log):
    guard(CHAT_ACTOR, Target.CONFIG, "edit_budget_pool", audit=log)
    last = log.entries()[-1]
    assert last.outcome == "denied"
    assert last.actor == "chat"
    assert last.target == "config"


# ------------------------------------------------------ operators change no rules

def test_operator_cannot_move_a_risk_weight(configuring, log):
    decision = guard(OPERATOR, Target.CONFIG, "edit", audit=log)
    assert not decision
    assert "OT's to set" in decision.reason


def test_operator_cannot_amend_the_framework(configuring, log):
    decision = guard(OPERATOR, Target.FRAMEWORK, "amend", audit=log)
    assert not decision
    assert decision.requires_council


def test_operator_writes_only_projects_they_own(configuring, log):
    mine = guard(OPERATOR, Target.REGISTRY, "advance_stage",
                 owners=["liz.operator"], audit=log)
    assert mine

    theirs = guard(OPERATOR, Target.REGISTRY, "advance_stage",
                   owners=["someone.else"], audit=log)
    assert not theirs
    assert "not an owner" in theirs.reason


# ----------------------------------------------------------- OT owns the config

def test_ot_tunes_freely_in_configuration_mode(configuring, log):
    decision = guard(OT, Target.CONFIG, "edit", audit=log)
    assert decision
    assert "Configuration Mode" in decision.reason


def test_ot_cannot_commit_config_once_guardrails_are_live(operating, log):
    decision = guard(OT, Target.CONFIG, "edit", audit=log)
    assert not decision, "OT committed a governed change in Operating Mode"
    assert decision.requires_council
    assert "proposed and approved" in decision.reason


def test_ot_cannot_amend_the_framework(configuring, log):
    decision = guard(OT, Target.FRAMEWORK, "amend", audit=log)
    assert not decision
    assert decision.requires_council


def test_ot_cannot_write_the_council_record(configuring, log):
    for target in (Target.COUNCIL_LOG, Target.MINUTES, Target.RECORDINGS):
        assert not guard(OT, target, "append", audit=log)


# ------------------------------------------------------------ the Council gate

def test_council_may_amend_framework_and_log_decisions(configuring, log):
    assert guard(COUNCIL, Target.FRAMEWORK, "amend", audit=log)
    assert guard(COUNCIL, Target.COUNCIL_LOG, "log_decision", audit=log)


def test_only_the_council_moves_the_mode(configuring, log):
    for actor in (OPERATOR, OT, CHAT_ACTOR):
        assert not guard(actor, Target.MODE, "adopt_operating", audit=log)
    assert guard(COUNCIL, Target.MODE, "adopt_operating", audit=log)


def test_mode_transition_needs_a_quorum(configuring, log):
    with pytest.raises(mode_mod.ModeError, match="quorum"):
        mode_mod.adopt_operating(members=["council.a"],
                                 parameter_set_hash="x", audit=log)
    assert mode_mod.current() is mode_mod.Mode.CONFIGURATION


def test_adoption_is_not_repeatable(operating, log):
    with pytest.raises(mode_mod.ModeError, match="Already in Operating"):
        mode_mod.adopt_operating(
            members=["council.a", "council.b", "council.c"],
            parameter_set_hash="y", audit=log)


def test_reopening_tuning_is_its_own_council_act(operating, log):
    with pytest.raises(mode_mod.ModeError, match="reason"):
        mode_mod.reopen_configuration(
            members=["council.a", "council.b", "council.c"],
            reason="   ", audit=log)

    with pytest.raises(mode_mod.ModeError, match="quorum"):
        mode_mod.reopen_configuration(
            members=["council.a"], reason="Annual re-tune", audit=log)

    record = mode_mod.reopen_configuration(
        members=["council.a", "council.b", "council.c"],
        reason="Annual re-tune authorized at the March session", audit=log)
    assert record.mode == mode_mod.Mode.CONFIGURATION.value
    assert record.history[-1]["reason"].startswith("Annual re-tune")


def test_require_raises_on_refusal(configuring, log):
    with pytest.raises(Denied):
        require(OPERATOR, Target.CONFIG, "edit", audit=log)


# ------------------------------------------------------------ the record itself

def test_every_attempt_lands_in_the_log(configuring, log):
    guard(OPERATOR, Target.CONFIG, "edit", audit=log)
    guard(OT, Target.CONFIG, "edit", audit=log)
    guard(CHAT_ACTOR, Target.FRAMEWORK, "amend", audit=log)

    outcomes = [(e.actor, e.outcome) for e in log.entries()]
    assert ("liz.operator", "denied") in outcomes
    assert ("sean.ot", "allowed") in outcomes
    assert ("chat", "denied") in outcomes


def test_audit_chain_detects_tampering(log):
    for n in range(4):
        log.append(actor="sean.ot", role="ot", action=f"edit_{n}",
                   target="config", outcome="allowed")
    ok, message = log.verify()
    assert ok, message

    rows = [json.loads(line) for line in
            log.path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[1]["detail"] = {"weight": "quietly changed"}
    log.path.write_text(
        "\n".join(json.dumps(r, sort_keys=True, separators=(",", ":"))
                  for r in rows) + "\n", encoding="utf-8")

    ok, message = log.verify()
    assert not ok
    assert "modified" in message


def test_audit_chain_detects_a_removed_entry(log):
    for n in range(4):
        log.append(actor="council.a", role="council-member",
                   action=f"decision_{n}", target="council_log",
                   outcome="allowed")
    lines = [l for l in log.path.read_text(encoding="utf-8").splitlines() if l.strip()]
    del lines[2]
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, message = log.verify()
    assert not ok
    assert "sequence break" in message or "broken chain" in message
