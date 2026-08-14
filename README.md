# SCDES AI Governance — reference build

Local-first application that operationalises the SCDES AI Governance Framework.
It reads the agency's adopted documents, answers questions about them with exact
citations, carries projects through the stage-gates while filling the real
appendix workbooks, and lets the Office of Technology tune every appendix
parameter while showing the consequences — until the Council closes the gate.

**Nothing in this repository invents governance.** The rules, weights,
thresholds and gate checklists are read out of the adopted instruments in
`corpus/`. Where a value appears in code it is a default read from the workbook,
not a policy decision.

---

## Status — all milestones complete

| Milestone | State | What it proves |
|---|---|---|
| **M1 · The spine** | **done** | One parser reads all fourteen appendices; documents chunk to exact citations; no governed change happens outside the guard |
| **M2 · Cited & explainable** | **done** | BM25 retrieval with exact citations, calibrated out-of-scope refusal, `config.explain()` on every control |
| **M3 · The money demo** | **done** | Risk sliders reclassify the live pipeline with a named explanation before saving |
| **M4 · Kinetic** | **done** | Gate walkthrough writes the real `.xlsx`, advances the stage, routes Council-tier decisions |
| **M5 · Budget, vision, oversight** | **done** | Delta Bravo scenario, capability-graph roadmap, incidents L1–3 |

**Run it:**

```
python -m app.server        # then open http://127.0.0.1:8765
python -m pytest tests -q   # 69 tests
python demo_m1.py           # the spine, in the terminal
```

## What M1 established

**All fourteen appendices parse — 1,106 editable fields, zero unclassified rows.**
The workbooks reduce to four repeating block shapes, so one parser serves the
Configure room, the Workflow Helper, writeback, and citation precision:

| Block | Where | Shape |
|---|---|---|
| `field_block` | D, E, G, K, L | `Label: | value | [hint]` |
| `checklist` | H | `# | Requirement | Status | Notes / Evidence` |
| `param_table` | B, D, J | any table carrying a Weight and/or Score column |
| `record_table` | A, C, I, M | header row + data rows |

Every field carries the **cell it writes back to**, which is what makes
writeback exact rather than positional. Control types are not guessed — the
templates declare them. Appendix G's hint column literally reads
`[Select: Water / Land and Waste / Air / Coastal Zone Management / ...]`, and
that becomes the dropdown.

**Citations are exact by construction.** The Framework and Operations Manual are
cleanly styled with numbered headings, so a chunk boundary *is* a citation
boundary — 218 chunks, 161 of them numbered. An answer cites
`SCDES AI Operations Manual §22.4 (Level 2 Procedure)`, not a page guess.

**One chokepoint, and it is tamper-evident.** Every governed write passes
`authz.guard()`, which checks role *and* mode and records the outcome — grants
and refusals alike. The audit log is hash-chained: editing or removing a past
entry breaks the chain and `verify()` names the entry.

## Roles and the two modes

Three roles, one governed record:

- **operator** — queries, runs scenarios, walks projects through gates; writes only to projects they own
- **ot** — the operational configuration and the Operations Manual
- **council-member** — Framework amendments, gate decisions, the record of decisions

Chat and scenarios run as a **read-only actor**, so "exploring changes nothing"
is a property of the actor rather than a rule someone has to remember.

**Configuration Mode** is the one-time window in which OT tunes every appendix
parameter freely — the Council adopted the appendices as *templates*, sight
unseen, and this is where their real values get set. OT then proposes the tuned
set, the Council adopts it, and **Operating Mode** begins: from that point every
governed change routes through the Council. Re-opening bulk tuning is itself a
Council act, recorded as such — it is not an undo.

## Layout

```
corpus/            the governed record — the agency's adopted documents
  framework/ manual/ appendices/ charter/     ingested, never modified
  config/          OT-owned parameters (+ mode.json)
  registry/        per-project filled appendix instances
  audit/log.jsonl  hash-chained, append-only
council/           gated to members; decision log, minutes, recordings
app/
  ingest_xlsx.py   the appendix parser (four block types)
  ingest_docx.py   heading-boundary sectioniser for citations
  audit.py         hash-chained log behind an AuditLog interface
  authz.py         roles + guard() — the only place a write is authorised
  mode.py          Configuration → Operating, and the Council act that closes it
tests/
```

The appendix templates in `corpus/appendices/` are **immutable** — they are the
adopted instruments. Filling Appendix G for a project copies the template to
`corpus/registry/<REG-ID>/` and writes there, so every project gets its own
auditable filled workbook and the masters are never touched.

## Setup

```
python -m pip install openpyxl python-docx pyyaml pytest
```

Python 3.11+ (developed against 3.14). No network access is required for
ingest, parsing, retrieval, scoring, or the audit trail.

## Open decisions (defaults chosen, not blocking)

- **Audit format.** git is not installed on the reference machine, so the record
  of authority is a hash-chained JSONL log behind an `AuditLog` interface.
  `GitAuditLog` is scaffolded; enabling it changes the storage, not the interface.
- **Language provider.** Retrieval and citation are always local — only retrieved
  snippets and the question ever reach a model. The Anthropic provider is the
  default for phrasing; a `LocalProvider` gives a fully offline path with no API
  key. (M2.)
- **Roles.** Local roster in v1; SCDES SSO in production.
- **Functional alert red `#b3261e`** sits outside the official SCDES palette and
  is used only for error / over-budget / High-risk / Level-3 states. Flagged for
  Comms, as the spec requires.
