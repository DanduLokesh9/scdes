"""The shared standard, and the claims it makes about itself.

SPINE.md is emphatic about a handful of things, and each one is the kind of
claim that decays quietly once eleven surfaces start binding to it. These
tests are what stop that.

The load-bearing ones: the application refuses a passage at two gates and
nowhere else; every number belongs to the organization; organizations are
never scored; a recommendation never blocks and never omits its reason; a
refused passage is not recorded, so no finding may read off an attempt.

Two earlier readings of the blocking rule were wrong — one said the app
blocks in exactly one place, which the Identify gate contradicted; another
read as though every binding floor refused a passage, which would have made
four gates block rather than two. Both are settled in `BINDS`, and the tests
below are what keep them settled.
"""

from __future__ import annotations

import pytest

from app import spine


# ------------------------------------------------------------- the gates

def test_seven_gates_in_order() -> None:
    assert spine.GATE_ORDER == (
        "gate.govern", "gate.identify", "gate.procure", "gate.test",
        "gate.deploy", "gate.measure", "gate.sunset")


def test_every_gate_has_an_owner_that_is_a_real_surface() -> None:
    """The owner of a gate is the surface that holds the evidence the gate
    turns on. That rule is what decides where a new field belongs."""
    surfaces = {"Projects", "Data", "Registry", "Vendors", "Vision",
                "Lifecycle", "Budget", "Oversight", "Process", "Integrity",
                "Audit trail"}
    for g in spine.GATES:
        assert g.owner in surfaces, g.id
        for writer in g.writes_from:
            assert writer in surfaces, f"{g.id}: {writer}"


def test_integrity_owns_two_gates_and_projects_owns_two() -> None:
    """Integrity owns Test and Measure because they are the same record at
    different times: the first check and every check after it, against the
    same baseline. Splitting them would put drift in a different place from
    the baseline it drifted from."""
    owned: dict[str, list[str]] = {}
    for g in spine.GATES:
        owned.setdefault(g.owner, []).append(g.id)
    assert owned["Integrity"] == [spine.TEST, spine.MEASURE]
    assert owned["Projects"] == [spine.IDENTIFY, spine.SUNSET]
    assert owned["Oversight"] == [spine.GOVERN]
    assert owned["Vendors"] == [spine.PROCURE]
    assert owned["Process"] == [spine.DEPLOY]


def test_audit_trail_owns_nothing() -> None:
    """A record of what happened cannot also be a participant in it."""
    assert all(g.owner != "Audit trail" for g in spine.GATES)
    assert all("Audit trail" not in g.writes_from for g in spine.GATES)


def test_lifecycle_holds_no_record_and_writes_nowhere() -> None:
    assert all("Lifecycle" not in g.writes_from for g in spine.GATES)
    assert all(g.owner != "Lifecycle" for g in spine.GATES)


def test_no_gate_is_ever_rendered_as_a_number() -> None:
    """Numbered gates invite a reader to line them up against somebody
    else's and import a staging scheme this platform did not write."""
    copy = " ".join(
        [g.name + " " + g.turns_on for g in spine.GATES]
        + [s.shown_as + " " + s.means for s in spine.STATES]
        + list(spine.REASONS) + list(spine.ABSENCE_COUNTERS)
        + [r.says + " " + r.because for r in spine.RECOMMENDATIONS]
        + [f.says for f in spine.FINDINGS]).lower()
    for form in spine.BANNED_GATE_FORMS:
        assert form not in copy, form


# --------------------------------------------- the two refusals, and only two

def test_exactly_two_gates_can_refuse() -> None:
    """The claim the whole spine turns on."""
    assert set(spine.REFUSING_GATES) == {spine.IDENTIFY, spine.DEPLOY}


def test_identify_refuses_on_one_obligation() -> None:
    assert spine.binding(spine.IDENTIFY, spine.SATISFIED) == (
        "floor.somebody_named",)


def test_deploy_refuses_on_six() -> None:
    assert len(spine.binding(spine.DEPLOY, spine.SATISFIED)) == 6


