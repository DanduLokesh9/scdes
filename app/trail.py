"""Audit trail — what happened, who did it, and under which rules.

The record every other screen writes to and nobody writes over. One line for
every change, carrying the person, the hat they were wearing, the moment it
happened, and the version of the framework that was in force when they made
it.

`app/audit.py` is the store: a hash-chained, append-only JSONL file. This is
the surface over it — the vocabulary, the counters, the two checks, the
findings, and the two views. The split is deliberate. The store has to be
boring and provably correct; the surface has opinions about wording.

**This surface writes nothing anywhere else.** No gate, no state, no field on
any other surface, no record anywhere. Every other surface writes here; this
one writes back to none of them. It owns no gate, and it is the only surface
where that is a rule rather than a consequence: a record of what happened
cannot also be a participant in it. Nothing here approves, blocks, moves,
reminds, or asks anybody for a decision. It raises findings, and beyond that
it is inert.

**Append-only, stated plainly.** Nothing here is edited and nothing is
deleted. A mistake is corrected by writing a new entry that names the earlier
one and says what is wrong with it. Both stay, side by side, permanently.
That will feel wrong the first time somebody mistypes a date, and it is right
anyway — the difference between what you believed in March and what you knew
in September is frequently the most useful thing on the record, and an
application that let you quietly reconcile the two would destroy the only
thing this screen is for.

**Four things it answers about any moment:** who did it, what changed, which
hat they were wearing, and which version of the rules was in force. The
fourth is the one everybody forgets to keep, and it is the one that settles
the argument, because rules move.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import collections
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app import spine

# ===========================================================================
# The vocabulary of the "What happened" column
# ===========================================================================

#: The full set of event types. A developer building this screen should not
#: have to write a sentence that is not here.
#:
#: Every sentence renders with the person and the hat appended in the row's
#: own columns rather than inside the sentence, except where the sentence
#: names them because the naming is the event.
@dataclass(frozen=True)
class EventType:
    id: str
    says: str
    #: Which surfaces may write it. "every" where any may. Enforced by
    #: `written_by_is_allowed` so that a surface writing an event it does not
    #: own is caught rather than quietly accepted.
    written_by: tuple[str, ...]


EVERY_SURFACE = ("every",)

EVENTS: tuple[EventType, ...] = (
    EventType("event.record_created", "Written down for the first time",
              ("Registry", "Vendors", "Data", "Vision", "Process",
               "Integrity", "Budget", "Oversight")),
    EventType("event.field_changed", "{field} changed", EVERY_SURFACE),
    EventType("event.gate_passed", "Passed {gate}", ("Projects",)),
    EventType("event.gate_moved_back", "Sent back to {gate}", ("Projects",)),
    EventType("event.state_changed", "Moved to {state}", ("Projects",)),
    EventType("event.version_opened",
              "The vendor said something is changing: {what}", ("Projects",)),
    EventType("event.version_judged", "{judgement}", ("Projects",)),
    EventType("event.version_live", "A new version went live", ("Projects",)),
    EventType("event.version_retired",
              "The version that was running was retired, because the new one "
              "went live", ("Projects",)),
    EventType("event.decision_recorded", "Decided: {outcome}, by {role}",
              ("Oversight",)),
    EventType("event.condition_attached",
              "A condition was attached: {condition}, owned by {role}, by "
              "{date}", ("Oversight",)),
    EventType("event.condition_closed", "A condition was closed: {condition}",
              ("Oversight", "Integrity", "Process", "Budget")),
    EventType("event.person_named", "{kind} named: {role}", ("Registry",)),
    EventType("event.person_changed",
              "The {kind} changed: was {was}, now {now}", ("Registry",)),
    EventType("event.gap_opened",
              "Recorded as unknown: {what}, owned by {role}, by {date}",
              EVERY_SURFACE),
    EventType("event.gap_closed", "An unknown was answered: {what}",
              EVERY_SURFACE),
    EventType("event.recommendation_offered",
              "A recommendation was offered: {what}", EVERY_SURFACE),
    EventType("event.recommendation_accepted",
              "A recommendation was accepted: {what}", EVERY_SURFACE),
    EventType("event.recommendation_declined",
              "A recommendation was declined: {what}", EVERY_SURFACE),
    EventType("event.paused", "Stopped, by {name} as {hat}", ("Projects",)),
    EventType("event.restarted", "Started again", ("Projects",)),
    EventType("event.incident_reported", "Something went wrong, reported by "
              "{name}", ("Integrity",)),
    EventType("event.notification_recorded", "{party} was told, on {date}",
              ("Integrity", "Vision")),
    EventType("event.check_recorded", "Somebody looked at it",
              ("Integrity",)),
    EventType("event.measurement_recorded",
              "A measurement was recorded against the claim",
              ("Integrity", "Vision")),
    EventType("event.framework_adopted",
              "Your framework was adopted by {authority}, in effect from "
              "{date}", ("Oversight",)),
    EventType("event.framework_amended",
              "Your framework changed to version {n}, in effect from {date}",
              ("Oversight",)),
    EventType("event.framework_answer_changed",
              "An answer in your framework changed: {question}",
              ("Oversight",)),
    EventType("event.file_attached", "A copy was attached: {what}",
              ("Oversight", "Vendors", "Integrity", "Process")),
    EventType("event.recorded_from_elsewhere",
              "Recorded from somewhere else: {what}", ("Audit trail",)),
    EventType("event.note_added", "A note was added", ("Audit trail",)),
    EventType("event.correction_recorded",
              "A correction was recorded against an earlier entry",
              ("Audit trail",)),
    EventType("event.exported", "The record was produced", ("Audit trail",)),
    EventType("event.hat_assigned", "{name} was given the {hat} hat",
              ("Oversight",)),
)
BY_EVENT: dict[str, EventType] = {e.id: e for e in EVENTS}

#: One state change writes one entry, and Projects is the only surface that
#: writes it. The spine gives Projects sole authorship of record state and
#: calls any surface that writes state directly a bug; the same holds for the
#: entry that describes a state moving.
#:
#: `event.paused` and `event.restarted` exist because "stopped" and "started
#: again" are the words a reader is looking for. Where either fires,
#: `event.state_changed` does not fire alongside it. Every other state,
#: Retired included, renders through `event.state_changed`. There is no
#: `event.retired`.
STATE_EVENTS = ("event.state_changed", "event.paused", "event.restarted")

#: Lifecycle writes nothing here. It explains what the seven gates are, holds
#: no record, and there is no entry in this trail whose source is Lifecycle.
#: A developer looking for one has found a bug rather than a gap.
NEVER_WRITES = ("Lifecycle",)


def written_by_is_allowed(event_id: str, surface: str) -> bool:
    kind = BY_EVENT.get(event_id)
    if kind is None or surface in NEVER_WRITES:
        return False
    return kind.written_by == EVERY_SURFACE or surface in kind.written_by


def sentence(event_id: str, **parts: Any) -> str:
    """The sentence for an event, with its parts filled in.

    Two renderings carry a gate-specific twist and they are the only ones:
    a passage recorded after the fact says so with its date, and passing
    Sunset says the tool was retired, because a reader who could not tell a
    version sunset from a tool sunset would read a routine update as a
    retirement.
    """
    kind = BY_EVENT.get(event_id)
    if kind is None:
        return ""
    if event_id == "event.gate_passed":
        gate_name = str(parts.get("gate", ""))
        if gate_name == "Sunset":
            said = "Passed Sunset — the tool was retired"
        else:
            said = f"Passed {gate_name}"
        if parts.get("happened"):
            return (f"Recorded as having passed {gate_name} on "
                    f"{parts['happened']}")
        return said
    try:
        return kind.says.format(**parts)
    except KeyError:
        # A missing part renders the template's own placeholder rather than
        # raising. A trail that refuses to display an entry is worse than one
        # that displays it incompletely.
        return kind.says


#: The three judgements a version call can carry. "Not yet decided" is a real
#: answer that writes an entry of its own rather than waiting for a better
#: one, and where the call is later revised that is a second entry beside the
#: first, and both stay.
JUDGED = {
    "yes": "This change was called material",
    "no": "This change was called not material",
    "not yet decided": "Nobody has decided yet whether this change is "
                       "material",
}


# ===========================================================================
# Reading the trail
# ===========================================================================

def _log():
    """This organization's own trail, and nobody else's."""
    from app.audit import OrganisationLog
    return OrganisationLog()


def rows() -> list[dict[str, Any]]:
    """Every entry, oldest first, as stored.

    Raw dictionaries rather than `Entry` objects: entries written before a
    field existed do not carry it, and a reader that insisted on the current
    shape would refuse to display the oldest and most interesting part of
    the trail.
    """
    log = _log()
    try:
        return list(log._raw())
    except (OSError, ValueError):
        return []


def _when(row: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(row.get("at", "")))
    except ValueError:
        return None


def _happened_before_written(row: dict[str, Any]) -> bool:
    """Whether this was recorded after the fact.

    The count that makes the spine's rule visible: order is recorded, never
    enforced.
    """
    said = str(row.get("happened") or "").strip()
    if not said:
        return False
    written = _when(row)
    try:
        when = datetime.fromisoformat(said)
    except ValueError:
        return False
    if written is None:
        return False
    # Compared on the date rather than the instant. Somebody recording
    # yesterday's board vote types a date, not a timestamp, and midnight
    # against an afternoon would otherwise make every one of them count.
    return when.date() < written.date()


# ===========================================================================
# The stat row — five counters, each a plain count
# ===========================================================================

#: No counter here is a score. There is no completeness figure, no coverage
#: percentage, no colour band, no target, no arrow, no comparison to any
#: other organisation, and no number that reads as a mark out of anything.
#:
#: This surface takes nothing from the shared bank of absence counters. Every
#: phrase in that bank describes something missing from a *record*; an
#: absence here is something missing from the *trail*, which is a fact about
#: the trail rather than about a tool. These five are reserved to this
#: surface and no other surface takes them.
COUNTERS = (
    "Entries in the trail",
    "Recorded after it happened",
    "Nothing said about why",
    "Corrections recorded",
    "Versions of your framework in this trail",
)

#: The application asks for a reason in exactly three places and nowhere
#: else. An entry it never asked about is not counted as missing one.
ASKS_WHY = ("event.recommendation_declined", "event.correction_recorded",
            "event.gate_moved_back")


def counters(held: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    held = rows() if held is None else held

    after_the_fact = sum(1 for r in held if _happened_before_written(r))
    corrections = sum(1 for r in held
                      if r.get("action") == "event.correction_recorded")
    silent = sum(1 for r in held
                 if r.get("action") in ASKS_WHY
                 and not str((r.get("detail") or {}).get("why") or "").strip())

    # Distinct versions stamped on at least one entry, plus one for entries
    # written before the framework took effect, which count as their own
    # version for this purpose.
    stamped = {str(r.get("version") or "") for r in held}
    seen_versions = len(stamped) if stamped else 0

    return {
        "entries": len(held),
        "after_the_fact": after_the_fact,
        "nothing_said_about_why": silent,
        "corrections": corrections,
        "versions": seen_versions,
        "guidance": {
            "entries":
                "Every entry, all time. This number never goes down. On a "
                "busy week in a large organization it moves by hundreds, and "
                "that is the trail working rather than anything being wrong.",
            "after_the_fact":
                "Something that happened first and was written down later. A "
                "tool you found already running walks Identify, Procure and "
                "Test in order, with each date saying when it was recorded "
                "rather than pretending it happened first. Every one of "
                "those counts here, and none of them is a fault.",
            "nothing_said_about_why":
                "The application asked for a reason and got a blank. It "
                "accepted the blank; it always will. This is a count of the "
                "places where the reason is now in somebody's memory instead "
                "of on the record.",
            "corrections":
                "Nothing here is edited or removed. Where something was "
                "wrong, somebody wrote a second entry saying so, and both "
                "are on the record. Corrections in a trail mean somebody is "
                "reading it.",
            "versions":
                "Each time your framework changes, everything written "
                "afterward is stamped with the new version, and everything "
                "written before keeps the old one. This is the count of how "
                "many sets of rules a reader would have to hold in their "
                "head to read the whole trail.",
        },
    }


# ===========================================================================
# The seal check, and the two things it cannot tell you
# ===========================================================================

#: Shown on the surface and never hidden behind a link.
SEAL_SAYS = (
    "Every entry carries a fingerprint of itself and of the entry before it. "
    "Once a night, and whenever you ask, the whole trail is read back in "
    "order and every fingerprint is checked against the entry it belongs to. "
    "Nothing is sent anywhere and nothing is fetched.")

#: Shown under the check and never hidden behind a link. Described this
#: narrowly because somebody will rely on the check in a room where it
#: matters.
SEAL_LIMIT = (
    "This proves that nothing changed these entries through this "
    "application, and that is the whole of what it proves. It is not a "
    "notarization, it is not filed with anybody, and no third party holds a "
    "copy. It cannot tell you anything about what somebody with direct "
    "access to the database underneath did. That is a question for whoever "
    "runs your systems and for whoever holds that access, and it is a "
    "question worth asking them. This check tells you that the entry you are "
    "reading today is the entry that was written, and it tells you the day "
    "that stops being true.")


def seal_check(held: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Four counts, reported as text and never as color.

    The chain is verified entry by entry rather than by the store's own
    all-or-nothing `verify()`, because the surface has to report how many
    matched as well as whether all of them did. A trail with one broken
    entry in four thousand is a different situation from a trail that cannot
    be read at all, and one boolean cannot tell them apart.
    """
    from app.audit import GENESIS, entry_hash

    held = rows() if held is None else held
    checked = matched = mismatched = unreadable = 0
    first_break = ""
    prev = GENESIS

    for row in held:
        checked += 1
        try:
            recomputed = entry_hash(row)
        except Exception:                                     # noqa: BLE001
            unreadable += 1
            prev = str(row.get("hash") or prev)
            continue
        ok = (recomputed == row.get("hash")
              and row.get("prev_hash") == prev)
        if ok:
            matched += 1
        else:
            mismatched += 1
            if not first_break:
                first_break = str(row.get("seq") or "")
        prev = str(row.get("hash") or prev)

    return {
        "checked": checked,
        "matched": matched,
        "did_not_match": mismatched,
        "could_not_be_read": unreadable,
        "first_break": first_break,
        "says": SEAL_SAYS,
        "limit": SEAL_LIMIT,
    }


