"""One agency must never see another's governance.

The client's standing rule, in his capitals:

    "THE ENTIRE MODULAR PROCESS IS NOT TO EVER REFERENCE OR HAVE ACCESS TO
     OTHER AGENCIES."

It was broken in three places at once, and only the first was reported:

  1. `corpus/` holds one agency's framework, manual and fourteen appendices,
     and the framework screen listed them for whoever asked. The client saw
     SCDES's papers inside the DEMO account.
  2. `framework_versions.json` is one file. Two registered agencies answered
     the same thirteen questions into it, so each would have found the other's
     words in their own framework.
  3. `decider.py` cached "who decides" in a module-level variable. Whichever
     agency asked first decided for every agency until the process restarted.

The first is a leak you can see. The other two are leaks you would only notice
after trusting the output, which is worse. So most of what is asserted here is
that a second agency finds *nothing* — an empty shelf being the truthful answer
before an agency has a framework of its own.
"""

from __future__ import annotations

import pytest

from app import decider, framework, tenant, versions
from app.authz import Actor, Role

OWNER = "sc.des"          # the agency whose documents are in corpus/
OTHER = "iia.test"        # the DEMO container

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    """Each test gets its own agency directories and no leftover cache."""
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    monkeypatch.setattr(tenant, "corpus_owner", lambda: OWNER)
    decider.invalidate()
    yield
    decider.invalidate()


def as_agency(code):
    """Act as `code` for the duration of a `with` block."""
    class _Ctx:
        def __enter__(self):
            self.token = tenant.set_current(code)
            decider.invalidate()
            return self

        def __exit__(self, *exc):
            tenant.reset(self.token)
            decider.invalidate()
    return _Ctx()


# ------------------------------------------------------------- the documents

def test_the_corpus_owner_sees_its_own_documents() -> None:
    with as_agency(OWNER):
        status = framework.status()
    assert status.document_count > 0, "SCDES must still see SCDES's papers"


def test_another_agency_sees_no_documents_at_all() -> None:
    """The reported bug, exactly: "See no reference documents in the DEMO
    account" against "I see all the reference documents, from SCDES to the
    appendices"."""
    with as_agency(OTHER):
        status = framework.status()
    assert status.document_count == 0
    assert all(not layer["files"] for layer in status.layers)
    assert all(not layer["present"] for layer in status.layers)
    assert status.state == "none"


def test_no_tenant_means_the_corpus_as_before() -> None:
    """Tests, the CLI and the ingest tools operate on the corpus directly. The
    leak was never those — it was one browser being shown another's files."""
    assert framework.status().document_count > 0


# --------------------------------------------------------------- the answers

def test_two_agencies_answer_into_different_files() -> None:
    with as_agency(OWNER):
        owner_file = versions._file()
    with as_agency(OTHER):
        other_file = versions._file()
    assert owner_file != other_file


def test_an_answer_given_by_one_agency_is_invisible_to_the_other(tmp_path,
                                                                 monkeypatch) -> None:
    # The owner writes to the real corpus file, which this test must not touch.
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "owner.json")

    with as_agency(OTHER):
        versions.answer("purpose.why", "Because DEMO said so.", OT)
        assert versions.state()["working"]["purpose.why"]["value"] \
            == "Because DEMO said so."

    with as_agency(OWNER):
        assert "purpose.why" not in versions.state()["working"], \
            "DEMO's words reached SCDES's framework"


def test_two_agencies_do_not_overwrite_each_other(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "owner.json")

    with as_agency(OTHER):
        versions.answer("purpose.why", "DEMO's answer.", OT)
    with as_agency(OWNER):
        versions.answer("purpose.why", "SCDES's answer.", OT)
    with as_agency(OTHER):
        assert versions.state()["working"]["purpose.why"]["value"] \
            == "DEMO's answer."
    with as_agency(OWNER):
        assert versions.state()["working"]["purpose.why"]["value"] \
            == "SCDES's answer."


