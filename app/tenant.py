"""Which agency this request belongs to, and where its files live.

Reported by the client, on the DEMO account:

    Expected:  See no reference documents in the DEMO account.
    Happened:  I see all the reference documents, from SCDES to the appendices.
               These are hidden and not relevant until they are created as a
               function of the contents of each agency's governance framework.

He was seeing more than he said. The application was single-tenant throughout:
one `corpus/` on disk holding SCDES's framework, manual and fourteen
appendices, and one `corpus/config/framework_versions.json` holding the answers
— so two registered agencies were reading and writing the same framework. The
documents were the visible half of it. The shared answer file was the half that
would have shown up as somebody else's words in your own framework.

Against the standing rule:

    "THE ENTIRE MODULAR PROCESS IS NOT TO EVER REFERENCE OR HAVE ACCESS TO
     OTHER AGENCIES."

Two decisions worth stating.

**The tenant is request-scoped, not passed down.** Every module that touches
this state — versions, decider, framework — reaches it through module-level
paths, and threading an agency argument through each of them and every caller
would be a large diff in which one missed call site is a silent leak. A
ContextVar set once per request in the dispatcher fails the other way: a module
that forgets to ask still gets the default, and the default is "no tenant",
which is the *unscoped* path. So the isolation is only as good as the coverage
here, and `tests/test_isolation.py` is what checks the coverage.

**The corpus owner keeps the original locations.** SCDES's documents and its
thirteen answered questions are real work that predates this split. Rather than
migrate them into `data/agencies/sc.des/`, the agency that owns the corpus goes
on reading exactly where it always did, and everyone else gets their own
directory. Nothing moves, so nothing is lost in the moving.
"""

from __future__ import annotations

import contextvars
from pathlib import Path

from app.audit import CORPUS

ROOT = Path(__file__).resolve().parent.parent

#: Where a non-owning agency's own governance state lives — one directory per
#: agency, named by the container code the registration created.
AGENCIES = ROOT / "data" / "agencies"

#: The agency this request is acting for. Empty means "not set", which resolves
#: to the original single-tenant paths: correct for tests, the CLI and the
#: ingest tools, all of which operate on the corpus directly.
_current: contextvars.ContextVar[str] = contextvars.ContextVar(
    "gaius_agency", default="")

#: A request that reached the server but could not be resolved to any agency —
#: signed out, mid-registration, or an address nobody's container knows.
#:
#: Distinct from "not set" on purpose, and the distinction is the whole safety
#: property. Not-set means a tool is running on this machine against the corpus
#: and may read it. This means a browser asked and we do not know who it is,
#: and the honest answer to "may I see the framework" is no. Collapsing the two
#: was the first version of this file, and it meant anyone not yet registered
#: was shown SCDES's papers — the reported bug, with a different cause.
ANONYMOUS = "~unresolved"


def set_current(code: str | None) -> contextvars.Token:
    """Bind this request to an agency. Returns a token for `reset`."""
    return _current.set((code or "").strip().lower())


def reset(token: contextvars.Token) -> None:
    _current.reset(token)


def current() -> str:
    return _current.get()


# ------------------------------------------------------------ who owns what

def corpus_owner() -> str:
    """The agency whose documents are in `corpus/`, or "" if none claims them.

    Deliberately reads the profile straight off disk rather than through
    anything tenant-aware: this is the question every other scoping decision is
    answered against, so it cannot itself depend on the answer.
    """
    from app import profile, states
    p = profile.load()
    short = (getattr(p, "short_name", "") or "").strip().lower()
    full = (getattr(p, "name", "") or "").strip().lower()
    juris = (getattr(p, "jurisdiction", "") or "").strip().lower()

    code = ""
    for state_code, name in states.STATE_NAMES.items():
        if name.lower() == juris:
            code = state_code
            break
    if not code:
        return ""

    for a in states.agencies_for(code):
        if short and a.get("abbrev", "").strip().lower() == short:
            return a["id"]
    for a in states.agencies_for(code):
        if full and a.get("name", "").strip().lower() == full:
            return a["id"]
    return ""


def owns_corpus() -> bool:
    """Whether the agency on this request is the one the corpus belongs to.

    No tenant set means a tool or a test is running against the corpus
    directly, which is allowed — the leak was never the CLI, it was one browser
    being shown another agency's files.
    """
    code = current()
    if not code:
        return True
    if code == ANONYMOUS:
        return False
    return code == corpus_owner()


# ------------------------------------------------------------------- paths

def scoped(default: Path) -> Path:
    """Where `default` lives for the agency on this request.

    The corpus owner, and anything running without a tenant, keeps the original
    path. Everyone else gets the same filename under their own directory.
    """
    code = current()
    if not code:
        return default
    if code != ANONYMOUS and code == corpus_owner():
        return default
    return AGENCIES / code / default.name


def data_dir() -> Path:
    """This agency's own directory, created on demand."""
    code = current()
    if not code or (code != ANONYMOUS and code == corpus_owner()):
        return CORPUS / "config"
    path = AGENCIES / code
    path.mkdir(parents=True, exist_ok=True)
    return path