#: Answers a different question from the seal check, so it is reported on its
#: own.
WINDOW_SAYS = (
    "Every entry is checked against the versions of your framework and the "
    "dates they took effect, so that every line in the trail can say which "
    "rules it was written under.")

BEFORE_ADOPTION = "before your framework took effect"
NO_VERSION = "No version in force"


def version_window(held: list[dict[str, Any]] | None = None
                   ) -> dict[str, Any]:
    """Which rules were in force, entry by entry.

    "Written before your framework took effect" is an ordinary reading and
    never a fault. It is how nearly every organization starts — most write
    down half their register before they adopt anything.
    """
    held = rows() if held is None else held

    adopted_at = ""
    undated = 0
    try:
        from app import versions
        state = versions.state()
        for row in state.get("versions") or []:
            when = str(row.get("adopted_on") or "").strip()
            if row.get("adopted") and not when:
                undated += 1
            if row.get("adopted") and when and (not adopted_at
                                                or when < adopted_at):
                adopted_at = when
    except Exception:                                         # noqa: BLE001
        pass

    covered = before = none_in_force = 0
    for row in held:
        stamp = str(row.get("version") or "").strip()
        if stamp:
            covered += 1
            continue
        when = clock.local_date(str(row.get("at") or ""))
        if adopted_at and when and when < adopted_at:
            before += 1
        elif adopted_at:
            none_in_force += 1
        else:
            # Nothing adopted at all, so every entry predates the framework.
            before += 1

    return {
        "covered": covered,
        "before_adoption": before,
        "no_version_in_force": none_in_force,
        "versions_without_a_date": undated,
        "says": WINDOW_SAYS,
        "note": ("Written before your framework took effect is an ordinary "
                 "reading and never a fault. It is how nearly every "
                 "organization starts."),
    }


