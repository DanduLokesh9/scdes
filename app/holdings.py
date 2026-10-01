"""What information this organization holds, where it lives, and whether a
tool can reach it.

The client: "Module for a data warehouse module. What data do you have
(content, format) for what purpose, where is it held, is it accessible via
API? ... Data warehouse module is the foundation on which all deployments
rest, so that must be robust, reliable and helpful."

Why this is the foundation
--------------------------

Every later question about an AI tool reduces to a question about data. Can it
reach what it needs? Is what it reaches allowed to go there? Is it current? A
governance framework that cannot answer those is a document about intentions.

It is also the answer to the module's own hardest moment. Question 7.2 asks
"do you know where your information actually lives?" and most organizations
answer "partly" or "no" — the framework records that as a gap with an owner,
which is honest and completely useless on its own. This is the thing that
closes it.

What an entry is
----------------

One *holding*: a body of information with a boundary somebody recognizes. A
permit system, a personnel file share, a SCADA historian, a folder of scanned
inspection reports. Not a table and not a whole department — the unit is
whatever a person would name if asked "where do you keep that?"

Every holding is scored against the categories the organization itself named
at 7.1 as never belonging in a general-purpose AI tool. That cross-reference
is the point: the register is not an inventory for its own sake, it is the
thing that says "you told us student records must never go into a general
tool, and this holding contains them and is exposed on an endpoint with no
authentication".

What this deliberately does not do
----------------------------------

**It does not connect to anything.** Recording that a system has an API is not
the same as this application holding a credential for it, and the second is a
much larger promise than the first. `app/monitor.py` probes reachability and
nothing else — no queries, no payloads, no credentials at rest.

**It does not classify data for them.** The categories come from their own
answer at 7.1. A tool that decided on their behalf which of their holdings
were sensitive would be making a legal judgment it is not qualified to make.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.audit import CORPUS, atomic_write
from app.authz import Actor

#: Where a tenant's register lives. Routed through `tenant.scoped`, like every
#: other file an agency owns.
HOLDINGS_FILE = CORPUS / "config" / "data_holdings.json"

#: What shape the information is in. Deliberately about *handling* rather than
#: about technology: "a database" and "a pile of scanned PDFs" need different
#: care, and "PostgreSQL 14" does not change the governance answer.
FORMATS = {
    "structured": "Structured records — a database, a register, a system of "
                  "record",
    "spreadsheets": "Spreadsheets and exports",
    "documents": "Documents — letters, reports, filings",
    "scanned": "Scans and images of paper",
    "media": "Photographs, video or audio",
    "geospatial": "Maps and geospatial layers",
    "telemetry": "Sensor readings, meter data or logs",
    "email": "Mailboxes and correspondence",
    "mixed": "A mixture",
    # Every select on this surface gains this answer, and it cannot be
    # removed. It produces a gap record rather than a blank.
    "unknown": "We are not sure",
}

#: 4.4 · Is this a live feed something reads from?
FEED = {"yes": "Yes", "no": "No", "unknown": "We are not sure"}

#: Anything entered under "something else" is kept with this prefix, so it
#: becomes an option for every later entry in this organisation and matches
#: in the overlap exactly as typed.
CUSTOM = "custom:"


def utility_label(value: str) -> str:
    value = str(value or "")
    if value.startswith(CUSTOM):
        return value[len(CUSTOM):]
    return UTILITY.get(value, value)


def _utility_ok(value: Any) -> bool:
    value = str(value or "")
    return value in UTILITY or (value.startswith(CUSTOM) and
                                bool(value[len(CUSTOM):].strip()))

#: Where it physically is. This is the question that decides who else can
#: reach it, which is why it is asked separately from what system holds it.
LOCATIONS = {
    "onprem": "On equipment we own and run",
    "gov_cloud": "In a government cloud tenancy we control",
    "vendor": "Held by a vendor on our behalf",
    "shared": "Shared with, or held by, another government",
    "paper": "On paper, or not in any system",
    "unknown": "We are not sure",
}

#: Whether a tool could reach it, which is a different question from whether
#: one should. Both get asked.
REACHABLE = {
    "api": "Yes — it has an interface a system can call",
    "export": "Only by exporting a file on request",
    "screen": "Only by a person reading it on screen",
    "no": "No — nothing can get at it programmatically",
    "unknown": "We are not sure",
}

#: How current the information is when somebody reads it. An AI tool answering
#: from a source refreshed once a quarter is a different risk from one reading
#: live records, and nobody asks until it has already gone wrong.
FRESHNESS = {
    "live": "Live — reads reflect the current state",
    "daily": "Refreshed daily",
    "weekly": "Refreshed weekly",
    "monthly": "Refreshed monthly or less often",
    "static": "A snapshot that is not refreshed",
    "unknown": "We are not sure",
}

#: A holding nobody owns is a holding nobody will fix. The register asks for a
#: role rather than a name, on the same rule as the framework itself.
#: What a body of information is operationally good for.
#:
#: **This is never a rating.** No holding is scored, ranked, or described as
#: high or low utility. It is a set of tags saying what the thing is good
#: for, and the application computes nothing from it except the overlap.
#:
#: Its purpose is cross-utility: surfacing, unprompted, where a holding one
#: unit keeps for one reason is what another unit said it needs. Units do
#: not appreciate what their own data is worth to somebody else, and this is
#: what makes that worth visible.
UTILITY = {
    "compliance": "Meeting a compliance or reporting obligation",
    "enforcement": "Enforcement",
    "deciding": "Deciding a case, a permit, an application or a claim",
    "historical": "Historical record — what happened, and when",
    "planning": "Planning and forecasting",
    "public": "Answering the public, including records requests",
    "billing": "Billing, fees or revenue",
    "other": "Something else",
}

#: How current a feed is expected to be. The organisation's own expectation,
#: against which lateness is judged; the application supplies no default,
#: which is why "No expectation set" is one of the answers rather than an
#: absence.
CURRENCY = {
    "live": "Live",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly or less often",
    "none": "No expectation set",
}

_LIMIT = 200
_LONG = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(value: Any, limit: int = _LIMIT) -> str:
    text = "".join(c for c in str(value or "") if c.isprintable())
    return text.strip()[:limit]


@dataclass
class Holding:
    """One body of information, as somebody in the organization would name it."""

    id: str = ""
    name: str = ""
    #: What is actually in it, in their words.
    contains: str = ""
    #: Why it exists and what it is used for.
    purpose: str = ""
    format: str = ""
    location: str = ""
    #: The system or place that holds it — "the permit system", "the K drive".
    system: str = ""
    #: A role, never a person. Titles outlast the people who hold them.
    owner: str = ""
    reachable: str = ""
    #: Where the interface is, if there is one. Recorded so it can be probed
    #: for reachability; never used to fetch content.
    endpoint: str = ""
    #: How a caller proves who it is. The *kind*, never a credential.
    auth: str = ""
    freshness: str = ""
    #: Which of the categories they named at 7.1 this holding contains.
    sensitive: list[str] = field(default_factory=list)
    #: What this information is operationally good for. Never a rating — see
    #: `UTILITY`. This is the field the whole register pays for.
    utility: list[str] = field(default_factory=list)
    #: Anything they added under "something else", which becomes an option
    #: for every subsequent entry in this organisation and appears nowhere
    #: else.
    utility_other: str = ""
    #: Everyone who reads this today. The field people skip, and the one
    #: that makes cross-utility work.
    units: list[str] = field(default_factory=list)
    #: The organisation's own label, where it keeps a scheme at all. This
    #: application records which one was chosen and never interprets it.
    classification: str = ""
    classification_why: str = ""
    #: The live feed block. Only meaningful where `feed` is "yes".
    feed: str = ""
    feed_read_by: list[str] = field(default_factory=list)
    #: The organisation's own expectation, against which lateness is judged.
    #: The application supplies no default.
    feed_expected: str = ""
    feed_confirmed: str = ""
    #: Anything else they want on the record.
    notes: str = ""
    added_at: str = ""
    added_by: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["format_label"] = FORMATS.get(self.format, "")
        out["location_label"] = LOCATIONS.get(self.location, "")
        out["reachable_label"] = REACHABLE.get(self.reachable, "")
        out["freshness_label"] = FRESHNESS.get(self.freshness, "")
        out["utility_labels"] = [utility_label(u) for u in self.utility]
        out["feed_label"] = FEED.get(self.feed, "")
        out["feed_expected_label"] = CURRENCY.get(self.feed_expected, "")
        return out


def _file():
    from app import tenant
    return tenant.scoped(HOLDINGS_FILE)


def _read() -> dict[str, Any]:
    path = _file()
    if not path.is_file():
        return {"holdings": []}
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"holdings": []}
    if not isinstance(held, dict):
        return {"holdings": []}
    held.setdefault("holdings", [])
    return held


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


def _clean(raw: dict[str, Any], existing: Holding | None = None) -> Holding:
    """One holding from whatever the browser sent, bounded and validated.

    Unknown values for the closed fields become "unknown" rather than being
    rejected: a register that refuses a row because somebody has not decided
    whether their file share is on-premises is a register nobody finishes.
    """
    base = existing or Holding()
    return Holding(
        id=base.id or raw.get("id") or f"DH-{uuid.uuid4().hex[:8].upper()}",
        name=_clip(raw.get("name", base.name)),
        contains=_clip(raw.get("contains", base.contains), _LONG),
        purpose=_clip(raw.get("purpose", base.purpose), _LONG),
        format=(raw.get("format", base.format) or "") if
        (raw.get("format", base.format) or "") in FORMATS else "unknown"
        if raw.get("format", base.format) else "",
        # Unanswered stays unanswered; "We are not sure" is an answer, and
        # the one that makes a gap record. Anything unrecognised is read as
        # not sure rather than refused.
        location=(raw.get("location", base.location) or "") if
        (raw.get("location", base.location) or "") in LOCATIONS else "unknown"
        if raw.get("location", base.location) else "",
        system=_clip(raw.get("system", base.system)),
        owner=_clip(raw.get("owner", base.owner)),
        reachable=(raw.get("reachable", base.reachable) or "") if
        (raw.get("reachable", base.reachable) or "") in REACHABLE
        else "unknown" if raw.get("reachable", base.reachable) else "",
        endpoint=_clip(raw.get("endpoint", base.endpoint), 500),
        auth=_clip(raw.get("auth", base.auth)),
        freshness=(raw.get("freshness", base.freshness) or "") if
        (raw.get("freshness", base.freshness) or "") in FRESHNESS
        else "unknown" if raw.get("freshness", base.freshness) else "",
        sensitive=[_clip(s, 60) for s in
                   (raw.get("sensitive", base.sensitive) or [])][:20],
        # Unknown utility values are dropped rather than kept, because the
        # overlap panel matches on them and a typo would pair two units on a
        # value neither of them chose. "other" carries its own free text.
        utility=[_clip(u, 120) for u in (raw.get("utility", base.utility) or [])
                 if _utility_ok(u)][:20],
        utility_other=_clip(raw.get("utility_other", base.utility_other)),
        units=[_clip(u, 80) for u in
               (raw.get("units", base.units) or []) if str(u).strip()][:30],
        classification=_clip(raw.get("classification",
                                     base.classification), 80),
        classification_why=_clip(raw.get("classification_why",
                                         base.classification_why)),
        feed=(raw.get("feed", base.feed) or "") if
        (raw.get("feed", base.feed) or "") in ("yes", "no", "unknown")
        else "",
        feed_read_by=[_clip(r, 80) for r in
                      (raw.get("feed_read_by", base.feed_read_by) or [])][:30],
        feed_expected=(raw.get("feed_expected", base.feed_expected) or "") if
        (raw.get("feed_expected", base.feed_expected) or "") in CURRENCY
        else "",
        feed_confirmed=_clip(raw.get("feed_confirmed", base.feed_confirmed),
                             40),
        notes=_clip(raw.get("notes", base.notes), _LONG),
        added_at=base.added_at or _now(),
        added_by=base.added_by,
        updated_at=_now(),
    )


def categories(answers: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The kinds of information a holding can be marked as containing.

    Read from their own 7.1, including anything they added themselves, because
    this module does not invent a second vocabulary for the same idea. Every
    category is offered whether or not they banned it — marking that a holding
    contains personnel files is a fact about the holding, and whether that is a
    problem is their framework's judgment, not this register's.

    `banned` says which ones they did name at 7.1, so the form can show what a
    tick will mean before it is ticked.
    """
    from app import module_one, versions

    if answers is None:
        answers = versions.state().get("working") or {}
    question = module_one.by_key("data.never")
    if question is None:
        return []

    named, _ = module_one.value_of(answers, "data.never")
    named = named if isinstance(named, list) else []

    out: list[dict[str, Any]] = []
    for option in module_one.options_for(question, answers):
        if option.value == module_one.UNKNOWN:
            continue
        out.append({"value": option.value, "label": option.label,
                    "banned": option.value in named})

    # Anything already recorded against a holding that 7.1 no longer offers —
    # they un-ticked their own addition, or the answer changed after the
    # holding was written. Kept visible, because a form that silently drops a
    # category on the next save loses the record without telling anybody.
    known = {c["value"] for c in out}
    for row in _read().get("holdings", []):
        for value in row.get("sensitive") or []:
            if value in known:
                continue
            known.add(value)
            out.append({"value": value,
                        "label": module_one.custom_label(value),
                        "banned": value in named})
    return out


