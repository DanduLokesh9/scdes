"""Local web server for the SCDES AI Governance app.

Standard-library HTTP only — no framework, no network dependency, so the whole
application runs offline. Serves the single-page UI and a small JSON API.

Run:  python -m app.server        then open http://127.0.0.1:8765
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import json
import mimetypes
import os
import traceback
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from app import (admin, agent, budget as budget_mod, config as config_mod,
                 council, mode as mode_mod, oversight, registry, retrieval,
                 scoring, spine, tenancy, tenant, vision)
from app.authz import Actor, Role, guard, Target
from app.audit import JsonlAuditLog
from app.provider import describe_provider, get_provider

WEB_DIR = Path(__file__).resolve().parent / "web"
#: Local by default — this is a reference build and binding to every interface
#: would expose an application with no authentication. A host that assigns a port
#: sets PORT, and needs 0.0.0.0 to route to the container, so both are read from
#: the environment when present.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))

#: The three levels of authority the framework establishes, and what each may do.
#:
#: These are *capacities*, not people. An earlier version shipped three invented
#: staff — "Liz Alvarez", "Sean Whitaker" — and offered them as a sign-in list.
#: That was wrong for a record intended to be relied on: it put a fabricated name
#: into every audit entry, and it invited someone to click a stranger's name and
#: act as them. The person signing in now supplies their own name and title, and
#: chooses only the capacity they hold.
#:
#: The ids are unchanged because seeded project ownership refers to them.
#: Production swaps all of this for the agency's own single sign-on.
ROSTER = {
    "liz.operator": Actor("liz.operator", "Operator", Role.OPERATOR,
                          bureau="Water"),
    "sean.ot": Actor("sean.ot", "Office of Technology", Role.OT),
    "council.cto": Actor("council.cto", "Council member", Role.COUNCIL),
}
DEFAULT_USER = "liz.operator"

#: What the sign-in screen offers: a capacity, plainly described. No names.
CAPACITIES = [
    {"id": "liz.operator", "label": "Operator",
     "does": "Submits and runs projects"},
    {"id": "sean.ot", "label": "Office of Technology",
     "does": "Owns the configuration and the risk model"},
    {"id": "council.cto", "label": "Council member",
     "does": "Approves gated decisions"},
]


def capacities() -> list[dict[str, str]]:
    """The sign-in capacities, with the deciding one named as this agency named
    it. "Council member" is a label, not a role — the role is "holds the
    decision", and an agency that appointed a single officer should see that
    officer's title in the picker."""
    from app import decider
    out = []
    for c in CAPACITIES:
        if c["id"] == "council.cto":
            out.append({**c, "label": decider.capacity_label(),
                        "does": f"Decides gated matters as {decider.body()}"})
        else:
            out.append(dict(c))
    return out

#: A supplied name is free text from an unauthenticated screen, so it is bounded
#: and stripped of control characters before it reaches the audit log.
_NAME_LIMIT = 80


def _clean(value: str | None) -> str:
    text = "".join(ch for ch in (value or "") if ch.isprintable())
    return text.strip()[:_NAME_LIMIT]


def actor_for(params: dict[str, list[str]], headers: Any) -> Actor:
    """The capacity being acted in, carrying the person's own name and title.

    The capacity decides what is permitted; the name and title decide what the
    audit trail records. Keeping them separate is the point: someone may not
    promote themselves to the Council by typing a grander title.
    """
    user = (params.get("user", [None])[0]
            or headers.get("X-SCDES-User")
            or DEFAULT_USER)
    actor = ROSTER.get(user, ROSTER[DEFAULT_USER])

    name = _clean(params.get("name", [None])[0] or headers.get("X-SCDES-Name"))
    title = _clean(params.get("title", [None])[0] or headers.get("X-SCDES-Title"))
    # Resolved here rather than per-handler so there is one place that decides
    # what a request has proved, in the same spirit as guard() being the one
    # place that decides what it may write.
    proven = session_email(params, headers)
    if not name and not title:
        return replace(actor, email=proven) if proven else actor
    # Fall back to the capacity label rather than inventing a person.
    return replace(actor, name=name or actor.name, title=title, email=proven)


# ------------------------------------------------------------------- handlers

def _tester_email(params: dict, headers: Any) -> str:
    """The signed-in address, if the browser told us. Used only for the tester
    bypass — everything else keys off the capacity, not the address."""
    return (params.get("email", [None])[0]
            or (headers.get("X-SCDES-Email") if headers else None) or "")


def session_email(params: dict, headers: Any) -> str:
    """The address this request has actually *proved*, or "".

    `_tester_email` above returns whatever the browser typed in the query
    string, which is the right amount of trust for choosing what to render and
    the wrong amount for anything that crosses an agency boundary. This resolves
    the token tenancy issued when a verification code was read out of a real
    mailbox, so it cannot be set by editing a URL.
    """
    token = (params.get("session", [None])[0]
             or (headers.get("X-GAIUS-Session") if headers else None) or "")
    return tenancy.session_email(token)


def _subscribed() -> bool:
    """Whether the agency on this request may open the paid modules.

    This was one switch for the whole deployment, which was right while
    nothing could be sold and wrong the moment anything could: it meant
    turning the paid modules on for one agency turned them on for every
    agency sharing the server. Entitlement is now per agency, recorded in
    `app/billing.py` against a paid order.

    The environment flag survives as a deliberate override, because staging
    has to be able to demonstrate the paid modules without an invoice being
    raised against a fictional county. It is named in the payments document
    as something that must not be set on a deployment serving real
    customers.
    """
    import os
    if os.getenv("IIA_SUBSCRIPTION", "").strip() in ("1", "true", "yes"):
        return True
    try:
        from app import billing, tenant
        return billing.entitled(tenant.current())
    except Exception:                                     # noqa: BLE001
        # Fails closed. An error reading the billing file must not hand out
        # the paid modules.
        return False


def _own_organization() -> dict[str, str]:
    here = tenant.current()
    if not here or here == tenant.ANONYMOUS:
        return {"code": "", "label": ""}
    try:
        label = tenancy._agency_names(here).get("agency_label") or ""
    except Exception:                                         # noqa: BLE001
        label = ""
    return {"code": here, "label": label}


def _session_expires() -> str:
    try:
        from app import impersonate
        return tenancy.session_expires(impersonate.session())
    except Exception:                                         # noqa: BLE001
        return ""