def test_procure_and_sunset_bind_by_answer_not_by_result() -> None:
    """A vendor who will not grant a term is a fact to record and argue
    with, not a reason this application refuses to let the organization buy
    anything."""
    for g in (spine.PROCURE, spine.SUNSET):
        assert spine.binding(g, spine.ANSWERED)
        assert spine.binding(g, spine.SATISFIED) == ()


def test_nothing_binds_at_govern_test_or_measure() -> None:
    for g in (spine.GOVERN, spine.TEST, spine.MEASURE):
        assert spine.BINDS[g] == {}


def test_identify_refuses_a_project_with_nobody_named() -> None:
    answer = spine.may_pass(spine.IDENTIFY, spine.PROCURE,
                            spine.BEING_WORKED,
                            satisfied=set(), has_owner=False)
    assert not answer.ok
    assert answer.refused == spine.REFUSE_IDENTIFY
    # And says where it could go instead, so the refusal is navigable.
    assert answer.refused_illegal


def test_identify_lets_a_named_project_through() -> None:
    answer = spine.may_pass(spine.IDENTIFY, spine.PROCURE,
                            spine.BEING_WORKED,
                            satisfied={"floor.somebody_named"})
    assert answer.ok
    assert answer.committed == spine.PROCURE


def test_deploy_refuses_until_all_six_point_at_something() -> None:
    six = set(spine.binding(spine.DEPLOY, spine.SATISFIED))
    for missing in sorted(six):
        answer = spine.may_pass(spine.DEPLOY, spine.MEASURE,
                                spine.WAITING_DECISION,
                                satisfied=six - {missing})
        assert not answer.ok, missing
        assert answer.refused == spine.REFUSE_DEPLOY
    assert spine.may_pass(spine.DEPLOY, spine.MEASURE,
                          spine.WAITING_DECISION, satisfied=six).ok


def test_procure_records_the_passage_with_a_term_absent() -> None:
    """Nothing at Procure is refused. The absent term produces a finding."""
    answer = spine.may_pass(spine.PROCURE, spine.TEST, spine.BEING_WORKED,
                            satisfied=set())
    assert answer.ok
    assert spine.unmet(spine.PROCURE, set())


def test_sunset_closes_even_where_deletion_was_never_confirmed() -> None:
    """A retirement this application refused to record would leave the
    organization with a tool that is off and a register that says it is
    running."""
    assert spine.may_move(spine.MEASURE, spine.SUNSET, spine.BEING_WORKED).ok


# ------------------------------------------------------------- transitions

def test_skipping_forward_is_not_available() -> None:
    """A project found already running still walks Identify, Procure and
    Test in order, with each gate's paper marked as recorded after the fact.
    The record shows what actually happened, including that it happened out
    of order."""
    answer = spine.may_move(spine.IDENTIFY, spine.DEPLOY, spine.BEING_WORKED)
    assert not answer.ok
    assert answer.refused == spine.REFUSE_NOT_AVAILABLE


@pytest.mark.parametrize("frm,to", [
    (spine.MEASURE, spine.TEST),     # the vendor changed something
    (spine.DEPLOY, spine.TEST),      # evidence failed
    (spine.MEASURE, spine.IDENTIFY),  # the scrutiny level was wrong
    (spine.MEASURE, spine.SUNSET),   # retirement does not walk back
    (spine.DEPLOY, spine.SUNSET),
])
def test_the_five_non_forward_moves_are_legal(frm: str, to: str) -> None:
    assert spine.may_move(frm, to, spine.BEING_WORKED).ok, f"{frm} -> {to}"


def test_the_update_loop_runs() -> None:
    """Measure to Test to Deploy and back to Measure. The most frequent
    non-forward move in the product and the only one that is routine — and
    the reason this is a workflow manager rather than a checklist."""
    six = set(spine.binding(spine.DEPLOY, spine.SATISFIED))
    assert spine.may_move(spine.MEASURE, spine.TEST, spine.BEING_WORKED).ok
    assert spine.may_move(spine.TEST, spine.DEPLOY, spine.CLEARED).ok
    assert spine.may_pass(spine.DEPLOY, spine.MEASURE, spine.CLEARED,
                          satisfied=six).ok


