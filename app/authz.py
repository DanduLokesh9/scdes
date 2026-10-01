"""Roles, and the single chokepoint every governed write passes through.

There is exactly one function that decides whether a change is allowed —
`guard()`. Scattering `if role == ...` checks through the modules is how these
invariants leak, and the acceptance criteria are explicitly a critic trying to
break them, so the check lives in one place and everything routes through it.

Three roles, one governed record:
  operator        queries, runs projects, owner-scoped operational writes
  ot              the operational configuration and the Operations Manual
  council-member  Framework amendments, gate decisions, the record of decisions

Chat and scenarios use a read-only actor, so "exploring changes nothing" is a
property of the actor rather than a rule someone has to remember to honor.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Iterable

from app import mode as mode_mod
from app.audit import AuditLog, JsonlAuditLog


class Role(str, Enum):
    OPERATOR = "operator"
    OT = "ot"
    COUNCIL = "council-member"


# ---------------------------------------------------------------- targets

class Target(str, Enum):
    CONFIG = "config"                        # OT-owned operational parameters
    MANUAL = "manual"                        # OT-owned narrative procedure
    FRAMEWORK = "framework"                  # Council-only
    REGISTRY = "registry"                    # operational, owner-scoped
    APPENDIX_INSTANCE = "appendix_instance"  # a project's filled workbook
    VENDOR_QUOTE = "vendor_quote"            # operational
    COUNCIL_LOG = "council_log"              # Council-only
    MINUTES = "minutes"                      # Council-only
    RECORDINGS = "recordings"                # Council-only
    MODE = "mode"                            # Council-only


#: Targets whose parameters the Council adopted; in Operating Mode a change here
#: is a proposal, not a commit.
GUARDED_IN_OPERATING = {Target.CONFIG, Target.MANUAL}

#: Targets only the Council may ever write, in any mode.
COUNCIL_ONLY = {Target.FRAMEWORK, Target.COUNCIL_LOG, Target.MINUTES,
                Target.RECORDINGS, Target.MODE}

#: Operational targets — owner-scoped for operators, open to OT.
OPERATIONAL = {Target.REGISTRY, Target.APPENDIX_INSTANCE, Target.VENDOR_QUOTE}


@dataclass(frozen=True)
class Actor:
    user_id: str
    name: str
    role: Role
    readonly: bool = False
    bureau: str = ""
    #: Job title, as the person typed it at sign-in. Recorded alongside the name
    #: in the audit trail, because "who approved this" is a weaker answer than
    #: "who approved this, and in what capacity".
    title: str = ""
    #: The address this request *proved*, via the session token tenancy issued
    #: when a verification code was read out of a real mailbox — or "" when
    #: nothing was proved.
    #:
    #: Distinct from `name` and `title`, which are whatever the person typed,
    #: and from the capacity above, which they choose from a dropdown. Those are
    #: right for the audit trail and for deciding what to render. This is the
    #: only one of them fit to answer "may you read something that is not
    #: yours" — see app/admin.py.
    email: str = ""

    @property
    def is_council(self) -> bool:
        return self.role is Role.COUNCIL

    @property
    def is_ot(self) -> bool:
        return self.role is Role.OT


#: The actor the chat/scenario surfaces run as. It can read everything and
#: write nothing — a what-if never touches the record of authority.
CHAT_ACTOR = Actor(user_id="chat", name="Chat & scenarios",
                   role=Role.OPERATOR, readonly=True)


@dataclass
class Decision:
    allowed: bool
    reason: str
    requires_council: bool = False
    detail: dict[str, Any] = dc_field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.allowed


class Denied(PermissionError):
    def __init__(self, decision: Decision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


# ------------------------------------------------------------------ policy

#: Recording that a framework was adopted. One rule for both ways in — the
#: Framework screen's "Record the adoption" and the builder's "Adopt this
#: version" — decided before the target is looked at.
#:
#: It was two rules that could not both be passed. The Framework screen drew
#: the button only for the Council capacity; its endpoint checked
#: `Target.CONFIG`, which admits the Office of Technology in configuration
#: mode and the Council in no mode at all. The builder's endpoint was
#: Council-only, and since the launcher signs every registrant in as the
#: Office of Technology ("an agency's first user owns their container"), no
#: person who had signed in could ever reach it. Nothing on the platform
#: could be adopted, by anybody.
#:
#: What the act is decides who may do it. Recording an adoption is not the
#: adoption: the vote, the signature or the director's decision happened
#: outside this software, and the application records being told — the file
#: it writes says "self-declared; the application was told, not shown". So
#: the question is who may tell it. The Council capacity may. So may a
#: verified, active member of the organization whose framework it is — the
#: person who registered it and proved their address — because in this
#: product that person owns the container. Nobody else, and never an
#: unverified request. Every recording is attributed by name and title and
#: audited either way.
ADOPTION_ACTIONS = frozenset({"record_framework_adoption",
                              "adopt_framework_version"})


def _decide(actor: Actor, target: Target, action: str,
            owners: Iterable[str] | None, current_mode: mode_mod.Mode,
            verified_member: bool = False) -> Decision:

    if actor.readonly:
        return Decision(
            False,
            f"{actor.name} is read-only: querying and running scenarios changes "
            f"nothing on the record. Nothing was written to {target.value}.",
        )

    if action in ADOPTION_ACTIONS:
        if actor.is_council:
            return Decision(True, "Council authority to record an adoption.")
        if verified_member:
            return Decision(
                True,
                "Recorded by a verified member of this organization, who "
                "states that the framework was adopted. The application was "
                "told, not shown.")
        return Decision(
            False,
            "Recording an adoption needs a verified member of this "
            "organization, signed in with the address they registered.",
            requires_council=True,
        )

    if target in COUNCIL_ONLY:
        if actor.is_council:
            return Decision(True, f"Council authority over {target.value}.")
        return Decision(
            False,
            f"{target.value} is the Council's to change. {actor.role.value} "
            f"cannot {action} it.",
            requires_council=True,
        )

    if target in GUARDED_IN_OPERATING:
        if not actor.is_ot:
            return Decision(
                False,
                f"The operational configuration is OT's to set; "
                f"{actor.role.value} cannot {action} {target.value}.",
            )
        if current_mode is mode_mod.Mode.CONFIGURATION:
            return Decision(
                True,
                "Configuration Mode: OT tunes appendix parameters freely; "
                "the change is audited and explainable.",
            )
        return Decision(
            False,
            "Operating Mode: the Council adopted these values, so this change "
            "must be proposed and approved before it commits.",
            requires_council=True,
        )

    if target in OPERATIONAL:
        if actor.is_ot or actor.is_council:
            return Decision(True, f"{actor.role.value} may {action} {target.value}.")
        owner_list = [o for o in (owners or []) if o]
        if owner_list and actor.user_id not in owner_list:
            return Decision(
                False,
                f"Operators write only to projects they own. {actor.name} is not "
                f"an owner of this record (owners: {', '.join(owner_list)}).",
            )
        return Decision(True, "Owner-scoped operational write.")

    return Decision(False, f"Unknown target {target.value!r}; refused by default.")


# ------------------------------------------------------------------- guard

_default_log: AuditLog | None = None


def default_log() -> AuditLog:
    """The log a write lands in, resolved for the organization on this
    request each time — never cached across organizations. A log handed in
    by a test replaces it."""
    if _default_log is not None:
        return _default_log
    from app.audit import OrganisationLog
    return OrganisationLog()


def guard(actor: Actor, target: Target | str, action: str, *,
          owners: Iterable[str] | None = None,
          detail: dict[str, Any] | None = None,
          audit: AuditLog | None = None,
          raise_on_deny: bool = False,
          verified_member: bool = False) -> Decision:
    """The only place a governed write is authorized. Always audited.

    `verified_member` is worked out by the caller, which is the only layer
    that can see the proven session and the tenant together. It is recorded
    in the audit entry whatever it says, so the log shows on what basis an
    adoption was let through.
    """
    target = Target(target) if not isinstance(target, Target) else target
    current_mode = mode_mod.current()
    decision = _decide(actor, target, action, owners, current_mode,
                       verified_member=verified_member)
    if action in ADOPTION_ACTIONS:
        detail = {**(detail or {}), "verified_member": verified_member,
                  "actor_email": actor.email}

    log = audit if audit is not None else default_log()
    # The person's own name and title go into the entry alongside the capacity
    # they acted in. `actor` stays the stable id so existing entries and any
    # tooling that reads them keep working; "who did this" is now answerable
    # without a lookup table that only exists in this build.
    log.append(
        actor=actor.user_id, role=actor.role.value, action=action,
        target=target.value,
        outcome="allowed" if decision.allowed else "denied",
        mode=current_mode.value,
        detail={**(detail or {}),
                "actor_name": actor.name,
                "actor_title": actor.title,
                "reason": decision.reason,
                "requires_council": decision.requires_council},
    )

    if raise_on_deny and not decision.allowed:
        raise Denied(decision)
    return decision


def require(actor: Actor, target: Target | str, action: str, **kwargs: Any) -> Decision:
    """guard() that raises instead of returning a refusal."""
    return guard(actor, target, action, raise_on_deny=True, **kwargs)