def api_session_renew(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """"Stay signed in." Reaching here at all renews the session (see
    tenancy.session_email); this reports the new end."""
    return {"ok": bool(actor.email), "session_expires": _session_expires()}


def _tour_seen(email: str) -> bool:
    try:
        from app import firstuse
        return firstuse.tour_seen(email)
    except Exception:                                         # noqa: BLE001
        return False


def _impersonating() -> dict[str, Any] | None:
    from app import impersonate
    return impersonate.public(impersonate.current())


def api_state(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import decider as decider_mod, tenant, vocabulary
    provider = get_provider()
    # This organisation's own trail. The shared back-end copy is never read
    # on anybody's behalf.
    from app.audit import OrganisationLog
    log = OrganisationLog()
    ok, message = log.verify()
    # Counts of somebody else's documents are still somebody else's. The
    # topbar chip read "Integrity 13 · 3 to fix" for every tenant on the
    # deployment, which is both a fact about the reference agency's corpus and
    # an invitation to open the room that lists them by name.
    #
    # The chip now reads this organisation's own Integrity register — its
    # checks and incidents, and the findings they raise against its own
    # framework — which is scoped to the caller like every other record.
    try:
        integrity_summary = _integrity_badge()
    except Exception:                                   # never block the shell
        integrity_summary = {"entries": 0, "to_fix": 0, "badge": "Integrity"}
    return {
        "vocabulary": vocabulary.as_display_map(),
        "integrity": integrity_summary,
        "mode": mode_mod.current().value,
        "mode_label": mode_mod.current().label,
        "actor": {"id": actor.user_id, "name": actor.name,
                  "title": actor.title, "role": actor.role.value},
        # Whether to draw the Admin section at all. The rail reads this, but it
        # is not what enforces anything — every admin endpoint checks the same
        # proven address for itself, because a hidden menu item is decoration
        # and this one guards other agencies' reports.
        "admin": admin.is_admin(actor.email),
        # Set only while a GAIUS admin is viewing as somebody. The screen
        # draws the "Viewing as … — End impersonation" bar from it.
        "impersonating": _impersonating(),
        # Whether this person has had the guided tour (app/firstuse.py), so it
        # is shown on first use only, whichever browser they use.
        "tour_seen": _tour_seen(actor.email),
        # When this sign-in ends, renewals included — the screen warns before
        # it does. Empty when nothing is proved.
        "session_expires": _session_expires(),
        # The organization this request is actually served from — the one
        # the signed-in address belongs to. The shell compares it with the
        # agency picked on the map and says so where they differ. Only the
        # caller's own, so it names nobody else.
        "organization": _own_organization(),
        # Capacities, not people. The sign-in screen asks for the name.
        "capacities": capacities(),
        "roster": [{"id": a.user_id, "name": a.name, "role": a.role.value}
                   for a in ROSTER.values()],
        "portfolio": registry.portfolio_summary(),
        "provider": {"name": provider.name, "offline": provider.offline,
                     "description": describe_provider(provider)},
        "audit": {"entries": len(log.entries()), "intact": ok, "message": message},
        # Seeded from the reference agency's own incidents, which cite its
        # Operations Manual by section — so it is theirs or it is nothing.
        # This appears on the home screen of every tenant, which is how a
        # stranger's first screen came to cite "SCDES AI Operations Manual
        # §22.4".
        "oversight": (oversight.status() if tenant.owns_corpus()
                      else {"active_incidents": 0, "highest_level": 0,
                            "standby": False, "monitored_systems": 0,
                            "incidents": [], "available": False}),
        "council_open": len(council.proposals()) if tenant.owns_corpus() else 0,
        # The framework is the free offering. Everything downstream — the
        # playbook, the appendices, workflow management — is a paid addition,
        # and no amount of finishing the framework turns it on. A single switch
        # so a demo or a paying agency can be opened without a code change.
        "subscription": _subscribed(),
        # The shell paints the rail from this, so the room is named correctly on
        # the very first frame rather than flickering from "Council" to whatever
        # the agency actually chose.
        "decider": decider_mod.state(),
        "framework_version": "v1.0 · adopted 21 July 2026",
        # Surfaced so the interface can both unlock the gates and show a badge.
        # A bypassed session that looks identical to a real one is a trap.
        "tester": _is_tester_request(params),
    }


def _is_tester_request(params: dict) -> bool:
    from app import tenancy
    return tenancy.is_tester(params.get("email", [""])[0])


def api_chat(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    result = agent.chat(body.get("message", ""), prefer=body.get("provider"))
    return result.as_dict()


def api_vision(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    return vision.overview()


def api_registry(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    projects = registry.load_all()
    rows = []
    for p in projects:
        risk = p.risk()
        rows.append({
            **p.as_dict(),
            "risk": risk.as_dict(),
            "gate_label": p.gate_label,
            "council_required": risk.council_required,
            "cadence": scoring.review_cadence(risk.band),
        })
    return {"projects": rows, "summary": registry.portfolio_summary(projects),
            "calibration": registry.calibration_report(projects)}


def api_catalog(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Registry — the catalog of tools, what each does, and who here has it.

    Replaces the reference agency's systems register, which carried its
    appendix scores and risk bands. The list of what this organization runs
    is Projects; this is the catalog somebody searches first.
    """
    from app import catalog, holdings, projects, vendors
    try:
        held = holdings.listing().get("holdings", [])
    except Exception:                                         # noqa: BLE001
        held = []
    try:
        suppliers = vendors.listing().get("vendors", [])
    except Exception:                                         # noqa: BLE001
        suppliers = []
    return catalog.surface(
        answers=_framework_answers(), projects=projects.all_projects(),
        vendors_rows=suppliers, holdings=held,
        terms=str(params.get("q", [""])[0])[:200],
        unit=str(params.get("unit", [""])[0])[:200])


def api_catalog_save(actor: Actor, body: dict, params: dict
                     ) -> dict[str, Any]:
    """Add a tool, or change one. Open to every hat."""
    from app import catalog
    fields = {k: body[k] for k in catalog.EDITABLE if k in body}
    for key in ("name", "does", "supplier", "vendor", "standing",
                "involvement", "could_also"):
        if key in fields:
            fields[key] = str(fields[key] or "")[:4000]
    for key in ("availability", "needs_holdings", "projects"):
        if key in fields:
            fields[key] = [str(x)[:60] for x in (fields[key] or [])][:60]
    if "held_by" in fields and not isinstance(fields["held_by"], list):
        fields["held_by"] = []
    ref = str(body.get("ref") or "")
    if not ref:
        made = catalog.add(str(fields.pop("name", "")), actor)
        if not made.get("ok"):
            return made
        ref = made["tool"]["ref"]
    return catalog.update(ref, actor, **fields)


def api_catalog_seed(actor: Actor, body: dict, params: dict
                     ) -> dict[str, Any]:
    from app import catalog
    return catalog.seed(catalog.framework_inputs(_framework_answers()), actor)


def api_costs(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Budget — what a tool costs, all in, including what it would cost to
    leave. Replaces the reference agency's budget pools."""
    from app import costs, projects, vendors
    try:
        suppliers = vendors.listing().get("vendors", [])
    except Exception:                                         # noqa: BLE001
        suppliers = []
    for v in suppliers:
        try:
            v["a_year"] = vendors.a_year(vendors._row(v)) or None
        except Exception:                                     # noqa: BLE001
            v["a_year"] = None
    return {**costs.surface(answers=_framework_answers(),
                            projects=projects.all_projects(),
                            vendors_rows=suppliers),
            "hat": actor.role.value,
            "may_set_difference": actor.role == Role.COUNCIL}


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def api_cost_save(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Record a cost line, or change one not yet committed. Open to every
    hat: restricting who may write a number down produces organizations
    where the numbers are not written down."""
    from app import costs
    def text(key: str, n: int = 4000) -> str:
        return str(body.get(key) or "").strip()[:n]
    extra = {k: text(k) for k in costs.LINE_FIELDS
             if k not in ("estimate_unsure", "actual_unsure", "field_gaps")
             and k in body}
    for key in ("estimate_unsure", "actual_unsure"):
        if key in body:
            extra[key] = bool(body.get(key))
    for choice, allowed in (("whose_money", costs.WHOSE_MONEY),
                            ("estimate_when", costs.ESTIMATE_WHEN),
                            ("included_or_extra", costs.INCLUDED),
                            ("ends_how", costs.ENDS_HOW)):
        if extra.get(choice) and extra[choice] not in allowed:
            extra[choice] = ""
    estimate, actual = _number(body.get("estimate")), _number(body.get("actual"))
    for key, raw, got in (("estimate", body.get("estimate"), estimate),
                          ("actual", body.get("actual"), actual)):
        if raw not in (None, "") and got is None:
            return {"ok": False, "field": key,
                    "error": "That could not be read as a number. What you "
                             "typed is still in the box."}
    ref = text("ref", 20)
    if ref:
        fields = {**extra, "estimate": estimate, "actual": actual,
                  "basis": text("basis", 30), "owner": text("owner", 200),
                  "note": text("note"), "version": text("version", 60),
                  "headcount": int(_number(body.get("headcount")) or 0),
                  "hours_a_year": _number(body.get("hours_a_year")) or 0.0,
                  "hours_one_off": _number(body.get("hours_one_off")) or 0.0}
        if body.get("kind") in costs.KINDS:
            fields["kind"] = body["kind"]
        return costs.edit(ref, actor, **fields)
    if not extra.get("what_for"):
        return {"ok": False, "field": "what_for",
                "error": "Say what this cost is for, in one line."}
    projects_ = [str(p)[:40] for p in (body.get("projects") or [])][:20]
    return costs.add(
        kind=text("kind", 30) if body.get("kind") in costs.KINDS else "",
        actor=actor, projects=projects_,
        not_one_project=bool(body.get("not_one_project")),
        basis=text("basis", 30), estimate=estimate, actual=actual,
        hours_a_year=_number(body.get("hours_a_year")) or 0.0,
        hours_one_off=_number(body.get("hours_one_off")) or 0.0,
        headcount=int(_number(body.get("headcount")) or 0),
        owner=text("owner", 200), version=text("version", 60),
        note=text("note"), extra=extra)


def _user_may_commit(actor: Actor, line: dict[str, Any],
                     inputs: dict[str, Any]) -> str:
    """Empty where this hat may commit this line; otherwise the one line of
    consequence. The User's power is the organization's own delegation answer
    and nothing more; the technology hat commits no money at all."""
    from app import costs, module_one, projects
    if actor.role == Role.COUNCIL:
        return ""
    if actor.role == Role.OT:
        return ("The technology hat commits no money. Whoever decides, or a "
                "User within your delegation, commits a line.")
    answers = _framework_answers()
    without = module_one.value_of(answers, "who.without")[0] or []
    without = without if isinstance(without, list) else [without]
    if not without or "nothing" in without:
        return ("You said nothing moves without whoever decides, so "
                "committing money is for them.")
    if line.get("basis") == costs.NO_CHARGE and "free" in without:
        return ""
    amount = inputs.get("delegation_amount")
    if amount is not None:
        project = line.get("project") or ""
        committed = [l for l in costs.open_lines()
                     if l.get("committed") and project and
                     project in (l.get("projects") or [])] + [line]
        got = costs.totals(committed)
        total = got["a_year"] + got["one_off"]
        if total < amount:
            return ""
        return (f"This takes the total on this project to ${total:,.0f}. You "
                f"said anything under ${amount:,.0f} moves without whoever "
                f"decides, so committing this is for them.")
    if "lowest_risk" in without:
        levels = _their_levels()
        held = projects.one(line.get("project") or "") or {}
        if levels and held.get("level") == levels[0]:
            return ""
    return ("This is outside what you said can move without whoever decides, "
            "so committing it is for them.")


def api_cost_commit(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import costs
    ref = str(body.get("ref", ""))
    line = next((l for l in costs.all_lines() if l.get("ref") == ref), None)
    if not line:
        return {"ok": False, "error": "No such line."}
    refused = _user_may_commit(
        actor, line, costs.framework_inputs(_framework_answers()))
    if refused:
        return {"ok": False, "error": refused}
    return costs.commit(ref, actor)


def api_cost_status(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Ended is open to every hat, because an end date is a fact. Withdrawn
    is the decision-maker's for any line, and a person's own for a line they
    recorded and nobody has committed."""
    from app import costs
    ref, status = str(body.get("ref", "")), str(body.get("status", ""))
    line = next((l for l in costs.all_lines() if l.get("ref") == ref), None)
    if not line:
        return {"ok": False, "error": "No such line."}
    if status == costs.WITHDRAWN and actor.role != Role.COUNCIL:
        mine = line.get("recorded_by") == actor.name
        if line.get("committed") or not mine:
            return {"ok": False,
                    "error": "You can withdraw lines you recorded before they "
                             "are committed. Whoever decides can withdraw any "
                             "line."}
    return costs.set_line_status(ref, status, actor)


def api_cost_gap(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import costs
    return costs.record_kind_gap(
        str(body.get("project", ""))[:40], str(body.get("kind", "")), actor,
        owner=str(body.get("owner", ""))[:200], by=str(body.get("by", ""))[:10],
        outside=str(body.get("outside", ""))[:300])


def api_cost_difference(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import costs
    if actor.role != Role.COUNCIL:
        return {"ok": False, "error": "Whoever decides sets this."}
    return costs.set_difference(str(body.get("mode", "")),
                                _number(body.get("value")), actor)


def _vision_inputs() -> dict[str, Any]:
    from app import module_one as m
    answers = _framework_answers()

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    def listed(key: str) -> list[str]:
        got = value(key) or []
        return got if isinstance(got, list) else [got]

    optional = listed("floor.optional")
    publish = listed("watch.publish")
    q_pub = m.by_key("watch.publish")
    labels = {o.value: o.label for o in (q_pub.options if q_pub else [])}
    failing = value("watch.failing")
    q_fail = m.by_key("watch.failing")
    fail_words = next((o.label for o in (q_fail.options if q_fail else [])
                       if o.value == failing), "")
    kind = value("org.kind")
    q_kind = m.by_key("org.kind")
    kind_label = next((o.label for o in (q_kind.options if q_kind else [])
                       if o.value == kind), "")
    functions = value("org.functions")
    functions = functions if isinstance(functions, dict) else {}
    seats = value("who.seats") or []
    return {
        "mission_tie": "mission" in optional,
        "value_or_retire": "value" in optional,
        "not_delivering": fail_words[:1].lower() + fail_words[1:]
        if fail_words else "",
        "publishes_yearly": "annual_report" in publish,
        "publishes_words": ", ".join(labels.get(p, p) for p in publish
                                     if p != "nothing"),
        "publishes_nothing": publish == ["nothing"],
        "organisation_type": kind_label,
        "small": value("org.size") == "u25",
        "owners": [o.label for o in m.FUNCTIONS
                   if functions.get(o.value) not in (None, "", "none")]
        + [str(r.get("role") or "").strip() for r in seats
           if isinstance(r, dict) and str(r.get("role") or "").strip()],
        "no_comms": functions.get("comms") == "none",
        # 11.1a and 11.1b — what AI should help achieve. Vision is pre-filled
        # from them (BUG-BE30FBD3).
        "vision_year": str(value("why.vision_year") or ""),
        "vision_five": str(value("why.vision_five") or ""),
    }


def api_goals(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Vision — where the organization is trying to get to. One entry per
    goal. Replaces the reference agency's strategic map and pillars."""
    from app import goals, projects
    inputs = _vision_inputs()
    rows = projects.all_projects()
    found = goals.report(projects=rows,
                         organisation_type=inputs["organisation_type"],
                         mission_tie=inputs["mission_tie"],
                         value_or_retire="yes" if inputs["value_or_retire"]
                         else "",
                         publishes_yearly=inputs["publishes_yearly"])
    for f in found["raised"]:
        if f["id"] == "finding.vs.outcome_missed_no_decision" and \
                inputs["not_delivering"]:
            f["says"] = f["says"].replace("what happens next",
                                          inputs["not_delivering"])
    return {**found, "inputs": inputs,
            "proposals": goals.proposals(),
            "projects": [{"ref": p["ref"], "name": p.get("name", ""),
                          "goal": p.get("goal", ""), "gate": p.get("gate", ""),
                          "state": p.get("state", "")} for p in rows],
            "decides": actor.role == Role.COUNCIL,
            "from_framework": goals.from_framework(inputs["vision_year"],
                                                   inputs["vision_five"]),
            "from_framework_says": goals.FROM_YOUR_FRAMEWORK,
            "read_from_document": goals.READ_FROM_YOUR_DOCUMENT}


def api_goal_save(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Anybody may write a goal and say what would have to be true. The
    wording, horizon and whether it is closed are whoever decides' to
    change; anyone else's change to those is recorded as a proposal."""
    from app import goals
    ref = str(body.get("ref") or "")
    def text(key: str, n: int = 2000) -> str:
        return str(body.get(key) or "").strip()[:n]
    if not ref:
        horizon = text("horizon", 40)
        return goals.write(goal=text("goal", 300), actor=actor,
                           horizon=horizon if horizon in goals.HORIZONS
                           else goals.NO_DATE,
                           would_be_true=text("would_be_true"),
                           owner=text("owner", 200),
                           responsibilities=text("responsibilities"),
                           owner_is_also_decider=bool(
                               body.get("owner_is_also_decider")))
    out = goals.update(ref, actor=actor,
                       would_be_true=body.get("would_be_true"),
                       owner=body.get("owner"),
                       responsibilities=body.get("responsibilities"))
    if not out.get("ok"):
        return out
    current = goals.goal(ref) or {}
    wording = text("goal", 300)
    horizon = text("horizon", 40)
    stands = text("stands", 40)
    changes = {k: v for k, v in (("goal", wording), ("horizon", horizon),
                                 ("stands", stands))
               if v and v != current.get(k)}
    if not changes:
        return out
    if actor.role == Role.COUNCIL:
        if "goal" in changes or "horizon" in changes:
            goals.reword(ref, actor=actor, goal=changes.get("goal", ""),
                         horizon=changes.get("horizon", ""))
        if "stands" in changes:
            goals.close(ref, actor=actor, stands=changes["stands"])
        return {"ok": True, "goal": goals.goal(ref)}
    proposed = goals.propose(ref, actor=actor, **changes)
    return {**out, **proposed}


def api_goal_settle(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import goals
    try:
        index = int(body.get("index", -1))
    except (TypeError, ValueError):
        index = -1
    return goals.settle(index, actor=actor, accept=bool(body.get("accept")))


def api_goal_public(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import goals
    return goals.set_public_view(
        actor=actor, publishes=str(body.get("publishes", "")),
        appears=[str(a) for a in (body.get("appears") or [])],
        where=str(body.get("where", ""))[:300],
        approver=str(body.get("approver", ""))[:200],
        last_published=str(body.get("last_published", ""))[:10])


def api_goal_read(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Read the organization's own vision, mission or planning document and
    offer the sentences that read like goals. The file is read and discarded
    — nothing from it is stored until a person adds a goal."""
    import base64
    import binascii
    import tempfile
    from pathlib import Path
    from app import goals, intake
    name = Path(str(body.get("filename") or "")).name
    suffix = Path(name).suffix.lower()
    if suffix not in intake.READABLE:
        return {"ok": False, "error": "Upload a Word document, PDF, text or "
                                      "Markdown file."}
    try:
        blob = base64.b64decode(str(body.get("content") or ""), validate=True)
    except (binascii.Error, ValueError):
        return {"ok": False, "error": "That upload did not arrive intact."}
    if not blob or len(blob) > intake.MAX_BYTES:
        return {"ok": False, "error": "That file is empty or too large."}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"document{suffix}"
        path.write_bytes(blob)
        try:
            paragraphs = intake._extract(path)
        except Exception:                                     # noqa: BLE001
            paragraphs = []
    if not paragraphs:
        return {"ok": False, "error": "Nothing readable came out of that "
                                      "file. A scanned page has no text to "
                                      "read; a Word or text copy will."}
    found = goals.candidates(paragraphs)
    return {"ok": True, "candidates": found,
            "says": goals.READ_FROM_YOUR_DOCUMENT if found else
            "Nothing in that document read like a goal. You can still write "
            "them in yourself."}


def api_project_goal(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import projects
    return projects.name_goal(str(body.get("ref", "")),
                              str(body.get("goal", ""))[:40], actor)


def api_project(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    registry_id = params.get("id", [""])[0]
    project = registry.load(registry_id)
    if project is None:
        return {"error": f"unknown project {registry_id}"}
    risk = project.risk()
    return {"project": project.as_dict(), "risk": risk.as_dict()}


# The Workflow Helper was retired here, along with its two endpoints and the
# six-gate map they served.
#
# It carried a Registry entry through gates named Concept, Readiness, Pilot,
# Deployment, Scaling and Annual review, rendering them as "3. Deployment",
# and wrote the values into a copy of one agency's Appendix H workbook. It
# was built against a single organisation's adopted corpus and it did that
# job well.
#
# It cannot coexist with the lifecycle spine. The spine has seven gates with
# fixed names — Govern, Identify, Procure, Test, Deploy, Measure, Sunset —
# and says a gate is never rendered as a number "anywhere, in code or in
# copy", because a numbered gate invites a reader to line it up against
# somebody else's and import a staging scheme this platform did not write.
# "Deployment" is separately on the banned list: Deploy is a gate name and
# the only sanctioned use of that root, and everywhere else a tool goes live
# or is in use.
#
# Two screens each claiming to be the lifecycle, disagreeing about how many
# gates there are and what they are called, is worse than either alone.
#
# What replaces it: the tracker on every project screen, which shows all
# seven gates with the current position marked (app/projects.py), and the
# Lifecycle reference page. Nothing was lost — no agency had generated a
# workbook through it, checked before it was removed.


def api_config(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    keys = config_mod.tunable_keys()
    return {
        "mode": mode_mod.current().value,
        "editable_by": Role.OT.value,
        "can_edit": guard(actor, Target.CONFIG, "inspect").allowed
        if actor.is_ot else False,
        "fields": [config_mod.explain(k).as_dict() for k in keys],
        "risk_model": config_mod.risk_model(),
        "budget": config_mod.load("budget"),
        "procurement": config_mod.load("procurement"),
        "parameter_set_hash": config_mod.parameter_set_hash(),
    }


def api_config_preview(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    value = body["value"]
    try:
        value = float(value)
        if value.is_integer() and "threshold" in body["key"]:
            value = int(value)
    except (TypeError, ValueError):
        pass
    return config_mod.consequence_preview(body["key"], value).as_dict()


def api_config_edit(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    value = body["value"]
    try:
        value = float(value)
        if value.is_integer() and ("threshold" in body["key"] or "count" in body["key"]):
            value = int(value)
    except (TypeError, ValueError):
        pass
    result = config_mod.edit(body["key"], value, actor)
    return {
        "committed": result.committed,
        "allowed": result.decision.allowed,
        "reason": result.decision.reason,
        "requires_council": result.decision.requires_council,
        "key": result.key, "old_value": result.old_value,
        "new_value": result.new_value,
        "consequence": result.consequence.as_dict() if result.consequence else None,
    }


def api_budget(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    recs = budget_mod.recommendations()
    return {
        "pools": config_mod.load("budget")["pools"],
        "goal_weights": config_mod.load("budget").get("goal_weights", {}),
        "recommendations": [r.as_dict() for r in recs],
        "detail": [
            {"quote_id": r.quote.quote_id, "vendor": r.quote.vendor,
             "product": r.quote.product, "cost_type": r.quote.cost_type,
             "one_time": r.quote.one_time_cost,
             "recurring": r.quote.recurring_cost_per_year,
             "tier": r.quote.disclosure_tier,
             "pool": r.fit.pool, "headroom_after": r.fit.headroom_after,
             "over_budget": r.fit.over_budget, "rationale": r.rationale,
             "risk": r.risk.band if r.risk else "", "score": r.score}
            for r in recs
        ],
        "roadmap": vision.gap_analysis(),
    }


def api_budget_scenario(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    if body.get("preset") == "delta_bravo":
        return budget_mod.delta_bravo_scenario()
    return budget_mod.scenario(
        recurring_per_year=body.get("recurring_per_year"),
        one_time=body.get("one_time"),
        retype=body.get("retype"),
    )


def api_process(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Process — the register of standing procedures.

    This served the reference agency's appendix map and risk bands, which
    no other organization has. It now reads this organization's own
    procedures against its own framework answers.
    """
    from app import checks, procedures, projects
    found = procedures.surface(answers=_framework_answers(),
                               projects=projects.all_projects(),
                               incidents=checks.incidents())
    found["may"] = {
        "adopt": actor.role == Role.COUNCIL
        or _user_may_adopt(found["inputs"]) is not None,
        "withdraw": actor.role == Role.COUNCIL,
    }
    found["hat"] = actor.role.value
    return found


def _user_may_adopt(inputs: dict[str, Any]) -> str | None:
    """Within the delegation the organization set, and nothing more.

    Of the delegation answers only one can describe a procedure: tools in
    the lowest level of scrutiny. Amounts, free tools and short pilots are
    about buying a tool, not about adopting an instruction. So a User may
    put in force a procedure that applies only at the lowest level, where
    the organization said the lowest level moves without the decision-maker,
    and nothing else. Returns the lowest level's name, or None.
    """
    levels = inputs.get("levels") or []
    if levels and "lowest_risk" in (inputs.get("delegation") or []):
        return levels[0]
    return None


def _may_put_in_force(actor: Actor, proc: dict[str, Any],
                      inputs: dict[str, Any]) -> str:
    """Empty where this hat may; otherwise the sentence saying why not."""
    if actor.role == Role.COUNCIL:
        return ""
    if actor.role == Role.OT:
        return ("The technology hat approves nothing on its own. Whoever "
                "decides puts a procedure in force.")
    lowest = _user_may_adopt(inputs)
    if lowest and (proc.get("levels") or []) == [lowest]:
        return ""
    said = (inputs.get("readbacks") or {}).get("delegation") or \
        "You have not said what can move without the decision-maker."
    return (f"{said} Putting this in force is for whoever decides. Anyone "
            f"can write it and propose it.")


def api_procedure_save(actor: Actor, body: dict, params: dict
                       ) -> dict[str, Any]:
    """Write a new procedure, or save one. A procedure in force saves as a
    new version; nothing that already happened changes."""
    from app import procedures
    allowed = {"name", "kind", "steps", "where_it_lives", "lives_here",
               "unusual", "gates", "levels", "covers", "covered_records",
               "owner", "adopted_by", "adopted_on", "look_again",
               "look_again_date", "items", "asks", "what_happens_next",
               "words", "words_appear", "wrote_it", "approved_by",
               "approved_on", "is_current", "may_stop_it",
               "turning_off_means", "can_roll_back", "falls_back_to",
               "somewhere_to_try", "who_tries_it", "how_long",
               "when_nowhere_to_try", "records_the_version", "gaps"}
    fields = {k: v for k, v in (body or {}).items() if k in allowed}
    for key in ("gates", "levels", "covered_records", "look_again",
                "words_appear", "gaps"):
        if key in fields:
            fields[key] = [str(x)[:300] for x in (fields[key] or [])][:60]
    for key in ("items", "asks"):
        if key in fields:
            fields[key] = [{str(k)[:40]: (v if isinstance(v, bool)
                                          else str(v)[:2000])
                            for k, v in (row or {}).items()}
                           for row in (fields[key] or [])
                           if isinstance(row, dict)][:80]
    for key, value in list(fields.items()):
        if isinstance(value, str):
            fields[key] = value.strip()[:8000]
    if fields.get("kind") and fields["kind"] not in procedures.KINDS:
        fields["kind"] = procedures.SOMETHING_ELSE
    ref = str(body.get("ref") or "")
    if ref:
        out = procedures.save(ref, actor=actor, **fields)
    else:
        out = procedures.write(actor=actor, status=procedures.DRAFTED,
                               **fields)
    return out


def api_procedure_status(actor: Actor, body: dict, params: dict
                         ) -> dict[str, Any]:
    from app import procedures
    ref, status = str(body.get("ref", "")), str(body.get("status", ""))
    proc = procedures.procedure(ref)
    if not proc:
        return {"ok": False, "error": "No such procedure."}
    inputs = procedures.framework_inputs(_framework_answers())
    if status == procedures.IN_FORCE:
        refused = _may_put_in_force(actor, proc, inputs)
        if refused:
            return {"ok": False, "error": refused}
    elif actor.role != Role.COUNCIL:
        return {"ok": False, "error": "Withdrawing a procedure in force is "
                                      "for whoever decides. Anyone can "
                                      "propose it."}
    return procedures.set_status(ref, status, actor=actor,
                                 adopted_by=actor.title or actor.name)


def api_procedure_confirm(actor: Actor, body: dict, params: dict
                          ) -> dict[str, Any]:
    from app import procedures
    return procedures.confirm(str(body.get("ref", "")), actor=actor,
                              by=str(body.get("by", ""))[:200],
                              on=str(body.get("on", ""))[:10])


def api_procedure_tried(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import procedures
    return procedures.mark_tried(str(body.get("ref", "")), actor=actor,
                                 answer=str(body.get("answer", "")),
                                 on=str(body.get("on", ""))[:10])


def api_procedure_event(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import procedures
    return procedures.record_event(actor=actor,
                                   trigger=str(body.get("trigger", "")),
                                   on=str(body.get("on", ""))[:10],
                                   note=str(body.get("note", "")))


def api_procedure_move(actor: Actor, body: dict, params: dict
                       ) -> dict[str, Any]:
    """Moving records onto a new version carries the weight of putting one in
    force, so it sits with the same hats."""
    from app import procedures
    proc = procedures.procedure(str(body.get("ref", "")))
    if not proc:
        return {"ok": False, "error": "No such procedure."}
    refused = _may_put_in_force(
        actor, proc, procedures.framework_inputs(_framework_answers()))
    if refused:
        return {"ok": False, "error": refused}
    return procedures.move_records(proc["ref"], actor=actor)


def api_procedure_seed(actor: Actor, body: dict, params: dict
                       ) -> dict[str, Any]:
    """Accepting the seeding offer is open to every hat: everything it
    writes arrives Drafted, not adopted, and nothing it does puts anything
    in force."""
    from app import procedures
    if procedures.all_procedures():
        return {"ok": False, "error": "The register already has entries, so "
                                      "there is nothing to seed."}
    return procedures.seed(procedures.framework_inputs(_framework_answers()),
                           actor=actor)


def _framework_answers() -> dict[str, Any]:
    """Whatever Module One has been answered so far, or nothing.

    Wrapped because the surfaces below read it to adapt their copy, and a
    reference page must render on an organization's first morning — before
    anything has been answered — rather than erroring or waiting.
    """
    try:
        from app import versions
        return dict(versions.state().get("working") or {})
    except Exception:                                         # noqa: BLE001
        return {}


def _organisation_type() -> str:
    """Their own answer, or an empty string.

    Empty is a real answer here: every surface that reads it drops the
    clause carrying the example rather than filling it with a word this
    application chose.
    """
    try:
        from app import module_one
        value, _ = module_one.value_of(_framework_answers(), "1.1")
        return str(value or "")
    except Exception:                                         # noqa: BLE001
        return ""


def api_lifecycle(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The reference page for the seven-gate spine.

    This endpoint is a read and nothing else. `app/lifecycle.py` has no
    store behind it, and there is no POST counterpart to this route — if a
    ticket asks this page to save something, that ticket belongs to
    Projects.

    Not behind the subscription. It explains the framework the organization
    already owns, and the rail says that framework is free and stays theirs.
    """
    from app import lifecycle
    return lifecycle.page(organisation_type=_organisation_type())


def api_projects(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The project tracker — the only surface that writes a record's state.

    Deliberately not behind `_paid`. Its neighbors in the rail are, but
    what this register holds is the lifecycle the organization's own
    framework describes, and whether that is part of the subscription is a
    billing decision nobody has made yet. Gating it on an assumption would
    put a locked door in front of the one screen every other new surface
    links into.
    """
    from app import checks, costs, goals, holdings, procedures, projects
    from app import catalog, vendors
    found = projects.report()
    answers = _framework_answers()
    inputs = projects.framework_inputs(answers)
    try:
        held = {h["id"]: h for h in holdings.listing().get("holdings", [])}
    except Exception:                                         # noqa: BLE001
        held = {}
    try:
        suppliers = vendors.listing().get("vendors", [])
    except Exception:                                         # noqa: BLE001
        suppliers = []
    done = checks.complete_checks()
    counts_as = costs.framework_inputs(answers)["counts_as_cost"]
    tools = catalog.all_tools()
    for row in found["projects"]:
        row["tracker"] = projects.tracker(row)
        row["passage"] = projects.passage_options(row)
        mine = [v for v in suppliers if row["ref"] in (v.get("projects") or [])]
        row["supplier"] = mine[0]["name"] if mine else ""
        row["findings"] = projects.findings_all(
            row, inputs=inputs, holdings=held, checks_done=done)
        row["summary"] = projects.summary(row)
        # Data 5.2 · every holding carrying what this project said it needs,
        # whoever owns it — the whole organisation, not the asker's unit.
        row["data_lookup"] = holdings.lookups(
            list((row.get("problem") or {}).get("info_for") or []))
        # 10.6 · computed on Budget, shown here, never typed.
        row["full_cost"] = costs.full_cost(row["ref"],
                                           counts_as_cost=counts_as or None)
        # 10.18 · the Vendors panel, read-only.
        row["vendors_panel"] = [{
            "name": v.get("name", ""), "product": v.get("product", ""),
            "route": v.get("route_label") or v.get("route", ""),
            "terms": v.get("terms") or {}, "renewal": v.get("renewal", ""),
            "amount": v.get("amount"), "basis": v.get("basis_label", "")}
            for v in mine]
    # Registry 4.3, shown on the project too — the finding names both.
    for f in catalog.findings(tools, projects=found["projects"]):
        if f["id"] == "finding.rg.duplicate_purchase":
            for row in found["projects"]:
                if row["ref"] == f.get("project"):
                    row["findings"].append({"id": f["id"], "says": f["says"]})
                    row["duplicate_of"] = f.get("tool")
    # The approved wording the disclosure can point at, from Process.
    found["wordings"] = [{"ref": p.get("ref"), "name": p.get("name", "")}
                         for p in procedures.of_kind(procedures.WORDING)
                         if p.get("status") == procedures.IN_FORCE]
    found["wording_home"] = procedures.framework_inputs(answers).get(
        "wording_home", "")
    found["list_findings"] = projects.list_findings(
        found["projects"], inputs=inputs,
        list_checked=projects.last_list_check())
    found["list_checked"] = projects.last_list_check()
    found["inputs"] = inputs
    found["levels"] = _their_levels()
    found["settable_states"] = [{"id": s, "shown_as": spine.BY_STATE[s].shown_as}
                                for s in SETTABLE_STATES]
    found["options"] = {
        "verdicts": list(projects.VERDICTS),
        "categories": [{"key": k, "name": n, "says": s}
                       for k, n, s in projects.CATEGORIES],
        "closes": list(projects.CLOSES_WITHOUT_TOOL),
        "steps": [{"n": s.number, "name": s.name, "question": s.question,
                   "from": s.answered_from} for s in spine.HIERARCHY],
        "confidence": list(projects.CONFIDENCE),
        "in_scope": list(projects.IN_SCOPE),
        "money_from": list(projects.MONEY_FROM),
        "how_often": list(projects.HOW_OFTEN),
        "material": list(projects.MATERIAL), "staged": list(projects.STAGED),
        "replaced_by": list(projects.REPLACED_BY),
        "delegating_told": list(projects.DELEGATING_TOLD),
    }
    found["holdings"] = [{"id": h["id"], "name": h.get("name", ""),
                          "reachable": h.get("reachable_label", ""),
                          "sensitive": h.get("sensitive", [])}
                         for h in held.values()]
    found["goals"] = [{"ref": g["ref"], "goal": g.get("goal", "")}
                      for g in goals.all_goals()]
    # Steps 2 to 4 are answered from Registry: what the organisation holds,
    # who holds it, and what is available on an agreement.
    found["catalog"] = [{"ref": t["ref"], "name": t.get("name", ""),
                         "does": t.get("does", ""),
                         "held_by": [h.get("unit") for h in t.get("held_by") or []],
                         "availability": t.get("availability") or []}
                        for t in tools]
    # The route in, in the organisation's own words, from Process.
    route = next((p for p in procedures.of_kind(procedures.ROUTE_IN)), None)
    found["route_in"] = {"name": route.get("name", ""),
                         "steps": route.get("steps", ""),
                         "next": route.get("what_happens_next", ""),
                         "ref": route.get("ref", "")} if route else {}
    found["recommendations"] = {r.id: r.as_dict() for r in spine.RECOMMENDATIONS}
    found["decides"] = actor.role == Role.COUNCIL
    found["utility_options"] = {**holdings.UTILITY,
                                **{holdings.CUSTOM + a: a
                                   for a in holdings.added_utility()}}
    found["utility_options"].pop("other", None)
    found["one_unit"] = holdings.framework_inputs(answers)["one_unit"]
    return found


def api_project_section(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import projects
    fields = body.get("fields") or {}
    if not isinstance(fields, dict):
        return {"ok": False, "error": "Nothing to save."}
    def tidy(value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()[:6000]
        if isinstance(value, list):
            return [tidy(v) for v in value][:60]
        if isinstance(value, dict):
            return {str(k)[:60]: tidy(v) for k, v in list(value.items())[:60]}
        return value if isinstance(value, (bool, int, float)) else None
    out = projects.save_section(str(body.get("ref", "")),
                                str(body.get("section", "")),
                                {k: tidy(v) for k, v in fields.items()}, actor)
    # 9.39 · is it running now — the one answer here Projects reads as state.
    running = fields.get("running")
    if out.get("ok") and body.get("section") == "tool" and running in (
            "yes", "no", "unknown"):
        projects._set_field(str(body.get("ref", "")), "in_use", running)
    return out


def api_project_verdicts(actor: Actor, body: dict, params: dict
                         ) -> dict[str, Any]:
    from app import projects
    return projects.save_verdicts(str(body.get("ref", "")),
                                  categories=body.get("categories") or None,
                                  steps=body.get("steps") or None, actor=actor)


def api_project_close_without_tool(actor: Actor, body: dict, params: dict
                                   ) -> dict[str, Any]:
    from app import projects
    return projects.close_without_tool(str(body.get("ref", "")),
                                       str(body.get("category", "")), actor,
                                       why=str(body.get("why", "")))


def api_project_version(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import projects
    ref = str(body.get("ref", ""))
    if body.get("vref"):
        allowed = {k: body[k] for k in ("material", "staged", "tested",
                                        "tested_reason", "live") if k in body}
        return projects.update_version(ref, str(body["vref"]), actor, **allowed)
    return projects.open_version(ref, actor, what=str(body.get("what", "")),
                                 told_on=str(body.get("told_on", "")),
                                 not_told=bool(body.get("not_told")))


def api_project_sunset(actor: Actor, body: dict, params: dict
                       ) -> dict[str, Any]:
    """Anybody may propose retirement and write the record; deciding it,
    confirming where the records went, and closing it are the decision-
    maker's."""
    from app import projects
    fields = {k: v for k, v in (body.get("fields") or {}).items()
              if k in projects.SUNSET_FIELDS}
    decider_only = ("decided_by", "decided_on", "records_confirmed_by")
    if actor.role != Role.COUNCIL and any(fields.get(k) for k in decider_only):
        return {"ok": False, "error": "Deciding the retirement and confirming "
                                      "where the records went are for whoever "
                                      "decides. Anybody can write the rest."}
    return projects.save_sunset(str(body.get("ref", "")), actor, **fields)


def api_project_sunset_close(actor: Actor, body: dict, params: dict
                             ) -> dict[str, Any]:
    from app import projects
    if actor.role != Role.COUNCIL:
        return {"ok": False, "error": "Closing the retirement record is for "
                                      "whoever decides."}
    return projects.close_sunset(str(body.get("ref", "")), actor)


def api_project_list_checked(actor: Actor, body: dict, params: dict
                             ) -> dict[str, Any]:
    from app import projects
    return projects.list_checked(actor)


def api_project_next_gate(actor: Actor, body: dict, params: dict
                          ) -> dict[str, Any]:
    from app import projects
    ref = str(body.get("ref", ""))
    if projects.one(ref) is None:
        return {"ok": False, "error": "No such project."}
    projects._set_field(ref, "next_gate_by", str(body.get("by", ""))[:10])
    return {"ok": True}


#: The states the Projects screen may set directly. Cleared is what a passage
#: produces, and Retired is what the Sunset gate produces — neither is a
#: button, because a project marked retired from a menu would skip the
#: retirement record the spine requires.
SETTABLE_STATES = (spine.BEING_WORKED, spine.WAITING_DECISION,
                   spine.WAITING_PERSON, spine.PAUSED, spine.TURNED_DOWN)


def _their_levels() -> list[str]:
    """The organization's own scrutiny levels, or none.

    None until the framework has answered how many levels there are.
    `module_one.tiers_for` hands back Low, Moderate and High for a framework
    that has answered nothing, and offering those here would put three levels
    in front of an organization that never chose them.
    """
    try:
        from app import module_one
        return [name for _, name in
                module_one.level_names(_framework_answers())]
    except Exception:                                         # noqa: BLE001
        return []


def api_project_start(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import projects
    return projects.start(str(body.get("name", "")), actor,
                          asked_by=str(body.get("asked_by", "")),
                          already_running=str(body.get("already_running",
                                                        "")))


def api_project_move(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Record a passage. The refusal, where there is one, comes from the
    spine and is passed through in the spine's own words."""
    from app import projects
    return projects.move(str(body.get("ref", "")), str(body.get("to", "")),
                         actor, happened=str(body.get("happened", "")))


def api_project_state(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import projects
    to = str(body.get("to", ""))
    if to not in SETTABLE_STATES:
        return {"ok": False,
                "error": "That state is not set from here. A project reaches "
                         "Cleared by passing a gate, and Retired through "
                         "Sunset."}
    if to == spine.WAITING_PERSON and not str(body.get("waiting_for", "")).strip():
        return {"ok": False, "error": "Say who it is waiting on."}
    return projects.set_state(str(body.get("ref", "")), to, actor,
                              waiting_for=str(body.get("waiting_for", "")))


def api_project_accountable(actor: Actor, body: dict,
                            params: dict) -> dict[str, Any]:
    from app import projects
    return projects.name_accountable(str(body.get("ref", "")),
                                     str(body.get("role", "")), actor,
                                     person=str(body.get("person", "")))


def api_project_point(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import projects
    return projects.point_at(str(body.get("ref", "")),
                             str(body.get("floor", "")),
                             str(body.get("points_at", "")), actor)


def api_project_level(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import projects
    return projects.set_level(str(body.get("ref", "")),
                              str(body.get("level", "")), actor,
                              levels=_their_levels())


def api_project_restart(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Start a paused project again, or pick a turned-down one back up."""
    from app import projects
    ref = str(body.get("ref", ""))
    how = str(body.get("how", ""))
    if how == spine.START_AGAIN:
        return projects.start_again(ref, actor)
    if how == spine.PICK_UP_AGAIN:
        return projects.pick_up_again(ref, actor)
    return {"ok": False, "error": spine.REFUSE_NOT_AVAILABLE}


def api_decider(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import decider
    return {**decider.state(),
            # First answer is a setup act (OT); changing one is an amendment.
            "can_answer": actor.is_ot if not decider.current().confirmed
                          else actor.is_council}


def api_decider_answer(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import decider
    return decider.answer(
        str(body.get("shape", "")), actor,
        noun=str(body.get("noun", "")),
        quorum=body.get("quorum", 3),
        report_out=str(body.get("report_out", "")),
    )


def api_council(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import decider
    d = decider.current()
    return {
        "decider": decider.state(),
        "is_member": actor.is_council and council.is_member(actor),
        # A single decider has no roster. Sending one anyway is how a screen
        # ends up rendering an empty members table to someone who chose not to
        # have members.
        "members": council.members() if d.is_group else None,
        "decisions": council.decisions(limit=40),
        "proposals": council.proposals(open_only=False)[:20],
        "minutes": council.minutes(),
        "recordings": council.recordings(),
        "mode": mode_mod.current().value,
        "parameter_set_hash": config_mod.parameter_set_hash(),
    }


def api_council_adopt(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    return council.adopt_parameter_set(
        actor=actor,
        members_present=body.get("members_present",
                                 ["council.cto", "council.gc", "council.water"]),
        summary=body.get("summary", ""),
    )


def api_council_decide(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    return council.decide_gate(
        body["decision_id"], outcome=body.get("outcome", "approved"),
        actor=actor, members_present=body.get("members_present"),
        rationale=body.get("rationale", ""),
    )


def api_oversight(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Oversight — the record of every decision made under the framework.

    This served the reference agency's incident levels and monitoring
    register, read from its corpus. It now reads this organization's own
    decisions against its own framework answers.
    """
    from app import checks, decisions, projects, versions
    live = versions.adopted()
    return {**decisions.surface(
        answers=_framework_answers(), projects=projects.all_projects(),
        incidents=checks.incidents(),
        adopted=live.as_dict() if live else None,
        versions_list=[v["label"] for v in versions.history()]),
        "hat": actor.role.value, "title": actor.title,
        "may_close_any": actor.role == Role.COUNCIL}


def _outside_delegation(inputs: dict[str, Any], level: str) -> bool:
    """Whether an approval in the User hat is outside what the organization
    said may move without the decision-maker. Only the answers that can be
    read against a record are read; the rest are left to the reason the
    person gives."""
    delegation = inputs.get("delegation") or []
    lowest = (inputs.get("levels") or [""])[0]
    if not delegation or "nothing" in delegation:
        return True
    return delegation == ["lowest_risk"] and bool(level) and level != lowest


def api_decision_save(actor: Actor, body: dict, params: dict
                      ) -> dict[str, Any]:
    """Record a decision, and propose the move its outcome implies. Projects
    commits the move or refuses it; the refusal is shown verbatim and the
    decision row stays, because the decision happened either way."""
    from app import decisions, projects, spine as sp
    inputs = decisions.framework_inputs(_framework_answers())
    kind = str(body.get("kind") or decisions.KIND_TOOL)
    if kind not in decisions.KIND_NAMES:
        kind = decisions.KIND_TOOL
    outcome = str(body.get("outcome") or "")
    about = str(body.get("about") or "")[:60]
    hat = str(body.get("hat_worn") or actor.role.value)
    project = projects.one(about) if about and about not in (
        "framework", "weights") else None

    # 6H · where the User's delegation runs out. Nothing is blocked: where
    # nothing moves without the decision-maker, no approval is offered; where
    # it is outside what they said, one line of consequence and a reason.
    if hat == "operator" and kind == decisions.KIND_TOOL and outcome in (
            decisions.APPROVED, decisions.APPROVED_WITH):
        level = (project or {}).get("level", "")
        if _outside_delegation(inputs, level) and not str(
                body.get("anyway_reason") or "").strip():
            said = inputs["readbacks"].get("delegation") or \
                "You have not said what the User may approve."
            return {"ok": False, "needs_reason": True,
                    "error": f"{said} This one is"
                             f"{f' at {level}' if level else ' not inside that'}. "
                             f"Record it anyway? Say why in one line."}

    def texts(v: Any, n: int = 4000) -> str:
        return str(v or "").strip()[:n]

    extra = {
        "kind": kind, "hat_worn": hat,
        "consulted": [texts(c, 200) for c in (body.get("consulted") or [])][:20],
        "why": texts(body.get("why")), "disagreed": texts(body.get("disagreed")),
        "where_else": texts(body.get("where_else"), 300),
        "anyway_reason": texts(body.get("anyway_reason"), 300),
    }
    if kind == decisions.KIND_FRAMEWORK:
        extra.update({
            "framework_what": texts(body.get("framework_what"), 80),
            "adopted_by_title": texts(body.get("adopted_by_title"), 200),
            "effective_on": texts(body.get("effective_on"), 10),
            "what_changed": texts(body.get("what_changed")),
            "owed": texts(body.get("owed"), 80),
            "comes_back": texts(body.get("comes_back"), 10)})
        about = "framework"
    elif kind == decisions.KIND_WENT_WRONG:
        severity = texts(body.get("severity"), 200)
        position = next((s["position"] for s in inputs["severities"]
                         if s["label"] == severity), 0)
        extra.update({
            "incident": texts(body.get("incident"), 40),
            "severity": severity, "severity_position": position,
            "was_stopped": texts(body.get("was_stopped"), 60),
            "not_stopped_why": texts(body.get("not_stopped_why"), 300),
            "stopped_by": texts(body.get("stopped_by"), 200),
            "stopped_at": texts(body.get("stopped_at"), 20),
            "told": [{"party": texts(t.get("party"), 200),
                      "when": texts(t.get("when"), 20),
                      "not_told": texts(t.get("not_told"), 300)}
                     for t in (body.get("told") or []) if isinstance(t, dict)
                     and texts(t.get("party"))][:20],
            "lookback": texts(body.get("lookback"), 80),
            "lookback_other": texts(body.get("lookback_other"), 200),
            "restart_condition": texts(body.get("restart_condition")),
            "writeup_by": texts(body.get("writeup_by"), 200)})
    elif kind == decisions.KIND_STANDING:
        extra.update({
            "standing_which": texts(body.get("standing_which"), 80),
            "standing_other": texts(body.get("standing_other"), 200),
            "says_now": texts(body.get("says_now")),
            "changes_framework": texts(body.get("changes_framework"), 80)})
    elif kind == decisions.KIND_WEIGHTS:
        axes = [{"axis": texts(a.get("axis"), 200),
                 "weight": texts(a.get("weight"), 20),
                 "why": texts(a.get("why"), 300)}
                for a in (body.get("axes") or []) if isinstance(a, dict)
                and texts(a.get("axis"))][:30]
        extra.update({
            "weights_what": texts(body.get("weights_what"), 80),
            "axes": axes,
            "single_factors": [{"factor": texts(f.get("factor"), 200)}
                               for f in (body.get("single_factors") or [])
                               if isinstance(f, dict) and texts(f.get("factor"))]
            if inputs.get("single_factor") else [],
            "weights_owner": texts(body.get("weights_owner"), 200),
            "weights_from": texts(body.get("weights_from"), 10),
            "what_changed": texts(body.get("what_changed"))})
        about = "weights"

    conditions = [{"what": texts(c.get("what"), 300),
                   "owner": texts(c.get("owner"), 200),
                   "by": texts(c.get("by"), 10),
                   "about": about}
                  for c in (body.get("conditions") or [])
                  if isinstance(c, dict) and texts(c.get("what"))][:20]
    if kind == decisions.KIND_WENT_WRONG and extra.get("restart_condition"):
        conditions.append({"what": extra["restart_condition"],
                           "owner": texts(body.get("restart_owner"), 200),
                           "by": texts(body.get("restart_by"), 10),
                           "about": about})

    gate = str(body.get("gate") or "")
    if kind == decisions.KIND_WEIGHTS:
        gate = gate if gate in sp.GATE_ORDER else ""
    out = decisions.record(
        about=about, what=texts(body.get("what"), 300), actor=actor,
        shape=inputs["shape"], decider=texts(body.get("decider"), 200),
        outcome=outcome, how_decided=texts(body.get("how_decided"), 40),
        conditions=conditions, gate=gate if gate in sp.GATE_ORDER else "",
        decided_on=texts(body.get("decided_on"), 10), extra=extra)
    if not out.get("ok"):
        return out

    if kind == decisions.KIND_WEIGHTS and extra.get("axes"):
        axes = {}
        for a in extra["axes"]:
            try:
                axes[a["axis"]] = float(a["weight"])
            except (TypeError, ValueError):
                continue
        if axes:
            decisions.set_weights(axes, actor, why=extra.get("what_changed", ""))

    # The move the outcome proposes. Projects commits it or says why not.
    move = decisions.proposed_move(outcome)
    if project and move:
        if move == "forward":
            here = project.get("gate") or ""
            order = list(sp.GATE_ORDER)
            to = order[order.index(here) + 1] if here in order and \
                order.index(here) + 1 < len(order) else ""
            moved = projects.move(about, to, actor) if to else \
                {"ok": False, "error": "There is no gate after this one."}
        elif move == sp.SUNSET:
            moved = projects.move(about, sp.SUNSET, actor)
        else:
            moved = projects.set_state(about, move, actor)
        out["move"] = {"ok": bool(moved.get("ok")),
                       "says": "" if moved.get("ok") else moved.get("error", "")}
    return out


def api_condition_close(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import decisions
    try:
        index = int(body.get("index", -1))
    except (TypeError, ValueError):
        index = -1
    return decisions.close_condition(str(body.get("decision", "")), index,
                                     actor=actor,
                                     may_close_any=actor.role == Role.COUNCIL)


def api_labels(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """§7 · the organization's own labels, if it keeps any. Any hat, no
    approval — requiring a signature to add a word would say the list
    matters more than they said it does."""
    from app import decisions
    if "on" in body:
        decisions.set_labels_on(bool(body.get("on")), actor)
    if "labels" in body:
        return decisions.set_labels([str(x)[:120] for x in
                                     (body.get("labels") or [])][:60], actor)
    return {"ok": True}


def api_incident(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    return oversight.report_incident(
        registry_id=body["registry_id"], level=int(body.get("level", 1)),
        summary=body.get("summary", ""), actor=actor, notes=body.get("notes", ""))


def api_search(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    query = params.get("q", [""])[0] or body.get("q", "")
    # The index is the reference agency's documents; only that agency searches
    # it. Everyone else searches what they uploaded. See agent.own_document_hits.
    if not tenant.owns_corpus():
        own = agent.own_document_hits(query, limit=8)
        return {"query": query, "in_scope": bool(own),
                "hits": [{"citation": f"{h['file']} · paragraph {h['paragraph'] + 1}",
                          "snippet": h["quote"][:300], "score": h["score"],
                          "coverage": None, "source": "your document"}
                         for h in own]}
    hits = retrieval.search(query, top_k=8)
    return {"query": query, "in_scope": retrieval.in_scope(hits),
            "hits": [{"citation": h.passage.citation, "snippet": h.snippet(300),
                      "score": h.score, "coverage": h.coverage,
                      "source": h.passage.source} for h in hits]}


#: Which state's corpus is actually loaded. Discovered, never assumed.
#: The browser refuses to compile WebAssembly that arrives as octet-stream, and
#: Windows' mimetypes registry has never heard of .wasm. Registered explicitly
#: rather than left to the platform.
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/octet-stream", ".onnx")


#: The dictation runtime and model: ~60 MB, and they change when the filename
#: changes and not otherwise. Everything else in this application is `no-store`,
#: which is right for a record that must never be stale and catastrophic for a
#: 60 MB model — it would be re-fetched on every visit.
LONG_CACHE_PREFIX = "/assets/speech/"
LONG_CACHE = "public, max-age=31536000, immutable"

#: The largest JSON body any screen sends. The document intake takes files
#: up to 12 MB, which base64 makes 16; this leaves room for that and no more.
MAX_JSON_BODY = 20 * 1024 * 1024


def _caller_agency(actor: Actor, params: dict) -> str:
    """Which agency container this request belongs to, or "".

    Prefers the proved address; falls back to the claimed one so that browsers
    signed in before session tokens existed keep reaching their own agency
    rather than silently landing in nobody's. Either way the answer comes from
    the tenancy record, not from anything the browser asserts about itself — a
    caller can name an address, but not which container it is a member of.
    """
    email = actor.email or (params.get("email", [""])[0] or "")
    if not email:
        return tenant.ANONYMOUS
    # `ANONYMOUS` rather than "" when nothing matches. Empty means "no tenant",
    # which resolves to the corpus itself — right for a CLI, and wrong for a
    # browser we cannot identify, which would then be shown SCDES's documents.
    return str(tenancy.access_for(email).get("state", "") or "") or tenant.ANONYMOUS


def _loaded_state_code() -> str | None:
    from app import profile
    juris = (profile.load().jurisdiction or "").strip()
    from app.states import STATE_NAMES
    for code, name in STATE_NAMES.items():
        if name.lower() == juris.lower():
            return code
    return None


def _loaded_agency_id() -> str:
    """Which *agency* the loaded corpus belongs to, not just which state.

    A state holds many governmental units and the corpus belongs to exactly one
    of them. Reporting only the state made every agency in South Carolina look
    like the owner of SCDES's documents — so registering with the DEMO agency
    showed SCDES's name, its project register and its framework files.

    Matched on the shorthand the profile derived from the documents themselves,
    falling back to the full name. No match means no agency claims the corpus,
    which is the safe answer: nothing is shown rather than the wrong thing.
    """
    from app import profile, states
    p = profile.load()
    short = (getattr(p, "short_name", "") or "").strip().lower()
    full = (getattr(p, "name", "") or "").strip().lower()
    code = _loaded_state_code()
    if not code:
        return ""
    for a in states.agencies_for(code):
        if short and a.get("abbrev", "").strip().lower() == short:
            return a["id"]
    for a in states.agencies_for(code):
        if full and a.get("name", "").strip().lower() == full:
            return a["id"]
    return ""


def api_states(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import states, tenancy
    loaded = _loaded_state_code()
    return {**states.registry(active_code=params.get("active", [None])[0],
                              loaded_code=loaded),
            "loaded_agency": _loaded_agency_id(),
            # Carried here because the launcher already loads this on boot, and
            # the sign-in copy has to know whether a reviewer step exists before
            # it describes one.
            "review_required": tenancy.review_required()}


#: What a tenant that does not own the corpus is told instead of the corpus.
#:
#: The client's ticket: "Click on Agency Profile, would see information about
#: the DEMO account agency. Still Showing SCDES." A sweep of every read
#: endpoint found nine doing it, not one — the profile, the home screen, and
#: the six reference rooms seeded from the corpus.
#:
#: Fails closed and says why, rather than returning an empty shell that reads
#: as a bug. The rule this protects is the client's own, in capitals: "Privacy
#: and security are paramount controls within the framework, we can't violate
#: our own rules by letting other content bleed across accounts."
NOT_YOURS = {
    "available": False,
    "why": "This section is built from a reference agency's own adopted "
           "documents. It becomes yours once your framework is adopted and "
           "your own records fill it — until then there is nothing here that "
           "belongs to your organization, and nothing from anybody else's is "
           "shown.",
}


def _corpus_only(payload_fn):
    """Serve corpus-derived content to the agency that owns it, and nobody
    else. Wrapped rather than repeated, because nine endpoints needed it and
    the tenth will too."""
    def guarded(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
        from app import tenant
        if not tenant.owns_corpus():
            return dict(NOT_YOURS)
        return payload_fn(actor, body, params)
    guarded.__name__ = getattr(payload_fn, "__name__", "guarded")
    guarded.__doc__ = payload_fn.__doc__
    return guarded


def api_profile(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import profile, tenant
    # The loaded corpus's profile is the reference agency's, not theirs.
    if not tenant.owns_corpus():
        return {**dict(NOT_YOURS), "can_edit": False,
                "agency": _agency_label(actor, params)}
    return {**profile.summary(), "can_edit": actor.is_ot}


def api_profile_rediscover(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import profile
    decision = guard(actor, Target.CONFIG, "rediscover_agency_profile")
    if not decision.allowed:
        return {"rediscovered": False, "reason": decision.reason}
    return {"rediscovered": True, **profile.rediscover().as_dict()}


def api_integrity(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The audit of the loaded corpus — for the agency that owns it, only.

    This was ungated. It reads the corpus on disk and reports on it by
    document name, so any signed-in tenant could fetch findings citing "the
    SCDES AI Governance Adoption Directive" and "the SCDES AI Implementation
    Playbook", with quoted lines from both.

    The earlier sweep of nine endpoints missed it because the sweep works off
    a hand-written list of endpoints and this one was not on it. That is fixed
    in `tools/_leak_scan.py`, which now derives the list from ROUTES.
    """
    from app import integrity
    return integrity.audit().as_dict()


def api_vocabulary(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import vocabulary
    return {**vocabulary.state(), "can_edit": actor.is_ot,
            "mode": mode_mod.current().value}


def api_vocabulary_preview(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import vocabulary
    return vocabulary.preview_rename(
        body["concept"], body["noun"], body.get("scheme")).as_dict()


def api_vocabulary_set(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import vocabulary
    return vocabulary.set_term(body["concept"], body["noun"], actor,
                               scheme=body.get("scheme"))


def _trail_selected(params: dict) -> tuple[list[dict[str, Any]], str, str]:
    """The entries a filter selects, the sentence that says so, and the one
    record where the filter is one record."""
    from app import trail
    held = trail.rows()
    def one(key: str) -> str:
        return str(params.get(key, [""])[0] or "").strip()[:200]
    record, person, hat = one("record"), one("person"), one("hat")
    kind, since, until = one("kind"), one("since"), one("until")
    surface = one("surface")
    picked = []
    for row in held:
        s = trail.shown(row)
        if record and s["record"] != record:
            continue
        if person and s["who"] != person:
            continue
        if hat and s["hat"] != hat:
            continue
        if kind and s["action"] != kind:
            continue
        if surface and s["where"] != surface:
            continue
        if since and str(row.get("at") or "")[:10] < since:
            continue
        if until and str(row.get("at") or "")[:10] > until:
            continue
        picked.append(row)
    said = trail.filter_sentence(len(picked), record=record, since=since,
                                 person=person, hat=hat)
    return picked, said, record


def api_audit(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The Audit trail — this organization's own, and nobody else's.

    This served the last sixty lines of one file every organization wrote
    into, names and details included, to whoever asked. Each organization
    now has its own trail, and the shared back-end copy is never read on
    anybody's behalf.

    Deliberately not behind the subscription: the trail is the
    organization's own record, and producing it is never behind a fee.
    """
    from app import decisions, module_one, projects, trail, versions
    answers = _framework_answers()
    def value(key: str) -> Any:
        return module_one.value_of(answers, key)[0]
    open_records = value("org.open_records") or "not sure"
    found = trail.report(open_records="yes" if open_records == "yes"
                         else str(open_records))
    picked, said, record = _trail_selected(params)
    sort = str(params.get("sort", ["Newest first"])[0] or "Newest first")
    ordered = trail.in_order(picked, newest_first=(sort != "Oldest first"
                                                   and not record))
    rendered = [trail.shown(r) for r in ordered]
    if sort == "By record":
        rendered.sort(key=lambda r: r["record"])
    elif sort == "By person":
        rendered.sort(key=lambda r: r["who"])
    elif sort == "By kind of event":
        rendered.sort(key=lambda r: r["what"])
    notes: dict[Any, list[dict[str, Any]]] = {}
    for r in (trail.shown(x) for x in trail.rows()):
        if r["of"] is not None:
            notes.setdefault(r["of"], []).append(r)
    live = versions.adopted()
    adopted_on = live.adopted_on if live else ""
    amendments = [d.get("decided_on", "") for d in decisions.all_decisions()
                  if d.get("kind") == decisions.KIND_FRAMEWORK
                  and d.get("framework_what") in decisions.CHANGES]
    written_where = str(value("who.record") or "").strip()
    q_amend = module_one.by_key("who.amend")
    amend = value("who.amend")
    amend_words = next((o.label for o in (q_amend.options if q_amend else [])
                        if o.value == amend), "")
    raised = trail.findings_for(
        trail.rows(), written_where=written_where,
        projects=projects.all_projects(), retention=value("data.retention") or "",
        amend_words=amend_words[:1].lower() + amend_words[1:] if amend_words else "",
        amendments_on=amendments, adopted_on=adopted_on)
    people = sorted({trail.shown(r)["who"] for r in trail.rows()})
    return {
        **found,
        "entries": rendered[:500],
        "total_selected": len(rendered),
        "notes": {str(k): v for k, v in notes.items()},
        "filter_sentence": said,
        "record": record,
        "raised": raised,
        "trail_line": trail.trail_line(found["first_entry"], written_where,
                                       gap_owner=""),
        "empty_state": trail.empty_state(
            knows_what_it_runs="unknown" not in (value("have.used") or []),
            adopted=(adopted_on, live.adopted_title or live.adopted_by)
            if live and not trail.rows()[1:] and trail.rows() else None),
        "written_where": written_where,
        "stoppers": [str(r.get("role") or "") for r in (value("bad.stopper") or [])
                     if isinstance(r, dict)],
        "people": people,
        "people_count": len(people),
        "small": value("org.size") == "u25",
        "options": {"how_known": list(trail.HOW_KNOWN),
                    "about": list(trail.ABOUT),
                    "note_kinds": list(trail.NOTE_KINDS),
                    "written_where": list(trail.WRITTEN_WHERE),
                    "hats": list(trail.HATS.values()) + [trail.NO_HAT],
                    "sorts": list(trail.SORTS)},
        "copy": {"record_it": trail.RECORD_IT_SAYS.format(
                     today=_today_str()),
                 "note": trail.NOTE_SAYS, "correction": trail.CORRECTION_SAYS,
                 "no_excluding": trail.NO_EXCLUDING},
        "projects": [{"ref": p["ref"], "name": p.get("name", "")}
                     for p in projects.all_projects()],
    }


def _today_str() -> str:
    from datetime import date
    return clock.today_str()


def api_trail_elsewhere(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import trail
    return trail.record_elsewhere(
        actor=actor, what=str(body.get("what", "")),
        happened=str(body.get("happened", "")),
        how_known=str(body.get("how_known", "")),
        about=str(body.get("about", "")), about_ref=str(body.get("ref", "")),
        involved=body.get("involved") or [], paper=str(body.get("paper", "")),
        written_where=str(body.get("written_where", "")),
        note=str(body.get("note", "")))


def api_trail_note(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import trail
    return trail.add_note(actor=actor, of=body.get("of"),
                          text=str(body.get("text", "")),
                          kind=str(body.get("kind", "")))


def api_trail_correct(actor: Actor, body: dict, params: dict
                      ) -> dict[str, Any]:
    from app import trail
    return trail.correct(actor=actor, of=body.get("of"),
                         wrong=str(body.get("wrong", "")),
                         should=str(body.get("should", "")))


def api_trail_produce(actor: Actor, body: dict, params: dict
                      ) -> dict[str, Any]:
    """Produce the record: two files from exactly what the filter selected.
    Nothing can be left out, and producing it is itself written down."""
    import base64
    from app import trail
    query = {k: [str(v)] for k, v in (body.get("filter") or {}).items()
             if isinstance(v, (str, int))}
    picked, said, record = _trail_selected(query)
    name = _agency_label(actor, params).get("name", "")
    out = trail.produce(actor=actor, selected=picked, sentence_=said,
                        organisation=name, one_record=record)
    return {"ok": True, "count": out["count"], "seal": out["seal"],
            "html": base64.b64encode(out["html"].encode()).decode(),
            "csv": base64.b64encode(out["csv"].encode()).decode()}


# ---------------------------------------------------------------- onboarding
#
# These run before anyone has an identity, so they cannot pass through guard() —
# there is no actor yet. They are kept safe by being narrow: each validates its
# input, writes one record, and cannot read another agency's container or touch
# the corpus. See app/tenancy.py for what each check does and does not prove.

def api_tenancy(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import tenancy
    agency = params.get("agency", [""])[0]
    out = tenancy.summary()
    if agency:
        # Whether it is taken, and nothing about who is in it. This handed
        # anybody who asked the whole member list — every name, title and
        # email address — without signing in.
        state = tenancy.agency_state(agency)
        out["agency"] = {k: state.get(k) for k in
                         ("code", "exists", "active", "status", "created_at")}
    return out


def api_whose_container(actor: Actor, body: dict,
                        params: dict) -> dict[str, Any]:
    """Which container this caller's writes would land in.

    Exists so an automated check can ask before it writes, rather than
    discovering afterward. The harnesses answer real questions through real
    endpoints and start by blanking keys to make the walk deterministic; run
    against the wrong container that is indistinguishable from vandalism.

    Says only which container the caller belongs to and what kind it is. No
    answers, no members, nothing about anybody else — a caller learns where
    their own writes go and nothing more.
    """
    from app import tenancy
    agency = _caller_agency(actor, params)
    return {
        "agency": agency,
        "resolved_from": "session" if actor.email else "claimed address",
        "is_test_container": tenancy.is_shared_test_container(agency),
        "is_harness_container": tenancy.is_harness_container(agency),
        "safe_to_overwrite": tenancy.is_harness_container(agency),
    }


# ------------------------------------------------- the Terms of Use (app/terms.py)

#: Writes allowed before the Terms of Use are accepted: getting in, accepting,
#: asking for the signed form, reporting a fault, and leaving.
TERMS_EXEMPT = {"/api/terms/accept", "/api/terms/signed", "/api/session/end",
                "/api/bugs/report", "/api/register"}
TERMS_EXEMPT_PREFIXES = ("/api/agency/", "/api/nda/")


def _terms_gate(method: str, path: str, actor: Actor,
                viewing: dict[str, Any] | None) -> dict[str, Any] | None:
    """Refuse a change from a signed-in person who has not accepted the Terms.

    The agreement used to be a gate in the browser only — the server never
    asked, and Escape on the agreement screen closed it. Writes are checked
    here now. The GAIUS team's own addresses are exempt (IIA does not agree
    to its own terms), and so is a View as session, which writes nothing."""
    if method != "POST" or viewing or not actor.email:
        return None
    if path in TERMS_EXEMPT or path.startswith(TERMS_EXEMPT_PREFIXES):
        return None
    from app import admin, terms
    if admin.is_admin(actor.email) or tenancy.is_tester(actor.email):
        return None
    if terms.status(actor.email)["accepted"]:
        return None
    return {"ok": False, "needs_terms": True,
            "error": "Accept the Terms of Use to continue."}


def _open_door(path: str) -> bool:
    """Writes that need no signed-in session: getting in, the Terms, reporting
    a fault, signing out, and the search box (which writes nothing)."""
    return (path in TERMS_EXEMPT or path.startswith(TERMS_EXEMPT_PREFIXES)
            or path == "/api/chat")


SESSION_ENDED = "Your session ended — sign in again. That change was not saved."


def _proven_session_gate(method: str, path: str, actor: Actor,
                         params: dict) -> dict[str, Any] | None:
    """Every change comes from a proven sign-in.

    A request without a valid session token used to fall back to whatever
    address the browser claimed (`_caller_agency`), kept for browsers signed
    in before tokens existed. That fallback is how a tab whose session had
    gone kept writing — and anybody who knew a member's address could have
    written into their organization. Reads still fall back, so an old browser
    can see where it is; changes no longer do."""
    if method != "POST" or actor.email or _open_door(path):
        return None
    claimed = (params.get("email", [""])[0] or "").strip().lower()
    _note_refused(claimed, path, "no signed-in session")
    return {"ok": False, "session_ended": True, "error": SESSION_ENDED}


def _note_refused(claimed: str, path: str, why: str) -> None:
    """Kept for the development team's daily report (app/techreport.py)."""
    try:
        from app import techreport
        org = tenancy.access_for(claimed).get("state", "") if claimed else ""
        techreport.note_refused_save(claimed, org, path, why)
    except Exception:                                         # noqa: BLE001
        pass


def _no_organization_gate(method: str, path: str) -> dict[str, Any] | None:
    """Refuse a change that belongs to no organization.

    A request this server cannot tie to an organization resolves to
    `tenant.ANONYMOUS`, which reads as empty — and used to be written to as
    well. On Sep 29 Rebecca Valencia answered 111 framework questions from a
    browser that had lost its session; every one was saved, under no
    organization, and her own framework showed 7. A change with nowhere to go
    is refused now, and the screen says the session ended and asks her to
    sign in again, instead of appearing to save. Getting in, the Terms,
    reporting a fault and the search box (which writes nothing) stay open."""
    if method != "POST" or _open_door(path):
        return None
    if tenant.current() != tenant.ANONYMOUS:
        return None
    _note_refused("", path, "signed in, but on no organization")
    return {"ok": False, "session_ended": True, "error": SESSION_ENDED}


def _needs_terms(email: str) -> dict[str, Any] | None:
    """The refusal for a registration that has not accepted the Terms yet."""
    from app import terms
    if terms.may_register(email):
        return None
    if terms.status(email)["awaiting_signed"]:
        return {"ok": False, "awaiting_signed": True,
                "error": "Your registration is waiting for the signed Terms of Use. "
                         "It continues once IIA has the executed copy back."}
    return {"ok": False, "needs_terms": True,
            "error": "Read and accept the Terms of Use first."}


def api_terms(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The agreement, word for word, with where this address stands."""
    from app import terms
    email = params.get("email", [""])[0]
    return {**terms.document(), "status": terms.status(email)}


def api_terms_accept(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import terms
    def text(key: str, n: int = 200) -> str:
        return str(body.get(key) or "")[:n]
    return terms.accept(email=text("email"), name=text("name"), title=text("title"),
                        unit=text("unit"), agency=text("agency", 120),
                        authority=bool(body.get("authority")),
                        scrolled=bool(body.get("scrolled")),
                        user_agent=text("user_agent"), sha256=text("sha256", 80))


def api_terms_signed(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import terms
    def text(key: str, n: int = 200) -> str:
        return str(body.get(key) or "")[:n]
    return terms.request_signed(email=text("email"), name=text("name"),
                                title=text("title"), unit=text("unit"),
                                agency=text("agency", 120))


def api_admin_terms_received(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The GAIUS team has the executed signed form back."""
    from app import terms
    if not _platform(actor):
        return _PLATFORM_ONLY
    email = str(body.get("email", ""))[:200]
    out = terms.mark_signed_received(email, actor.email)
    if not out.get("ok"):
        return out
    return {**_organizations_view(),
            "says": f"Signed Terms received for {email.strip().lower()}. They can get "
                    f"their code now."}


def api_tour_seen(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The guided tour has been shown to this person (app/firstuse.py)."""
    from app import firstuse
    return firstuse.mark_tour_seen(actor.email)


def api_register_agency(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import tenancy
    refused = _needs_terms(str(body.get("email", "")))
    if refused:
        return refused
    return tenancy.start_registration(
        agency=str(body.get("agency", "")), name=str(body.get("name", "")),
        title=str(body.get("title", "")), email=str(body.get("email", "")),
        phone=str(body.get("phone", "")), attested=bool(body.get("attested")),
    )


def api_register_unlisted(actor: Actor, body: dict,
                          params: dict) -> dict[str, Any]:
    """Register a governmental unit that is not on the list.

    Records the unit the person describes, then registers them into it the
    ordinary way — the same name, title, phone and authority checks, the
    same code to the same mailbox — with no email domain applied. See
    `app/unlisted.py` for what that does and does not prove.

    The fields are checked before the unit is recorded, and a unit whose
    registration is refused on the spot is removed again, so a form that
    fails does not leave empty organizations behind.
    """
    from app import tenancy, unlisted
    name = str(body.get("name", ""))
    title = str(body.get("title", ""))
    email = str(body.get("email", "")).strip()
    phone = str(body.get("phone", ""))
    attested = bool(body.get("attested"))

    # The cheap refusals first, so a mistyped phone number does not mint a
    # unit. `start_registration` checks these too; checking here as well is
    # what keeps `unlisted.create` from running on a form that will fail.
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return {"ok": False, "error": "That does not look like an email address."}
    refused = _needs_terms(email)
    if refused:
        return refused
    if not attested:
        return {"ok": False,
                "error": "You need to confirm you hold delegated authority to "
                         "register on behalf of this organization."}

    made = unlisted.create(str(body.get("state", "")),
                           str(body.get("unit", "")), email)
    if not made["ok"]:
        return made
    unit = made["unit"]

    result = tenancy.start_registration(
        agency=unit["id"], name=name, title=title, email=email, phone=phone,
        attested=attested)
    if not result.get("ok") and not made.get("reused"):
        unlisted.forget(unit["id"])
        return result
    return {**result,
            "agency": {"id": unit["id"], "name": unit["name"],
                       "abbrev": unit["abbrev"], "state": unit["state"],
                       "unlisted": True}}


def api_signin_agency(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Send a code to someone already registered. Unauthenticated by necessity,
    like registration — and narrow for the same reason: it writes one pending
    code for an address that is already a member, and can do nothing else."""
    from app import tenancy
    email = str(body.get("email", ""))
    # The agency the person picked on the map. Where the address is registered
    # to a different one, no code is sent: signing in used to succeed and then
    # show that other organization's records under the picked agency's name.
    # The refusal does not say which organization it is registered to — this
    # endpoint is open to anybody, and that would tell a stranger who is
    # registered where.
    picked = str(body.get("agency", "") or "").strip().lower()
    if picked:
        belongs = str(tenancy.access_for(email).get("state") or "")
        if belongs and belongs != picked:
            label = tenancy._agency_names(picked).get("agency_label") or picked
            # IIA's own addresses, including the GAIUS team's, all belong to
            # IIA's own organization. Saying so tells a stranger nothing: the
            # domain is IIA's, and so is the organization. Keyed on the domain
            # and that organization — never on who is an admin, which a
            # refusal must not reveal.
            domain = email.strip().lower().rpartition("@")[2]
            if (domain == tenancy.TESTER_DOMAIN
                    and tenancy.is_shared_test_container(belongs)):
                own = tenancy._agency_names(belongs).get("agency_label") or belongs
                return {"ok": False, "wrong_agency": True, "iia": True,
                        "error": f"IIA addresses sign in from {own}, under "
                                 f"South Carolina — not from {label}. Go Back, "
                                 f"type DEMO in the agency list, and sign in "
                                 f"there. The GAIUS team's Admin screens, "
                                 f"including Organizations, are in its menu."}
            return {"ok": False, "wrong_agency": True,
                    "error": f"That address is not registered to {label}. "
                             f"Sign in from the agency it was registered "
                             f"with, or use your {label} email."}
    return tenancy.start_signin(email)


def api_verify_agency(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import tenancy
    out = tenancy.verify_code(str(body.get("email", "")),
                              str(body.get("code", "")))
    if out.get("ok"):
        # The address that accepted the Terms has now proved itself.
        from app import terms
        terms.confirm(str(body.get("email", "")))
    # A new organization waits for the GAIUS team to appoint its admin, so
    # the team is told the moment one exists.
    if out.get("ok") and out.get("needs_admin"):
        agency = out.get("agency") or {}
        first = (agency.get("members") or [{}])[0]
        notify_needs_admin(str(agency.get("code", "")), first.get("name", ""),
                           first.get("title", ""), first.get("email", ""))
    return out


def api_agency_access(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """What this address may see. The gate the whole interface reads."""
    from app import tenancy
    return tenancy.access_for(params.get("email", [""])[0])


def api_agency_approve(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The human step. Confirms delegated authority, which no check can infer.

    Council-only in this build, and audited. In a hosted product this is IIA's
    review queue rather than something inside the agency's own container.
    """
    from app import tenancy
    decision = guard(actor, Target.CONFIG, "approve_agency_registration",
                     detail={"agency": body.get("agency", "")})
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}
    return tenancy.approve(str(body.get("agency", "")),
                           reviewer=f"{actor.name} ({actor.title})".strip(),
                           note=str(body.get("note", "")))


def _people(actor: Actor) -> dict[str, Any]:
    """The people in the caller's own organization, for a proven member of
    it. Colleagues' addresses go only to its admins, who are the ones who add
    and need to see them; everybody else sees names, titles and roles."""
    from app import tenancy
    here = tenant.current()
    state = tenancy.agency_state(here)
    me = (actor.email or "").strip().lower()
    is_admin = tenancy.is_agency_admin(here, me)
    container = tenancy._load()["agencies"].get(here) or {}
    domain = str((container.get("identity") or {}).get("domain") or "")
    members = state.get("members") or []
    admins = [m for m in members if m.get("role") in ("admin", "owner")]
    return {
        "ok": True,
        # The organization these people belong to — the one the signed-in
        # address is a member of. The heading reads this, never the agency
        # picked on the map: those can differ, and the heading once named
        # SCDES above another organization's people.
        "organization": tenancy._agency_names(here).get("agency_label") or here,
        "is_admin": is_admin,
        "me": me if is_admin else "",
        "admin_names": [m.get("name", "") for m in admins],
        "needs_admin": not admins,
        "domain": domain,
        "people": [{"name": m.get("name", ""), "title": m.get("title", ""),
                    "role": "Admin" if m.get("role") in ("admin", "owner")
                            else "Member",
                    "added_at": m.get("added_at", ""),
                    **({"email": m.get("email", "")} if is_admin else {})}
                   for m in members],
    }


def api_agency_people(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    if not _verified_member(actor):
        return {"ok": False, "error": "Only a signed-in member of the "
                                      "organization can see who is in it."}
    return _people(actor)


def _people_change(actor: Actor, action: str, detail: dict[str, Any],
                   agency: str | None = None) -> None:
    """On the audit log, which outlives everything else. `agency` is given
    when the GAIUS team acts on an organization that is not their own."""
    from app.authz import default_log
    try:
        default_log().append(actor=actor.user_id, role=actor.role.value,
                             action=action, target="tenancy", outcome="allowed",
                             detail={"agency": agency or tenant.current(),
                                     "by": (actor.email or "").strip().lower(),
                                     **detail})
    except Exception:                                         # noqa: BLE001
        pass


def api_agency_remove_member(actor: Actor, body: dict, params: dict
                             ) -> dict[str, Any]:
    """An admin takes somebody off their own organization. Who is asking
    and which organization come from the proven session, never the body."""
    from app import tenancy
    if not _verified_member(actor):
        return {"ok": False, "error": "Sign in to your organization first."}
    email = str(body.get("email", ""))[:200]
    out = tenancy.remove_member(tenant.current(), actor.email, email)
    if not out.get("ok"):
        return out
    _people_change(actor, "remove_member", {"removed": email})
    you = email.strip().lower() == (actor.email or "").strip().lower()
    return {**_people(actor),
            "says": ("You are off the organization." if you else
                     f"{out['removed']} is off the organization and signed out.")}


def api_agency_role(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """An admin makes somebody in their own organization an admin, or a
    member. Their own organization only — it comes from the session."""
    from app import tenancy
    if not _verified_member(actor):
        return {"ok": False, "error": "Sign in to your organization first."}
    email = str(body.get("email", ""))[:200]
    role = str(body.get("role", ""))
    out = tenancy.set_role(tenant.current(), actor.email, email, role)
    if not out.get("ok"):
        return out
    _people_change(actor, "set_member_role", {"person": email, "role": out["role"]})
    return {**_people(actor),
            "says": (f"{out['name']} is an admin now." if out["role"] == "admin"
                     else f"{out['name']} is a member now.")}


def api_agency_add_member(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """An admin adds a colleague to their own organization, as a member or
    an admin.

    Who is asking, and which organization, come from the proven session and
    nothing else. This used to take both from the request body — "agency" and
    "by" — so anybody who knew an owner's address could add themselves to that
    organization by typing it.
    """
    from app import tenancy
    if not _verified_member(actor):
        return {"ok": False, "error": "Sign in to your organization to add "
                                      "somebody to it."}
    here = tenant.current()
    role = "admin" if body.get("role") == "admin" else "member"
    out = tenancy.add_member(
        agency=here, by_email=actor.email,
        name=str(body.get("name", ""))[:120],
        title=str(body.get("title", ""))[:120],
        email=str(body.get("email", ""))[:200], role=role)
    if not out.get("ok"):
        return out
    _people_change(actor, "add_member",
                   {"added": str(body.get("email", ""))[:200],
                    "name": str(body.get("name", ""))[:120],
                    "title": str(body.get("title", ""))[:120], "role": role})
    return {**_people(actor),
            "says": (f"{str(body.get('name', '')).strip()} is on "
                     f"{tenancy._agency_names(here).get('agency_label') or 'your organization'} "
                     f"now{', as an admin' if role == 'admin' else ''}. They sign "
                     f"in with their own work email and a code sent to it — "
                     f"nothing is sent to them from here.")}


# ------------------------------------------------ the GAIUS team: organizations
#
# brett@, lokesh@ and dev@iiac.ai appoint every organization's admins and
# clear sign-ups that never finished. People only: these read and change the
# member lists in tenancy's own store, and never bind another organization's
# container — so no framework, answer or document is reachable from here.

def _platform(actor: Actor) -> bool:
    from app import admin
    return admin.is_admin(actor.email)


_PLATFORM_ONLY = {"ok": False, "error": "This is for the GAIUS team."}


def _organizations_view() -> dict[str, Any]:
    from app import tenancy
    orgs = tenancy.organizations()
    from app import terms
    return {"ok": True, "organizations": orgs,
            "waiting": sum(1 for o in orgs if o["needs_admin"] and not o["test"]),
            "pending": tenancy.pending_signups(),
            # Registrations paused for the signed Terms of Use.
            "awaiting_signed": terms.awaiting_signed()}


def api_admin_organizations(actor: Actor, body: dict, params: dict
                            ) -> dict[str, Any]:
    if not _platform(actor):
        return _PLATFORM_ONLY
    return _organizations_view()


def api_admin_appoint(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Make somebody an organization's admin — promoting them if they are on
    it, adding them if not, opening the agency if nobody has registered it."""
    from app import tenancy
    if not _platform(actor):
        return _PLATFORM_ONLY
    agency = str(body.get("agency", ""))[:120].strip().lower()
    email = str(body.get("email", ""))[:200]
    out = tenancy.appoint(agency, actor.email,
                          str(body.get("name", ""))[:120],
                          str(body.get("title", ""))[:120], email)
    if not out.get("ok"):
        return out
    _people_change(actor, "appoint_admin", {"person": email}, agency=agency)
    label = tenancy._agency_names(agency).get("agency_label") or agency
    return {**_organizations_view(),
            "says": f"{email.strip().lower()} is an admin of {label}. They sign "
                    f"in with that address and a code sent to it."}


def api_admin_member_role(actor: Actor, body: dict, params: dict
                          ) -> dict[str, Any]:
    from app import tenancy
    if not _platform(actor):
        return _PLATFORM_ONLY
    agency = str(body.get("agency", ""))[:120].strip().lower()
    email = str(body.get("email", ""))[:200]
    out = tenancy.set_role(agency, actor.email, email, str(body.get("role", "")),
                           by_platform=True)
    if not out.get("ok"):
        return out
    _people_change(actor, "set_member_role",
                   {"person": email, "role": out["role"], "as": "GAIUS team"},
                   agency=agency)
    return {**_organizations_view(),
            "says": f"{out['name']} is {'an admin' if out['role'] == 'admin' else 'a member'} now."}


def api_admin_member_remove(actor: Actor, body: dict, params: dict
                            ) -> dict[str, Any]:
    from app import tenancy
    if not _platform(actor):
        return _PLATFORM_ONLY
    agency = str(body.get("agency", ""))[:120].strip().lower()
    email = str(body.get("email", ""))[:200]
    out = tenancy.remove_member(agency, actor.email, email, by_platform=True)
    if not out.get("ok"):
        return out
    _people_change(actor, "remove_member",
                   {"removed": email, "as": "GAIUS team"}, agency=agency)
    return {**_organizations_view(),
            "says": f"{out['removed']} is off the organization and signed out."}


def api_admin_pending_remove(actor: Actor, body: dict, params: dict
                             ) -> dict[str, Any]:
    from app import tenancy
    if not _platform(actor):
        return _PLATFORM_ONLY
    email = str(body.get("email", ""))[:200]
    out = tenancy.remove_pending(email, actor.email)
    if not out.get("ok"):
        return out
    _people_change(actor, "remove_pending_signup",
                   {"removed": email.strip().lower()}, agency=out["agency"])
    return {**_organizations_view(),
            "says": f"The sign-up for {out['removed']} is removed."}


def api_admin_impersonate_start(actor: Actor, body: dict, params: dict
                                ) -> dict[str, Any]:
    """View as one of an organization's people — view only. See
    app/impersonate.py. Keyed on this browser's own proven session."""
    from app import impersonate
    if not _platform(actor):
        return _PLATFORM_ONLY
    return impersonate.start(impersonate.session(), actor.email,
                             str(body.get("email", ""))[:200])


def api_admin_impersonate_stop(actor: Actor, body: dict, params: dict
                               ) -> dict[str, Any]:
    """End it. Allowed while viewing — it is the one write that is."""
    from app import impersonate
    return impersonate.stop(impersonate.session())


def notify_needs_admin(agency: str, name: str, title: str, email: str) -> None:
    """Tell the GAIUS team an organization is waiting for them to appoint its
    admin. In the background, so registering is not held up by mail; never
    raises."""
    import threading

    def send() -> None:
        try:
            from app import admin, mailer, tenancy
            label = tenancy._agency_names(agency).get("agency_label") or agency
            text = (f"{label} ({agency.split('.', 1)[0].upper()}) was just registered "
                    f"and has no admin yet.\n\n"
                    f"Registered by: {name}, {title} <{email}>\n\n"
                    f"Until one of you appoints an admin, nobody can add people "
                    f"to it. Sign in to GAIUS and open Admin → Organizations to "
                    f"make {name} (or somebody else) its admin.")
            for to in sorted(admin.admins()):
                mailer.send(to, f"GAIUS — {label} needs an admin", text)
        except Exception:                                     # noqa: BLE001
            pass

    threading.Thread(target=send, name="needs-admin-mail", daemon=True).start()


def api_module(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Module One, adapted to what this agency has answered so far.

    The answers go with the request rather than being fetched separately,
    because every question's visibility, options and recommendation depend on
    them — a step returned without them would be the generic module, which is
    the one thing it must not be.
    """
    from app import module_one, versions
    working = versions.state().get("working") or {}
    answers = {k: v for k, v in working.items()}

    number = params.get("step", [""])[0]
    if number:
        step = module_one.by_number(number)
        if step is None:
            return {"error": f"no step {number}"}
        payload = {**step.as_dict(answers),
                   "gaps": [g for g in module_one.gaps(answers)
                            if g["step"] == step.number]}
        # What this organization's own uploaded documents appear to say about
        # each question — a passage, its file, and what it would fill in where
        # that is clear. Read once for the whole step. Never answers anything:
        # the person chooses to use it.
        try:
            from app import intake
            context = intake.matcher()
            if context:
                for q in payload.get("questions") or []:
                    q["evidence"] = intake.evidence_for_question(
                        q, context=context)
        except Exception:                                   # never block the work
            traceback.print_exc()
        return payload
    return module_one.summary(answers)


def api_discretion(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The Discretion Register — what this agency actually gets to decide.

    Superseded by Module One, and no longer reachable. Left as a function so
    `app/intake.py` — which matches uploaded documents against these rows —
    keeps working until it is rewritten against Module One's questions.

    It was still routed, and a sweep of every read endpoint found it handing a
    stranger the reference agency's own answers: "South Carolina Department of
    Environmental Services · SCDES · state environmental regulatory agency" as
    the default under a question about their identity.
    """
    from app import discretion, tenant
    if not tenant.owns_corpus():
        return dict(NOT_YOURS)
    number = params.get("section", [""])[0]
    if number:
        section = discretion.by_number(number)
        if not section:
            return {"error": f"no section {number}"}
        payload = section.as_dict()
        # Each row carries whatever the agency's own uploaded documents appear
        # to say about it. Attached here rather than fetched per question, so
        # opening a section is one request instead of nine.
        try:
            from app import intake
            for row in payload.get("rows", []):
                row["evidence"] = (intake.evidence_for_row(row)
                                   if row.get("configurable") else [])
        except Exception:                                   # never block the work
            pass
        return payload
    return discretion.summary()


def api_framework(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import framework
    answered, total = _policy_progress()
    return {
        **framework.summary(),
        # Whether this person may record an adoption, decided by the same
        # rule the endpoint applies — so the screen stops guessing from the
        # capacity name. It guessed "council-member", which nobody who signs
        # in holds, and told them to switch capacity in a header control
        # that no longer exists.
        "can_record_adoption": actor.is_council or _verified_member(actor),
        # The questions that decide policy, answered and in total. Optional
        # questions and the two about how the document should read are not
        # counted — adoption should not wait on a formatting preference.
        "policy_answered": answered,
        "policy_total": total,
        "can_record_incomplete": _may_record_incomplete(actor),
    }


def _verified_member(actor: Actor) -> bool:
    """A proven, active member of the organization on this request.

    Proven means the address came from the session token issued when a code
    was read out of that mailbox — `actor.email` — never from anything the
    person typed. Active means the container is approved. And it has to be
    the container this request is scoped to: a member of one organization
    is nobody at another.
    """
    if not actor.email:
        return False
    try:
        from app import tenancy, tenant
        here = tenant.current()
        if not here or here == tenant.ANONYMOUS:
            return False
        acc = tenancy.access_for(actor.email)
        return bool(acc.get("allowed")) and acc.get("state") == here
    except Exception:                                         # noqa: BLE001
        return False


def _policy_progress() -> tuple[int, int]:
    try:
        from app import module_one, versions
        return module_one.policy_progress(
            dict(versions.state().get("working") or {}))
    except Exception:                                         # noqa: BLE001
        return 0, 0


def _may_record_incomplete(actor: Actor) -> bool:
    """Whether the completeness gate may be passed with questions open.

    Only for the GAIUS team, and only inside IIA's own test container. The
    gate is the client's own rule — "Record the adoption should be gated:
    available after framework completion" — and it stays exactly that for
    every real organization. The exception exists because the DEMO container
    has to be able to show the adopted state, and the questionnaire has
    grown since it was filled in: its Purpose step did not exist when the
    DEMO answers were written, and neither did step 2. The screen states how
    many questions are open when this is used, and the audit entry records
    who used it.
    """
    try:
        from app import admin, tenancy, tenant
        return (admin.is_admin(actor.email)
                and tenancy.is_shared_test_container(tenant.current()))
    except Exception:                                         # noqa: BLE001
        return False


def api_framework_adopt(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Record that a body with authority adopted the loaded framework.

    Council-only, and audited either way. Recording an adoption is itself a
    governance act — if anyone could do it, the distinction between "loaded" and
    "adopted" would be worth nothing.
    """
    from app import framework
    # `Target.FRAMEWORK`, as the docstring always said. It checked
    # `Target.CONFIG`, which let the Office of Technology through in
    # configuration mode and the Council through in no mode — while the
    # screen drew the button for the Council alone. The rule itself now
    # lives in `authz.ADOPTION_ACTIONS`, shared with the builder.
    decision = guard(actor, Target.FRAMEWORK, "record_framework_adoption",
                     detail={"adopted_on": body.get("adopted_on", "")},
                     verified_member=_verified_member(actor))
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}
    return framework.record_adoption(
        actor_name=actor.name, actor_title=actor.title,
        adopted_on=str(body.get("adopted_on", "")),
        note=str(body.get("note", "")),
    )


def api_framework_export(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The framework as a .docx, for the agency on this request.

    Base64 inside JSON rather than a binary response, for the same reason the
    upload arrives that way: this router returns JSON, and a second response
    path for one endpoint is more to get wrong than a few tens of kilobytes of
    encoding. The browser turns it back into a file.

    Not guarded. Exporting reads the agency's own answers and writes nothing —
    and the whole offer is that the framework is theirs to take away, so
    requiring a capability to take it would contradict the product.
    """
    import base64
    from app import export, versions

    label = _agency_label(actor, params)
    try:
        blob = export.build(label["name"])
    except Exception as exc:                                    # noqa: BLE001
        traceback.print_exc()
        return {"ok": False, "error": f"The document could not be built: {exc}"}
    return {
        "ok": True,
        "filename": export.filename(label["abbrev"]),
        "bytes": len(blob),
        "content": base64.b64encode(blob).decode("ascii"),
        "label": versions.export_label(),
    }


def _agency_label(actor: Actor, params: dict) -> dict[str, str]:
    """The agency's own name for the title page.

    From the tenancy record and the agency registry, never from anything the
    browser asserts — a document that names whoever asked for it is worse than
    one that names nobody.
    """
    from app import states
    code = _caller_agency(actor, params)
    if not code or code == tenant.ANONYMOUS:
        return {"name": "Your organization", "abbrev": ""}
    for state_code in list(states.STATE_NAMES) + [states.FEDERAL_CODE]:
        for a in states.agencies_for(state_code):
            if a.get("id") == code:
                return {"name": a.get("name") or code,
                        "abbrev": a.get("abbrev") or ""}
    return {"name": code, "abbrev": ""}


def api_bug_report(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """File a bug. Deliberately unauthenticated — a broken sign-in is a bug too,
    and the person who most needs to report one is the person who cannot get in.

    Narrow rather than trusted: one append-only record, everything scrubbed and
    bounded server-side, and it reads nothing."""
    from app import bugs
    return bugs.report(
        expected=str(body.get("expected", "")),
        happened=str(body.get("happened", "")),
        context=body.get("context") or {},
        events=body.get("events"),
        reporter=str(body.get("reporter", "")),
        name=str(body.get("name", "")),
        agency=str(body.get("agency", "")),
    )


def api_bugs(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The queue. GAIUS admins see everything; everyone else sees their own.

    This used to key off `actor.is_ot`, which every user can become by picking
    "Office of Technology" from the header dropdown — so the whole queue, across
    every agency, was one click from anyone signed in. That is the client's
    hardest rule broken by an off-by-one in what a role means: OT is authority
    over *your own agency's* configuration, and the queue is everybody's.

    So it keys off the proven address instead. Reading other people's reports is
    running GAIUS, not governing an agency.
    """
    from app import bugs
    # The proved address only, as with the bell. `mine()` returns somebody's own
    # reports, which is the same content the bell hands back and needs the same
    # rule — an address in a query string is a claim, not proof.
    email = (actor.email or "").strip().lower()
    if not admin.is_admin(actor.email):
        return {"team": False, "tickets": bugs.mine(email),
                "counts": {}, "statuses": bugs.STATUSES,
                "note": admin.REFUSAL,
                "summary": bugs.summary()}
    return {"team": True,
            **bugs.listing(status=params.get("status", [""])[0],
                           query=params.get("q", [""])[0]),
            "summary": bugs.summary()}


def api_usage(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Who is using GAIUS, from where, for how long, and how far they got.

    Admin only, on the same terms as the bug queue and for the same reason:
    this reads across every agency, which is the line the rest of the
    application never crosses. So it keys off the *proved* address — the one
    resolved from a session token issued when somebody read a code out of
    their own inbox — and not off a capacity anybody can pick from the header.

    Refused rather than thinned. A half-report showing one agency's own
    figures would look like the page working, and this page is only ever
    about the whole estate.
    """
    if not admin.is_admin(actor.email):
        return {"allowed": False, "note": admin.REFUSAL}
    from app import usage
    wanted = params.get("robots", [""])[0] in ("1", "true", "yes")
    return {"allowed": True, **usage.report(include_robots=wanted)}


def api_notifications(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """What the team has said to this person, and nobody else.

    Keyed on the *proved* address only. It used to fall back to whatever address
    the caller put in the query string, so knowing somebody's work email was
    enough to read the replies on their bug reports — their own words about what
    went wrong, and the team's answers. That fallback existed so browsers signed
    in before session tokens shipped would not find the bell silently empty; it
    has been removed now that signing in issues a token.

    A caller without a token gets an empty list **and is told why**. Returning
    nothing silently is what made the old behavior tempting: an empty bell and
    a broken bell look identical, so the fix looked like a regression. The note
    is what the interface shows instead of a dark bell.
    """
    from app import bugs
    if not actor.email:
        return {"items": [], "total": 0, "signed_in": False,
                "note": "Sign in again to see replies to what you reported. "
                        "This browser has no proof of who it belongs to, and "
                        "these are somebody's own words about a fault — so they "
                        "are not handed out on an address alone."}
    return {**bugs.notifications(actor.email), "signed_in": True}


def api_bug_respond(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Answer a report and move it. Admins only — bugs.respond() checks the
    capacity too, and this checks the identity, which is the half a dropdown
    cannot satisfy."""
    from app import bugs
    if not admin.is_admin(actor.email):
        return {"ok": False, "error": admin.REFUSAL}
    return bugs.respond(str(body.get("id", "")),
                        message=str(body.get("message", "")),
                        status=str(body.get("status", "")), actor=actor)


def api_bug_forget(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Delete a junk ticket. Admins only, and irreversible after the next one.

    `wont_fix` is for a report the team disagrees with. This is for one that
    should not be in the queue at all — a duplicate, an empty message, or a
    test harness's own report. Refusing to have it meant the queue accumulated
    litter nobody could clear without a shell on the server.
    """
    from app import bugs
    if not admin.is_admin(actor.email):
        return {"ok": False, "error": admin.REFUSAL}
    return bugs.forget(str(body.get("id", "")), why=str(body.get("why", "")))


def api_session_end(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Retire a session token. Unauthenticated by design: the only thing anyone
    can do with a token they hold is destroy it, and requiring proof to sign out
    would mean an expired session could not be cleaned up."""
    from app import impersonate
    impersonate.stop(str(body.get("session", "")))   # signing out ends it too
    tenancy.end_session(str(body.get("session", "")))
    return {"ok": True}


def api_bug_reopen(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import bugs
    return bugs.reopen(str(body.get("id", "")),
                       message=str(body.get("message", "")),
                       email=str(body.get("email", "")))


def api_intake(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import intake
    return {**intake.summary(), "can_upload": actor.is_ot or actor.is_council}


def api_intake_upload(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Upload one of the agency's existing policies.

    The file arrives base64-encoded inside the JSON body rather than as
    multipart. This server is stdlib `ThreadingHTTPServer` with a JSON router;
    adding a multipart parser to it for one screen would be more code, and more
    to get wrong, than a few hundred KB of base64.
    """
    from app import intake
    return intake.upload(str(body.get("filename", "")),
                         str(body.get("content", "")), actor,
                         kind=str(body.get("kind", "")))


def api_intake_remove(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import intake
    return intake.remove(str(body.get("filename", "")), actor)


def api_versions(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import decider, versions
    return {**versions.state(),
            "can_save": actor.is_ot or actor.is_council,
            # Adoption is the act the DRAFT label exists to withhold. This was
            # `actor.is_council`, which nobody who signs in holds, so the
            # "Record adoption of version N" button was never drawn. It now
            # asks the same question the endpoint does — see
            # `authz.ADOPTION_ACTIONS`.
            "can_adopt": actor.is_council or _verified_member(actor),
            "adopter": decider.body()}


def _with_spelling(saved: dict[str, Any], *typed: str) -> dict[str, Any]:
    """Add a spelling note to a saved answer, if there is one to add.

    The answer is already stored by the time this runs, exactly as typed.
    Nothing here can change what was recorded — it only attaches a line for
    the screen to offer. See `app/typos.py` for why it offers rather than
    corrects.
    """
    if not saved.get("ok"):
        return saved
    text = " ".join(t for t in typed if t and t.strip())
    if not text.strip():
        return saved
    from app import typos
    spellings = typos.found(text)
    if not spellings:
        return saved
    return {**saved, "spelling": spellings,
            "spelling_note": typos.note(spellings)}


def api_version_answer(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Record one Module One answer. Does not move the version number.

    Validated against `module_one`, which replaced the mined register. Nothing
    here refuses an answer for being the one we would not have picked — the
    spec is firm that "the moment the module refuses something, it becomes
    someone else's framework". The only refusal is a key that does not exist.

    An "I don't know" carries an owner rather than being stored bare: a gap
    with a name against it is auditable, and a blank is not.
    """
    from app import module_one, versions
    key = str(body.get("key", ""))

    # A section's own paragraph is not a question and has no response set —
    # "text goes in verbatim". It is stored under a reserved prefix so it can
    # never collide with a question key, and only for a step that actually
    # offers the box.
    if key.startswith(module_one.OWN_WORDS_PREFIX):
        number = key[len(module_one.OWN_WORDS_PREFIX):]
        step = module_one.by_number(number)
        if step is None or not step.own_words:
            return {"ok": False, "error": f"No section called {number!r}."}
        said = str(body.get("value", "") or "").strip()
        # Their own paragraph is the longest thing anybody types here and the
        # one carried into the document verbatim, so it is the last place a
        # typo should go unmentioned.
        return _with_spelling(versions.answer(key, said, actor), said)

    question = module_one.by_key(key)
    if question is None:
        return {"ok": False, "error": f"No question called {key!r}."}

    value = body.get("value")
    owner = str(body.get("owner", "") or "").strip()
    detail = str(body.get("detail", "") or "").strip()

    # A multi-select can have a follow-up blank against more than one of its
    # options — 6.2d has two — so each is keyed by the option it belongs to.
    # A single shared `detail` let whichever was typed last overwrite the
    # other. Only options this question actually declares are accepted.
    per_option = {}
    for option in question.options:
        if not option.then_text:
            continue
        name = f"detail_{option.value}"
        said = str(body.get(name, "") or "").strip()
        if said:
            per_option[name] = said[:400]

    if value == module_one.UNKNOWN and not question.unknown_ok:
        return {"ok": False,
                "error": "That one needs an answer or nothing at all — leave "
                         "it blank if there is nothing to say."}

    # A question can ask two things at once — "who writes it, and who approves
    # it" — and the second travels with the answer rather than under its own
    # key, so the pair cannot drift apart in the store. Only the field this
    # question actually declares is accepted; a caller cannot invent extras.
    paired = {}
    if question.also:
        name = str(question.also.get("key", ""))
        said = str(body.get(name, "") or "").strip()
        if name and said:
            paired[name] = said

    # Where the answer was taken from one of the organization's own uploaded
    # documents, which passage it came from travels with it — so anybody can
    # later see that this answer is the county's own policy speaking, not
    # something typed or suggested. Only a passage that actually exists in
    # this organization's uploads is accepted.
    source = {}
    named = body.get("from_document")
    if isinstance(named, dict):
        from datetime import datetime, timezone
        from app import intake
        try:
            para = int(named.get("paragraph"))
        except (TypeError, ValueError):
            para = -1
        text = intake.passage(str(named.get("file", "")), para)
        if text:
            source = {"from_document": {
                "file": str(named.get("file"))[:120], "paragraph": para,
                "quote": text[:300] + ("…" if len(text) > 300 else ""),
                "used_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds")}}

    # Stored as a record rather than a bare value where there is more to it
    # than the choice: the owner of a gap, or the detail a "yes" opened up.
    stored: Any = value
    if owner or detail or paired or per_option or source:
        stored = {"value": value, **({"owner": owner} if owner else {}),
                  **({"detail": detail} if detail else {}), **paired,
                  **per_option, **source}

    return _with_spelling(
        versions.answer(key, stored, actor),
        *(v for v in (value, detail, *paired.values(), *per_option.values())
          if isinstance(v, str)))


def api_version_save(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import versions
    return versions.save_version(actor, note=str(body.get("note", "")))


def api_version_adopt(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import projects, versions
    out = versions.adopt(int(body.get("version", 0)), actor,
                         adopted_on=str(body.get("adopted_on", "")),
                         note=str(body.get("note", "")),
                         verified_member=_verified_member(actor))
    # §14 · on the day the framework is adopted, project number one is the
    # tool this organisation is already running: this one.
    if out.get("ok"):
        try:
            projects.seed_gaius(actor)
        except Exception:                                     # noqa: BLE001
            pass
    return out


def api_reset_preview(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import reset
    return {**reset.preview(),
            "can_reset": actor.is_ot or actor.is_council,
            # Said plainly, so the panel can explain rather than refuse with a
            # sentence about operational configuration.
            "why_not": "" if (actor.is_ot or actor.is_council) else
                       "Starting over is irreversible, so it needs the "
                       "Office of Technology capacity — switch it in the "
                       "header. Taking and restoring a copy needs nothing."}


def api_reset(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import reset
    return reset.reset(actor, confirm_phrase=str(body.get("confirm", "")),
                       reason=str(body.get("reason", "")))


# ------------------------------------------------------------- snapshots
#
# Wiping a tenant is a one-way act, and the client wanted to do it repeatedly
# to demo from zero. Take a copy first and he can put a fortnight of answers
# back afterwards. Each of these is scoped to the caller's own container by
# `reset._targets()`, which is the single definition of "this agency's work".

# ------------------------------------------------ the data warehouse module
#
# The client: "Data warehouse module is the foundation on which all
# deployments rest, so that must be robust, reliable and helpful." A paid
# module, so it is gated — but gated with an explanation rather than a 404,
# because a locked door somebody cannot see is indistinguishable from a bug.

NOT_SUBSCRIBED = {
    "available": False,
    # Named for what it means. `subscription: True` read as "you have one" —
    # the opposite of the payload it sits in, and one key away from a screen
    # unlocking itself on the strength of its own refusal.
    "requires_subscription": True,
    "why": "Your framework is free and stays yours. This module is part of "
           "the subscription.",
}


def _paid(payload_fn, what: str = ""):
    """A module that is part of the subscription.

    `what` names the module in the refusal. One shared sentence described the
    data register, which read as a non-sequitur on any other locked screen —
    and the point of explaining a locked door rather than hiding it is lost if
    the explanation is about a different door.
    """
    def gated(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
        if not _subscribed():
            payload = dict(NOT_SUBSCRIBED)
            if what:
                payload["why"] = ("Your framework is free and stays yours. "
                                  f"This module — {what} — is part of the "
                                  "subscription.")
            return payload
        return payload_fn(actor, body, params)
    gated.__name__ = getattr(payload_fn, "__name__", "gated")
    gated.__doc__ = payload_fn.__doc__
    return gated


#: How each paid module names itself when it is shut.
WHAT_IT_IS = {
    "data": "the record of what information you hold, where it lives and "
            "whether a tool can reach it",
    "vendors": "the record of who you buy from, what it costs, and what "
               "those tools could also do",
    "integrity": "the record of every time somebody looked at whether a tool "
                 "works, and every time it went wrong",
    "process": "the written instructions — the route in, the checklists at "
               "each gate, and what to do when a tool is off",
    "oversight": "the record of every decision made under your framework — "
                 "who decided, on what day, and what they attached to it",
    "registry": "the catalog of tools — what each one does, who sells it, "
                "and which parts of your organization already have it",
    "budget": "the record of what each tool costs you, all in, including "
              "what it would cost to leave",
    "vision": "the goals your AI work is meant to serve, and what each "
              "project is doing about them",
}


def _data_labels() -> list[str]:
    """Section 9 exists only where the organization told Oversight it keeps
    its own labels, and has written them."""
    from app import decisions
    try:
        held = decisions._read()
    except Exception:                                         # noqa: BLE001
        return []
    return list(held.get("labels") or []) if held.get("labels_on") else []


def api_holdings(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import catalog, holdings, monitor, projects
    mon = monitor.summary()
    try:
        tools = catalog.all_tools()
    except Exception:                                         # noqa: BLE001
        tools = []
    return {**holdings.surface(answers=_framework_answers(),
                               projects=projects.all_projects(), tools=tools,
                               labels=_data_labels(),
                               checks=mon.get("checks") or {},
                               role=actor.role.value),
            "concerns": holdings.concerns(),
            "monitor": mon}


def api_holding_save(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import holdings
    inputs = holdings.framework_inputs(_framework_answers())
    if not holdings.may_edit_technical(actor.role.value, inputs):
        existing = next((h for h in holdings._read().get("holdings", [])
                         if h.get("id") == body.get("id")), {}) or {}
        for key in holdings.TECHNICAL_FIELDS:
            if key in body and str(body.get(key) or "") != str(
                    existing.get(key) or ""):
                return {"ok": False, "error": holdings.TECHNICAL_REFUSED}
    return holdings.save(body, actor, labels=_data_labels())


def api_holding_confirm(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import holdings
    return holdings.confirm_current(str(body.get("id", "")), actor)


def api_holding_forget(actor: Actor, body: dict,
                       params: dict) -> dict[str, Any]:
    from app import holdings
    return holdings.forget(str(body.get("id", "")), actor)


def api_monitor_check(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Probe one endpoint now, rather than waiting for the sweep.

    Reachability only — see `app/monitor.py`. The endpoint comes from the
    register rather than from the request, so this cannot be used to point the
    server at an address nobody recorded.
    """
    from app import holdings, monitor
    wanted = str(body.get("id", ""))
    row = next((h for h in holdings._read().get("holdings", [])
                if h.get("id") == wanted), None)
    if row is None:
        return {"ok": False, "error": f"No holding {wanted!r}."}
    endpoint = str(row.get("endpoint") or "").strip()
    if not endpoint:
        return {"ok": False,
                "error": "Nothing recorded to check. Add the address of the "
                         "interface to this holding first."}
    result = monitor.probe(endpoint)
    monitor.record(wanted, result)
    return {"ok": True, "result": result, "monitor": monitor.summary()}


def api_monitor_sweep(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import monitor
    return {"ok": True, **monitor.sweep(), "monitor": monitor.summary()}


# ---------------------------------------------------- the vendor registry
#
# The client: "the vendor registry; Module will contain a list of vendors,
# costs, and use case potential." Built after the data register and reading
# from it, because what a vendor can see is the question that makes the rest
# of the entry mean anything.

# ------------------------------------------------------------------ billing
#
# The subscription page and what it writes. Deliberately *not* behind
# `_paid` — a screen that sells the paid modules cannot itself be one of
# them — and deliberately not behind the framework or corpus gates either,
# because somebody has to be able to buy before they have anything.

def api_billing(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import billing, tenant
    return billing.listing(tenant.current())


def api_billing_order(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Raise an order. Nothing about the money is read from the request.

    The client sends which route it wants and nothing else that matters. The
    amount, currency and term come from the plan, server-side, and are frozen
    into the order — so a posted price, a posted total or a posted currency
    is simply not looked at.
    """
    from app import billing, tenant
    return billing.start_order(
        tenant.current(), str(body.get("route", "")), actor,
        note=str(body.get("note", ""))[:400])


def api_billing_plan(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Price the subscription. Admins only — the check is inside `set_plan`,
    where it cannot be bypassed by reaching the function another way."""
    from app import billing
    return billing.set_plan(body, actor)


def api_billing_settle(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Record an invoice as paid. Admins only, reference required, audited."""
    from app import billing
    return billing.settle_invoice(
        str(body.get("order", "")), actor,
        reference=str(body.get("reference", "")),
        amount=body.get("amount"))


def api_beta(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The beta notice's words and version. See `app/beta.py`."""
    from app import beta
    return beta.notice()


def api_beta_acknowledge(actor: Actor, body: dict,
                         params: dict) -> dict[str, Any]:
    """Record that this person read the notice. Audited."""
    from app import beta
    return beta.acknowledge(actor, str(body.get("version", "")))


def api_billing_admin(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Every organization's orders, for the GAIUS team to settle.

    Checked on the proven address, like every other admin endpoint. The rail
    only decides whether the menu item is drawn; this is what decides
    whether anything comes back.
    """
    from app import admin, billing
    if not admin.is_admin(actor.email):
        return {"ok": False, "error": "Only the GAIUS team can see this."}
    return {"ok": True, **billing.admin_listing()}


def api_billing_reconcile(actor: Actor, body: dict,
                          params: dict) -> dict[str, Any]:
    """The daily check that orders, entitlements and payments agree."""
    from app import admin, billing
    if not admin.is_admin(actor.email):
        return {"ok": False, "error": "Only the GAIUS team can reconcile."}
    return {"ok": True, **billing.reconcile()}


def api_vendors(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import checks, module_one, projects, vendors
    answers = _framework_answers()
    required = {t["value"] for t in vendors.required_terms(answers)
                if t["required"]}
    docs, _ = module_one.value_of(answers, "floor.access_docs")

    # Renewing inside their own window, on projects nothing has measured.
    measured = {c.get("project") for c in checks.complete_checks()
                if c.get("gate") == spine.MEASURE}
    renewing = {r["id"] for r in vendors.renewing_soon()}
    unmeasured = set()
    for row in vendors.listing()["vendors"]:
        if row["id"] in renewing and row.get("projects") \
                and not any(p in measured for p in row["projects"]):
            unmeasured.add(row["id"])

    return {**vendors.listing(),
            "findings": vendors.findings(
                required=required,
                requires_staging="staging" in required,
                requires_accessibility_docs=str(docs) == "yes",
                renewals_unmeasured=unmeasured),
            "shared_findings": list(vendors.SHARED_FINDINGS),
            "own_findings": [{"id": f.id, "says": f.says}
                             for f in vendors.OWN_FINDINGS],
            "nothing_to_flag": spine.NOTHING_TO_FLAG,
            "projects": [{"ref": p["ref"], "name": p.get("name", "")}
                         for p in projects.all_projects()],
            "concerns": vendors.concerns(),
            "renewing_soon": vendors.renewing_soon()}


def api_vendor_save(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import vendors
    return vendors.save(body, actor)


def api_vendor_forget(actor: Actor, body: dict,
                      params: dict) -> dict[str, Any]:
    from app import vendors
    return vendors.forget(str(body.get("id", "")), actor)


def api_vendor_change(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Record a change the vendor made — on the vendor entry, and by default
    as a version record on each project it serves."""
    from app import vendors
    return vendors.record_change(
        str(body.get("id", ""))[:40], actor,
        what=str(body.get("what", "")),
        told_on=str(body.get("told_on", ""))[:10],
        not_told=bool(body.get("not_told")),
        open_versions=body.get("open_versions", True) is not False)


# ------------------------------------------------------------- Integrity

def _integrity_surface(viewer: str = "") -> dict[str, Any]:
    from app import catalog, checks, holdings, projects
    try:
        held = holdings.listing().get("holdings", [])
    except Exception:                                         # noqa: BLE001
        held = []
    try:
        tools = catalog.all_tools()
    except Exception:                                         # noqa: BLE001
        tools = []
    try:
        from app import vendors
        vendor_changes = vendors.changes_by_project()
    except Exception:                                         # noqa: BLE001
        vendor_changes = {}
    return checks.surface(answers=_framework_answers(),
                          projects=projects.all_projects(), holdings=held,
                          tools=tools, vendor_changes=vendor_changes,
                          viewer=viewer)


def _integrity_badge() -> dict[str, Any]:
    """1.2 · two numbers, and no nag where the second is zero."""
    found = _integrity_surface()
    return {"entries": len(found["entries"]), "to_fix": len(found["raised"]),
            "badge": found["badge"]}


def api_checks(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """The Integrity register — checks and incidents, one table."""
    from app import public_report
    found = _integrity_surface(viewer=actor.user_id)
    found["decides"] = actor.role == Role.COUNCIL
    link = public_report.link_for(tenant.current())
    found["public_link"] = f"{public_report.PREFIX}{link}" if link else ""
    found["stoppers"] = found["inputs"].get("stoppers", [])
    return found


def _texts(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def api_check_save(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import checks
    watched = {str(k)[:200]: _texts(v, 1000)
               for k, v in (body.get("watched") or {}).items()
               if _texts(v, 1000)} if isinstance(body.get("watched"), dict) \
        else {}
    conditions = [{"what": _texts(c.get("what"), 500),
                   "owner": _texts(c.get("owner"), 200),
                   "by": _texts(c.get("by"), 10), "state": "proposed"}
                  for c in (body.get("conditions") or [])
                  if isinstance(c, dict) and _texts(c.get("what"))]
    segments = [{k: _texts(s.get(k), 300) for k in
                 ("segment", "tried", "did_not_hold", "rule_says")}
                for s in (body.get("segments") or []) if isinstance(s, dict)
                and any(_texts(s.get(k)) for k in
                        ("segment", "tried", "did_not_hold", "rule_says"))]
    def one_of(key: str, allowed: tuple[str, ...]) -> str:
        value = _texts(body.get(key), 200)
        return value if value in allowed else ""
    out = checks.record_check(
        project=_texts(body.get("project"), 40), actor=actor,
        occasion=one_of("occasion", checks.OCCASIONS),
        version=_texts(body.get("version"), 60),
        back_to_first_look=one_of("back_to_first_look",
                                  checks.BACK_TO_FIRST_LOOK),
        at=_texts(body.get("at"), 10), who=_texts(body.get("who"), 200),
        who_name=_texts(body.get("who_name"), 120),
        outside_organisation=_texts(body.get("outside_organisation"), 200),
        tried_on=_texts(body.get("tried_on")),
        holdings=[_texts(h, 60) for h in (body.get("holdings") or [])][:40],
        where=one_of("where", checks.WHERES),
        period=_texts(body.get("period"), 200), found=_texts(body.get("found")),
        limits=_texts(body.get("limits")),
        limits_not_written=bool(body.get("limits_not_written")),
        verdict=one_of("verdict", checks.VERDICTS),
        determination=one_of("determination", checks.DETERMINATIONS),
        against_baseline=one_of("against_baseline", checks.BASELINE_ANSWERS),
        baseline_why_not=_texts(body.get("baseline_why_not"), 500),
        watched=watched,
        manual_way=one_of("manual_way", checks.MANUAL_ANSWERS),
        accessibility=one_of("accessibility", checks.ACCESS_ANSWERS),
        accessibility_fixes=_texts(body.get("accessibility_fixes")),
        stopping_rule_met=one_of("stopping_rule_met", checks.RULE_MET_ANSWERS),
        segments=segments, conditions=conditions,
        attachments=_attached(body),
        corrects=_texts(body.get("corrects"), 40),
        complete=bool(body.get("complete")))
    if out.get("ok") and body.get("have_rule") in checks.RULE_ANSWERS:
        checks.set_stopping_rule(actor=actor, have_one=body["have_rule"],
                                 name=_texts(body.get("rule_name"), 200),
                                 says=_texts(body.get("rule_says")))
    return out


def api_check_complete(actor: Actor, body: dict, params: dict
                       ) -> dict[str, Any]:
    from app import checks
    return checks.mark_complete(_texts(body.get("ref"), 40), actor=actor)


def api_incident_save(actor: Actor, body: dict, params: dict
                      ) -> dict[str, Any]:
    from app import checks
    told = {str(k)[:200]: _texts(v, 10)
            for k, v in (body.get("told") or {}).items()} \
        if isinstance(body.get("told"), dict) else {}
    def one_of(key: str, allowed: tuple[str, ...]) -> str:
        value = _texts(body.get(key), 200)
        return value if value in allowed else ""
    inputs = checks.framework_inputs(_framework_answers())
    levels = {s["label"] for s in inputs.get("severities") or []}
    severity = _texts(body.get("severity"), 200)
    out = checks.report_incident(
        actor=actor, project=_texts(body.get("project"), 40),
        tool=_texts(body.get("tool"), 300),
        what_were_you_using=_texts(body.get("what_were_you_using"), 300),
        what_happened=_texts(body.get("what_happened")),
        at=_texts(body.get("at"), 16),
        first_noticed=_texts(body.get("first_noticed"), 16),
        affected=_texts(body.get("affected")),
        touched_a_person=one_of("touched_a_person", checks.TOUCHED_A_PERSON),
        severity=severity if severity in levels else "",
        stopped=one_of("stopped", (checks.STOPPED_YES, checks.STOPPED_NO,
                                   checks.STOPPED_UNSURE)),
        stopped_at=_texts(body.get("stopped_at"), 16),
        stopped_by=_texts(body.get("stopped_by"), 200),
        told=told, lookback=one_of("lookback", checks.LOOKBACK_ANSWERS),
        lookback_back_to=_texts(body.get("lookback_back_to"), 10),
        cause=_texts(body.get("cause")),
        what_was_done=_texts(body.get("what_was_done")),
        written_up_by=_texts(body.get("written_up_by"), 200),
        written_up_where=_texts(body.get("written_up_where"), 300),
        closed=one_of("closed", (checks.INCIDENT_OPEN, checks.INCIDENT_CLOSED))
        or checks.INCIDENT_OPEN,
        closed_at=_texts(body.get("closed_at"), 10),
        closed_by=_texts(body.get("closed_by"), 200),
        attachments=_attached(body),
        signed_in=True)
    if out.get("ok"):
        out["says"] = checks.after_an_incident(out["incident"],
                                               route=inputs.get("route", ""))
    return out


def _attached(body: dict) -> list[str]:
    """Only files this organization holds, and at most five."""
    from app import attachments
    ids = [str(i)[:40] for i in (body.get("attachments") or [])
           if isinstance(i, str)]
    return attachments.known(ids)[:attachments.MAX_PER_RECORD]


#: 13 · what an edit may change, and how each is cleaned. Anything else sent
#: is dropped.
_EDIT_TEXT = {"tried_on": 4000, "period": 200, "found": 4000, "limits": 4000,
              "what_happened": 4000, "affected": 4000, "cause": 4000,
              "what_was_done": 4000, "written_up_by": 200,
              "written_up_where": 300, "who": 200, "who_name": 120,
              "at": 16, "first_noticed": 16, "baseline_why_not": 500,
              "accessibility_fixes": 4000, "lookback_back_to": 10,
              "closed_at": 10, "closed_by": 200, "tool": 300}


def api_entry_edit(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """13 · Change a check or an incident while it is still being written —
    its author, or whoever decides."""
    from app import checks
    raw = body.get("fields") or {}
    if not isinstance(raw, dict):
        return {"ok": False, "error": "Nothing to change."}
    options = {"verdict": checks.VERDICTS, "where": checks.WHERES,
               "occasion": checks.OCCASIONS,
               "against_baseline": checks.BASELINE_ANSWERS,
               "manual_way": checks.MANUAL_ANSWERS,
               "accessibility": checks.ACCESS_ANSWERS,
               "stopping_rule_met": checks.RULE_MET_ANSWERS,
               "touched_a_person": checks.TOUCHED_A_PERSON,
               "lookback": checks.LOOKBACK_ANSWERS,
               "closed": (checks.INCIDENT_OPEN, checks.INCIDENT_CLOSED)}
    fields: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _EDIT_TEXT:
            fields[key] = _texts(value, _EDIT_TEXT[key])
        elif key in options and value in options[key]:
            fields[key] = value
        elif key == "limits_not_written":
            fields[key] = bool(value)
        elif key == "attachments":
            fields[key] = _attached({"attachments": value})
    return checks.edit_entry(_texts(body.get("ref"), 40), fields, actor=actor,
                             decider=actor.role == Role.COUNCIL)


def api_incident_reopen(actor: Actor, body: dict, params: dict
                        ) -> dict[str, Any]:
    from app import checks
    return checks.reopen_incident(_texts(body.get("ref"), 40), actor=actor,
                                  why=_texts(body.get("why"), 1000))


def api_incident_stop(actor: Actor, body: dict, params: dict
                      ) -> dict[str, Any]:
    """11.8 · Stop it now, for a signed-in person who says they hold one of
    the roles the organization named at 10.5."""
    from app import checks
    if not _verified_member(actor):
        return {"ok": False, "error": "Only a signed-in member of the "
                                      "organization can stop a tool from here."}
    inputs = checks.framework_inputs(_framework_answers())
    return checks.stop_now(_texts(body.get("ref"), 40),
                           role=_texts(body.get("role"), 200), actor=actor,
                           stoppers=inputs.get("stoppers") or [])


def api_attachment_upload(actor: Actor, body: dict, params: dict
                          ) -> dict[str, Any]:
    from app import attachments
    here = tenant.current()
    if not here or here == tenant.ANONYMOUS or not _verified_member(actor):
        return {"ok": False, "error": "Only a signed-in member of the "
                                      "organization can attach a file."}
    return attachments.store_base64(str(body.get("data") or ""),
                                    _texts(body.get("name"), 200),
                                    by=actor.name or actor.user_id,
                                    content_type=_texts(body.get("type"), 100))


def api_attachment_get(actor: Actor, body: dict, params: dict
                       ) -> dict[str, Any]:
    from app import attachments
    here = tenant.current()
    if not here or here == tenant.ANONYMOUS or not _verified_member(actor):
        return {"ok": False, "error": "Only a signed-in member of the "
                                      "organization can open this."}
    return attachments.fetch(params.get("id", [""])[0])


def api_check_recommendation(actor: Actor, body: dict, params: dict
                             ) -> dict[str, Any]:
    from app import checks
    return checks.answer_recommendation(_texts(body.get("entry"), 40),
                                        _texts(body.get("state"), 20),
                                        actor=actor)


def api_public_link(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Issue, replace or stop this organization's public report page."""
    from app import public_report
    here = tenant.current()
    if not here or here == tenant.ANONYMOUS or not _verified_member(actor):
        return {"ok": False, "error": "Only a signed-in member of the "
                                      "organization can do this."}
    if body.get("action") == "stop":
        public_report.stop_link(here, actor)
        return {"ok": True, "public_link": ""}
    token = public_report.make_link(here, actor)
    return {"ok": True, "public_link": f"{public_report.PREFIX}{token}"}


def api_snapshots(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import snapshot
    return snapshot.listing()


def api_snapshot_take(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import snapshot
    return snapshot.take(actor, label=str(body.get("label", "")))


def api_snapshot_restore(actor: Actor, body: dict,
                         params: dict) -> dict[str, Any]:
    from app import snapshot
    return snapshot.restore(str(body.get("id", "")), actor)


def api_snapshot_forget(actor: Actor, body: dict,
                        params: dict) -> dict[str, Any]:
    from app import snapshot
    return snapshot.forget(str(body.get("id", "")), actor)


# ---------------------------------------------------------------------- NDA
#
# These run after mailbox verification and before anything else is reachable,
# so like the registration endpoints above they have no actor to guard against.
# Kept safe the same way: each validates its input, writes one record, and can
# touch nothing but that person's own NDA status.

def _who(body: dict, params: dict) -> str:
    return str(body.get("email")
               or (params.get("email", [""])[0] if params else "")).strip().lower()


def api_nda(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import nda
    email = _who(body, params)
    if not email:
        return {"status": "pending", "may_enter": False,
                "document": nda.document(),
                "error": "No address given, so there is nothing to look up."}
    return nda.status(email)


def api_nda_accept(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import nda
    return nda.accept(_who(body, params),
                      name=str(body.get("name", "")),
                      title=str(body.get("title", "")),
                      agency=str(body.get("agency", "")))


def api_nda_decline(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import nda
    return nda.decline(_who(body, params),
                       name=str(body.get("name", "")),
                       title=str(body.get("title", "")),
                       agency=str(body.get("agency", "")),
                       reason=str(body.get("reason", "")))


def api_nda_unlock(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Lift a lock. IIA's to do, so this one *is* guarded."""
    from app import nda
    decision = guard(actor, Target.CONFIG, "unlock_nda_account",
                     detail={"email": _who(body, params)})
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}
    return nda.unlock(_who(body, params),
                      by=actor.name or actor.user_id,
                      note=str(body.get("note", "")))


def api_nda_admin(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import nda
    return {**nda.summary(), "can_unlock": actor.is_ot or actor.is_council}


def api_portals(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import onboarding
    return onboarding.summary()


def api_register(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Onboarding registration. Deliberately unauthenticated.

    This runs before anyone has identified themselves, so it cannot pass through
    guard() — there is no actor yet. That makes it the one write in the
    application without an authorization check, and it is kept safe by being
    narrow rather than by being trusted: it validates the address, appends a
    single line to its own file, and can neither read what is already there nor
    touch the corpus or the audit log.

    It is also why the same eligibility rule lives in app/onboarding.py rather
    than in the browser. A rule enforced only client-side is advice.
    """
    from app import onboarding
    return onboarding.register(
        email=str(body.get("email", "")),
        portal=str(body.get("portal", "government")),
        organisation=str(body.get("organisation", "")),
    )


ROUTES: dict[tuple[str, str], Callable[..., dict[str, Any]]] = {
    ("GET", "/api/tenancy"): api_tenancy,
    ("GET", "/api/whose-container"): api_whose_container,
    ("POST", "/api/agency/register"): api_register_agency,
    ("POST", "/api/agency/register-unlisted"): api_register_unlisted,
    ("POST", "/api/agency/signin"): api_signin_agency,
    ("POST", "/api/agency/verify"): api_verify_agency,
    ("GET", "/api/agency/access"): api_agency_access,
    ("POST", "/api/agency/approve"): api_agency_approve,
    ("POST", "/api/agency/member"): api_agency_add_member,
    ("GET", "/api/agency/people"): api_agency_people,
    ("POST", "/api/agency/member/remove"): api_agency_remove_member,
    ("POST", "/api/agency/role"): api_agency_role,
    ("GET", "/api/admin/organizations"): api_admin_organizations,
    ("POST", "/api/admin/appoint"): api_admin_appoint,
    ("POST", "/api/admin/member/role"): api_admin_member_role,
    ("POST", "/api/admin/member/remove"): api_admin_member_remove,
    ("POST", "/api/admin/pending/remove"): api_admin_pending_remove,
    ("GET", "/api/terms"): api_terms,
    ("POST", "/api/terms/accept"): api_terms_accept,
    ("POST", "/api/terms/signed"): api_terms_signed,
    ("POST", "/api/admin/terms/received"): api_admin_terms_received,
    ("POST", "/api/me/tour-seen"): api_tour_seen,
    ("POST", "/api/session/renew"): api_session_renew,
    ("POST", "/api/admin/impersonate/start"): api_admin_impersonate_start,
    ("POST", "/api/admin/impersonate/stop"): api_admin_impersonate_stop,
    ("GET", "/api/module"): api_module,
    ("GET", "/api/discretion"): api_discretion,
    ("GET", "/api/framework"): api_framework,
    ("POST", "/api/framework/adopt"): api_framework_adopt,
    ("GET", "/api/portals"): api_portals,
    ("POST", "/api/register"): api_register,
    ("GET", "/api/state"): api_state,
    ("POST", "/api/chat"): api_chat,
    ("GET", "/api/vision"): _corpus_only(api_vision),
    ("GET", "/api/registry"): _corpus_only(api_registry),
    ("GET", "/api/catalog"): _paid(api_catalog, WHAT_IT_IS["registry"]),
    ("GET", "/api/goals"): _paid(api_goals, WHAT_IT_IS["vision"]),
    ("POST", "/api/goals"): _paid(api_goal_save, WHAT_IT_IS["vision"]),
    ("POST", "/api/goals/settle"): _paid(api_goal_settle, WHAT_IT_IS["vision"]),
    ("POST", "/api/goals/public"): _paid(api_goal_public, WHAT_IT_IS["vision"]),
    ("POST", "/api/goals/read"): _paid(api_goal_read, WHAT_IT_IS["vision"]),
    ("POST", "/api/projects/goal"): api_project_goal,
    ("POST", "/api/projects/section"): api_project_section,
    ("POST", "/api/projects/verdicts"): api_project_verdicts,
    ("POST", "/api/projects/close-without-tool"): api_project_close_without_tool,
    ("POST", "/api/projects/version"): api_project_version,
    ("POST", "/api/projects/sunset"): api_project_sunset,
    ("POST", "/api/projects/sunset/close"): api_project_sunset_close,
    ("POST", "/api/projects/list-checked"): api_project_list_checked,
    ("POST", "/api/projects/next-gate"): api_project_next_gate,
    ("GET", "/api/costs"): _paid(api_costs, WHAT_IT_IS["budget"]),
    ("POST", "/api/costs"): _paid(api_cost_save, WHAT_IT_IS["budget"]),
    ("POST", "/api/costs/commit"): _paid(api_cost_commit, WHAT_IT_IS["budget"]),
    ("POST", "/api/costs/status"): _paid(api_cost_status, WHAT_IT_IS["budget"]),
    ("POST", "/api/costs/gap"): _paid(api_cost_gap, WHAT_IT_IS["budget"]),
    ("POST", "/api/costs/difference"): _paid(api_cost_difference,
                                             WHAT_IT_IS["budget"]),
    ("POST", "/api/catalog"): _paid(api_catalog_save, WHAT_IT_IS["registry"]),
    ("POST", "/api/catalog/seed"): _paid(api_catalog_seed,
                                         WHAT_IT_IS["registry"]),
    ("GET", "/api/project"): api_project,
    ("GET", "/api/config"): api_config,
    ("POST", "/api/config/preview"): api_config_preview,
    ("POST", "/api/config/edit"): api_config_edit,
    ("GET", "/api/budget"): _corpus_only(api_budget),
    ("POST", "/api/budget/scenario"): api_budget_scenario,
    ("GET", "/api/process"): _paid(api_process, WHAT_IT_IS["process"]),
    ("POST", "/api/procedures"): _paid(api_procedure_save,
                                       WHAT_IT_IS["process"]),
    ("POST", "/api/procedures/status"): _paid(api_procedure_status,
                                              WHAT_IT_IS["process"]),
    ("POST", "/api/procedures/confirm"): _paid(api_procedure_confirm,
                                               WHAT_IT_IS["process"]),
    ("POST", "/api/procedures/tried"): _paid(api_procedure_tried,
                                             WHAT_IT_IS["process"]),
    ("POST", "/api/procedures/event"): _paid(api_procedure_event,
                                             WHAT_IT_IS["process"]),
    ("POST", "/api/procedures/move"): _paid(api_procedure_move,
                                            WHAT_IT_IS["process"]),
    ("POST", "/api/procedures/seed"): _paid(api_procedure_seed,
                                            WHAT_IT_IS["process"]),
    # A read and nothing else. There is deliberately no POST here: the
    # Lifecycle page has no store behind it.
    ("GET", "/api/lifecycle"): api_lifecycle,
    ("GET", "/api/projects"): api_projects,
    ("POST", "/api/projects/start"): api_project_start,
    ("POST", "/api/projects/move"): api_project_move,
    ("POST", "/api/projects/state"): api_project_state,
    ("POST", "/api/projects/accountable"): api_project_accountable,
    ("POST", "/api/projects/point"): api_project_point,
    ("POST", "/api/projects/level"): api_project_level,
    ("POST", "/api/projects/restart"): api_project_restart,
    ("POST", "/api/bugs/report"): api_bug_report,
    ("GET", "/api/bugs"): api_bugs,
    ("GET", "/api/notifications"): api_notifications,
    ("POST", "/api/bugs/respond"): api_bug_respond,
    ("POST", "/api/bugs/reopen"): api_bug_reopen,
    ("POST", "/api/bugs/forget"): api_bug_forget,
    ("POST", "/api/session/end"): api_session_end,
    ("GET", "/api/framework/export"): api_framework_export,
    ("GET", "/api/intake"): api_intake,
    ("POST", "/api/intake/upload"): api_intake_upload,
    ("POST", "/api/intake/remove"): api_intake_remove,
    ("GET", "/api/nda"): api_nda,
    ("POST", "/api/nda/accept"): api_nda_accept,
    ("POST", "/api/nda/decline"): api_nda_decline,
    ("POST", "/api/nda/unlock"): api_nda_unlock,
    ("GET", "/api/nda/admin"): api_nda_admin,
    ("GET", "/api/versions"): api_versions,
    ("POST", "/api/versions/answer"): api_version_answer,
    ("POST", "/api/versions/save"): api_version_save,
    ("POST", "/api/versions/adopt"): api_version_adopt,
    ("GET", "/api/usage"): api_usage,
    ("GET", "/api/reset"): api_reset_preview,
    ("POST", "/api/reset"): api_reset,
    ("GET", "/api/holdings"): _paid(api_holdings, WHAT_IT_IS["data"]),
    ("POST", "/api/holdings"): _paid(api_holding_save, WHAT_IT_IS["data"]),
    ("POST", "/api/holdings/forget"): _paid(api_holding_forget,
                                            WHAT_IT_IS["data"]),
    ("POST", "/api/holdings/confirm"): _paid(api_holding_confirm,
                                             WHAT_IT_IS["data"]),
    ("POST", "/api/holdings/check"): _paid(api_monitor_check,
                                           WHAT_IT_IS["data"]),
    ("POST", "/api/holdings/sweep"): _paid(api_monitor_sweep,
                                           WHAT_IT_IS["data"]),
    # Billing is not itself a paid module — see `api_billing`.
    ("GET", "/api/billing"): api_billing,
    ("POST", "/api/billing/order"): api_billing_order,
    ("POST", "/api/billing/plan"): api_billing_plan,
    ("POST", "/api/billing/settle"): api_billing_settle,
    ("GET", "/api/billing/reconcile"): api_billing_reconcile,
    ("GET", "/api/billing/admin"): api_billing_admin,
    ("GET", "/api/beta"): api_beta,
    ("POST", "/api/beta/acknowledge"): api_beta_acknowledge,
    # /api/billing/webhook is handled in `_dispatch` before the JSON parse,
    # because its signature covers the raw bytes. It is not in this table.
    ("GET", "/api/vendors"): _paid(api_vendors, WHAT_IT_IS["vendors"]),
    ("POST", "/api/vendors"): _paid(api_vendor_save, WHAT_IT_IS["vendors"]),
    ("POST", "/api/vendors/forget"): _paid(api_vendor_forget,
                                           WHAT_IT_IS["vendors"]),
    ("POST", "/api/vendors/change"): _paid(api_vendor_change,
                                           WHAT_IT_IS["vendors"]),
    ("GET", "/api/snapshots"): api_snapshots,
    ("POST", "/api/snapshots"): api_snapshot_take,
    ("POST", "/api/snapshots/restore"): api_snapshot_restore,
    ("POST", "/api/snapshots/forget"): api_snapshot_forget,
    ("GET", "/api/decider"): api_decider,
    ("POST", "/api/decider/answer"): api_decider_answer,
    ("GET", "/api/council"): _corpus_only(api_council),
    ("POST", "/api/council/adopt"): api_council_adopt,
    ("POST", "/api/council/decide"): api_council_decide,
    ("GET", "/api/oversight"): _paid(api_oversight, WHAT_IT_IS["oversight"]),
    ("POST", "/api/decisions"): _paid(api_decision_save,
                                      WHAT_IT_IS["oversight"]),
    ("POST", "/api/decisions/condition/close"): _paid(
        api_condition_close, WHAT_IT_IS["oversight"]),
    ("POST", "/api/decisions/labels"): _paid(api_labels,
                                             WHAT_IT_IS["oversight"]),
    ("GET", "/api/search"): api_search,
    ("GET", "/api/audit"): api_audit,
    ("POST", "/api/trail/elsewhere"): api_trail_elsewhere,
    ("POST", "/api/trail/note"): api_trail_note,
    ("POST", "/api/trail/correct"): api_trail_correct,
    ("POST", "/api/trail/produce"): api_trail_produce,
    ("GET", "/api/states"): api_states,
    ("GET", "/api/profile"): api_profile,
    ("POST", "/api/profile/rediscover"): api_profile_rediscover,
    ("GET", "/api/integrity"): _corpus_only(api_integrity),
    ("GET", "/api/checks"): _paid(api_checks, WHAT_IT_IS["integrity"]),
    ("POST", "/api/checks"): _paid(api_check_save, WHAT_IT_IS["integrity"]),
    ("POST", "/api/checks/complete"): _paid(api_check_complete,
                                            WHAT_IT_IS["integrity"]),
    ("POST", "/api/incidents"): _paid(api_incident_save,
                                      WHAT_IT_IS["integrity"]),
    ("POST", "/api/entries/edit"): _paid(api_entry_edit,
                                         WHAT_IT_IS["integrity"]),
    ("POST", "/api/incidents/reopen"): _paid(api_incident_reopen,
                                             WHAT_IT_IS["integrity"]),
    ("POST", "/api/incidents/stop"): _paid(api_incident_stop,
                                           WHAT_IT_IS["integrity"]),
    ("POST", "/api/attachments"): _paid(api_attachment_upload,
                                        WHAT_IT_IS["integrity"]),
    ("GET", "/api/attachments/get"): _paid(api_attachment_get,
                                           WHAT_IT_IS["integrity"]),
    ("POST", "/api/checks/public-link"): _paid(api_public_link,
                                               WHAT_IT_IS["integrity"]),
    ("POST", "/api/checks/recommendation"): _paid(api_check_recommendation,
                                                  WHAT_IT_IS["integrity"]),
    ("GET", "/api/vocabulary"): api_vocabulary,
    ("POST", "/api/vocabulary/preview"): api_vocabulary_preview,
    ("POST", "/api/vocabulary/set"): api_vocabulary_set,
}


class Handler(BaseHTTPRequestHandler):
    # Sent as the `Server:` header on every single response, including to
    # anybody scanning the public internet. This said "SCDES-AI-Governance",
    # which put one agency's name on every byte the product served — the same
    # mistake as the browser title, in a place nothing was looking.
    #
    # Version dropped too: announcing the exact Python build to a stranger is
    # free reconnaissance and buys nothing.
    server_version = "GoverningAI"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:      # quieter console
        # str(): send_error logs an HTTPStatus here, not the request line.
        if "/api/" in (str(args[0]) if args else ""):
            return
        super().log_message(fmt, *args)

    # -- plumbing ---------------------------------------------------------

    def _send(self, status: int, payload: bytes, content_type: str,
              cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        # On every response, not only the HTML. A `noindex` meta tag cannot
        # travel on an exported .docx or a JSON payload, and both are served
        # from this host — an indexed framework document would be a client's
        # draft policy in a search result.
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        # Cheap and standard. Nothing here should be framed by another site,
        # and a browser guessing at a content type it was already given is how
        # an uploaded file gets executed as something else.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, data: dict[str, Any], status: int = 200) -> None:
        self._send(status, json.dumps(data, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        ctype, _ = mimetypes.guess_type(str(target))
        # The dictation runtime is 60 MB and changes when its filename changes.
        # `no-store` on that would re-download it every visit, which is the
        # difference between a one-time cost and an unusable feature.
        cache = LONG_CACHE if path.startswith(LONG_CACHE_PREFIX) else "no-store"
        self._send(200, target.read_bytes(),
                   ctype or "application/octet-stream", cache)

    def _stripe_webhook(self) -> None:
        """Stripe's payment confirmation — see billing.stripe_event. The same
        rules as the provider webhook below: raw bytes, no signed-in user, and
        the status code is part of the protocol (200 when dealt with, 400 when
        the signature is wrong, so Stripe retries a real one and not a forgery)."""
        from app import billing
        length = int(self.headers.get("Content-Length") or 0)
        if length > 256 * 1024:
            self._json({"error": "That body is too large to be an event."}, 413)
            return
        raw = self.rfile.read(length) if length else b""
        out = billing.stripe_event(raw, self.headers.get("Stripe-Signature", ""))
        self._json(out, 200 if out.get("ok") or out.get("unmatched") else 400)

    def _webhook(self) -> None:
        """A provider's payment confirmation.

        Handled before the JSON parse and outside the normal route table,
        because it is a different kind of request in three ways that all
        matter:

        * The signature covers the **raw bytes**. `_dispatch` parses the body
          into a dict and throws the bytes away, and verifying a re-serialized
          copy is the classic way to make a signature check pass for a body
          that is not the one that was signed.
        * There is no signed-in user. The provider is not a person and has no
          agency, so binding a tenant would be meaningless.
        * The status code is part of the protocol. A duplicate has to answer
          200 or the provider retries it for ever; a bad signature has to
          answer 400.
        """
        from app import billing
        length = int(self.headers.get("Content-Length") or 0)
        if length > 256 * 1024:
            self._json({"error": "That body is too large to be an event."},
                       413)
            return
        raw = self.rfile.read(length) if length else b""

        out = billing.handle_event(
            raw,
            self.headers.get("X-GAIUS-Signature", ""),
            self.headers.get("X-GAIUS-Timestamp", ""),
        )
        # 200 for anything we have dealt with — including a duplicate and an
        # event type we deliberately ignore — so the provider stops resending
        # it. 400 only where the request itself was not acceptable.
        self._json(out, 200 if out.get("ok") else 400)

    def _public_report(self, method: str, token: str) -> None:
        """Integrity 16E — the incident page for somebody with no login.

        Outside the route table for the webhook's reasons: no signed-in
        person, a form body rather than JSON, and HTML back rather than
        JSON, so that it works with JavaScript switched off.
        """
        from app import public_report
        token = token.strip("/")
        page = "text/html; charset=utf-8"
        if method == "GET":
            body = public_report.form(token)
            status = 200 if public_report.agency_for(token) else 404
            self._send(status, body.encode("utf-8"), page)
            return
        if method != "POST":
            self._send(405, b"", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > public_report.MAX_BODY:
            self._send(413, public_report.not_found().encode("utf-8"), page)
            return
        raw = self.rfile.read(length) if length else b""
        # Behind the proxy every request arrives from loopback; the proxy's
        # header is the only address worth limiting on. Where there is none
        # the per-address limit is skipped rather than applied to everybody
        # at once, and the per-page daily limit still holds.
        peer = self.client_address[0] if self.client_address else ""
        forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[-1]
        address = forwarded.strip() if peer in ("127.0.0.1", "::1") else peer
        status, body = public_report.submit(
            token, raw, address, self.headers.get("Content-Type") or "")
        self._send(status, body.encode("utf-8"), page)

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if method == "POST" and parsed.path == "/api/billing/webhook":
            self._webhook()
            return
        if method == "POST" and parsed.path == "/api/billing/stripe":
            self._stripe_webhook()
            return

        from app import public_report
        if parsed.path.startswith(public_report.PREFIX):
            self._public_report(method, parsed.path[len(public_report.PREFIX):])
            return

        route = ROUTES.get((method, parsed.path))

        if route is None:
            if method == "GET":
                self._static(parsed.path)
            else:
                self._json({"error": f"no route for {method} {parsed.path}"}, 404)
            return

        body: dict[str, Any] = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            # Nothing a screen sends is this large; an attachment is the
            # biggest thing, and it is capped well below this.
            if length > MAX_JSON_BODY:
                self._json({"error": "That is too large to send."}, 413)
                return
            if length:
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    self._json({"error": "invalid JSON body"}, 400)
                    return

        actor = actor_for(params, self.headers)
        # View as (app/impersonate.py). Only a GAIUS admin's own proven
        # session can carry one; while it does, this request is answered as
        # the person being viewed, in their organization, and writes are
        # refused below. Nothing about the person's own sessions changes.
        from app import impersonate
        session_token = (params.get("session", [None])[0]
                         or self.headers.get("X-GAIUS-Session") or "")
        viewing = (impersonate.for_session(session_token, actor.email)
                   if actor.email else None)
        if viewing:
            actor = replace(actor, email=viewing["email"],
                            name=viewing["name"], title=viewing["title"])
            params = {**params, "email": [viewing["email"]]}
        seen = impersonate.set_current(viewing, session_token)
        # Bound for the life of this request only. Every module that reads the
        # agency's own governance state resolves its path through this — see
        # app/tenant.py — so a handler that forgets to ask still cannot be
        # handed another agency's file. Reset in `finally` because this is a
        # threading server and the thread is reused.
        token = tenant.set_current(_caller_agency(actor, params))
        # Where the person is, for the dates this request stamps. Minutes
        # east of UTC, from the browser; see app/clock.py.
        tick = clock.set_offset(self.headers.get("X-GAIUS-UTC-Offset"))
        try:
            blocked = impersonate.refused(method, parsed.path)
            if blocked:
                self._json(blocked, 403)
                return
            unaccepted = _terms_gate(method, parsed.path, actor, viewing)
            if unaccepted:
                self._json(unaccepted, 403)
                return
            unproven = _proven_session_gate(method, parsed.path, actor, params)
            if unproven:
                self._json(unproven, 401)
                return
            nowhere = _no_organization_gate(method, parsed.path)
            if nowhere:
                self._json(nowhere, 401)
                return
            self._json(route(actor, body, params))
        except KeyError as exc:
            self._json({"error": f"not found: {exc}"}, 404)
        except Exception as exc:                                # noqa: BLE001
            traceback.print_exc()
            # Kept for the development team's daily report; see
            # app/techreport.py. Where and what — never the request body.
            from app import techreport
            techreport.note_server_error(f"{method} {parsed.path}", exc,
                                         tenant.current())
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        finally:
            clock.reset(tick)
            tenant.reset(token)
            impersonate.reset(seen)

    def do_GET(self) -> None:      # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:     # noqa: N802
        self._dispatch("POST")


def ensure_seeded() -> None:
    """First run: bootstrap config, seed the pipeline, build the index."""
    config_mod.bootstrap()
    vision.ensure_defaults()
    council.members()
    ot = ROSTER["sean.ot"]
    if not registry.load_all():
        registry.seed(ot)
    if not budget_mod.load_quotes():
        budget_mod.seed(ot)
    retrieval.get_index()
    # Retention is a number, not an intention. Attached technical capture past
    # the window is dropped here; the tickets themselves stay.
    try:
        from app import bugs
        dropped = bugs.purge()
        if dropped["purged"]:
            print(f"  bug capture purged from {dropped['purged']} ticket(s) "
                  f"older than {dropped['retention_days']} days")
    except Exception:
        pass


def serve(host: str = HOST, port: int = PORT) -> None:
    # A local .env, if there is one. The server on the box gets its secrets
    # from /etc/governingai.env via systemd and this finds nothing; a laptop
    # has no systemd unit, and without this the alternative is exporting keys
    # by hand or — what actually happens — pasting them into a script.
    #
    # Names only in the line below. Never the values.
    from app import env as env_file
    took = env_file.load()
    if took:
        print(f"  .env: {', '.join(took)}")

    ensure_seeded()

    # The accessibility monitor, on a clock. Only where somebody is paying
    # for it — it is part of the paid module, and a deployment nobody has
    # bought should not be making outbound requests on anybody's behalf.
    #
    # Asked of the deployment, not of a tenant: this runs before any request
    # exists, so there is no agency bound to ask about. `_subscribed()` would
    # have resolved `tenant.current()` to whatever the default is and
    # answered a different question than the one being asked.
    #
    # Started here rather than at import, so the tests and the CLI tools do
    # not each spawn a thread that quietly probes the internet.
    import os
    from app import billing
    if (os.getenv("IIA_SUBSCRIPTION", "").strip() in ("1", "true", "yes")
            or billing.anyone_entitled()):
        from app import monitor
        monitor.start()

    # The development team's daily technical report: 5 PM Eastern, only on
    # days somebody reported a bug. See app/techreport.py.
    from app import techreport
    techreport.start()

    httpd = ThreadingHTTPServer((host, port), Handler)
    # Not "SCDES AI Governance". The rule that no agency's name appears where
    # it was not put deliberately applies to the console too — this line ends
    # up in journalctl, in screenshots of a terminal, and in the runbook.
    print(f"\n  Governing AI — http://{host}:{port}")
    print(f"  mode: {mode_mod.current().label}")
    print(f"  provider: {describe_provider(get_provider())}")
    print("  Ctrl-C to stop\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()




