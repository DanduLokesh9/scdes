# The AI Governance App — what it is, and how it works

Written for anyone who has to understand or explain this, whether or not they
write software. Technical choices are described in plain English, each with an
example. Where something is not real yet, it says so.

---

## 1. The problem

An agency adopts a set of rules for how it will use AI. In this case South
Carolina's Department of Environmental Services (SCDES) adopted a Governance
Framework, an Operations Manual, and thirteen appendices, signed into effect on
21 July 2026.

Then those rules sit in a binder.

Someone wants to build an AI tool. They have to know which rules apply, what
risk band it falls into, which committee has to approve it, which forms to fill,
and what happens if it goes wrong. All of that is written down somewhere across
several hundred pages. In practice nobody reads it, so the rules get applied
from memory, inconsistently, and the record of *why* a decision was made is a
scattering of emails.

**This application turns the binder into working software.** Not a summary of
the rules — the rules themselves, executing.

---

## 2. What it does

Seven things, each corresponding to a section in the left-hand menu.

| Section | What it is for |
|---|---|
| **Vision** | Where the agency intends to get to, and how the current portfolio climbs toward it |
| **Registry** | Every AI system the agency has, as a tracked project: stage, owner, risk, review date |
| **Lifecycle** | Walking a project through six approval gates, filling the real forms as you go |
| **Budget** | Which proposals fit the money available, and which to fund first |
| **Oversight** | Monitoring duties, incident response, and re-scoring risk when something changes |
| **Terminology** | Choosing the agency's vocabulary once, so every screen speaks the same language |
| **Configure** | Tuning the risk model and thresholds — with the consequences shown before saving |

Plus three assurance screens: the **Agency profile** (what the app has worked
out about the agency from its own documents), **Integrity** (what is wrong with
the record), and the **Audit trail** (everything that has happened).

There is also a command bar on `Ctrl-K` that does three things: answers a
question with citations, runs a hypothetical that changes nothing, and turns a
plain-English problem statement into a draft project.

---

## 3. How it works, in plain English

### 3.1 It reads the agency's own documents

Nothing is typed into the code. The application opens the actual Word and Excel
files the agency adopted, and works out their structure.

**What that means concretely.** The thirteen Excel appendices contain 32 sheets,
which break down into 418 blocks and **1,068 individual fields**. Every field
carries where it came from — which file, which sheet, which cell.

The hard part was that a spreadsheet has no idea it is a form. A human looking
at Appendix G sees "Project Name:" followed by a box to write in. A computer
sees two cells. So the parser recognises four shapes that these documents use
over and over:

- **A form** — a label, then a space for the answer (`Project Name: | ____`)
- **A checklist** — numbered requirement, status, evidence (all of Appendix H)
- **A parameter table** — anything with a Weight or Score column (Appendix B)
- **A record table** — a header row with data rows underneath (Appendices A, C)

*Example of why this matters:* Appendix G's template literally tells you what
kind of control each field needs — `[Select: Water / Land and Waste / Air]`. The
application reads that hint and builds a dropdown with exactly those three
options. Nobody wrote "Water, Land and Waste, Air" into the code. If the agency
amends the appendix to add a fourth programme, the dropdown gains a fourth
option with no code change.

### 3.2 It answers questions, and shows its working

Ask *"What triggers a Level 2 incident?"* and you get an answer that cites
**Operations Manual §22.4**. Click the citation, read the actual paragraph.

**How, in plain terms.** The documents are chopped at their own headings, so a
chunk is always a complete numbered section. When you ask a question, the
application scores every chunk on how well it matches your words — favouring
rare, specific words like "Gate 3" or "Federal Program Nexus" over common ones
like "the" or "process". The best-matching chunks are the answer, and because
the chunk boundary *is* a numbered section, the citation is exact by
construction rather than approximate.

**It also refuses.** Ask *"What is the best pizza topping?"* and it declines,
because the question is not about anything in the corpus.