def test_nothing_moves_from_a_stop_until_it_is_reversed() -> None:
    for stopped in spine.STOPPED:
        answer = spine.may_move(spine.TEST, spine.DEPLOY, stopped)
        assert not answer.ok
        assert answer.refused == spine.REFUSE_STOPPED
        # And names the reversal, so the refusal says what to do next.
        assert answer.refused_illegal in ((spine.START_AGAIN,),
                                          (spine.PICK_UP_AGAIN,))


def test_a_refusal_never_composes_its_own_wording() -> None:
    """A user meeting two wordings for one refusal will assume they mean
    different things."""
    seen = set()
    for frm in spine.GATE_ORDER:
        for to in spine.GATE_ORDER:
            for st in spine.STATE_ORDER:
                answer = spine.may_pass(frm, to, st, satisfied=set(),
                                        has_owner=False)
                if answer.refused:
                    seen.add(answer.refused)
    assert seen, "nothing was refused, so this proved nothing"
    for reason in seen:
        assert reason in spine.REASONS, reason


def test_asking_a_project_for_evidence_it_has_not_reached_yet() -> None:
    """A different question from "may it move", with its own sentence.

    Measure reads the baseline written at Procure. Asking for it before the
    project has been through that gate is not an illegal move — nobody
    proposed a move — it is a surface reaching for evidence that does not
    exist yet, and it says so by name.
    """
    answer = spine.requires_passed(spine.IDENTIFY, spine.PROCURE)
    assert not answer.ok
    assert answer.refused == "This has not passed Procure yet."
    assert spine.requires_passed(spine.MEASURE, spine.PROCURE).ok


def test_every_reason_string_is_reachable() -> None:
    """A reason nothing returns is a sentence nobody maintains."""
    reached = set()
    for frm in spine.GATE_ORDER:
        for to in spine.GATE_ORDER:
            for st in (spine.BEING_WORKED, spine.PAUSED, spine.TURNED_DOWN):
                got = spine.may_pass(frm, to, st, has_owner=False)
                if got.refused:
                    reached.add(got.refused)
            got = spine.requires_passed(frm, to)
            if got.refused:
                reached.add(got.refused.split(" yet")[0].rsplit(" ", 1)[0])
    # Every reason but the retirement one, which belongs to Projects closing
    # a Sunset record and is returned there rather than by the spine.
    unreached = [r for r in spine.REASONS
                 if r != spine.REFUSE_RETIREMENT
                 and r not in reached
                 and not any(r.startswith(x.rsplit(" ", 2)[0])
                             for x in reached)]
    assert not unreached, unreached


def test_a_refused_passage_is_not_recorded() -> None:
    """The protocol returns a string and writes nothing. It follows that
    there can be no finding whose trigger is an attempted-and-refused
    passage — such a finding would read off state this app never stores."""
    answer = spine.may_pass(spine.IDENTIFY, spine.PROCURE, spine.PROPOSED,
                            has_owner=False)
    assert not answer.ok
    assert answer.committed == ""
    assert "a passage was attempted and refused" in spine.NOT_FINDINGS
    for finding in spine.FINDINGS:
        assert "refus" not in finding.trigger.lower(), finding.id


# ------------------------------------------------------------ the three flags

def test_running_ahead_is_the_most_valuable_fact_and_not_an_accusation() -> None:
    assert spine.running_ahead(spine.IN_USE_YES, spine.IDENTIFY)
    assert spine.running_ahead(spine.IN_USE_YES, spine.TEST)
    # Past Deploy it is simply in use.
    assert not spine.running_ahead(spine.IN_USE_YES, spine.MEASURE)
    assert not spine.running_ahead(spine.IN_USE_NO, spine.IDENTIFY)
    # The wording never accuses.
    said = spine.BY_FINDING["finding.running_ahead"].says.lower()
    for word in ("unauthorised", "unauthorized", "violation", "illegal",
                 "should not", "failure"):
        assert word not in said