#: Shown at the foot of the checks, in the same weight as the checks above.
CANNOT_SEE = (
    "This records what happened in this application. It does not record what "
    "anybody typed into an AI tool, what the tool answered, what a vendor "
    "changed on their side of a product, what was said in a meeting, or "
    "anything that happened before you started using this. Those reach this "
    "trail only when a person writes them down, and an entry a person wrote "
    "down says so, in the entry, on every screen it appears on, permanently. "
    "There is no connection to any tool you run, and there will not be one "
    "without you being told exactly what was connected and exactly what it "
    "can see.")


def not_recorded(open_records: str = "yes") -> str:
    """What is deliberately not kept, and why.

    A log of reading is a trap set for the person who reads. The single
    exception is producing the record: an export is a copy of the record
    leaving for somewhere this application can no longer see.
    """
    said = ("Nobody's screen views. Nobody's searches or filters. No "
            "addresses, no devices, no session times, no keystrokes, no time "
            "spent on a page. Nothing on this screen can answer the question "
            "of who looked at what, and that is a decision rather than an "
            "omission. ")
    if str(open_records).strip().lower() in ("yes", "true"):
        said += ("You said you are subject to open records. ")
    else:
        said += (f"Nearly every organization using this is subject to open "
                 f"records, and you answered {open_records}. Either way, ")
    said += ("A record of who read what would itself be producible, and the "
             "first time somebody asked for it, it would be used against one "
             "of your own people rather than in defense of one of your "
             "decisions. A log of reading is a trap set for the person who "
             "reads.\n\nThe single exception is producing the record. When "
             "somebody exports the trail, that is written down — who did it, "
             "when, for which records, and with which filter — because an "
             "export is a copy of the record leaving for somewhere this "
             "application can no longer see.")
    return said