def listing(*, one_unit_organisation: bool = False,
            labels: list[str] | None = None) -> dict[str, Any]:
    """Every holding this organization has recorded, with what it adds up to."""
    held = _read()
    rows = [Holding(**h) for h in held.get("holdings", [])]
    out = {
        "holdings": [h.as_dict() for h in rows],
        "formats": FORMATS,
        "locations": LOCATIONS,
        "reachable": REACHABLE,
        "freshness": FRESHNESS,
        "utility_options": UTILITY,
        "utility_added": added_utility(rows),
        "currency": CURRENCY,
        "sensitive_options": categories(),
        "summary": summary(rows),
        "utility_note": UTILITY_IS_NOT_A_RATING,
        "monitor_limit": CANNOT_BE_CHECKED,
    }
    # The part of this register that pays. Everything above it is
    # bookkeeping — and where the organisation has one unit it does not
    # appear, and its absence is never explained.
    if not one_unit_organisation:
        out["overlap"] = overlap(rows)
    # Section 9 does not exist unless the organisation told Oversight it
    # keeps a scheme. No field, no counter, no finding, and no empty state
    # referring to one: explaining the absence would imply something was
    # missing.
    if labels:
        out["labels"] = list(labels)
        out["labels_note"] = LABELS_ARE_YOURS
    else:
        # Conditional at the schema level, not the display level: a hidden
        # field with a null in it is a field somebody will eventually
        # surface.
        for h in out["holdings"]:
            h.pop("classification", None)
            h.pop("classification_why", None)
    return out