def test_a_discovered_tool_is_a_complete_record() -> None:
    """`state.proposed` at `gate.identify` with `in_use = not known` is
    valid, and on the first day of a small organization's use it is most of
    the list."""
    record = {"gate": spine.IDENTIFY, "state": spine.PROPOSED,
              "in_use": spine.IN_USE_UNKNOWN}
    assert record["state"] in spine.STATE_ORDER
    assert record["in_use"] in spine.IN_USE
    assert spine.flags(record)["running_ahead"] is False


def test_conditions_and_versions_are_flags_rather_than_states() -> None:
    """A project can be running with conditions open, and pretending
    otherwise is how conditions get forgotten."""
    assert spine.conditions_open([{"closed": None}])
    assert not spine.conditions_open([{"closed": "2026-01-01"}])
    assert not spine.conditions_open([])
    assert spine.version_pending([{"live": "", "material": "yes"}])
    assert not spine.version_pending([{"live": "2026-01-01"}])
    assert not spine.version_pending([{"live": "", "material": "no"}])
    for name in ("conditions_open", "version_pending"):
        assert name not in spine.STATE_ORDER


# ------------------------------------------------------------ gaps

def test_a_gap_without_a_question_is_not_a_gap() -> None:
    """A surface that opened one for every blank would make its own clean
    state unreachable."""
    ok, why = spine.Gap(question="", field="cost", answer="We don't know",
                        owner="Clerk").valid()
    assert not ok
    assert "question" in why


def test_a_gap_without_an_owner_is_not_a_gap() -> None:
    ok, why = spine.Gap(question="7.2", field="cost",
                        answer="We don't know", owner="").valid()
    assert not ok
    assert "outside help" in why


def test_a_gap_carries_one_of_the_four_answers() -> None:
    ok, _ = spine.Gap(question="7.2", field="cost", answer="dunno",
                      owner="Clerk").valid()
    assert not ok
    for answer in spine.NOT_SURE:
        ok, why = spine.Gap(question="7.2", field="cost", answer=answer,
                            owner="Clerk").valid()
        assert ok, why


def test_nobody_has_counted_is_the_measurement_form() -> None:
    """It exists for the baseline at Procure and the claim at Vision."""
    assert "Nobody has counted" in spine.NOT_SURE


# -------------------------------------------------------- recommendations

def test_every_recommendation_carries_its_reason() -> None:
    """A recommendation with no reason is an instruction, and this
    application does not issue instructions."""
    for rec in spine.RECOMMENDATIONS:
        ok, why = rec.valid()
        assert ok, f"{rec.id}: {why}"
        assert len(rec.because) > 40, rec.id


def test_no_recommendation_names_a_vendor_or_a_product() -> None:
    for rec in spine.RECOMMENDATIONS:
        words = (rec.says + " " + rec.because).lower()
        for named in ("microsoft", "google", "openai", "copilot", "chatgpt",
                      "salesforce", "oracle", "aws", "azure"):
            assert named not in words, rec.id


def test_declining_a_recommendation_is_recorded_without_comment() -> None:
    """Declining is a complete and legitimate answer. There is no gate, no
    state and no finding whose trigger is a declined recommendation."""
    assert "a recommendation was declined" in spine.NOT_FINDINGS
    for finding in spine.FINDINGS:
        assert "recommendation" not in finding.trigger.lower(), finding.id
    rec = spine.Recommendation("x", spine.IDENTIFY, "s", "b" * 41)
    rec.state = spine.DECLINED
    ok, _ = rec.valid()
    assert ok
    assert rec.declined_note == "", "never required"


def test_the_module_one_answer_outranks_anything_we_would_say() -> None:
    """Where Module One already has a recommended answer, the recommendation
    reads it back rather than inventing a new one."""
    from_m1 = [r for r in spine.RECOMMENDATIONS
               if r.basis == spine.FROM_MODULE_ONE]
    assert len(from_m1) >= 3
    assert any("8.6" in r.because for r in from_m1)


