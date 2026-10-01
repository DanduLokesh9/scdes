"""The framework is the brain. Nothing downstream exists without it.

This module answers one question — *does this agency have an adopted governance
framework loaded?* — and everything else in the application is gated on the
answer.

Why gate at all. The risk model, the approval gates, the vocabulary, the
required instruments and every citation are read out of the framework. Without
one there is nothing to read, so a registry, a lifecycle or a budget screen
would be showing structure the agency has not agreed to. That is not an empty
app; it is a misleading one. So the application refuses, and says why.

Three states an agency can be in:

  ``none``      No framework. Nothing but the Framework Builder is reachable.
  ``draft``     A framework is loaded but not recorded as adopted. Readable,
                and the app works, but every screen says it is provisional.
  ``adopted``   Loaded and recorded as adopted, with a date and by whom.

The distinction between *loaded* and *adopted* matters. Dropping a Word file
into a folder is not an act of governance; a council adopting it is. The app can
read an unadopted draft — that is how you review one before adopting — but it
never pretends the draft carries authority.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.audit import CORPUS

#: Where an adoption is recorded. Separate from the documents themselves: the
#: framework is the agency's file, the adoption is this application's record of
#: being told about it.
ADOPTION_FILE = CORPUS / "config" / "framework_adoption.json"

#: What a complete governance regime looks like, and what each part is for. The
#: builder walks these in order, because each one depends on the one above.
LAYERS = [
    {"key": "framework", "label": "Governance Framework",
     "dir": "framework",
     "why": "The constitution. Names who decides, the roles, the risk "
            "categories and the naming everything else inherits.",
     "required": True},
    {"key": "manual", "label": "Operations Manual",
     "dir": "manual",
     "why": "How the framework is carried out day to day — the procedures, the "
            "gates and the timelines.",
     "required": True},
    {"key": "appendices", "label": "Appendices",
     "dir": "appendices",
     "why": "The working instruments: the risk matrix, the intake form, the "
            "gate checklists, the registry.",
     "required": True},
    {"key": "charter", "label": "Charter and adoption memo",
     "dir": "charter",
     "why": "Evidence that whoever holds the authority actually adopted the "
            "above, and on what date. A standing body files its charter here; "
            "a single decision-maker files the memo appointing them.",
     "required": False},
]

#: File types the reader understands.
READABLE = (".docx", ".xlsx", ".pdf", ".md", ".txt")


@dataclass
class LayerStatus:
    key: str
    label: str
    why: str
    required: bool
    files: list[str] = field(default_factory=list)
    present: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FrameworkStatus:
    #: none | draft | adopted
    state: str
    layers: list[dict[str, Any]]
    #: True when every required layer has at least one readable document.
    complete: bool
    adopted_on: str = ""
    adopted_by: str = ""
    adopted_note: str = ""
    document_count: int = 0
    #: What the user is told, and what they can do about it.
    headline: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def usable(self) -> bool:
        """Whether the rest of the application may be entered at all."""
        return self.state in ("draft", "adopted")


def adoption_file() -> Path:
    """Where this agency's adoption is recorded. See app/tenant.py."""
    from app import tenant
    return tenant.scoped(ADOPTION_FILE)


def _files_in(directory: str) -> list[str]:
    """The documents in one layer — for the agency they belong to, and nobody
    else.

    There is one `corpus/` on this machine and it holds one agency's papers.
    This used to list it for whoever asked, so every agency that registered saw
    SCDES's framework, its operations manual and its fourteen appendices, all
    marked present. Reported by the client, who was right that they should not
    be visible: an agency's appendices are a function of its own framework, and
    an empty shelf is the truthful answer before it has one.
    """
    from app import tenant
    if not tenant.owns_corpus():
        return []
    path = CORPUS / directory
    if not path.is_dir():
        return []
    return sorted(f.name for f in path.iterdir()
                  if f.is_file() and f.suffix.lower() in READABLE
                  and not f.name.startswith("~$"))     # Word lock files


def _adoption() -> dict[str, Any]:
    path = adoption_file()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (ValueError, OSError):
        return {}