#: Never a rating, and said on the screen rather than only in the spec.
UTILITY_IS_NOT_A_RATING = (
    "Tick everything this is good for. Most people tick the one their own "
    "unit uses it for and stop. The second and third ticks are the ones "
    "that matter — they are how somebody in another part of the "
    "organization finds out you already have what they need. Nothing here "
    "is scored or ranked.")

#: Said once, where the scheme is set up.
LABELS_ARE_YOURS = (
    "These are your labels and this application does not interpret them. It "
    "records which one you chose and shows it wherever this holding "
    "appears. Nothing here will tell you that a label is wrong, because "
    "nothing here knows what your labels mean.")

#: The standard for everything on this page: where a check cannot be
#: performed, say so in these terms rather than reporting a state you did
#: not observe.
CANNOT_BE_CHECKED = (
    "A system on your own internal network cannot be reached from here, and "
    "will show as 'cannot be checked'. Watching those needs an agent inside "
    "your network — it is not built yet, and a green tick that meant "
    "nothing would be worse.")


def added_utility(rows: list[Holding] | None = None) -> list[str]:
    """Anything entered under "something else".

    Becomes an option for every subsequent entry in this organization, and
    appears nowhere else.
    """
    if rows is None:
        rows = [Holding(**h) for h in _read().get("holdings", [])]
    seen: list[str] = []
    for row in rows:
        said = (row.utility_other or "").strip()
        if said and said not in seen:
            seen.append(said)
        for value in row.utility:
            if value.startswith(CUSTOM) and utility_label(value) not in seen:
                seen.append(utility_label(value))
    return seen