# ------------------------------------------------------------ who decides

def test_the_decider_is_not_shared_between_agencies() -> None:
    """The module-level cache meant whichever agency asked first decided for
    everyone."""
    with as_agency(OWNER):
        first = decider.load()
    with as_agency(OTHER):
        second = decider.load()
    assert second.shape == decider.UNSET, \
        "DEMO was handed SCDES's answer to who decides"
    assert first is not second


def test_a_second_agency_is_offered_nothing_derived_from_the_corpus() -> None:
    """Deriving reads the charter. An agency with no corpus has no charter, and
    proposing SCDES's answer is the one suggestion this must never make."""
    with as_agency(OTHER):
        loaded = decider.load()
    assert loaded.shape == decider.UNSET
    assert not loaded.confirmed
    assert not loaded.noun, "not even the name of somebody else's body"


# ------------------------------------------------------------ the mechanism

def test_the_owner_keeps_the_original_locations() -> None:
    """Nothing moves, so nothing is lost in the moving."""
    with as_agency(OWNER):
        assert versions._file() == versions.VERSIONS_FILE
        assert decider._file() == decider.DECIDER_FILE
        assert framework.adoption_file() == framework.ADOPTION_FILE


def test_an_unknown_agency_is_scoped_rather_than_given_the_default() -> None:
    """Fail closed: an agency code nobody recognizes gets its own empty
    directory, not the corpus owner's files."""
    with as_agency("somewhere.else"):
        assert versions._file() != versions.VERSIONS_FILE
        assert framework.status().document_count == 0


def test_the_tenant_does_not_survive_the_request() -> None:
    token = tenant.set_current(OTHER)
    assert tenant.current() == OTHER
    tenant.reset(token)
    assert tenant.current() == ""
    assert tenant.owns_corpus(), "back to the single-tenant default"


# -------------------------------------------------- the agency's own uploads

def test_uploaded_policies_are_not_shared() -> None:
    """An agency uploads its existing policies precisely because they are not
    public. They were landing in one shared directory, so another agency could
    list them — and their passages were offered as evidence when anybody
    answered a framework question."""
    from app import intake
    with as_agency(OTHER):
        other_store = intake._store()
    with as_agency(OWNER):
        owner_store = intake._store()
    assert other_store != owner_store


def test_an_uploaded_document_is_invisible_to_another_agency(tmp_path,
                                                             monkeypatch) -> None:
    from app import intake
    monkeypatch.setattr(intake, "STORE", tmp_path / "intake")
    monkeypatch.setattr(intake, "INDEX", tmp_path / "intake" / "index.json")

    with as_agency(OTHER):
        intake._save({"documents": [{"file": "iia-acceptable-use.docx",
                                     "title": "IIA Acceptable Use"}]})
        assert len(intake._load()["documents"]) == 1

    with as_agency(OWNER):
        assert intake._load()["documents"] == [], \
            "IIA's own policy was listed for SCDES"


def test_a_caller_we_cannot_identify_sees_nothing() -> None:
    """Fail closed.

    The first version of this treated "no agency resolved" the same as "no
    tenant bound", and no-tenant means the CLI, which may read the corpus. So
    anybody signed out — or mid-registration, or using an address no container
    knows — was shown SCDES's papers. Same reported bug, different cause.
    """
    with as_agency(tenant.ANONYMOUS):
        assert not tenant.owns_corpus()
        assert framework.status().document_count == 0
        assert decider.load().shape == decider.UNSET
        assert versions._file() != versions.VERSIONS_FILE


