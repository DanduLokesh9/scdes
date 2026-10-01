"""One environmental agency per state, and what is honestly known about it.

Adding fifty states at once is mostly a data exercise, and the risk in it is
not that the code breaks. It is that a guessed email domain becomes an access
rule nobody notices: too narrow and a real deputy director is refused at the
door, too broad and the domain check stops meaning anything.

So these tests are about the honesty of the table rather than its size. Every
row says whose domain it is and whether a person checked it. Nothing claims
to be confirmed that was not confirmed by somebody outside this application.
And the one entry the client stated himself is not allowed to be overwritten
by a generated one.
"""

from __future__ import annotations

from app import states, tenancy


# --------------------------------------------------------------- the coverage

def test_every_state_and_the_district_has_an_environmental_agency() -> None:
    for code in states.STATE_NAMES:
        found = states.agencies_for(code)
        assert found, code
        assert any(a.get("domain") for a in found), code


def test_every_state_is_open_for_registration() -> None:
    for code in states.STATE_NAMES:
        assert states.is_open(code), code


def test_south_carolina_keeps_its_own_list() -> None:
    """Its units come from the client's own spreadsheet, and generating a
    149th here would give one department two ids."""
    assert "SC" not in states._ENV_DOMAINS
    sc = states.agencies_for("SC")
    assert len(sc) > 100
    assert any(a["id"] == "sc.des" for a in sc)
    assert not any(a["id"] == "sc.env" for a in sc)


def test_no_agency_id_is_used_twice() -> None:
    seen: dict[str, str] = {}
    for code in states.STATE_NAMES:
        for a in states.agencies_for(code):
            assert a["id"] not in seen or seen[a["id"]] == code, a["id"]
            seen[a["id"]] = code


def test_the_name_comes_from_the_map_not_a_second_copy() -> None:
    """The map and the registration dropdown disagreeing once already put two
    different names for one agency in front of one user."""
    for code, (name, abbrev) in states.AGENCIES.items():
        if code in states._STATED or code == "SC":
            continue
        entry = states.STATE_AGENCIES[code][0]
        assert entry["name"] == name
        assert entry["abbrev"] == abbrev


# ------------------------------------------------------- what the table admits

def test_every_row_says_whose_domain_it_is() -> None:
    for code in states._ENV_DOMAINS:
        entry = states.STATE_AGENCIES[code][0]
        assert entry["scope"] in (states.AGENCY_DOMAIN,
                                  states.STATEWIDE_DOMAIN), code


def test_every_row_says_who_vouched_for_the_domain() -> None:
    for code in states._ENV_DOMAINS:
        assert states.STATE_AGENCIES[code][0]["domain_source"] in (
            states.DOMAIN_STATED, states.DOMAIN_CHECKED,
            states.DOMAIN_UNCONFIRMED), code


def test_only_the_client_stated_entry_says_the_client_stated_it() -> None:
    """`stated` means somebody outside this application said so. Nothing
    this module worked out for itself may wear that word."""
    claimed = [code for code in states._ENV_DOMAINS
               if states.STATE_AGENCIES[code][0]["domain_source"]
               == states.DOMAIN_STATED]
    assert claimed == ["NM"]


def test_the_two_axes_stay_apart() -> None:
    """`confidence` is about the local-part rule; `domain_source` is about
    the domain. Folding them together made New Mexico read as confirmed when
    what was confirmed was the domain and not the naming rule — and the test
    written to stop exactly that drift is the one that caught it.
    """
    for code in states._ENV_DOMAINS:
        entry = states.STATE_AGENCIES[code][0]
        # No local-part rule is confirmed for any state outside South
        # Carolina, whoever vouched for the domain.
        assert entry["confidence"] == "none", code
        assert entry["domain_source"] != "none", code


def test_the_client_stated_entry_is_not_overwritten_by_a_generated_one() \
        -> None:
    nm = states.STATE_AGENCIES["NM"][0]
    assert nm == states._STATED["NM"]
    assert nm["domain"] == "env.nm.gov"
    assert nm["name"] == "New Mexico Department of the Environment"


def test_no_local_part_rule_is_guessed_for_any_state() -> None:
    """A guessed convention that refuses a real deputy director is worse than
    no rule. Nobody has confirmed one outside South Carolina."""
    for code in states._ENV_DOMAINS:
        assert states.STATE_AGENCIES[code][0]["convention"] == "any", code


