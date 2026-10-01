"""The Integrity screen: the framework read in, the findings it adds, and the
public page for somebody with no login.

The register itself is pinned in test_checks.py. These pin what the screen
needed on top of it: that every input comes from the organization's own
answers and nothing stands in for one that is missing; the two findings
that were specified but not computed; the incident date that was being
filled in with today; and the public page's promises — no lookup, third
person, no agency code in its address, and a stranger's report written into
that organization's register and no other.
"""

from __future__ import annotations

import pytest

from app import checks, public_report, server, spine, tenant
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")

ANSWERS = {
    "org.kind": "county",
    "risk.levels": "two",
    "watch.cadence": {"routine": {"every": "annual"},
                      "elevated": {"every": "quarterly"}},
    "watch.what": ["accuracy"],
    "watch.failing": "pause",
    "bad.lookback": "yes", "bad.lookback_far": "90",
    "bad.tell": ["board", "federal"],
    "bad.levels": {"minor": {"meaning": "Caught before it reached anyone."}},
    "bad.speed": {"serious": "3days"},
    "bad.report_to": "the IT service desk, 555-0100",
    "floor.fallback_tested": "annual",
    "risk.factors": {"disparate": "major"},
    "org.functions": {"legal": "contracted"},
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_file", lambda: tmp_path / "checks.json")
    monkeypatch.setattr(checks, "_log", lambda *a, **k: None)
    monkeypatch.setattr(public_report, "LINKS_FILE", tmp_path / "links.json")
    monkeypatch.setattr(public_report, "_log", lambda *a, **k: None)
    public_report._seen_address.clear()
    public_report._seen_link.clear()
    yield


# ------------------------------------------------------ the framework, read in

def test_every_input_is_their_own_answer() -> None:
    got = checks.framework_inputs(ANSWERS)
    assert got["levels"] == ["Routine", "Elevated"]
    assert got["intervals"] == {"Routine": 366, "Elevated": 92}
    assert got["determination"] == checks.PAUSE_UNTIL_FIXED
    assert got["lookback_answer"] == checks.LOOKBACK_YES
    assert got["lookback_scope"] == "90 days"
    assert got["route"].startswith("the IT service desk")
    assert got["organisation_type"] == "County government"


def test_nothing_is_invented_for_an_unanswered_framework() -> None:
    got = checks.framework_inputs({})
    assert got["levels"] == [] and got["intervals"] == {}
    assert got["watches"] == [] and got["must_be_told"] == []
    assert got["severities"] == [] and got["report_hours"] == {}
    assert got["route"] == "" and got["fallback_days"] is None
    # An unanswered 10.6 is not a yes: no look-back is ever owed from it.
    assert got["lookback_answer"] == checks.LOOKBACK_UNSURE


def test_a_federal_partner_is_told_only_where_they_run_a_delegated_program() \
        -> None:
    assert checks.framework_inputs(ANSWERS)["must_be_told"] == [
        "Your board or elected officials"]
    delegated = {**ANSWERS, "org.delegated": "yes"}
    assert "A federal partner" in checks.framework_inputs(delegated)[
        "must_be_told"]


def test_a_level_with_no_interval_is_left_without_one() -> None:
    answers = {**ANSWERS, "watch.cadence": {"routine": {"every": "annual"}}}
    assert checks.framework_inputs(answers)["intervals"] == {"Routine": 366}


# ------------------------------------------------ the two findings added here

def _measure_project(**over):
    return {"ref": "P1", "name": "Permit triage", "gate": spine.MEASURE,
            "level": "Routine", **over}


def test_fallback_untried_where_they_said_it_is_tried_on_an_interval() -> None:
    found = checks.surface(answers=ANSWERS, projects=[_measure_project()])
    said = [f["says"] for f in found["raised"]
            if f["id"] == "finding.fallback_untried"]
    assert said == ["You said the manual way gets tried once a year. There "
                    "is no record of anyone trying it."]


def test_fallback_tried_recently_raises_nothing() -> None:
    checks.record_check(project="P1", actor=WHO, occasion=checks.REGULAR_LOOK,
                        manual_way=checks.MANUAL_TRIED, limits="None tried",
                        complete=True)
    found = checks.surface(answers=ANSWERS, projects=[_measure_project()])
    assert not any(f["id"] == "finding.fallback_untried"
                   for f in found["raised"])


def test_never_testing_the_fallback_is_their_answer_and_never_raised() -> None:
    answers = {**ANSWERS, "floor.fallback_tested": "never"}
    found = checks.surface(answers=answers, projects=[_measure_project()])
    assert not any(f["id"] == "finding.fallback_untried"
                   for f in found["raised"])


def test_a_test_check_saying_nothing_about_groups_is_raised() -> None:
    checks.record_check(project="P1", actor=WHO, occasion=checks.FIRST_LOOK,
                        limits="Only March files", complete=True)
    found = checks.surface(answers=ANSWERS, projects=[_measure_project()])
    said = [f["says"] for f in found["raised"]
            if f["id"] == "finding.groups_check_missing"]
    assert said and "a major concern" in said[0]


def test_where_the_factor_is_not_a_concern_nothing_is_asked() -> None:
    answers = {**ANSWERS, "risk.factors": {"disparate": "none"}}
    checks.record_check(project="P1", actor=WHO, occasion=checks.FIRST_LOOK,
                        limits="Only March files", complete=True)
    found = checks.surface(answers=answers, projects=[_measure_project()])
    assert not any(f["id"] == "finding.groups_check_missing"
                   for f in found["raised"])


def test_finding_sentences_do_not_capitalise_mid_sentence() -> None:
    checks.record_check(project="P1", actor=WHO, occasion=checks.REGULAR_LOOK,
                        limits="x", complete=True)
    checks.report_incident(actor=WHO, what_happened="Wrong answer")
    for f in checks.surface(answers=ANSWERS,
                            projects=[_measure_project()])["raised"]:
        assert "watch Whether" not in f["says"]
        assert "said Your" not in f["says"]


# ------------------------------------------------------ incident dates

def test_an_incident_with_no_date_is_not_given_today() -> None:
    made = checks.report_incident(actor=WHO, what_happened="Wrong answer")
    row = made["incident"]
    assert row["at"] == ""
    assert "not known" in checks.date_column(row)


# ----------------------------------------------------------- the recommendation

def test_the_recommendation_carries_its_reason_and_can_be_declined() -> None:
    made = checks.record_check(project="P1", actor=WHO,
                               where=checks.WHERE_NONE)
    ref = made["check"]["ref"]
    found = checks.surface(answers=ANSWERS, projects=[_measure_project()])
    rec = found["recommended"][0]
    assert rec["reason"] and rec["state"] == spine.OFFERED
    assert checks.answer_recommendation(ref, spine.DECLINED, actor=WHO)["ok"]
    again = checks.surface(answers=ANSWERS, projects=[_measure_project()])
    assert again["recommended"][0]["state"] == spine.DECLINED
    # Declining raises nothing, anywhere.
    assert len(again["raised"]) == len(found["raised"])


# ---------------------------------------------------------- the public page

@pytest.fixture
def live_agency(monkeypatch):
    from app import tenancy
    monkeypatch.setattr(tenancy, "agency_state",
                        lambda code: {"active": code == "gc.county"})
    monkeypatch.setattr(tenancy, "_agency_names",
                        lambda code: {"agency_label": "Greenville County"})
    monkeypatch.setattr(public_report, "_inputs",
                        lambda agency: checks.framework_inputs(ANSWERS))
    return "gc.county"


def test_the_address_carries_no_agency_code(live_agency) -> None:
    token = public_report.make_link(live_agency, WHO)
    assert live_agency not in token
    assert len(token) >= 20
    assert public_report.agency_for(token) == live_agency


def test_a_wrong_token_looks_like_one_that_never_existed(live_agency) -> None:
    public_report.make_link(live_agency, WHO)
    page = public_report.form("not-a-real-token")
    assert public_report.NOT_FOUND_TITLE in page
    assert "Greenville" not in page


def test_replacing_the_link_stops_the_old_one(live_agency) -> None:
    old = public_report.make_link(live_agency, WHO)
    new = public_report.make_link(live_agency, WHO)
    assert public_report.agency_for(old) == ""
    assert public_report.agency_for(new) == live_agency


def test_a_link_for_an_inactive_container_opens_nothing(live_agency) -> None:
    token = public_report.make_link("someone.else", WHO)
    assert public_report.agency_for(token) == ""


def test_the_page_speaks_in_the_third_person(live_agency) -> None:
    page = public_report.form(public_report.make_link(live_agency, WHO))
    assert "You said" not in page and "you said" not in page
    assert "Greenville County recorded that it goes to the IT service desk" \
        in page
    assert "Caught before it reached anyone." in page


def test_the_page_has_no_lookup_and_no_navigation(live_agency) -> None:
    page = public_report.form(public_report.make_link(live_agency, WHO))
    assert page.count("<form") == 1
    assert "<nav" not in page and "href=" not in page
    assert "<script" not in page


def test_internal_role_titles_never_reach_the_public_page(live_agency,
                                                          monkeypatch) -> None:
    answers = {**ANSWERS, "bad.stopper": [{"role": "Deputy Director"}]}
    monkeypatch.setattr(public_report, "_inputs",
                        lambda agency: checks.framework_inputs(answers))
    page = public_report.form(public_report.make_link(live_agency, WHO))
    assert "Deputy Director" not in page


def test_a_report_is_written_into_that_organisations_register(
        live_agency, tmp_path, monkeypatch) -> None:
    seen = {}

    def scoped_file():
        seen["agency"] = tenant.current()
        return tmp_path / f"{tenant.current()}-checks.json"
    monkeypatch.setattr(checks, "_file", scoped_file)
    token = public_report.make_link(live_agency, WHO)
    status, page = public_report.submit(
        token, b"what_happened=It+told+me+the+wrong+fee&name=", "203.0.113.9")
    assert status == 200
    assert seen["agency"] == live_agency
    assert "Your reference is" in page and "IN-" in page
    assert "Nobody is emailed" in page


def test_an_empty_report_is_refused_in_place(live_agency) -> None:
    token = public_report.make_link(live_agency, WHO)
    status, page = public_report.submit(token, b"what_happened=&tool=",
                                        "203.0.113.9")
    assert status == 400 and 'role="alert"' in page


def test_one_address_cannot_flood_the_register(live_agency) -> None:
    token = public_report.make_link(live_agency, WHO)
    for _ in range(public_report.PER_ADDRESS_PER_HOUR):
        assert public_report.submit(token, b"what_happened=x",
                                    "203.0.113.9")[0] == 200
    assert public_report.submit(token, b"what_happened=x",
                                "203.0.113.9")[0] == 429


def test_a_severity_not_on_their_list_is_not_kept(live_agency, tmp_path,
                                                  monkeypatch) -> None:
    token = public_report.make_link(live_agency, WHO)
    public_report.submit(token, b"what_happened=x&severity=Catastrophic",
                         "203.0.113.9")
    assert checks.all_entries()[0]["severity"] == ""


# ------------------------------------------- the public page, over HTTP

@pytest.fixture
def running(live_agency):
    import threading
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _fetch(url: str, data: bytes | None = None) -> tuple[int, str, dict]:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def test_the_public_page_is_served_as_html_without_script(running,
                                                          live_agency) -> None:
    token = public_report.make_link(live_agency, WHO)
    status, page, headers = _fetch(f"{running}/report/{token}")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert "<script" not in page and 'method="post"' in page
    assert headers.get("X-Robots-Tag", "").startswith("noindex")


def test_a_report_posts_as_a_plain_form_and_returns_its_reference(
        running, live_agency) -> None:
    token = public_report.make_link(live_agency, WHO)
    status, page, _ = _fetch(f"{running}/report/{token}",
                             b"what_happened=It+quoted+the+wrong+fee")
    assert status == 200 and "Your reference is" in page


def test_the_agency_code_is_not_an_address(running, live_agency) -> None:
    public_report.make_link(live_agency, WHO)
    status, page, _ = _fetch(f"{running}/report/{live_agency}")
    assert status == 404 and "Greenville" not in page


# ----------------------------------------------------------------- the routes

def test_the_routes_are_registered() -> None:
    for method, path in (("GET", "/api/checks"), ("POST", "/api/checks"),
                         ("POST", "/api/checks/complete"),
                         ("POST", "/api/incidents"),
                         ("POST", "/api/checks/public-link"),
                         ("POST", "/api/checks/recommendation")):
        assert (method, path) in server.ROUTES


def test_the_badge_drops_a_zero() -> None:
    assert checks.badge([], open_findings=0) == "Integrity 0"
