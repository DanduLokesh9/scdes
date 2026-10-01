"""Integrity 16E · the person with no login.

Anyone may write an incident down, including somebody with no login and no
role here. A reporting route that depends on holding a hat is a reporting
route people go around, and the person who has just watched a tool do
something wrong is the person most likely to need it.

**Reached by an unguessable link, never by an agency code.** A page at
`/report/<agency code>` would let anybody on the internet find out which
organizations use this application by trying codes — the one thing this
product promises never to tell one organization about another. So each
organization's page lives at a random token it can share, replace, or stop
sharing, and a token that does not match renders the same page as one that
never existed.

What the page contains is exactly 16E's list: the incident form and its
fields, the visibility line above the submit button, the 10.1 read-back
where AI incidents attach to an existing process, the organization's own
severity levels and definitions, its own reporting route, and the legal
line. No stat row, no findings, no list, no other record, no navigation, and
no lookup by reference.

Every read-back is third person. "You" on this page means the person
reporting, so a read-back that says "you said" to a member of the public is
a bug.

It works without JavaScript: a plain HTML form, posted and answered by the
server, with the confirmation as a real page.
"""

from __future__ import annotations

import html
import json
import secrets
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

from app import tenant
from app.audit import atomic_write

LINKS_FILE = tenant.AGENCIES.parent / "public_report_links.json"
_LOCK = threading.Lock()

PREFIX = "/report/"
#: 11.14 · a person with no login may attach up to two files of 5 MB each.
PUBLIC_FILES = 2
MAX_BODY = PUBLIC_FILES * 5 * 1024 * 1024 + 256 * 1024

#: Abuse limits. Generous for a person, useless for a script. Held in memory:
#: a restart forgets them, which costs nothing a person would notice.
PER_ADDRESS_PER_HOUR = 6
PER_LINK_PER_DAY = 200
_seen_address: dict[str, list[float]] = {}
_seen_link: dict[str, list[float]] = {}

TOO_MANY = ("Several reports have come from here in the last hour. Wait a "
            "while and try again — the limit is there so this page cannot be "
            "used to flood the register.")

NOT_FOUND_TITLE = "This page is not available"
NOT_FOUND_BODY = ("The link may have been replaced, or it may have been typed "
                  "wrongly. Ask the organization that gave it to you for the "
                  "current one.")


# ---------------------------------------------------------------- the links

def _read() -> dict[str, Any]:
    try:
        held = json.loads(LINKS_FILE.read_text(encoding="utf-8"))
        if isinstance(held, dict):
            held.setdefault("links", {})
            return held
    except (OSError, ValueError):
        pass
    return {"links": {}}


def _write(data: dict[str, Any]) -> None:
    atomic_write(LINKS_FILE, json.dumps(data, indent=2))


def link_for(agency: str) -> str:
    """The organization's current token, or empty where it has none."""
    for token, row in _read()["links"].items():
        if row.get("agency") == agency and not row.get("retired"):
            return token
    return ""


def make_link(agency: str, actor: Any) -> str:
    """Issue a token, retiring any earlier one. Replacing the link is how an
    organization stops a page it no longer wants reachable."""
    if not agency or agency == tenant.ANONYMOUS:
        return ""
    with _LOCK:
        data = _read()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in data["links"].values():
            if row.get("agency") == agency and not row.get("retired"):
                row["retired"] = now
        token = secrets.token_urlsafe(18)
        data["links"][token] = {"agency": agency, "created_at": now,
                                "created_by": getattr(actor, "user_id", "")}
        _write(data)
    _log("event.public_report_link_issued", actor, {"agency": agency})
    return token


def stop_link(agency: str, actor: Any) -> bool:
    with _LOCK:
        data = _read()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stopped = False
        for row in data["links"].values():
            if row.get("agency") == agency and not row.get("retired"):
                row["retired"] = now
                stopped = True
        _write(data)
    if stopped:
        _log("event.public_report_link_stopped", actor, {"agency": agency})
    return stopped


def agency_for(token: str) -> str:
    """The agency a live token belongs to, or empty. Constant-time on the
    comparison, so a timing difference does not narrow a guess."""
    token = str(token or "")
    found = ""
    for held, row in _read()["links"].items():
        if secrets.compare_digest(held.encode(), token.encode()) \
                and not row.get("retired"):
            found = row.get("agency", "")
    if not found:
        return ""
    try:
        from app import tenancy
        if not tenancy.agency_state(found).get("active"):
            return ""
    except Exception:                                         # noqa: BLE001
        return ""
    return found