*This took two attempts.* The first version scored that pizza question as
in-scope — it had matched the word "best" inside "best practices". The fix was
to check what fraction of the *question's meaningful words* actually appear in
the documents, not just whether something matched. Off-topic questions now score
0.17–0.21 against a 0.30 threshold; real questions score 0.37–0.83.

### 3.3 It classifies risk, and the maths is visible

Appendix B rates six factors from 1 to 3 and weights them:

| Factor | Weight | A "3" means |
|---|---|---|
| Regulatory Impact | ×1.5 | Direct effect on regulatory outcomes |
| Public-Facing Exposure | ×1.0 | Directly affects public services or decisions |
| Data Sensitivity | ×1.5 | Personal, enforcement, or legally protected data |
| Reversibility | ×1.0 | Difficult to reverse; downstream dependencies |
| Community Impact | ×1.5 | Likely disproportionate impact on overburdened communities |
| Federal Program Nexus | ×1.5 | Delegated federal programme (NPDES, RCRA, Clean Air Act) |

Score 12 or below is **Low**, 13–17 is **Moderate**, 18 or above is **High**
(maximum 24). Two or more factors rated 3 forces High regardless of total; a
single 3 forces at least Moderate.

**The important design decision.** This calculation is a *pure function* — it
takes numbers in and returns a band out, and it touches nothing else. No saving,
no side effects.

That sounds like a technicality. It is actually the feature that sells the
product. Because the calculation changes nothing, the same code can safely be
run against hypothetical settings. So the Configure screen can say:

> *If you move Data Sensitivity from ×1.5 to ×2.0, these two projects move from
> Moderate to High, which newly triggers a Council decision at Gate 2 and makes
> Appendix K required.*

…and show you that **before** anything is saved. "Exploring changes nothing"
becomes structurally true rather than a rule someone has to remember not to
break.

### 3.4 One place decides who may do what

Every action that changes anything passes through a single function that asks
two questions: *who are you*, and *what mode is the agency in*. It then records
its answer either way — permission granted **and** permission refused are both
written to the audit log.

**Why one place and not fifty.** If each screen checked permissions for itself,
there would be fifty chances to forget. There is one gate, and the test suite
actively attacks it: a test tries to make the chat assistant write configuration,
tries to have an operator move a risk weight, tries to have a hypothetical
scenario overwrite the real budget. Each attempt must be refused *and* the
refusal must appear in the audit log.

### 3.5 The audit trail is tamper-evident

Every entry includes a fingerprint of the entry before it, forming a chain.

**The analogy.** Imagine a ledger where every page has, printed at the top, a
summary code of the previous page. Tear out page 40 and page 41's code no longer
matches page 39 — the gap is obvious even though the missing page is gone.

That is what this does. Change or delete a past entry and every entry after it
stops matching, and verification names the exact entry where the chain broke.

**What it does not do — and this matters.** It is tamper-*evident*, not
tamper-*proof*. Anyone with access to the file could rewrite the entire chain
from the beginning and it would verify cleanly. Closing that needs an
append-only store or cryptographic signatures. This is written down rather than
glossed over, because the client has said the trail will be legally binding.

### 3.6 Configuration Mode is a one-way door

The Council adopted the appendices as *templates*. The Office of Technology then
sets what the agency actually needs — the weights, the thresholds, the budget
pools. That is **Configuration Mode**, and the header shows "Tuning open".

Once the Council adopts the tuned settings, the app moves to **Operating Mode**
("Guardrails live"). From then on, even the Office of Technology must route a
change through the Council.

**It only moves one way.** Returning to Configuration Mode requires a Council
act. A test tries to do it without one and must be refused.

### 3.7 It standardises the agency's vocabulary

Agencies name the same concepts differently — bucket or category, tier or level,
A/B/C or 1/2/3. Mixed usage in a legally binding record is a genuine hazard.

The application counted how each term is actually used across the corpus and
proposes the winner:

