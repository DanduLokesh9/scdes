"""Brett's Framework tickets of Sep 24 (DEMO account).

BUG-87D0867C  1.1 — "Wanted to select Federal Agency. Not available."
BUG-41D9BD0A  1.7 — "Does your IT program coordinate with a centralized IT
              authority?" Yes/No; if yes, name. The old 1.7 becomes 1.8.
BUG-0081CD67  2.3 — "selected yes, then it says upload or paste. No ability
              to Upload file."
BUG-8EC4E0E9  4.7 — sub-text about the Subscription version.
BUG-1D7F2D29  5.3 — "All of THE ABOVE", not "all of that".
"""

from __future__ import annotations

from app import module_one as m1, prose, spine


def _q(number):
    return next(q for q in m1.all_questions() if q.number == number)


def test_federal_is_a_kind_of_organization():
    labels = {o.value: o.label for o in _q("1.1").options}
    assert labels["federal"] == "Federal agency or department"
    order = [o.value for o in _q("1.1").options]
    assert order.index("federal") == order.index("state") + 1


def test_federal_gets_its_own_examples():
    words = m1.examples_for({"org.kind": "federal"})
    assert "grant" in words["decision"] and words["record"] == "your case management system"


def test_the_central_it_question_is_1_7_and_the_catch_all_is_1_8():
    q = _q("1.7")
    assert q.key == "org.it_authority"
    assert q.prompt == "Does your IT program coordinate with a centralized IT authority?"
    yes = next(o for o in q.options if o.value == "yes")
    assert yes.then_text and "Name" in yes.then_text
    assert {o.value for o in q.options} >= {"yes", "no"}
    assert _q("1.8").key == "org.unusual"


def test_a_named_it_authority_is_written_into_the_framework():
    answers = {"org.it_authority": {"value": "yes",
                                    "detail": "the South Carolina Department of Administration"}}
    clause = prose._clause_for("org.it_authority", answers)
    assert clause is not None
    assert "the South Carolina Department of Administration" in clause.text, clause.text
    assert not spine.banned_in(clause.text)


def test_no_is_no_sentence():
    assert prose._clause_for("org.it_authority", {"org.it_authority": {"value": "no"}}) is None


def test_it_sits_in_authority_and_governance():
    section = next(s for s in prose.SECTIONS if s["title"] == "Authority and governance")
    assert "org.it_authority" in section["keys"]


def test_2_3_offers_an_upload():
    adopted = next(o for o in _q("2.3").options if o.value == "adopted")
    assert adopted.then_upload is True
    assert adopted.as_dict()["then_upload"] is True


def test_4_7_says_where_the_subscription_helps():
    assert "Subscription version of GoverningAI.US" in _q("4.7").help


def test_5_3_says_all_of_the_above():
    field = next(f for f in _q("5.3").tier_fields if f["key"] == "written")
    assert field["defaults"]["high"].startswith("All of the above")
    assert "All of that" not in field["defaults"]["high"]
