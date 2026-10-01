"""Who you buy from, what it costs, and what else it could do.

The client: "Module will contain a list of vendors, costs, and use case
potential. ... 1 should be very easy to stand up bc you already have a
template as Appendix C (I think that's the registry)."

One correction to that, carried here rather than left in a message: Appendix C
is the **AI System Registry** — its unit is a system, with vendor and contract
as two columns among twenty-one. The vendor questionnaire is **Appendix E —
Vendor AI Disclosure**, and its tiering model is what decides how much a
vendor has to tell you. This module draws on both, and its unit is the vendor
relationship, because that is what a renewal date and an invoice attach to.

Why it is not just a list
-------------------------

A list of vendors is a spreadsheet, and every organization already has one in
somebody's inbox. What this does that a spreadsheet cannot is hold each
agreement up against the rules the organization wrote for itself:

  8.3   the terms they said must be in *every* AI agreement, checked off one
        contract at a time — so "we require breach notification" becomes "and
        these four agreements do not have it"
  8.5   what they decided happens when a vendor adds AI to something already
        bought, checked against the vendors who have done exactly that
  8.7b  what they said counts as cost, checked against what was actually
        estimated before signing
  7.1   what must never reach a general-purpose tool, checked against the
        holdings each vendor can see — the join between this module and the
        data register

Nothing here is inferred beyond those pairings. A tool that decided on its own
which vendors were risky would be making a procurement judgment it is not
qualified to make, and the first time it was wrong nobody would trust the
other findings either.

What it does not do
-------------------

It does not hold contracts, invoices or payment details, and it does not talk
to a finance system. The amount recorded is what somebody typed, for the
purpose of noticing that four tools do the same thing. It is a governance
register, not a general ledger.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from app.audit import CORPUS, atomic_write
from app.authz import Actor

#: Where a tenant's registry lives. Routed through `tenant.scoped`, like every
#: other file an agency owns.
VENDORS_FILE = CORPUS / "config" / "vendor_registry.json"

#: Where the relationship actually is. Appendix C's lifecycle stage, in the
#: words somebody in a purchasing office would use, and with the two endings a
#: registry usually forgets: turned down, and retired. Both matter — "we looked
#: at this and said no" is the most useful record there is when the same
#: product is proposed again eighteen months later.
STATUS = {
    "in_use": "In use today",
    "pilot": "In a pilot",
    "evaluating": "Being looked at",
    "proposed": "Proposed, not bought yet",
    "declined": "Looked at and turned down",
    "retired": "Retired",
}

#: How much AI is in it. The middle two are where governance is usually lost:
#: a product bought for something else that grew an AI feature, and one the
#: vendor switched on without asking.
INVOLVEMENT = {
    "core": "AI is what the product is",
    "feature": "AI is one feature inside a product that does other things",
    "added": "The vendor added AI to something we already had",
    "none": "No AI in it that we know of",
    "unknown": "We are not sure",
}

#: What the price is per. "Unknown" is a real answer and gets counted as one
#: rather than quietly treated as zero.
BASIS = {
    "year": "A year",
    "month": "A month",
    "per_user": "Each person, each month",
    "once": "One-off",
    "usage": "How much we use it",
    "free": "No charge",
    "unknown": "We are not sure",
}

#: Appendix E's two dimensions, asked in plain language. The tier follows from
#: them rather than being picked, because a vendor choosing their own
#: disclosure tier is the whole problem the appendix was written to solve.
CRITICALITY = {
    "high": "It informs decisions about people — permits, benefits, "
            "enforcement, employment",
    "low": "It does not decide anything about anyone",
    "unknown": "We are not sure",
}
FACING = {
    "public": "Members of the public use it, or see its output",
    "internal": "Only staff use it",
    "unknown": "We are not sure",
}

#: Appendix E, section 1 question 4 — the single question that has caused more
#: trouble than the other twenty put together.
TRAINING = {
    "no": "No — our information is not used to improve their product",
    "yes": "Yes",
    "opt_out": "Only unless we opt out",
    "unknown": "We have not asked",
}

#: The client's standing requirement, and Appendix E's Tier 3. "We have not
#: asked" is separated from "they said no" on purpose: one is a gap in the
#: file and the other is a decision.
ACCESSIBILITY = {
    "report": "A conformance report is on file — a VPAT or equivalent",
    "claimed": "They say it conforms; nothing on file",
    "no": "They have not claimed conformance",
    "unknown": "We have not asked",
}

#: How the thing arrived. The last option is the most common way AI enters a
#: government and the easiest to miss — nothing anywhere collected the route
#: before, and it matters because the most common route is the one nobody
#: decided on.
ROUTE = {
    "activated": "Activated inside something we already owned — a feature "
                 "switched on in a product already in place",
    "cooperative": "Taken from another government's agreement or a "
                   "cooperative purchase",
    "built": "Built or configured internally — there may be no supplier at "
             "all; the entry still exists",
    "bought": "Bought new",
    "found": "Found already present, because a vendor added it to something "
             "we already had — nobody in the organization decided anything",
}

#: Three answers per term, and there is no fourth. No "not applicable": a
#: term the organisation required and did not get is exactly what this
#: register has to record.
PRESENT = "present"
ABSENT = "absent"
NOT_ASKED = "not_asked"
TERM_ANSWERS = {PRESENT: "Present", ABSENT: "Absent",
                NOT_ASKED: "Not asked"}

#: The ten terms as Module One 8.3 writes them, in the order it gives them.
#: Where an organisation added terms of their own, those appear here
#: identically. The application adds none of its own and removes none of
#: theirs — these are the defaults for an organisation that took the
#: recommended list.
#:
#: Keyed exactly as Module One keys them. This list had drifted: it called
#: two of the terms `what_ai` and `return_delete` where Module One says
#: `disclose` and `return`, so a term marked on a vendor under one key was
#: invisible to anything reading it under the other. Old keys are migrated
#: on read — see `_RENAMED`.
TERMS = (
    ("disclose", "Tell us what AI is in the product and who built it"),
    ("notice", "Tell us before changes go live"),
    ("accuracy", "Commit to how accurate it is and how well it performs"),
    ("audit", "Let us inspect or audit how it's working"),
    ("return", "Return and delete our information when we leave"),
    ("breach", "Notify us of a security breach within the time we set"),
    ("staging", "Testing or staging environments for staff training and "
                "product testing prior to production-environment updates"),
    ("accessibility", "Provide accessibility documentation"),
    ("indemnity", "Cover us if someone claims the output infringes their "
                  "rights"),
    ("subcontractors", "Disclose who else is involved — subcontractors and "
                       "the company whose AI is underneath the tool"),
)

#: The eight cost categories as Module One 8.7 writes them. The figures
#: themselves live on Budget; this records which categories were considered,
#: which is what 8.7 asked.
#:
#: Two of these had been replaced with categories Module One does not have —
#: storage, and support — in place of getting your data ready and ongoing
#: monitoring. The list is Module One's, and the specification says so.
COST_CATEGORIES = (
    ("licence", "The license or subscription"),
    ("setup", "Setting it up"),
    ("training", "Training staff"),
    ("staff_time", "Staff time to run it"),
    ("data_prep", "Getting your data ready"),
    ("integration", "Connecting it to other systems"),
    ("monitoring", "Ongoing monitoring and review"),
    ("exit", "What it costs to leave"),
)

#: Keys this module used before it was brought back in line with Module One,
#: mapped to the keys Module One uses. Applied on read, so nothing already
#: marked is lost.
_RENAMED = {"what_ai": "disclose", "return_delete": "return"}

#: 6.4 · Have you actually opted out? Shown only where the training answer
#: is "only unless we opt out". An unexercised opt-out is the same as no
#: term, and the finding says so.
OPTED_OUT = {"yes": "Yes", "no": "No"}

#: 7 · How the vendor has behaved. Recorded facts for whoever decides
#: whether to buy from them again — never a score, a rating or a grade.
BEHAVED_NOTICE = {
    "always": "Every time", "sometimes": "Sometimes", "never": "Never",
    "no_change": "Nothing has changed yet", "unknown": "We would not know",
}
BEHAVED_STAGING = {
    "included": "Yes, included", "extra": "Yes, for an extra charge",
    "no": "No", "not_asked": "We did not ask",
}
BEHAVED_ANSWERS = {
    "fully": "Fully", "partly": "Partly", "no": "No",
    "not_asked": "We did not ask",
}
BEHAVED_RENEWAL = {
    "held": "Held the price", "raised": "Raised it",
    "changed": "Changed the terms", "not_yet": "Not renewed yet",
}

_LIMIT = 200
_LONG = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(value: Any, limit: int = _LIMIT) -> str:
    text = "".join(c for c in str(value or "") if c.isprintable())
    return text.strip()[:limit]


def _money(value: Any) -> float:
    """A number from whatever somebody typed in a money field.

    "$41,500/yr" is what a person writes and "41500" is what a spreadsheet
    wants. Refusing the first is how a register acquires a column of zeroes.
    """
    text = re.sub(r"[^0-9.]", "", str(value or ""))
    if not text or text.count(".") > 1:
        return 0.0
    try:
        return round(float(text), 2)
    except ValueError:
        return 0.0


def _a_date(value: Any) -> str:
    """An ISO date, or "" — never a guess. A wrong renewal date is worse than
    none, because somebody will plan around it."""
    text = _clip(value, 32)
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return ""


def must_tell_you(criticality: str, facing: str, *,
                  required: list[str] | None = None) -> dict[str, Any]:
    """What this vendor has to disclose, as sentences.

    This replaced a tier model — four numbered tiers with names, derived
    from one agency's vendor-disclosure appendix. Three rules now bind this
    panel and the old construction broke all three: it never renders a tier
    name, a number or a letter, because all three collide with the
    organization's own scrutiny levels, and that collision is what made the
    earlier version unusable. It never names another organization's
    framework, appendix or lettering.

    What a vendor must disclose is the organization's own answer at Module
    One 8.3, read back as obligations. Two questions decide which of those
    obligations apply here, and the panel says why in the same breath.

    `required` is the organization's own list of terms, so that an
    organization which required nothing specific is told so plainly rather
    than being shown this application's opinion of what a vendor owes.
    """
    # `required` may be keys, or the organization's own rows from 8.3 with
    # their own labels — including terms they added themselves, which this
    # module's list does not know the words for.
    labels = dict(TERMS)
    keys: list[str] = []
    for item in (required if required is not None
                 else [key for key, _ in TERMS]):
        if isinstance(item, dict):
            if item.get("required", True):
                keys.append(str(item.get("value", "")))
                labels.setdefault(str(item.get("value", "")),
                                  str(item.get("label", "")))
        else:
            keys.append(str(item))
    required = [k for k in keys if k]

    if not required:
        return {
            "applies": [],
            "says": ("Your framework does not require anything specific of "
                     "a vendor here. You can add to what you require at any "
                     "time; anything you add applies to new agreements from "
                     "that day."),
            "because": "",
        }

    decides = criticality == "high"
    public = facing == "public"

    # Which of their own terms are the disclosure obligations, and which of
    # those bite hardest given what this tool does and who sees it.
    applies = [k for k in required if k in labels]
    because: list[str] = []
    if decides:
        because.append("this informs decisions about people")
    if public:
        because.append("the public sees its output")
    if criticality == "unknown" or facing == "unknown":
        because.append("you have not said what it decides or who sees it")

    reason = " and ".join(because) if because else ""
    listed = " · ".join(labels[k].lower() for k in applies)
    said = (f"Because {reason}, your framework requires them to tell you: "
            f"{listed}." if reason
            else f"Your framework requires them to tell you: {listed}.")

    return {
        "applies": applies,
        "says": said,
        "because": ("You decided this at question 8.3. A vendor choosing for "
                    "themselves what to disclose is the problem that "
                    "question exists to solve."),
    }


@dataclass
class Vendor:
    """One supplier relationship, as a purchasing office would recognize it."""

    id: str = ""
    #: The company.
    name: str = ""
    #: The thing you actually bought from them.
    product: str = ""
    #: What it is used for here, in their words.
    what_for: str = ""
    #: What else it could do — the client's "use case potential", and the
    #: answer to their own 8.6, "check whether a tool you already have can
    #: resolve the problem before buying a new one".
    could_also: str = ""
    status: str = ""
    involvement: str = ""
    #: A role, never a person.
    owner: str = ""
    #: What it costs and what that is per.
    amount: float = 0.0
    basis: str = ""
    #: A reference somebody can look up. Not the contract itself.
    contract: str = ""
    renewal: str = ""
    #: How the thing arrived. The most common route is the one nobody
    #: decided on, and nothing collected it before.
    route: str = ""
    #: Each of the terms they named at 8.3, marked Present, Absent or Not
    #: asked. Three answers and no fourth: a term the organisation required
    #: and did not get is exactly what this register has to record, and
    #: "absent" and "nobody asked" are not the same fact — one is a decision
    #: and the other is a gap in the file.
    #:
    #: This was a list of the terms that were present, which could not tell
    #: those two apart. Old rows are migrated on read; see `_terms`.
    terms: dict[str, str] = field(default_factory=dict)
    #: Which of the cost parts they named at 8.7 were estimated before this
    #: was committed to, on the same three answers. The figures themselves
    #: live on Budget — this records which categories were considered, which
    #: is what the question asked.
    costed: dict[str, str] = field(default_factory=dict)
    criticality: str = ""
    facing: str = ""
    training: str = ""
    accessibility: str = ""
    #: 6.4 to 6.6 — the opt-out, where the training answer relied on one.
    opted_out: str = ""
    opted_out_on: str = ""
    opted_out_by: str = ""
    #: 7.1 to 7.5 — how the vendor has actually behaved.
    behaved_notice: str = ""
    behaved_staging: str = ""
    behaved_answers: str = ""
    behaved_renewal: str = ""
    behaved_note: str = ""
    #: 8.16's other answer. A blank date is "not recorded"; this is "there is
    #: no renewal", which is a different fact.
    no_renewal: bool = False
    #: 8.17 — which projects use this. Many to many: one supplier can serve
    #: four projects, and neither side owns the other.
    projects: list[str] = field(default_factory=list)
    #: Which holdings from the data register this vendor can see. The join
    #: between the two paid modules, and the reason the data one came first.
    holdings: list[str] = field(default_factory=list)
    #: Every change the vendor told the organization about — or made without
    #: telling it — in the vendor's own words, newest last. Integrity reads
    #: these for the projects this vendor serves; nothing here ever deletes
    #: one. Written only through `record_change`, never by the edit form.
    changes: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    added_at: str = ""
    added_by: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["status_label"] = STATUS.get(self.status, "")
        out["involvement_label"] = INVOLVEMENT.get(self.involvement, "")
        out["basis_label"] = BASIS.get(self.basis, "")
        out["training_label"] = TRAINING.get(self.training, "")
        out["accessibility_label"] = ACCESSIBILITY.get(self.accessibility, "")
        out["route_label"] = ROUTE.get(self.route, "")
        # Sentences, not a tier. See `must_tell_you` for why the numbered
        # tiers went: they collided with the organisation's own scrutiny
        # levels, and a screen showing "Tier 2" beside a framework whose
        # levels are Routine and Elevated asks the reader to hold two
        # numbering schemes at once.
        out["must_tell_you"] = must_tell_you(self.criticality, self.facing)
        out["terms_absent"] = [k for k, v in (self.terms or {}).items()
                               if v == ABSENT]
        out["a_year"] = a_year(self)
        return out


def a_year(vendor: Vendor) -> float:
    """What this costs in a year, where that can be said honestly.

    A one-off, a usage-based bill and a per-person price are all real answers
    and none of them is an annual figure without something this register does
    not hold — a headcount, or last year's invoices. Those return 0 and are
    counted separately, so the total never quietly includes a number nobody
    can defend.
    """
    if vendor.basis == "year":
        return vendor.amount
    if vendor.basis == "month":
        return round(vendor.amount * 12, 2)
    return 0.0


def _row(raw: dict[str, Any]) -> Vendor:
    """A stored vendor, read into the current shape.

    Every read goes through here. Rows saved before the terms became
    Present / Absent / Not asked still hold them as a list, and a Vendor built
    from one directly broke the first line of code that asked which terms
    were absent — the screen's own summary among them.
    """
    known = {k: v for k, v in (raw or {}).items()
             if k in Vendor.__dataclass_fields__}
    vendor = Vendor(**known)
    vendor.terms = _marked(vendor.terms)
    vendor.costed = _marked(vendor.costed)
    return vendor


def _rows() -> list[Vendor]:
    return [_row(v) for v in _read().get("vendors", [])]


def _file():
    from app import tenant
    return tenant.scoped(VENDORS_FILE)


def _read() -> dict[str, Any]:
    path = _file()
    if not path.is_file():
        return {"vendors": []}
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"vendors": []}
    if not isinstance(held, dict):
        return {"vendors": []}
    held.setdefault("vendors", [])
    return held


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


def _one_of(raw: dict[str, Any], base: Vendor, key: str,
            allowed: dict[str, str], missing: str = "") -> str:
    value = raw.get(key, getattr(base, key)) or ""
    return value if value in allowed else missing


def _marked(held: Any) -> dict[str, str]:
    """Terms or cost categories, as Present / Absent / Not asked.

    Migrates the older shape on read. That was a list of the terms that were
    present, which could not tell an absent term from one nobody asked
    about — and those are not the same fact. Everything on an old list
    becomes Present; everything else is simply unrecorded, which is honest,
    because the old shape never held the answer.
    """
    if isinstance(held, dict):
        return {_RENAMED.get(str(k), str(k))[:60]: v for k, v in held.items()
                if v in TERM_ANSWERS}
    if isinstance(held, list):
        return {_RENAMED.get(str(k), str(k))[:60]: PRESENT
                for k in held[:40] if str(k).strip()}
    return {}


def _clean(raw: dict[str, Any], existing: Vendor | None = None) -> Vendor:
    """One vendor from whatever the browser sent, bounded and validated."""
    base = existing or Vendor()
    return Vendor(
        id=base.id or raw.get("id") or f"VN-{uuid.uuid4().hex[:8].upper()}",
        name=_clip(raw.get("name", base.name)),
        product=_clip(raw.get("product", base.product)),
        what_for=_clip(raw.get("what_for", base.what_for), _LONG),
        could_also=_clip(raw.get("could_also", base.could_also), _LONG),
        status=_one_of(raw, base, "status", STATUS),
        involvement=_one_of(raw, base, "involvement", INVOLVEMENT, "unknown"),
        owner=_clip(raw.get("owner", base.owner)),
        amount=_money(raw.get("amount", base.amount)),
        basis=_one_of(raw, base, "basis", BASIS, "unknown"),
        contract=_clip(raw.get("contract", base.contract), 80),
        renewal=_a_date(raw.get("renewal", base.renewal)),
        route=_one_of(raw, base, "route", ROUTE, ""),
        terms=_marked(raw.get("terms", base.terms)),
        costed=_marked(raw.get("costed", base.costed)),
        criticality=_one_of(raw, base, "criticality", CRITICALITY, "unknown"),
        facing=_one_of(raw, base, "facing", FACING, "unknown"),
        training=_one_of(raw, base, "training", TRAINING, "unknown"),
        accessibility=_one_of(raw, base, "accessibility", ACCESSIBILITY,
                              "unknown"),
        opted_out=_one_of(raw, base, "opted_out", OPTED_OUT, ""),
        opted_out_on=_a_date(raw.get("opted_out_on", base.opted_out_on)),
        opted_out_by=_clip(raw.get("opted_out_by", base.opted_out_by)),
        behaved_notice=_one_of(raw, base, "behaved_notice", BEHAVED_NOTICE, ""),
        behaved_staging=_one_of(raw, base, "behaved_staging",
                                BEHAVED_STAGING, ""),
        behaved_answers=_one_of(raw, base, "behaved_answers",
                                BEHAVED_ANSWERS, ""),
        behaved_renewal=_one_of(raw, base, "behaved_renewal",
                                BEHAVED_RENEWAL, ""),
        behaved_note=_clip(raw.get("behaved_note", base.behaved_note), _LONG),
        no_renewal=bool(raw.get("no_renewal", base.no_renewal)),
        projects=[_clip(p, 20)
                  for p in (raw.get("projects", base.projects) or [])][:50],
        holdings=[_clip(h, 40)
                  for h in (raw.get("holdings", base.holdings) or [])][:100],
        # Kept as they are. The edit form never writes the change log, so a
        # save cannot rewrite or drop a change somebody recorded.
        changes=list(base.changes or []),
        notes=_clip(raw.get("notes", base.notes), _LONG),
        added_at=base.added_at or _now(),
        added_by=base.added_by,
        updated_at=_now(),
    )


# ------------------------------------------------------ what they chose at 8.3

def _from_question(key: str, answers: dict[str, Any] | None,
                   ) -> list[dict[str, Any]]:
    """The options of one multi-select question, marked with what they picked.

    Used for 8.3's required terms and 8.7b's cost parts. Both work the same
    way as 7.1 does for the data register: their own list, including anything
    they added themselves, never a second vocabulary invented here.
    """
    from app import module_one, versions

    if answers is None:
        answers = versions.state().get("working") or {}
    question = module_one.by_key(key)
    if question is None:
        return []

    chosen, _ = module_one.value_of(answers, key)
    chosen = chosen if isinstance(chosen, list) else []

    out: list[dict[str, Any]] = []
    for option in module_one.options_for(question, answers):
        if option.value == module_one.UNKNOWN:
            continue
        out.append({"value": option.value, "label": option.label,
                    "required": option.value in chosen})
    return out


def required_terms(answers: dict[str, Any] | None = None
                   ) -> list[dict[str, Any]]:
    """8.3 — the terms they said must be in every AI agreement."""
    return _from_question("proc.terms", answers)


def cost_parts(answers: dict[str, Any] | None = None
               ) -> list[dict[str, Any]]:
    """8.7b — what they said counts as cost."""
    return _from_question("proc.cost_parts", answers)


# ------------------------------------------------------------------ the list

def listing() -> dict[str, Any]:
    """Every vendor recorded, with the vocabularies the form is built from."""
    from app import holdings

    rows = _rows()
    terms = required_terms()
    # The panel is drawn from their own list, in their own words, and
    # nothing else. Built here rather than in `as_dict`, which has no
    # framework to read.
    shown = []
    for v in rows:
        out = v.as_dict()
        out["must_tell_you"] = must_tell_you(v.criticality, v.facing,
                                             required=terms)
        shown.append(out)
    return {
        "vendors": shown,
        "statuses": STATUS,
        "involvement": INVOLVEMENT,
        "bases": BASIS,
        "criticality": CRITICALITY,
        "facing": FACING,
        "training": TRAINING,
        "accessibility": ACCESSIBILITY,
        "routes": ROUTE,
        "term_answers": TERM_ANSWERS,
        "opted_out": OPTED_OUT,
        "behaved": {"notice": BEHAVED_NOTICE, "staging": BEHAVED_STAGING,
                    "answers": BEHAVED_ANSWERS, "renewal": BEHAVED_RENEWAL},
        "training_consequence": TRAINING_CONSEQUENCE,
        "training_not_listed": TRAINING_IS_NOT_IN_THE_LIST,
        "renewal_window": renewal_window(),
        "money_line": money_line(rows),
        "terms": terms,
        "cost_parts": cost_parts(),
        # So a vendor can be tied to what it can actually see. Names only —
        # the data register is the place that holds the detail.
        "holdings": [{"id": h["id"], "name": h["name"]}
                     for h in holdings.listing()["holdings"]],
        "summary": summary(rows),
    }


# ===========================================================================
# Findings
# ===========================================================================

from app import spine  # noqa: E402  (here to avoid a cycle at import)

SHARED_FINDINGS = ("finding.term_absent", "finding.gap_no_owner")

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.vd.trains_on_us", "Vendors",
        "They use your information to improve their product, or only unless "
        "you opt out with no record of opting out",
        "They use your information to improve their product. You said that "
        "term has to be in every agreement."),
    spine.Finding(
        "finding.vd.never_asked", "Vendors",
        "Nobody has asked whether they train on your information, on "
        "something in use today",
        "Nobody has asked [vendor] whether they use your information to "
        "improve their product."),
    spine.Finding(
        "finding.vd.no_staging", "Vendors",
        "The staging term is marked absent and the organization required it",
        "You require a testing environment in every agreement. This one does "
        "not have it."),
    spine.Finding(
        "finding.vd.no_change_notice", "Vendors",
        "The notice term is marked absent on something in use today",
        "You require notice before changes. Anything [vendor] changes, you "
        "will find out by noticing."),
    spine.Finding(
        "finding.vd.arrived_undecided", "Vendors",
        "The route is Found already present and no project accounts for it",
        "This arrived inside something you already had and no project "
        "accounts for it."),
    spine.Finding(
        "finding.vd.accessibility_unasked", "Vendors",
        "Nobody asked for accessibility documentation and the organization "
        "requires it before purchase",
        "You said you require accessibility documentation before buying. "
        "Nobody asked for it."),
    spine.Finding(
        "finding.vd.renewal_no_review", "Vendors",
        "A renewal falls inside the notice window and the projects it serves "
        "have no current Measure cycle",
        "This renews on [date] and nothing has been measured since [date]."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}

#: Said where the training answer is anything but no. The one term that
#: cannot be fixed afterwards, so the consequence is stated at the moment
#: the answer is given rather than at sunset when it is too late.
#:
#: The specification's own draft of this sentence ends "what it taught their
#: model", and that is the one word this product never writes — "Never write
#: model. Write tool." It says tool.
TRAINING_CONSEQUENCE = (
    "You can get your information back and you can have it deleted. You "
    "cannot get back what it taught their tool. At the end of this "
    "agreement there is nothing to return. That is what 'your data stays "
    "yours' is protecting, and it is the one term that cannot be fixed "
    "afterwards.")

#: Module One 8.3 does not currently list a term forbidding training. The
#: nearest is "return and delete our information when we leave", which does
#: not deliver it — a vendor can return the data, delete it, and still keep
#: everything the data taught the model.
#:
#: So this surface asks the question itself rather than waiting for the
#: framework to be reopened, and carries the reason rather than asserting
#: the requirement bare. An organisation improves its framework at the next
#: procurement rather than by going back over what it already signed.
TRAINING_IS_NOT_IN_THE_LIST = (
    "Your list of required terms does not include one forbidding them from "
    "training on your information. The closest is returning and deleting "
    "it, and that is a different term — they can return it, delete it, and "
    "still keep what it taught. This asks the question anyway.")


def findings(rows: list[Vendor] | None = None, *,
             requires_staging: bool = False,
             requires_accessibility_docs: bool = False,
             on_a_project: dict[str, bool] | None = None,
             required: set[str] | None = None,
             renewals_unmeasured: set[str] | None = None
             ) -> list[dict[str, Any]]:
    """Contradictions against the organization's own answers, and nothing
    else. Never an external standard, never a benchmark.

    `required` is the set of terms the organization required at 8.3. Where
    it is given, only a required term marked absent is a finding — a term
    they never asked for being absent contradicts nothing of theirs.
    `renewals_unmeasured` is the vendors renewing inside the window whose
    projects have no Measure check on record.
    """
    if rows is None:
        rows = _rows()
    on_a_project = dict(on_a_project or {})
    for row in rows:
        if row.projects:
            on_a_project.setdefault(row.id, True)
    found: list[dict[str, Any]] = []

    for row in rows:
        live = row.status in ("in_use", "pilot")

        # An opt-out counts only once somebody has actually opted out. An
        # unexercised opt-out is the same as no term.
        relied_on_opt_out = row.training == "opt_out" and row.opted_out != "yes"
        if row.training == "yes" or relied_on_opt_out:
            found.append({
                "id": "finding.vd.trains_on_us", "vendor": row.id,
                "says": ("They use your information to improve their "
                         "product. You said that term has to be in every "
                         "agreement.")})
        elif row.training == "unknown" and row.status == "in_use":
            found.append({
                "id": "finding.vd.never_asked", "vendor": row.id,
                "says": (f"Nobody has asked {row.name or 'this vendor'} "
                         f"whether they use your information to improve "
                         f"their product.")})

        if requires_staging and row.terms.get("staging") == ABSENT:
            found.append({
                "id": "finding.vd.no_staging", "vendor": row.id,
                "says": ("You require a testing environment in every "
                         "agreement. This one does not have it.")})

        if live and row.terms.get("notice") == ABSENT:
            found.append({
                "id": "finding.vd.no_change_notice", "vendor": row.id,
                "says": (f"You require notice before changes. Anything "
                         f"{row.name or 'this vendor'} changes, you will "
                         f"find out by noticing.")})

        if row.route == "found" and not on_a_project.get(row.id):
            found.append({
                "id": "finding.vd.arrived_undecided", "vendor": row.id,
                "says": ("This arrived inside something you already had and "
                         "no project accounts for it.")})

        if requires_accessibility_docs and row.accessibility == "unknown":
            found.append({
                "id": "finding.vd.accessibility_unasked", "vendor": row.id,
                "says": ("You said you require accessibility documentation "
                         "before buying. Nobody asked for it.")})

        for key, answer in row.terms.items():
            if answer != ABSENT or key in ("staging", "notice"):
                continue
            if required is not None and key not in required:
                continue
            found.append({
                "id": "finding.term_absent", "vendor": row.id,
                "says": ("You require this term in every agreement. "
                         "This one does not have it."),
                "term": key})

        # Shared, and worded by the spine: 8.12 left empty.
        if not row.owner.strip():
            found.append({
                "id": "finding.gap_no_owner", "vendor": row.id,
                "says": spine.BY_FINDING["finding.gap_no_owner"].says})

        if row.id in (renewals_unmeasured or set()):
            found.append({
                "id": "finding.vd.renewal_no_review", "vendor": row.id,
                "says": (f"This renews on {row.renewal} and nothing has been "
                         f"measured on the projects it serves.")})
    return found


def money_line(rows: list[Vendor] | None = None) -> str:
    """A total of what was typed in, never an estimate.

    Across entries in use or in a pilot only. Where anything material is
    unpriced the line says so, rather than presenting a total that quietly
    omits it.
    """
    if rows is None:
        rows = _rows()
    live = [v for v in rows if v.status in ("in_use", "pilot")]
    total = sum(a_year(v) for v in live)
    unpriced = sum(1 for v in live if not v.amount)
    # Priced, but per person, by use or once — a real figure that is not a
    # yearly one without a headcount or an invoice this register lacks.
    other_basis = sum(1 for v in live if v.amount and not a_year(v))
    said = f"${total:,.0f} a year across what is in use or in a pilot"
    if unpriced:
        said += f", and {unpriced} with no cost recorded"
    said += "."
    if other_basis:
        said += (f" {other_basis} priced another way, which cannot be added "
                 f"up as a year.")
    return said


def summary(rows: list[Vendor] | None = None) -> dict[str, Any]:
    """What the registry says about the portfolio as a whole."""
    if rows is None:
        rows = _rows()
    live = [v for v in rows if v.status in ("in_use", "pilot")]
    yearly = [a_year(v) for v in live]
    return {
        "total": len(rows),
        "in_use": sum(1 for v in rows if v.status == "in_use"),
        "with_ai": sum(1 for v in rows
                       if v.involvement in ("core", "feature", "added")),
        "unowned": sum(1 for v in rows if not v.owner.strip()),
        # Said as two numbers on purpose. One total with a footnote is a
        # number people quote without the footnote.
        "a_year": round(sum(yearly), 2),
        "not_totalled": sum(1 for v in live if a_year(v) == 0),
        "renewing_soon": len(renewing_soon(rows)),
    }


#: Used only where the organization set no notice period of its own, and
#: then named on the screen as exactly that — "Renewing, no window set" —
#: rather than presented as if it were theirs.
NO_WINDOW_DAYS = 90


def renewal_window(answers: dict[str, Any] | None = None) -> dict[str, Any]:
    """The organization's own notice period, from Module One 9.9.

    The application supplies no window of its own. Where 9.9 is unanswered,
    or answered "no set notice period" or "something else", renewals inside
    ninety days are counted and the label says so.
    """
    from app import module_one, versions
    if answers is None:
        try:
            answers = versions.state().get("working") or {}
        except Exception:                                     # noqa: BLE001
            answers = {}
    value, _ = module_one.value_of(answers, "watch.notice")
    if str(value) in ("30", "60", "90"):
        days = int(value)
        return {"days": days, "theirs": True,
                "label": "Renewing soon",
                "says": f"You said {days} days' notice."}
    return {"days": NO_WINDOW_DAYS, "theirs": False,
            "label": "Renewing, no window set",
            "says": "You have not set a notice period, so this counts "
                    "renewals in the next ninety days."}


def renewing_soon(rows: list[Vendor] | None = None,
                  within_days: int | None = None) -> list[dict[str, str]]:
    """What comes up for renewal, soonest first, inside the organization's
    own notice window — or ninety days, said as such, where they set none."""
    if within_days is None:
        within_days = renewal_window()["days"]
    if rows is None:
        rows = _rows()
    today = clock.today()
    out = []
    for vendor in rows:
        if not vendor.renewal or vendor.status in ("declined", "retired"):
            continue
        try:
            when = date.fromisoformat(vendor.renewal)
        except ValueError:
            continue
        days = (when - today).days
        if days <= within_days:
            out.append({"id": vendor.id, "name": vendor.name,
                        "product": vendor.product, "renewal": vendor.renewal,
                        "days": days})
    return sorted(out, key=lambda r: r["days"])


def save(raw: dict[str, Any], actor: Actor) -> dict[str, Any]:
    """Add or update one vendor.

    Not gated on a capacity, for the same reason as the data register: this is
    the organization's own record of its own agreements, in its own container.
    Recorded, though — every write names who made it.
    """
    if not _clip(raw.get("name")):
        return {"ok": False,
                "error": "A vendor needs a name — the company you buy from."}

    held = _read()
    rows = {v["id"]: v for v in held.get("vendors", [])}
    wanted = raw.get("id") or ""
    existing = _row(rows[wanted]) if wanted in rows else None

    vendor = _clean(raw, existing)
    if existing is None:
        vendor.added_by = _clip(actor.name) or "unnamed"
    rows[vendor.id] = asdict(vendor)
    held["vendors"] = list(rows.values())
    _write(held)

    _record("record_vendor" if existing is None else "update_vendor", actor,
            {"vendor": vendor.id, "name": vendor.name})
    return {"ok": True, "vendor": vendor.as_dict(), "state": listing()}


NOT_TOLD = "We were not told"


def record_change(vendor_id: str, actor: Actor, *, what: str,
                  told_on: str = "", not_told: bool = False,
                  open_versions: bool = True) -> dict[str, Any]:
    """The vendor changed something. Recorded on the vendor entry in their
    own words — a summary written today is the thing somebody disputes in
    two years.

    Where `open_versions`, a version record is also opened on each project
    this vendor serves, because on Projects anything the vendor tells you
    about opens one. Either way Integrity counts the change against those
    projects until a check is marked complete after it.
    """
    what = str(what or "").strip()
    if not what:
        return {"ok": False, "error": "Paste what the vendor said changed, or "
                                      "describe the change if they said "
                                      "nothing."}
    held = _read()
    rows = {v["id"]: v for v in held.get("vendors", [])}
    if vendor_id not in rows:
        return {"ok": False, "error": f"No vendor {vendor_id!r}."}
    vendor = _row(rows[vendor_id])
    change = {
        "ref": "CH-" + uuid.uuid4().hex[:6].upper(),
        "what": what[:_LONG * 3],
        "told_on": "" if not_told else _a_date(told_on),
        "not_told": bool(not_told),
        "recorded_on": clock.today_str(),
        "recorded_at": _now(),
        "by": _clip(actor.name) or "unnamed",
        "versions": [],
    }
    opened = []
    if open_versions and vendor.projects:
        from app import projects
        for ref in vendor.projects:
            if projects.one(ref) is None:
                continue
            got = projects.open_version(
                ref, actor, what=f"From {vendor.name or 'the vendor'}: {what}",
                told_on=change["told_on"], not_told=bool(not_told))
            if got.get("ok"):
                opened.append({"project": ref, "version": got["version"]["ref"]})
    change["versions"] = opened
    vendor.changes = list(vendor.changes or []) + [change]
    vendor.updated_at = _now()
    rows[vendor_id] = asdict(vendor)
    held["vendors"] = list(rows.values())
    _write(held)
    _record("record_vendor_change", actor,
            {"vendor": vendor_id, "name": vendor.name, "change": change["ref"],
             "what": what[:300], "not_told": bool(not_told),
             "versions_opened": opened})
    return {"ok": True, "change": change, "vendor": vendor.as_dict(),
            "state": listing()}


def changes_by_project(rows: list[Vendor] | None = None
                       ) -> dict[str, list[str]]:
    """The dates each project's vendors recorded a change, for Integrity."""
    rows = _rows() if rows is None else rows
    out: dict[str, list[str]] = {}
    for vendor in rows:
        for change in vendor.changes or []:
            for ref in vendor.projects or []:
                out.setdefault(ref, []).append(str(change.get("recorded_on") or ""))
    return out