# ===========================================================================
# Findings
# ===========================================================================

#: Nine this surface defines, plus three it renders from the spine. None is
#: raised against an external standard, a benchmark, or another
#: organisation's practice.
OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.audit.not_written_where_you_said", "Audit trail",
        "An entry recorded from somewhere else is marked as not written "
        "where you said, and the record has since moved on",
        "You said decisions get written down here: [their answer]. This one "
        "was recorded here and marked as not written there, and it has moved "
        "on since."),
    spine.Finding(
        "finding.audit.changed_after_approval", "Audit trail",
        "A field recorded for every tool changed after a passage was "
        "approved, with nothing recorded since",
        "This passed [gate] on [date]. [Field], which you said is recorded "
        "for every tool, changed on [date], and nothing has been recorded on "
        "it since."),
    spine.Finding(
        "finding.audit.approval_before_evidence", "Audit trail",
        "An approval is stamped earlier than the evidence it points at",
        "This was approved on [date]. The [thing it points at] was written "
        "down on [date], afterward."),
    spine.Finding(
        "finding.audit.framework_changed_without_an_amendment",
        "Audit trail",
        "A framework answer changed and no amendment record exists for it",
        "Your framework changed on [date] and there is no amendment recorded "
        "for it. You said [their answer] may change it."),
    spine.Finding(
        "finding.audit.no_version_in_force", "Audit trail",
        "An entry falls after the first effective date but inside a period "
        "no version covers",
        "This happened on [date]. No version of your framework was in effect "
        "then."),
    spine.Finding(
        "finding.audit.version_without_a_date", "Audit trail",
        "A framework version exists with no effective date, and entries have "
        "been written since",
        "One version of your framework has no date on it, so nothing written "
        "since [date] can say which rules it was under."),
    spine.Finding(
        "finding.audit.retention_silent_on_ai", "Audit trail",
        "The retention schedule does not mention AI-assisted documents and "
        "tools are in use",
        "You said your retention schedule does not mention documents an AI "
        "tool helped produce. [N] tools are in use and producing them."),
    spine.Finding(
        "finding.audit.retired_but_still_relied_on", "Audit trail",
        "A retired record carries a note that something it touched is still "
        "open, and the Sunset record is closed",
        "This was retired on [date] and somebody recorded that a matter it "
        "touched is still open. The record behind a tool does not end when "
        "the tool does."),
    spine.Finding(
        "finding.audit.correction_unanswered", "Audit trail",
        "A correction names an earlier entry as wrong and nothing has been "
        "recorded on that record since",
        "Somebody recorded on [date] that this was wrong. Nothing has been "
        "recorded on it since."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}

#: Defined once in the spine and never redefined here. This surface renders
#: them where they attach to an entry rather than to a record.
SHARED_FINDINGS = ("finding.condition_overdue", "finding.gap_no_owner",
                   "finding.framework_moved")