def test_an_agency_must_be_one_the_platform_knows() -> None:
    """Found by walking a new agency through for the first time.

    `check_identity` treats an unrecognized agency id as an agency with no
    recorded convention and lets it through on the domain alone — right for a
    real agency missing from the convention table. But nothing checked that the
    id named an agency at all, so a typo (`sc.scde` for `sc.ed`) opened a real
    container for something that does not exist. It then resolved to no name,
    so the framework it exported had no agency on its title page and no route
    to acquire one — and it occupied an id a real registration would collide
    with.
    """
    from app import states, tenancy as t
    assert "sc.ed" in states.agency_ids(), "the real one"
    assert "sc.scde" not in states.agency_ids(), "the typo"

    refused = t.start_registration(
        agency="sc.scde", name="Jordan Doe", title="CIO",
        email="jdoe@ed.sc.gov", phone="(803) 734 8500", attested=True)
    assert not refused["ok"]
    assert "sc.scde" in refused["error"]


def test_the_agency_list_covers_every_jurisdiction() -> None:
    """The guard above is only as good as what it checks against."""
    from app import states
    ids = states.agency_ids()
    assert "sc.des" in ids, "the corpus owner"
    assert any(i.startswith("fed.") for i in ids), "the federal estate"
    assert len(ids) > 400, f"only {len(ids)} — a jurisdiction is missing"


def test_the_owner_sees_its_own_room_and_nobody_else_does() -> None:
    """The owner half of tools/check_agency_isolation.js. The browser walk
    cannot prove membership of the owner organization — it has no session
    code — so it checks only that nobody unproven sees the room. That the
    owner is not over-blocked is proven here, where the tenant is bound."""
    from app import server
    who = Actor("owner.ot", "", Role.OT)
    with as_agency(OWNER):
        assert server.api_profile(who, {}, {}).get("available") is not False
    for code in (OTHER, tenant.ANONYMOUS):
        with as_agency(code):
            assert server.api_profile(who, {}, {}).get("available") is False


def test_being_unidentified_is_not_the_same_as_being_a_tool() -> None:
    """The distinction the safety property rests on."""
    assert tenant.owns_corpus(), "no tenant bound: a CLI, and allowed"
    with as_agency(tenant.ANONYMOUS):
        assert not tenant.owns_corpus(), "a browser we cannot name: refused"


# ------------------------------- the checks write somewhere nobody is working

def test_the_harness_has_a_container_of_its_own() -> None:
    """The browser walks blank answers to make themselves deterministic, and
    for a while they did that in the shared test container — which is where the
    client was doing his real work. Five of his answers were blanked and nine
    overwritten, and the audit log could not say what had been there because it
    records the question and the actor but not the value.

    A shared test container cannot be both the place people try the product and
    the place an unattended destructive script runs. So the scripts have their
    own, and `tools/harness_identity.py` refuses to run anywhere else.
    """
    from app import states, tenancy
    assert tenancy.is_harness_container("gaius.harness")
    assert "gaius.harness" in states.agency_ids(), "registerable"


def test_nobody_can_pick_the_harness_container_from_the_dropdown() -> None:
    """Registerable is not the same as offered. A person choosing their agency
    must never be able to land in the scratch space."""
    from app import states
    for code in list(states.STATE_NAMES) + [states.FEDERAL_CODE]:
        offered = [a.get("id") for a in states.agencies_for(code)]
        assert "gaius.harness" not in offered, code


def test_a_real_container_is_never_marked_safe_to_overwrite() -> None:
    """The one property the guard rests on. `iia.test` is shared and for
    testing — and it still holds work somebody would miss."""
    from app import tenancy
    for agency in ("sc.des", "sc.ed", "iia.test"):
        assert not tenancy.is_harness_container(agency), agency


# ------------------------------------------------- every choice is on the log