def test_no_finding_punishes_a_missing_classification_scheme() -> None:
    """AI governance is not data governance. Nothing in the framework asks
    for a classification scheme or treats its absence as a defect."""
    assert ("the organization has no data classification scheme"
            in spine.NOT_FINDINGS)
    for finding in spine.FINDINGS:
        assert "classification" not in finding.trigger.lower(), finding.id


# ------------------------------------------------------------- the role matrix

def test_proposing_is_open_to_everybody() -> None:
    """Restricting who may write something down produces organizations where
    nothing is written down."""
    for what, who in spine.MAY_PROPOSE.items():
        for role in spine.ROLES:
            assert who.get(role) in ("yes", "reads"), f"{what}/{role}"


def test_anyone_at_all_may_report_an_incident() -> None:
    """A reporting route that depends on holding a hat is one people go
    around."""
    assert spine.MAY_PROPOSE["incident_report"].get("anyone") == "yes"


def test_the_technology_office_approves_nothing_on_its_own() -> None:
    """Its approvals are readiness confirmations the decision-maker's
    approval depends on, and they exist only where the organization said
    technology has to be asked."""
    for gate_id in spine.GATE_ORDER:
        answer = spine.MAY_APPROVE.get(gate_id, {}).get(spine.TECHNOLOGY)
        assert answer in (None, "no", spine.READINESS), gate_id


def test_the_operator_approves_only_within_their_own_delegation() -> None:
    for gate_id in (spine.IDENTIFY, spine.PROCURE):
        assert spine.MAY_APPROVE[gate_id][spine.OPERATOR] == spine.DELEGATED
    for gate_id in (spine.TEST, spine.DEPLOY):
        assert spine.MAY_APPROVE[gate_id][spine.OPERATOR] == "no"


def test_nobody_approves_govern() -> None:
    """The organization passes Govern, not the project, and the adopting
    authority is a named party rather than a fourth hat with a login."""
    for role in spine.ROLES:
        assert spine.MAY_APPROVE[spine.GOVERN][role] == "no"


def test_a_hat_that_may_approve_may_attach_a_condition() -> None:
    """Conditions are the mechanism that keeps this application from
    blocking. Restricting who may attach one leaves the mechanism out of
    reach of the person in front of the missing answer."""
    own = spine.MAY_APPROVE["condition_on_own_passage"]
    assert own[spine.OPERATOR] == spine.DELEGATED
    assert own[spine.DECIDER] == "yes"


def test_stopping_and_retiring_are_separate_powers() -> None:
    """Requiring a quorum to stop a malfunctioning tool is how a small
    problem becomes a large one over a weekend."""
    assert spine.MAY_RETIRE["stop_immediately"][spine.OPERATOR] != "no"
    assert spine.MAY_RETIRE["decide_tool_retirement"][spine.OPERATOR] == "no"
    # Retiring a version inside the loop is bookkeeping, open to anyone.
    for role in spine.ROLES:
        assert spine.MAY_RETIRE["retire_version"][role] == "yes"


def test_who_amends_the_framework_is_their_answer_and_not_ours() -> None:
    for role in spine.ROLES:
        assert (spine.MAY_APPROVE["framework_amendment"][role]
                == spine.THEIR_ANSWER)


def test_concentration_is_a_count_and_never_a_score() -> None:
    said = spine.concentration({"jo": [spine.OPERATOR, spine.TECHNOLOGY,
                                       spine.DECIDER]})
    assert said == "3 of 3 roles held by one person"
    for word in ("risk", "score", "warning", "should", "concern", "poor"):
        assert word not in said.lower()


# ------------------------------------------------------- the hierarchy

def test_the_hierarchy_reaches_a_vendor_last() -> None:
    assert spine.HIERARCHY[-1].name == "An external vendor's tool"
    assert spine.HIERARCHY[0].name == "Define the problem"