def _log(action: str, actor: Any, detail: dict[str, Any]) -> None:
    try:
        from app.authz import default_log
        default_log().append(
            actor=getattr(actor, "user_id", "") or "public",
            role=getattr(getattr(actor, "role", None), "value", "") or "public",
            action=action, target="Integrity", outcome="allowed",
            detail=detail)
    except Exception:                                         # noqa: BLE001
        pass


def _allowed(address: str, token: str) -> bool:
    now = time.time()
    hour = [t for t in _seen_address.get(address, []) if now - t < 3600]
    day = [t for t in _seen_link.get(token, []) if now - t < 86400]
    _seen_address[address] = hour
    _seen_link[token] = day
    if address and len(hour) >= PER_ADDRESS_PER_HOUR:
        return False
    return len(day) < PER_LINK_PER_DAY


def _note(address: str, token: str) -> None:
    now = time.time()
    if address:
        _seen_address.setdefault(address, []).append(now)
    _seen_link.setdefault(token, []).append(now)


# ---------------------------------------------------------------- the page

def _organisation(agency: str) -> str:
    try:
        from app import tenancy
        names = tenancy._agency_names(agency)
        return str(names.get("agency_label") or "") or "This organization"
    except Exception:                                         # noqa: BLE001
        return "This organization"


def _inputs(agency: str) -> dict[str, Any]:
    from app import checks
    held = tenant.set_current(agency)
    try:
        from app import versions
        answers = dict(versions.state().get("working") or {})
    except Exception:                                         # noqa: BLE001
        answers = {}
    finally:
        tenant.reset(held)
    return checks.framework_inputs(answers)


def _e(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


_STYLE = """
:root{color-scheme:light}
body{margin:0;font:17px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
 color:#1b1b1b;background:#f7f5f0}
main{max-width:44rem;margin:0 auto;padding:1.5rem 1.25rem 3rem}
h1{font-size:1.7rem;line-height:1.25;margin:.5rem 0 1rem}
h2{font-size:1.2rem;margin:2rem 0 .5rem}
p{margin:.5rem 0}
.lead{font-size:1.05rem}
.note{background:#fff;border:1px solid #6b6b6b;border-radius:6px;
 padding:.75rem 1rem;margin:1rem 0}
fieldset{border:1px solid #6b6b6b;border-radius:6px;margin:1.25rem 0;
 padding:.75rem 1rem 1rem;background:#fff}
legend{font-weight:600;padding:0 .35rem}
label{display:block;font-weight:600;margin:1rem 0 .25rem}
.opt{display:flex;gap:.6rem;align-items:flex-start;font-weight:400;
 margin:.5rem 0;min-height:24px}
.opt input{width:1.2rem;height:1.2rem;margin-top:.2rem;flex:none}
.help{color:#3d3d3d;font-size:.95rem;margin:.15rem 0 .4rem}
input[type=text],input[type=date],textarea{box-sizing:border-box;width:100%;
 font:inherit;padding:.55rem .65rem;border:1px solid #595959;border-radius:5px;
 background:#fff;color:#1b1b1b;min-height:44px}
textarea{min-height:7rem}
:focus-visible{outline:3px solid #1d4ed8;outline-offset:2px}
button{font:inherit;font-weight:600;padding:.7rem 1.4rem;border-radius:6px;
 border:2px solid #14365c;background:#14365c;color:#fff;min-height:44px;
 cursor:pointer}
.error{border:2px solid #9b1c1c;background:#fff;color:#7a1414;padding:.75rem 1rem;
 border-radius:6px}
.ref{font:600 1.4rem/1.3 ui-monospace,Consolas,monospace;
 user-select:all;background:#fff;border:1px solid #595959;padding:.4rem .7rem;
 display:inline-block;border-radius:5px}
.small{font-size:.92rem;color:#3d3d3d}
"""


def _page(title: str, body: str) -> str:
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,"
            "initial-scale=1\"><meta name=\"robots\" content=\"noindex,"
            "nofollow\"><title>" + _e(title) + "</title><style>" + _STYLE +
            "</style></head><body><main id=\"main\">" + body +
            "</main></body></html>")