def overlap(rows: list[Holding] | None = None, *,
            wanted: list[dict[str, str]] | None = None
            ) -> dict[str, Any]:
    """Holdings useful to somebody who does not know they exist.

    A holding recorded by unit A, carrying a utility value that unit B named
    on a project, where unit B has no holding of their own carrying that
    value.

    `wanted` is what the projects asked for: [{"unit": ..., "utility": ...}].
    Passed in rather than read here, because Projects owns that record and
    two surfaces reading the same thing by different routes is how they come
    to disagree.

    No score, no ranking, no percentage of holdings shared. Counts and named
    pairs.
    """
    if rows is None:
        rows = [Holding(**h) for h in _read().get("holdings", [])]

    # What each unit already holds, by utility, so a unit is never told
    # about a need it can already meet itself.
    holds: dict[str, set[str]] = {}
    for row in rows:
        for unit in row.units:
            holds.setdefault(unit.strip().lower(), set()).update(row.utility)

    pairs: list[dict[str, str]] = []
    for asked in wanted or []:
        unit = str(asked.get("unit") or "").strip()
        value = str(asked.get("utility") or "").strip()
        if not unit or not _utility_ok(value):
            continue
        if value in holds.get(unit.lower(), set()):
            continue
        label = utility_label(value)
        said = label if value.startswith(CUSTOM) else label.lower()
        for row in rows:
            if value not in row.utility:
                continue
            for keeper in row.units:
                if keeper.strip().lower() == unit.lower():
                    continue
                pair = {
                    "holding": row.name,
                    "keeper": keeper,
                    "needs_it": unit,
                    "utility": label,
                    "says": (f"{keeper} keeps this for "
                             f"{said}. {unit} recorded "
                             f"that they need {said} "
                             f"information of this kind and have none."),
                }
                if pair not in pairs:
                    pairs.append(pair)

    # "[n] holdings" counts holdings, not pairs: one holding two units need
    # is one holding.
    n = len({p["holding"] for p in pairs})
    return {
        "count": n,
        "pairs": pairs,
        "says": (f"{n} holding{'' if n == 1 else 's'} "
                 f"{'is' if n == 1 else 'are'} useful to somebody "
                 f"who does not know {'it exists' if n == 1 else 'they exist'}."),
    }