- **Retrieval is lexical (BM25), not semantic.** This corpus is dense regulatory
  prose searched with its own vocabulary ("Gate 3", "Tier B", "Federal Program
  Nexus"), where lexical precision beats embeddings and the chunk boundary *is*
  the citation. (M2.)

## Theming across fifty agencies

An agency's brand here is **however many colours it actually has** — two, three,
eight, twenty — and that list is never padded. Interface roles (`app/theme.py`)
are filled by *reusing* those colours, so a two-colour agency is themed in
exactly its two. Every role resolves to a colour the agency owns; a test asserts
it for all 51 entries.

This replaced a fixed eight-slot palette that synthesised whatever was missing,
and the reason is worth recording because the bug looked fine one state at a
time. The derived filler followed the same recipe for every agency, so a state
with four real colours came out four-parts itself and four-parts house style —
the filler dominated and the states converged toward one look, defeating the
point of theming per agency.

Two things are deliberately not taken from the brand:

- **Status colours are universal.** Low / Moderate / High risk are identical in
  all fifty states. A record where "High risk" renders maroon in one state and
  olive in the next invites misreading, and theming them was what forced a green
  to be invented for every agency that hasn't got one.
- **Foregrounds are chosen, not invented.** Text over a brand colour is black or
  white, whichever is legible; the brand colour is never altered to make text
  fit. Where a fill must carry text, the `action` role is picked from the
  agency's own colours *by legibility* — a mid-tone olive that reaches only
  4.3:1 is passed over for one that clears AA. The single exception is
  `--accent-text`, a brand colour walked down its own hue until it clears AA as
  small text on white.

Colours come from `tools/scrape_brands.py`, which reads each agency's live
stylesheets. Two filters keep the result honest, both aimed at the same failure:

- a blocklist of framework defaults (Bootstrap 3/4/5, the WordPress Gutenberg
  palette, Materialize, Tailwind), because harvesting them yields Bootstrap's
  brand rather than the agency's; and
- a **cross-agency** filter — any hex appearing on three or more different
  agencies' sites is a CMS default nobody chose, and is dropped. Across 32
  scraped sites, 335 colours belonged to exactly one agency and only a dozen
  appeared on three or more, all traceable to a framework. This catches whatever
  ships next without the blocklist having to be maintained forever.

Provenance is graded in four levels and shown on the launcher, because the
standards of evidence are not equivalent: `brand` (a published guide — SCDES
only), `scraped` (colours the agency demonstrably uses, but has not ratified),
`documented` (Pantone chips or an inherited statewide standard), and `generated`
(no colours found — a neutral slate that says so rather than inventing an
identity). **No agency has confirmed any of the scraped values.**

19 of 51 sites refuse the scraper — Akamai/Cloudflare 403 on California, New
York, Michigan, Massachusetts, South Carolina, Virginia and others, plus a DNS
failure on Wisconsin. Those states show the neutral placeholder. An agency
supplies its real palette by dropping a `colors:` list into
`corpus/config/brand.yaml`.

## A finding worth your attention

**Appendix A's "typical risk classification" is not reproducible under Appendix
B's matrix, and the cause is structural.**

Seeding the pipeline derives the six factor ratings from Appendix A's own
columns. Those derived scores reproduce Appendix A's stated band in only 36% of
the 24 use cases. The disagreement is not noise:

- **8 of the 11 use cases Appendix A calls "Low" carry exactly one High factor —
  Federal Program Nexus.** Appendix B rates any delegated federal programme
  (NPDES, RCRA, CAA…) as 3, and at weight ×1.5 that contributes 4.5 points,
  consuming 37.5% of the 12-point Low ceiling before anything else is scored.
- Relaxing the single-High-forces-Moderate rule does **not** rescue them: their
  composites (12.5–15.0) already exceed the ceiling on their own.
- The practical consequence: *no SCDES environmental use case touching a
  delegated federal programme can classify Low under the matrix as adopted* —
  yet Appendix A labels eleven of them Low.

This is exactly the tension Configuration Mode exists to resolve. OT can move
the Federal Program Nexus weight, raise the Low ceiling, or accept that the
agency's delegated-programme work is inherently Moderate — and the Configure
room shows which projects each choice moves before it is saved. The app does not
pick; it makes the choice visible and its consequence explicit.

The remaining disagreements run the other way: Appendix A calls the three
Category 3 innovation use cases "High" where the derivation says Moderate. Those
reflect judgement the columns do not carry, which is why derived scores are
marked `derived` in the Registry and confirmed by an operator at Gate 0 —
consistent with Appendix A's own note that its risk column is "starting guidance
only".

## Corpus integrity notes

The ingester surfaces rather than silently normalises three defects the package
author already identified:

1. **Appendix M naming conflict** — the Operations Manual calls M "Table of
   Authorities"; the Implementation Playbook calls it "Institutional Capacity
   Assessment".
2. **The Manual's closing appendix list drops Appendix E**; §2 includes it.
3. **Six-phase vs. seven-step model.** The Framework and Manual use Gates 0–5;
   the Seven-Step Environmental AI Lifecycle is a communications-facing synthesis
   over the same phases. This build treats **gates as the mechanics** (they are
   what Appendix H encodes and what the Council decides on) and the seven steps
   as the presentation layer above them.