def not_found() -> str:
    return _page(NOT_FOUND_TITLE, f"<h1>{_e(NOT_FOUND_TITLE)}</h1>"
                                  f"<p>{_e(NOT_FOUND_BODY)}</p>")


def _radio(name: str, options: list[tuple[str, str]], chosen: str,
           legend: str, help_text: str = "") -> str:
    hid = f"{name}-help"
    described = f' aria-describedby="{hid}"' if help_text else ""
    out = [f"<fieldset{described}><legend>{_e(legend)}</legend>"]
    if help_text:
        out.append(f"<p class=\"help\" id=\"{hid}\">{_e(help_text)}</p>")
    for i, (value, label) in enumerate(options):
        rid = f"{name}-{i}"
        mark = " checked" if value == chosen else ""
        out.append(f"<div class=\"opt\"><input type=\"radio\" id=\"{rid}\" "
                   f"name=\"{name}\" value=\"{_e(value)}\"{mark}>"
                   f"<label for=\"{rid}\" style=\"margin:0;font-weight:400\">"
                   f"{label}</label></div>")
    out.append("</fieldset>")
    return "".join(out)


def form(token: str, *, error: str = "", values: dict[str, str] | None = None
         ) -> str:
    """The public incident form, in the third person."""
    from app import checks
    agency = agency_for(token)
    if not agency:
        return not_found()
    org = _organisation(agency)
    inputs = _inputs(agency)
    tried, affected = checks.example_for(inputs.get("organisation_type", ""))
    v = values or {}

    parts = [f"<h1>Report a problem with an AI tool at {_e(org)}</h1>",
             "<p class=\"lead\">Anyone can write this down, including somebody "
             "with no login and no role here. Only one thing is required: "
             "either which tool, or a sentence about what happened.</p>"]
    if inputs.get("attached_to_existing"):
        parts.append(f"<p class=\"note\">{_e(org)} recorded that AI incidents "
                     f"go through its existing incident process. This does "
                     f"not replace that; it keeps the tool's whole history in "
                     f"one place.</p>")
    if error:
        parts.append(f"<div class=\"error\" role=\"alert\" id=\"form-error\">"
                     f"<p style=\"margin:0\">{_e(error)}</p></div>")

    parts.append(f"<form method=\"post\" action=\"{PREFIX}{_e(token)}\" "
                 f"enctype=\"multipart/form-data\" novalidate>")
    # 11.1 — free text here. The organisation's own list of tools is an
    # internal record, and nobody has been asked whether to publish it.
    parts.append("<label for=\"tool\">What were you using?</label>"
                 "<p class=\"help\" id=\"tool-help\">The name of the tool, the "
                 "website, or the service, if you know it. If you do not "
                 "know, describe it.</p>"
                 f"<input type=\"text\" id=\"tool\" name=\"tool\" "
                 f"aria-describedby=\"tool-help\" maxlength=\"300\" "
                 f"value=\"{_e(v.get('tool'))}\">")
    parts.append("<label for=\"what_happened\">What happened?</label>"
                 "<p class=\"help\" id=\"wh-help\">In your own words. "
                 "&ldquo;It gave the wrong answer and I do not know why&rdquo; "
                 "is a complete report.</p>"
                 "<textarea id=\"what_happened\" name=\"what_happened\" "
                 "aria-describedby=\"wh-help\" maxlength=\"6000\">"
                 f"{_e(v.get('what_happened'))}</textarea>")
    parts.append("<label for=\"at\">When did it happen?</label>"
                 "<p class=\"help\" id=\"at-help\">Leave it empty if you are "
                 "not sure.</p>"
                 f"<input type=\"date\" id=\"at\" name=\"at\" "
                 f"aria-describedby=\"at-help\" value=\"{_e(v.get('at'))}\">")
    parts.append("<label for=\"first_noticed\">When did you first notice?"
                 "</label><p class=\"help\" id=\"fn-help\">These are often "
                 "different, and the gap between them is what tells somebody "
                 "how far back to look.</p>"
                 f"<input type=\"date\" id=\"first_noticed\" "
                 f"name=\"first_noticed\" aria-describedby=\"fn-help\" "
                 f"value=\"{_e(v.get('first_noticed'))}\">")
    parts.append("<label for=\"affected\">Who or what was affected?</label>"
                 f"<p class=\"help\" id=\"af-help\">In your own words. For "
                 f"example: {_e(affected)} If you only know part of it, write "
                 f"the part you know.</p>"
                 "<textarea id=\"affected\" name=\"affected\" "
                 "aria-describedby=\"af-help\" maxlength=\"4000\">"
                 f"{_e(v.get('affected'))}</textarea>")
    parts.append(_radio(
        "touched_a_person",
        [(o, _e(o)) for o in checks.TOUCHED_A_PERSON],
        v.get("touched_a_person", ""),
        "Did it affect a decision about a person?"))

    severities = inputs.get("severities") or []
    if severities:
        parts.append(_radio(
            "severity",
            [(s["label"], f"<b>{_e(s['label'])}</b> — {_e(s['meaning'])}")
             for s in severities] + [("", "Not sure")],
            v.get("severity", ""),
            "How serious is it?",
            f"{org}'s own levels, in its own words."))

    route = inputs.get("route") or ""
    stop_line = (f"If it needs stopping now, {org} recorded that it goes to "
                 f"{route}." if route else
                 f"{org} has not written down where a problem goes, and that "
                 f"is recorded as a gap.")
    parts.append(_radio(
        "stopped",
        [(checks.STOPPED_YES, "Yes, it has been stopped"),
         (checks.STOPPED_NO, "No, it is still running"),
         (checks.STOPPED_UNSURE, "Not sure")],
        v.get("stopped", ""), "Has the tool been stopped?", stop_line))

    # 11.9 — each party the organisation listed, in the third person.
    told = inputs.get("must_be_told") or []
    if told:
        rows = [f"<fieldset aria-describedby=\"told-help\"><legend>Who has been "
                f"told?</legend><p class=\"help\" id=\"told-help\">{_e(org)} "
                f"said each of these must be told. Tick any you know have "
                f"been, and when.</p>"]
        for i, party in enumerate(told):
            ticked = " checked" if party in (v.get("told") or []) else ""
            rows.append(
                f"<div class=\"opt\"><input type=\"checkbox\" id=\"told-{i}\" "
                f"name=\"told\" value=\"{_e(party)}\"{ticked}><label "
                f"for=\"told-{i}\" style=\"margin:0;font-weight:400\">"
                f"{_e(party)}</label></div><label for=\"told-on-{i}\" "
                f"class=\"small\" style=\"font-weight:400;margin:.1rem 0 .6rem "
                f"2rem\">When {_e(party[:1].lower() + party[1:])} was told"
                f"<input type=\"date\" id=\"told-on-{i}\" name=\"told_on_{i}\" "
                f"value=\"{_e((v.get('told_on') or {}).get(str(i)))}\"></label>")
        rows.append("</fieldset>")
        parts.append("".join(rows))

    # 11.10 — shown where their answer at 10.6 is anything but No, with
    # their scope line only on Yes, and in the third person.
    look = inputs.get("lookback_answer")
    if look != checks.LOOKBACK_NO:
        scope = inputs.get("lookback_scope") or ""
        help_line = {
            checks.LOOKBACK_YES: f"{org} said it goes back {scope} after a problem."
            if scope else f"{org} said it goes back over earlier work after a problem.",
            checks.LOOKBACK_CASE_BY_CASE: f"{org} said it decides this case by case.",
        }.get(look, f"{org} has not decided whether it goes back over earlier work.")
        options = [(checks.LOOKBACK_NOT_YET, "Not yet"),
                   (checks.LOOKBACK_BACK_TO, "Yes, back to a date — say which below")]
        if look == checks.LOOKBACK_YES and scope:
            # The stored answer says "you said"; this page never does, not
            # even in its markup. Mapped back on submit.
            options.append(("their_scope", f"Yes, {_e(scope)}"))
        options += [(checks.LOOKBACK_NOT_NEEDED, "Not needed for this one"),
                    (checks.LOOKBACK_UNSURE_HERE, "Not sure")]
        parts.append(_radio("lookback", options, v.get("lookback", ""),
                            "Has anyone gone back over earlier work?", help_line))
        parts.append("<label for=\"lookback_back_to\">Back to which date "
                     "<span class=\"small\">(where it went back to a date)"
                     "</span></label><input type=\"date\" id=\"lookback_back_to\" "
                     f"name=\"lookback_back_to\" value=\"{_e(v.get('lookback_back_to'))}\">")

    # 11.11 – 11.12a.
    parts.append("<label for=\"cause\">What caused it? <span class=\"small\">"
                 "(optional)</span></label><p class=\"help\" id=\"cause-help\">"
                 "If nobody knows yet, write that.</p><textarea id=\"cause\" "
                 "name=\"cause\" aria-describedby=\"cause-help\" "
                 f"maxlength=\"4000\">{_e(v.get('cause'))}</textarea>")
    parts.append("<label for=\"what_was_done\">What was done about it? "
                 "<span class=\"small\">(optional)</span></label><textarea "
                 "id=\"what_was_done\" name=\"what_was_done\" maxlength=\"4000\">"
                 f"{_e(v.get('what_was_done'))}</textarea>")
    # The organisation's own answer at 10.8 names an internal role, and
    # internal roles are never shown on this page — so this is asked plainly.
    parts.append("<label for=\"written_up_where\">If you are writing this up "
                 "somewhere else too, where does it live? <span class=\"small\">"
                 "(optional)</span></label><input type=\"text\" "
                 "id=\"written_up_where\" name=\"written_up_where\" "
                 f"maxlength=\"300\" value=\"{_e(v.get('written_up_where'))}\">")

    # 11.14 — stored, never read.
    parts.append("<label for=\"files\">Anything attached? <span class=\"small\">"
                 "(optional)</span></label><p class=\"help\" id=\"files-help\">"
                 "A screenshot, a letter, a document. Nothing here is read by "
                 "the application; it is stored so the next person can see what "
                 f"you saw. Up to {PUBLIC_FILES} files, 5 MB each. The kind, "
                 "never the credential: nothing you attach should be a password "
                 "or a secret.</p><input type=\"file\" id=\"files\" name=\"files\" "
                 "multiple aria-describedby=\"files-help\">")

    parts.append("<label for=\"name\">Your name <span class=\"small\">"
                 "(optional)</span></label>"
                 f"<input type=\"text\" id=\"name\" name=\"name\" "
                 f"maxlength=\"120\" autocomplete=\"name\" "
                 f"value=\"{_e(v.get('name'))}\">")
    parts.append(f"<p class=\"note\">This record is visible to everyone in "
                 f"{_e(org)} and, in most places, to anyone who asks for it. "
                 f"Leave your name off if you would rather; the report still "
                 f"counts.</p>")
    parts.append(f"<p class=\"small\">{_e(checks.legal_line(inputs, organisation=org))}</p>")
    parts.append("<button type=\"submit\">Write it down</button></form>")
    return _page(f"Report a problem — {org}", "".join(parts))