#: Findings this surface will not raise, stated so nobody adds them later.
#:
#: One person having written every entry is never a finding. Somebody
#: proposing a thing and approving it the same day is never a finding here —
#: it is recorded exactly as it happened, and the judgment belongs to
#: whoever the framework named. How long anything took is never a finding,
#: because this application did not set that clock and will not invent one.
#: A quiet week, month or year is never a finding. Nobody's rate of entries
#: is calculated, displayed, ranked or compared against anybody else's.
#:
#: Nothing here is flagged as unusual: that would require the application to
#: hold an opinion about what your usual is, and it would accuse a named
#: person on the strength of a picture of normal nobody agreed to.
WILL_NOT_RAISE = (
    "one person wrote every entry",
    "somebody proposed and approved on the same day",
    "how long something took",
    "a quiet week, month or year",
    "anybody's rate of entries",
    "anything flagged as unusual",
    "a recommendation was declined",
    "anything measured against an outside standard or another organization",
)


# ===========================================================================
# The trail line, and the views
# ===========================================================================

def trail_line(first_entry: str = "", written_where: str = "",
               gap_owner: str = "") -> str:
    """One sentence directly under the counters. Three renderings, no fourth.

    The date is never rendered as an age, a duration, or a number of days.
    """
    if not first_entry:
        return ("The trail is empty. It starts writing itself the first time "
                "somebody writes something down anywhere in the "
                "application.")
    opening = (f"The trail starts {first_entry}. Everything before that date "
               f"happened somewhere else.")
    if written_where.strip():
        # Quoted whole and never split into a place and a role. A split needs
        # a parse, and a parse of one line of free text is a guess that would
        # then be shown back to the user as their own words.
        return (f"{opening} You said decisions get written down here: "
                f"{written_where.strip()} This does not replace that and it "
                f"cannot see inside it.")
    who = gap_owner.strip() or "nobody yet"
    return (f"{opening} You have not said where decisions get written down; "
            f"that is recorded as a gap, owned by {who}, and it is the only "
            f"thing on this screen anybody can act on.")


COLUMNS = ("When", "What happened", "Which record", "Where", "Who", "Hat",
           "What changed", "Under which version")

SORTS = ("Newest first", "Oldest first", "By record", "By person",
         "By kind of event")

FILTERS = ("By record", "By surface", "By person", "By hat",
           "By kind of event", "By date range", "By framework version",
           "Entries recorded after they happened",
           "Entries with nothing said about why",
           "Corrections, shown together with the entries they correct",
           "Entries written by somebody with no hat",
           "Entries a person recorded from somewhere else",
           "Entries with a note attached", "The entries belonging to one "
           "version", "The two kinds of sunset, separately")


def filter_sentence(showing: int, **applied: str) -> str:
    """The filter in force, always stated in words above the list, and
    carried into anything produced from it."""
    parts = [f"Showing {showing:,} entr{'y' if showing == 1 else 'ies'}."]
    if applied.get("record"):
        parts.append(f"One record: {applied['record']}.")
    if applied.get("since"):
        parts.append(f"From {applied['since']}.")
    who = applied.get("person") or "anybody"
    hat = applied.get("hat") or "any hat"
    parts.append(f"Written by {who}, wearing {hat}.")
    return " ".join(parts)


#: Two entries written in the same second are held in the order they were
#: written, by sequence number, because their order is a fact rather than a
#: preference. Within a single moment the order never changes and is never
#: sortable.
def in_order(held: list[dict[str, Any]], newest_first: bool = True
             ) -> list[dict[str, Any]]:
    ordered = sorted(held, key=lambda r: (str(r.get("at", "")),
                                          int(r.get("seq") or 0)))
    return list(reversed(ordered)) if newest_first else ordered


def empty_state(knows_what_it_runs: bool = True,
                adopted: tuple[str, str] | None = None) -> str:
    """Three renderings. There is nothing on this screen to fill in."""
    if adopted:
        when, authority = adopted
        return (f"One line so far: your framework was adopted on {when} by "
                f"{authority}. That is the right first line, and everything "
                f"written from here carries the version it was written "
                f"under. Open Projects and start one for a tool you already "
                f"run. The second line will be that.")
    if not knows_what_it_runs:
        return ("Nothing here yet, and there is nothing on this screen to "
                "fill in. It writes itself, starting with whatever anybody "
                "writes down first. In most organizations the first line is "
                "somebody recording a tool they found already running. That "
                "is an ordinary place to start, and it is the first honest "
                "entry in the record.")
    return ("Nothing here yet, and there is nothing on this screen to fill "
            "in. This is the one page in the application you never write to. "
            "It writes itself, starting the moment somebody writes something "
            "down anywhere else. If you want to see what it will hold, open "
            "Projects and start one for a tool you already run. Come back, "
            "and the first line will be that.")


#: There is no way to leave something out of a produced record, and the
#: reason is stated on the screen rather than only here.
NO_EXCLUDING = (
    "There is no way to leave something out of this. What you hand over is "
    "the whole of what the filter selected. A record you could edit on the "
    "way out would not be worth producing, and somebody would notice the "
    "gap.")


# ===========================================================================
# Rendering an entry, in words
# ===========================================================================

HATS = {"operator": "User", "ot": "Office of Technology",
        "council-member": "Decision-maker"}
NO_HAT = "No hat — recorded from outside"

#: The detail keys that name the record an entry is about, in the order they
#: are looked for.
_RECORD_KEYS = ("ref", "project", "procedure", "check", "incident",
                "decision", "line", "tool", "goal", "vendor", "id")

#: Detail keys that are bookkeeping rather than something that changed.
_QUIET = {"actor_name", "actor_title", "reason", "agency", "organisation",
          "verified_member", "actor_email"}