| Concept | Chosen | Evidence |
|---|---|---|
| Grouping of use cases | Category 1 / 2 / 3 | 72 uses |
| Council decision class | Tier A / B / C | 34 uses |
| Incident severity | Level 1 / 2 / 3 | 35 uses |
| Vendor disclosure | Tier 1–4 | 41 uses |
| Risk band | Low / Moderate / High | 8 uses |

Choose once, and every screen, checklist and cited answer re-labels itself. It
does **not** rewrite the adopted documents — those stay exactly as signed.

### 3.8 It audits the record and reports what is wrong

A standing check of the corpus against itself: citations that do not resolve,
dates left blank, duties assigned to roles the framework never established.

Current result: **13 findings — 1 critical, 2 serious, 10 moderate.**

The critical one: the adoption date is blank across the entire corpus, even
though the charter was executed on 21 July 2026. On a document set intended as
a legal record, that is the kind of defect that surfaces at the worst possible
moment.

**It reports; it does not silently fix.** Correcting an adopted instrument is a
Council amendment — propose, diff, approve, commit. An application that quietly
edited signed documents would destroy the thing it exists to protect.

---

## 4. Making it work for any state

The client's brief was that this should not be a South Carolina product.

### 4.1 Nothing about SCDES is in the code

The agency's name, its instruments, its gates, its roles and its vocabulary are
all worked out from whatever documents are loaded.

*How this was proved.* A synthetic agency was invented that shares nothing with
SCDES — different state, different domain, instruments called "Schedule 1–5"
instead of "Appendix A–N", checkpoints called "Stage" instead of "Gate",
different roles, different vocabulary. The application discovers all of it
correctly. A test also greps the discovery code for agency-specific words and
fails the build if any appear. That test has caught real regressions.

### 4.2 The map

The landing page is a real map of the United States, with the flag set into the
country's outline.

**What "real" means here.** The state boundaries are US Census Bureau
cartographic data, projected using Albers equal-area conic — the standard
projection for the continental US — with Alaska and Hawaii as insets, which is
how essentially every US thematic map is drawn. It is built once, offline, into
a file the browser reads. No mapping library, no internet connection, no API key.

The flag uses the actual specification: Old Glory Red, Old Glory Blue, a canton
two-fifths of the length and seven stripes deep, and fifty five-pointed stars in
nine rows on an eleven-column grid.

### 4.3 Each agency's own colours

Selecting a state themes the whole application in that agency's colours,
harvested from its live public website.

**The mistake worth recording.** The first version forced every agency into a
fixed palette of eight colours and generated whatever was missing. Each one
looked fine on its own. Together they converged — because the generated filler
followed the same recipe every time, an agency with four real colours came out
half itself and half house style, and all fifty states drifted toward looking
alike. Which defeats the entire point of theming per agency.

Now the palette is however many colours the agency actually has — from 2 to 19,
averaging 12 for the sites that could be read. Nothing is padded. Interface
roles are filled by *reusing* those colours, so a three-colour agency is themed
in exactly its three.

**Two things are deliberately not taken from the brand.**

*Risk colours are the same in all fifty states.* Low green, Moderate amber, High
red, everywhere. Theming these was what forced a green to be invented for every
agency that hasn't got one — and it produced a Maine palette where "Low risk"
rendered magenta. In a legally binding record, an interface that misstates risk
in order to look on-brand is the wrong trade.

*Text colour adapts to the brand, never the reverse.* Text over an agency colour
is black or white, whichever is legible. The brand colour is never altered.

**Filtering out what isn't really a brand.** Many agency sites run WordPress or
Bootstrap and inherit those default colours. Harvesting them yields Bootstrap's
brand, not the agency's — and again makes every state look the same. Two filters
handle it: a list of known framework defaults, and a data-driven one — any colour
appearing on three or more *different* agencies' sites is a default nobody chose,
and is dropped. Across 32 scraped sites, 335 colours belonged to exactly one
agency and only a dozen appeared on three or more, all traceable to a framework.

---

## 5. What is real and what is not