def lookup(utility: str, rows: list[Holding] | None = None
           ) -> dict[str, Any]:
    """Every holding carrying a utility, whoever owns it.

    Called from Identify when somebody asks what data would resolve this. It
    searches the whole organization rather than the unit the person belongs
    to, and that is the point of it.
    """
    if rows is None:
        rows = [Holding(**h) for h in _read().get("holdings", [])]
    found = [h for h in rows if utility in h.utility]
    label = utility_label(utility)
    return {
        "utility": utility,
        "label": label,
        "holdings": [{
            "id": h.id, "name": h.name, "units": list(h.units),
            "owner": h.owner,
            "reachable": REACHABLE.get(h.reachable, ""),
            "freshness": FRESHNESS.get(h.freshness, ""),
        } for h in found],
        # Two different meanings, and the sentence says both rather than
        # picking one.
        "empty_says": (f"Nothing recorded here is marked as useful for "
                       f"{label.lower()}. That may mean nobody has it, or "
                       f"it may mean nobody has written down what they "
                       f"have."),
    }


def summary(rows: list[Holding] | None = None) -> dict[str, Any]:
    """What the register says about the organization as a whole.

    Counts and absences. Never a rate and never a grade: a small
    organization with three holdings and one unknown would read 33% as a
    failing mark, so nothing here is expressed as a proportion and nothing
    is colored as an alarm.
    """
    if rows is None:
        rows = [Holding(**h) for h in _read().get("holdings", [])]
    return {
        "total": len(rows),
        "with_an_interface": sum(1 for h in rows if h.reachable == "api"),
        "unreachable": sum(1 for h in rows if h.reachable == "no"),
        # 2.5 · We are not sure, or unanswered.
        "unknown_location": sum(1 for h in rows
                                if h.location in ("unknown", "")),
        "unowned": sum(1 for h in rows if not h.owner.strip()),
        "holding_sensitive": sum(1 for h in rows if h.sensitive),
        "stale_or_unknown": sum(1 for h in rows
                                if h.freshness in ("static", "unknown")),
    }


# ===========================================================================
# Findings
# ===========================================================================

from app import spine  # noqa: E402  (placed here to avoid a cycle at import)

SHARED_FINDINGS = ("finding.never_category", "finding.gap_no_owner")

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.dt.unreachable_in_scope", "Data",
        "A holding a live project names is recorded as not reachable "
        "programmatically",
        "[Project] needs this and nothing can get at it programmatically."),
    spine.Finding(
        "finding.dt.stale_source", "Data",
        "A holding named as a baseline source is recorded as a snapshot "
        "that is not refreshed",
        "The measurement for [project] comes from this, and this is a "
        "snapshot that is not refreshed."),
    spine.Finding(
        "finding.dt.feed_silent", "Data",
        "A watched endpoint has not answered for longer than the "
        "organization's own tolerance, where they set one",
        "This has not answered since [date]."),
    spine.Finding(
        "finding.dt.owner_gone", "Data",
        "The owning role is one the organization later recorded as not "
        "present",
        "This is owned by [function], which your framework says you do not "
        "have."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}

#: Three findings this surface will never raise, stated so nobody adds them.
#: All three would punish a choice this product leaves open — AI governance
#: is not data governance, and nothing here requires a classification
#: scheme, a complete register, or a recorded utility before work proceeds.
WILL_NOT_RAISE = (
    "a holding without a classification",
    "an organization with no classification scheme",
    "a holding whose utility is unrecorded",
)


def findings(rows: list[Holding] | None = None, *,
             needed_by: dict[str, str] | None = None,
             baseline_for: dict[str, str] | None = None,
             absent: list[str] | None = None,
             checks: dict[str, dict[str, Any]] | None = None,
             now: str = "") -> list[dict[str, Any]]:
    """Contradictions against the organization's own answers, and nothing
    else. Never an external standard, never a benchmark.

    `needed_by` and `baseline_for` map a holding id to the project that
    names it, passed in rather than read here because Projects owns that
    record. `absent` is the functions the organization recorded at 1.4 as
    not present — an owner is named only where it is one of those, never
    because it is a role the framework did not list. `checks` is the
    monitor's record, for 3.3.
    """
    if rows is None:
        rows = [Holding(**h) for h in _read().get("holdings", [])]
    needed_by = needed_by or {}
    baseline_for = baseline_for or {}
    gone = {f.strip().lower() for f in (absent or []) if f.strip()}
    checks = checks or {}
    found: list[dict[str, Any]] = []
    for row in rows:
        silent = feed_silent_since(row, checks.get(row.id) or {}, now=now)
        if silent:
            found.append({
                "id": "finding.dt.feed_silent", "holding": row.id,
                "says": f"This has not answered since {silent}."})

    for row in rows:
        project = needed_by.get(row.id, "")
        if project and row.reachable == "no":
            found.append({
                "id": "finding.dt.unreachable_in_scope", "holding": row.id,
                "says": (f"{project} needs this and nothing can get at it "
                         f"programmatically.")})
        measures = baseline_for.get(row.id, "")
        if measures and row.freshness == "static":
            found.append({
                "id": "finding.dt.stale_source", "holding": row.id,
                "says": (f"The measurement for {measures} comes from this, "
                         f"and this is a snapshot that is not refreshed.")})
        if gone and row.owner.strip().lower() in gone:
            found.append({
                "id": "finding.dt.owner_gone", "holding": row.id,
                "says": (f"This is owned by {row.owner}, which your "
                         f"framework says you do not have.")})
    return found