def test_an_answer_is_recorded_with_what_it_replaced(tmp_path,
                                                     monkeypatch) -> None:
    """The client, in capitals: "WE NEED TO LOG ALL CHOICES, ACTIVITIES, and
    Framework versions on the back end."

    This wrote nothing. The register Module One replaced logged the question
    and the person but never the answer; Module One's own path logged neither.
    So the log could say somebody answered 1.1 and not what they said — and
    when a harness overwrote a client's answers there was nothing to restore
    them from.
    """
    from app import audit, versions
    from app.authz import Actor, Role, _default_log
    import app.authz as authz

    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    log = audit.JsonlAuditLog(tmp_path / "log.jsonl")
    monkeypatch.setattr(authz, "_default_log", log)

    who = Actor("sean.ot", "Sam Doe", Role.OT, title="CTO")
    versions.answer("org.kind", "district", who)
    versions.answer("org.kind", "county", who)

    written = [e for e in log.entries()
               if e.action == "answer_framework_question"]
    assert len(written) == 2, "one line per choice"
    assert written[0].detail["value"] == "district"
    assert written[0].detail["was"] is None, "nothing was there before"
    assert written[1].detail["value"] == "county"
    assert written[1].detail["was"] == "district", "and what it replaced"
    assert written[1].detail["actor_name"] == "Sam Doe"


def test_a_long_answer_is_bounded_but_still_recorded(tmp_path,
                                                     monkeypatch) -> None:
    """A pasted policy must not make the log unreadable, and must not vanish
    from it either."""
    from app import audit, versions
    from app.authz import Actor, Role
    import app.authz as authz

    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    log = audit.JsonlAuditLog(tmp_path / "log.jsonl")
    monkeypatch.setattr(authz, "_default_log", log)

    huge = "x" * 9000
    versions.answer("org.unusual", huge,
                    Actor("sean.ot", "Sam Doe", Role.OT, title="CTO"))
    held = [e for e in log.entries()
            if e.action == "answer_framework_question"][0]
    assert len(held.detail["value"]) < 4200
    assert "9000 characters" in held.detail["value"]


def test_the_log_never_stops_somebody_answering(tmp_path,
                                                monkeypatch) -> None:
    """The log records what happened; it does not gate it. A disk problem in
    the audit directory must not stop a public official saving their work."""
    from app import versions
    from app.authz import Actor, Role
    import app.authz as authz

    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")

    class Broken:
        def append(self, **kwargs):
            raise OSError("the disk is full")

    monkeypatch.setattr(authz, "_default_log", Broken())
    out = versions.answer("org.kind", "city",
                          Actor("sean.ot", "Sam Doe", Role.OT, title="CTO"))
    assert out["ok"] is True
    assert versions.working()["org.kind"]["value"] == "city"


# ----------------------------------- nobody else's name, including in the tab

def test_the_page_title_names_no_agency() -> None:
    """The browser tab said "SCDES AI Governance".

    Found by reading the access log, not by a test — every isolation check in
    this file reads the rendered body, and none of them had ever looked at the
    document title. So the one thing the client has drawn a hard line against
    was in the tab of everybody who had not signed in yet, in every bookmark
    of the landing page, and in every screenshot of it.

    `launcher.js` sets the title to the agency's own abbreviation once one is
    known; before that it must name nobody.
    """
    from pathlib import Path
    import re

    page = (Path(__file__).resolve().parent.parent
            / "app" / "web" / "index.html").read_text(encoding="utf-8")
    title = re.search(r"<title>([^<]*)</title>", page)
    assert title, "no title at all"
    for name in ("SCDES", "South Carolina", "Environmental"):
        assert name not in title.group(1), title.group(1)


def test_staging_asks_not_to_be_indexed() -> None:
    """This host answers on the public internet and serves clients' draft
    frameworks. A crawler indexing it would put somebody's unfinished policy
    into a search result — the same leak by a route nobody was watching.

    Three layers, because each covers what the others cannot: the meta tag for
    a crawler that fetches the page, robots.txt for one that checks first, and
    the header for everything that is not HTML — the exported .docx included.
    """
    from pathlib import Path

    web = Path(__file__).resolve().parent.parent / "app" / "web"
    page = (web / "index.html").read_text(encoding="utf-8")
    assert 'name="robots"' in page and "noindex" in page

    robots = (web / "robots.txt").read_text(encoding="utf-8")
    assert "Disallow: /" in robots

    from app import server
    import inspect
    assert "X-Robots-Tag" in inspect.getsource(server.Handler._send)


