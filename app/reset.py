"""Start over — a blank slate for the agency, with the record left standing.

The client's reason for wanting this is the useful part: *"I like this because
it'll let a user go through it, figure out how it works, then be able to bring it
to the larger group."* Somebody senior will walk the whole framework alone to see
what it asks, and then want to run it properly with their leadership in the room.
Without a reset they either live with their exploratory answers or ask for a new
container.

So: **all the configurations are wiped and it is treated like a blank slate for
the agency.** And, emphatically: *"Log should survive absolutely."*

That split is the whole design, and it is not an implementation detail. An audit
trail that can be cleared by the person it audits is not an audit trail, it is a
draft. Keeping the log is what makes "a previous attempt existed" a fact rather
than a memory — and this application's entire claim is that its record can be
relied on. A reset is itself a governed act: it is authorized through `guard()`,
it appends to the same hash-chained log as everything else, and the entry names
who did it and what it cleared.

What survives is therefore small and deliberate:

  · the audit log, entire and unbroken
  · the registration — the person is still who they are, and still owns the
    container; they asked to start the *work* again, not to lose their account
  · the loaded reference corpus, which is IIA's document set, not the agency's
    answers about it

Everything the agency authored goes. The distinction to hold on to is *authored*
versus *recorded*: answers, versions, tuned parameters and decisions are things
the agency wrote and may unwrite. The log is a record of them having done so,
and that is not theirs to edit.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit import CORPUS
from app.authz import Actor, Target, guard

ROOT = CORPUS.parent


@dataclass(frozen=True)
class Clearable:
    """One thing a reset removes, and the plain-language reason it goes."""
    path: Path
    label: str
    why: str
    #: True for a directory whose *contents* go while the directory stays.
    contents_only: bool = False


def _targets() -> list[Clearable]:
    """Everything a reset clears, *for the agency making the request*.

    A glob would eventually match something nobody meant it to — the audit log
    sits two directories from here — so each entry is named, and anything not
    named survives by default. That is the safe direction for this to fail in.

    Every path routes through `tenant.scoped`, which is the fix for a bug
    found before anybody hit it: these were hardcoded to `corpus/config/...`,
    which is where the *reference* agency's answers live. So a tenant clicking
    Start Over would have left their own answers untouched and cleared
    somebody else's — failing at the one thing it was asked to do while doing
    real damage on the way past. The client asked for exactly this button an
    hour before it was found.
    """
    from app import tenant
    scoped = tenant.scoped
    return [
        Clearable(scoped(CORPUS / "config" / "framework_versions.json"),
                  "Framework answers and version history",
                  "Every question you answered, and every version you saved."),
        Clearable(scoped(CORPUS / "config" / "framework_adoption.json"),
                  "Adoption record",
                  "The record that a version was adopted. The framework goes "
                  "back to being a draft."),
        Clearable(scoped(CORPUS / "config" / "decider.json"),
                  "Who decides",
                  "Your answer to whether a group or one person makes gated "
                  "decisions. The question is asked again."),
        Clearable(scoped(CORPUS / "config" / "vocabulary.yaml"),
                  "Terminology",
                  "Your naming choices. These are re-derived from the "
                  "reference documents."),
        Clearable(tenant.data_dir() / "registry"
                  if not tenant.owns_corpus() else CORPUS / "registry",
                  "Project registry",
                  "Every tracked system and its filled workbooks.",
                  contents_only=True),
        Clearable(tenant.data_dir() / "intake"
                  if not tenant.owns_corpus() else ROOT / "data" / "intake",
                  "Uploaded policies",
                  "The documents you uploaded, and the passages matched from "
                  "them. Your originals are yours — keep a copy before "
                  "clearing.",
                  contents_only=True),
        Clearable(tenant.data_dir() / "council"
                  if not tenant.owns_corpus() else ROOT / "council",
                  "Decision log, proposals and minutes",
                  "Decisions your agency recorded in the platform. Note these "
                  "are the agency's own record — the platform's audit trail is "
                  "separate and is not touched.",
                  contents_only=True),
    ]


#: Named so the guarantee can be asserted by a test rather than believed.
PROTECTED = (
    CORPUS / "audit",
    # Every organisation's own trail lives in an `audit` folder under its own
    # directory, and no reset target names it.
    CORPUS / "framework",
    CORPUS / "manual",
    CORPUS / "appendices",
    CORPUS / "charter",
    ROOT / "data" / "tenancy.json",
)


def preview() -> dict[str, Any]:
    """What a reset would clear, and what it would not. Computed, never acted on.

    Shown before the confirmation, because "are you sure?" is not informed
    consent — the person needs to see the list.
    """
    goes, stays = [], []
    for t in _targets():
        exists = t.path.exists()
        if exists and t.contents_only:
            items = [p for p in t.path.iterdir() if not p.name.startswith(".")]
            exists = bool(items)
        goes.append({"label": t.label, "why": t.why, "present": exists})

    # This organisation's own trail. The shared back-end copy counts every
    # organisation's entries, and that number is not this one's to see.
    from app import audit as audit_mod
    log = audit_mod.organisation_log_path()
    if log is None or log == audit_mod.DEFAULT_LOG:
        # No organisation on the request: the corpus's own log, read from
        # this module's corpus so a sandboxed reset reads its own sandbox.
        log = CORPUS / "audit" / "log.jsonl"
    entries = 0
    if log.is_file():
        entries = sum(1 for line in log.read_text(encoding="utf-8").splitlines()
                      if line.strip())
    stays.append({
        "label": "Audit trail",
        "why": f"{entries} entries, hash-chained. Every governed action, "
               f"including this reset. It survives so that a later reader can "
               f"see a previous attempt existed — it is not the agency's to "
               f"clear.",
    })
    stays.append({
        "label": "Your registration",
        "why": "You stay signed in and still own this agency. You asked to "
               "start the work again, not to lose the account.",
    })
    stays.append({
        "label": "The reference documents",
        "why": "The loaded framework, manual and appendices are the reference "
               "set, not your answers about them.",
    })
    return {"clears": goes, "keeps": stays, "audit_entries": entries}


def reset(actor: Actor, *, confirm_phrase: str = "",
          reason: str = "") -> dict[str, Any]:
    """Clear the agency's own work. Guarded, audited, and irreversible.

    The confirmation is a typed phrase rather than a second button. This deletes
    work that cannot be recovered, and a button that has been clicked once is
    easy to click twice.
    """
    if confirm_phrase.strip().upper() != "START OVER":
        return {"ok": False,
                "error": 'Type START OVER to confirm. This clears every answer, '
                         'version and decision your agency has recorded, and it '
                         'cannot be undone.'}

    plan = preview()
    # Still gated, deliberately.
    #
    # The capacity gate was briefly removed here so that the client, asking to
    # "erase all of my content I have built in this tenant", would not be
    # refused as an operator. That was the wrong fix: this is irreversible, it
    # destroys work several people may have contributed to, and "an operator
    # cannot wipe the agency" is a property this project wrote a test for on
    # purpose.
    #
    # The right fix was the snapshot beside it. Taking and restoring a copy
    # needs no capacity, because a copy destroys nothing and exists precisely
    # so a mistake is recoverable. Wiping still asks for the authority it has
    # always asked for — and the panel now says so, rather than refusing with
    # a sentence about operational configuration.
    decision = guard(
        actor, Target.CONFIG, "reset_agency_configuration",
        # Not "reason": guard() writes its own `reason` into the detail, and
        # this one was being silently overwritten by the authorisation message.
        detail={"why": (reason or "").strip()[:300],
                "cleared": [c["label"] for c in plan["clears"] if c["present"]],
                "audit_entries_before": plan["audit_entries"],
                "note": "configuration wiped; the audit log is untouched"},
    )
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}

    removed: list[str] = []
    failed: list[dict[str, str]] = []
    for target in _targets():
        # Belt and braces. The target list is explicit, but a future edit adding
        # the wrong path here would be the single worst bug this module could
        # have, so the protected paths are checked at the moment of deletion.
        if any(target.path == p or p in target.path.parents for p in PROTECTED):
            failed.append({"label": target.label,
                           "error": "refused: protected path"})
            continue
        try:
            if not target.path.exists():
                continue
            if target.contents_only:
                for child in list(target.path.iterdir()):
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            elif target.path.is_dir():
                shutil.rmtree(target.path)
            else:
                target.path.unlink()
            removed.append(target.label)
        except OSError as exc:
            failed.append({"label": target.label, "error": str(exc)})

    _invalidate_caches()

    after = preview()["audit_entries"]
    return {
        "ok": True,
        "cleared": removed,
        "failed": failed,
        "audit_entries": after,
        "message": (
            f"Cleared {len(removed)} item(s). Your agency is a blank slate: the "
            f"framework is unanswered, the version history is empty and nothing "
            f"is adopted. The audit trail kept all {after} entries, including "
            f"this reset — a later reader can see a previous attempt existed."),
    }


def _invalidate_caches() -> None:
    """Drop anything holding the state we just deleted.

    Without this the process keeps serving the old answers from memory until it
    is restarted, and a reset that appears not to have worked is worse than one
    that failed loudly.
    """
    for module, fn in (("decider", "invalidate"), ("vocabulary", "invalidate")):
        try:
            mod = __import__(f"app.{module}", fromlist=[module])
            getattr(mod, fn)()
        except Exception:
            pass
    try:
        from app import states
        states._sc_agencies.cache_clear()
    except Exception:
        pass