def save(raw: dict[str, Any], actor: Actor, *,
         labels: list[str] | None = None) -> dict[str, Any]:
    """Add or update one holding.

    Not gated on a capacity, on the same reasoning as `versions.answer`: this
    is the organization's own record of its own systems, in its own container,
    and requiring an Office of Technology before somebody can write down where
    the permit database lives is the circularity this module exists to break.
    Recorded, though — every write names who made it.
    """
    if not _clip(raw.get("name")):
        return {"ok": False, "error": "A holding needs a name — whatever the "
                                      "people who use it call it."}

    held = _read()
    rows = {h["id"]: h for h in held.get("holdings", [])}
    wanted = raw.get("id") or ""
    existing = Holding(**rows[wanted]) if wanted in rows else None

    holding = _clean(raw, existing)
    if existing is None:
        holding.added_by = _clip(actor.name) or "unnamed"
    stored = asdict(holding)
    if labels is not None:
        if not labels:
            stored.pop("classification", None)
            stored.pop("classification_why", None)
        elif stored.get("classification") and \
                stored["classification"] not in labels:
            stored["classification"] = ""
    rows[holding.id] = stored
    held["holdings"] = list(rows.values())
    _write(held)

    _record("record_data_holding" if existing is None
            else "update_data_holding", actor,
            {"holding": holding.id, "name": holding.name})
    return {"ok": True, "holding": holding.as_dict(), "state": listing()}


def forget(holding_id: str, actor: Actor) -> dict[str, Any]:
    """Remove a holding from the register."""
    held = _read()
    rows = [h for h in held.get("holdings", []) if h.get("id") != holding_id]
    if len(rows) == len(held.get("holdings", [])):
        return {"ok": False, "error": f"No holding {holding_id!r}."}
    held["holdings"] = rows
    _write(held)
    # Its check results go with it. Leaving them behind inflated the monitor's
    # counts against entries no longer on any screen.
    try:
        from app import monitor
        monitor.forget(holding_id)
    except Exception:                                     # noqa: BLE001
        pass
    _record("forget_data_holding", actor, {"holding": holding_id})
    return {"ok": True, "state": listing()}


def _record(action: str, actor: Actor, detail: dict[str, Any]) -> None:
    from app import tenant
    from app.authz import default_log
    try:
        default_log().append(
            actor=actor.user_id, role=actor.role.value, action=action,
            target="config", outcome="allowed",
            detail={**detail, "agency": tenant.current(),
                    "actor_name": _clip(actor.name),
                    "reason": "The organization's own record of its own "
                              "systems. Recorded, not gated."})
    except Exception:
        pass


# ------------------------------------------------- what the register tells them