def _humanise(action: str) -> str:
    """An action this vocabulary does not name, in plain words rather than
    as an identifier."""
    text = str(action or "").replace("event.", "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Something happened"


def _changed(detail: dict[str, Any]) -> str:
    """What changed, in words: "was [x], now [y]" — never a symbol."""
    field = detail.get("field") or detail.get("key") or ""
    if "was" in detail and ("now" in detail or "value" in detail):
        now = detail.get("now", detail.get("value"))
        label = f"{field}: " if field else ""
        return f"{label}was {detail.get('was') or 'nothing'}, now {now or 'nothing'}"
    bits = []
    for key, value in detail.items():
        if key in _QUIET or key in _RECORD_KEYS or value in (None, "", [], {}):
            continue
        shown = ", ".join(map(str, value)) if isinstance(value, list) else value
        bits.append(f"{key.replace('_', ' ')}: {shown}")
    return "; ".join(str(b) for b in bits)[:600]


def shown(row: dict[str, Any]) -> dict[str, Any]:
    """One entry as the list and the story view render it."""
    detail = row.get("detail") or {}
    action = str(row.get("action") or "")
    parts = {k: v for k, v in detail.items() if isinstance(v, (str, int, float))}
    said = sentence(action, **parts) if action in BY_EVENT else _humanise(action)
    record = next((str(detail[k]) for k in _RECORD_KEYS if detail.get(k)), "")
    target = str(row.get("target") or "")
    if not record and target.lower() == "framework":
        record = "Your framework"
    at = str(row.get("at") or "")
    happened = str(row.get("happened") or "")
    when = clock.local_stamp(at) if at else "No time recorded"
    if happened and happened[:10] != clock.local_date(at):
        when = f"happened {happened[:10]} · recorded {when}"
    hat = HATS.get(str(row.get("role") or ""), NO_HAT)
    version = str(row.get("version") or "") or "Before your framework took effect"
    who = str(detail.get("actor_name") or row.get("actor") or "Not recorded")
    return {
        "seq": row.get("seq"), "when": when, "at": at, "what": said,
        "action": action, "record": record or "How you run things",
        "where": target, "who": who, "hat": hat,
        "changed": _changed(detail), "version": version,
        "denied": row.get("outcome") == "denied",
        "of": detail.get("of"), "note_kind": detail.get("kind", ""),
        "from_elsewhere": action == "event.recorded_from_elsewhere",
    }


# ===========================================================================
# 8 · The three things a person may write
# ===========================================================================

HOW_KNOWN = ("I was there", "I read it in a document", "Somebody told me",
             "I found it afterward in the system", "We are not sure")
ABOUT = ("A project", "A catalog row", "An agreement", "A holding", "A goal",
         "A procedure", "A cost line",
         "Not about one tool — about your framework",
         "Not about one tool — about how you run things",
         "We are not sure which one")
NOTE_KINDS = ("This entry needs some context",
              "Something here is wrong",
              "This record is still needed for something that is still open",
              "Nothing more, just a note")
STILL_NEEDED = NOTE_KINDS[2]
WRITTEN_WHERE = ("Yes", "No", "We are not sure")

RECORD_IT_SAYS = (
    "This will be written as recorded by you, from somewhere else, on {today}, "
    "and it will say so on every screen it appears on. Like everything else "
    "here, it cannot be edited or removed afterward. If it turns out to be "
    "wrong, you correct it by writing a second entry beside it.")

NOTE_SAYS = ("A note never changes the entry it is attached to. The entry "
             "stays exactly as it was written, with its own date and its own "
             "name on it, and your note sits beside it with yours.")

CORRECTION_SAYS = (
    "This does not remove or alter the entry above. It writes a new entry "
    "beside it, saying what you say is wrong, with your name and today's date "
    "on it, and both stay on the record permanently. If what was wrong was a "
    "decision rather than a description of one, correcting the entry does not "
    "change the decision. That is a new decision, and it belongs in the "
    "Oversight section.")


def _write(actor: Any, action: str, detail: dict[str, Any],
           happened: str = "") -> dict[str, Any]:
    entry = _log().append(
        actor=getattr(actor, "user_id", "") or "unknown",
        role=getattr(getattr(actor, "role", None), "value", "") or "",
        action=action, target="Audit trail", outcome="allowed",
        detail={**detail,
                "actor_name": str(getattr(actor, "name", "") or "")[:120]},
        happened=happened)
    return {"ok": True, "seq": entry.seq}


def record_elsewhere(*, actor: Any, what: str, happened: str = "",
                     how_known: str = "", about: str = "",
                     about_ref: str = "", involved: list[dict] | None = None,
                     paper: str = "", written_where: str = "",
                     note: str = "") -> dict[str, Any]:
    """8A · Record something that happened somewhere else. Only the first
    line is required. There is no upload: this records that a thing
    happened, and where the paper is."""
    what = str(what or "").strip()
    if not what:
        return {"ok": False, "error": "Say what happened, in one line."}
    people = [{"role": str(p.get("role") or "").strip()[:200],
               "name": str(p.get("name") or "").strip()[:120],
               "outside": str(p.get("outside") or "").strip()[:200]}
              for p in (involved or []) if isinstance(p, dict)
              and str(p.get("role") or "").strip()]
    return _write(actor, "event.recorded_from_elsewhere", {
        "what": what[:300],
        "how_known": how_known if how_known in HOW_KNOWN else "",
        "about": about if about in ABOUT else "",
        "ref": str(about_ref or "")[:40],
        "involved": [f"{p['role']}{' (' + p['name'] + ')' if p['name'] else ''}"
                     f"{' — ' + p['outside'] if p['outside'] else ''}"
                     for p in people],
        "paper": str(paper or "").strip()[:300],
        "written_where_you_said": written_where if written_where in
        WRITTEN_WHERE else "",
        "note": str(note or "").strip()[:2000]},
        happened=str(happened or "")[:10])


def _entry(seq: Any) -> dict[str, Any] | None:
    try:
        wanted = int(seq)
    except (TypeError, ValueError):
        return None
    return next((r for r in rows() if r.get("seq") == wanted), None)


def add_note(*, actor: Any, of: Any, text: str, kind: str = "") -> dict[str, Any]:
    """8B · A note beside an entry. The entry is never changed."""
    target = _entry(of)
    if not target:
        return {"ok": False, "error": "No such entry."}
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "error": "Say what you want to say about this "
                                      "entry."}
    record = shown(target)["record"]
    return _write(actor, "event.note_added", {
        "of": target["seq"], "kind": kind if kind in NOTE_KINDS else "",
        "text": text[:4000], "ref": record if record != "How you run things"
        else ""})