# ------------------------------- a reset clears the caller's own work only

def test_a_reset_clears_the_callers_own_answers() -> None:
    """The client asked for a button to erase his own content so he could demo
    from zero. It would have done neither thing it needed to.

    Every path in `reset._targets` was hardcoded to the corpus config
    directory, which is where the *reference* agency's answers live. A tenant
    clicking Start Over would have left their own answers exactly where they
    were and cleared somebody else's — failing at the one thing it was for,
    while doing real damage on the way past.
    """
    from app import reset

    with as_agency("iia.test"):
        mine = [c.path for c in reset._targets()]
    assert all("iia.test" in str(p) for p in mine), mine

    # And the corpus owner still clears the corpus, which is its own work.
    theirs = [str(c.path) for c in reset._targets()]
    assert any("corpus" in p for p in theirs)


def test_one_agencys_reset_cannot_reach_another() -> None:
    """The property that matters, stated directly rather than inferred from
    the paths above."""
    from app import reset

    with as_agency("iia.test"):
        mine = {str(c.path) for c in reset._targets()}
    with as_agency("sc.ed"):
        theirs = {str(c.path) for c in reset._targets()}
    assert not mine & theirs, "two agencies share a reset target"


def test_the_log_survives_absolutely() -> None:
    """His words, emphatically. An audit trail that can be cleared by the
    person it audits is not an audit trail."""
    from app import reset

    for agency in ("iia.test", "sc.ed", "gaius.harness"):
        with as_agency(agency):
            for target in reset._targets():
                for protected in reset.PROTECTED:
                    assert target.path != protected, agency
                    assert protected not in target.path.parents, agency


# --------------------------------- the log cannot corrupt itself under load

def test_concurrent_appends_do_not_tear_the_log(tmp_path) -> None:
    """`append` reads the head of the hash chain, computes from it, then
    writes. Split across threads that interleaves — and the server is a
    `ThreadingHTTPServer`, so two requests genuinely are concurrent.

    The observed failure was one entry's bytes written into the middle of
    another's: a file that would not parse and a chain that could not be
    verified. That is the worst place in this application for a race, because
    a log that corrupts itself under ordinary load cannot be relied on to show
    that nobody tampered with it.
    """
    import json
    import threading

    from app import audit

    log = audit.JsonlAuditLog(tmp_path / "log.jsonl")
    writers, per_writer = 8, 25

    def hammer(which: int) -> None:
        for i in range(per_writer):
            log.append(actor=f"writer-{which}", role="ot",
                       action="answer_framework_question", target="framework",
                       outcome="allowed",
                       detail={"key": f"q.{which}.{i}", "value": "x" * 60})

    threads = [threading.Thread(target=hammer, args=(w,))
               for w in range(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = [ln for ln in
             (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    assert len(lines) == writers * per_writer

    # Every line is whole.
    for line in lines:
        json.loads(line)

    # And the chain is unbroken: no duplicate sequence numbers, no gaps.
    numbers = [json.loads(ln)["seq"] for ln in lines]
    assert numbers == list(range(1, writers * per_writer + 1))
    intact, message = log.verify()
    assert intact, message


def test_two_handles_on_one_file_share_the_lock(tmp_path) -> None:
    """Handlers construct `JsonlAuditLog()` freely, so two objects routinely
    point at the same file. A lock held per instance would protect nothing."""
    from app import audit

    first = audit.JsonlAuditLog(tmp_path / "log.jsonl")
    second = audit.JsonlAuditLog(tmp_path / "log.jsonl")
    assert first._lock is second._lock

    other = audit.JsonlAuditLog(tmp_path / "elsewhere.jsonl")
    assert other._lock is not first._lock