def concerns(answers: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Where the register and their own framework disagree.

    This is the whole reason the register is worth keeping. Each finding pairs
    something they wrote down here with something they decided in the
    framework, and nothing is inferred beyond that pairing — a tool that
    guessed which holdings were sensitive would be making a legal judgment it
    is not qualified to make.
    """
    from app import module_one, versions

    if answers is None:
        answers = versions.state().get("working") or {}
    rows = [Holding(**h) for h in _read().get("holdings", [])]
    out: list[dict[str, str]] = []

    banned = module_one.value_of(answers, "data.never")[0]
    banned = banned if isinstance(banned, list) else []
    labels = {o.value: o.label for o in module_one.options_for(
        module_one.by_key("data.never"), answers)}

    for holding in rows:
        overlap = [labels.get(s, s) for s in holding.sensitive if s in banned]
        if overlap and holding.reachable == "api" and not holding.auth.strip():
            out.append({
                "holding": holding.name,
                "says": f"holds {overlap[0].lower()}, is reachable by an "
                        f"interface, and no way of proving who is calling is "
                        f"recorded",
                "against": "7.1 — what must never go into a general-purpose "
                           "AI tool",
            })
        elif overlap:
            out.append({
                "holding": holding.name,
                "says": f"holds {overlap[0].lower()}",
                "against": "7.1 — keep it out of any general-purpose tool",
            })

        if not holding.owner.strip():
            out.append({
                "holding": holding.name,
                "says": "has nobody named against it",
                "against": "Floor 7 — somebody's name is on it",
            })

        if holding.location == "unknown":
            out.append({
                "holding": holding.name,
                "says": "is recorded without anybody knowing where it lives",
                "against": "7.2 — do you know where your information lives",
            })

    return out


# ===========================================================================
# 4B · The feed, and how late is late
# ===========================================================================

#: 4.6 · the organisation's own expectation, turned into how long silence is
#: tolerated before 3.3 names it. "No expectation set" tolerates anything:
#: the application supplies no default.
TOLERANCE_HOURS = {"live": 1, "daily": 24, "weekly": 24 * 7,
                   "monthly": 24 * 31}


def feed_silent_since(row: Holding, check: dict[str, Any], *, now: str = ""
                      ) -> str:
    """3.3 · The date a watched feed last answered, where it has been silent
    for longer than the organization said it should be. Empty otherwise —
    including where no expectation was set, or it was never watched."""
    hours = TOLERANCE_HOURS.get(row.feed_expected)
    if row.feed != "yes" or not hours or check.get("state") != "down":
        return ""
    history = check.get("history") or []
    answered = next((h.get("at") for h in history if h.get("state") == "up"),
                    "")
    since = answered or check.get("changed_at") or (
        history[-1].get("at") if history else "")
    if not since:
        return ""
    try:
        then = datetime.fromisoformat(str(since))
        at = datetime.fromisoformat(now) if now else \
            datetime.now(timezone.utc)
    except ValueError:
        return ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if (at - then).total_seconds() / 3600 <= hours:
        return ""
    return str(since)[:10] if answered else f"it was first checked on {str(since)[:10]}"


def confirm_current(holding_id: str, actor: Actor, *, on: str = "") -> dict[str, Any]:
    """4.7 · Written by whoever confirms it. Nothing computes this."""
    held = _read()
    row = next((h for h in held.get("holdings", [])
                if h.get("id") == holding_id), None)
    if row is None:
        return {"ok": False, "error": f"No holding {holding_id!r}."}
    row["feed_confirmed"] = _clip(on, 10) or clock.today_str()
    row["updated_at"] = _now()
    _write(held)
    _record("update_data_holding", actor, {"holding": holding_id,
                                           "field": "feed_confirmed",
                                           "on": row["feed_confirmed"]})
    return {"ok": True, "on": row["feed_confirmed"]}


# ===========================================================================
# 12, 14, 15 · What this surface reads from the framework
# ===========================================================================

#: 15 · Every example and placeholder, by organisation type. Where 1.1 is
#: unanswered, or names a type the specification gives no example for, the
#: clause carrying the example is dropped rather than filled with a word this
#: application chose.
EXAMPLES = {
    "state": "the permit system and the inspection history",
    "federal": "the grants system and the case files",
    "district": "the work-order system and the meter readings",
    "school": "the enrollment file and the transport routes",
    "city": "the service-call log and the code-enforcement file",
}

#: 7.6, 10.1 and 10.2 are the technology hat's: they are the only fields on
#: this surface where a wrong answer is a technical claim.
TECHNICAL_FIELDS = ("reachable", "endpoint", "auth")

TECHNICAL_REFUSED = (
    "Whether a tool can reach it, where the interface is, and how a caller "
    "proves who it is are for the technology hat to record, because a wrong "
    "answer there is a technical claim. Everything else here is yours to "
    "write.")


def framework_inputs(answers: dict[str, Any] | None) -> dict[str, Any]:
    from app import module_one as m
    answers = dict(answers or {})

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    functions = value("org.functions")
    functions = functions if isinstance(functions, dict) else {}
    present = [o.label for o in m.FUNCTIONS
               if functions.get(o.value) not in (None, "", "none")]
    absent = [o.label for o in m.FUNCTIONS if functions.get(o.value) == "none"]
    it = functions.get("it")
    return {
        "example": EXAMPLES.get(str(value("org.kind") or ""), ""),
        "one_unit": value("org.size") == "u25",
        # 7.9 · only roles the organisation said exist. Where 1.4 is
        # unanswered nothing is offered and the field is free text.
        "roles": present,
        "absent": absent,
        "absent_says": [f"You said you have no {a[:1].lower() + a[1:]}."
                        for a in absent],
        # The restriction holds only where 1.4 records a technology
        # function. Where they recorded none — or have not said — the
        # fields fold to whoever is here, rather than blocking the only
        # person who could answer.
        "technical_restricted": it not in (None, "", "none"),
        "open_records": value("org.open_records") == "yes",
    }


def may_edit_technical(role_value: str, inputs: dict[str, Any]) -> bool:
    return (not inputs.get("technical_restricted") or
            role_value in ("ot", "council"))


#: The selects whose "We are not sure" is a gap record rather than a blank.
_GAP_FIELDS = (("format", "Shape"), ("location", "Where it lives"),
               ("reachable", "Can a tool reach it"),
               ("freshness", "How current it is"),
               ("feed", "Whether it is a live feed"))


def gaps(rows: list[Holding] | None = None) -> list[dict[str, str]]:
    """Every "We are not sure", as a gap record: what is not known, on which
    holding, and whose it is to close — the owning role, where one is
    named."""
    if rows is None:
        rows = [Holding(**h) for h in _read().get("holdings", [])]
    out: list[dict[str, str]] = []
    for row in rows:
        for key, label in _GAP_FIELDS:
            if getattr(row, key) == "unknown":
                out.append({"holding": row.id, "name": row.name,
                            "field": key, "question": label,
                            "owner": row.owner.strip()})
    return out


def surface(*, answers: dict[str, Any] | None, projects: list[dict[str, Any]],
            tools: list[dict[str, Any]] | None = None,
            labels: list[str] | None = None,
            checks: dict[str, dict[str, Any]] | None = None,
            role: str = "", now: str = "") -> dict[str, Any]:
    """The whole Data surface: the register, what it found against the
    organization's own answers, the overlap, and what it reads."""
    from app import module_one as m
    answers = dict(answers or {})
    inputs = framework_inputs(answers)
    rows = [Holding(**h) for h in _read().get("holdings", [])]
    out = listing(one_unit_organisation=inputs["one_unit"], labels=labels)

    stopped = {"state.turned_down", "state.retired"}
    live = [p for p in projects if p.get("state") not in stopped]
    needed_by: dict[str, str] = {}
    baseline_for: dict[str, str] = {}
    for p in live:
        name = p.get("name") or p.get("ref") or ""
        for hid in p.get("holdings") or []:
            needed_by.setdefault(hid, name)
        for hid in (p.get("grounds") or {}).get("holdings") or []:
            baseline_for.setdefault(hid, name)

    found = findings(rows, needed_by=needed_by, baseline_for=baseline_for,
                     absent=inputs["absent"], checks=checks, now=now)
    # finding.never_category — the shared finding, in the spine's sentence.
    banned = m.value_of(answers, "data.never")[0]
    banned = banned if isinstance(banned, list) else []
    names = {c["value"]: c["label"] for c in categories(answers)}
    for row in rows:
        hit = [s for s in row.sensitive if s in banned]
        if hit and row.id in needed_by:
            cat = names.get(hit[0], hit[0])
            found.append({"id": "finding.never_category", "holding": row.id,
                          "says": f"You said never for "
                                  f"{cat[:1].lower() + cat[1:]}. "
                                  f"{needed_by[row.id]} reaches it."})
    open_gaps = gaps(rows)
    for g in open_gaps:
        if not g["owner"]:
            found.append({"id": "finding.gap_no_owner", "holding": g["holding"],
                          "says": f"{g['question']}, on {g['name']}, is "
                                  f"recorded as unknown with nobody named to "
                                  f"close it."})
    by_id = {r.id: r.name for r in rows}
    for f in found:
        f["name"] = by_id.get(f.get("holding", ""), "")

    # 5.1 · what projects at Identify said they need, and who said it.
    wanted = []
    for p in live:
        problem = p.get("problem") or {}
        unit = str(problem.get("unit") or "").strip()
        for value in problem.get("info_for") or []:
            wanted.append({"unit": unit, "utility": value})
    if not inputs["one_unit"]:
        out["overlap"] = overlap(rows, wanted=wanted)

    out.update({
        "findings": found,
        "gaps": open_gaps,
        "nothing_to_flag": ("Nothing to flag — nothing you have recorded "
                            "here contradicts anything you decided in your "
                            "framework."),
        "inputs": inputs,
        "may_edit_technical": may_edit_technical(role, inputs),
        "technical_refused": TECHNICAL_REFUSED,
        "feed_options": FEED,
        "projects": [{"ref": p.get("ref"), "name": p.get("name", "")}
                     for p in projects],
        "tools": [{"ref": t.get("ref"), "name": t.get("name", "")}
                  for t in tools or []],
    })
    return out


def lookups(values: list[str], rows: list[Holding] | None = None
            ) -> list[dict[str, Any]]:
    """5.2 · the lookup at Identify, for every purpose a project named."""
    return [lookup(v, rows) for v in values if _utility_ok(v)]