def correct(*, actor: Any, of: Any, wrong: str, should: str = "",
            why: str = "") -> dict[str, Any]:
    """8C · A correction is an entry, not an edit. Both stay."""
    target = _entry(of)
    if not target:
        return {"ok": False, "error": "No such entry."}
    wrong = str(wrong or "").strip()
    if not wrong:
        return {"ok": False, "error": "Say what is wrong with it."}
    record = shown(target)["record"]
    return _write(actor, "event.correction_recorded", {
        "of": target["seq"], "wrong": wrong[:500],
        "should": str(should or "").strip()[:2000],
        "why": str(why or "").strip()[:500] or wrong[:500],
        "ref": record if record != "How you run things" else ""})


# ===========================================================================
# 7C · Produce the record — two files, together, and the producing written
# ===========================================================================

def produce(*, actor: Any, selected: list[dict[str, Any]], sentence_: str,
            organisation: str = "", one_record: str = "") -> dict[str, Any]:
    """Two files from exactly what the filter selected, with nothing left
    out, both carrying the seal check as it stood at that moment."""
    import csv
    import html
    import io
    seal = seal_check()
    seal_line = (f"Seal check at the moment this was produced: "
                 f"{seal['checked']} entries checked, {seal['matched']} "
                 f"matched, {seal['did_not_match']} did not match, "
                 f"{seal['could_not_be_read']} could not be read.")
    ordered = sorted(selected, key=lambda r: (str(r.get("at", "")),
                                              int(r.get("seq") or 0)))
    rendered = [shown(r) for r in ordered]

    e = html.escape
    body = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>The record — {e(organisation)}</title></head><body>",
            f"<h1>The record — {e(organisation or 'your organization')}</h1>",
            f"<p>{e(sentence_)}</p>", f"<p>{e(seal_line)}</p>"]
    versions_seen = sorted({r["version"] for r in rendered})
    body.append("<h2>Versions of your framework in this record</h2><ul>"
                + "".join(f"<li>{e(v)}</li>" for v in versions_seen)
                + "</ul>")
    if one_record:
        body.append("<h2>What somebody would need to explain a decision this "
                    "touched</h2><p>Nobody has written that down yet. It is "
                    "asked on the retirement record, when the tool is shut "
                    "off.</p>")
    body.append("<h2>The entries, in date order</h2><ol>")
    for r in rendered:
        body.append(f"<li><p><strong>{e(r['when'])}.</strong> {e(r['what'])}. "
                    f"{e(r['who'])}, as {e(r['hat'])}. About: {e(r['record'])}. "
                    f"Under {e(r['version'])}.</p>"
                    + (f"<p>{e(r['changed'])}</p>" if r["changed"] else "")
                    + "</li>")
    body.append("</ol></body></html>")

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["# dates are ISO 8601, in UTC"])
    writer.writerow(["sequence", "recorded_at_utc", "happened", "what_happened",
                     "record", "where", "who", "hat", "what_changed",
                     "version", "outcome"])
    for raw, r in zip(ordered, rendered):
        writer.writerow([raw.get("seq"), raw.get("at"), raw.get("happened", ""),
                         r["what"], r["record"], r["where"], r["who"],
                         r["hat"], r["changed"], r["version"],
                         raw.get("outcome", "")])
    writer.writerow([f"# {seal_line}"])

    _write(actor, "event.exported", {
        "entries": len(ordered), "filter": sentence_[:500],
        "record": one_record})
    return {"ok": True, "html": "".join(body), "csv": out.getvalue(),
            "count": len(ordered), "seal": seal_line}


# ===========================================================================
# 5 · The findings this surface can compute
# ===========================================================================

