"""Registry — what is out there, and what you already have.

The catalog somebody searches when they have a defined problem and need to
know what would solve it. A person finishes the problem walkthrough at
Identify and arrives here with one question: is there already something that
does this? The answer decides whether this organization spends money.

**The unit is one tool** — a product, and what it does. The supplier is the
unit on Vendors, because one supplier sells several tools and a tool can have
no supplier at all where somebody built it. The job is the unit on Projects,
because the same tool doing two jobs is two projects and one catalog row. The
catalog counts products and Projects counts what this organization runs, and
they are separate lists on purpose.

**The field that makes this worth building is `held_by`** — which units
already hold each tool, and what they use it for. A unit with a problem does
not know what the unit down the hall already owns, and that is the most
expensive ignorance in a government. Module One says it in its own words at
question 8.6: most organizations do not realize the cross-utilization
capabilities of the AI tools already in place. Every other field here is
bookkeeping.

**It gates nothing.** No project is refused for anything recorded or missing
here. What the catalog returns is advice, and a person decides what to do
with it. The application never recommends a vendor: it shows what is in the
catalog, in hierarchy order, and a person chooses.

Named `catalog` rather than `registry` because `app/registry.py` already
holds the older concept — the list of what one organization runs, with the
Identify gate attached. That was two jobs under one name, and the list of
what an organization runs is now Projects. This module is the catalog half.
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from typing import Any

from app import spine
from app.audit import atomic_write

FILENAME = "catalog.json"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file():
    from app import tenant
    from app.audit import CORPUS
    return tenant.scoped(CORPUS / "config" / FILENAME)


def _read() -> dict[str, Any]:
    path = _file()
    if not path.is_file():
        return {"tools": {}}
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tools": {}}
    if not isinstance(held, dict):
        return {"tools": {}}
    held.setdefault("tools", {})
    return held


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


def _record(action: str, actor: Any, detail: dict[str, Any]) -> None:
    try:
        from app.authz import default_log
        default_log().append(
            actor=getattr(actor, "user_id", "") or "unknown",
            role=getattr(getattr(actor, "role", None), "value", "")
            or "system",
            action=action, target="Registry", outcome="allowed",
            detail={**detail,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120]})
    except Exception:                                         # noqa: BLE001
        pass


# ===========================================================================
# The record
# ===========================================================================

#: How a tool could be obtained without a fresh purchase. Drives search band
#: three, which answers step 4 of the hierarchy.
ON_COOPERATIVE = "cooperative"
ON_OTHER_GOVERNMENT = "another_government"
FROM_SISTER_AGENCY = "sister_agency"
FROM_THE_STATE = "the_state"
PIGGYBACK_ROUTES = (ON_OTHER_GOVERNMENT, ON_COOPERATIVE, FROM_SISTER_AGENCY,
                    FROM_THE_STATE)

ROUTE_LABELS = {
    ON_OTHER_GOVERNMENT: "On another government's agreement",
    ON_COOPERATIVE: "On a cooperative purchase",
    FROM_SISTER_AGENCY: "From a sister agency",
    FROM_THE_STATE: "From the state",
}

#: 6.3 · the two answers besides naming a supplier on Vendors.
BUILT_HERE = "Built here"
CAME_WITH = "Nobody — it came with something else"

#: 6.4 · where it stands with you.
STANDINGS = ("We hold this", "Available to us on an agreement",
             "We looked at it and turned it down", "We have not looked at it",
             "We used to have it")
AVAILABLE = STANDINGS[1]

#: 6.6 · how much AI is in it — the same words Vendors uses.
INVOLVEMENT = ("AI is what the product is",
               "AI is one feature inside a product that does other things",
               "The vendor added AI to something we already had",
               "No AI in it that we know of", "We are not sure")

#: The fields an edit may change. Anything else sent is dropped.
EDITABLE = ("name", "does", "supplier", "vendor", "standing", "availability",
            "involvement", "held_by", "could_also", "needs_holdings",
            "projects", "general_purpose")

#: Whether this is a general-purpose tool under the organisation's own scope
#: answers at Module One 3.1 and 3.2. Recorded here, never inferred; Integrity
#: 4.13 reads it, and where it is unanswered that finding is not computed.
GENERAL_PURPOSE = ("Yes", "No", "We are not sure")


def _reference(existing: set[str]) -> str:
    for _ in range(64):
        ref = "T-" + "".join(secrets.choice("23456789BCDFGHJKMNPQRSTVWXYZ")
                             for _ in range(6))
        if ref not in existing:
            return ref
    return "T-" + secrets.token_hex(6).upper()


def add(name: str, actor: Any, *, does: str = "", supplier: str = "",
        availability: list[str] | None = None,
        seeded: bool = False) -> dict[str, Any]:
    """Only the name is required.

    A catalog that refuses a row until every box is filled is one nobody
    finishes. Come back and add the rest as you learn it.
    """
    name = str(name or "").strip()
    if not name:
        return {"ok": False, "error": "The product name is the one thing "
                                      "this needs."}
    with _LOCK:
        held = _read()
        ref = _reference(set(held["tools"]))
        row = {
            "ref": ref,
            "name": name,
            "does": does.strip(),
            "supplier": supplier.strip(),
            # [{"unit": ..., "used_for": ...}] — the field the surface
            # exists for.
            "held_by": [],
            "availability": list(availability or []),
            "standing": "",
            "projects": [],
            "added": _now(),
            "seeded": seeded,
        }
        held["tools"][ref] = row
        _write(held)
    _record("event.record_created", actor, {"tool": ref, "name": name})
    return {"ok": True, "tool": row}


def hold(ref: str, unit: str, actor: Any, *,
         used_for: str = "") -> dict[str, Any]:
    """Record that a unit here holds this tool, and what they use it for.

    One line on what they do with it is frequently what stops a purchase:
    "the planning office has this and uses it for permit summaries."
    """
    unit = str(unit or "").strip()
    if not unit:
        return {"ok": False, "error": "Name the unit that holds it."}
    with _LOCK:
        held = _read()
        row = held["tools"].get(ref)
        if row is None:
            return {"ok": False, "error": f"No tool {ref!r}."}
        for existing in row["held_by"]:
            if existing["unit"].lower() == unit.lower():
                existing["used_for"] = used_for.strip()
                break
        else:
            row["held_by"].append({"unit": unit,
                                   "used_for": used_for.strip()})
        _write(held)
    _record("event.field_changed", actor,
            {"tool": ref, "field": "held_by", "unit": unit})
    return {"ok": True, "tool": row}


def update(ref: str, actor: Any, **fields: Any) -> dict[str, Any]:
    """Change what is recorded about a tool. Every hat may, on purpose: this
    is the surface most likely to be wrong because somebody did not know, and
    if only one role could correct it most of those errors would stay."""
    changes = {k: v for k, v in fields.items() if k in EDITABLE}
    if "name" in changes and not str(changes["name"] or "").strip():
        return {"ok": False, "error": "The product name is the one thing "
                                      "this needs."}
    if changes.get("standing") and changes["standing"] not in STANDINGS:
        changes["standing"] = ""
    if changes.get("involvement") and changes["involvement"] not in INVOLVEMENT:
        changes["involvement"] = ""
    if changes.get("general_purpose") and \
            changes["general_purpose"] not in GENERAL_PURPOSE:
        changes["general_purpose"] = ""
    if "availability" in changes:
        changes["availability"] = [a for a in (changes["availability"] or [])
                                   if a in PIGGYBACK_ROUTES]
    if "held_by" in changes:
        seen, rows = set(), []
        for h in changes["held_by"] or []:
            unit = str((h or {}).get("unit") or "").strip()
            if unit and unit.lower() not in seen:
                seen.add(unit.lower())
                rows.append({"unit": unit[:200],
                             "used_for": str(h.get("used_for") or "").strip()[:300],
                             "ask": str(h.get("ask") or "").strip()[:200]})
        changes["held_by"] = rows
    with _LOCK:
        held = _read()
        row = held["tools"].get(ref)
        if row is None:
            return {"ok": False, "error": f"No tool {ref!r}."}
        for key, value in changes.items():
            row[key] = value.strip() if isinstance(value, str) else value
        _write(held)
    _record("event.field_changed", actor,
            {"tool": ref, "fields": sorted(changes)})
    return {"ok": True, "tool": row}


def all_tools() -> list[dict[str, Any]]:
    return list(_read()["tools"].values())


def one(ref: str) -> dict[str, Any] | None:
    return _read()["tools"].get(ref)


# ===========================================================================
# The search, and why it is ordered the way it is
# ===========================================================================

#: Results come back in hierarchy order, in four labelled bands. The
#: ordering is how this surface gives its guidance — the spine sets six
#: steps and this surface answers four of them, in that sequence rather than
#: by relevance, price or alphabet.
BAND_ALREADY_RUN = "You already run this"
BAND_ANOTHER_UNIT = "Another unit here has this"
BAND_PIGGYBACK = "Available on an agreement you could use"
BAND_WOULD_BUY = "Something you would buy"

BANDS = (BAND_ALREADY_RUN, BAND_ANOTHER_UNIT, BAND_PIGGYBACK,
         BAND_WOULD_BUY)

#: Which hierarchy step each band answers, so the ordering can be checked
#: against the spine rather than trusted.
BAND_STEPS = {BAND_ALREADY_RUN: 2, BAND_ANOTHER_UNIT: 3,
              BAND_PIGGYBACK: 4, BAND_WOULD_BUY: 6}

EMPTY_BAND = {
    BAND_ALREADY_RUN: "Nothing you already run would do this.",
    BAND_ANOTHER_UNIT: "Nothing another unit here has would do this.",
    BAND_PIGGYBACK: "Nothing is available on an agreement you could use.",
    BAND_WOULD_BUY: "Nothing in the catalog you would have to buy.",
}


def _matches(tool: dict[str, Any], terms: str) -> bool:
    if not terms.strip():
        return True
    hay = " ".join([tool.get("name", ""), tool.get("does", ""),
                    tool.get("supplier", "")]
                   + [h.get("used_for", "") for h in tool.get("held_by", [])]
                   ).lower()
    return all(word in hay for word in terms.lower().split())


def search(terms: str = "", *, unit: str = "",
           one_unit_organisation: bool = False) -> list[dict[str, Any]]:
    """The four bands, in hierarchy order, each labeled and never collapsed.

    Nothing is ranked within a band. No relevance score, no star, no
    recommended badge. Ranking candidate solutions happens at a purchase
    decision, on the organization's own weights, with the working shown —
    and it happens on the project, not here.

    Where a band is empty it says so rather than closing up. An empty second
    band is itself an answer.
    """
    unit = (unit or "").strip().lower()
    found = [t for t in all_tools() if _matches(t, terms)]

    mine, theirs, piggyback, buy = [], [], [], []
    for tool in found:
        units = [h.get("unit", "") for h in tool.get("held_by", [])]
        lowered = [u.lower() for u in units]
        # With one unit, anything held is held by the person searching.
        if (unit and unit in lowered) or (one_unit_organisation and units):
            mine.append(tool)
        elif units:
            theirs.append(tool)
        elif tool.get("availability"):
            piggyback.append(tool)
        else:
            buy.append(tool)

    bands = [
        {"band": BAND_ALREADY_RUN, "step": 2, "tools": mine},
        {"band": BAND_ANOTHER_UNIT, "step": 3, "tools": theirs},
        {"band": BAND_PIGGYBACK, "step": 4, "tools": piggyback},
        {"band": BAND_WOULD_BUY, "step": 6, "tools": buy},
    ]
    for row in bands:
        row["empty_says"] = EMPTY_BAND[row["band"]]
    # In an organisation with one unit this band does not appear, and its
    # absence is never explained.
    if one_unit_organisation:
        bands = [b for b in bands if b["band"] != BAND_ANOTHER_UNIT]
    return bands


#: The application never recommends a vendor. Stated on the surface rather
#: than only in the specification.
NEVER_RECOMMENDS = ("This shows what is in your catalog, in the order the "
                    "hierarchy asks you to look. It does not recommend a "
                    "product and it does not rank them.")


# ===========================================================================
# The stat row
# ===========================================================================

def counters(rows: list[dict[str, Any]] | None = None, *,
             one_unit_organisation: bool = False) -> dict[str, Any]:
    rows = all_tools() if rows is None else rows

    held = [t for t in rows if t.get("held_by")]
    shared = [t for t in rows if len(t.get("held_by") or []) >= 2]
    unexplained = [t for t in rows if not str(t.get("does") or "").strip()]
    ungoverned = [t for t in held if not t.get("projects")]

    out = {
        "in_catalog": len(rows),
        "you_already_have": len(held),
        "held_by_more_than_one": len(shared),
        "nobody_said_what_it_does": len(unexplained),
        "held_on_no_project": len(ungoverned),
        "says": {
            "held_by_more_than_one":
                "A tool two units already use is a tool a third unit "
                "probably does not know about.",
            "held_on_no_project":
                "These are things you have that nothing on your list "
                "explains. That is the ordinary way this starts.",
        },
    }
    if one_unit_organisation:
        # The cross-utility counter is meaningless with one unit, and its
        # absence is never explained.
        out.pop("held_by_more_than_one")
        out["says"].pop("held_by_more_than_one")
    return out


# ===========================================================================
# Findings
# ===========================================================================

SHARED_FINDINGS = ("finding.gap_no_owner",)

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.rg.held_ungoverned", "Registry",
        "The organization holds a tool and no project references it",
        "[Unit] has this and nothing on your list accounts for it."),
    spine.Finding(
        "finding.rg.paid_not_listed", "Registry",
        "A Vendors entry marked in use today with AI in it, with no catalog "
        "entry linked",
        "[Product] is on your Vendors list as in use with AI in it. Nothing "
        "here says what job it does."),
    spine.Finding(
        "finding.rg.duplicate_purchase", "Registry",
        "A project reached Procure choosing an external vendor for a "
        "capability a tool already held by another unit provides",
        "[Unit] already has [tool] for this. [Project] is buying something "
        "new."),
    spine.Finding(
        "finding.rg.holder_gone", "Registry",
        "A holding unit is one the organization later recorded as not "
        "present",
        "This is recorded as held by [unit], which your framework no longer "
        "lists."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}


def findings(rows: list[dict[str, Any]] | None = None, *,
             units: list[str] | None = None,
             absent: list[str] | None = None,
             projects: list[dict[str, Any]] | None = None
             ) -> list[dict[str, Any]]:
    """`units` is a list of units the organization keeps, where it keeps
    one; `absent` is the functions it recorded at 1.4 as not present. A
    holder is named against either, and never merely for being a unit the
    framework did not list."""
    rows = all_tools() if rows is None else rows
    known = {u.strip().lower() for u in (units or []) if u.strip()}
    gone = {a.strip().lower() for a in (absent or []) if a.strip()}
    found: list[dict[str, Any]] = []

    # 4.3 · a project that reached Procure choosing an external vendor, for
    # something a tool another unit already holds was named against. Never
    # blocks; states the fact and names both.
    for project in projects or []:
        gate = str(project.get("gate") or "")
        if not gate or spine.before(gate, spine.PROCURE):
            continue
        if int(project.get("chosen_step") or 0) != 6:
            continue
        steps = project.get("hierarchy") or {}
        named = " ".join(str((steps.get(k) or {}).get("candidate") or "")
                         for k in ("2", "3")).lower()
        mine = str((project.get("problem") or {}).get("unit") or "").strip().lower()
        for tool in rows:
            holders = [h.get("unit", "") for h in tool.get("held_by") or []
                       if h.get("unit", "").strip().lower() not in ("", mine)]
            if not holders:
                continue
            linked = project.get("ref") in (tool.get("projects") or [])
            mentioned = bool(tool.get("name")) and \
                tool["name"].strip().lower() in named
            if linked or mentioned:
                found.append({
                    "id": "finding.rg.duplicate_purchase",
                    "tool": tool.get("ref"), "project": project.get("ref"),
                    "says": (f"{holders[0]} already has {tool.get('name')} for "
                             f"this. {project.get('name') or project.get('ref')} "
                             f"is buying something new.")})

    for tool in rows:
        holders = tool.get("held_by") or []
        if holders and not tool.get("projects"):
            who = ", ".join(h.get("unit", "") for h in holders)
            found.append({
                "id": "finding.rg.held_ungoverned",
                "tool": tool.get("ref"),
                "says": (f"{who} has this and nothing on your list accounts "
                         f"for it.")})
        if known or gone:
            for holder in holders:
                unit = holder.get("unit", "").strip().lower()
                if (known and unit not in known) or unit in gone:
                    found.append({
                        "id": "finding.rg.holder_gone",
                        "tool": tool.get("ref"),
                        "says": (f"This is recorded as held by "
                                 f"{holder.get('unit')}, which your "
                                 f"framework no longer lists.")})
    return found


#: Never blocks and is never a reprimand. There are good reasons to buy a
#: second thing — a different unit, a different scale, a licence that will
#: not extend. The finding states the fact, links to both, and the project
#: records why it went ahead.
DUPLICATE_IS_NOT_A_REPRIMAND = (
    "There are good reasons to buy a second one: a different unit, a "
    "different scale, a license that will not extend. This says what is "
    "already here so the decision is made knowing it.")


# ===========================================================================
# The list view
# ===========================================================================

#: Held by renders as unit names, not a count, because the name is the
#: actionable part.
COLUMNS = ("The tool", "What it does", "Who supplies it", "Held by",
           "Used for", "Where it stands", "Projects")

#: The default sort applies the same hierarchy as the search.
SORTS = ("By whether you hold it", "By name", "By supplier",
         "By how many units hold it")

FILTERS = ("By held or not", "By holding unit", "By supplier",
           "By what it does", "By availability route",
           "By whether any project references it")

EMPTY = ("Nothing in the catalog yet.\n\nStart with the tools you already "
         "pay for. The point of this list is that somebody with a problem "
         "can find out you already have the answer. That only works once "
         "the things you have are on the list.")


def empty_state(seeded: int = 0) -> str:
    if seeded:
        return (f"{seeded} tools you already have.\n\nThese came from your "
                f"framework. Add what each one does and who else uses it, "
                f"and the next person with a problem will find them.")
    return EMPTY


def sorted_tools(rows: list[dict[str, Any]] | None = None
                 ) -> list[dict[str, Any]]:
    rows = all_tools() if rows is None else rows
    return sorted(rows,
                  key=lambda t: (0 if t.get("held_by") else 1,
                                 t.get("name", "").lower()))


def report(*, one_unit_organisation: bool = False) -> dict[str, Any]:
    rows = sorted_tools()
    return {
        "tools": rows,
        "counters": counters(rows,
                             one_unit_organisation=one_unit_organisation),
        "columns": list(COLUMNS),
        "sorts": list(SORTS),
        "filters": list(FILTERS),
        "bands": list(BANDS),
        "never_recommends": NEVER_RECOMMENDS,
        "duplicate_note": DUPLICATE_IS_NOT_A_REPRIMAND,
        "empty": empty_state(sum(1 for t in rows if t.get("seeded"))),
        "findings": [{"id": f.id, "trigger": f.trigger, "says": f.says}
                     for f in OWN_FINDINGS],
        "shared_findings": list(SHARED_FINDINGS),
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "routes": ROUTE_LABELS,
    }


# ===========================================================================
# 9 · Framework read-back, and the whole screen
# ===========================================================================

#: 2.2 · what the organisation told us it already uses, as catalog names.
#: "This came from what you told us."
_SOFTWARE_NAMES = {
    "office": "Office software with AI built in",
    "permitting": "Permitting, licensing, or case management software",
    "chat": "A chat window on your website",
    "records": "Document or records management",
    "gis": "Mapping or GIS",
    "scada": "Operations monitoring or SCADA",
    "erp": "Financial, ERP, or billing software",
    "hr": "Hiring or HR software",
    "cameras": "Security cameras or access control",
    "transcription": "Meeting transcription or notes",
}

#: The one unit a single-unit organisation holds things in.
HERE = "Here"


def framework_inputs(answers: dict[str, Any] | None) -> dict[str, Any]:
    from app import module_one as m
    answers = dict(answers or {})

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    def asked(key: str) -> bool:
        q = m.by_key(key)
        return bool(q) and m.answered(q, answers)

    def label_of(key: str, raw: Any) -> str:
        q = m.by_key(key)
        for o in (q.options if q else []) or []:
            if o.value == raw:
                return m._fill(o.label, answers)
        return str(raw or "")

    out: dict[str, Any] = {"readbacks": {}}
    rb = out["readbacks"]
    # 1.2 · a headcount under twenty-five is read as one unit: the
    # cross-utility machinery is real value in a large agency and noise in a
    # small one.
    out["one_unit"] = value("org.size") == "u25"
    functions = value("org.functions")
    functions = functions if isinstance(functions, dict) else {}
    out["can_build"] = functions.get("it") not in ("none", None, "") \
        if functions else False
    # 4.4 · the functions recorded as not present, by their own labels.
    out["absent"] = [o.label for o in m.FUNCTIONS
                     if functions.get(o.value) == "none"]
    rb["can_build"] = ("" if out["can_build"] or not functions else
                       "You said you have no information technology "
                       "function, so nothing is offered as built here.")
    # 8.2 · buying off other governments' agreements.
    coop = value("proc.cooperative")
    rb["agreements"] = {
        "regularly": "You said you buy off other governments' agreements "
                     "regularly.",
        "sometimes": "You said you buy off other governments' agreements "
                     "sometimes.",
        "no": "You said you do not buy off other governments' agreements.",
    }.get(coop, "")
    # 8.5 · a vendor adds AI to something already owned.
    added = value("proc.added_ai")
    rb["added_ai"] = (f"You said: {label_of('proc.added_ai', added)}."
                      if added else "")
    # 8.6 · check what you have first.
    reuse = value("proc.reuse")
    out["check_first"] = reuse == "yes"
    rb["check_first"] = ("You said staff have to check what you already have "
                         "first." if out["check_first"] else "")
    # 7.1 · never in a general-purpose tool.
    never = value("data.never") if asked("data.never") else []
    q_never = m.by_key("data.never")
    labels = {o.value: o.label for o in (q_never.options if q_never else [])}
    out["never"] = {v: labels.get(v, v) for v in (never or [])
                    if v != m.UNKNOWN}
    # 2.2 · what they already have, for the seeded state.
    have = value("have.software") if asked("have.software") else []
    out["already_have"] = [_SOFTWARE_NAMES.get(h, h) for h in (have or [])
                           if h in _SOFTWARE_NAMES]
    # 1.1 · the example.
    out["example"] = {
        "state": "permitting or enforcement", "federal": "grant review",
        "county": "the clerk's office",
        "city": "code enforcement", "district": "work orders",
        "school": "enrollment", "regional": "grant review",
    }.get(value("org.kind"), "")
    return out


def seed(inputs: dict[str, Any], actor: Any) -> dict[str, Any]:
    """The tools they told us they already have, as catalog rows, held here.
    An offer the person accepts, never a write on opening the screen."""
    made = []
    existing = {t.get("name", "").lower() for t in all_tools()}
    for name in inputs.get("already_have") or []:
        if name.lower() in existing:
            continue
        got = add(name, actor, seeded=True)
        if got.get("ok"):
            update(got["tool"]["ref"], actor, standing="We hold this",
                   held_by=[{"unit": HERE, "used_for": ""}])
            made.append(got["tool"]["ref"])
    return {"ok": True, "made": made}


def surface(*, answers: dict[str, Any] | None,
            projects: list[dict[str, Any]] | None = None,
            vendors_rows: list[dict[str, Any]] | None = None,
            holdings: list[dict[str, Any]] | None = None,
            terms: str = "", unit: str = "") -> dict[str, Any]:
    inputs = framework_inputs(answers)
    rows = sorted_tools()
    one_unit = inputs["one_unit"]
    vendors_rows = list(vendors_rows or [])
    by_vendor = {v.get("id"): v for v in vendors_rows}
    project_names = {p["ref"]: p.get("name", "") for p in (projects or [])
                     if p.get("ref")}

    raised = findings(rows, absent=inputs["absent"], projects=projects)
    # 4.2 · paid for, in use, with AI in it, and nothing here says what job
    # it does.
    linked = {t.get("vendor") for t in rows if t.get("vendor")}
    for v in vendors_rows:
        if v.get("status") == "in_use" and v.get("involvement") in (
                "core", "feature", "added") and v.get("id") not in linked:
            product = v.get("product") or v.get("name") or "A tool"
            raised.append({
                "id": "finding.rg.paid_not_listed", "tool": "",
                "says": f"{product} is on your Vendors list as in use with AI "
                        f"in it. Nothing here says what job it does."})

    listed = []
    for t in rows:
        vendor = by_vendor.get(t.get("vendor")) or {}
        needs = t.get("needs_holdings") or []
        never_hits = []
        for h in holdings or []:
            if h.get("id") in needs:
                for cat in h.get("sensitive") or []:
                    if cat in inputs["never"]:
                        never_hits.append(
                            f"{h.get('name', '')} · {inputs['never'][cat]} — "
                            f"you said never")
        listed.append({
            **t,
            "supplier_shown": (vendor.get("name") or t.get("supplier")
                               or "Not recorded"),
            # Cost lives on Vendors and nowhere else; shown here read-only.
            "vendor_money": (f"${vendor['amount']:,.0f} "
                             f"{vendor.get('basis_label', '')}".strip()
                             if isinstance(vendor.get("amount"), (int, float))
                             and vendor.get("amount") else ""),
            "vendor_renewal": vendor.get("renewal") or "",
            "held_shown": ", ".join(h["unit"] for h in t.get("held_by") or [])
                          or "Nobody here",
            "used_for_shown": "; ".join(
                f"{h['unit']}: {h['used_for']}" if not one_unit else h["used_for"]
                for h in t.get("held_by") or [] if h.get("used_for")),
            "projects_shown": ", ".join(project_names.get(p, p)
                                        for p in t.get("projects") or [])
                              or "No project",
            "never_hits": never_hits,
        })

    bands = search(terms, unit=unit, one_unit_organisation=one_unit)
    return {
        "counters": counters(rows, one_unit_organisation=one_unit),
        "bands": [{**b, "tools": [x["ref"] for x in b["tools"]]}
                  for b in bands],
        "tools": listed,
        "raised": raised,
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "never_recommends": NEVER_RECOMMENDS,
        "empty": empty_state(sum(1 for t in rows if t.get("seeded"))),
        "seed_offer": [n for n in inputs["already_have"]
                       if n.lower() not in {t.get("name", "").lower()
                                            for t in rows}],
        "inputs": inputs,
        "units": sorted({h["unit"] for t in rows
                         for h in t.get("held_by") or []}),
        "vendors": [{"id": v.get("id"), "name": v.get("name", ""),
                     "product": v.get("product", "")} for v in vendors_rows],
        "projects": [{"ref": r, "name": n} for r, n in project_names.items()],
        "holdings": [{"id": h.get("id"), "name": h.get("name", "")}
                     for h in holdings or []],
        "options": {"standings": list(STANDINGS),
                    "routes": [{"value": k, "label": v}
                               for k, v in ROUTE_LABELS.items()],
                    "involvement": list(INVOLVEMENT),
                    "general_purpose": list(GENERAL_PURPOSE),
                    "built_here": BUILT_HERE, "came_with": CAME_WITH},
        "one_unit": one_unit,
    }