def test_no_domain_is_a_bare_gov_or_a_wildcard() -> None:
    """`.gov` alone, or anything with a star in it, would admit most of the
    United States government."""
    for code in states._ENV_DOMAINS:
        domain = states.STATE_AGENCIES[code][0]["domain"]
        assert "*" not in domain and " " not in domain, code
        assert domain.count(".") >= 1, code
        assert domain not in ("gov", ".gov", "us", ".us"), code


def test_the_checked_rows_are_the_ones_that_were_checked() -> None:
    """Twelve were verified against addresses the agencies publish. The
    number is pinned so that nobody can quietly promote a guess."""
    checked = [code for code, (_, _, ok) in states._ENV_DOMAINS.items() if ok]
    assert sorted(checked) == ["CO", "KS", "LA", "MI", "ND", "NM", "PA",
                               "TX", "UT", "VT", "WA", "WV", "WY"]


# --------------------------------------------------- the confirmation report

def test_the_report_lists_everything_still_owed() -> None:
    owed = states.needs_confirming()
    assert len(owed) == len(states._ENV_DOMAINS) - 1     # all but New Mexico
    assert not any(a["domain_source"] == states.DOMAIN_STATED for a in owed)


def test_the_report_puts_the_weakest_rows_first() -> None:
    """An unchecked statewide domain admits a whole state government and no
    person has looked at it, so it is the thing to do something about."""
    first = states.needs_confirming()[0]
    assert first["domain_source"] == states.DOMAIN_UNCONFIRMED
    assert first["scope"] == states.STATEWIDE_DOMAIN


# ------------------------------------------------- what registration will do

def test_every_agency_reaches_the_registration_table() -> None:
    """Being in the dropdown and not in this table is the failure mode worth
    a test: the agency would be offered, and then refused at the door with no
    rule to check against."""
    for code in states.STATE_NAMES:
        for a in states.agencies_for(code):
            if not a.get("domain"):
                continue
            assert a["id"] in tenancy.KNOWN, a["id"]


def test_the_registration_table_carries_the_domain_and_the_scope() -> None:
    for code in states._ENV_DOMAINS:
        entry = states.STATE_AGENCIES[code][0]
        known = tenancy.KNOWN[entry["id"]]
        assert known["domains"] == [entry["domain"]]
        assert known["state"] == code
        assert known["scope"] == entry["scope"], code


def test_every_entry_says_where_its_rule_came_from() -> None:
    """The test that stops a guess from entering the table silently."""
    for code in states._ENV_DOMAINS:
        entry = states.STATE_AGENCIES[code][0]
        source = tenancy.KNOWN[entry["id"]]["source"]
        assert source and len(source) > 30, code


def test_an_unconfirmed_domain_says_so_to_whoever_approves() -> None:
    unchecked = next(code for code, (_, _, ok) in states._ENV_DOMAINS.items()
                     if not ok)
    source = tenancy.KNOWN[states.STATE_AGENCIES[unchecked][0]["id"]]["source"]
    assert "nobody has confirmed it" in source
    assert "Approve on the person, not on the address" in source


def test_a_checked_domain_says_what_was_and_was_not_checked() -> None:
    source = tenancy.KNOWN["tx.env"]["source"]
    assert "verified against addresses the agency itself publishes" in source
    assert "the local part is not" in source


def test_a_statewide_domain_tells_the_approver_it_proves_less() -> None:
    """Texas has the agency's own domain; Pennsylvania shares the state's.
    A reviewer looking at the second is doing all of the work themselves."""
    said = "belongs to the whole state government"
    assert said in tenancy.KNOWN["pa.env"]["source"]
    assert said not in tenancy.KNOWN["tx.env"]["source"]


def test_no_state_agency_became_a_shared_test_container() -> None:
    """Opening fifty states at once is exactly the change that could turn a
    real governmental unit into a space anybody can walk into. Every one of
    them is a real container, and none is shared or a harness."""
    for code in states._ENV_DOMAINS:
        agency_id = states.STATE_AGENCIES[code][0]["id"]
        assert not tenancy.is_shared_test_container(agency_id), code
        assert not tenancy.is_harness_container(agency_id), code


def test_nobody_skips_approval_on_an_unconfirmed_domain() -> None:
    """The domain check is not the gate. It narrows the queue and a person
    clears it, which is what makes an unconfirmed domain survivable.

    Only an address on IIA's own test domain may skip the queue, and
    `is_tester` decides that on the address rather than on the container —
    so no state entry can grant it by being edited.
    """
    for code in list(states._ENV_DOMAINS)[:8]:
        domain = states.STATE_AGENCIES[code][0]["domain"]
        assert not tenancy.is_tester(f"director@{domain}"), code