def findings_for(held: list[dict[str, Any]], *, written_where: str = "",
                 projects: list[dict[str, Any]] | None = None,
                 retention: str = "", retention_gapped: bool = False,
                 amend_words: str = "",
                 amendments_on: list[str] | None = None,
                 adopted_on: str = "") -> list[dict[str, Any]]:
    """The findings that read the trail against the organization's own
    answers. None reads an outside standard, and none is about how much,
    how fast or how often anybody wrote."""
    projects = list(projects or [])
    by_ref = {p.get("ref"): p for p in projects}
    raised: list[dict[str, Any]] = []
    later_on_record: dict[str, str] = {}
    for r in held:
        ref = shown(r)["record"]
        at = str(r.get("at") or "")
        if at > later_on_record.get(ref, ""):
            later_on_record[ref] = at

    for r in held:
        detail = r.get("detail") or {}
        action = r.get("action")
        # 5.1 — from the one field that carries it, and only where the record
        # has since moved to a later gate.
        if action == "event.recorded_from_elsewhere" and written_where and \
                detail.get("written_where_you_said") == "No":
            project = by_ref.get(detail.get("ref"))
            moved = project and str(project.get("last_moved") or "") > \
                str(r.get("at") or "")
            if moved:
                raised.append({
                    "id": "finding.audit.not_written_where_you_said",
                    "seq": r.get("seq"),
                    "says": f"You said decisions get written down here: "
                            f"{written_where} This one was recorded here and "
                            f"marked as not written there, and it has moved "
                            f"on since."})
        # 5.9 — a correction with nothing recorded on that record since.
        if action == "event.correction_recorded":
            ref = str(detail.get("ref") or "")
            project = by_ref.get(ref)
            live = project and project.get("state") not in (
                spine.RETIRED, spine.TURNED_DOWN)
            if ref and live and later_on_record.get(ref, "") <= \
                    str(r.get("at") or ""):
                raised.append({
                    "id": "finding.audit.correction_unanswered",
                    "seq": r.get("seq"),
                    "says": f"Somebody recorded on {clock.local_date(str(r.get('at')))} "
                            f"that this was wrong. Nothing has been recorded "
                            f"on it since."})
        # 5.8 — a retired record somebody said is still needed.
        if action == "event.note_added" and detail.get("kind") == STILL_NEEDED:
            project = by_ref.get(detail.get("ref"))
            if project and project.get("state") == spine.RETIRED:
                raised.append({
                    "id": "finding.audit.retired_but_still_relied_on",
                    "seq": r.get("seq"),
                    "says": f"This was retired on "
                            f"{clock.local_date(str(project.get('last_moved') or ''))} and "
                            f"somebody recorded that a matter it touched is "
                            f"still open. The record behind a tool does not "
                            f"end when the tool does."})

    # 5.7 — their own answer about their retention schedule, unless the gap
    # is recorded with somebody's name against it.
    in_use = sum(1 for p in projects if p.get("in_use") == spine.IN_USE_YES)
    if retention == "silent" and in_use and not retention_gapped:
        raised.append({
            "id": "finding.audit.retention_silent_on_ai", "seq": None,
            "says": f"You said your retention schedule does not mention "
                    f"documents an AI tool helped produce. {in_use} "
                    f"tool{'' if in_use == 1 else 's'} "
                    f"{'is' if in_use == 1 else 'are'} in use and producing "
                    f"them."})

    # 5.4 — an answer changed after adoption with no amendment anywhere.
    if adopted_on:
        changes = sorted(clock.local_date(str(r.get("at") or "")) for r in held
                         if r.get("action") == "answer_framework_question"
                         and clock.local_date(str(r.get("at") or "")) > adopted_on)
        amended = [d for d in (amendments_on or []) if d >= adopted_on]
        if changes and not amended:
            raised.append({
                "id": "finding.audit.framework_changed_without_an_amendment",
                "seq": None,
                "says": f"Your framework changed on {changes[0]} and there is "
                        f"no amendment recorded for it."
                        + (f" You said {amend_words} may change it."
                           if amend_words else "")})

    # 5.5 · 5.6 — from the version window.
    window = version_window(held)
    if window["no_version_in_force"]:
        raised.append({"id": "finding.audit.no_version_in_force", "seq": None,
                       "says": f"{window['no_version_in_force']} entries fall "
                               f"after your framework first took effect, in a "
                               f"period no version of it covers."})
    if window["versions_without_a_date"]:
        raised.append({"id": "finding.audit.version_without_a_date",
                       "seq": None,
                       "says": "One version of your framework has no date on "
                               "it, so nothing written since can say which "
                               "rules it was under."})
    return raised


def report(open_records: str = "yes") -> dict[str, Any]:
    """Everything the surface renders, in one read."""
    held = rows()
    ordered = in_order(held, newest_first=False)
    first = ordered[0] if ordered else {}
    by_surface = collections.Counter(str(r.get("target") or "")
                                     for r in held)
    return {
        "counters": counters(held),
        "seal": seal_check(held),
        "window": version_window(held),
        "cannot_see": CANNOT_SEE,
        "not_recorded": not_recorded(open_records),
        "columns": list(COLUMNS),
        "sorts": list(SORTS),
        "filters": list(FILTERS),
        "events": [{"id": e.id, "says": e.says,
                    "written_by": list(e.written_by)} for e in EVENTS],
        "findings": [{"id": f.id, "trigger": f.trigger, "says": f.says}
                     for f in OWN_FINDINGS],
        "shared_findings": list(SHARED_FINDINGS),
        "will_not_raise": list(WILL_NOT_RAISE),
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "first_entry": clock.local_date(str(first.get("at") or "")),
        "by_surface": dict(by_surface),
        "no_excluding": NO_EXCLUDING,
    }
