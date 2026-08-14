"""Local web server for the SCDES AI Governance app.

Standard-library HTTP only — no framework, no network dependency, so the whole
application runs offline. Serves the single-page UI and a small JSON API.

Run:  python -m app.server        then open http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import mimetypes
import os
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from app import (agent, budget as budget_mod, config as config_mod, council,
                 mode as mode_mod, oversight, registry, retrieval, scoring,
                 vision, workflow)
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

#: v1 local roster. Production swaps this for SCDES SSO.
ROSTER = {
    "liz.operator": Actor("liz.operator", "Liz Alvarez", Role.OPERATOR,
                          bureau="Water"),
    "sean.ot": Actor("sean.ot", "Sean Whitaker", Role.OT),
    "council.cto": Actor("council.cto", "Dana Reyes (CTO)", Role.COUNCIL),
}
DEFAULT_USER = "liz.operator"


def actor_for(params: dict[str, list[str]], headers: Any) -> Actor:
    user = (params.get("user", [None])[0]
            or headers.get("X-SCDES-User")
            or DEFAULT_USER)
    return ROSTER.get(user, ROSTER[DEFAULT_USER])


# ------------------------------------------------------------------- handlers

def api_state(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import integrity, vocabulary
    provider = get_provider()
    log = JsonlAuditLog()
    ok, message = log.verify()
    try:
        report = integrity.audit()
        integrity_summary = {"counts": report.counts(),
                             "total": len(report.findings)}
    except Exception:                                   # never block the shell
        integrity_summary = {"counts": {}, "total": 0}
    return {
        "vocabulary": vocabulary.as_display_map(),
        "integrity": integrity_summary,
        "mode": mode_mod.current().value,
        "mode_label": mode_mod.current().label,
        "actor": {"id": actor.user_id, "name": actor.name,
                  "role": actor.role.value},
        "roster": [{"id": a.user_id, "name": a.name, "role": a.role.value}
                   for a in ROSTER.values()],
        "portfolio": registry.portfolio_summary(),
        "provider": {"name": provider.name, "offline": provider.offline,
                     "description": describe_provider(provider)},
        "audit": {"entries": len(log.entries()), "intact": ok, "message": message},
        "oversight": oversight.status(),
        "council_open": len(council.proposals()),
        "framework_version": "v1.0 · adopted 21 July 2026",
    }


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


def api_project(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    registry_id = params.get("id", [""])[0]
    project = registry.load(registry_id)
    if project is None:
        return {"error": f"unknown project {registry_id}"}
    risk = project.risk()
    return {"project": project.as_dict(), "risk": risk.as_dict(),
            "gate_map": workflow.gate_map_summary()}


def api_workflow(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    registry_id = params.get("id", [""])[0]
    gate = params.get("gate", [None])[0]
    step = workflow.render_step(registry_id, int(gate) if gate else None)
    return {"step": step.as_dict(), "gate_map": workflow.gate_map_summary()}


def api_workflow_save(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    return workflow.save_step(
        body["registry_id"], body.get("appendix", "G"),
        body.get("values", {}), actor,
        advance_to=body.get("advance_to"), note=body.get("note", ""),
    )


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
    return {
        "gates": workflow.gate_map_summary(),
        "tiers": council.TIER_RULES,
        "bands": {b: {"approval": scoring.BAND_APPROVAL[b],
                      "cadence": scoring.review_cadence(b),
                      "appendices": sorted(scoring.required_appendices(b))}
                  for b in scoring.BANDS},
        "procurement": config_mod.load("procurement"),
    }


def api_council(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    return {
        "is_member": actor.is_council,
        "members": council.members(),
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
    return {
        "status": oversight.status(),
        "register": oversight.monitoring_register(),
        "incidents": [i.as_dict() for i in oversight.incidents()],
        "levels": oversight.LEVEL_RULES,
    }


def api_incident(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    return oversight.report_incident(
        registry_id=body["registry_id"], level=int(body.get("level", 1)),
        summary=body.get("summary", ""), actor=actor, notes=body.get("notes", ""))


def api_search(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    query = params.get("q", [""])[0] or body.get("q", "")
    hits = retrieval.search(query, top_k=8)
    return {"query": query, "in_scope": retrieval.in_scope(hits),
            "hits": [{"citation": h.passage.citation, "snippet": h.snippet(300),
                      "score": h.score, "coverage": h.coverage,
                      "source": h.passage.source} for h in hits]}


#: Which state's corpus is actually loaded. Discovered, never assumed.
def _loaded_state_code() -> str | None:
    from app import profile
    juris = (profile.load().jurisdiction or "").strip()
    from app.states import STATE_NAMES
    for code, name in STATE_NAMES.items():
        if name.lower() == juris.lower():
            return code
    return None


def api_states(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import states
    loaded = _loaded_state_code()
    return states.registry(active_code=params.get("active", [None])[0],
                           loaded_code=loaded)


def api_profile(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import profile
    return {**profile.summary(), "can_edit": actor.is_ot}


def api_profile_rediscover(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import profile
    decision = guard(actor, Target.CONFIG, "rediscover_agency_profile")
    if not decision.allowed:
        return {"rediscovered": False, "reason": decision.reason}
    return {"rediscovered": True, **profile.rediscover().as_dict()}


def api_integrity(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
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


def api_audit(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    log = JsonlAuditLog()
    ok, message = log.verify()
    entries = [asdict(e) for e in log.entries()[-60:]]
    return {"intact": ok, "message": message, "entries": list(reversed(entries))}


def api_portals(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    from app import onboarding
    return onboarding.summary()


def api_register(actor: Actor, body: dict, params: dict) -> dict[str, Any]:
    """Onboarding registration. Deliberately unauthenticated.

    This runs before anyone has identified themselves, so it cannot pass through
    guard() — there is no actor yet. That makes it the one write in the
    application without an authorisation check, and it is kept safe by being
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
    ("GET", "/api/portals"): api_portals,
    ("POST", "/api/register"): api_register,
    ("GET", "/api/state"): api_state,
    ("POST", "/api/chat"): api_chat,
    ("GET", "/api/vision"): api_vision,
    ("GET", "/api/registry"): api_registry,
    ("GET", "/api/project"): api_project,
    ("GET", "/api/workflow"): api_workflow,
    ("POST", "/api/workflow/save"): api_workflow_save,
    ("GET", "/api/config"): api_config,
    ("POST", "/api/config/preview"): api_config_preview,
    ("POST", "/api/config/edit"): api_config_edit,
    ("GET", "/api/budget"): api_budget,
    ("POST", "/api/budget/scenario"): api_budget_scenario,
    ("GET", "/api/process"): api_process,
    ("GET", "/api/council"): api_council,
    ("POST", "/api/council/adopt"): api_council_adopt,
    ("POST", "/api/council/decide"): api_council_decide,
    ("GET", "/api/oversight"): api_oversight,
    ("POST", "/api/oversight/incident"): api_incident,
    ("GET", "/api/search"): api_search,
    ("GET", "/api/audit"): api_audit,
    ("GET", "/api/states"): api_states,
    ("GET", "/api/profile"): api_profile,
    ("POST", "/api/profile/rediscover"): api_profile_rediscover,
    ("GET", "/api/integrity"): api_integrity,
    ("GET", "/api/vocabulary"): api_vocabulary,
    ("POST", "/api/vocabulary/preview"): api_vocabulary_preview,
    ("POST", "/api/vocabulary/set"): api_vocabulary_set,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "SCDES-AI-Governance/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:      # quieter console
        if "/api/" in (args[0] if args else ""):
            return
        super().log_message(fmt, *args)

    # -- plumbing ---------------------------------------------------------

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
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
        self._send(200, target.read_bytes(), ctype or "application/octet-stream")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
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
            if length:
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    self._json({"error": "invalid JSON body"}, 400)
                    return

        actor = actor_for(params, self.headers)
        try:
            self._json(route(actor, body, params))
        except KeyError as exc:
            self._json({"error": f"not found: {exc}"}, 404)
        except Exception as exc:                                # noqa: BLE001
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

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


def serve(host: str = HOST, port: int = PORT) -> None:
    ensure_seeded()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  SCDES AI Governance — http://{host}:{port}")
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