def forget(vendor_id: str, actor: Actor) -> dict[str, Any]:
    """Take a vendor off the registry."""
    held = _read()
    rows = [v for v in held.get("vendors", []) if v.get("id") != vendor_id]
    if len(rows) == len(held.get("vendors", [])):
        return {"ok": False, "error": f"No vendor {vendor_id!r}."}
    held["vendors"] = rows
    _write(held)
    _record("forget_vendor", actor, {"vendor": vendor_id})
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
                              "agreements. Recorded, not gated."})
    except Exception:
        pass


# ------------------------------------------------- what the registry tells them

def concerns(answers: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Where the registry and their own framework disagree.

    Every finding pairs something recorded here with something decided in the
    framework, and names the question it came from so it can be argued with.
    """
    from app import holdings as data_register, module_one, versions

    if answers is None:
        answers = versions.state().get("working") or {}
    rows = _rows()
    out: list[dict[str, str]] = []

    wanted = {t["value"]: t["label"]
              for t in required_terms(answers) if t["required"]}
    parts = {p["value"]: p["label"]
             for p in cost_parts(answers) if p["required"]}

    added_ai, _ = module_one.value_of(answers, "proc.added_ai")
    full_cost, _ = module_one.value_of(answers, "proc.full_cost")

    # What each holding contains, and which of those they banned at 7.1.
    banned, _ = module_one.value_of(answers, "data.never")
    banned = banned if isinstance(banned, list) else []
    labels = {o.value: o.label for o in module_one.options_for(
        module_one.by_key("data.never"), answers)}
    sensitive_holdings = {}
    for row in data_register.listing()["holdings"]:
        overlap = [labels.get(s, s) for s in row.get("sensitive", [])
                   if s in banned]
        if overlap:
            sensitive_holdings[row["id"]] = (row["name"], overlap[0])

    for vendor in rows:
        # A retired or declined vendor is a record, not an exposure.
        if vendor.status in ("declined", "retired"):
            continue
        where = f"{vendor.name}" + (f" — {vendor.product}"
                                    if vendor.product else "")

        missing = [label for value, label in wanted.items()
                   if value not in vendor.terms]
        if missing:
            out.append({
                "vendor": where, "id": vendor.id,
                "says": f"the agreement does not record {len(missing)} term"
                        f"{'' if len(missing) == 1 else 's'} you require: "
                        f"{missing[0].lower()}"
                        + (f", and {len(missing) - 1} more"
                           if len(missing) > 1 else ""),
                "against": "8.3 — the terms that must be in every agreement",
            })

        for holding_id in vendor.holdings:
            found = sensitive_holdings.get(holding_id)
            if not found:
                continue
            name, category = found
            if vendor.training in ("yes", "opt_out", "unknown"):
                out.append({
                    "vendor": where, "id": vendor.id,
                    "says": f"can see {name}, which holds "
                            f"{category.lower()}, and "
                            + {"yes": "their terms use our information to "
                                      "improve their product",
                               "opt_out": "their terms use our information "
                                          "unless we opt out",
                               "unknown": "nobody has asked whether our "
                                          "information trains their product"
                               }[vendor.training],
                    "against": "7.1 — what must never go into a "
                               "general-purpose AI tool",
                })

        if (vendor.facing == "public"
                and vendor.accessibility in ("no", "unknown")):
            out.append({
                "vendor": where, "id": vendor.id,
                "says": "is used by the public and has no accessibility "
                        "conformance on file",
                # Cited to the organization's own floor. This named one
                # agency's appendix and tier to every organization using the
                # product — the reference the specification says to remove
                # before anything else.
                "against": "Floor 4 — it works for people with disabilities",
            })

        if (vendor.involvement == "added" and added_ai == "as_new"
                and vendor.status == "in_use"):
            out.append({
                "vendor": where, "id": vendor.id,
                "says": "had AI added to a product you already owned, and is "
                        "recorded as in use without a review",
                "against": "8.5 — treat it as a new tool and review it "
                           "like one",
            })

        if full_cost == "yes" and parts:
            not_costed = [label for value, label in parts.items()
                          if value not in vendor.costed]
            if not_costed and vendor.status in ("in_use", "pilot"):
                out.append({
                    "vendor": where, "id": vendor.id,
                    "says": f"was committed to without estimating "
                            f"{not_costed[0].lower()}"
                            + (f" and {len(not_costed) - 1} other cost"
                               f"{'' if len(not_costed) == 2 else 's'}"
                               if len(not_costed) > 1 else ""),
                    "against": "8.7 — the full cost before you commit",
                })

        if not vendor.owner.strip():
            out.append({
                "vendor": where, "id": vendor.id,
                "says": "has nobody named against it",
                "against": "Floor 7 — somebody's name is on it",
            })

    return out