def done(token: str, ref: str) -> str:
    agency = agency_for(token)
    org = _organisation(agency) if agency else "This organization"
    route = _inputs(agency).get("route", "") if agency else ""
    last = (f"{org} recorded that a problem here goes to {route}."
            if route else
            f"{org} has not written down where a problem goes, and that is "
            f"recorded as a gap.")
    body = ("<section aria-labelledby=\"done-h\"><h1 id=\"done-h\" "
            "tabindex=\"-1\">Written down. This is on the record now.</h1>"
            f"<p>Your reference is</p><p><span class=\"ref\">{_e(ref)}</span>"
            "</p><p>Write it down or print this page; there is no account "
            "here to keep it in, so this is the only copy you will get.</p>"
            f"<p>Nobody is emailed when a report arrives, and this page does "
            f"not promise you a reply. {_e(last)}</p></section>")
    return _page("Written down", body)


def _parse(raw: bytes, content_type: str
           ) -> tuple[dict[str, list[str]], list[tuple[str, bytes, str]]]:
    """The posted form, as fields and files. A plain form and a multipart
    one both arrive here; nothing in a file is looked at beyond its size."""
    if not content_type.lower().startswith("multipart/form-data"):
        return parse_qs(raw.decode("utf-8", "replace"),
                        keep_blank_values=True), []
    from email import policy
    from email.parser import BytesParser
    message = BytesParser(policy=policy.HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1", "replace") +
        b"\r\n\r\n" + raw)
    fields: dict[str, list[str]] = {}
    files: list[tuple[str, bytes, str]] = []
    if not message.is_multipart():
        return fields, files
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition") or ""
        filename = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if filename is not None:
            if data:
                files.append((filename, data, part.get_content_type()))
        else:
            fields.setdefault(str(name), []).append(
                data.decode(part.get_content_charset() or "utf-8", "replace"))
    return fields, files