def test_two_steps_are_separate_on_purpose() -> None:
    """A unit with a problem does not know what the unit down the hall
    already owns, and collapsing the two loses the more valuable half."""
    assert spine.HIERARCHY[1].name == "Fix it in house now"
    assert spine.HIERARCHY[2].name == "Another business unit"


def test_most_honest_outcomes_are_not_technology() -> None:
    """A surface that renders the hierarchy as a route to a purchase has
    misread it."""
    technology = [o for o in spine.HIERARCHY_OUTCOMES
                  if "build" in o.lower() or "buy" in o.lower()]
    assert len(technology) == 2
    assert len(spine.HIERARCHY_OUTCOMES) > 6
    assert "Do nothing" in spine.HIERARCHY_OUTCOMES


# -------------------------------------------------------------- vocabulary

def test_the_spine_obeys_its_own_vocabulary_rule() -> None:
    """Say tool. The one sanctioned use of the deploy root is the gate name
    itself, so the check runs over the copy rather than the identifiers."""
    copy = " ".join(
        [g.turns_on for g in spine.GATES]
        + [s.means for s in spine.STATES]
        + [f.says for f in spine.FLOORS]
        + list(spine.REASONS) + list(spine.ABSENCE_COUNTERS)
        + [spine.NOTHING_TO_FLAG, spine.SAME_PERSON_NOTE,
           spine.NO_TECHNOLOGY_NOTE]
        + [f.says for f in spine.FINDINGS]
        + [r.says for r in spine.RECOMMENDATIONS]).lower()
    for word in spine.BANNED_IN_COPY:
        assert word not in spine.banned_in(copy), word


def test_nothing_is_ever_deployed_in_the_spines_own_words() -> None:
    """Deploy is a gate name and the only sanctioned use of that root.
    Everywhere else a tool *goes live* or is *in use* — including in the
    recommendation about notice, which used to borrow the other word."""
    notice = spine.BY_RECOMMENDATION["rec.notice_of_changes"]
    assert notice.says == "Require notice before changes go live"
    assert notice.basis == spine.FROM_MODULE_ONE
    for said in [r.says + " " + r.because for r in spine.RECOMMENDATIONS]:
        assert "deploy" not in said.lower()


def test_no_number_belongs_to_the_application() -> None:
    """No default review period, no default dollar amount, no default sample
    size, no default number of scrutiny levels. Where this module is tempted
    to write a number, it writes a read-back instead."""
    import re
    copy = " ".join(
        [g.turns_on for g in spine.GATES]
        + [f.says for f in spine.FLOORS]
        + [r.says + " " + r.because for r in spine.RECOMMENDATIONS]
        + [f.says for f in spine.FINDINGS])
    # The only numerals permitted are the framework question references the
    # read-back quotes, such as "8.6".
    numbers = [n for n in re.findall(r"\b\d+(?:\.\d+)?\b", copy)
               if "." not in n]
    assert not numbers, numbers


def test_the_clean_state_is_one_shared_sentence() -> None:
    """So that eleven surfaces do not each invent their own way of saying
    nothing is wrong."""
    assert spine.NOTHING_TO_FLAG.startswith("Nothing to flag")
    assert "your framework" in spine.NOTHING_TO_FLAG


def test_the_absence_counters_are_distinct() -> None:
    """Take one; do not take one another surface has taken."""
    assert len(set(spine.ABSENCE_COUNTERS)) == len(spine.ABSENCE_COUNTERS)


# ----------------------------------------------------------- serialisation

def test_the_whole_spine_serialises_for_the_browser() -> None:
    import json
    blob = spine.as_dict()
    json.dumps(blob)
    assert len(blob["gates"]) == 7
    assert len(blob["states"]) == 8
    assert len(blob["floors"]) == 8
    assert len(blob["findings"]) == 13
    assert len(blob["recommendations"]) == 9
    assert blob["refusing_gates"] == [spine.IDENTIFY, spine.DEPLOY]