This is the section to read before showing anyone.

**Real:**

- The SCDES corpus — the actual adopted documents, parsed
- The risk weights and thresholds — read from Appendix B
- The 24 pre-classified use cases in Appendix A
- The integrity findings — computed against the real documents
- The vocabulary counts — counted in the corpus
- The map geography — Census data
- SCDES's own palette — from its published brand guide

**Not confirmed:**

- **The scraped colours.** These are what each agency uses in public. **No
  agency has confirmed them.** 33 of 51 sites could be read; 16 refuse automated
  reading (Cloudflare/Akamai blocks on California, New York, Michigan,
  Massachusetts, South Carolina, Virginia among others) and show a neutral
  placeholder rather than a guess.
- **The agency names.** Seeded from public knowledge and marked unverified —
  agencies rename themselves; South Carolina's did in 2024. Loading a corpus
  replaces the name with what the documents say.

**Invented for demonstration, and labelled as such:** the budget recommendation
weights, the roadmap costs, and the mapping from risk band to required
appendices. These are placeholders for values the agency must set.

**Only one corpus is loaded at a time.** Selecting Texas themes the application
and changes the name, but Texas's documents do not exist. Rather than show South
Carolina's project register under a Texas heading — a fabricated record — every
screen refuses and explains why.

---

## 6. Known limits

- **No authentication.** The current user is a URL parameter. Fine for a local
  reference build, not for deployment. Production needs the agency's single
  sign-on.
- **The audit log is tamper-evident, not tamper-proof** (§3.5).
- **Configure covers 13 of the 1,068 parsed fields.** The parser reads
  everything; the tuning interface exposes the parameters that matter most.
- **No live model telemetry exists**, so Oversight ships a schedule and
  attestation register rather than invented drift charts. Showing fabricated
  monitoring numbers would be worse than showing what is owed.
- **PermitPro's six source files were not in the package**, so the worked
  example is reconstructed from what the other documents say about it.

### One substantive finding

**Appendix A's stated risk classifications are not reproducible under Appendix
B's matrix, and the cause is structural.** Deriving the six factor ratings from
Appendix A's own columns reproduces its stated band in only about a third of
cases. Eight of the eleven cases Appendix A calls "Low" carry exactly one High
factor — Federal Program Nexus. Appendix B rates any delegated federal programme
as 3, and at ×1.5 that alone consumes 37.5% of the Low ceiling before anything
else is scored.

This is not a bug to be fixed in code. It is a policy tension for the Council:
either move the Federal Program Nexus weight, raise the Low ceiling, or accept
that delegated-programme work is inherently Moderate. The Configure screen shows
which projects each choice moves before it is saved.

---

## 7. How it is built

- **Python 3.11+ with no web framework.** The server is the standard library's
  own. No installation of anything, no internet, no external service.
- **No database.** The corpus is files; the audit log is a text file, one JSON
  record per line. Everything is inspectable with a text editor, which matters
  for something meant to be a legal record.
- **Retrieval is lexical, not AI embeddings.** This corpus is dense regulatory
  prose searched using its own vocabulary, where exact terms beat similarity —
  and the chunk boundary is the citation.
- **Language model is optional.** Retrieval and citation are always local; only
  the retrieved snippets and the question would ever reach a model, and there is
  a fully offline path with no API key.
- 23 modules, **757 automated tests**.

### Running it

```
python -m app.server        # then open http://127.0.0.1:8765
python -m pytest -q         # run the test suite
```

---

## 8. Using it — the short version

Open it and you land on the map. Pick an agency; press **Enter** to go in.

Inside, the **? Guide** button in the header walks through the interface. The
left rail is the sections; the centre is the record; the right is always *why*,
with the section it cites. `Ctrl-K` asks questions. `Esc` returns to the map.

The single idea behind the layout: **the record and the reason, side by side.**
Explainability is part of the frame rather than a panel you go looking for — for
a governance trail, being able to see why something says what it says is the
point of the whole exercise.