def submit(token: str, raw: bytes, address: str, content_type: str = ""
           ) -> tuple[int, str]:
    """Handle a posted report. Returns the status and the page to show."""
    from app import attachments, checks
    agency = agency_for(token)
    if not agency:
        return 404, not_found()
    parsed, files = _parse(raw, content_type)
    fields = {k: (vals[0] if vals else "") for k, vals in parsed.items()}
    values: dict[str, Any] = {k: str(fields.get(k, ""))[:6000] for k in (
        "tool", "what_happened", "at", "first_noticed", "affected",
        "touched_a_person", "severity", "stopped", "name", "lookback",
        "lookback_back_to", "cause", "what_was_done", "written_up_where")}
    values["told"] = [str(t)[:200] for t in parsed.get("told", [])][:20]
    values["told_on"] = {k[len("told_on_"):]: str(v[0] if v else "")[:10]
                         for k, v in parsed.items() if k.startswith("told_on_")}

    if not _allowed(address, token):
        return 429, form(token, error=TOO_MANY, values=values)
    lookback = {"their_scope": checks.LOOKBACK_THEIR_SCOPE,
                checks.LOOKBACK_THEIR_SCOPE: ""}.get(values["lookback"],
                                                     values["lookback"])
    if len(files) > PUBLIC_FILES:
        return 400, form(token, error=f"{PUBLIC_FILES} files is the most this "
                                      f"page takes.", values=values)
    # Checked before anything is stored, so a refused file never leaves an
    # earlier one kept with no record pointing at it.
    if any(len(data) > attachments.MAX_BYTES for _, data, _ in files):
        return 400, form(token, error=attachments.TOO_LARGE, values=values)

    inputs = _inputs(agency)
    severities = {s["label"] for s in inputs.get("severities") or []}
    parties = inputs.get("must_be_told") or []
    told = {}
    for i, party in enumerate(parties):
        if party in values["told"]:
            on = values["told_on"].get(str(i), "")
            told[party] = on if _is_date(on) else ""
    reporter = SimpleNamespace(user_id="public",
                               name=values["name"].strip()[:120], role=None)
    held = tenant.set_current(agency)
    try:
        stored = []
        for filename, data, ctype in files:
            kept = attachments.store(data, filename, by="public",
                                     content_type=ctype)
            if not kept.get("ok"):
                return 400, form(token, error=kept["error"], values=values)
            stored.append(kept["id"])
        out = checks.report_incident(
            actor=reporter,
            tool=values["tool"].strip()[:300],
            what_happened=values["what_happened"].strip(),
            at=values["at"][:10] if _is_date(values["at"]) else "",
            first_noticed=values["first_noticed"][:10]
            if _is_date(values["first_noticed"]) else "",
            affected=values["affected"].strip(),
            touched_a_person=values["touched_a_person"]
            if values["touched_a_person"] in checks.TOUCHED_A_PERSON else "",
            severity=values["severity"] if values["severity"] in severities
            else "",
            stopped=values["stopped"] if values["stopped"] in (
                checks.STOPPED_YES, checks.STOPPED_NO, checks.STOPPED_UNSURE)
            else "",
            told=told,
            lookback=lookback if lookback in checks.LOOKBACK_ANSWERS and
            inputs.get("lookback_answer") != checks.LOOKBACK_NO else "",
            lookback_back_to=values["lookback_back_to"][:10]
            if _is_date(values["lookback_back_to"]) else "",
            cause=values["cause"].strip()[:4000],
            what_was_done=values["what_was_done"].strip()[:4000],
            written_up_where=values["written_up_where"].strip()[:300],
            attachments=stored,
            signed_in=False)
    finally:
        tenant.reset(held)
    if not out.get("ok"):
        return 400, form(token, error=out.get("error", ""), values=values)
    _note(address, token)
    return 200, done(token, out["incident"]["ref"])


def _is_date(text: str) -> bool:
    try:
        datetime.strptime(str(text or "")[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False