def status() -> FrameworkStatus:
    """What the agency has, and therefore what the application may do."""
    layers: list[LayerStatus] = []
    for spec in LAYERS:
        files = _files_in(spec["dir"])
        layers.append(LayerStatus(
            key=spec["key"], label=spec["label"], why=spec["why"],
            required=spec["required"], files=files, present=bool(files)))

    required = [ln for ln in layers if ln.required]
    complete = all(ln.present for ln in required)
    any_present = any(ln.present for ln in layers)
    total = sum(len(ln.files) for ln in layers)

    record = _adoption()
    if not any_present:
        state = "none"
    elif record.get("adopted_on"):
        state = "adopted"
    else:
        state = "draft"

    result = FrameworkStatus(
        state=state,
        layers=[ln.as_dict() for ln in layers],
        complete=complete,
        adopted_on=record.get("adopted_on", ""),
        adopted_by=record.get("adopted_by", ""),
        adopted_note=record.get("note", ""),
        document_count=total,
    )
    result.headline, result.detail = _wording(result, layers)
    return result


def _wording(s: FrameworkStatus, layers: list[LayerStatus]) -> tuple[str, str]:
    missing = [ln.label for ln in layers if ln.required and not ln.present]

    if s.state == "none":
        return ("No governance framework loaded",
                "Everything this application does is read out of your adopted "
                "framework — the risk model, the approval gates, the required "
                "instruments and every citation. Until one is here there is "
                "nothing to read, so the rest of the application stays closed. "
                "Load yours, or start from the reference framework.")

    if s.state == "draft" and missing:
        return (f"Framework loaded, {len(missing)} part(s) still missing",
                "You can look around, but " + ", ".join(missing) + " "
                + ("is" if len(missing) == 1 else "are") +
                " not here yet, so any screen that depends on them will say so "
                "rather than guess.")

    if s.state == "draft":
        return ("Framework loaded but not adopted",
                "All the parts are here and readable. Nothing records that a "
                "body with authority adopted them, so every screen treats this "
                "as provisional. Record the adoption when it happens.")

    return (f"Framework adopted {s.adopted_on}",
            "The application is operating on your adopted framework. Every "
            "figure and citation on every screen traces back to these "
            "documents.")


def record_adoption(actor_name: str, actor_title: str = "",
                    adopted_on: str = "", note: str = "") -> dict[str, Any]:
    """Note that a body with authority adopted what is loaded.

    This records a claim about something that happened outside the software. It
    does not verify it, and it deliberately does not *perform* an adoption —
    the adoption happened in a meeting, and this is the application being told.
    """
    current = status()
    if current.state == "none":
        return {"ok": False,
                "error": "There is no framework loaded to adopt."}
    if not current.complete:
        missing = [ln["label"] for ln in current.layers
                   if ln["required"] and not ln["present"]]
        return {"ok": False,
                "error": "Still missing: " + ", ".join(missing) +
                         ". Adopting an incomplete framework would leave "
                         "screens citing documents that are not here."}

    when = (adopted_on or "").strip() or clock.today().isoformat()
    record = {
        "adopted_on": when,
        "adopted_by": (actor_name or "").strip()[:120],
        "adopted_by_title": (actor_title or "").strip()[:120],
        "note": (note or "").strip()[:400],
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": current.document_count,
        # Stated on the record itself, so a later reader cannot mistake this for
        # verification of the adoption.
        "verified": False,
        "record_note": "self-declared; the application was told, not shown",
    }
    path = adoption_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return {"ok": True, "adoption": record, "status": status().as_dict()}


#: What each part of the application needs from the framework. Shown in the
#: builder so the dependency is visible rather than asserted.
DEPENDENTS = [
    {"screen": "Registry", "needs": "The categories and risk bands that classify "
                                    "each system"},
    {"screen": "Lifecycle", "needs": "The gates, and the checklist for each one"},
    {"screen": "Budget", "needs": "The cost types and the approval thresholds"},
    {"screen": "Oversight", "needs": "The incident levels and the monitoring "
                                     "obligations"},
    {"screen": "Terminology", "needs": "The naming the framework fixes, which "
                                       "everything downstream inherits"},
    {"screen": "Configure", "needs": "The parameters the framework leaves for the "
                                     "agency to set"},
    {"screen": "Decisions", "needs": "Who decides when a decision is gated — a "
                                     "standing body, or one named person. The "
                                     "answer creates the room, or leaves it out"},
]


def summary() -> dict[str, Any]:
    """Everything the Framework Builder screen needs to draw itself."""
    s = status()
    return {**s.as_dict(), "usable": s.usable, "dependents": DEPENDENTS}
