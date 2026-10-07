/* SCDES AI Governance — shell.

   Two ideas drive the layout:
   · the record (center) is what the governed record says; the reason (right
     rail) is always why, with the section it cites. Explainability is part of
     the frame rather than a panel you go looking for.
   · the command bar (Ctrl/Cmd-K) carries query, what-if and intake, so asking
     is available everywhere instead of living on one page. */

const S = { user: "liz.operator", view: "vision", project: "AI-001",
            gate: null, state: null, vocab: {}, decider: null,
            projectGate: null };

const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const n = document.createElement(t);
  if (c) n.className = c; if (h !== undefined) n.innerHTML = h; return n; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = (n) => "$" + Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
const cls = (b) => String(b || "").toLowerCase();

/* vocabulary-aware labels — the configured term, not a hardcoded one */
const vlabel = (concept, key) =>
  (S.vocab[concept] && S.vocab[concept][String(key).toLowerCase()]) || String(key);

/** The address this browser registered with, if any. */
function registeredEmail() {
  try {
    return (JSON.parse(localStorage.getItem("scdes.registration") || "{}")
            || {}).email || "";
  } catch (e) { return ""; }
}

/** The token issued when a verification code was actually read out of a
    mailbox. What the address above claims, this one proves. */
function sessionToken() {
  try { return localStorage.getItem("scdes.session") || ""; }
  catch (e) { return ""; }
}

async function api(p, opts = {}) {
  const sep = p.includes("?") ? "&" : "?";
  // Name and title travel as headers on every request, because the audit entry
  // is written server-side at the moment of the action — if they were only sent
  // at sign-in, every later entry would fall back to the bare capacity label.
  const headers = {
    "Content-Type": "application/json",
    "X-SCDES-User": S.user,
    // Where this person is, so the dates the server stamps are today here,
    // not today in UTC. Minutes east of UTC; carries daylight saving.
    "X-GAIUS-UTC-Offset": String(-new Date().getTimezoneOffset()),
  };
  if (S.actorName) headers["X-SCDES-Name"] = S.actorName;
  if (S.actorTitle) headers["X-SCDES-Title"] = S.actorTitle;
  // The registered address, only so the server can recognize a tester.
  const reg = registeredEmail();
  if (reg) headers["X-SCDES-Email"] = reg;
  // The proof of that address, as opposed to the claim of it. A header rather
  // than a query parameter so it stays out of server access logs and out of the
  // URLs the bug reporter captures.
  const session = sessionToken();
  if (session) headers["X-GAIUS-Session"] = session;
  const qs = "user=" + encodeURIComponent(S.user) +
             (reg ? "&email=" + encodeURIComponent(reg) : "");
  const r = await fetch(p + sep + qs, { headers, ...opts });
  const data = await r.json();
  // The server could not tie this to a signed-in person in an organization:
  // keep the change to send again after signing back in, and say so, rather
  // than let the screen look as if it saved (see sessionEnded).
  if (data && data.session_ended) {
    if (opts.method === "POST" && window.queueRefused) window.queueRefused(p, opts.body);
    if (window.sessionEnded) window.sessionEnded(data.error);
  }
  return data;
}
const post = (p, b) => api(p, { method: "POST", body: JSON.stringify(b) });

let tt;
function toast(msg, bad = false) {
  const t = $("#toast"); t.textContent = msg;
  t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(tt); tt = setTimeout(() => (t.className = "toast"), 5600);
}

/* ----------------------------------------------------------- reason rail */

function reason(blocks) {
  const body = $("#reasonBody");
  body.innerHTML = "";
  if (!blocks || !blocks.length) {
    body.innerHTML = `<p class="reason-empty">Nothing selected.</p>`;
    return;
  }
  blocks.forEach((b) => {
    const w = el("div", "reason-block");
    w.innerHTML =
      (b.title ? `<h3>${esc(b.title)}</h3>` : "") +
      (b.body ? `<p>${esc(b.body)}</p>` : "") +
      (b.quote ? `<div class="reason-quote">${esc(b.quote)}</div>` : "") +
      (b.cite ? `<div class="reason-cite">${esc(b.cite)}</div>` : "");
    body.appendChild(w);
  });
}

/* ---------------------------------------------------------------- shell */

const META = {
  home:      ["Welcome", "What this is, why it matters, and what happens next."],
  framework: ["Framework", "The adopted documents everything else is read out of. Load them here first."],
  // Summaries reworded by the team, Sep 30 2026: Vision, Registry, Data,
  // Projects, Lifecycle, Process, and Audit trail renamed History.
  holdings:  ["Data", "What information you hold, where it lives, and who uses it."],
  vendors:   ["Vendors", "Who you buy from, what it costs, and what those tools could also do."],
  billing:   ["Subscription", "What the paid modules cover, what your organization has, and how to buy it."],
  vision:    ["Vision", "Your goals for AI, filled in from your framework."],
  registry:  ["Registry", "List the AI tools you use, and find ones you could use."],
  // `workflow` was the retired gate screen, titled Lifecycle. These two
  // replace it: the tracker that carries one project through the seven named
  // gates, and a reference page that explains them and holds no record — see
  // the note above `api_config` in app/server.py.
  projects:  ["Projects", "Each use of AI, from the problem to the day it is switched off."],
  // Shown as Guide since Oct 2026 (the team's request); the key is unchanged.
  lifecycle: ["Guide", "See the seven steps every project goes through."],
  budget:    ["Budget", "What it costs you, all in."],
  oversight: ["Oversight", "Who decides, and what happens when it goes wrong."],
  process:   ["Process", "See how a new request is reviewed and approved."],
  setup:     ["Terminology", "One vocabulary, chosen once, applied everywhere after."],
  bugs:      ["Reported bugs", "What users hit, what was already happening when they did, and where it got to."],
  usage:     ["Usage", "Every agency on this installation, who is working in it, and how far each has got."],
  subscriptions: ["Subscriptions", "Every organization's orders, and where an invoice is marked paid."],
  organizations: ["Organizations", "Every organization's admins, appointed by the GAIUS team, and sign-ups that never finished."],
  configure: ["Configure", "The operational layer beneath the Framework."],
  // Deliberately not a fixed string. What this room is called, and whether it
  // describes a body at all, is an answer the agency gives while writing its
  // framework — see deciderMeta(), which overwrites this entry once known.
  council:   ["Who decides", "One framework answer: a standing body, or one named person."],
  agency:    ["Agency profile", "Who this corpus belongs to, and how it is structured — all of it discovered."],
  integrity: ["Integrity", "Does it work, and is it still working."],
  audit:     ["History", "See every change: what, who, and when."],
};

/* The agency picked on the map, against the organization the signed-in
   address actually belongs to. Every record on screen comes from the second;
   the header used to come from the first. Signed in as an IIA address after
   picking SCDES, the header said SCDES and the People panel listed IIA's test
   organization under SCDES's name. Where they differ this says so, in words,
   and the header names the organization the records belong to. */
function orgMismatch(st) {
  const old = document.getElementById("orgMismatch");
  if (old) old.remove();
  const picked = window.SCDES_AGENCY || {};
  const own = (st && st.organization) || {};
  if (!own.code || !picked.agency_id || picked.agency_id === own.code) return;
  const email = (typeof registeredEmail === "function" && registeredEmail()) || "this address";
  const mine = own.label || "another organization";
  const chosen = picked.agency || "the agency you picked";
  const note = el("div", "locked");
  note.id = "orgMismatch";
  note.setAttribute("role", "status");
  note.style.margin = "0 0 14px";
  note.innerHTML = `<b>You are in ${esc(mine)}, not ${esc(chosen)}.</b>
    You chose ${esc(chosen)} on the map, but you signed in as ${esc(email)}, which belongs to
    ${esc(mine)}. Everything on these screens is ${esc(mine)}'s. To work in ${esc(chosen)},
    sign out and sign in with an address registered to it.
    <div class="row" style="margin-top:8px"><button type="button" class="btn ghost" id="orgMismatchOut">Sign out</button></div>`;
  const record = $("#record");
  if (record) record.prepend(note);
  const out = note.querySelector("#orgMismatchOut");
  const signOut = $("#signOut") || [...document.querySelectorAll(".topbar button")]
    .find((b) => /sign out/i.test(b.textContent));
  if (signOut) out.onclick = () => signOut.click(); else out.remove();
  // The header names the organization the records belong to.
  const crumb = $("#agencyCrumb");
  if (crumb && own.label) crumb.textContent = own.label;
  if (own.label) document.title = `${own.label} — AI Governance`;
}
document.addEventListener("agencychange", () => {
  if (S.state && !S.state.impersonating) orgMismatch(S.state);
});

/* "Viewing as … — End impersonation". Only ever drawn for a GAIUS admin who
   chose View as on the Organizations screen (app/impersonate.py). Fixed
   across the top, above everything — including any dialog the viewed
   person's state would open — so the way out is always one press away. */
function impersonationBar(st) {
  const old = document.getElementById("impBar");
  if (old) old.remove();
  document.body.classList.remove("impersonating");
  const v = st && st.impersonating;
  if (!v) return;
  const bar = el("div", "imp-bar");
  bar.id = "impBar";
  bar.setAttribute("role", "region");
  bar.setAttribute("aria-label", "Impersonation");
  bar.innerHTML = `<span><b>Viewing as ${esc(v.name)}</b>${v.title ? `, ${esc(v.title)}` : ""}
      · ${esc(v.organization)} · <b>view only</b> — nothing can be saved or changed.</span>
    <button type="button" class="btn" id="impEnd">End impersonation</button>`;
  document.body.prepend(bar);
  document.body.classList.add("impersonating");
  bar.querySelector("#impEnd").onclick = async () => {
    const b = bar.querySelector("#impEnd");
    b.disabled = true;
    await post("/api/admin/impersonate/stop", {});
    location.reload();
  };
  const crumb = $("#agencyCrumb");
  if (crumb && v.organization) crumb.textContent = v.organization;
  document.title = `Viewing as ${v.name} — ${v.organization}`;
}

async function refreshState() {
  const st = await api("/api/state");
  S.state = st;
  S.vocab = st.vocabulary || {};

  // Drawn only for the three GAIUS admins. Not a security measure — the server
  // re-checks the proven address on every admin request — but a user who never
  // sees the heading never wonders what is behind it.
  const adminRail = $("#adminRail");
  if (adminRail) adminRail.hidden = !st.admin;

  impersonationBar(st);
  if (!st.impersonating) orgMismatch(st);
  watchSessionEnd(st);

  const mode = $("#modeChip");
  mode.textContent = st.mode === "operating" ? "Guardrails live" : "Tuning open";
  mode.className = "tb-chip " + (st.mode === "operating" ? "live" : "tuning");

  // §1.2 · two numbers, and no "0 to fix" — a badge reading that is a nag.
  // Words carry the meaning; the chip's color does not change with it.
  const ig = $("#integrityChip");
  ig.textContent = (st.integrity || {}).badge || "Integrity";
  ig.className = "tb-chip";

  const tchip = $("#testerChip");
  if (tchip) tchip.hidden = !st.tester;

  $("#avatar").textContent = st.actor.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
  $("#avatar").title = st.actor.title
    ? `${st.actor.name} — ${st.actor.title}` : st.actor.name;

  // The picker switches *capacity*, not person — the person is whoever signed
  // in. Built from `capacities`, so no invented names appear anywhere.
  const pick = $("#userPick");
  if (!pick.options.length)
    (st.capacities || []).forEach((c) => {
      const o = el("option"); o.value = c.id; o.textContent = c.label;
      pick.appendChild(o);
    });
  pick.value = st.actor.id;
  paintDecider(st.decider);
  await renderSpine();
}

/* An earlier build shipped "Council" as furniture: a permanent room in the rail,
   and gate wording that told every agency its approvals route to a body. That is
   SCDES's answer to a framework question, not everyone's. A unit with one
   technology officer who makes the calls and reports out was being pointed at a
   council it had deliberately not created.

   So the room is named by the answer, and says the question when there isn't
   one yet. */
/* The deciding body, in this agency's own words.

   "Council" is SCDES's answer to a framework question, not a fixture of the
   product — the client's point, and the whole reason app/decider.py exists. The
   rail label followed it from the start; the prose did not, so screens went on
   telling every agency that its changes "route through the Council" while the
   sidebar beside them said something else.

   These read `S.decider`, which arrives with /api/state, and fall back to
   wording that names no shape at all rather than to "Council". */
function whoDecides() {
  return (S.decider && S.decider.body) || "whoever holds the decision";
}

function whoDecidesPossessive() {
  return (S.decider && S.decider.possessive) || "the decision-maker's";
}

function whoDecidesLabel() {
  return (S.decider && S.decider.rail_label) || "Who decides";
}

/** The agency's own shorthand, for prose that used to say "SCDES". */
function agencyShort() {
  const a = window.SCDES_AGENCY || {};
  return (a.abbrev && a.abbrev !== "—" ? a.abbrev : "") || "this agency";
}

function paintDecider(d) {
  S.decider = d || null;
  const label = (d && d.rail_label) || "Who decides";
  const item = document.querySelector('.rail-item[data-view="council"]');
  if (item) {
    // Keep the icon node; replace only the text after it.
    const icon = item.querySelector("i");
    item.textContent = label;
    if (icon) item.insertBefore(icon, item.firstChild);
    item.title = (d && d.sentence) || "";
    // Unanswered is a real state, not an error — mark it as outstanding work
    // rather than hiding the room and leaving the question unasked.
    item.classList.toggle("rail-open-question", !(d && d.decided));
  }
  META.council = d && d.decided
    ? [label, d.is_group
        ? "The gated room where the governance changes."
        : "Every gated call, who made it, and what it was based on."]
    : ["Who decides",
       "One framework answer: a standing body, or one named person."];
}

/* The six-gate spine strip and its renderer were retired here, with the
   Workflow Helper they navigated.

   They drew Concept · Readiness · Pilot · Deployment · Scaling · Annual
   review across the top of every screen as numbered links, and tracked two
   facts at once: where the project had reached, and which gate you were
   reading. That distinction is right and worth keeping when the tracker
   grows the same behavior.

   What was wrong with it is not the design. It renders a gate as a number,
   which the lifecycle spine forbids "anywhere, in code or in copy", because
   a numbered gate invites a reader to line it up against somebody else's
   and import a staging scheme this platform did not write. It also says
   Deployment, which belongs to the Deploy gate's name and nowhere else.
   And a strip claiming to show where "the project" is, above a screen about
   something else, is only ever right while exactly one project exists.

   Replaced by the tracker in app/projects.py: all seven named gates, on the
   project they belong to. See the note above `api_config` in
   app/server.py. */
async function renderSpine() {
  const spine = $("#spine");
  if (spine) spine.hidden = true;
}

/* One distinction from the retired spine is worth carrying forward when the
   tracker grows the same behavior, so it is recorded rather than lost.

   `now`     — the gate the project has actually reached. A property of the
               record: it sits where it sits whatever you are looking at.
   `viewing` — the gate you clicked. A property of the screen.

   Those were once collapsed into a single highlight driven by the project's
   position, so clicking one gate left the previous one lit and the header
   looked frozen. Both are worth showing at once: losing "where the project
   is" would be worse than the bug, because that is the fact a tracker
   exists to state. */
function paintSpineSelection() {
  /* The strip it painted is gone. Kept as a no-op rather than deleted
     because `go()` calls it on every navigation, and a retirement that
     leaves a call site throwing is not a retirement. */
}

/* Every record in this application — PermitPro, the 25 tracked systems, the
   budget pools, the integrity findings — comes from the one corpus that is
   actually loaded. Selecting a state on the map changes the theme and the name;
   it does not and cannot conjure that state's documents.

   So when the selected agency is not the loaded one, the views must not run.
   Rendering South Carolina's project register under "Texas Commission on
   Environmental Quality" would be a fabricated record, and this is the app whose
   whole claim is that its trail can be relied on. */
function agencyHasCorpus() {
  const a = window.SCDES_AGENCY;
  /* No agency chosen means no corpus — not "the loaded one".

     This read `!a || a.corpus_loaded`, so before anyone signed in the
     application assumed SCDES's documents were yours. Registering with the
     DEMO agency put SCDES in the header, PermitPro across the spine and
     SCDES's framework files on the Framework page, because none of those
     screens had any reason to think otherwise.

     Defaulting to "yes" is the wrong direction for a question about whose
     records a person may see. */
  return !!(a && a.corpus_loaded);
}

/* ------------------------------------------------------- the framework gate

   The framework is the brain: the risk model, the gates, the vocabulary and the
   required instruments are all read out of it. Without one there is nothing to
   read, so every other screen would be showing structure the agency never
   agreed to — worse than an empty screen, because it looks authoritative.

   So: one section reachable, and it explains itself. */

//: `bugs` is exempt because an admin looking at the queue is not doing the
//: agency's authoring work, so the framework gate has nothing to say about it.
//: It is no longer exempt for the original reason — that reporting a fault must
//: never be gated — because reporting moved to the help panel, which is on
//: every screen and gated by nothing. This is the reading side, and it is
//: admin-only.
//: `holdings` and `vendors` are exempt because the gate's own reason does not
//: apply to them. The panel says "this screen is read out of the adopted
//: framework" — the two registers are read out of nothing but what this
//: tenant typed into them. The data one is also the answer to the framework's
//: own question 7.2, "do you know where your information actually lives", so
//: shutting it until the framework is finished puts the answer behind the
//: question. Their *findings* do read the framework, and where there is
//: nothing to read they say so rather than reporting a clean bill of health.
//: The subscription gate still applies to both: these are the paid modules
//: and the framework is the free one.
//: `billing` is exempt for the plainest reason of all: it is the page that
//: sells the rest, so gating it on having finished the thing you are buying
//: — or on already having bought it — would be a shop with the door locked.
//: `usage` is exempt on the same reasoning as `bugs`: it is IIA reading who
//: is using the product, across every agency, which is running GAIUS rather
//: than authoring any one agency's framework. Neither gate has anything to
//: say about it, and gating it on *this* tenant having finished a framework
//: would be nonsense — the page is about everybody else's.
/* `lifecycle` is exempt, and it is the clearest case on the list. It is the
   page somebody opens when they are stuck partway through authoring the
   framework, and it explains the seven steps the authoring work is about.
   Greying it out with "build your governance framework first" would shut the
   explanation behind the thing it explains. It also holds no record, reads
   nothing that belongs to a tenant, and renders in full with every question
   unanswered — so neither gate has anything to protect here.

   `projects` is deliberately not exempt. Its levels, its cadence and the
   paper each gate asks for are all read out of the framework, so a tracker
   opened before any of that exists would be a screen of blanks. */
/* Integrity is here because every read-back on it falls back to the recorded
   gap rather than waiting on an answer, and because the incident form must
   never be locked: "Restricting who may write something down produces
   organizations where nothing is written down." */
const FRAMEWORK_EXEMPT = new Set(["home", "framework", "agency", "bugs",
                                  "usage", "holdings", "vendors", "billing",
                                  "lifecycle", "subscriptions", "organizations", "integrity",
                                  "process", "oversight", "registry",
                                  "budget", "vision", "audit"]);

/* The corpus gate asks a different question, and the two answers have now
   stopped coinciding — which is what this name was kept separate for.

     needs the framework      — have you decided anything yet
     needs a corpus           — do the records on this screen belong to you

   Every screen that needs no framework still holds nothing but this
   tenant's own material, so the whole of the list above carries over. What
   is added is `projects`.

   Projects reads no adopted document. Its register is its own file, written
   through `tenant.scoped()`, so there is no version of it that could show
   somebody another organization's rows — `api_projects` is deliberately not
   wrapped in `_corpus_only` for the same reason. Left behind the corpus
   gate it rendered "none have been loaded", about documents it never reads,
   to an organization whose own project list was sitting there unshown. */
const CORPUS_EXEMPT = new Set([...FRAMEWORK_EXEMPT, "projects"]);

function frameworkReady() {
  return !S.framework || S.framework.usable;
}

async function refreshFramework() {
  try { S.framework = await api("/api/framework"); }
  catch (e) { S.framework = null; }
  paintFrameworkState();
}

/** The rail reflects the gate, so nothing looks clickable that is not. */
function paintFrameworkState() {
  const f = S.framework;
  const tag = $("#fwTag");
  if (tag && f) {
    tag.textContent = { none: "SET UP", draft: "DRAFT", adopted: "LIVE" }[f.state] || "—";
    tag.className = "tag " + (f.state === "adopted" ? "ok"
                             : f.state === "draft" ? "warn" : "bad");
  }
  /* Two different reasons a section can be shut, and they are not the same
     thing — so they do not look the same or say the same thing.

       needs the framework — you can open it by finishing the authoring work
       needs a subscription — you cannot, and no amount of clicking will help

     Both stay visible. Hiding them would leave someone wondering where the
     product went; greying them shows what the work leads to. */
  const tester = !!(S.state && S.state.tester);
  // Finishing the framework does not buy the subscription. The old rule
  // unlocked every paid section the moment a framework was adopted, and the
  // tooltip said "available once your governance framework is complete" — a
  // promise the commercial model does not make. The framework is the free
  // offering; the playbook, appendices and workflow management are not.
  // The server's answer — see `subscribed()` below for why a tester is not
  // counted as subscribed here any more.
  const subscribed = !!(S.state && S.state.subscription);
  document.querySelectorAll(".rail-item[data-view]").forEach((b) => {
    const paid = b.dataset.paid === "1";
    const needsFramework = !tester && !frameworkReady() && !FRAMEWORK_EXEMPT.has(b.dataset.view);
    const needsSub = paid && !subscribed;
    const off = needsFramework || needsSub;
    b.classList.toggle("rail-locked", off);
    b.disabled = off;
    b.title = needsSub
      ? "A paid addition — the governance framework is the free offering"
      : needsFramework ? "Build your governance framework first" : "";
  });
}

/* The seven-step lifecycle, shown on landing so someone understands what they
   are doing and why before they are asked to do any of it.

   Authored by IIA — the provenance line on every generated draft says so, and
   it is repeated here rather than left implicit. */
const LIFECYCLE = [
  { n: 1, name: "Govern",
    what: "Stand up the authority, rules, and register before any project begins.",
    why: "Nothing gets built until someone owns the outcome and the rules are on paper. This is the foundation of public trust.",
    gives: ["Council Charter & Adoption Memo", "Agency Adoption Directive",
            "Program-Level Accountability Roster", "Annual Public AI Report"] },
  { n: 2, name: "Identify",
    what: "Surface the use case, screen the risk, and prove the data is ready.",
    why: "Good ideas are separated from risky ones early — before a dollar is spent or a promise is made.",
    gives: ["Data Readiness Package", "Peer Agency & Center-of-Excellence Check",
            "Portfolio Analysis Package"] },
  { n: 3, name: "Procure",
    what: "Reuse before you buy; buy with the six mandatory provisions.",
    why: "Taxpayer dollars stretch further, and every vendor is held to enforceable AI standards — not marketing claims.",
    gives: ["Six Mandatory Contractual Provisions", "Vendor AI Inventory",
            "Solution Selection Hierarchy record"] },
  { n: 4, name: "Test",
    what: "Pilot with stopping rules, bias tests, and a rollback plan.",
    why: "Systems earn their place with evidence, not promises — and can be pulled the moment they underperform.",
    gives: ["Pilot Plan & Rollback Plan", "Bias Testing Plan & Report to Council",
            "Mid-Pilot & Final Pilot Evaluation",
            "Accessibility Compliance Plan (WCAG 2.1 AA)",
            "Incident Response Tabletop"] },
  { n: 5, name: "Deploy",
    what: "Publish how the tool works, train the workforce, wire up fallbacks.",
    why: "The public can see how the system works, and staff can run it safely — including when it fails.",
    gives: ["Stakeholder Engagement & Communication Plan",
            "Role-Specific Training Plan & Records",
            "Manual Fallback, Recovery & Continuity",
            "VPAT & Accessibility Feedback", "30/60/90-Day Feedback Mechanism"] },
  { n: 6, name: "Measure",
    what: "Monitor drift, bias, and incidents; report on a fixed cadence.",
    why: "Performance is proven continuously, not assumed. Accountability that outlasts the launch.",
    gives: ["Drift Monitoring", "Ongoing Bias Monitoring Records",
            "Root Cause Analysis & Lookback Review",
            "Annual Evaluation & Lessons-Learned"] },
  { n: 7, name: "Sunset",
    what: "Retire the system with the same discipline used to deploy it.",
    why: "Nothing lingers unmanaged. Data, records, and obligations are closed out responsibly to the end.",
    gives: ["90-Day Sunset Notice", "Data Migration & Archival Plan",
            "Verified Transition Confirmation", "Post-Mortem Document",
            "Superseded-Version Retention"] },
];

/* Controls that are live at every step rather than belonging to one. Shown
   separately because presenting them as an eighth step would misrepresent how
   they work. */
const LIFECYCLE_CROSSCUTTING = [
  { name: "The System Registry",
    what: "The single source of truth — every AI system on record, established up front and kept current from first pilot through retirement." },
  { name: "Risk Classification",
    what: "Set at intake and re-checked at every decision point and after any material change, vendor swap, or incident — so oversight scales with risk." },
  { name: "Gate Reviews",
    what: "A consistent go/no-go checkpoint the governing body uses between steps — the connective tissue that keeps every project honest." },
];

/* Taken from the purpose section of the reference framework, with the agency's
   own name substituted. Deliberately parameterised: this text must never name
   another agency to the reader. */
function purposeText(agencyName, stateName) {
  const unit = agencyName || "your governmental unit";
  const where = stateName || "your state";
  return `The creation and adoption of an enterprise-wide Artificial ` +
    `Intelligence Governance Framework is used to establish the evaluation, ` +
    `approval, use, measurement of value, and ongoing oversight of ` +
    `artificial intelligence systems within governmental units in ${where}. ` +
    `Its adoption will reflect a determination by your leadership that AI ` +
    `presents both meaningful opportunity and material risk for a governmental ` +
    `unit. Where artificial intelligence is a nascent and emerging technology, ` +
    `one which is only beginning to enter operational use in ` +
    `governmental settings, this framework and associated policies and ` +
    `procedures have been created in an attempt to support the ethical, ` +
    `responsible, measurable, and efficient use of this technology for ` +
    `your employees and the citizens you serve. The goal of this framework is ` +
    `to create standards which help your colleagues and the public feel ` +
    `confident that ${unit} is putting its best faith efforts into this ` +
    `endeavor.`;
}

const VIEW_HOME = async () => {
  const f = S.framework || await api("/api/framework");
  S.framework = f;
  const agencyName = (window.SCDES_AGENCY && window.SCDES_AGENCY.agency) || "";
  const stateName = (window.SCDES_AGENCY && window.SCDES_AGENCY.state) || "";
  const root = el("div");

  const intro = el("div", "panel");
  intro.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Why you are here</h2>
    <p class="intro">${esc(purposeText(agencyName, stateName))}</p>`;
  root.appendChild(intro);

  const steps = el("div", "panel");
  steps.innerHTML = `
    <h2 class="sub3" style="margin-top:0">The Seven-Step AI Lifecycle</h2>
    <p class="intro">A single, repeatable path that turns AI ambition into
      accountable, auditable delivery — every project moves through the same
      seven steps, so leaders always know who owns it, what it costs, whether it
      works, and how it will be wound down.</p>
    <p class="intro"><b>Govern is what you build here.</b> Nothing gets built
      until someone owns the outcome and the rules are on paper, which is why
      the rest stays closed until it is done.</p>
    <!-- The client's own diagram, rebuilt rather than screenshotted: seven
         columns, an arrow between each, the "why it matters" panel, and the
         deliverables under it. Built in markup so it re-flows on a laptop,
         re-colors with the agency's palette, and leaves the text selectable
         and readable by a screen reader — none of which an image does.

         The step number came out of every column here, and out of the
         paragraph above. The spine forbids rendering a gate as a number
         anywhere, in code or in copy, because a number invites the reader
         to line these up against somebody else's staging scheme — and the
         names carry the sequence on their own. The order of the columns is
         the order of the gates; nothing else is needed to say so. -->
    <div class="lc-board" role="list">
      ${LIFECYCLE.map((s, i) => `
        <div class="lc-col${s.n === 1 ? " lc-now" : ""}" role="listitem">
          <h3 class="lc-title">${esc(s.name)}</h3>
          <p class="lc-does">${esc(s.what)}</p>
          <div class="lc-why">
            <div class="lc-why-h">Why it matters</div>
            <p>${esc(s.why)}</p>
          </div>
          <div class="lc-gives-h">Key deliverables</div>
          <ul class="lc-gives">${s.gives.map((g) =>
            `<li>${esc(g)}</li>`).join("")}</ul>
          ${s.n === 1 ? `<div class="lc-here">You are here</div>` : ""}
        </div>
        ${i < LIFECYCLE.length - 1 ? `<div class="lc-arrow" aria-hidden="true">›</div>` : ""}
      `).join("")}
    </div>

    <div class="lc-cross">
      <div class="lc-cross-h">Cross-cutting: controls active at every step</div>
      <div class="lc-cross-grid">
        ${LIFECYCLE_CROSSCUTTING.map((c) => `
          <div><b>${esc(c.name)}.</b> ${esc(c.what)}</div>`).join("")}
      </div>
    </div>

    <div class="lc-claims">
      <div><b>Accountable by design</b><span>Every decision has a named owner
        and a paper trail — no orphaned systems, no untraceable calls.</span></div>
      <div><b>Auditable at every step</b><span>Leadership, regulators and the
        public can follow the evidence from idea to sunset.</span></div>
      <div><b>Cost-disciplined</b><span>Reuse-before-buy procurement and
        stop-early pilots stretch limited public dollars.</span></div>
      <div><b>Portable across agencies</b><span>One repeatable playbook any
        public body can adopt — not a one-off built to be rebuilt.</span></div>
    </div>

    <p class="small muted" style="margin-top:14px">
      The Seven-Step AI Lifecycle was authored by
      Innovative Infrastructure Advising, LLC · iiac.ai · Charleston, SC.</p>`;
  // The board summarizes; the reference page is where somebody goes when
  // they are stuck on one step. A link rather than more copy here, because
  // this screen already carries the whole of the purpose statement.
  const toRef = el("button", "linky",
    "What each step asks, and where the work is done");
  toRef.onclick = () => go("lifecycle");
  steps.appendChild(toRef);
  root.appendChild(steps);

  const next = el("div", "panel");
  next.innerHTML = `
    <h2 class="sub3" style="margin-top:0">What happens next</h2>
    <p class="intro">${esc(f.headline)} — ${esc(f.detail)}</p>
    <div class="row" style="margin-top:12px">
      <button class="btn" id="homeGo" type="button">
        ${f.state === "none" ? "Start the framework" : "Continue the framework"}</button>
      <button class="btn ghost" id="homeWatch" type="button">Watch the 60-second intro</button>
    </div>`;
  root.appendChild(next);

  const people = await api("/api/agency/people").catch(() => null);
  if (people && people.ok) root.appendChild(peoplePanel(people, agencyName));

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  $("#homeGo").onclick = () => go("framework");
  $("#homeWatch").onclick = () => window.replayWelcome && window.replayWelcome();

  reason([
    { title: "Why the framework comes first",
      body: "Steps 2 to 7 all read from step 1. Identify needs risk categories; Procure needs the contractual provisions; Test needs the gate reviews; Measure needs the incident levels. Without the rules there is nothing for them to apply.",
      cite: "Framework §1 (Purpose)" },
    { title: "Whose framework this is",
      body: "The rules you build here are your agency's. The reference regime is a worked example to start from and amend, never something adopted on your behalf.",
      cite: "Framework §1 (Purpose and Authority)" },
  ]);
};

/* Who is in this organization, and — for its admins — adding and managing
   colleagues.

   Everybody in the organization sees who is in it; only admins see addresses,
   the form and the buttons. An organization can have several admins. The GAIUS
   team appoints the first one (a new registration has none), and admins then
   make others. The last admin cannot be removed or made a member from here,
   so an organization is never left with nobody who can add anyone. Nothing is
   emailed from here — the colleague signs in with their own work email and a
   code sent to it. */
function peoplePanel(d, agencyName) {
  const box = el("section", "panel");
  box.id = "peoplePanel";
  box.setAttribute("aria-labelledby", "peopleH");
  const admin = !!d.is_admin;
  const rows = (d.people || []).map((p) => {
    const mine = admin && p.email && p.email === d.me;
    const isAdmin = p.role === "Admin";
    return `<tr>
      <th scope="row">${esc(p.name)}</th><td>${esc(p.title)}</td><td>${esc(p.role)}</td>
      ${admin ? `<td class="small">${esc(p.email || "")}</td>` : ""}
      <td class="small muted">${esc(niceDate(p.added_at))}</td>
      ${admin ? `<td>${mine ? `<span class="small muted">You</span>` : `
        <button type="button" class="btn ghost" data-role="${isAdmin ? "member" : "admin"}"
          data-email="${esc(p.email)}" data-name="${esc(p.name)}"
          aria-label="Make ${esc(p.name)} ${isAdmin ? "a member" : "an admin"}">${
          isAdmin ? "Make member" : "Make admin"}</button>
        <button type="button" class="btn ghost" data-remove="${esc(p.email)}" data-name="${esc(p.name)}"
          aria-label="Remove ${esc(p.name)}">Remove</button>`}</td>` : ""}</tr>`;
  }).join("");
  const who = (d.admin_names || []).filter(Boolean);
  box.innerHTML = `
    <h2 class="sub3" id="peopleH" style="margin-top:0">People in ${esc(d.organization || agencyName || "your organization")}</h2>
    <div class="table-scroll" role="region" aria-labelledby="peopleH" tabindex="0">
      <table class="vr-table"><thead><tr><th scope="col">Name</th><th scope="col">Title</th>
        <th scope="col">Role</th>${admin ? `<th scope="col">Work email</th>` : ""}
        <th scope="col">Added</th>${admin ? `<th scope="col"><span class="vh">Actions</span></th>` : ""}</tr></thead><tbody>${rows}</tbody></table></div>
    <p class="small" id="peopleSaid" aria-live="polite"></p>
    ${admin ? `
      <h3 class="sub4" id="addPersonH">Add a colleague</h3>
      <p class="small muted">They sign in with their own work email and a code sent to it.
        Nothing is sent to them from here, so tell them they have been added.</p>
      <div class="ap-row">
        <div class="vr-field"><label for="apName">Full name</label>
          <input id="apName" type="text" autocomplete="off" spellcheck="false"></div>
        <div class="vr-field"><label for="apTitle">Job title</label>
          <input id="apTitle" type="text" autocomplete="off"></div>
        <div class="vr-field"><label for="apEmail">Work email${d.domain
            ? ` <span class="small muted" id="apEmail-help">— must end in @${esc(d.domain)}</span>` : ""}</label>
          <input id="apEmail" type="email" autocomplete="off" spellcheck="false"${
            d.domain ? ` aria-describedby="apEmail-help" placeholder="name@${esc(d.domain)}"` : ""}></div>
        <div class="vr-field"><label for="apRole">Role</label>
          <select id="apRole"><option value="member">Member</option><option value="admin">Admin</option></select></div>
        <button type="button" class="btn" id="apGo">Add them</button>
      </div>
      <p class="small muted">An admin can add people, make people admins, and take people off.</p>
      <p class="signin-error" id="apErr" role="alert" hidden></p>
      <p class="small" id="apSaid" aria-live="polite"></p>`
    : d.needs_admin
    ? `<p class="small muted">This organization has no admin yet. The GAIUS team appoints one;
         until then, nobody can add people to it.</p>`
    : `<p class="small muted">${esc(who.join(", ") || "Its admins")} can add people to this organization.</p>`}`;

  if (admin) {
    const err = box.querySelector("#apErr"), said = box.querySelector("#apSaid");
    const val = (id) => box.querySelector(`#${id}`).value.trim();
    const submit = async () => {
      err.hidden = true; said.textContent = "";
      if (!val("apName") || !val("apTitle") || !val("apEmail").includes("@")) {
        err.textContent = "Enter their full name, job title and work email.";
        err.hidden = false; return;
      }
      const go_ = box.querySelector("#apGo");
      go_.disabled = true;
      const r = await post("/api/agency/member",
        { name: val("apName"), title: val("apTitle"), email: val("apEmail"),
          role: box.querySelector("#apRole").value });
      go_.disabled = false;
      if (!r || !r.ok) {
        err.textContent = (r && r.error) || "They could not be added.";
        err.hidden = false; box.querySelector("#apEmail").focus(); return;
      }
      const fresh = peoplePanel(r, agencyName);
      box.replaceWith(fresh);
      const note = fresh.querySelector("#apSaid");
      if (note) note.textContent = r.says || "Added.";
      const first = fresh.querySelector("#apName");
      if (first) first.focus();
    };
    box.querySelector("#apGo").onclick = submit;

    // Remove, or change a role — each confirmed first, because both take
    // effect at once.
    const after = (r, focusSel) => {
      const fresh = peoplePanel(r, agencyName);
      box.replaceWith(fresh);
      const note = fresh.querySelector("#peopleSaid");
      if (note) note.textContent = r.says || "Done.";
      const target = fresh.querySelector(focusSel) || fresh.querySelector("#peopleH");
      if (target) { if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1"); target.focus(); }
    };
    box.querySelectorAll("[data-remove]").forEach((b) => b.onclick = () => askConfirm({
      title: `Remove ${b.dataset.name}?`,
      body: `${b.dataset.name} comes off the organization and is signed out now. `
          + "Everything they recorded stays on the record with their name on it. "
          + "You can add them again later.",
      confirmLabel: "Remove them",
      onYes: async () => {
        const r = await post("/api/agency/member/remove", { email: b.dataset.remove });
        if (!r || !r.ok) { toast((r && r.error) || "That did not work.", true); return; }
        after(r, "#apName");
      },
    }));
    box.querySelectorAll("[data-role]").forEach((b) => b.onclick = () => {
      const toAdmin = b.dataset.role === "admin";
      askConfirm({
        title: toAdmin ? `Make ${b.dataset.name} an admin?` : `Make ${b.dataset.name} a member?`,
        body: toAdmin
          ? `${b.dataset.name} will be able to add people, make people admins, and take `
            + "people off this organization — including you."
          : `${b.dataset.name} will stay on the organization but will no longer be able `
            + "to add or remove people.",
        confirmLabel: toAdmin ? "Make admin" : "Make member",
        onYes: async () => {
          const r = await post("/api/agency/role", { email: b.dataset.email, role: b.dataset.role });
          if (!r || !r.ok) { toast((r && r.error) || "That did not work.", true); return; }
          after(r, "#peopleH");
        },
      });
    });
    ["apName", "apTitle", "apEmail"].forEach((id) => box.querySelector(`#${id}`).onkeydown = (e) => {
      if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); submit(); }
    });
  }
  return box;
}

const VIEW_FRAMEWORK = async () => {
  const f = S.framework || await api("/api/framework");
  S.framework = f;
  const root = el("div");

  /* The builder first, then the corpus status.

     This screen used to open on "four layers, here are the files present,
     record an adoption when it happens" — a status page. Useful once you have
     a framework; useless on the day you are writing one, which is the day
     almost every agency arrives on.

     So the click-through that actually writes the thing leads, and the layer
     inventory sits underneath it as reference. */
  if (window.renderBuilder) {
    try {
      await window.renderBuilder(root);
    } catch (e) {
      console.error("builder failed to render", e);
      root.appendChild(el("div", "panel",
        `<p class="intro">The framework builder could not load. The corpus
         status below still works.</p>`));
    }
  }

  const tone = { none: "bad", draft: "warn", adopted: "ok" }[f.state] || "warn";
  const head = el("div", "panel");
  head.innerHTML = `
    <div class="fw-head">
      <span class="pill ${tone}">${esc(f.state)}</span>
      <h2 class="sub3" style="margin:0">${esc(f.headline)}</h2>
    </div>
    <p class="intro">${esc(f.detail)}</p>`;
  root.appendChild(head);

  // What is present, and what each part is for. The "why" matters more than the
  // tick: someone missing a layer needs to know what it would have given them.
  const layers = el("div", "panel");
  layers.innerHTML = `<h2 class="sub3" style="margin-top:0">Reference documents</h2>
    <p class="intro">Each one is read by the one below it. That is the order they
      have to arrive in.</p>` +
    f.layers.map((ln) => `
      <div class="step-row">
        <span class="step-dot" style="background:var(--${
          ln.present ? "ok" : ln.required ? "alert" : "line"})"></span>
        <div class="step-main">
          <div class="step-name">${esc(ln.label)}
            ${ln.required ? "" : `<span class="small muted">optional</span>`}</div>
          <div class="step-why">${esc(ln.why)}</div>
          ${ln.files.length
            ? `<div class="small muted mono">${ln.files.map(esc).join(" · ")}</div>`
            : `<div class="small" style="color:var(--alert)">not loaded</div>`}
        </div>
      </div>`).join("");
  root.appendChild(layers);

  // Two honest routes in. Neither pretends the app can write the framework for
  // them — that is the agency's document to author and adopt.
  /* Start Here — the client's own words, used verbatim.

     What stood here explained the mechanics: which folder to drop Word files
     into, and that the SCDES regime is available as a worked reference. True,
     and the wrong first thing to say to a director who has just arrived. This
     says why any of it matters before it says how any of it works. */
  /* And it goes away once they have started.

     "Once framework created and I'm on the save a version, no reason to still
     have the Start Here section."

     Quite right. This is a pitch — why govern AI at all, what this site is
     for, click here to begin. It is the correct first thing to say to a
     director who has just arrived and dead weight to somebody on their
     fourth visit, sitting above their work and pushing it down the page
     every time they come back to it.

     Keyed on whether any question has been answered rather than on whether a
     version has been saved. He named the save-a-version screen because that
     is where he happened to be, but the pitch is stale from the first answer
     onwards — and somebody who has answered forty questions without saving
     is the last person who needs telling what the site is for. */
  const started = ((window.frameworkProgress
    && window.frameworkProgress()) || { done: 0 }).done > 0;
  const routes = started ? null : el("div", "panel fw-start");
  if (routes) routes.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Start Here</h2>
    <p class="intro">Artificial intelligence gives you and your staff powerful
      new tools for carrying out your mission; it is also a new class of asset,
      one your organization needs to govern deliberately. Governing it well
      comes down to three things: defining how AI may and may not be used in
      your organization; confirming that every use case satisfies the legal
      requirements that apply to you, from your own policies to state and
      federal law; and establishing one clear process that every AI project
      moves through, so that adoption stays consistent, repeatable, and
      responsible.</p>
    <p class="intro">GoverningAI.us exists to make that achievable. Our AI
      governance framework creator module is available at no cost to every
      governmental unit in the United States, giving you a standardized,
      defensible way to stand up AI governance so you can deploy these
      capabilities faster, with less risk and greater public trust.</p>
    <p class="intro">To begin, please click <b>Start Here</b>.</p>
    <div class="row" style="margin-top:16px">
      <button class="btn btn-lg" id="fwBegin" type="button">Start Here</button>
    </div>`;
  if (routes) root.appendChild(routes);

  /* Recording the adoption.

     Gated on the framework being finished, per the client: "Record the adoption
     should be gated: available after framework completion." Offering it earlier
     invites someone to adopt a document that is mostly unanswered — and the
     DRAFT stamp exists precisely to stop that being possible by accident.

     Note also "it's not up to the Council unless the framework establishes":
     who may record it comes from the agency's own answer about who decides, not
     from an assumption made here. */
  const adopt = el("div", "panel");
  if (f.state === "adopted") {
    adopt.innerHTML = `<h2 class="sub3" style="margin-top:0">Adoption on record</h2>
      <p class="intro">Recorded as adopted on <b>${esc(f.adopted_on)}</b>${
        f.adopted_by ? ` by ${esc(f.adopted_by)}` : ""}.
        ${f.adopted_note ? esc(f.adopted_note) : ""}</p>
      <p class="small muted">This is the application's record of being told. It
        does not verify that the adoption happened — the evidence for that is the
        signed charter in the corpus.</p>`;
  } else {
    /* Both answers come from the server, which applies the same rule as the
       endpoint. This used to read the capacity name — "council-member" — and
       nobody who signs in holds that capacity, so the button was never drawn,
       and the sentence underneath sent people to a capacity switcher in the
       header that had already been removed. */
    const can = !!f.can_record_adoption;
    // The questions that decide policy — not the optional ones, and not the
    // two about how the document reads.
    const done = f.policy_answered || 0, total = f.policy_total || 0;
    const open = Math.max(total - done, 0);
    const finished = total > 0 && open === 0;
    // IIA's own test container only, for the GAIUS team. See
    // `_may_record_incomplete` in app/server.py.
    const demoException = !finished && can && f.can_record_incomplete;

    const form = `
        <div class="row" style="margin-top:10px">
          <label class="small" for="fwDate">Adopted on</label>
          <input id="fwDate" type="date" value="${localToday()}">
          <label class="small" for="fwNote">Minute reference (optional)</label>
          <input id="fwNote" type="text" style="flex:1;min-width:200px">
          <button class="btn" id="fwAdopt" type="button">Record adoption</button>
        </div>
        <p class="small muted" style="margin-top:8px">Audited, and attributed to
          you by name and title. This records that you told the application
          the framework was adopted; it cannot see the vote or the signature
          itself.</p>`;

    adopt.innerHTML = `<h2 class="sub3" style="margin-top:0">Record the adoption</h2>
      <p class="intro">Writing a framework is not adopting one. When whoever
        holds the authority adopts what you have written, record it here — every
        screen then stops calling it provisional.</p>
      ${demoException ? `
        <div class="locked" style="margin-top:10px">
          <b>${open} question${open === 1 ? "" : "s"} that decide policy
          ${open === 1 ? "is" : "are"} still unanswered.</b>
          This is IIA's own test container, so the adoption can be recorded
          anyway to show the adopted state. The open questions will print in
          the document as matters not yet settled. For any real organization
          this stays shut until the framework is complete.
        </div>${form}`
      : !finished ? `
        <div class="locked" style="margin-top:10px">
          <b>Available after the framework is complete.</b>
          ${total
            ? `${done} of ${total} questions that decide policy are answered so far.`
            : "Nothing has been answered yet."}
          Adopting a document that is mostly unanswered is the one thing the
          DRAFT stamp exists to prevent, so this stays shut until it is
          finished.
        </div>` : can ? form
        : `<div class="locked" style="margin-top:10px">
            <b>Recording the adoption needs a verified member of this
            organization.</b> Sign in with the address this organization was
            registered under, and it will be available here.</div>`}`;
  }
  root.appendChild(adopt);

  // What depends on it — the argument for the gate, made concrete.
  const deps = el("div", "panel");
  /* What the framework unlocks, and what that costs.

     This was a plain table of dependencies, which read as a list of screens
     already included. They are not: the framework is the free offering and
     everything that reads from it — the workflow management and the system of
     record — is the paid addition. So the list is shown dimmed with the ask
     attached, rather than promising rooms that will not open. */
  deps.className = "panel fw-deps";
  deps.innerHTML = `
    <h2 class="sub3" style="margin-top:0">What your framework unlocks</h2>
    <p class="intro">Everything below is read out of the framework you are
      writing. They are part of the workflow management and system of record —
      a paid addition to the free framework module.</p>
    <table class="fw-locked-table"><tbody>${f.dependents.map((d) => `
      <tr><td style="width:130px"><b>${esc(d.screen)}</b></td>
          <td>${esc(d.needs)}</td>
          <td style="width:20px" aria-hidden="true">🔒</td></tr>`).join("")}</tbody></table>
    <p class="small muted" style="margin-top:12px">Subscribe to access the
      workflow management and system of record. Your framework, and everything
      you write into it, stays yours either way.</p>`;
  root.appendChild(deps);

  $("#view").innerHTML = ""; $("#view").appendChild(root);

  // Start Here scrolls to the first section rather than navigating: the builder
  // is already on this page, and a button that appears to go somewhere and then
  // stays put is worse than one that visibly moves you down it.
  const begin = $("#fwBegin");
  if (begin) begin.onclick = () => {
    const first = document.querySelector(".fb-section:not(:disabled)");
    if (first) {
      first.scrollIntoView({ behavior: "smooth", block: "center" });
      first.focus();
    }
  };

  const btn = $("#fwAdopt");
  if (btn) btn.onclick = async () => {
    btn.disabled = true;
    const r = await api("/api/framework/adopt", {
      method: "POST",
      body: JSON.stringify({ adopted_on: $("#fwDate").value,
                             note: $("#fwNote").value }),
    });
    btn.disabled = false;
    if (r.ok) { toast("Adoption recorded."); await refreshFramework(); go("framework"); }
    else toast(r.error || "Could not record the adoption.");
  };

  reason([
    { title: "Why this comes first",
      body: "Every parameter, gate, category and citation in this application is read out of the adopted framework. It is not a settings screen — it is the source the rest of the software reads.",
      cite: "SCDES AI Governance Framework §1 (Purpose and Authority)" },
    { title: "Loaded is not adopted",
      body: "The application can read a draft so it can be reviewed. It marks it provisional until a body with authority adopts it, because a document in a folder carries no authority on its own.",
      cite: "Appendix N — Framework and Appendix Amendments" },
  ]);
};

/** A locked screen explains the gate rather than showing an empty table. */
/* Whether a view is behind the subscription.

   Read off the rail markup rather than kept as a second list here. The rail is
   where a human decides what is free and what is not; a duplicate set in
   JavaScript is a thing that drifts, and the direction it drifts in is a paid
   screen quietly becoming reachable.

   `paintFrameworkState` greys the rail button, but that only guards one way in.
   The project spine navigates to Lifecycle and Registry too, and it was walking
   straight past the lock — clicking a gate pip opened a screen the sidebar next
   to it said was unavailable. */
function viewIsPaid(view) {
  const item = document.querySelector(`.rail-item[data-view="${view}"]`);
  return !!(item && item.dataset.paid === "1");
}

/* The server's answer, and only the server's.
 *
 * This added `|| S.state.tester`, and the server's `_subscribed()` never did
 * — so on a deployment without the evaluation switch a tester saw every paid
 * module unlocked in the rail, opened one, and was refused by the endpoint
 * behind it. The tester arrangement skips the approval queue and nothing
 * else (see `tenancy.is_tester`); a tester's organization is subscribed the
 * same way anybody's is, which the Subscriptions admin screen now makes
 * possible. */
function subscribed() {
  return !!(S.state && S.state.subscription);
}

function subscriptionPanel(view) {
  const root = el("div", "panel");
  const [title, sub] = META[view] || [view, ""];
  root.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${esc(title)} is a paid addition</h2>
    <p class="intro">${esc(sub)}</p>
    <p class="intro">Building and adopting your governance framework is the
      free offering, and it is complete on its own — the framework is the
      document your agency adopts and publishes. ${esc(title)} is part of the
      workflow management that runs <em>on top of</em> an adopted framework:
      the playbook, the appendices, and the tracking of real systems through
      the gates.</p>
    <p class="small muted">Nothing here is withheld from work you have already
      done. Everything you answer in the Framework stays yours, exports as a
      draft, and is unaffected by this.</p>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="paidBack" type="button">Back to the Framework</button>
    </div>`;
  return root;
}

function frameworkGatePanel(view) {
  const f = S.framework || {};
  const root = el("div", "panel");
  root.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${esc(META[view] ? META[view][0] : view)}
      needs the framework first</h2>
    <p class="intro">${esc((f.dependents || []).find((d) =>
        d.screen.toLowerCase() === (META[view] ? META[view][0].toLowerCase() : ""))
        ?.needs || "This screen is read out of the adopted framework.")}</p>
    <p class="intro">None of that exists yet, so this screen would be showing
      structure your agency has not agreed to. That is worse than showing
      nothing.</p>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="gateGo" type="button">Set up the framework</button>
      <button class="btn ghost" id="gateWhy" type="button">Watch the 60-second intro</button>
    </div>`;
  return root;
}

/** Abbreviation of the agency whose corpus is actually on disk. */
function loadedAgencyName() {
  const reg = window.LNCH_DATA;
  if (!reg) return null;
  const hit = reg.states.find((s) => s.code === reg.loaded);
  return hit ? hit.abbrev : null;
}

function noCorpusPanel() {
  /* Says what THIS agency is missing, and names no other.

     It used to explain that the loaded records "belong to South Carolina
     Department of Environmental Services" and offer a button to open them.
     Accurate, and precisely the thing an agency must never be shown — the
     client's rule is that the process never references or gives access to
     another agency. Telling someone whose documents they are not looking at,
     and offering to show them, breaks it twice. */
  const a = window.SCDES_AGENCY || {};
  const root = el("div", "panel empty-agency");
  root.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Nothing here yet for ${
      esc(a.abbrev || "your agency")}</h2>
    <p class="intro">This screen reads from your agency's own adopted documents,
      and none have been loaded. It stays empty rather than filling itself from
      somewhere else — a register showing records that are not yours would be
      worse than a blank one.</p>
    <p class="intro">Start with the Framework. Everything on this screen — the
      registry, the lifecycle, the budget, the vocabulary and every citation —
      is read out of it once it exists.</p>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="emptyBuild" type="button">Build the framework</button>
    </div>
    <p class="small muted" style="margin-top:12px">Working on a different
      governmental unit? Sign out and register it separately. An agency's
      records are only reachable from inside that agency.</p>`;
  return root;
}

/* Screens whose content is a table rather than something to read.
   Everything else is capped to one reading measure — see `--measure` in
   app.css, and tools/check_measure.js for why. */
const WIDE_VIEWS = new Set(["holdings", "vendors", "registry", "audit",
                            "budget", "oversight", "bugs",
                            // Eight columns of people and eight of agencies.
                            "usage"]);

function go(view) {
  S.view = view;
  if (window.bugNoteView) window.bugNoteView(view);
  $("#view").classList.toggle("wide", WIDE_VIEWS.has(view));
  // The spine's selection depends on which view is open, so it is repainted
  // here rather than only where a gate is clicked — the rail, the registry and
  // the back button all reach Lifecycle too.
  paintSpineSelection();
  // Only items that name a view can be the current one. Matching on the whole
  // rail meant "Choose agency" — which has no data-view — went active whenever
  // `view` was undefined, marking the front door as the page you are on.
  document.querySelectorAll(".rail-item[data-view]").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === view));
  const [t, s] = META[view] || ["", ""];
  $("#viewTitle").textContent = t; $("#viewSub").textContent = s;

  // The framework gate comes before the corpus gate: without a framework there
  // is no structure to show, whichever agency is selected.
  const testerSession = !!(S.state && S.state.tester);
  if (!testerSession && !frameworkReady() && !FRAMEWORK_EXEMPT.has(view)) {
    // `$("#spine").hidden = true` stood here, and in the two gates below.
    // The strip it hid was retired and its markup came out of index.html,
    // so all three were dereferencing null — which meant every one of these
    // three locked screens threw instead of rendering its explanation. A
    // person without a framework got a blank panel where the sentence
    // telling them to go and build one should have been.
    $("#view").innerHTML = "";
    $("#view").appendChild(frameworkGatePanel(view));
    $("#gateGo").onclick = () => go("framework");
    $("#gateWhy").onclick = () => window.replayWelcome && window.replayWelcome();
    reason([{ title: "Why this is closed",
      body: "You cannot have a process without a framework. The gates, categories and thresholds this screen would show are all read out of the framework — there is nothing to read yet.",
      cite: "Framework §1 (Purpose and Authority)" }]);
    return;
  }

  // Checked after the framework gate and before the corpus gate. Order matters:
  // "you have not built a framework yet" is more useful than "this costs money"
  // to someone who has neither.
  if (viewIsPaid(view) && !subscribed()) {
    $("#view").innerHTML = "";
    $("#view").appendChild(subscriptionPanel(view));
    const back = $("#paidBack");
    if (back) back.onclick = () => go("framework");
    reason([{ title: "Where the line is drawn",
      body: "The governance framework is the free offering — authoring it, versioning it, and adopting it. The playbook, the appendices and the workflow management that tracks real systems through the gates are a paid addition.",
      cite: "IIA — Innovative Infrastructure Advising" }]);
    return;
  }

  /* The corpus gate, with the same exemptions as the framework gate.

     It had none, so tightening `agencyHasCorpus()` to fail closed shut the
     Framework screen too — and Framework is how an agency gets a corpus in the
     first place. A door that locks the room containing its own key. */
  if (!CORPUS_EXEMPT.has(view) && !agencyHasCorpus()) {
    $("#view").innerHTML = "";
    $("#view").appendChild(noCorpusPanel());
    $("#emptyBuild").onclick = () => go("framework");
    reason([{ title: "Why this is empty",
      body: "The application holds one corpus at a time. Every figure on every screen traces to a document in it, so an agency without one has nothing to show — and borrowing another agency's records would break the only guarantee this tool makes.",
      cite: "README — theming across fifty agencies" }]);
    return;
  }

  $("#view").innerHTML = `<p class="muted">Loading…</p>`;
  // Returned so a caller can wait for the render — the tab set moves focus
  // onto the tab that was chosen once its panel exists.
  return (VIEWS[view] || VIEWS.vision)();
}

// Re-render when the agency changes, so switching states on the map takes effect
// immediately. Guarded on S.state: the launcher makes its first selection during
// boot, before /api/state has returned, and the views cannot render without it.
document.addEventListener("agencychange", () => {
  if (!S.state) return;
  // The spine is agency-scoped too — it names a project from the loaded
  // corpus. It was drawn only by refreshState(), so changing agency re-rendered
  // the view while leaving the previous agency's project sitting above it.
  renderSpine();
  if (S.view) go(S.view);
});

/* --------------------------------------------------------------- palette */

function openPalette() {
  $("#palette").hidden = false;
  $("#paletteInput").value = "";
  $("#paletteOut").innerHTML = "";
  $("#paletteInput").focus();
}
const closePalette = () => ($("#palette").hidden = true);

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault(); openPalette();
  } else if (e.key === "Escape") closePalette();
});
$("#cmdkBtn").onclick = openPalette;
$("#paletteClose").onclick = closePalette;
$("#palette").addEventListener("click", (e) => {
  if (e.target.id === "palette") closePalette();
});
$("#paletteInput").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  const msg = e.target.value.trim();
  if (!msg) return;
  $("#paletteOut").innerHTML = `<div class="answer"><p class="muted">Searching…</p></div>`;
  const r = await post("/api/chat", { message: msg });
  renderAnswer(r);
});

function renderAnswer(r) {
  const label = { query: "Cited answer", scenario: "What-if · nothing changed",
    intake: "Draft project · not on the record" }[r.mode] || r.mode;
  const box = el("div", "answer");
  box.innerHTML =
    `<div class="amode">${esc(label)} · ${esc(r.provider)}</div>` +
    `<p>${esc(r.answer)}</p>` +
    (r.citations && r.citations.length
      ? `<div class="cites">` + r.citations.slice(0, 4).map((c) =>
          `<div class="cite"><b>[${c.n}] ${esc(c.citation)}</b>${esc((c.snippet || "").slice(0, 190))}…</div>`
        ).join("") + `</div>` : "") +
    // "local" is the server searching this organization's own uploads — every
    // organization except the one the reference documents belong to.
    `<div class="foot">${r.provider === "local"
      ? "Searched your organization's own documents only. Nothing was written."
      : r.mode === "query"
      ? "Answered from the governed corpus. Nothing was written."
      : "Computed live. The record of authority is unchanged."}</div>`;
  $("#paletteOut").innerHTML = ""; $("#paletteOut").appendChild(box);

  if (r.citations && r.citations.length)
    reason(r.citations.slice(0, 3).map((c) =>
      ({ title: c.citation, quote: (c.snippet || "").slice(0, 240) })));
}

/* ----------------------------------------------------------------- views */

const VIEWS = {};

// Registered here rather than defined inline, because the gate in go() refers to
// it and it must exist before the first navigation.
VIEWS.framework = VIEW_FRAMEWORK;
VIEWS.home = VIEW_HOME;

/* Vision — where you are trying to get to. One entry per goal. Replaces the
   reference agency's strategic map, pillars and maturity table. Nothing here
   is a progress figure: a goal is reached when a person says it is. */
const VS = { said: "", candidates: [] };

VIEWS.vision = async () => {
  const d = await api("/api/goals");
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    const p = el("div", "panel");
    p.innerHTML = `<p class="intro">${esc(d.why || "This is part of the subscription.")}</p>`;
    $("#view").appendChild(p);
    return;
  }
  const inp = d.inputs || {};
  const byRef = Object.fromEntries((d.goals || []).map((g) => [g.ref, g]));
  const portfolio = Object.fromEntries((d.goals || []).map((g, i) => [g.ref, (d.portfolio || [])[i] || {}]));
  const root = el("div");
  const live = el("p", "vh"); live.setAttribute("aria-live", "polite");
  root.appendChild(live);

  // Upload a planning document first, where they have one.
  const head = el("section", "panel");
  head.setAttribute("aria-labelledby", "vsHeadH");
  head.innerHTML = `
    <h2 class="sub3" id="vsHeadH" style="margin-top:0">Where you are trying to get to</h2>
    <p class="intro">One entry per goal — what this organization wants to be true a year from
      now and five years from now, and what each project is doing about it.</p>
    <p class="small"><a href="#vsFindings">Skip to the findings</a> · <a href="#vsList">Skip to the goals</a></p>
    ${/* Brett, BUG-BE30FBD3: Vision is part of the framework. What it asks
         at 11.1a and 11.1b is offered here first, horizon already set. */ ""}
    <div id="vsFromFramework" role="group" aria-labelledby="vsFwH">
      <h3 class="sub4" id="vsFwH">From your framework</h3>
      ${(d.from_framework || []).length ? `<p class="small">${esc(d.from_framework_says)}</p>
        <ul class="vr-flags">${d.from_framework.map((c, i) => `<li>${esc(c.goal)}
          <span class="muted">${esc(c.horizon)} · ${esc(c.from)}</span>
          <button type="button" class="btn ghost" data-vs-fw="${i}"
            aria-label="Use this one: ${esc(c.goal)}">Use this one</button></li>`).join("")}</ul>
        <p><button type="button" class="btn ghost" id="vsFwAll">Add all ${d.from_framework.length} as goals</button></p>`
      : `<p class="small muted">Framework questions 11.1a and 11.1b ask what you want AI to help
          you achieve within a year and within five years. Whatever you answer there is offered here,
          ready to add.</p>
          <p><button type="button" class="btn ghost" id="vsToFw">Open the framework</button></p>`}
    </div>
    <div class="vr-field"><label for="vs-doc">${esc(d.upload_first)}</label>
      <input type="file" id="vs-doc" accept=".docx,.pdf,.txt,.md" aria-describedby="vs-doc-help">
      <p class="small muted" id="vs-doc-help">Read here and then discarded. Nothing from it is kept until you add a goal.</p></div>
    <p><button type="button" class="btn ghost" id="vsRead">Read it</button>
      <span class="small" role="alert" id="vsReadErr"></span></p>
    <div id="vsCandidates"></div>
    <p><button type="button" class="btn" id="vsNew">Write down a goal</button></p>`;
  root.appendChild(head);

  // §2 · the stat row.
  const c = d.counters || {};
  const stats = el("section", "panel");
  stats.setAttribute("aria-label", "Counts");
  stats.innerHTML = `<div class="vr-tiles">${[[c.recorded, "Goals recorded"],
      [c.being_worked_on, "Being worked on"], [c.nothing_against_them, "Nothing against them"],
      [c.serving_no_goal, "Projects serving no goal"], [c.closed, "Reached, or no longer wanted"]]
      .map(([n, l]) => `<div class="vr-tile"><b>${n || 0}</b><span>${esc(l)}</span></div>`).join("")}</div>
    <p class="small muted" style="margin:8px 0 0">${esc(c.two_halves)}</p>`;
  root.appendChild(stats);

  // Proposals waiting for whoever decides.
  const props = d.proposals || [];
  if (props.length) {
    const pp = el("section", "panel");
    pp.setAttribute("aria-labelledby", "vsPropH");
    pp.innerHTML = `<h2 class="sub3" id="vsPropH" style="margin-top:0">${props.length} proposed change${props.length === 1 ? "" : "s"}, waiting for whoever decides</h2>
      <ul class="vr-flags">${props.map((p) => `<li><b>${esc((byRef[p.goal_ref] || {}).goal || "")}</b>
        ${p.goal ? `Reword to “${esc(p.goal)}”.` : ""} ${p.horizon ? `By: ${esc(p.horizon)}.` : ""} ${p.stands ? `Mark as: ${esc(p.stands)}.` : ""}
        <span class="muted">Proposed by ${esc(p.by)}</span>
        ${d.decides ? `<span class="row" style="gap:8px;margin-top:6px">
          <button type="button" class="btn ghost" data-vs-settle="${p.index}" data-accept="1">Accept</button>
          <button type="button" class="btn ghost" data-vs-settle="${p.index}" data-accept="">Decline</button></span>` : ""}</li>`).join("")}</ul>`;
    pp.querySelectorAll("[data-vs-settle]").forEach((b) => b.onclick = async () => {
      const out = await post("/api/goals/settle", { index: Number(b.dataset.vsSettle), accept: !!b.dataset.accept });
      if (out && out.ok) { VS.said = b.dataset.accept ? "Accepted." : "Declined. Recorded without comment."; go("vision"); }
    });
    root.appendChild(pp);
  }

  // §3 · findings.
  const raised = d.raised || [];
  const f = el("section", "panel");
  f.id = "vsFindings";
  f.setAttribute("aria-labelledby", "vsFindingsH");
  f.innerHTML = `<h2 class="sub3" id="vsFindingsH" style="margin-top:0">${raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"}` : "Nothing to flag"}</h2>
    ${raised.length ? `<ul class="vr-flags">${raised.map((x) => `<li>${byRef[x.entry]
      ? `<b>${esc(byRef[x.entry].goal)}</b> ` : ""}${esc(x.says)}</li>`).join("")}</ul>`
      : `<p class="intro">${esc(d.clean_state)}</p>`}`;
  root.appendChild(f);

  // §4 · the goals, grouped by horizon, with §6 · the portfolio under each.
  const list = el("section", "panel");
  list.id = "vsList";
  list.setAttribute("aria-labelledby", "vsListH");
  list.innerHTML = `<h2 class="sub3" id="vsListH" style="margin-top:0">The goals</h2>
    <p class="small muted">${esc(d.no_progress_figure)} ${esc(d.history_stays)}</p>
    ${(d.grouped || []).length ? d.grouped.map((g) => `<section class="vs-group" aria-labelledby="vsG-${esc(g.horizon).replace(/\W/g, "")}">
      <h3 class="sub3" id="vsG-${esc(g.horizon).replace(/\W/g, "")}">${esc(g.heading)}</h3>
      ${g.goals.map((goal) => { const pf = portfolio[goal.ref] || {};
        return `<article class="vr-tell" aria-label="${esc(goal.goal)}">
          <p style="margin:0"><b>${esc(goal.goal)}</b> <span class="small muted">· ${esc(goal.stands)}${goal.owner ? ` · owned by ${esc(goal.owner)}` : ""}</span></p>
          ${goal.would_be_true ? `<p class="small">What would have to be true: ${esc(goal.would_be_true)}</p>` : ""}
          <p class="small">${esc(pf.summary || "")}</p>
          ${(pf.lines || []).length ? `<ul class="small">${pf.lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}
          <p><button type="button" class="btn ghost" data-vs-edit="${esc(goal.ref)}">Edit</button></p></article>`;
      }).join("")}</section>`).join("")
      : `<p class="intro" style="white-space:pre-line">${esc(d.empty_state)}</p>`}`;
  root.appendChild(list);

  // Naming a goal on a project — anybody may. The tie is written on the
  // project, and a goal never claims a project.
  if ((d.projects || []).length && (d.goals || []).length) {
    const tie = el("section", "panel");
    tie.setAttribute("aria-labelledby", "vsTieH");
    tie.innerHTML = `<h2 class="sub3" id="vsTieH" style="margin-top:0">Which goal each project serves</h2>
      <p class="small muted">Written on the project. A project names at most one goal, or none and says so.
        ${inp.mission_tie ? "You said every tool has to serve one of your goals." : ""}</p>
      <table class="vr-table"><caption class="vh">Projects and the goal each serves</caption>
      <thead><tr><th scope="col">Project</th><th scope="col">The goal it serves</th></tr></thead>
      <tbody>${d.projects.map((p) => `<tr><th scope="row">${esc(p.name)}</th><td>
        <label class="vh" for="vs-tie-${esc(p.ref)}">The goal ${esc(p.name)} serves</label>
        <select id="vs-tie-${esc(p.ref)}" data-vs-tie="${esc(p.ref)}"><option value="">It names no goal</option>
        ${d.goals.map((g) => `<option value="${esc(g.ref)}"${p.goal === g.ref ? " selected" : ""}>${esc(g.goal)}</option>`).join("")}</select></td></tr>`).join("")}</tbody></table>`;
    tie.querySelectorAll("[data-vs-tie]").forEach((s) => s.onchange = async () => {
      const out = await post("/api/projects/goal", { ref: s.dataset.vsTie, goal: s.value });
      if (out && out.ok) { VS.said = "Recorded on the project."; go("vision"); }
    });
    root.appendChild(tie);
  }

  // §7 · the public view.
  const pv = d.public_view || {};
  const pub = el("section", "panel");
  pub.setAttribute("aria-labelledby", "vsPubH");
  pub.innerHTML = `<h2 class="sub3" id="vsPubH" style="margin-top:0">What you publish about this</h2>
    <p class="small">${inp.publishes_words ? `You said you publish ${esc(inp.publishes_words.toLowerCase())}.`
      : inp.publishes_nothing ? "You said you publish nothing about this. That is recorded. You can change it here." : ""}</p>
    ${igRadios("vs-publishes", "Do you publish anything about this?", ["Yes", "No", "Not decided"],
      pv.publishes || (inp.publishes_words ? "Yes" : inp.publishes_nothing ? "No" : "Not decided"))}
    <fieldset class="vr-tri"><legend>What appears publicly</legend>
      ${["The goal", "What would have to be true", "What you are running against it", "How to reach a person", "Nothing"]
        .map((a) => `<label><input type="checkbox" name="vs-appears" value="${esc(a)}"${(pv.appears || []).includes(a) ? " checked" : ""}> ${esc(a)}</label>`).join("")}</fieldset>
    ${igText("vs-where", "Where it appears", "A page, a report, a meeting packet.", { value: pv.where || "" })}
    ${igText("vs-approver", "Who approves the wording", inp.no_comms ? "You recorded no public information function, so this sits with whoever holds that hat." : "", { value: pv.approver || "" })}
    ${inp.publishes_yearly ? igText("vs-last", "When the last yearly report went out", "", { type: "date", value: pv.last_published || "" }) : ""}
    <p class="small muted">${esc(d.publishes_nothing)}</p>
    <p><button type="button" class="btn ghost" id="vsPubSave">${d.decides ? "Keep this" : "Propose this"}</button>
      <span class="small" role="alert" id="vsPubErr"></span></p>`;
  pub.querySelector("#vsPubSave").onclick = async () => {
    const out = await post("/api/goals/public", {
      publishes: igPicked(pub, "vs-publishes"),
      appears: [...pub.querySelectorAll('[name="vs-appears"]:checked')].map((c) => c.value),
      where: igVal(pub, "vs-where"), approver: igVal(pub, "vs-approver"),
      last_published: igVal(pub, "vs-last") });
    if (out && out.ok) { VS.said = "Kept."; go("vision"); }
    else pub.querySelector("#vsPubErr").textContent = (out && out.error) || "";
  };
  root.appendChild(pub);

  const scope = el("div", "panel");
  scope.innerHTML = (d.what_it_is_not || []).map((s) => `<p class="small">${esc(s)}</p>`).join("");
  root.appendChild(scope);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  live.textContent = VS.said || (d.grouped || []).map((g) => g.heading).join(". ");
  VS.said = "";

  const open = (goal, preset) => {
    const old = $("#vsForm"); if (old) old.remove();
    const host = el("section", "panel");
    host.id = "vsForm";
    head.after(host);
    goalForm(host, d, goal, preset);
    const h = host.querySelector("h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  };
  $("#vsNew").onclick = () => open(null, null);
  $("#view").querySelectorAll("[data-vs-edit]").forEach((b) => b.onclick = () => open(byRef[b.dataset.vsEdit], null));
  const fw = d.from_framework || [];
  $("#view").querySelectorAll("[data-vs-fw]").forEach((b) => b.onclick = () => open(null, fw[Number(b.dataset.vsFw)]));
  const toFw = $("#vsToFw");
  if (toFw) toFw.onclick = () => go("framework");
  const fwAll = $("#vsFwAll");
  if (fwAll) fwAll.onclick = async () => {
    fwAll.disabled = true;
    let added = 0;
    for (const c of fw) {
      const out = await post("/api/goals", { goal: c.goal, horizon: c.horizon });
      if (out && out.ok) added += 1;
    }
    VS.said = `${added} goal${added === 1 ? "" : "s"} added from your framework.`;
    go("vision");
  };

  const drawCandidates = () => {
    const host = $("#vsCandidates");
    if (!VS.candidates.length) { host.innerHTML = ""; return; }
    host.innerHTML = `<p class="small">${esc(d.read_from_document)}</p>
      <ul class="vr-flags">${VS.candidates.map((c, i) => `<li>${esc(c.goal)} <span class="muted">${esc(c.horizon)}</span>
        <button type="button" class="btn ghost" data-vs-use="${i}">Use this one</button></li>`).join("")}</ul>`;
    host.querySelectorAll("[data-vs-use]").forEach((b) => b.onclick = () => open(null, VS.candidates[Number(b.dataset.vsUse)]));
  };
  drawCandidates();
  $("#vsRead").onclick = async () => {
    const file = ($("#vs-doc").files || [])[0];
    const err = $("#vsReadErr"); err.textContent = "";
    if (!file) { err.textContent = "Choose a file first."; $("#vs-doc").focus(); return; }
    const content = await new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).split(",").pop());
      r.readAsDataURL(file);
    });
    const out = await post("/api/goals/read", { filename: file.name, content });
    if (!out || !out.ok) { err.textContent = (out && out.error) || "That could not be read."; return; }
    VS.candidates = out.candidates || [];
    err.textContent = out.says || "";
    drawCandidates();
  };
};

/* §5 · the form. Only the goal itself is required. */
function goalForm(host, d, goal, preset) {
  const inp = d.inputs || {};
  const g = { ...(goal || {}), ...(preset || {}) };
  const settles = !goal || d.decides;
  host.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${goal ? "Change this goal" : "Write down a goal"}</h2>
    <p class="intro">${esc(d.only_the_goal)}${goal && !d.decides ? " A change to the wording, the horizon or where it stands is recorded as a proposal for whoever decides." : ""}</p>
    ${igText("vs-goal", "The goal", `In your own words, the way you would say it out loud. One sentence.${d.placeholder ? ` For example: “${d.placeholder}”.` : ""}`, { value: g.goal || "" })}
    ${igRadios("vs-horizon", "By when", d.horizons, g.horizon || "")}
    ${igText("vs-true", "What would have to be true", "How you would know you had got there. This is not a measurement of any one tool — it is the state of the world you are aiming at.", { long: true, value: g.would_be_true || "" })}
    <div class="vr-field"><label for="vs-owner">Who owns it</label>
      <p class="small muted vr-help" id="vs-owner-help">A role. The person who would be asked about this at a board meeting.</p>
      <input id="vs-owner" list="vs-owner-list" aria-describedby="vs-owner-help" value="${esc(g.owner || "")}">
      <datalist id="vs-owner-list">${(inp.owners || []).map((o) => `<option value="${esc(o)}">`).join("")}</datalist></div>
    ${inp.small && !goal ? `<label class="small"><input type="checkbox" id="vs-fold"> The person who decides owns this too — in an organization your size one person commonly holds both.</label>` : ""}
    ${igText("vs-resp", "Which of your responsibilities this serves (optional)", "The program, the service, or the duty. If the honest answer is that it frees up staff time for something else, write that.", { long: true, value: g.responsibilities || "" })}
    ${goal ? igRadios("vs-stands", "Where it stands", d.standings, g.stands || "Open", "A goal is reached when a person says it is, not when a number crosses a line.") : ""}
    <p class="small" id="vs-err" role="alert"></p>
    <p><button type="button" class="btn" id="vs-save">${goal ? (settles ? "Save it" : "Save, and propose the rest") : "Add it"}</button>
      <button type="button" class="btn ghost" id="vs-cancel">Cancel</button></p>`;
  const $$ = (s) => host.querySelector(s);
  $$("#vs-cancel").onclick = () => { host.remove(); $("#vsNew").focus(); };
  $$("#vs-save").onclick = async () => {
    const err = $$("#vs-err"); err.textContent = "";
    const text = igVal(host, "vs-goal");
    if (!text) { err.textContent = "Write down the goal."; $$("#vs-goal").focus(); return; }
    const out = await post("/api/goals", {
      ref: goal ? goal.ref : "", goal: text, horizon: igPicked(host, "vs-horizon"),
      would_be_true: igVal(host, "vs-true"), owner: igVal(host, "vs-owner"),
      responsibilities: igVal(host, "vs-resp"), stands: igPicked(host, "vs-stands"),
      owner_is_also_decider: !!($$("#vs-fold") && $$("#vs-fold").checked) });
    if (!out || !out.ok) { err.textContent = (out && out.error) || "That did not save."; return; }
    VS.said = out.proposed ? "Saved. The change to the wording is recorded as a proposal." : goal ? "Saved." : "Written down.";
    if (preset) VS.candidates = VS.candidates.filter((c) => c !== preset);
    go("vision");
  };
}

/* Registry — what is out there, and what you already have. One entry per
   tool. Replaces the reference agency's systems register (its appendix
   scores and risk bands); what this organization runs is Projects. */
const RG = { q: "", unit: "", said: "", sort: "held" };

VIEWS.registry = async () => {
  const qs = new URLSearchParams({ q: RG.q, unit: RG.unit }).toString();
  const d = await api(`/api/catalog?${qs}`);
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    const p = el("div", "panel");
    p.innerHTML = `<p class="intro">${esc(d.why || "This is part of the subscription.")}</p>`;
    $("#view").appendChild(p);
    return;
  }
  const inp = d.inputs || {}, rb = inp.readbacks || {};
  const byRef = Object.fromEntries((d.tools || []).map((t) => [t.ref, t]));
  const root = el("div");
  const live = el("p", "vh"); live.setAttribute("aria-live", "polite");
  root.appendChild(live);

  // §2 · the search, in hierarchy order. Built first, because this is what
  // the surface is for.
  const find = el("section", "panel");
  find.setAttribute("aria-labelledby", "rgFindH");
  find.innerHTML = `
    <h2 class="sub3" id="rgFindH" style="margin-top:0">Is there already something that does this?</h2>
    <p class="intro">One entry per tool — what it does, who sells it, and which parts
      of your organization already hold it.${rb.check_first ? ` ${esc(rb.check_first)}` : ""}</p>
    <p class="small"><a href="#rgFindings">Skip to the findings</a> · <a href="#rgList">Skip to the catalog</a></p>
    <form id="rgSearch" class="row" style="gap:12px;align-items:flex-end;flex-wrap:wrap">
      <label class="vr-field" style="flex:2 1 260px;margin:0">What do you need it to do?
        <input id="rg-q" value="${esc(RG.q)}" placeholder="${esc(inp.example ? `Something for ${inp.example}` : "")}"></label>
      ${d.one_unit ? "" : `<label class="vr-field" style="flex:1 1 180px;margin:0">Your unit
        <input id="rg-unit" list="rg-units" value="${esc(RG.unit)}">
        <datalist id="rg-units">${(d.units || []).map((u) => `<option value="${esc(u)}">`).join("")}</datalist></label>`}
      <button type="submit" class="btn">Search</button></form>
    <p class="small muted">${esc(d.never_recommends)}</p>
    ${(d.bands || []).map((b) => `<section class="rg-band" aria-labelledby="rgBand-${b.step}">
      <h3 class="sub3" id="rgBand-${b.step}">${esc(b.band)} <span class="small muted">· ${b.tools.length} result${b.tools.length === 1 ? "" : "s"}</span></h3>
      ${b.band === "Available on an agreement you could use" && rb.agreements ? `<p class="small muted">${esc(rb.agreements)}</p>` : ""}
      ${b.tools.length ? `<ul class="vr-flags">${b.tools.map((ref) => {
        const t = byRef[ref] || {};
        return `<li><b>${esc(t.name)}</b> ${t.does ? esc(t.does) : '<span class="muted">Nobody has said what it does.</span>'}
          ${b.step === 3 || b.step === 2 ? (t.held_by || []).map((h) => `<span>${esc(h.unit)}${h.used_for ? ` uses it for ${esc(h.used_for)}` : ""}${h.ask ? ` · ask ${esc(h.ask)}` : ""}</span>`).join("") : ""}
          ${b.step === 4 ? `<span>${esc((t.availability || []).map((a) => ((d.options.routes || []).find((r) => r.value === a) || {}).label || a).join(", "))}</span>` : ""}
          ${b.step === 6 && t.supplier_shown !== "Not recorded" ? `<span>From ${esc(t.supplier_shown)} — the agreement would be written on Vendors.</span>` : ""}</li>`;
      }).join("")}</ul>` : `<p class="small">${esc(b.empty_says)}</p>`}</section>`).join("")}`;
  find.querySelector("#rgSearch").onsubmit = (e) => {
    e.preventDefault();
    RG.q = igVal(find, "rg-q"); RG.unit = igVal(find, "rg-unit");
    const total = (d.bands || []).length;
    RG.said = `Searched. Results in ${total} bands, in the order the hierarchy asks you to look.`;
    go("registry");
  };
  root.appendChild(find);

  // §3 · the stat row.
  const c = d.counters || {};
  const stats = el("section", "panel");
  stats.setAttribute("aria-label", "Counts");
  const tiles = [[c.in_catalog, "Tools in your catalog"], [c.you_already_have, "You already have"]];
  if (!d.one_unit) tiles.push([c.held_by_more_than_one, "Held by more than one unit"]);
  tiles.push([c.nobody_said_what_it_does, "Nobody has said what it does"],
             [c.held_on_no_project, "Held here, on no project"]);
  stats.innerHTML = `<div class="vr-tiles">${tiles.map(([n, l]) =>
      `<div class="vr-tile"><b>${n || 0}</b><span>${esc(l)}</span></div>`).join("")}</div>
    ${Object.values((c.says || {})).map((s) => `<p class="small muted" style="margin:8px 0 0">${esc(s)}</p>`).join("")}`;
  root.appendChild(stats);

  // §4 · findings.
  const raised = d.raised || [];
  const f = el("section", "panel");
  f.id = "rgFindings";
  f.setAttribute("aria-labelledby", "rgFindingsH");
  f.innerHTML = `<h2 class="sub3" id="rgFindingsH" style="margin-top:0">${raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"}` : "Nothing to flag"}</h2>
    ${raised.length ? `<ul class="vr-flags">${raised.map((x) => `<li>${x.tool && byRef[x.tool]
      ? `<b>${esc(byRef[x.tool].name)}</b> ` : ""}${esc(x.says)}</li>`).join("")}</ul>`
      : `<p class="intro">${esc(d.nothing_to_flag)}</p>`}`;
  root.appendChild(f);

  // §5 · the catalog.
  root.appendChild(registryList(d));

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  live.textContent = RG.said || (d.bands || []).map((b) =>
    `${b.band}, ${b.tools.length} result${b.tools.length === 1 ? "" : "s"}`).join(". ");
  RG.said = "";

  const open = (tool) => {
    const old = $("#rgForm"); if (old) old.remove();
    const host = el("section", "panel");
    host.id = "rgForm";
    find.after(host);
    catalogForm(host, d, tool);
    const h = host.querySelector("h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  };
  $("#view").querySelectorAll("[data-rg-edit]").forEach((b) => b.onclick = () => open(byRef[b.dataset.rgEdit]));
  const add = $("#rgAdd"); if (add) add.onclick = () => open(null);
  const seed = $("#rgSeed");
  if (seed) seed.onclick = async () => {
    const out = await post("/api/catalog/seed", {});
    if (out && out.ok) { RG.said = `Added ${out.made.length} from your framework.`; go("registry"); }
  };
};

function registryList(d) {
  const box = el("section", "panel");
  box.id = "rgList";
  box.setAttribute("aria-labelledby", "rgListH");
  const rows = (d.tools || []).slice();
  const sorts = { held: "By whether you hold it", name: "By name", supplier: "By supplier", units: "By how many units hold it" };
  const cmp = {
    held: (a, b) => (!!(b.held_by || []).length - !!(a.held_by || []).length) || String(a.name).localeCompare(String(b.name)),
    name: (a, b) => String(a.name).localeCompare(String(b.name)),
    supplier: (a, b) => String(a.supplier_shown).localeCompare(String(b.supplier_shown)),
    units: (a, b) => (b.held_by || []).length - (a.held_by || []).length,
  }[RG.sort];
  rows.sort(cmp);
  box.innerHTML = `<h2 class="sub3" id="rgListH" style="margin-top:0">The catalog</h2>
    <div class="row" style="gap:12px;align-items:flex-end;flex-wrap:wrap">
      <button type="button" class="btn" id="rgAdd">Add a tool</button>
      <label class="vr-field" style="margin:0">Sort
        <select id="rgSort">${Object.entries(sorts).map(([k, l]) => `<option value="${k}"${k === RG.sort ? " selected" : ""}>${l}</option>`).join("")}</select></label></div>
    ${(d.seed_offer || []).length ? `<div class="vr-tell"><p><b>${d.seed_offer.length} tools you already have.</b>
      These came from your framework. Add what each one does and who else uses it, and the next
      person with a problem will find them.</p><p class="small">${esc(d.seed_offer.join("; "))}</p>
      <p><button type="button" class="btn ghost" id="rgSeed">Add these to the catalog</button></p></div>` : ""}
    ${rows.length ? `<div class="vr-scroll" tabindex="0" role="region" aria-labelledby="rgListH">
      <table class="vr-table"><caption class="vh">The catalog, ${esc(sorts[RG.sort].toLowerCase())}</caption>
      <thead><tr>${["The tool", "What it does", "Who supplies it", "Held by", "Used for", "Where it stands", "Projects", ""]
        .map((h) => `<th scope="col">${h || '<span class="vh">Actions</span>'}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((t) => `<tr>
        <th scope="row">${esc(t.name)}<br><span class="small muted">${esc(t.ref)}</span></th>
        <td>${esc(t.does || "Nobody has said")}</td>
        <td>${esc(t.supplier_shown)}${t.vendor_money ? `<br><span class="small muted">${esc(t.vendor_money)} · on Vendors</span>` : ""}</td>
        <td>${esc(t.held_shown)}</td><td>${esc(t.used_for_shown)}</td>
        <td>${esc(t.standing || "Not said")}</td><td>${esc(t.projects_shown)}</td>
        <td><button type="button" class="btn ghost" data-rg-edit="${esc(t.ref)}">Edit</button></td></tr>`).join("")}</tbody></table></div>`
    : `<p class="intro" style="white-space:pre-line">${esc(d.empty)}</p>`}`;
  box.querySelector("#rgSort").onchange = (e) => { RG.sort = e.target.value; go("registry"); };
  return box;
}

/* §6–8 · the form. Only the name is required. */
function catalogForm(host, d, tool) {
  const inp = d.inputs || {}, rb = inp.readbacks || {}, opt = d.options || {};
  const t = tool || {};
  const supplierValue = t.vendor ? `vendor:${t.vendor}` : t.supplier || "";
  host.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${tool ? esc(t.name) : "Add a tool"}</h2>
    <p class="intro">Only the name is required. A catalog that refuses a row until every box
      is filled is one nobody finishes. Come back and add the rest as you learn it.</p>
    ${igText("rg-name", "The tool", "The product name.", { value: t.name || "" })}
    ${igText("rg-does", "What it does", "In plain words, what somebody would use it for. Write it the way you would say it to a colleague, not the way the vendor writes it.", { long: true, value: t.does || "" })}
    <div class="vr-field"><label for="rg-supplier">Who supplies it</label>
      <p class="small muted vr-help" id="rg-supplier-help">Where a supplier is named, cost, terms and renewal live on Vendors and are shown here read-only.${rb.can_build ? ` ${esc(rb.can_build)}` : ""}</p>
      <select id="rg-supplier" aria-describedby="rg-supplier-help"><option value="">Not recorded</option>
        ${(d.vendors || []).map((v) => `<option value="vendor:${esc(v.id)}"${supplierValue === `vendor:${v.id}` ? " selected" : ""}>${esc(v.name)}${v.product ? ` — ${esc(v.product)}` : ""}</option>`).join("")}
        ${inp.can_build ? `<option${supplierValue === opt.built_here ? " selected" : ""}>${esc(opt.built_here)}</option>` : ""}
        <option${supplierValue === opt.came_with ? " selected" : ""}>${esc(opt.came_with)}</option></select></div>
    ${igRadios("rg-standing", "Where it stands with you", opt.standings, t.standing || "")}
    <div id="rg-availbox" hidden>${igRadios("rg-avail", "How it is available to you",
      [...opt.routes.map((r) => [r.value, r.label]), ["", "We are not sure"]], (t.availability || [])[0] || "", "", rb.agreements)}</div>
    ${igRadios("rg-ai", "How much AI is in it", opt.involvement, t.involvement || "", "", rb.added_ai)}
    ${igRadios("rg-general", "Is it a general-purpose tool, under your own definition of what counts?", opt.general_purpose || [], t.general_purpose || "",
      "Recorded here, never worked out for you. Where your framework says something never goes into a general-purpose tool, this is what that is checked against.")}
    ${d.one_unit ? igRadios("rg-have", "Do you have this?", ["Yes", "No"], (t.held_by || []).length ? "Yes" : "")
      : `<fieldset class="vr-tri" style="display:block"><legend>Who here has it</legend>
        <p class="small muted">Most people fill in their own unit and stop. The second and third entries are the ones that matter. A tool one team uses for permit summaries is frequently the answer to a problem somebody in another building has been trying to buy their way out of.</p>
        <div id="rg-holders"></div></fieldset>`}
    ${igText("rg-could", "What else it could do", "What it is capable of beyond what anybody here uses it for. This is what a vendor turns on next year, and it is also where the second use case usually comes from.", { long: true, value: t.could_also || "" })}
    ${(d.holdings || []).length ? `<fieldset class="vr-tri"><legend>What information it would need</legend>
      <p class="small muted vr-help" style="width:100%">So a person at Identify can see whether the information exists before the tool is chosen. Read from Data.</p>
      ${d.holdings.map((h) => `<label><input type="checkbox" name="rg-holdings" value="${esc(h.id)}"${(t.needs_holdings || []).includes(h.id) ? " checked" : ""}> ${esc(h.name)}</label>`).join("")}
      ${(t.never_hits || []).map((n) => `<p class="small" style="width:100%">${esc(n)}</p>`).join("")}</fieldset>` : ""}
    ${(d.projects || []).length ? `<fieldset class="vr-tri"><legend>Which projects use it</legend>
      ${d.projects.map((p) => `<label><input type="checkbox" name="rg-projects" value="${esc(p.ref)}"${(t.projects || []).includes(p.ref) ? " checked" : ""}> ${esc(p.name)}</label>`).join("")}</fieldset>` : ""}
    <p class="small" id="rg-err" role="alert"></p>
    <p><button type="button" class="btn" id="rg-save">${tool ? "Save it" : "Add it"}</button>
      <button type="button" class="btn ghost" id="rg-cancel">Cancel</button></p>`;
  const $$ = (s) => host.querySelector(s);
  const availShown = () => $$("#rg-availbox").hidden = igPicked(host, "rg-standing") !== "Available to us on an agreement";
  host.querySelectorAll('[name="rg-standing"]').forEach((r) => r.onchange = availShown);
  availShown();
  const holders = $$("#rg-holders") ? prRows($$("#rg-holders"), [["unit", "Unit"],
    ["used_for", "What they use it for"], ["ask", "Who to ask about it — role"]],
    (t.held_by || []).length ? t.held_by : [{}], "Unit") : null;
  $$("#rg-cancel").onclick = () => { host.remove(); };
  $$("#rg-save").onclick = async () => {
    const err = $$("#rg-err"); err.textContent = "";
    const name = igVal(host, "rg-name");
    if (!name) { err.textContent = "The product name is the one thing this needs."; $$("#rg-name").focus(); return; }
    const sup = $$("#rg-supplier").value;
    const body = {
      ref: tool ? tool.ref : "", name, does: igVal(host, "rg-does"),
      vendor: sup.startsWith("vendor:") ? sup.slice(7) : "",
      supplier: sup.startsWith("vendor:") ? "" : sup,
      standing: igPicked(host, "rg-standing"),
      availability: igPicked(host, "rg-avail") ? [igPicked(host, "rg-avail")] : [],
      involvement: igPicked(host, "rg-ai"), general_purpose: igPicked(host, "rg-general"),
      could_also: igVal(host, "rg-could"),
      needs_holdings: [...host.querySelectorAll('[name="rg-holdings"]:checked')].map((c) => c.value),
      projects: [...host.querySelectorAll('[name="rg-projects"]:checked')].map((c) => c.value),
      held_by: holders ? holders.read().filter((h) => h.unit)
        : igPicked(host, "rg-have") === "Yes" ? [{ unit: "Here", used_for: "" }] : [],
    };
    const out = await post("/api/catalog", body);
    if (!out || !out.ok) { err.textContent = (out && out.error) || "That did not save."; return; }
    RG.said = tool ? "Saved." : `Added to the catalog as ${out.tool.ref}.`;
    go("registry");
  };
}

/* The seven-gate tracker for one project.
 *
 * A labeled list, and deliberately not a progress graphic. Every gate is
 * drawn, always, with its own state word beside its name — passed, and on
 * what date; where it is now; or not yet. A reader who cannot see the tint
 * gets the same three facts from the text.
 *
 * No gate is numbered. The names are the whole of the sequence, and there is
 * no "3 of 7" and no percentage, because this is not a measure of how far
 * along anything is. */
function trackerOf(tr) {
  const ul = el("ul", "pj-track");
  ul.setAttribute("aria-label", "The seven steps, and where this stands");
  tr.gates.forEach((g) => {
    const state = g.current ? "Here now"
      : g.passed_on ? "Passed " + g.passed_on : "Not yet";
    const cls = g.current ? "here" : g.passed_on ? "passed" : "ahead";
    const li = el("li", "pj-gate " + cls,
      `<span class="g-name">${esc(g.name)}</span>
       <span class="g-was">${esc(state)}</span>` +
      // Recording late is ordinary. Both facts are kept rather than one of
      // them being flattened into the other.
      (g.recorded_after_the_fact
        ? `<span class="pj-late">written up later</span>` : ""));
    ul.appendChild(li);
  });
  return ul;
}

/* One project, opened beneath the list: the tracker, then the forms that move
 * it.
 *
 * Every form here writes through Projects, the only surface allowed to write
 * a record's state. The moves offered are the ones the spine allows from
 * where the project stands, named by gate and never numbered; a refusal is
 * the spine's own sentence, shown word for word in an announced region, with
 * what is still outstanding listed underneath so it is navigable rather than
 * a dead end. */
function projectPanel(one, d, ref) {
  const p = d.projects.find((x) => x.ref === ref);
  if (!p) return;
  S.openProject = ref;
  const pass = p.passage || { moves: [], binds: [] };
  const gateName = (id) => (d.spine.gates.find((g) => g.id === id) || {}).name || "";
  const here = gateName(p.gate);
  const redraw = () => go("projects");

  one.hidden = false;
  one.innerHTML = `<h2 class="sub3" style="margin-top:0">${esc(p.name)}
    <span class="mono">${esc(p.ref)}</span></h2>`;
  one.appendChild(trackerOf(p.tracker));
  one.appendChild(el("p", "pj-waiting", esc(p.tracker.waiting_on)));
  if (p.tracker.version_pending) {
    one.appendChild(el("p", "note", esc(p.tracker.version_pending_says)));
  }

  const said = el("p", "pj-said");
  said.id = "pjSaid";
  said.setAttribute("role", "alert");
  said.hidden = true;
  one.appendChild(said);
  const refuse = (r) => {
    said.hidden = false;
    said.innerHTML = `<b>${esc(r.error || "That was not recorded.")}</b>` +
      ((r.unmet || []).length ? `<br><span class="small">Still outstanding
        here: ${r.unmet.map((f) => esc(((p.passage.binds || [])
          .find((b) => b.id === f) || {}).says || f)).join("; ")}.</span>` : "");
  };

  /* Who is accountable — the one obligation that stops a project leaving
     Identify. A role, with a person beside it where one is given. */
  const who = el("div", "pj-block");
  who.innerHTML = `<h3 class="sub4">Who is accountable</h3>` + (p.accountable
    ? `<p>${esc(p.accountable)}${p.accountable_person
        ? ` — ${esc(p.accountable_person)}` : ""}</p>`
    : `<p class="small muted">Nobody is named yet. A project with nobody's
        name against it cannot leave Identify.</p>`) + `
    <div class="pj-inline">
      <label class="pj-field"><span>Role</span>
        <input id="pjRole" type="text" value="${esc(p.accountable || "")}"
               placeholder="" aria-describedby="pjRoleHelp"></label>
      <label class="pj-field"><span>Person <em>(optional)</em></span>
        <input id="pjPerson" type="text" value="${esc(p.accountable_person || "")}"></label>
      <button class="btn" id="pjNameIt" type="button">${p.accountable
        ? "Change" : "Name them"}</button>
    </div>
    <p class="small muted" id="pjRoleHelp">A title, such as General Manager,
      so the record still makes sense after somebody moves on.</p>`;
  one.appendChild(who);

  // The scrutiny level, in the organization's own words and no others.
  const lvl = el("div", "pj-block");
  lvl.innerHTML = `<h3 class="sub4">Scrutiny level</h3>` + ((d.levels || []).length
    ? `<div class="pj-inline"><label class="pj-field"><span>Level</span>
        <select id="pjLevel"><option value="">Not set</option>${d.levels.map((l) =>
          `<option${l === p.level ? " selected" : ""}>${esc(l)}</option>`).join("")}
        </select></label>
        <button class="btn" id="pjSetLevel" type="button">Set</button></div>`
    : `<p class="small muted">Your framework has not set its levels of
        scrutiny yet. Once it does, they are offered here in your own words.</p>`);
  one.appendChild(lvl);

  /* What binds here. Each obligation is met by pointing at something — the
     procedure, the document, the decision — never by a box that says yes. */
  if ((pass.binds || []).length) {
    const binds = el("div", "pj-block");
    binds.innerHTML = `<h3 class="sub4">What has to hold before this leaves ${esc(here)}</h3>
      <ul class="pj-binds">${pass.binds.map((b, i) => `<li>
        <b>${esc(b.says.charAt(0).toUpperCase() + b.says.slice(1))}.</b>
        <span class="small">${b.refuses
          ? "Has to be met before this can be recorded as past " + esc(here) + "."
          : "Recorded if it is missing; the project still moves."}</span>
        ${b.satisfied
          ? `<span class="pj-met">Points at: ${esc(b.points_at)}</span>`
          : b.id === "floor.somebody_named"
            ? `<span class="small muted">Met by naming who is accountable, above.</span>`
            : `<div class="pj-inline">
                 <label class="pj-field"><span>What does this point at?</span>
                   <input type="text" id="pjPoint${i}" data-floor="${esc(b.id)}"
                          aria-describedby="pjPointHelp"></label>
                 <button class="btn ghost" type="button" data-point="${i}">Record</button>
               </div>`}
      </li>`).join("")}</ul>
      <p class="small muted" id="pjPointHelp">Name the procedure, the document
        or the decision, and where it is — for example "Procedure PR-4F2K9M,
        turning off the permit assistant".</p>`;
    one.appendChild(binds);
  }

  // Recording a passage — or starting again, where the project is stopped.
  const move = el("div", "pj-block");
  if (pass.stopped) {
    move.innerHTML = `<h3 class="sub4">This project is stopped</h3>
      <p class="small muted">Nothing moves from a stop until it is reversed.
        Its history is kept either way.</p>
      <button class="btn" id="pjRestart" type="button" data-how="${esc(pass.restart)}">${
        pass.restart === "start_again" ? "Start it again" : "Pick it up again"}</button>`;
  } else if ((pass.moves || []).length) {
    move.innerHTML = `<h3 class="sub4">Record a passage</h3>
      <div class="pj-inline">
        <label class="pj-field"><span>Move to</span>
          <select id="pjTo">${pass.moves.map((m) =>
            `<option value="${esc(m.id)}">${m.back ? "Back to " : ""}${esc(m.name)}</option>`).join("")}
          </select></label>
        <label class="pj-field"><span>This happened on <em>(if earlier than today)</em></span>
          <input id="pjHappened" type="date"></label>
        <button class="btn" id="pjMove" type="button">Record the passage</button>
      </div>
      <p class="small muted">Recording late is ordinary. Where it happened
        earlier, the record shows both dates rather than pretending it was
        written down at the time.</p>`;
  } else {
    move.innerHTML = `<h3 class="sub4">Record a passage</h3>
      <p class="small muted">There is nowhere further for this project to go
        from ${esc(here)}.</p>`;
  }
  one.appendChild(move);

  // Where it stands. Cleared and Retired are not offered: a passage produces
  // the first, and the Sunset gate the second.
  if (!pass.stopped) {
    const st = el("div", "pj-block");
    st.innerHTML = `<h3 class="sub4">Where it stands</h3>
      <div class="pj-inline">
        <label class="pj-field"><span>State</span>
          <select id="pjState">${(d.settable_states || []).map((s) =>
            `<option value="${esc(s.id)}"${s.id === p.state ? " selected" : ""}>${esc(s.shown_as)}</option>`).join("")}
          </select></label>
        <label class="pj-field" id="pjWhoWrap"><span>Waiting on whom</span>
          <input id="pjWaitingFor" type="text" value="${esc(p.waiting_for || "")}"></label>
        <button class="btn ghost" id="pjSetState" type="button">Set</button>
      </div>`;
    one.appendChild(st);
  }

  // Wiring.
  const act = async (url, body, done) => {
    const r = await post(url, { ref, ...body });
    if (!r.ok) { refuse(r); return; }
    S.openProject = ref;
    toast(done);
    redraw();
  };
  const q = (s) => one.querySelector(s);
  q("#pjNameIt").onclick = () => act("/api/projects/accountable",
    { role: q("#pjRole").value.trim(), person: q("#pjPerson").value.trim() },
    "Recorded who is accountable.");
  if (q("#pjSetLevel")) q("#pjSetLevel").onclick = () => act("/api/projects/level",
    { level: q("#pjLevel").value }, "Scrutiny level set.");
  one.querySelectorAll("[data-point]").forEach((b) => {
    const box = q("#pjPoint" + b.dataset.point);
    b.onclick = () => act("/api/projects/point",
      { floor: box.dataset.floor, points_at: box.value.trim() },
      "Recorded what it points at.");
  });
  if (q("#pjMove")) q("#pjMove").onclick = () => act("/api/projects/move",
    { to: q("#pjTo").value, happened: q("#pjHappened").value },
    "Passage recorded.");
  if (q("#pjRestart")) q("#pjRestart").onclick = () => act("/api/projects/restart",
    { how: q("#pjRestart").dataset.how }, "The project is moving again.");
  if (q("#pjSetState")) {
    const sel = q("#pjState"), wrap = q("#pjWhoWrap");
    const show = () => { wrap.hidden = sel.value !== "state.waiting_person"; };
    sel.onchange = show; show();
    q("#pjSetState").onclick = () => act("/api/projects/state",
      { to: sel.value, waiting_for: q("#pjWaitingFor").value.trim() },
      "State recorded.");
  }
  projectWriteUp(one, d, p);
}

/* §4, §8 – §12 · Everything written up about one project, section by
   section. Every answer is optional: the first half of this surface exists to
   be answered slowly, by somebody who does not yet know the answers. */
function projectWriteUp(one, d, p) {
  const opt = d.options || {}, inp = d.inputs || {};
  const pr = p.problem || {}, sol = p.solution || {}, hi = p.hierarchy || {};
  const pre = p.pressure || {}, tl = p.tool || {}, cs = p.case_detail || {};
  const bl = p.baseline_detail || {}, gr = p.grounds || {}, sn = p.sunset || {};
  const say = el("p", "vh"); say.setAttribute("aria-live", "polite");
  one.appendChild(say);
  const save = async (url, body, done) => {
    const r = await post(url, { ref: p.ref, ...body });
    if (!r || !r.ok) { toast((r && r.error) || "That was not saved.", true); return false; }
    S.openProject = p.ref; toast(done); go("projects"); return true;
  };
  const block = (title, open, inner) => {
    const b = el("details", "pj-block");
    if (open) b.open = true;
    b.innerHTML = `<summary><h3 class="sub4" style="display:inline">${esc(title)}</h3></summary>${inner}`;
    one.appendChild(b);
    return b;
  };
  const verdictSelect = (id, v) => `<select id="${id}"><option value="">No verdict yet</option>${
    opt.verdicts.map((x) => `<option${x === v ? " selected" : ""}>${esc(x)}</option>`).join("")}</select>`;

  // §4 · the findings on this project.
  const f = p.findings || [];
  const fb = block(f.length ? `${f.length} finding${f.length === 1 ? "" : "s"} on this one` : "Nothing to flag on this one", f.length > 0,
    f.length ? `<ul class="vr-flags">${f.map((x) => `<li>${esc(x.says)}</li>`).join("")}</ul>`
      : `<p class="small">${esc(d.nothing_to_flag)}</p>`);

  // When somebody means to reach the next gate — 4.15 reads it.
  block("When should this reach the next gate?", false, `
    ${igText("pj-nextby", "A date somebody set", "Optional. Nothing is refused for passing it; it is named if it passes.", { type: "date", value: p.next_gate_by || "" })}
    <p><button type="button" class="btn ghost" id="pjNextSave">Keep this date</button></p>`)
    .querySelector("#pjNextSave").onclick = () => save("/api/projects/next-gate", { by: igVal(one, "pj-nextby") }, "Date kept.");

  // §8 · Identify, first half — the nine questions, never mentioning technology.
  const route = d.route_in || {};
  const prob = block("What is going wrong", p.gate === "gate.identify" && !pr.happening, `
    ${route.name ? `<p class="vr-tell small">Your own route in, <b>${esc(route.name)}</b>: ${esc(route.steps || "")}</p>` : ""}
    <p class="small muted">This half never mentions technology. Every question can be answered with “I don't know” — that is a legitimate answer here.</p>
    ${igText("pb-happening", "What's happening?", "Describe the situation as you experience it. What goes wrong, where in the process, and what it looks like when it does. If your answer names a product, a tool, a vendor or a technology, you have described a solution instead of a problem.", { long: true, value: pr.happening || "" })}
    ${igText("pb-affects", "Who does this affect, and how often?", "Which roles or teams run into this? Roughly how many people? How many times a week, month or year does it happen?", { long: true, value: pr.affects || "" })}
    ${igText("pb-costs", "What does it cost?", "Time per occurrence. Rework. Delay to the applicant or the public. Risk exposure. Money, if you know it. If you do not have numbers, say so — that itself is worth knowing.", { long: true, value: pr.costs || "" })}
    <label class="small"><input type="checkbox" id="pb-notcounted"${pr.costs_not_counted ? " checked" : ""}> We have not counted</label>
    <div class="row" style="gap:12px;flex-wrap:wrap">
      <div style="flex:1 1 240px">${igText("pb-known", "Known", "Where do your numbers come from — a report, a system, a count you did?", { long: true, value: pr.known || "" })}</div>
      <div style="flex:1 1 240px">${igText("pb-assumed", "Assumed", "Or a sense you have? Both are useful. Mixing them up is not.", { long: true, value: pr.assumed || "" })}</div></div>
    ${igText("pb-tried", "What's already been tried?", "Include anything that used to work and stopped, workarounds people built on their own, and tools already bought that were supposed to help.", { long: true, value: pr.tried || "" })}
    ${igText("pb-else", "Who else has this problem?", "Other sections, divisions or programs. Other governments, if you know of any.", { long: true, value: pr.who_else || "" })}
    ${igText("pb-nothing", "What happens if nothing changes?", "Six months from now. A year from now. Does it hold steady, get worse, or reach a breaking point?", { long: true, value: pr.if_nothing || "" })}
    ${igText("pb-fixed", "How would you know it was fixed?", "What would be different? What would you be able to measure, count or observe?", { long: true, value: pr.how_known || "" })}
    <fieldset class="vr-tri" aria-describedby="pb-infofor-help"><legend>What would information that helps with this be good for?</legend>
      <p class="small muted vr-help" id="pb-infofor-help" style="width:100%">Tick what applies. The whole organization is searched, not just your own part of it — somebody may already have it.</p>
      ${Object.entries(d.utility_options || {}).map(([k, l]) => `<label><input type="checkbox" name="pb-infofor" value="${esc(k)}"${(pr.info_for || []).includes(k) ? " checked" : ""}> ${esc(l)}</label>`).join("")}</fieldset>
    ${d.one_unit ? "" : igText("pb-unit", "Which part of the organization is asking?", "So that somebody elsewhere who already holds this can be pointed at you.", { value: pr.unit || "" })}
    ${(p.data_lookup || []).map((l) => `<div class="vr-tell small"><b>${esc(l.label)}</b>: ${l.holdings.length
      ? `<ul>${l.holdings.map((h) => `<li>${esc(h.name)}${h.units.length ? ` — used by ${esc(h.units.join(", "))}` : ""}${h.owner ? `, owned by ${esc(h.owner)}` : ""}. ${esc(h.reachable || "Reachability not recorded")}. ${esc(h.freshness || "How current is not recorded")}.</li>`).join("")}</ul>`
      : esc(l.empty_says)}</div>`).join("")}
    ${igText("pb-parked", "Anything else you noticed? (optional)", "Things that came up that are not the main problem but seem worth writing down.", { long: true, value: pr.parked || "" })}
    <details${pr.idea ? " open" : ""}><summary>Did you already have something in mind?</summary>
      <p class="small">Most people do. Write it down now so it is not lost. It gets picked up again at the solution search, once the problem is clear. Nothing here counts for or against it.</p>
      ${igText("pb-idea", "What were you thinking of?", "A product, an idea, something you saw somewhere.", { long: true, value: pr.idea || "" })}
      ${igText("pb-ideausers", "Who would use it?", "", { value: pr.idea_users || "" })}
      ${igRadios("pb-company", "Is there a company behind it?", ["Yes, name it", "No, we would build or configure it ourselves", "It is already inside something we own", "We are not sure"], pr.idea_company || "")}
      ${igText("pb-companyname", "The company", "", { value: pr.idea_company_name || "" })}
      ${igText("pb-ideacost", "Do you know what it would cost?", "", { value: pr.idea_cost || "" })}</details>
    ${igText("pb-cause", "The cause", "Stated plainly. Where nobody is confident, say so rather than manufacturing certainty.", { long: true, value: pr.cause || "" })}
    ${igRadios("pb-conf", "How confident", opt.confidence, pr.confidence || "")}
    <p><button type="button" class="btn" id="pbSave">Save what is going wrong</button></p>`);
  prob.querySelector("#pbSave").onclick = () => save("/api/projects/section", { section: "problem", fields: {
    happening: igVal(prob, "pb-happening"), affects: igVal(prob, "pb-affects"), costs: igVal(prob, "pb-costs"),
    costs_not_counted: prob.querySelector("#pb-notcounted").checked, known: igVal(prob, "pb-known"),
    assumed: igVal(prob, "pb-assumed"), tried: igVal(prob, "pb-tried"), who_else: igVal(prob, "pb-else"),
    if_nothing: igVal(prob, "pb-nothing"), how_known: igVal(prob, "pb-fixed"), parked: igVal(prob, "pb-parked"),
    idea: igVal(prob, "pb-idea"), idea_users: igVal(prob, "pb-ideausers"), idea_company: igPicked(prob, "pb-company"),
    idea_company_name: igVal(prob, "pb-companyname"), idea_cost: igVal(prob, "pb-ideacost"),
    cause: igVal(prob, "pb-cause"), confidence: igPicked(prob, "pb-conf"),
    info_for: [...prob.querySelectorAll('[name="pb-infofor"]:checked')].map((c) => c.value),
    ...(d.one_unit ? {} : { unit: igVal(prob, "pb-unit") }) } }, "Saved.");

  // §9A · is the answer a tool at all? Nine categories, none skipped silently.
  const cat = block("Is the answer a tool at all?", false, `
    <p class="small muted">Every category gets a verdict and one line of reasoning. Some will not apply, and saying so is a complete answer. Skipping one without saying anything is the failure.</p>
    <p class="small">Does this fix help the people doing the work, and make any future technology easier? When a fix does both, it is almost always the right first move.</p>
    <ol class="pj-cats">${opt.categories.map((c) => `<li><fieldset class="vr-tri" style="display:block"><legend><b>${esc(c.name)}</b></legend>
      <p class="small muted">${esc(c.says)}</p>
      <label class="small">Verdict ${verdictSelect(`cv-${c.key}`, (sol[c.key] || {}).verdict)}</label>
      <label class="small" style="display:block">One line of reasoning <input id="cw-${c.key}" value="${esc((sol[c.key] || {}).why || "")}"></label>
      ${c.key === "data" ? `<p class="small">${esc((d.recommendations["rec.fix_data_first"] || {}).says || "")} — ${esc((d.recommendations["rec.fix_data_first"] || {}).because || "")}</p>` : ""}</fieldset></li>`).join("")}</ol>
    <p><button type="button" class="btn" id="catSave">Save the verdicts</button></p>
    ${p.gate === "gate.identify" && p.state !== "state.turned_down" ? `<div class="vr-tell">
      <p class="small">Where a category that is not a tool was taken, the project can close here. It stays on the list for ever and counts under Ended without a tool.</p>
      <label class="small">Close it with <select id="catClose"><option value="">Choose the category taken</option>${opt.categories.filter((c) => opt.closes.includes(c.key)).map((c) => `<option value="${c.key}">${esc(c.name)}</option>`).join("")}</select></label>
      <button type="button" class="btn ghost" id="catCloseGo">This is the answer — close it here</button></div>` : ""}`);
  cat.querySelector("#catSave").onclick = () => save("/api/projects/verdicts", { categories: Object.fromEntries(
    opt.categories.map((c) => [c.key, { verdict: igVal(cat, `cv-${c.key}`), why: igVal(cat, `cw-${c.key}`) }])) }, "Verdicts saved.");
  const closeGo = cat.querySelector("#catCloseGo");
  if (closeGo) closeGo.onclick = () => {
    const k = igVal(cat, "catClose");
    if (!k) { toast("Choose the category that was taken.", true); return; }
    save("/api/projects/close-without-tool", { category: k, why: igVal(cat, `cw-${k}`) },
      "This is a complete outcome. What you learned here is on the record.");
  };

  // §9B · the hierarchy — where the technology comes from.
  const techTaken = ["simple_tech", "involved_tech"].some((k) => (sol[k] || {}).verdict === "Taken");
  const catalog = d.catalog || [];
  const hier = block("Where the technology comes from", false, `
    <p class="small muted">${techTaken ? "Six steps, walked in order. Each is either taken or documented as inadequate before the next is considered."
      : "This is reached where the verdict on one of the two technology categories above is Taken. You can still write it now."}
      Recommended, never required: walking it, skipping it, or recording that you went straight to a vendor are all complete answers.</p>
    <p class="small">${esc((d.recommendations["rec.walk_hierarchy"] || {}).because || "")}</p>
    <ol class="pj-steps">${opt.steps.map((s) => {
      const v = hi[String(s.n)] || {};
      const note = s.n === 2 || s.n === 3 ? (catalog.filter((t) => (t.held_by || []).length).length
          ? `In your catalog, held here: ${esc(catalog.filter((t) => (t.held_by || []).length).map((t) => `${t.name} (${t.held_by.join(", ")})`).join("; "))}.`
          : "Nothing in your catalog is recorded as held here yet.")
        : s.n === 4 ? `${inp.coop ? `You said you buy off other governments' agreements ${esc(inp.coop)}.` : ""} ${catalog.filter((t) => (t.availability || []).length).map((t) => esc(t.name)).join(", ")}`
        : s.n === 5 && !inp.can_build ? "You said you have no information technology function, so this is not available here — never a step you failed."
        : s.n === 6 && pr.idea_company === "Yes, name it" ? `This is what you had in mind when you started: ${esc(pr.idea_company_name || pr.idea || "")}.` : "";
      return `<li><fieldset class="vr-tri" style="display:block"><legend><b>Step ${s.n} — ${esc(s.name)}</b></legend>
        <p class="small muted">${esc(s.question)}. Answered from ${esc(s.from)}.</p>
        ${note ? `<p class="small">${note}</p>` : ""}
        <label class="small">Verdict ${verdictSelect(`hv-${s.n}`, v.verdict)}</label>
        <label class="small" style="display:block">One line of reasoning <input id="hw-${s.n}" value="${esc(v.why || "")}"></label>
        <label class="small" style="display:block">The candidate found, and why it did not fit <input id="hc-${s.n}" value="${esc(v.candidate || "")}"></label></fieldset></li>`;
    }).join("")}</ol>
    ${inp.reuse ? `<p class="small">You said staff have to check what you already have first. Most organizations do not realize the cross-utilization capabilities of the tools already in place.</p>` : ""}
    <p><button type="button" class="btn" id="hierSave">Save the steps</button></p>`);
  hier.querySelector("#hierSave").onclick = () => save("/api/projects/verdicts", { steps: Object.fromEntries(
    opt.steps.map((s) => [String(s.n), { verdict: igVal(hier, `hv-${s.n}`), why: igVal(hier, `hw-${s.n}`), candidate: igVal(hier, `hc-${s.n}`) }])) }, "Steps saved.");

  // §9C · sequence and pressure-test.
  const pt = block("Before it leaves Identify", false, `
    ${igText("pt-first", "What has to happen first regardless of which option we choose?", "There is almost always something.", { long: true, value: pre.first_regardless || "" })}
    ${igText("pt-cheap", "What is the cheapest thing that would meaningfully help?", "The cheapest useful fix rather than the best one. Sometimes that is the whole answer.", { long: true, value: pre.cheapest || "" })}
    ${igText("pt-breaks", "If we do the complicated thing without doing the simple thing, what breaks?", "", { long: true, value: pre.what_breaks || "" })}
    ${igText("pt-rebuild", "Are we about to build something we will have to rebuild?", "Where the input is inconsistent, a build that copes with it has to be reworked the day the input gets standardized.", { long: true, value: pre.rebuild || "" })}
    <p><button type="button" class="btn" id="ptSave">Save</button></p>`);
  pt.querySelector("#ptSave").onclick = () => save("/api/projects/section", { section: "pressure", fields: {
    first_regardless: igVal(pt, "pt-first"), cheapest: igVal(pt, "pt-cheap"),
    what_breaks: igVal(pt, "pt-breaks"), rebuild: igVal(pt, "pt-rebuild") } }, "Saved.");

  // §9E · what the record carries when the answer is a tool.
  const factors = inp.factors || [];
  const tr = block("The tool record", false, `
    ${igText("tl-what", "What is it, in one sentence", "In the proposer's words, kept verbatim. Not the vendor's description of it.", { value: tl.what_it_is || "" })}
    ${igRadios("tl-scope", "Is it in scope under your own definition?", opt.in_scope, tl.in_scope || "",
      (inp.scope_covered || []).length ? `You said these count: ${inp.scope_covered.join("; ")}.${(inp.scope_excluded || []).length ? ` And these do not: ${inp.scope_excluded.join("; ")}.` : ""}` : "")}
    <div id="tl-borderbox"${tl.in_scope === "Borderline" ? "" : " hidden"}>
      ${igText("tl-bby", "Who made the borderline call", inp.arbiter ? `You said ${inp.arbiter} decides when it is not clear.` : "", { value: tl.borderline_by || inp.arbiter || "" })}
      ${igRadios("tl-brev", "Has that call been reviewed afterward?", ["Yes", "No"], tl.borderline_reviewed || "")}</div>
    ${factors.length ? `<fieldset class="vr-tri" style="display:block"><legend>How the level was reached — your own factors</legend>
      ${factors.map(([k, label]) => `<label class="small" style="display:flex;gap:8px;align-items:center;margin:4px 0">
        <select data-factor="${esc(k)}"><option value="">Not answered</option>${["yes", "no"].map((v) => `<option value="${v}"${(tl.factors || {})[k] === v ? " selected" : ""}>${v === "yes" ? "Yes" : "No"}</option>`).join("")}</select>
        ${esc(label)} <span class="muted">you said this matters: ${esc((inp.factor_weights || {})[k] || "not answered")}</span></label>`).join("")}
      ${inp.single_factor ? `<p class="small">You said one serious factor lifts the whole thing.</p>` : ""}</fieldset>` : ""}
    ${(d.holdings || []).length ? `<fieldset class="vr-tri"><legend>What information would it touch</legend>
      ${d.holdings.map((h) => `<label><input type="checkbox" name="tl-hold" value="${esc(h.id)}"${(p.holdings || []).includes(h.id) ? " checked" : ""}> ${esc(h.name)}</label>`).join("")}
      <label style="flex:1 1 100%"><input type="checkbox" id="tl-holdunsure"${tl.holdings_unsure ? " checked" : ""}> We are not sure</label></fieldset>` : ""}
    ${igRadios("tl-running", "Is it running now?", [["yes", "Yes"], ["no", "No"], ["unknown", "Not known"]], p.in_use || "",
      "Answer honestly. A tool nobody approved is the ordinary way this starts and nothing here treats it as a fault.")}
    ${igText("tl-found", "When it was found (if it was already running)", "", { type: "date", value: tl.found_on || "" })}
    ${igText("tl-users", "Who has been using it", "", { value: tl.used_by || "" })}
    ${igRadios("tl-final", "Does it decide or finalize anything on its own?", [["yes", "Yes"], ["no", "No"]], tl.finalises || "")}
    ${igRadios("tl-public", "Does the public see it, or what it produces?", [["yes", "Yes — the public uses it directly"],
      ["output", "The public sees what it produces"], ["no", "No"], ["unknown", "We are not sure"]], tl.public_facing || "",
      "Where the public uses it, the accessibility checks you said you run apply to it. Where the public sees it or its output, somebody has to be able to reach a person instead.")}
    <div class="vr-field"><label for="tl-wording">The words the public sees</label>
      <p class="small muted vr-help" id="tl-wording-help">${d.wording_home
        ? `You said approved wording lives in one place: ${esc(d.wording_home)}. Point at it rather than writing your own.`
        : "Point at approved wording on Process, or write this one's own."}</p>
      <select id="tl-wording" aria-describedby="tl-wording-help"><option value="">None chosen</option>
        ${(d.wordings || []).map((w) => `<option value="${esc(w.ref)}"${tl.disclosure_ref === w.ref ? " selected" : ""}>${esc(w.name)} (${esc(w.ref)})</option>`).join("")}
      </select></div>
    ${igText("tl-owntext", "Or this one's own words", "", { long: true, value: tl.disclosure_text || "" })}
    ${(d.goals || []).length ? `<div class="vr-field"><label for="tl-goal">Which of your responsibilities this serves</label>
      <select id="tl-goal"><option value="">None named</option>${d.goals.map((g) => `<option value="${esc(g.ref)}"${p.goal === g.ref ? " selected" : ""}>${esc(g.goal)}</option>`).join("")}</select></div>` : ""}
    ${igText("tl-adv", "How it advances that goal (optional)", "", { long: true, value: tl.advances || "" })}
    <p><button type="button" class="btn" id="tlSave">Save the tool record</button></p>`);
  tr.querySelectorAll('[name="tl-scope"]').forEach((r) => r.onchange = () => {
    tr.querySelector("#tl-borderbox").hidden = igPicked(tr, "tl-scope") !== "Borderline"; });
  tr.querySelector("#tlSave").onclick = async () => {
    const goal = tr.querySelector("#tl-goal");
    if (goal && goal.value !== (p.goal || "")) await post("/api/projects/goal", { ref: p.ref, goal: goal.value });
    save("/api/projects/section", { section: "tool", fields: {
      what_it_is: igVal(tr, "tl-what"), in_scope: igPicked(tr, "tl-scope"), borderline_by: igVal(tr, "tl-bby"),
      borderline_reviewed: igPicked(tr, "tl-brev"),
      factors: Object.fromEntries([...tr.querySelectorAll("[data-factor]")].map((s) => [s.dataset.factor, s.value])),
      holdings: [...tr.querySelectorAll('[name="tl-hold"]:checked')].map((c) => c.value),
      holdings_unsure: !!(tr.querySelector("#tl-holdunsure") || {}).checked,
      found_on: igVal(tr, "tl-found"), used_by: igVal(tr, "tl-users"), finalises: igPicked(tr, "tl-final"),
      public_facing: igPicked(tr, "tl-public"),
      disclosure_ref: igVal(tr, "tl-wording"), disclosure_text: igVal(tr, "tl-owntext"),
      advances: igVal(tr, "tl-adv"), running: igPicked(tr, "tl-running") } }, "Tool record saved.");
  };

  // §9D · what Identify produces — assembled from what was written.
  const sm = p.summary || {};
  block("What Identify produced", false, `
    <p class="small muted">Assembled from what was written here, and nothing else. Where an answer is missing, it says so.</p>
    <h4 class="sub4">Problem statement</h4><p class="small">${esc(sm.problem_statement)}</p>
    <h4 class="sub4">Known</h4><p class="small">${esc(sm.known)}</p>
    <h4 class="sub4">Assumed</h4><p class="small">${esc(sm.assumed)}</p>
    <h4 class="sub4">Root cause</h4><p class="small">${esc(sm.cause)}</p>
    <h4 class="sub4">Options considered</h4><ul class="small">${(sm.options_considered || []).map((o) => `<li>${esc(o)}</li>`).join("")}</ul>
    <h4 class="sub4">Recommended sequence</h4><ul class="small">${(sm.sequence || []).map((o) => `<li>${esc(o)}</li>`).join("")}</ul>
    <h4 class="sub4">What to measure</h4><p class="small">${esc(sm.what_to_measure)}</p>
    ${sm.parking_lot ? `<h4 class="sub4">Parking lot</h4><p class="small">${esc(sm.parking_lot)}</p>` : ""}`);

  // §10 · Procure — the business case, the baseline, the data grounds.
  const fc = p.full_cost || {};
  const rows = (bl.rows || []);
  const pc = block("Procure — the business case, the baseline and the data grounds", false, `
    <h4 class="sub4">The business case</h4>
    <p class="small">The problem and the options considered are read back from Identify above, and edited there.</p>
    <p class="small"><b>Full cost across its life</b>, computed on Budget from its cost lines: $${Math.round(fc.a_year || 0).toLocaleString()} a year and $${Math.round(fc.one_off || 0).toLocaleString()} one-off.
      ${(fc.nothing_recorded || []).length ? `Nothing recorded for: ${esc(fc.nothing_recorded.map((n) => n.label).join(", "))}.` : ""}
      <span class="muted">${esc(fc.no_lifetime_total || "")}</span></p>
    ${inp.roi ? igText("bc-back", "What we expect to get back", "A claim, in your words, that somebody will check later. It does not have to be money.", { long: true, value: cs.expect_back || "" }) : ""}
    <fieldset class="vr-tri"><legend>Where the money would come from</legend>
      ${opt.money_from.map((m) => `<label><input type="checkbox" name="bc-money" value="${esc(m)}"${(cs.money_from || []).includes(m) ? " checked" : ""}> ${esc(m)}</label>`).join("")}</fieldset>
    ${igText("bc-wrote", "Who wrote this — role", "", { value: cs.wrote_it || "" })}
    ${p.duplicate_of || p.chosen_step === 6 ? igText("bc-whynew", "If another part of the organization already has something that does this, why buy a new one? (optional)",
      "There are good reasons — a different unit, a different scale, a license that will not extend. This records yours.", { long: true, value: cs.why_buy_new || "" }) : ""}
    <h4 class="sub4">The baseline — current conditions</h4>
    <p class="small">${esc((d.recommendations["rec.baseline_first"] || {}).because || "")}</p>
    ${igText("bl-today", "What the work looks like today", "How it is done now, by whom, in what order. Somebody reading this in two years should be able to picture the job as it stood before anything changed.", { long: true, value: bl.today || p.baseline || "" })}
    <fieldset class="vr-tri" style="display:block"><legend>The numbers, as they stand today</legend>
      <p class="small muted">A report, a system, a count somebody did, or a considered estimate. The app never supplies a metric; what gets counted is yours.</p>
      <div id="bl-rows"></div></fieldset>
    ${igText("bl-sharp", "How you will know it worked", "", { long: true, value: bl.sharpened || pr.how_known || "" })}
    <h4 class="sub4">The data grounds</h4>
    <p class="small">A baseline is worth nothing if the same measurement cannot be taken again.</p>
    ${(d.holdings || []).length ? `<fieldset class="vr-tri"><legend>Where the measurement comes from</legend>
      ${d.holdings.map((h) => `<label><input type="checkbox" name="gr-hold" value="${esc(h.id)}"${(gr.holdings || []).includes(h.id) ? " checked" : ""}> ${esc(h.name)} <span class="muted">${esc(h.reachable || "")}</span></label>`).join("")}</fieldset>`
      : `<p class="small">Every later use case depends on knowing what you hold and whether a tool can reach it. Record it on Data.</p>`}
    ${igText("gr-who", "Who can take the measurement", "The person who could pull this number again next year.", { value: gr.who_measures || "" })}
    ${igRadios("gr-often", "How often it can be taken", opt.how_often, gr.how_often || "")}
    ${(p.vendors_panel || []).length ? `<h4 class="sub4">From Vendors, read-only</h4>${p.vendors_panel.map((v) => `<p class="small">${esc(v.name)}${v.product ? ` — ${esc(v.product)}` : ""}. ${esc(v.route || "")} ${v.renewal ? `Renews ${esc(v.renewal)}.` : ""}</p>`).join("")}` : ""}
    <p><button type="button" class="btn" id="pcSave">Save Procure</button></p>`);
  const blRows = prRows(pc.querySelector("#bl-rows"), [["what", "What is counted"], ["figure", "The figure"],
    ["source", "Where the figure came from"], ["taken", "The date it was taken", "date"],
    ["nobody", "Nobody has counted", "check"]], rows, "Number");
  pc.querySelector("#pcSave").onclick = async () => {
    const ok1 = await post("/api/projects/section", { ref: p.ref, section: "business_case", fields: {
      expect_back: igVal(pc, "bc-back"), money_from: [...pc.querySelectorAll('[name="bc-money"]:checked')].map((c) => c.value),
      wrote_it: igVal(pc, "bc-wrote"),
      ...(pc.querySelector("#bc-whynew") ? { why_buy_new: igVal(pc, "bc-whynew") } : {}) } });
    const ok2 = await post("/api/projects/section", { ref: p.ref, section: "baseline", fields: {
      today: igVal(pc, "bl-today"), rows: blRows.read(), sharpened: igVal(pc, "bl-sharp") } });
    await save("/api/projects/section", { section: "grounds", fields: {
      holdings: [...pc.querySelectorAll('[name="gr-hold"]:checked')].map((c) => c.value),
      who_measures: igVal(pc, "gr-who"), how_often: igPicked(pc, "gr-often") } }, ok1 && ok2 ? "Procure saved." : "Saved.");
  };

  // §11 · versions, and the update loop.
  const vs = (p.versions || []).filter((v) => v && v.ref);
  const vb = block(`Versions${vs.length ? ` · ${vs.length}` : ""}`, !!p.version_pending, `
    <p class="small muted">${esc(d.no_vendor_feed)}</p>
    ${vs.map((v) => `<fieldset class="vr-tri" style="display:block"><legend><b>${esc(v.ref)}</b> · opened ${esc(v.opened)}${v.live ? ` · live ${esc(v.live)}` : ""}${v.retired ? ` · retired ${esc(v.retired)}, because the next one went live` : ""}</legend>
      <p class="small">${v.not_told ? "We were not told." : v.told_on ? `The vendor said it was coming on ${esc(v.told_on)}.` : ""} What changed, in their words: ${esc(v.what)}</p>
      <label class="small">Is this material? <select data-vmat="${esc(v.ref)}">${opt.material.map((m) => `<option${m === v.material ? " selected" : ""}>${esc(m)}</option>`).join("")}</select></label>
      <label class="small">Did it go through a testing environment first? <select data-vstage="${esc(v.ref)}"><option value="">Not said</option>${opt.staged.map((m) => `<option${m === v.staged ? " selected" : ""}>${esc(m)}</option>`).join("")}</select></label>
      <label class="small" style="display:block">What was tried — a check reference, or why there is none <input data-vtest="${esc(v.ref)}" value="${esc(v.tested || v.tested_reason || "")}"></label>
      ${v.live ? "" : `<label class="small">When it went live <input type="date" data-vlive="${esc(v.ref)}"></label>`}
      <button type="button" class="btn ghost" data-vsave="${esc(v.ref)}">Save this version</button></fieldset>`).join("")}
    <details><summary>The vendor says something is changing</summary>
      ${igText("vn-what", "What changed", "Paste what they sent. Their words, not a summary.", { long: true })}
      ${igText("vn-told", "When the vendor said it was coming", "", { type: "date" })}
      <label class="small"><input type="checkbox" id="vn-nottold"> We were not told</label>
      <p><button type="button" class="btn ghost" id="vnOpen">Open a version record</button></p></details>
    <p class="small">${esc((d.recommendations["rec.try_the_update_first"] || {}).says || "")} — ${esc((d.recommendations["rec.try_the_update_first"] || {}).because || "")}</p>`);
  vb.querySelector("#vnOpen").onclick = () => save("/api/projects/version", { what: igVal(vb, "vn-what"),
    told_on: igVal(vb, "vn-told"), not_told: vb.querySelector("#vn-nottold").checked }, "Version record opened.");
  vb.querySelectorAll("[data-vsave]").forEach((b) => b.onclick = () => {
    const r = b.dataset.vsave;
    const tested = vb.querySelector(`[data-vtest="${r}"]`).value.trim();
    const live = vb.querySelector(`[data-vlive="${r}"]`);
    save("/api/projects/version", { vref: r, material: vb.querySelector(`[data-vmat="${r}"]`).value,
      staged: vb.querySelector(`[data-vstage="${r}"]`).value,
      tested: /^CK-/.test(tested) ? tested : "", tested_reason: /^CK-/.test(tested) ? "" : tested,
      live: live ? live.value : "" }, "Version saved.");
  });

  // §12 · the tool sunset record.
  const sb = block("Retiring the tool", p.gate === "gate.sunset", `
    <p class="small muted">A tool sunset is a judgment against the claim that justified the tool. A version going live and the one before it retiring is bookkeeping, recorded under Versions above.</p>
    ${igRadios("sn-trigger", "Which trigger fired", [...(inp.triggers || []), "Somebody proposed it"], sn.trigger || "")}
    ${igText("sn-by", "Who decided — role (whoever decides)", "", { value: sn.decided_by || "" })}
    ${igText("sn-on", "When it was decided", "", { type: "date", value: sn.decided_on || "" })}
    ${igText("sn-notice", "Notice given on", inp.notice_words ? `You said ${inp.notice_words} notice.` : "", { type: "date", value: sn.notice_on || "" })}
    ${igText("sn-noticeto", "Who was told", "", { value: sn.notice_to || "" })}
    ${igRadios("sn-replace", "What replaces it", opt.replaced_by, sn.replaced_by || "")}
    ${igText("sn-records", "What happened to the records and the information", inp.retire_words ? `You said: ${inp.retire_words}` : "What was kept and for how long; where it went.", { long: true, value: sn.records || "" })}
    ${igText("sn-confirmed", "Who confirmed the records went where they were supposed to — role (whoever decides)", "", { value: sn.records_confirmed_by || "" })}
    ${p.supplier ? `${igText("sn-returned", "Information returned and deleted — who confirmed it", "Confirmed rather than assumed.", { value: sn.information_returned_by || "" })}
      ${igText("sn-returnedon", "On", "", { type: "date", value: sn.information_returned_on || "" })}
      <p class="small">You can get the information back and you can have it deleted. What it taught their tool cannot be returned.</p>` : ""}
    ${((tl.factors || {}).delegated === "yes") ? igRadios("sn-deleg", "Did the delegating body have to be told?", opt.delegating_told, sn.delegating_told || "") : ""}
    <p class="small">Kept whether it flatters the organization or not.</p>
    ${igText("sn-final", "The final measurement, against the baseline", "", { long: true, value: sn.final_measurement || "" })}
    ${igText("sn-explain", "What somebody would need to explain a decision this touched, two years from now", "Quoted at the top of this project's story in History.", { long: true, value: sn.explain_later || "" })}
    <p><button type="button" class="btn ghost" id="snSave">Save the retirement record</button>
      ${d.decides && p.state !== "state.retired" && ["gate.measure", "gate.sunset"].includes(p.gate)
        ? `<button type="button" class="btn" id="snClose">Close the retirement record</button>` : ""}</p>
    ${d.decides && !["gate.measure", "gate.sunset"].includes(p.gate) ? `<p class="small muted">The record can be closed once this reaches Measure.</p>` : ""}`);
  // Deciding the retirement and confirming the records are whoever decides';
  // everybody else sees those answers and writes the rest.
  if (!d.decides) ["sn-by", "sn-on", "sn-confirmed"].forEach((id) => {
    const f = sb.querySelector(`#${id}`); if (f) f.readOnly = true; });
  sb.querySelector("#snSave").onclick = () => {
    const fields = {
      trigger: igPicked(sb, "sn-trigger"), notice_on: igVal(sb, "sn-notice"),
      notice_to: igVal(sb, "sn-noticeto"), replaced_by: igPicked(sb, "sn-replace"),
      records: igVal(sb, "sn-records"),
      information_returned_by: igVal(sb, "sn-returned"), information_returned_on: igVal(sb, "sn-returnedon"),
      delegating_told: igPicked(sb, "sn-deleg"), final_measurement: igVal(sb, "sn-final"),
      explain_later: igVal(sb, "sn-explain") };
    if (d.decides) Object.assign(fields, { decided_by: igVal(sb, "sn-by"),
      decided_on: igVal(sb, "sn-on"), records_confirmed_by: igVal(sb, "sn-confirmed") });
    save("/api/projects/sunset", { fields }, "Retirement record saved.");
  };
  const snClose = sb.querySelector("#snClose");
  if (snClose) snClose.onclick = () => save("/api/projects/sunset/close", {}, "Retired. It stays on the list with its whole history.");
}

VIEWS.projects = async () => {
  const d = await api("/api/projects");
  { const w = notYours(d); if (w) { $("#view").innerHTML = ""; $("#view").appendChild(w); return; } }
  const root = el("div");
  const c = d.counters;

  /* Five counts, each with the label the module wrote. Never a rate, never a
     grade, never a proportion — and the two that could read as an accusation
     carry their own sentence saying they are not one. */
  const tiles = el("div", "tiles");
  [["open", "open"], ["running_ahead", "already running"],
   ["nobody_named", "nobody named"],
   ["changed_never_tried", "changed, never tried"],
   ["ended_without_a_tool", "ended without a tool"]].forEach(([k, cap]) => {
    tiles.appendChild(el("div", "tile",
      `<div class="num">${c[k]}</div><div class="cap">${esc(cap)}</div>`));
  });
  root.appendChild(tiles);

  Object.entries(c.says || {}).forEach(([, line]) =>
    root.appendChild(el("p", "note", esc(line))));

  /* 4 · What the list itself shows, and 4.18 · the list was checked. */
  const lf = el("div", "panel");
  lf.innerHTML = `<h2 class="sub3" style="margin-top:0">What this list shows</h2>
    ${(d.list_findings || []).length
      ? `<ul class="vr-flags">${d.list_findings.map((f) => `<li>${esc(f.says)}</li>`).join("")}</ul>`
      : `<p class="small">${esc(d.nothing_to_flag)}</p>`}
    <p class="small">${d.list_checked ? `Somebody last confirmed this list is accurate on ${esc(d.list_checked)}.`
      : "Nobody has confirmed this list is accurate yet."}
      <button type="button" class="btn ghost" id="pjListChecked">This list is accurate today</button></p>`;
  root.appendChild(lf);
  lf.querySelector("#pjListChecked").onclick = async () => {
    const r = await post("/api/projects/list-checked", {});
    if (!r || !r.ok) { toast("That was not recorded.", true); return; }
    toast("Recorded that the list was checked today."); go("projects");
  };

  /* 7 · Starting a project. Only the name is required — a register that
     refuses a row until every box is filled is one nobody finishes. */
  const start = el("div", "panel");
  start.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Start a project</h2>
    <div class="pj-form">
      <label class="pj-field"><span>What would you call this?</span>
        <input id="pjName" type="text" aria-describedby="pjNameHelp"></label>
      <p class="small muted" id="pjNameHelp">Whatever the people who would use
        it call it. You can change this later.</p>
      <label class="pj-field"><span>Who is asking for it? <em>(optional)</em></span>
        <input id="pjAsked" type="text" aria-describedby="pjAskedHelp"></label>
      <p class="small muted" id="pjAskedHelp">The person or team that noticed
        the problem. This is not the same as who will be accountable for it
        later.</p>
      <label class="pj-field"><span>Is something already running for this?</span>
        <select id="pjRunning" aria-describedby="pjRunningHelp">
          <option value="">Not sure</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select></label>
      <p class="small muted" id="pjRunningHelp">Answer honestly. A tool nobody
        approved is the ordinary way this starts, and nothing here treats it
        as a fault.</p>
      <div class="row" style="border:0;padding-top:0">
        <button class="btn" id="pjStart" type="button">Start the project</button>
      </div>
    </div>`;
  root.appendChild(start);

  if (!d.projects.length) {
    const box = el("div", "panel");
    box.innerHTML = `<div class="pj-empty">${esc(d.empty)}</div>`;
    root.appendChild(box);
  } else {
    const list = el("div", "panel");
    list.innerHTML =
      `<table><thead><tr>` +
      d.columns.map((h) => `<th scope="col">${esc(h)}</th>`).join("") +
      `</tr></thead><tbody>` +
      d.projects.map((p) => {
        const st = (d.spine.states.find((s) => s.id === p.state) || {});
        // The reference is a button, so the row opens from a keyboard as well
        // as a mouse. A clickable <tr> is not reachable with Tab.
        return `<tr class="click" data-ref="${esc(p.ref)}">
          <td><button class="linky mono" type="button" data-open="${esc(p.ref)}"
                aria-label="Open ${esc(p.name)} (${esc(p.ref)})">${esc(p.ref)}</button></td>
          <td>${esc(String(p.name || "").slice(0, 44))}</td>
          <td>${esc((d.spine.gates.find((g) => g.id === p.gate) || {}).name || "")}</td>
          <td>${esc(st.shown_as || "")}</td>
          <td class="small">${esc(p.tracker.waiting_on)}</td>
          <td>${esc(p.in_use || "")}</td>
          <td>${esc(p.level || "Not set")}</td>
          <td>${esc(p.accountable || "Nobody named")}</td>
          <td class="small muted">${esc(niceDate(p.last_moved))}</td>
        </tr>`;
      }).join("") + `</tbody></table>`;

    const one = el("div", "panel");
    one.hidden = true;
    one.id = "pjOne";
    list.querySelectorAll("[data-open]").forEach((b) =>
      b.onclick = (e) => { e.stopPropagation(); projectPanel(one, d, b.dataset.open); });
    list.querySelectorAll("tr[data-ref]").forEach((tr) =>
      tr.onclick = () => projectPanel(one, d, tr.dataset.ref));
    root.appendChild(list);
    root.appendChild(one);
    // After an action the screen redraws; reopen what was open.
    if (S.openProject && d.projects.some((p) => p.ref === S.openProject)) {
      projectPanel(one, d, S.openProject);
    }
  }

  // Said on the screen in these words, because a count that looked complete
  // would be the more dangerous thing to show.
  root.appendChild(el("p", "note", esc(d.no_vendor_feed)));

  $("#view").innerHTML = ""; $("#view").appendChild(root);

  $("#pjStart").onclick = async () => {
    const name = $("#pjName").value.trim();
    if (!name) { toast("Give it a name — you can change it later.", true); $("#pjName").focus(); return; }
    const r = await post("/api/projects/start", {
      name, asked_by: $("#pjAsked").value.trim(),
      already_running: $("#pjRunning").value });
    if (!r.ok) { toast(r.error || "Could not start the project.", true); return; }
    S.openProject = r.project.ref;
    toast(`Started ${r.project.ref}. It begins at Identify.`);
    go("projects");
  };

  reason([
    { title: "What the unit is", body: "One project is one narrow use of one tool — its own baseline, its own named person, its own answers. The same tool doing two jobs is two projects.", cite: "Projects §1" },
    { title: "Why nothing here is a score", body: "No chart, no task list, no percentage complete. An organization that ran every project to ended without a tool has used this correctly.", cite: "Projects §1 — what this surface is not" },
    { title: "Where state is written", body: "Here, and nowhere else. Every other surface reads a project's gate and state; this is the only one that writes them.", cite: "Lifecycle spine §3.2" },
  ]);
};

VIEWS.lifecycle = async () => {
  const d = await api("/api/lifecycle");
  const root = el("div");

  /* The standing panel, above the first step. It says where the work
     actually happens, because this page does none of it. */
  const top = el("div", "panel");
  top.innerHTML = `<p class="intro" style="margin:0">${esc(d.standing_panel)}</p>`;
  const jump = el("button", "linky", "Open Projects");
  jump.onclick = () => go("projects");
  top.appendChild(jump);
  root.appendChild(top);

  /* Seven blocks, all expanded, h2 per step and h3 per part, so a screen
     reader user can jump between steps with heading navigation. Nothing is
     collapsed and nothing is behind a hover. */
  const steps = el("div", "panel");
  steps.innerHTML = d.steps.map((s) => `
    <section class="lcr-step">
      <h2>${esc(s.name)}</h2>
      <p class="lcr-q">${esc(s.question)}</p>
      <div class="lcr-part"><p>${esc(s.says)}</p></div>
      <div class="lcr-part">
        <h3>What it asks of you</h3>
        <ul>${s.asks.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
      </div>
      <div class="lcr-part">
        <h3>Who decides</h3><p>${esc(s.who_decides)}</p>
      </div>
      <div class="lcr-part">
        <h3>What holds people up here</h3>
        <ul>${s.holds_people_up.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>
      </div>
      ${s.adaptive ? `<p class="lcr-flag">${esc(s.adaptive)}</p>` : ""}
      ${s.flag ? `<p class="lcr-flag">${esc(s.flag)}</p>` : ""}
      <div class="lcr-part">
        <h3>Where the work is done</h3>
        <p class="lcr-where">${esc(s.where_the_work_is_done)}</p>
      </div>
    </section>`).join("");
  root.appendChild(steps);

  // A section of its own, because it is the part people do not expect. Text
  // only: any diagram beside this would be decorative and would carry
  // nothing the paragraph does not.
  const loop = el("div", "panel");
  loop.innerHTML = `<h2 class="sub3" style="margin-top:0">The loop</h2>
    <p class="lcr-loop">${esc(d.loop)}</p>`;
  root.appendChild(loop);

  const st = el("div", "panel");
  st.innerHTML = `<h2 class="sub3" style="margin-top:0">The states a project can be in</h2>` +
    d.states.map((s) =>
      `<div class="req"><span class="t"><b>${esc(s.shown_as)}</b> —
        ${esc(s.means)}</span></div>`).join("") +
    `<h3 class="sub4">Two things that are not states</h3>` +
    d.not_states.map((n) =>
      `<div class="req"><span class="t"><b>${esc(n.fact)}</b> —
        ${esc(n.says)}</span></div>`).join("") +
    `<p class="lcr-flag" style="margin-top:12px">${esc(d.in_use_and_early)}</p>`;
  root.appendChild(st);

  const hats = el("div", "panel");
  hats.innerHTML = `<h2 class="sub3" style="margin-top:0">The three hats</h2>` +
    // The paragraph about one person holding all three appears for every
    // organization. Only where it sits changes.
    (d.hats_first ? `<p class="intro">${esc(d.one_person_all_three)}</p>` : "") +
    d.hats.map((h) => `<div class="req"><span class="t">${esc(h.name)}</span></div>`).join("") +
    (d.hats_first ? "" : `<p class="intro" style="margin-top:12px">${esc(d.one_person_all_three)}</p>`);
  root.appendChild(hats);

  /* Real table semantics, row and column headers, scrolling inside its own
     container. The single most useful thing on this page for somebody who
     thinks governance happens at purchase. */
  const fl = el("div", "panel");
  fl.innerHTML = `<h2 class="sub3" style="margin-top:0">What has to hold, and where it comes back</h2>
    <p class="intro">${esc(d.why_the_floors_table)}</p>
    <div class="lcr-floors"><table>
      <thead><tr><th scope="col">What has to hold</th>
      <th scope="col">First asked at</th><th scope="col">Comes back at</th>
      <th scope="col">Refuses a passage</th></tr></thead><tbody>` +
    d.floors.map((f) =>
      `<tr><th scope="row">${esc(f.says)}</th>
       <td>${esc(f.set_at)}</td>
       <td>${esc(f.comes_back_at.join(", ") || "—")}</td>
       <td>${esc(f.refuses_at.join(", ") || "No")}</td></tr>`).join("") +
    `</tbody></table></div>`;
  root.appendChild(fl);

  const three = el("div", "panel");
  three.innerHTML = `<h2 class="sub3" style="margin-top:0">Findings, gaps and recommendations</h2>
    <p class="intro">Three things that look similar on a screen and mean
      different things.</p>` +
    d.three_objects.map((o) =>
      `<div class="req"><span class="t"><b>${esc(o.object)}</b>
        ${esc(o.says)}</span></div>`).join("");
  root.appendChild(three);

  const not = el("div", "panel");
  not.innerHTML = `<h2 class="sub3" style="margin-top:0">What this page does not do</h2>
    <ul class="small muted" style="margin:0;padding-left:18px">` +
    d.what_it_does_not_do.map((w) => `<li>${esc(w)}</li>`).join("") +
    `</ul><p class="note">${esc(d.render_the_gap)}</p>`;
  root.appendChild(not);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why this page exists", body: "The seven steps are the product's shape and nobody arrives knowing them. Somebody handed a governance framework needs one screen that says what each step asks, in the words their own organization used.", cite: "Lifecycle §1" },
    { title: "It holds nothing", body: "No record, no state, no count, no date. Every project lives on Projects, which is the only surface that writes a record's state. Holding anything here would create a second place for the truth to live.", cite: "Lifecycle §1; spine §3.2" },
    { title: "Where the numbers come from", body: "This page supplies none. The scrutiny levels, the cadence, the required terms and the decision shape are all read back from your own framework, and where you answered that you are not sure it says so rather than filling it in.", cite: "Lifecycle §1" },
  ]);
};

/* VIEWS.workflow was retired here. It rendered one Registry entry at one of
   six numbered gates, showed the Appendix H checklist parsed out of that
   agency's own workbook, and wrote the form back into a copy of it.

   It was good work against a single adopted corpus, and it cannot survive
   the lifecycle spine: seven gates, fixed names, never numbered, and no
   dependence on any one organization's spreadsheets. Its replacement is the
   tracker on every project screen plus the gate panels on Projects. Nothing
   was lost — no agency had generated a workbook through it.

   See the note above `api_config` in app/server.py. */

VIEWS.setup = async () => {
  const d = await api("/api/vocabulary");
  const root = el("div");

  if (!d.can_edit) {
    root.appendChild(el("div", "locked", `<b>Terminology is the Office of Technology's to set.</b>
      You are signed in as ${esc(S.state.actor.role)}. The vocabulary below is what
      the adopted documents actually use.`));
  }

  const intro = el("div", "panel");
  intro.innerHTML = `<p class="intro">Agencies name the same concepts differently —
    bucket or category, tier or level, A/B/C or 1/2/3. SCDES settled its naming in
    the Governance Framework; that fixed the Council Operating Procedures, which
    fixed the Operations Manual, which fixed all fourteen appendices. So this is
    <b>one choice made once</b>, and it cascades. The defaults below were read out
    of the adopted corpus, not assumed.</p>`;
  root.appendChild(intro);

  d.concepts.forEach((c) => {
    const w = el("div", "panel");
    const alt = Object.entries(c.alternatives_in_corpus || {})
      .map(([k, n]) => `${k} ×${n}`).join(", ");
    w.innerHTML =
      `<div class="field"><h3>${esc(c.title)}</h3>
       <p class="governs">${esc(c.governs)}</p>
       <div class="ctrl">
         <select data-role="noun" ${d.can_edit ? "" : "disabled"}>` +
           c.options.map((o) => `<option ${o === c.noun ? "selected" : ""}>${esc(o)}</option>`).join("") +
         `</select>
         <span class="val">${esc(Object.values(c.labels).join(" · "))}</span>
       </div>
       <div class="impact quiet"><b>In the corpus:</b> ${esc(c.evidence)}${alt ? " — " + esc(alt) : ""}.
         Applies to ${esc((c.surfaces || []).join(", "))}.</div></div>`;

    const sel = w.querySelector("[data-role=noun]");
    const box = w.querySelector(".impact");
    const val = w.querySelector(".val");
    sel.onchange = async () => {
      const p = await post("/api/vocabulary/preview", { concept: c.concept, noun: sel.value });
      val.textContent = Object.values(p.new_labels).join(" · ");
      box.className = "impact";
      box.innerHTML = `<b>Impact of this change:</b> ${esc(p.summary)}`;
    };

    if (d.can_edit) {
      const row = el("div", "row");
      const b = el("button", "btn", "Apply");
      b.onclick = async () => {
        const r = await post("/api/vocabulary/set", { concept: c.concept, noun: sel.value });
        if (!r.committed) return toast(r.reason, true);
        toast(`Terminology updated: ${r.impact.old_noun} → ${r.impact.new_noun}`);
        await refreshState(); go("setup");
      };
      row.appendChild(b);
      row.appendChild(el("span", "note", `Implements ${c.citation}`));
      w.appendChild(row);
    }
    root.appendChild(w);
  });

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why terminology comes first", body: "The Framework fixes the naming; everything downstream inherits it. Choosing here before the risk levels or the budget means every later screen, checklist and cited answer speaks one language.", cite: "SCDES AI Governance Framework §5, §6" },
    { title: "What it does not do", body: "The app re-labels its own surfaces. It does not rewrite the adopted documents — those remain exactly as signed.", cite: "Appendix N — Framework and Appendix Amendments" },
  ]);
};

/* A room built from a reference agency's documents, seen by somebody else.

   The endpoints behind these rooms now fail closed — they answer
   `{available: false, why: ...}` rather than handing over another agency's
   content. The screens did not know that: `VIEWS.agency` read `d.name` and
   `d.instruments.length`, so the client's DEMO account showed dashes where
   SCDES used to be and then threw on the instrument count.

   Half a fix is worse than none here, because the half that shipped looks
   like a broken page rather than a boundary being kept. */
function notYours(d) {
  if (!d || d.available !== false) return null;
  const box = el("div", "panel");
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Nothing here belongs to you yet</h2>
    <p class="intro">${esc(d.why || "")}</p>
    <p class="small muted">Your framework is the part that is yours, and it is
      free. Everything on this screen fills in from your own adopted documents
      and your own records — never from anybody else's.</p>
    <div class="row" style="margin-top:12px">
      <button class="btn" type="button" data-go="framework">Go to your
        framework</button>
    </div>`;
  const go = box.querySelector("[data-go]");
  if (go) go.onclick = () => window.go("framework");
  return box;
}

/* Data · What you hold, and what it is good for.

   One entry per body of information. It gates nothing, and that is
   deliberate: AI governance is not data governance, and nothing here requires
   a classification scheme, a data program, or a complete register before a
   project may proceed. Where something is unrecorded or unknown, this records
   a gap and lets the work go on. */
const DH = { sort: "name", f: {}, said: "" };
VIEWS.holdings = async () => {
  const d = await api("/api/holdings");
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    $("#view").appendChild(paidWall(d));
    return;
  }
  const root = el("div");
  const sum = d.summary || {};
  const mon = d.monitor || {};
  const inp = d.inputs || {};

  const live = el("p", "vh"); live.setAttribute("aria-live", "polite");
  live.textContent = DH.said; DH.said = "";
  root.appendChild(live);

  // 2 · Five counts. Two are absences, and stay absences — never a
  // proportion, never colored as an alarm.
  const head = el("div", "panel");
  head.innerHTML = `
    <p class="intro">One entry per body of information — where it lives, whether a tool
      can reach it, whether the feed is still true, and which parts of the organization
      it would serve if they knew it was there.</p>
    <div class="dh-tiles">
      ${[["Holdings recorded", sum.total],
         ["Reachable by an interface", sum.with_an_interface],
         ["Holding something sensitive", sum.holding_sensitive],
         ["Nobody named against it", sum.unowned],
         ["Where it lives is unknown", sum.unknown_location]]
        .map(([label, n]) => `<div class="dh-tile"><b>${n || 0}</b><span>${esc(label)}</span></div>`).join("")}
    </div>`;
  root.appendChild(head);

  // 5.1 · The overlap, above the list, without being asked for. Complete
  // sentences, each naming both units, the holding and the purpose.
  if (d.overlap) {
    const ov = el("div", "panel");
    ov.innerHTML = `<h2 class="sub3" style="margin-top:0">${esc(d.overlap.says)}</h2>
      ${d.overlap.pairs.length ? `<ul class="dh-flags">${d.overlap.pairs.map((p) =>
        `<li><b>${esc(p.holding)}</b>: ${esc(p.says)}</li>`).join("")}</ul>` : ""}`;
    root.appendChild(ov);
  }

  // 3 · Findings, only against the organization's own answers.
  const found = d.findings || [];
  const flags = el("div", "panel");
  flags.innerHTML = found.length
    ? `<h2 class="sub3" style="margin-top:0">${found.length} finding${found.length === 1 ? "" : "s"}</h2>
       <ul class="dh-flags">${found.map((f) => `<li><b>${esc(f.name)}</b> ${esc(f.says)}</li>`).join("")}</ul>`
    : `<p class="intro" style="margin:0">${esc(d.nothing_to_flag)}</p>`;
  root.appendChild(flags);

  // Every "We are not sure" is a gap record rather than a blank.
  if ((d.gaps || []).length) {
    const g = el("div", "panel");
    g.innerHTML = `<h2 class="sub3" style="margin-top:0">Not known yet</h2>
      <ul class="small">${d.gaps.map((x) => `<li>${esc(x.question)}, on <b>${esc(x.name)}</b> — ${
        x.owner ? `${esc(x.owner)} to close it` : "nobody named to close it"}</li>`).join("")}</ul>`;
    root.appendChild(g);
  }

  // 4A · The monitor. Four states, in text; a change is announced; the
  // honest limit sits immediately after the counts.
  const named = Object.fromEntries((d.holdings || []).map((h) => [h.id, h.name]));
  const dark = Object.entries(mon.checks || {}).filter(([, c]) => c.state === "down")
    .map(([id]) => named[id]).filter(Boolean);
  const watch = el("div", "panel");
  watch.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Accessibility monitor</h2>
    <p class="intro">Every endpoint you record is checked every fifteen minutes — one request,
      to see whether it answers. Nothing is sent with it and nothing is read back. It records
      that the door opened, not what is behind it.</p>
    <div class="dh-tiles">
      ${[["Watched", mon.watched], ["Answering", mon.up], ["Not answering", mon.down],
         ["Cannot be checked", mon.refused]]
        .map(([label, n]) => `<div class="dh-tile"><b>${n || 0}</b><span>${esc(label)}</span></div>`).join("")}
    </div>
    <p class="small muted" style="margin-top:10px">${esc(d.monitor_limit)}</p>
    ${dark.length ? `<p class="dh-outage" role="status"><b>Not answering:</b> ${esc(dark.join(", "))}.
      Anything reading from ${dark.length === 1 ? "it" : "them"} is working from whatever it last saw.</p>` : ""}
    <div class="row" style="margin-top:12px">
      <button class="btn ghost" id="dhSweep" type="button">Check them all now</button></div>`;
  root.appendChild(watch);

  root.appendChild(holdingsTable(d));
  root.appendChild(holdingForm(d, null));

  $("#view").innerHTML = "";
  $("#view").appendChild(root);

  const sweep = $("#dhSweep");
  if (sweep) sweep.onclick = async () => {
    sweep.disabled = true;
    sweep.textContent = "Checking…";
    const r = await post("/api/holdings/sweep", {});
    const m = (r && r.monitor) || {};
    DH.said = `Checked. ${m.up || 0} answering, ${m.down || 0} not answering, ${m.refused || 0} cannot be checked.`;
    go("holdings");
  };
};

/* A module somebody has not bought. Explained rather than hidden, on the same
   reasoning as a room that belongs to another agency: a locked door nobody
   can see is indistinguishable from a bug. */
function paidWall(d) {
  const box = el("div", "panel");
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Part of the subscription</h2>
    <p class="intro">${esc(d.why || "")}</p>
    <div class="row" style="margin-top:12px">
      <button class="btn" type="button" data-go="framework">Back to your
        framework</button>
    </div>`;
  const go_ = box.querySelector("[data-go]");
  if (go_) go_.onclick = () => go("framework");
  return box;
}

/* 6 · The list. Utility renders as its tags, not as a count, so scanning
   the column is how somebody spots the overlap themselves. */
function holdingsTable(d) {
  const box = el("div", "panel");
  const all = d.holdings || [];
  const checks = (d.monitor || {}).checks || {};
  const words = { up: "Answering", down: "Not answering", refused: "Cannot be checked" };
  const state = (h) => h.endpoint ? (words[(checks[h.id] || {}).state] || "Watched") : "";
  const units = [...new Set(all.flatMap((h) => h.units || []))].sort();
  const tags = [...new Set(all.flatMap((h) => h.utility_labels || []))].sort();
  const F = DH.f;
  const opts = (o, v) => `<option value="">Any</option>${Object.entries(o).map(([k, l]) =>
    `<option value="${esc(k)}"${k === v ? " selected" : ""}>${esc(l)}</option>`).join("")}`;
  const listOpts = (o, v) => opts(Object.fromEntries(o.map((x) => [x, x])), v);

  const rank = { live: 0, daily: 1, weekly: 2, monthly: 3, static: 4, unknown: 5, "": 6 };
  const reach = { api: 0, export: 1, screen: 2, no: 3, unknown: 4, "": 5 };
  let rows = all.filter((h) =>
    (!F.format || h.format === F.format) && (!F.location || h.location === F.location) &&
    (!F.reachable || h.reachable === F.reachable) &&
    (!F.utility || (h.utility_labels || []).includes(F.utility)) &&
    (!F.unit || (h.units || []).includes(F.unit)) &&
    (!F.sensitive || (F.sensitive === "yes") === !!(h.sensitive || []).length) &&
    (!F.feed || h.feed === F.feed));
  rows = rows.slice().sort((a, b) => DH.sort === "current" ? rank[a.freshness || ""] - rank[b.freshness || ""]
    : DH.sort === "reach" ? reach[a.reachable || ""] - reach[b.reachable || ""]
    : String(a.name).localeCompare(String(b.name)));

  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">What you hold</h2>
    ${all.length ? `<div class="row" style="gap:10px;flex-wrap:wrap;align-items:flex-end">
      <label class="small">Sort by <select id="dhSort">
        <option value="name"${DH.sort === "name" ? " selected" : ""}>Name</option>
        <option value="current"${DH.sort === "current" ? " selected" : ""}>How current</option>
        <option value="reach"${DH.sort === "reach" ? " selected" : ""}>Reachability</option></select></label>
      <label class="small">Shape <select data-f="format">${opts(d.formats || {}, F.format)}</select></label>
      <label class="small">Where it lives <select data-f="location">${opts(d.locations || {}, F.location)}</select></label>
      <label class="small">Reachable <select data-f="reachable">${opts(d.reachable || {}, F.reachable)}</select></label>
      ${tags.length ? `<label class="small">Good for <select data-f="utility">${listOpts(tags, F.utility)}</select></label>` : ""}
      ${units.length ? `<label class="small">Used by <select data-f="unit">${listOpts(units, F.unit)}</select></label>` : ""}
      <label class="small">Sensitive <select data-f="sensitive">${opts({ yes: "Holds a sensitive category", no: "Holds none" }, F.sensitive)}</select></label>
      <label class="small">Live feed <select data-f="feed">${opts(d.feed_options || {}, F.feed)}</select></label>
    </div>
    <p class="small muted" aria-live="polite">${rows.length} of ${all.length} shown.</p>
    <div class="table-scroll" role="region" aria-label="What you hold" tabindex="0">
    <table class="dh-table">
      <thead><tr>${["Name", "What is in it", "Shape", "Where it lives", "Reachable", "How current",
        "Owner", "Utility", "Feed", "Monitor", ""].map((c) => `<th scope="col">${c ? esc(c) : '<span class="vh">Actions</span>'}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((h) => `<tr>
        <th scope="row">${esc(h.name)}</th>
        <td class="small">${esc(h.contains || "")}</td>
        <td class="small">${esc(h.format_label || "")}</td>
        <td class="small">${esc(h.location_label || "")}${h.system ? `<span class="dh-sub">${esc(h.system)}</span>` : ""}</td>
        <td class="small">${esc(h.reachable_label || "")}</td>
        <td class="small">${esc(h.freshness_label || "")}</td>
        <td class="small">${esc(h.owner || "Nobody named")}</td>
        <td class="small">${esc((h.utility_labels || []).join("; "))}</td>
        <td class="small">${esc(h.feed_label || "")}${h.feed === "yes" ? `<span class="dh-sub">${
          h.feed_confirmed ? `Last confirmed current ${esc(h.feed_confirmed)}` : "Never confirmed"}</span>` : ""}</td>
        <td class="small">${esc(state(h))}</td>
        <td><button class="btn ghost" type="button" data-edit="${esc(h.id)}" aria-label="Edit ${esc(h.name)}">Edit</button>
          ${h.endpoint ? `<button class="btn ghost" type="button" data-check="${esc(h.id)}" aria-label="Check ${esc(h.name)} now">Check</button>` : ""}</td>
      </tr>`).join("")}</tbody></table></div>`
    : `<p class="intro">Nothing recorded yet. Start with the one system you would miss most if it stopped.</p>`}`;

  const sort = box.querySelector("#dhSort");
  if (sort) sort.onchange = () => { DH.sort = sort.value; go("holdings"); };
  box.querySelectorAll("[data-f]").forEach((s) => s.onchange = () => {
    DH.f[s.dataset.f] = s.value; go("holdings"); });
  box.querySelectorAll("[data-check]").forEach((b) => {
    b.onclick = async () => {
      b.disabled = true;
      const r = await post("/api/holdings/check", { id: b.dataset.check });
      DH.said = r && r.ok ? `Checked: ${words[r.result.state] || r.result.state}${r.result.why ? " — " + r.result.why : ""}.`
        : (r && r.error) || "That did not work.";
      if (!(r && r.ok)) toast(DH.said, true);
      go("holdings");
    };
  });
  box.querySelectorAll("[data-edit]").forEach((b) => {
    b.onclick = () => {
      const row = all.find((h) => h.id === b.dataset.edit);
      const form = holdingForm(d, row);
      const old = document.getElementById("dhForm");
      old.parentElement.replaceChild(form, old);
      form.scrollIntoView({ behavior: "smooth", block: "center" });
      const first = form.querySelector("#dh-name");
      if (first) first.focus();
    };
  });
  return box;
}

/* 7 – 11 · The form. One column, in reading order; every label stays
   visible; help is tied to its field rather than shown on hover. */
function holdingForm(d, row) {
  const box = el("div", "panel");
  box.id = "dhForm";
  const v = row || {};
  const inp = d.inputs || {};
  const tech = !!d.may_edit_technical;
  const cats = d.sensitive_options || [];
  const help = (id, text) => text ? `<p class="small muted vr-help" id="${id}-help">${esc(text)}</p>` : "";
  /* ⓘ beside a label, for what a field means. Brett, BUG-98855006: "a small
     i icon with info explaining what some of this means would be helpful
     (e.g. what system holds it?)". A button, not a hover, so a keyboard and a
     screen reader reach it; the explanation opens under the label and the
     field is described by it once open. */
  const INFO = {
    contains: "The kind of information inside. For example: permit applications with names and addresses, or monthly meter readings. A sentence is enough.",
    purpose: "Why your organization keeps it — the job it does for you. For example: “to track which permits are due for renewal”.",
    format: "How the information is stored: a database, a spreadsheet, documents, scanned paper, and so on.",
    location: "Where it sits: on your own servers, in a vendor's online service, in a shared drive, or on paper in a filing room.",
    reachable: "Whether a software tool could read it directly — through an interface or an export — or only by somebody copying it out by hand.",
    freshness: "How up to date it usually is: updated as things happen, daily, monthly, or only now and then.",
    system: "The software or place it is kept in, named the way your staff name it — “the permit system”, “the K drive”, “the finance spreadsheet”. If it is on paper, say where the paper is.",
  };
  const info = (id, label) => INFO[id] ? `<button type="button" class="info-i" aria-expanded="false"
      aria-controls="dh-${id}-info" aria-label="What “${esc(label)}” means">i</button>` : "";
  const infoText = (id) => INFO[id] ? `<p class="small vr-info" id="dh-${id}-info" hidden>${esc(INFO[id])}</p>` : "";
  /* The question and its ⓘ on one line. The field is a column, so the
     button used to drop to a line of its own (Brett, BUG-DAA12AE2: "Make
     all information i icons in line with the question"). */
  const question = (id, label) => `<span class="vr-q"><label for="dh-${id}">${esc(label)}</label>${info(id, label)}</span>`;
  const sel = (id, label, options, chosen, hint, locked) => `<div class="vr-field">
    ${question(id, label)}${infoText(id)}${help(`dh-${id}`, hint)}
    <select id="dh-${id}"${hint ? ` aria-describedby="dh-${id}-help"` : ""}${locked ? " disabled" : ""}>
      <option value="">Not answered</option>
      ${Object.entries(options).map(([k, l]) => `<option value="${esc(k)}"${k === chosen ? " selected" : ""}>${esc(l)}</option>`).join("")}
    </select></div>`;
  const txt = (id, label, value, hint, { long = false, locked = false } = {}) => `<div class="vr-field">
    ${question(id, label)}${infoText(id)}${help(`dh-${id}`, hint)}
    ${long ? `<textarea id="dh-${id}" rows="2"${hint ? ` aria-describedby="dh-${id}-help"` : ""}>${esc(value || "")}</textarea>`
      : `<input type="text" id="dh-${id}" value="${esc(value || "")}"${hint ? ` aria-describedby="dh-${id}-help"` : ""}${locked ? " readonly" : ""}>`}</div>`;
  const roles = inp.roles || [];
  const ownerIsListed = roles.includes(v.owner || "");
  const knownUnits = [...new Set((d.holdings || []).flatMap((h) => h.units || []))].sort();
  const addedTags = d.utility_added || [];
  const utilities = Object.entries(d.utility_options || {}).filter(([k]) => k !== "other");
  const lockNote = tech ? "" : `<p class="small">${esc(d.technical_refused)}</p>`;
  const feedOn = v.feed && v.feed !== "no";

  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0" id="dhFormTitle">${row ? `Edit ${esc(v.name)}` : "Add a holding"}</h2>
    <p class="intro">Only the name is required. A register that refuses a row until every box is
      filled is one nobody finishes — come back and add the rest when you know it.</p>
    ${txt("name", "What is it called?", v.name, `Whatever the people who use it call it.${inp.example ? ` For example, ${inp.example}.` : ""}`)}
    ${txt("contains", "What is in it?", v.contains, "", { long: true })}
    ${txt("purpose", "What is it for?", v.purpose, "", { long: true })}
    ${sel("format", "Shape", d.formats || {}, v.format)}
    ${sel("location", "Where it lives", d.locations || {}, v.location)}
    ${lockNote}
    ${sel("reachable", "Can a tool reach it?", d.reachable || {}, v.reachable, "", !tech)}
    ${sel("freshness", "How current it is", d.freshness || {}, v.freshness)}
    ${txt("system", "What system holds it", v.system)}
    <div class="vr-field"><label for="dh-owner">Who owns it</label>
      ${help("dh-owner", "A role, not a person's name. Where the person who knows this is the only person who knows it, that is worth recording too.")}
      ${(inp.absent_says || []).length ? `<p class="small muted">${esc(inp.absent_says.join(" "))}</p>` : ""}
      ${roles.length ? `<select id="dh-owner" aria-describedby="dh-owner-help"><option value="">Nobody named yet</option>
        ${roles.map((r) => `<option${r === v.owner ? " selected" : ""}>${esc(r)}</option>`).join("")}
        <option value="__other"${v.owner && !ownerIsListed ? " selected" : ""}>Another role — say which</option></select>
        <label for="dh-ownerother" class="small" style="display:block">The role, where it is another one
          <input type="text" id="dh-ownerother" value="${esc(v.owner && !ownerIsListed ? v.owner : "")}"></label>`
      : `<input type="text" id="dh-owner" value="${esc(v.owner || "")}" aria-describedby="dh-owner-help">`}</div>
    <fieldset class="vr-tri" aria-describedby="dh-units-help"><legend>Which units use it</legend>
      <p class="small muted vr-help" id="dh-units-help" style="width:100%">Everyone who reads this today. This is what lets
        somebody with a problem find out you already have what they need.</p>
      ${knownUnits.map((u) => `<label><input type="checkbox" name="dh-unit" value="${esc(u)}"${(v.units || []).includes(u) ? " checked" : ""}> ${esc(u)}</label>`).join("")}
      <label style="flex:1 1 100%;flex-direction:column;align-items:stretch">Another unit, or several — separated by commas or one per line
        <textarea id="dh-unitsnew" rows="2"></textarea></label></fieldset>
    <fieldset class="vr-tri" aria-describedby="dh-utility-help"><legend>What is this information good for?</legend>
      <p class="small muted vr-help" id="dh-utility-help" style="width:100%">${esc(d.utility_note)}</p>
      ${utilities.map(([k, l]) => `<label><input type="checkbox" name="dh-utility" value="${esc(k)}"${(v.utility || []).includes(k) ? " checked" : ""}> ${esc(l)}</label>`).join("")}
      ${addedTags.map((t) => `<label><input type="checkbox" name="dh-utility" value="${esc("custom:" + t)}"${(v.utility || []).includes("custom:" + t) ? " checked" : ""}> ${esc(t)}</label>`).join("")}
      <label style="flex:1 1 100%;flex-direction:column;align-items:stretch">Something else — say what
        <input type="text" id="dh-utilitynew"></label></fieldset>
    ${(d.labels || []).length ? `${sel("classification", "Classification", Object.fromEntries(d.labels.map((l) => [l, l])), v.classification, "Your labels, exactly as you wrote them.")}
      ${txt("classwhy", "Why this one (optional)", v.classification_why, "One line, for whoever reads this later.")}` : ""}
    ${txt("endpoint", "Where the interface is, if there is one", v.endpoint, "Watched by the monitor above.", { locked: !tech })}
    ${txt("auth", "How a caller proves who it is", v.auth, "The kind of credential, in a word or two. A key, a token, a certificate, a signed-in account, an address allow-list, nothing at all. Never the credential itself.", { locked: !tech })}
    <p class="small muted">The kind, never the credential. Nothing on this screen should be a secret, and nothing here is ever sent anywhere.</p>
    ${sel("feed", "Is this a live feed something reads from?", d.feed_options || {}, v.feed)}
    <div id="dh-feedbox"${feedOn ? "" : " hidden"}>
      <fieldset class="vr-tri" aria-describedby="dh-readby-help"><legend>What reads from it</legend>
        <p class="small muted vr-help" id="dh-readby-help" style="width:100%">Which of your projects or tools depends on this being
          current. Where something reads it and is not on this list, that is worth knowing before it breaks.</p>
        ${[...(d.projects || []).map((p) => [p.ref, `${p.name} (project)`]), ...(d.tools || []).map((t) => [t.ref, `${t.name} (tool)`])]
          .map(([k, l]) => `<label><input type="checkbox" name="dh-readby" value="${esc(k)}"${(v.feed_read_by || []).includes(k) ? " checked" : ""}> ${esc(l)}</label>`).join("")
          || `<span class="small muted">No projects or tools are recorded yet.</span>`}</fieldset>
      ${sel("expected", "How current it should be", d.currency || {}, v.feed_expected, "Your own expectation, against which lateness is judged. Nothing is assumed.")}
      <p class="small">Last confirmed current: <b>${esc(v.feed_confirmed || "Never confirmed")}</b>.
        ${row ? `<button type="button" class="btn ghost" id="dhConfirm">It is current — confirm today</button>` : ""}</p>
      <p class="small muted">This does not read the contents of any feed, sample records, validate a schema, or check whether
        the numbers are right. It observes that an endpoint answers and it records what a person confirmed.</p></div>
    ${cats.length ? `<fieldset class="vr-tri" aria-describedby="dh-sens-help"><legend>Does it hold any of these?</legend>
      <p class="small muted vr-help" id="dh-sens-help" style="width:100%">Your own categories, from question 7.1. This is the only
        part of the register that can disagree with your framework — leave it blank and nothing here will ever be flagged.</p>
      ${cats.map((c) => `<label><input type="checkbox" name="dh-sensitive" value="${esc(c.value)}"${
        (v.sensitive || []).includes(c.value) ? " checked" : ""}> ${esc(c.label)}${c.banned ? ", you said never" : ""}</label>`).join("")}
    </fieldset>` : ""}
    <div class="row" style="margin-top:14px">
      <button class="btn" id="dhSave" type="button">${row ? "Save changes" : "Add it"}</button>
      ${row ? `<button class="btn ghost" id="dhForget" type="button">Remove from the register</button>` : ""}
    </div>
    <p class="signin-error" id="dhErr" role="alert" hidden></p>`;

  box.querySelectorAll(".info-i").forEach((b) => b.onclick = () => {
    const open = b.getAttribute("aria-expanded") !== "true";
    const text = box.querySelector(`#${b.getAttribute("aria-controls")}`);
    b.setAttribute("aria-expanded", String(open));
    text.hidden = !open;
    // Once open, the field is described by it as well as by its own help.
    const field = box.querySelector(`#${b.getAttribute("aria-controls").replace(/-info$/, "")}`);
    if (field) {
      const ids = (field.getAttribute("aria-describedby") || "").split(" ").filter((x) => x && x !== text.id);
      if (open) ids.unshift(text.id);
      if (ids.length) field.setAttribute("aria-describedby", ids.join(" "));
      else field.removeAttribute("aria-describedby");
    }
  });

  const feed = box.querySelector("#dh-feed");
  feed.onchange = () => { box.querySelector("#dh-feedbox").hidden = !feed.value || feed.value === "no"; };
  const confirmBtn = box.querySelector("#dhConfirm");
  if (confirmBtn) confirmBtn.onclick = async () => {
    const r = await post("/api/holdings/confirm", { id: v.id });
    if (!r || !r.ok) { toast((r && r.error) || "That was not recorded.", true); return; }
    DH.said = `Confirmed current on ${r.on}.`; go("holdings");
  };

  box.querySelector("#dhSave").onclick = async () => {
    const get = (n) => { const f = box.querySelector(`#dh-${n}`); return f ? f.value.trim() : ""; };
    const ticked = (n) => [...box.querySelectorAll(`[name="${n}"]:checked`)].map((c) => c.value);
    let owner = get("owner");
    if (owner === "__other") owner = get("ownerother");
    const typed = get("utilitynew");
    const body = {
      id: v.id || "", name: get("name"), contains: get("contains"), purpose: get("purpose"),
      format: get("format"), location: get("location"), freshness: get("freshness"),
      system: get("system"), owner,
      units: [...ticked("dh-unit"), ...get("unitsnew").split(/[,\n]/).map((s) => s.trim()).filter(Boolean)],
      utility: [...ticked("dh-utility"), ...(typed ? ["custom:" + typed] : [])],
      feed: get("feed"), feed_read_by: ticked("dh-readby"), feed_expected: get("expected"),
      sensitive: cats.length ? ticked("dh-sensitive") : (v.sensitive || []),
    };
    if ((d.labels || []).length) Object.assign(body, { classification: get("classification"), classification_why: get("classwhy") });
    // The technology hat's three fields are sent only by whoever may write
    // them; everybody else reads them.
    if (tech) Object.assign(body, { reachable: get("reachable"), endpoint: get("endpoint"), auth: get("auth") });
    const r = await post("/api/holdings", body);
    if (!r || !r.ok) {
      const err = box.querySelector("#dhErr");
      err.textContent = (r && r.error) || "That could not be saved.";
      err.hidden = false;
      return;
    }
    DH.said = row ? `${body.name} saved.` : `${body.name} added.`;
    go("holdings");
  };

  const forget = box.querySelector("#dhForget");
  if (forget) forget.onclick = () => askConfirm({
    title: "Remove this holding?",
    body: "It comes off the register. Nothing about the system itself "
        + "changes, and your audit trail keeps the record that it was here.",
    confirmLabel: "Remove it",
    onYes: async () => {
      await post("/api/holdings/forget", { id: v.id });
      DH.said = "Removed from the register.";
      go("holdings");
    },
  });
  return box;
}

/* The subscription page.
 *
 * Three decisions shape it, and they are recorded in `app/billing.py`:
 * agencies pay by purchase order *and* by card, no provider is wired yet,
 * and the price is configuration rather than something invented in code.
 *
 * What this page does NOT do, at all: collect a card number, an expiry, a
 * CVC or a wallet credential. There is no such field anywhere in this file.
 * The invoice route needs no instrument, and the card route hands off to a
 * provider's own page. That keeps the card data environment out of scope —
 * which is a statement about scope, not a claim of PCI compliance.
 *
 * It also never decides what anybody is entitled to. The server answers
 * that; this draws the answer.
 */
VIEWS.billing = async () => {
  const d = await api("/api/billing");
  const root = el("div");
  const plan = d.plan || {};
  const held = d.entitlement || {};
  const money = (n, cur) => (n || 0).toLocaleString(undefined,
    { style: "currency", currency: cur || "USD", maximumFractionDigits: 0 });

  /* Where this organization stands, first. Somebody arriving on a billing
     page wants to know what they already have before they are sold
     anything. */
  const now = el("div", "panel");
  const active = held.state === "active";
  now.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${active
      ? "Your subscription is active"
      : held.state === "expired" ? "Your subscription has run out"
      : held.state === "cancelled" ? "Your subscription was canceled"
      : "Your framework is free, and stays yours"}</h2>
    ${active ? `
      <p class="intro">Runs until <b>${esc(niceDate(held.until))}</b>${
        held.days_left !== null && held.days_left !== undefined
          ? ` — ${held.days_left} day${held.days_left === 1 ? "" : "s"} left`
          : ""}. Bought by ${esc(held.route_label || "arrangement")}.</p>`
      : held.state === "expired" ? `
      <p class="intro">It ran until <b>${esc(niceDate(held.until))}</b>. The
        paid modules are closed until it is renewed. Nothing you wrote has
        been touched — your framework, your answers and your registers are
        all still there.</p>`
      : `<p class="intro">Writing your governance framework, versioning it,
        adopting it and downloading the document cost nothing and always
        will. The modules below are the paid addition.</p>`}
    ${d.override ? `
      <p class="bl-off" style="margin-top:12px"><b>Open for evaluation on
        this installation.</b> Every paid module is unlocked here for everyone,
        by a setting on the server rather than by anything your organization
        has bought. Without saying so, this page would be telling you that
        you have no subscription while the modules sat open beside it.</p>`
      : ""}`;
  root.appendChild(now);

  /* What the money buys, read from the rail rather than listed here.
     A second list of paid modules kept in this file would drift, and the
     direction it drifts in is a page promising something that is not
     included. */
  const covers = [...document.querySelectorAll('.rail-item[data-paid="1"]')]
    .map((b) => ({ view: b.dataset.view,
                   name: (META[b.dataset.view] || [b.dataset.view])[0],
                   what: (META[b.dataset.view] || ["", ""])[1] }));

  const what = el("div", "panel");
  what.innerHTML = `
    <h2 class="sub3" style="margin-top:0">What a subscription covers</h2>
    <p class="intro">${covers.length} module${covers.length === 1 ? "" : "s"},
      all of them reading from the framework you have already written.</p>
    <ul class="bl-covers">${covers.map((c) => `<li>
      <b>${esc(c.name)}</b><span>${esc(c.what)}</span></li>`).join("")}</ul>
    <p class="small muted" style="margin-top:12px">Your framework is not on
      this list and never will be. It is the free offering, and finishing it
      does not unlock any of the above — they are a separate purchase.</p>`;
  root.appendChild(what);

  // The price, or an honest absence of one.
  const price = el("div", "panel");
  price.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${plan.amount_set
      ? "Price" : "Pricing"}</h2>
    ${plan.amount_set ? `
      <p class="bl-price"><b>${money(plan.amount, plan.currency)}</b>
        <span>per agency, per ${plan.term_months === 12 ? "year"
          : `${plan.term_months} months`}</span></p>
      <p class="small muted">${esc(plan.currency)}, excluding any sales tax
        your jurisdiction applies. One subscription covers your whole
        organization — there is no per-seat charge.</p>`
      : `<p class="intro">Pricing for your organization is quoted rather than
        listed. Tell us you are interested and we will come back with a
        figure and, if you need one, a formal quotation your procurement
        office can attach to a purchase order.</p>`}`;
  root.appendChild(price);

  // How to buy: by card, through Stripe. The purchase-order-and-invoice
  // option was taken off this page at the team's request (Oct 2026); the
  // invoice route itself still exists on the server, for orders IIA raises.
  const buy = el("div", "panel");
  buy.innerHTML = `
    <h2 class="sub3" style="margin-top:0">How to buy it</h2>

    <div class="bl-route">
      <h3 class="bl-route-h">Card</h3>
      ${d.card_ready ? `
        <div class="row" style="margin:4px 0 12px">
          <button class="btn" id="blCard" type="button">Pay by card</button>
        </div>
        <div id="blStripe" class="bl-stripe" aria-live="polite"></div>
        <p>Pay now on Stripe's own secure page — card, Apple Pay or Google Pay.</p>
        <p class="small muted">Your card details are entered on Stripe's page and never
          pass through this application. Your subscription starts once the payment is
          confirmed, and you will see it on this page.</p>`
      : `<p class="bl-off">${esc(d.card_note || "Not available yet.")}</p>`}
    </div>`;
  root.appendChild(buy);

  // Their own orders. Only theirs — the register is shared, the view is not.
  if ((d.orders || []).length) {
    const orders = el("div", "panel");
    orders.innerHTML = `
      <h2 class="sub3" style="margin-top:0">Your orders</h2>
      <table class="vr-table">
        <thead><tr><th>Raised</th><th>How</th><th>Amount</th>
          <th>State</th><th>Reference</th></tr></thead>
        <tbody>${d.orders.map((o) => `<tr>
          <th scope="row">${esc(niceDate(o.raised_at))}
            <span class="vr-sub">${esc(o.raised_by || "")}</span></th>
          <td>${esc(o.route_label || "")}</td>
          <td>${o.amount_set ? money(o.amount, o.currency)
            : `<span class="muted">to be quoted</span>`}</td>
          <td><span class="bl-state ${esc(o.state)}">${
            esc(String(o.state || "").replace(/_/g, " "))}</span></td>
          <td>${esc(o.reference || "—")}</td>
        </tr>`).join("")}</tbody></table>
      <p class="small muted" style="margin-top:10px">An order is a record of
        what was asked for. It grants nothing until it is paid — see the
        state column.</p>`;
    root.appendChild(orders);
  }

  $("#view").innerHTML = "";
  $("#view").appendChild(root);

  const raise = async (route, button) => {
    button.disabled = true;
    const was = button.textContent;
    button.textContent = "Just a moment…";
    // The route, and nothing about the money. The server reads the amount
    // from the plan; anything posted here would be ignored.
    const r = await post("/api/billing/order", { route });
    button.disabled = false;
    button.textContent = was;
    if (!r || !r.ok) {
      return toast((r && r.error) || "That did not work. Nothing was "
                   + "charged.", true);
    }
    toast(r.reused
      ? "You already have that request open — we have not raised a second."
      : "Thank you. We will come back to you by email.");
    go("billing");
  };

  const card = $("#blCard");
  const sp = d.stripe || {};
  if (card && sp.available) {
    /* Stripe's Buy Button (from IIA's CFO). An order is raised first, so the
       payment can be matched to this organization: the order number goes to
       Stripe as the client reference, with the payer's email. Stripe's
       webhook then marks that order paid — or the GAIUS team does, from the
       Stripe payment reference. */
    card.onclick = async () => {
      card.disabled = true;
      const was = card.textContent;
      card.textContent = "Just a moment…";
      const r = await post("/api/billing/order", { route: "card" });
      card.disabled = false;
      card.textContent = was;
      if (!r || !r.ok) {
        return toast((r && r.error) || "That did not work. Nothing was charged.", true);
      }
      const order = r.order.id;
      const email = registeredEmail();
      if (!document.querySelector('script[src="https://js.stripe.com/v3/buy-button.js"]')) {
        const s = document.createElement("script");
        s.async = true;
        s.src = "https://js.stripe.com/v3/buy-button.js";
        document.head.appendChild(s);
      }
      const link = `${sp.payment_link}?client_reference_id=${encodeURIComponent(order)}`
        + (email ? `&prefilled_email=${encodeURIComponent(email)}` : "");
      const host = $("#blStripe");
      host.innerHTML = `
        <p class="small" style="margin:14px 0 8px">Order <b>${esc(order)}</b> is raised. Pay below —
          it is tagged with this order, so the payment is matched to your organization.</p>
        <stripe-buy-button buy-button-id="${esc(sp.buy_button_id)}"
          publishable-key="${esc(sp.publishable_key)}"
          client-reference-id="${esc(order)}"${email ? ` customer-email="${esc(email)}"` : ""}>
        </stripe-buy-button>
        <p class="small" style="margin-top:8px">Button not showing?
          <a href="${esc(link)}" target="_blank" rel="noopener">Open Stripe's secure payment page</a>
          (opens in a new tab).</p>`;
      card.hidden = true;
    };
  } else if (card) {
    card.onclick = () => raise("card", card);
  }
};

/* Who you buy from, what it costs, and what else those tools could do.

   The client: "the vendor registry; Module will contain a list of vendors,
   costs, and use case potential."

   Same shape as the data register and for the same reason: what the registry
   *found* comes before the registry itself. The findings here are their own
   procurement rules checked one agreement at a time — 8.3's required terms,
   8.5's rule about a vendor adding AI, 8.7's full cost — plus the one that
   needs both paid modules at once: a vendor who can see a holding that
   contains something their 7.1 said must never reach a general-purpose
   tool. */
VIEWS.vendors = async () => {
  const d = await api("/api/vendors");
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    $("#view").appendChild(paidWall(d));
    return;
  }

  const root = el("div");
  const rows = d.vendors || [];
  const win = d.renewal_window || { label: "Renewing soon", says: "" };

  /* §2 · Five counters and the money line. Counts with plain labels, never a
     rate or a grade. "In use today" counts pilots too, as the specification
     defines it; the renewal counter reads the organization's own notice
     period and says so where they set none. */
  const inUse = rows.filter((v) => ["in_use", "pilot"].includes(v.status)).length;
  const withAi = rows.filter((v) => ["core", "feature", "added"]
    .includes(v.involvement)).length;
  const unowned = rows.filter((v) => !String(v.owner || "").trim()).length;
  const head = el("div", "panel");
  head.innerHTML = `
    <p class="intro">One entry per supplier relationship — the company, and
      the thing you get from them. A renewal date and an invoice attach to
      that, which is why it is the unit here. One supplier can serve four
      projects, and a project can have no supplier at all.</p>
    <div class="vr-tiles">
      ${[["Vendors recorded", rows.length], ["In use today", inUse],
         ["With AI in them", withAi], ["Nobody named against it", unowned],
         [win.label, (d.renewing_soon || []).length]]
        .map(([label, n]) => `<div class="vr-tile">
          <b>${n || 0}</b><span>${esc(label)}</span></div>`).join("")}
    </div>
    <p class="small muted" style="margin:10px 0 0">${esc(win.says)}</p>
    <p class="vr-money">${esc(d.money_line || "")}</p>`;
  root.appendChild(head);

  /* §3 · The findings. Each is a contradiction between something recorded
     here and something the organization decided — never an outside
     standard. The one concern kept from the older panel is the Data join,
     which the specification mirrors here from Data. */
  const byId = Object.fromEntries(rows.map((v) => [v.id, v]));
  const findings = d.findings || [];
  const mirrored = (d.concerns || []).filter((c) =>
    String(c.against || "").startsWith("7.1"));
  const flags = el("div", "panel");
  flags.innerHTML = `<h2 class="sub3" style="margin-top:0">${
      findings.length + mirrored.length
        ? `${findings.length + mirrored.length} thing${
            findings.length + mirrored.length === 1 ? "" : "s"} to look at`
        : "Nothing to flag"}</h2>` +
    (findings.length + mirrored.length
      ? `<ul class="vr-flags">${findings.map((f) => {
          const v = byId[f.vendor] || {};
          return `<li><b>${esc(v.name || "")}${v.product
            ? ` — ${esc(v.product)}` : ""}</b> ${esc(f.says)}</li>`;
        }).join("")}${mirrored.map((c) => `<li><b>${esc(c.vendor)}</b>
          ${esc(c.says)} <span class="muted">${esc(c.against)}</span></li>`).join("")}</ul>`
      : `<p class="intro">${esc(d.nothing_to_flag || "")}</p>`);
  root.appendChild(flags);

  // What is about to renew, which is the one thing in here with a deadline.
  const due = d.renewing_soon || [];
  if (due.length) {
    const soon = el("div", "panel");
    soon.innerHTML = `
      <h2 class="sub3" style="margin-top:0">Coming up for renewal</h2>
      <p class="intro">${esc(win.says)} A decision left past this point
        tends to become an automatic renewal somebody explains
        afterward.</p>
      <ul class="vr-flags">${due.map((r) => `<li>
        <b>${esc(r.name)}</b>${r.product ? ` — ${esc(r.product)}` : ""}
        <span class="muted">${r.days < 0
          ? `renewal date passed ${Math.abs(r.days)} day${
              Math.abs(r.days) === 1 ? "" : "s"} ago`
          : r.days === 0 ? "renews today"
          : `renews in ${r.days} day${r.days === 1 ? "" : "s"}`
        } · ${esc(niceDate(r.renewal))}</span></li>`).join("")}</ul>`;
    root.appendChild(soon);
  }

  /* Use case potential — the client's third word, and the answer to their own
     8.6: "before buying something new, must staff check whether an existing
     tool you already have can resolve the problem?" Listed rather than
     matched. A tool that claimed two products overlapped would be guessing at
     a procurement judgment; a person reading these four lines next to each
     other spots it in a second. */
  const potential = (d.vendors || []).filter((v) => v.could_also
    && ["in_use", "pilot"].includes(v.status));
  if (potential.length) {
    const also = el("div", "panel");
    also.innerHTML = `
      <h2 class="sub3" style="margin-top:0">What you already pay for could
        also do this</h2>
      <p class="intro">Your framework says staff must check whether an
        existing tool can solve the problem before buying a new one. This is
        that list. It is not matched for you — read them together and the
        overlap is usually obvious.</p>
      <ul class="vr-flags">${potential.map((v) => `<li>
        <b>${esc(v.name)}${v.product ? ` — ${esc(v.product)}` : ""}</b>
        ${esc(v.could_also)}</li>`).join("")}</ul>`;
    root.appendChild(also);
  }

  root.appendChild(vendorsTable(d));
  root.appendChild(vendorForm(d, null));

  $("#view").innerHTML = "";
  $("#view").appendChild(root);
};

/* A date a person can read. Stored as ISO because that sorts and cannot be
   misread between two countries; shown as "22 Oct 2026" because "2026-10-22"
   in a narrow column wrapped after the month and read as two numbers. */
function niceDate(iso) {
  if (!iso) return "";
  // A full timestamp is stored in UTC; its date is the date where the person
  // reading it is. A bare date is a calendar date and is shown as written.
  const when = /T\d{2}:\d{2}/.test(String(iso)) ? utcTime(iso)
    : new Date(String(iso).slice(0, 10) + "T00:00:00");
  if (!when || isNaN(when)) return iso;
  return when.toLocaleDateString(undefined,
    { day: "numeric", month: "short", year: "numeric" });
}

/* A stored timestamp, read as the UTC it was written in. Stored without a
   zone it is still UTC — every timestamp this server writes is. */
function utcTime(iso) {
  const s = String(iso || "").trim();
  if (!s) return null;
  const zoned = /(Z|[+-]\d{2}:?\d{2})$/.test(s);
  const when = new Date(zoned ? s : s + "Z");
  return isNaN(when) ? null : when;
}

/* When something happened, in the reader's own time: "Sep 24, 2026, 9:38 PM"
   rather than "2026-09-25T01:38" in UTC. A bare date is shown as a date. */
function whenLocal(iso) {
  if (!iso) return "";
  if (!/T\d{2}:\d{2}/.test(String(iso))) return niceDate(iso);
  const when = utcTime(iso);
  if (!when) return String(iso);
  return when.toLocaleString(undefined, { day: "numeric", month: "short",
    year: "numeric", hour: "numeric", minute: "2-digit" });
}

/* Today's date where the person is. `toISOString()` is UTC, so in the
   evening in the United States it was already tomorrow. */
function localToday() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 10);
}

function vendorsTable(d) {
  const box = el("div", "panel");
  const rows = d.vendors || [];
  const money = (n) => (n || 0).toLocaleString(undefined,
    { style: "currency", currency: "USD", maximumFractionDigits: 0 });

  /* §8A · The ten columns. Sorted by renewal date, soonest first — the sort
     that finds what is about to happen. The "Disclosure" column went with
     the tier it displayed: a tier this product no longer has, and a number
     that collided with the organization's own scrutiny levels. */
  const soonest = [...rows].sort((a, b) =>
    (a.renewal || "9999") < (b.renewal || "9999") ? -1 : 1);
  const renews = (v) => {
    if (v.no_renewal) return "No renewal";
    if (!v.renewal) return "—";
    const days = Math.round((new Date(v.renewal + "T00:00:00") - new Date(
      localToday() + "T00:00:00")) / 86400000);
    // A date and a phrase, never a color alone.
    const phrase = days < 0 ? `passed ${-days} day${days === -1 ? "" : "s"} ago`
      : days === 0 ? "renews today"
      : `renews in ${days} day${days === 1 ? "" : "s"}`;
    return `${esc(niceDate(v.renewal))}<span class="vr-sub">${phrase}</span>`;
  };
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Who you buy from</h2>
    ${rows.length ? `<div class="vr-scroll" role="region" tabindex="0"
        aria-label="Vendors, scrolls sideways"><table class="vr-table">
      <thead><tr><th scope="col">The company</th><th scope="col">The product</th>
        <th scope="col">Where it stands</th><th scope="col">Route</th>
        <th scope="col">AI in it</th><th scope="col">Owner</th>
        <th scope="col" class="num">Cost</th><th scope="col">Per</th>
        <th scope="col">Renewal</th><th scope="col">Projects</th>
        <th scope="col"><span class="vh">Edit</span></th></tr></thead>
      <tbody>${soonest.map((v) => `<tr>
        <th scope="row"><b>${esc(v.name)}</b></th>
        <td>${esc(v.product || "—")}</td>
        <td>${esc(v.status_label || "—")}</td>
        <td class="small">${esc((v.route_label || "—").split(" — ")[0])}</td>
        <td class="small">${esc(v.involvement_label || "—")}</td>
        <td>${esc(v.owner || "Nobody named")}</td>
        <td class="num">${v.amount ? money(v.amount) : "—"}</td>
        <td class="small">${esc(v.basis_label || "")}</td>
        <td style="white-space:nowrap">${renews(v)}</td>
        <td class="small">${(v.projects || []).length
          ? (v.projects || []).map(esc).join(", ") : "—"}</td>
        <td><button class="btn ghost" type="button" data-vedit="${esc(v.id)}"
          aria-label="Edit ${esc(v.name)}">Edit</button></td>
      </tr>`).join("")}</tbody></table></div>`
    : `<p class="intro">Nothing recorded yet. Start with the one you would
        have to explain first if somebody asked what AI you are paying
        for.</p>`}`;

  box.querySelectorAll("[data-vedit]").forEach((b) => {
    b.onclick = () => {
      const row = (d.vendors || []).find((v) => v.id === b.dataset.vedit);
      const form = vendorForm(d, row);
      box.parentElement.replaceChild(form, box.nextElementSibling);
      form.scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
  return box;
}

/* Changes the vendor told you about — or made without telling you. Kept in
   their own words, newest first, and never edited or deleted. Recording one
   can open a version record on each project this vendor serves, which is
   what Projects asks for; Integrity counts the change against those
   projects until a check is marked complete after it. */
function vendorChanges(v, projects) {
  const names = Object.fromEntries((projects || []).map((p) => [p.ref, p.name]));
  const serves = (v.projects || []).map((r) => names[r] || r);
  const log = (v.changes || []).slice().reverse();
  return `<section class="vr-tri" style="display:block;margin-top:14px" aria-labelledby="vcH">
    <h3 class="sub4" id="vcH" style="margin-top:0">Changes this vendor made</h3>
    ${log.length ? `<ul class="small">${log.map((c) => `<li><b>${esc(niceDate(c.recorded_on))}</b> —
        ${esc(c.what)} <span class="muted">(${c.not_told ? "we were not told"
          : c.told_on ? `they told us on ${esc(niceDate(c.told_on))}` : "no date given"} · recorded by ${esc(c.by)}${
          (c.versions || []).length ? ` · version record opened on ${(c.versions || []).length} project${(c.versions || []).length === 1 ? "" : "s"}` : ""})</span></li>`).join("")}</ul>`
      : `<p class="small muted">None recorded.</p>`}
    <div class="vr-field"><label for="vc-what">What changed</label>
      <p class="small muted vr-help" id="vc-what-help">Paste what they sent — their words, not a summary.
        If they said nothing, describe what changed.</p>
      <textarea id="vc-what" rows="3" aria-describedby="vc-what-help"></textarea></div>
    <div class="vr-field"><label for="vc-told">When they told you</label>
      <input id="vc-told" type="date"></div>
    <label class="small"><input type="checkbox" id="vc-nottold"> We were not told</label>
    ${serves.length ? `<label class="small" style="display:block;margin-top:6px"><input type="checkbox" id="vc-versions" checked>
        Also open a version record on the project${serves.length === 1 ? "" : "s"} this serves:
        ${esc(serves.join(", "))}</label>`
      : `<p class="small muted">This vendor is not linked to a project yet, so the change is recorded here only.</p>`}
    <p class="signin-error" id="vcErr" role="alert" hidden></p>
    <p><button type="button" class="btn ghost" id="vcGo">Record the change</button></p>
    <p class="small" id="vcSaid" aria-live="polite"></p>
  </section>`;
}

function vendorForm(d, row) {
  const box = el("div", "panel");
  box.id = "vnForm";
  const v = row || {};
  const terms = d.terms || [];
  const parts = d.cost_parts || [];
  const held = d.holdings || [];
  const answers = d.term_answers || { present: "Present", absent: "Absent",
                                      not_asked: "Not asked" };
  // A select for each single-choice field, with a visible label and a
  // blank first choice meaning "not recorded yet".
  const pick = (name, options, chosen, describedBy = "") => `<select
    id="vn-${name}"${describedBy ? ` aria-describedby="${describedBy}"` : ""}>
    <option value="">Not recorded</option>
    ${Object.entries(options).map(([k, label]) =>
      `<option value="${esc(k)}"${k === chosen ? " selected" : ""}>${
        esc(label)}</option>`).join("")}</select>`;
  /* §6.1 and §6.3 · One labeled group per row, three answers and no fourth.
     The term and "you require this" are one string in the legend, so a
     screen reader reads them together without hunting for context. The old
     checkboxes held "present" only, and could not tell a term that was
     absent from one nobody asked about. */
  const rowsOf = (name, list, marked) => list.map((c, i) => `
    <fieldset class="vr-tri">
      <legend>${esc(c.label)}${c.required ? ", you require this" : ""}</legend>
      ${Object.entries(answers).map(([k, label]) => `<label>
        <input type="radio" name="${name}-${i}" value="${esc(k)}"
               data-key="${esc(c.value)}"${
          ((marked || {})[c.value] || "") === k ? " checked" : ""}>
        ${esc(label)}</label>`).join("")}
    </fieldset>`).join("");
  const field = (id, label, input, help = "") => `
    <label class="g-field vr-field"><span>${label}</span>${input}</label>
    ${help ? `<p class="small muted vr-help" id="${id}Help">${help}</p>` : ""}`;
  const text = (name, value, help) => `<input type="text" id="vn-${name}"
    value="${esc(value || "")}"${help ? ` aria-describedby="vn-${name}Help"` : ""}>`;
  const projects = d.projects || [];

  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${row ? "Edit" : "Add"} a vendor</h2>
    <p class="intro">Only the name is required. Come back and fill the rest in
      as you find it. A registry that refuses a row until every box is filled
      is one nobody finishes.</p>

    ${field("vn-name", "The company", text("name", v.name))}
    ${field("vn-product", "The product", text("product", v.product))}
    ${field("vn-what_for", "What you use it for",
      `<textarea id="vn-what_for" rows="2">${esc(v.what_for || "")}</textarea>`)}
    ${field("vn-could_also", "What else it could do",
      `<textarea id="vn-could_also" rows="2" aria-describedby="vn-could_alsoHelp"
        >${esc(v.could_also || "")}</textarea>`,
      "What it is capable of beyond what you bought it for. This is what a " +
      "vendor turns on next year.")}
    ${field("vn-status", "Where it stands", pick("status", d.statuses || {}, v.status))}
    ${field("vn-route", "How it arrived",
      pick("route", d.routes || {}, v.route, "vn-routeHelp"),
      "How this actually turned up, whatever you would have preferred. The " +
      "last one is the ordinary way AI arrives in a government, and it is the " +
      "reason the question is asked. Nothing here treats it as a fault.")}
    ${field("vn-involvement", "How much AI is in it",
      pick("involvement", d.involvement || {}, v.involvement))}
    ${field("vn-owner", "Who owns it — a role", text("owner", v.owner))}
    ${field("vn-amount", "What it costs", text("amount", v.amount ? String(v.amount) : ""))}
    ${field("vn-basis", "Per", pick("basis", d.bases || {}, v.basis))}
    ${field("vn-contract", "Agreement reference", text("contract", v.contract))}
    ${field("vn-renewal", "Renewal date",
      `<input type="date" id="vn-renewal" value="${esc(v.renewal || "")}">`)}
    <label class="vr-check"><input type="checkbox" id="vn-no_renewal"${
      v.no_renewal ? " checked" : ""}> <span>There is no renewal</span></label>

    <fieldset class="vr-sens">
      <legend>Which projects use this</legend>
      ${projects.length ? projects.map((p) => `<label class="vr-check">
        <input type="checkbox" name="vn-projects" value="${esc(p.ref)}"${
          (v.projects || []).includes(p.ref) ? " checked" : ""}>
        <span>${esc(p.name)} <span class="mono">${esc(p.ref)}</span></span></label>`).join("")
        : `<p class="small muted">No projects yet. A vendor with no project is
            fine — it may be one you are still looking at.</p>`}
    </fieldset>

    <fieldset class="vr-sens">
      <legend>What the vendor has to tell you</legend>
      ${field("vn-criticality", "Does it decide anything about anyone?",
        pick("criticality", d.criticality || {}, v.criticality))}
      ${field("vn-facing", "Who uses it", pick("facing", d.facing || {}, v.facing))}
      ${row && v.must_tell_you ? `<div class="vr-tell">
        <p><b>What ${esc(v.name || "this vendor")} has to tell you.</b>
          ${esc(v.must_tell_you.says)}</p>
        ${v.must_tell_you.because
          ? `<p class="small muted">${esc(v.must_tell_you.because)}</p>` : ""}
      </div>` : ""}
    </fieldset>

    <fieldset class="vr-sens">
      <legend>Do they use our information to improve their product?</legend>
      ${field("vn-training", "Their answer", pick("training", d.training || {}, v.training))}
      <p class="small vr-warn" id="vnTrainingWhy"${
        v.training && v.training !== "no" ? "" : " hidden"}>${
        esc(d.training_consequence || "")}</p>
      <div id="vnOptOut"${v.training === "opt_out" ? "" : " hidden"}>
        ${field("vn-opted_out", "Have you actually opted out?",
          pick("opted_out", d.opted_out || {}, v.opted_out))}
        <p class="small muted">An opt-out nobody exercised is the same as no
          term.</p>
        ${field("vn-opted_out_on", "When you opted out",
          `<input type="date" id="vn-opted_out_on" value="${esc(v.opted_out_on || "")}">`)}
        ${field("vn-opted_out_by", "Who did it — a role", text("opted_out_by", v.opted_out_by))}
      </div>
      <p class="small muted">${esc(d.training_not_listed || "")}</p>
    </fieldset>

    ${field("vn-accessibility", "Accessibility conformance",
      pick("accessibility", d.accessibility || {}, v.accessibility))}

    ${terms.length ? `<fieldset class="vr-sens">
      <legend>Which of these terms are actually in this agreement?</legend>
      <p class="small muted">Your own list, from question 8.3. Marking one you
        require as absent is what produces a finding above.</p>
      ${rowsOf("vn-term", terms, v.terms)}
    </fieldset>` : `<p class="small muted">Your framework has not listed the
      terms every agreement needs yet (question 8.3). Once it does, each one
      appears here to mark.</p>`}

    ${parts.length ? `<fieldset class="vr-sens">
      <legend>Which costs were estimated before you committed?</legend>
      <p class="small muted">From question 8.7 — what you said counts as cost.
        The figures themselves live on Budget.</p>
      ${rowsOf("vn-cost", parts, v.costed)}
    </fieldset>` : ""}

    <fieldset class="vr-sens">
      <legend>How the vendor has behaved</legend>
      <p class="small muted">Recorded facts for whoever decides whether to buy
        from them again. None of this is a score or a rating.</p>
      ${field("vn-behaved_notice", "Did they tell you before changes?",
        pick("behaved_notice", (d.behaved || {}).notice || {}, v.behaved_notice))}
      ${field("vn-behaved_staging", "Did they give you a testing environment?",
        pick("behaved_staging", (d.behaved || {}).staging || {}, v.behaved_staging))}
      ${field("vn-behaved_answers", "Did they answer your questions about the AI?",
        pick("behaved_answers", (d.behaved || {}).answers || {}, v.behaved_answers))}
      ${field("vn-behaved_renewal", "At renewal",
        pick("behaved_renewal", (d.behaved || {}).renewal || {}, v.behaved_renewal))}
      ${field("vn-behaved_note", "Anything worth telling the next person",
        `<textarea id="vn-behaved_note" rows="2" aria-describedby="vn-behaved_noteHelp"
          >${esc(v.behaved_note || "")}</textarea>`,
        "One or two lines for whoever handles this in three years. Plain " +
        "facts, not a review.")}
    </fieldset>

    ${held.length ? `<fieldset class="vr-sens">
      <legend>What can this vendor see?</legend>
      <p class="small muted">From your data register. This is what lets the
        registry notice a vendor who can reach something you said must never
        go into a general-purpose tool.</p>
      ${held.map((h) => `<label class="vr-check">
        <input type="checkbox" name="vn-holdings" value="${esc(h.id)}"${
          (v.holdings || []).includes(h.id) ? " checked" : ""}>
        <span>${esc(h.name)}</span></label>`).join("")}
    </fieldset>` : `<p class="small muted">Record what you hold in the Data
      section and you will be able to say which of it each vendor can
      see.</p>`}

    <label class="g-field"><span>Anything else worth recording</span>
      <textarea id="vn-notes" rows="2">${esc(v.notes || "")}</textarea></label>
    <p class="small muted">No contract text, no invoices, no payment details.
      This is a governance register, not a ledger.</p>
    ${row ? vendorChanges(v, projects) : ""}
    <div class="row" style="margin-top:14px">
      <button class="btn" id="vnSave" type="button">${
        row ? "Save changes" : "Add it"}</button>
      ${row ? `<button class="btn ghost" id="vnForget" type="button">Remove
        from the registry</button>` : ""}
    </div>
    <p class="signin-error" id="vnErr" hidden></p>`;

  // Recording a change the vendor made: its own button, apart from saving
  // the entry, so the change log is never rewritten by an edit.
  const chGo = box.querySelector("#vcGo");
  if (chGo) chGo.onclick = async () => {
    const err = box.querySelector("#vcErr"), said = box.querySelector("#vcSaid");
    err.hidden = true; said.textContent = "";
    const what = box.querySelector("#vc-what").value.trim();
    if (!what) { err.textContent = "Paste what they said changed, or describe it."; err.hidden = false;
      box.querySelector("#vc-what").focus(); return; }
    chGo.disabled = true;
    const notTold = box.querySelector("#vc-nottold").checked;
    const r = await post("/api/vendors/change", { id: v.id, what,
      told_on: notTold ? "" : box.querySelector("#vc-told").value,
      not_told: notTold,
      open_versions: !!(box.querySelector("#vc-versions") || {}).checked });
    chGo.disabled = false;
    if (!r || !r.ok) { err.textContent = (r && r.error) || "That was not recorded."; err.hidden = false; return; }
    const opened = (r.change.versions || []).length;
    const note = `Recorded.${opened ? ` A version record was opened on ${opened} project${opened === 1 ? "" : "s"}.` : ""}`;
    const fresh = vendorForm(d, r.vendor);
    box.replaceWith(fresh);
    const s = fresh.querySelector("#vcSaid");
    if (s) s.textContent = note;
    const h = fresh.querySelector("#vcH");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  };
  const notToldBox = box.querySelector("#vc-nottold");
  if (notToldBox) notToldBox.onchange = () => {
    box.querySelector("#vc-told").disabled = notToldBox.checked;
  };

  // The opt-out questions exist only where the answer relied on one, and the
  // consequence sentence only where the answer is anything but no.
  const training = box.querySelector("#vn-training");
  training.onchange = () => {
    box.querySelector("#vnOptOut").hidden = training.value !== "opt_out";
    box.querySelector("#vnTrainingWhy").hidden =
      !training.value || training.value === "no";
  };

  box.querySelector("#vnSave").onclick = async () => {
    const get = (n) => {
      const field = box.querySelector(`#vn-${n}`);
      return field ? field.value.trim() : "";
    };
    const ticked = (name) =>
      [...box.querySelectorAll(`[name="${name}"]:checked`)].map((c) => c.value);
    // Three answers per row, collected as a record keyed by the term. A row
    // left unanswered is simply not recorded, which is honest: it was not.
    const marked = (prefix) => {
      const out = {};
      box.querySelectorAll(`input[type=radio][name^="${prefix}-"]:checked`)
        .forEach((r) => { out[r.dataset.key] = r.value; });
      return out;
    };
    const r = await post("/api/vendors", {
      id: v.id || "", name: get("name"), product: get("product"),
      what_for: get("what_for"), could_also: get("could_also"),
      status: get("status"), route: get("route"),
      involvement: get("involvement"),
      owner: get("owner"), amount: get("amount"), basis: get("basis"),
      contract: get("contract"), renewal: get("renewal"),
      no_renewal: box.querySelector("#vn-no_renewal").checked,
      criticality: get("criticality"), facing: get("facing"),
      training: get("training"), accessibility: get("accessibility"),
      opted_out: get("opted_out"), opted_out_on: get("opted_out_on"),
      opted_out_by: get("opted_out_by"),
      behaved_notice: get("behaved_notice"),
      behaved_staging: get("behaved_staging"),
      behaved_answers: get("behaved_answers"),
      behaved_renewal: get("behaved_renewal"),
      behaved_note: get("behaved_note"),
      notes: get("notes"),
      terms: terms.length ? marked("vn-term") : (v.terms || {}),
      costed: parts.length ? marked("vn-cost") : (v.costed || {}),
      projects: ticked("vn-projects"),
      holdings: held.length ? ticked("vn-holdings") : (v.holdings || []),
    });
    if (!r || !r.ok) {
      const err = box.querySelector("#vnErr");
      err.textContent = (r && r.error) || "That could not be saved.";
      err.hidden = false;
      return;
    }
    go("vendors");
  };

  const forget = box.querySelector("#vnForget");
  if (forget) forget.onclick = () => askConfirm({
    title: "Remove this vendor?",
    body: "It comes off the registry. Nothing about the agreement itself "
        + "changes, and your audit trail keeps the record that it was here.",
    confirmLabel: "Remove it",
    onYes: async () => {
      await post("/api/vendors/forget", { id: v.id });
      go("vendors");
    },
  });
  return box;
}

VIEWS.agency = async () => {
  const d = await api("/api/profile");
  const withheld = notYours(d);
  if (withheld) { $("#view").innerHTML = ""; $("#view").appendChild(withheld); return; }
  const root = el("div");

  const head = el("div", "panel");
  head.innerHTML =
    `<p class="intro">Everything below was read out of the corpus on first run —
     no agency, instrument set, checkpoint structure or program list is written
     into this application. Point it at another agency's documents and it
     re-derives all of it.</p>
     <table><tbody>
     <tr><th>Agency</th><td><b>${esc(d.name || "—")}</b>
       ${d.short_name ? `<span class="pill neutral">${esc(d.short_name)}</span>` : ""}</td></tr>
     <tr><th>Jurisdiction</th><td>${esc(d.jurisdiction || "—")}</td></tr>
     <tr><th>Adopted</th><td>${esc(d.adoption_date || "not stated in the corpus")}
       <br><span class="small muted">${esc(d.adoption_source || "")}</span></td></tr>
     <tr><th>Naming rule</th><td class="small">${esc(d.naming_rule || "—")}</td></tr>
     <tr><th>Discovered</th><td class="mono">${esc(d.discovered_at || "")}</td></tr>
     </tbody></table>`;
  root.appendChild(head);

  const inst = el("div", "panel");
  inst.innerHTML = `<h2 class="sub3" style="margin-top:0">Instruments —
    this agency calls them “${esc(d.instrument_noun)}”, and there are
    ${d.instruments.length}</h2>
    <table><thead><tr><th>Key</th><th>Title</th><th>Recognized as</th>
    <th class="num">Fields</th></tr></thead><tbody>` +
    d.instruments.map((i) => `<tr><td><b>${esc(i.key)}</b></td>
      <td>${esc(i.title || "—")}</td>
      <td>${i.role ? `<span class="pill info">${esc(i.role.replace(/_/g, " "))}</span>`
        : '<span class="pill neutral">unrecognized</span>'}</td>
      <td class="num">${i.fields || "—"}</td></tr>`).join("") + `</tbody></table>`;
  root.appendChild(inst);

  const life = el("div", "panel");
  life.innerHTML = `<h2 class="sub3" style="margin-top:0">Lifecycle —
    called “${esc(d.gate_noun)}”, ${d.gates.length} of them</h2>` +
    (d.gates.length ? d.gates.map((g) =>
      `<div class="req"><span class="n">${esc(g.key)}</span>
       <span class="t">${esc(g.name)}</span>
       <span class="small muted">${g.requirements} requirements</span></div>`).join("")
      : `<p class="muted">None discovered.</p>`);
  root.appendChild(life);

  const who = el("div", "panel");
  who.innerHTML = `<h2 class="sub3" style="margin-top:0">Read from the corpus</h2>
    <p class="gh">Roles named in the governing documents</p>
    ${d.roles.map((r) => `<span class="pill neutral">${esc(r)}</span> `).join("") || "—"}
    <p class="gh" style="margin-top:14px">Operating units (from the intake form's own picker)</p>
    ${d.org_units.map((u) => `<span class="pill neutral">${esc(u)}</span> `).join("") || "—"}
    <p class="gh" style="margin-top:14px">Statutory programs referenced</p>
    ${d.statutory_programmes.map((p) => `<span class="pill info">${esc(p)}</span> `).join("") || "—"}`;
  if (d.notes && d.notes.length)
    who.innerHTML += `<div class="impact" style="margin-top:14px"><b>Gaps in discovery:</b><ul>` +
      d.notes.map((n) => `<li>${esc(n)}</li>`).join("") + `</ul></div>`;

  if (d.can_edit) {
    const row = el("div", "row");
    const b = el("button", "btn ghost", "Re-read the corpus");
    b.onclick = async () => {
      const r = await post("/api/profile/rediscover", {});
      toast(r.rediscovered ? "Profile re-derived from the corpus." : r.reason,
            !r.rediscovered);
      await refreshState(); go("agency");
    };
    row.appendChild(b);
    row.appendChild(el("span", "note",
      "Run this after the agency amends or replaces a document."));
    who.appendChild(row);
  }
  root.appendChild(who);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why this exists", body: "The application is not built for one agency. It is pointed at an adopted corpus and works out whose it is, what the instruments are called, how many there are, and what the lifecycle looks like.", cite: "Discovered from the corpus; confirmed by OT" },
    { title: "What is never assumed", body: "That instruments are lettered A–N, that there are six gates, that the agency is environmental, or that a charter exists with a legible date. Each is read, and reported as a gap when it cannot be.", cite: "app/profile.py" },
  ]);
};

/* Integrity — does it work, and is it still working. One entry per check or
   per incident: one occasion when somebody looked, or one occasion when it
   went wrong. Replaces the older screen that audited one agency's corpus;
   that audit named another organization's documents and has no place on a
   screen every organization sees. */
const IG = { group: "grouped", sort: "", kind: "both", unanswered: false,
             form: "" };

VIEWS.integrity = async () => {
  const d = await api("/api/checks");
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    const p = el("div", "panel");
    p.innerHTML = `<p class="intro">${esc(d.why || "This is part of the subscription.")}</p>`;
    $("#view").appendChild(p);
    return;
  }
  const inp = d.inputs || {};
  const rb = inp.readbacks || {};
  const copy = d.copy || {};
  const opt = d.options || {};
  const projects = d.projects || [];
  const byRef = Object.fromEntries(projects.map((p) => [p.ref, p]));
  const root = el("div");
  const live = el("p", "vh");
  live.setAttribute("aria-live", "polite");
  root.appendChild(live);

  // §1 · the header block, and the skip links §17 asks for.
  const head = el("div", "panel");
  head.innerHTML = `
    <p class="intro" style="margin-top:0">One entry per check or per incident —
      one occasion when somebody looked, or one occasion when it went wrong.</p>
    <p class="small"><a href="#igFindings">Skip to the findings</a> ·
      <a href="#igList">Skip to the list</a></p>
    <div class="row" style="gap:8px;flex-wrap:wrap">
      <button type="button" class="btn" id="igNewCheck">Record a check</button>
      <button type="button" class="btn ghost" id="igNewIncident">Write down an incident</button>
    </div>`;
  root.appendChild(head);

  // §3 · five counters, always five, always in this order.
  const c = d.counters || {};
  const fifth = d.fifth || {};
  const stats = el("section", "panel");
  stats.setAttribute("aria-label", "Counts");
  stats.innerHTML = `<div class="vr-tiles">${[
      [c.checks_recorded, "Checks recorded"],
      [c.looked_at_this_cycle, "Looked at this cycle"],
      [c.never_checked, "Never checked"],
      [c.past_due, "Past due for a look"],
      [fifth.count, fifth.label || "Look-backs owed"]]
    .map(([n, label]) => `<div class="vr-tile"><b>${n || 0}</b>
      <span>${esc(label)}</span></div>`).join("")}</div>
    ${fifth.says ? `<p class="small muted" style="margin:10px 0 0">${esc(fifth.says)}</p>` : ""}`;
  root.appendChild(stats);

  // §4 · the findings panel, and §5 · the recommendation in its own block.
  const entryName = (ref) => {
    const row = (d.entries || []).find((e) => e.ref === ref);
    if (row) return `${row.kind === "check" ? "Check" : "Incident"} ${ref} · ${row.about}`;
    return (byRef[ref] || {}).name || ref;
  };
  const raised = d.raised || [];
  const findings = el("section", "panel");
  findings.id = "igFindings";
  findings.setAttribute("aria-labelledby", "igFindingsH");
  findings.innerHTML = `
    <h2 class="sub3" id="igFindingsH" style="margin-top:0">${raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"}` : "Nothing to flag"}</h2>
    <p class="small muted">${esc(d.findings_are_comparisons)}</p>
    ${raised.length
      ? `<ul class="vr-flags">${raised.map((f) => `<li><b>${esc(entryName(f.entry))}</b>
          ${esc(f.says)}</li>`).join("")}</ul>`
      : `<p class="intro">${esc(d.nothing_to_flag)}</p>`}`;
  root.appendChild(findings);

  const recs = (d.recommended || []);
  if (recs.length) {
    const rec = el("section", "panel");
    rec.setAttribute("aria-labelledby", "igRecH");
    const r = d.recommendation || {};
    rec.innerHTML = `
      <h2 class="sub3" id="igRecH" style="margin-top:0">${recs.length} recommendation${
        recs.length === 1 ? "" : "s"} · nothing here has to be done</h2>
      <p style="margin:0 0 6px"><b>${esc(r.says)}</b></p>
      <ul class="vr-flags">${recs.map((x) => `<li>
        <b>${esc(entryName(x.entry))}</b> ${esc(x.reason)}
        <span class="muted">${x.state === "offered" ? "Not answered yet"
          : x.state === "accepted" ? "Accepted" : "Declined"}</span>
        ${x.state === "offered" ? `<span class="row" style="gap:8px;margin-top:6px">
          <button type="button" class="btn ghost" data-rec="${esc(x.entry)}" data-state="accepted">Accept</button>
          <button type="button" class="btn ghost" data-rec="${esc(x.entry)}" data-state="declined">Decline</button>
        </span>` : ""}</li>`).join("")}</ul>`;
    rec.querySelectorAll("[data-rec]").forEach((b) => b.onclick = async () => {
      const out = await post("/api/checks/recommendation",
        { entry: b.dataset.rec, state: b.dataset.state });
      if (out && out.ok) { go("integrity"); }
    });
    root.appendChild(rec);
  }
  const recLive = el("p", "vh");
  recLive.setAttribute("aria-live", "polite");
  root.appendChild(recLive);

  // §6 · the two watches, and what they cannot do.
  const due = d.due_watch || {};
  const chg = d.change_watch || {};
  const watches = el("section", "panel");
  watches.setAttribute("aria-label", "The due watch and the change watch");
  watches.innerHTML = `
    <h2 class="sub3" style="margin-top:0">The due watch</h2>
    <p class="small muted">${esc(due.says)}</p>
    <div class="vr-tiles">${[[due.watched, "Watched"],
      [due.inside_your_window, "Looked at within your own window"],
      [due.past_due, "Past due"],
      [due.no_interval_set, "No interval set at this level"]]
      .map(([n, l]) => `<div class="vr-tile"><b>${n || 0}</b><span>${esc(l)}</span></div>`).join("")}</div>
    ${(due.lines || []).filter((l) => l.state !== "Looked at within your own window").length
      ? `<ul class="vr-flags">${due.lines.filter((l) =>
          l.state !== "Looked at within your own window").map((l) => `<li>
          <b>${esc((byRef[l.project] || {}).name || l.project)}</b> ${esc(l.state)}${
          l.days_over ? ` — ${l.days_over} day${l.days_over === 1 ? "" : "s"} over` : ""}
          <span class="muted">${l.last_looked ? `Last looked ${esc(niceDate(l.last_looked))}`
            : "Nobody has looked"}${l.level ? ` · ${esc(l.level)}` : ""}${
            l.beside_the_date ? ` · ${esc(l.beside_the_date)}` : ""}</span></li>`).join("")}</ul>` : ""}
    <p><button type="button" class="btn ghost" id="igDue">Work out what is due now</button></p>
    <h2 class="sub3">The change watch</h2>
    <p class="small muted">${esc(chg.says)}</p>
    <div class="vr-tiles">${[[chg.changes_recorded, "Changes recorded"],
      [chg.tools_touched, "Tools touched"], [chg.answered, "Answered"],
      [chg.not_yet_answered, "Not yet answered"],
      [chg.live_with_no_check, "Versions live with no check"]]
      .map(([n, l]) => `<div class="vr-tile"><b>${n || 0}</b><span>${esc(l)}</span></div>`).join("")}</div>
    <p><button type="button" class="btn ghost" id="igUnanswered" aria-pressed="${IG.unanswered}">
      Show me the ones nobody has answered</button></p>
    <details><summary>What these two watches cannot do</summary>
      ${String(d.watches_cannot || "").split("\n\n").map((p) => `<p class="small">${esc(p)}</p>`).join("")}
      <p class="small">${esc(d.never_emails)}</p></details>`;
  // Recomputed on the server at every read, so asking is a fresh read and an
  // announcement of what it found.
  watches.querySelector("#igDue").onclick = () => { IG.dueAsked = true; go("integrity"); };
  watches.querySelector("#igUnanswered").onclick = () => {
    IG.unanswered = !IG.unanswered; go("integrity");
  };
  root.appendChild(watches);

  // §7 · the list. One table holding both kinds of entry.
  root.appendChild(integrityList(d, byRef));

  // The public page — 16E. Reached by an unguessable link.
  const pub = el("section", "panel");
  pub.setAttribute("aria-labelledby", "igPubH");
  const full = d.public_link ? location.origin + d.public_link : "";
  pub.innerHTML = `
    <h2 class="sub3" id="igPubH" style="margin-top:0">Reporting without a login</h2>
    <p class="intro">Anyone can write an incident down, including somebody with no
      login and no role here. They use a page of its own, with a link only you
      hand out — it is not listed anywhere, and nobody can find it by guessing.</p>
    ${full ? `<p><label for="igPubLink" class="small">Your page</label>
        <input id="igPubLink" type="text" readonly value="${esc(full)}" style="width:100%"></p>
      <p class="row" style="gap:8px;flex-wrap:wrap">
        <button type="button" class="btn ghost" id="igPubNew">Replace the link</button>
        <button type="button" class="btn ghost" id="igPubStop">Stop the page</button></p>
      <p class="small muted">Replacing it stops the old link at once. Reports already
        written stay on the list.</p>`
      : `<p><button type="button" class="btn ghost" id="igPubNew">Make the page</button></p>`}`;
  const pubDo = async (action) => {
    const out = await post("/api/checks/public-link", { action });
    if (out && out.ok) go("integrity");
    else toast((out && out.error) || "That did not work.", true);
  };
  pub.querySelector("#igPubNew").onclick = () => pubDo("make");
  const stopBtn = pub.querySelector("#igPubStop");
  if (stopBtn) stopBtn.onclick = () => pubDo("stop");
  root.appendChild(pub);

  // §15B · scope, and the legal line, in the same place.
  const scope = el("div", "panel");
  scope.innerHTML = `<p class="small">${esc(copy.scope)}</p>
    <p class="small">${esc(copy.legal)}</p>`;
  root.appendChild(scope);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  live.textContent = IG.dueAsked
    ? `Worked out. ${due.watched || 0} watched, ${due.past_due || 0} past due, ${
        due.no_interval_set || 0} with no interval set.`
    : raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"} on this surface.` : "";
  if (IG.dueAsked) { IG.dueAsked = false; const b = $("#igDue"); if (b) b.focus(); }
  recLive.textContent = recs.filter((x) => x.state === "offered").length
    ? `${recs.length} recommendation${recs.length === 1 ? "" : "s"} on this surface. Nothing here has to be done.` : "";

  const open = (kind) => {
    IG.form = kind;
    const host = el("section", "panel");
    host.id = "igForm";
    const existing = $("#igForm"); if (existing) existing.remove();
    head.after(host);
    (kind === "check" ? checkForm : incidentForm)(host, d, byRef);
    const first = host.querySelector("h2");
    if (first) { first.setAttribute("tabindex", "-1"); first.focus(); }
  };
  $("#igNewCheck").onclick = () => open("check");
  $("#igNewIncident").onclick = () => open("incident");
  if (IG.form) { const f = IG.form; IG.form = ""; open(f); }
};

/* §7 · the list view — grouped by project by default, or straight down the
   page by date. Real table semantics, a caption naming the sort, and a
   horizontally scrollable region that a keyboard can reach. */
function integrityList(d, byRef) {
  const box = el("section", "panel");
  box.id = "igList";
  box.setAttribute("aria-labelledby", "igListH");
  let rows = (d.entries || []).slice();
  if (IG.kind !== "both") rows = rows.filter((r) => r.kind === IG.kind);
  if (IG.unanswered) rows = rows.filter((r) => r.kind === "check"
    && r.occasion === "A look after something changed" && !r.complete);

  const sorts = ["Most recent first", "Oldest first", "By project, A to Z",
                 "Open incidents first", "Checks with no limits first"];
  const sort = IG.sort || "Most recent first";
  const when = (r) => r.at || r.written_down || "";
  const cmp = {
    "Most recent first": (a, b) => when(b).localeCompare(when(a)),
    "Oldest first": (a, b) => when(a).localeCompare(when(b)),
    "By project, A to Z": (a, b) => String(a.about).localeCompare(String(b.about)),
    "Open incidents first": (a, b) =>
      ((b.kind === "incident" && b.closed !== "Closed") - (a.kind === "incident" && a.closed !== "Closed"))
      || when(b).localeCompare(when(a)),
    "Checks with no limits first": (a, b) =>
      ((b.kind === "check" && !b.limits) - (a.kind === "check" && !a.limits))
      || when(b).localeCompare(when(a)),
  }[sort];
  rows.sort(cmp);

  const stateOf = (r) => r.kind === "check"
    ? (r.complete ? "Complete" : "Still being written")
    : (r.closed === "Closed" ? `Closed${r.closed_at ? " " + niceDate(r.closed_at) : ""}` : "Still open");
  const cells = (r) => `
    <td>${r.kind === "check" ? "A check" : "An incident"}<br>
      <span class="small muted">${esc(r.ref)}</span></td>
    <th scope="row">${esc(r.about)}</th>
    <td>${esc(r.version_shown)}</td>
    <td>${esc(r.gate_shown)}</td>
    <td>${esc(r.date_shown)}</td>
    <td>${esc([r.who || r.by, r.who_name, r.outside_organisation].filter(Boolean).join(" · ")
      || (r.kind === "incident" && !r.signed_in ? "Reported without a login" : ""))}</td>
    <td>${esc(r.where_shown)}</td>
    <td>${esc(String(r.found || r.what_happened || "").split("\n")[0].slice(0, 140))}</td>
    <td>${esc(r.limits_shown)}</td>
    <td>${esc(r.kind === "incident" ? r.severity : "")}</td>
    <td>${esc(stateOf(r))}${r.kind === "check" && !r.complete
      ? `<br><button type="button" class="btn ghost" data-complete="${esc(r.ref)}"
          aria-describedby="igRefusal-${esc(r.ref)}">Mark complete</button>
         <span class="small" id="igRefusal-${esc(r.ref)}" role="alert"></span>` : ""}
      ${(r.attached || []).map((a) => `<br><button type="button" class="linky" data-att="${esc(a.id)}">Open ${esc(a.name)}</button>`).join("")}
      ${r.editable && (r.yours || d.decides) ? `<br><button type="button" class="btn ghost" data-edit="${esc(r.ref)}" aria-label="Change ${esc(r.ref)}">Change it</button>` : ""}
      ${r.kind === "check" && r.complete ? `<br><button type="button" class="btn ghost" data-correct="${esc(r.ref)}" aria-label="Correct ${esc(r.ref)} with a new check">Correct it</button>` : ""}
      ${r.corrects ? `<br><span class="small muted">Corrects ${esc(r.corrects)}</span>` : ""}
      ${r.kind === "incident" && r.closed === "Closed" ? `<br><button type="button" class="btn ghost" data-reopen="${esc(r.ref)}" aria-label="Reopen ${esc(r.ref)}">Reopen it</button>` : ""}
      ${(r.reopened || []).length ? `<br><span class="small muted">Reopened ${r.reopened.length} time${r.reopened.length === 1 ? "" : "s"}</span>` : ""}
      ${r.kind === "incident" && r.project && r.stopped !== "Yes, stopped" && (d.stoppers || []).length
        ? `<br><button type="button" class="btn ghost" data-stop="${esc(r.ref)}" aria-label="Stop the tool in ${esc(r.ref)} now">Stop it now</button>` : ""}</td>
    <td>${r.open_findings ? r.open_findings : ""}</td>`;

  let body = "";
  if (IG.group === "grouped") {
    const groups = {};
    rows.forEach((r) => { (groups[r.project || r.about] ||= []).push(r); });
    const last = (list) => list.filter((r) => r.kind === "check" && r.complete)
      .map(when).sort().pop() || "";
    Object.entries(groups)
      .sort(([, a], [, b]) => last(a).localeCompare(last(b)))
      .forEach(([key, list]) => {
        const name = (byRef[key] || {}).name || list[0].about;
        const l = last(list);
        body += `<tr><th scope="rowgroup" colspan="12" class="ig-group">${esc(name)}
          <span class="small muted">· ${l ? `last looked ${esc(niceDate(l))}` : "nobody has recorded a complete check"}</span></th></tr>`;
        body += list.map((r) => `<tr>${cells(r)}</tr>`).join("");
      });
  } else {
    body = rows.map((r) => `<tr>${cells(r)}</tr>`).join("");
  }

  const heads = ["Kind", "About", "Version", "Gate", "Date", "Who", "Where",
                 "What was found", "Limits", "Level", "State", "Findings"];
  box.innerHTML = `
    <h2 class="sub3" id="igListH" style="margin-top:0">Checks and incidents</h2>
    <div class="row" style="gap:16px;flex-wrap:wrap;align-items:flex-end">
      <fieldset class="vr-tri" style="border-top:0">
        <legend>Show</legend>
        ${[["grouped", "Grouped by project"], ["flat", "Straight down the page by date"]]
          .map(([v, l]) => `<label><input type="radio" name="igGroup" value="${v}"${
            IG.group === v ? " checked" : ""}> ${l}</label>`).join("")}
      </fieldset>
      <label class="vr-field" style="margin:0">Sort
        <select id="igSort">${sorts.map((s) => `<option${s === sort ? " selected" : ""}>${s}</option>`).join("")}</select></label>
      <label class="vr-field" style="margin:0">Kind
        <select id="igKind">${[["both", "Checks and incidents"], ["check", "Checks"], ["incident", "Incidents"]]
          .map(([v, l]) => `<option value="${v}"${IG.kind === v ? " selected" : ""}>${l}</option>`).join("")}</select></label>
    </div>
    ${rows.length ? `<div class="vr-scroll" tabindex="0" role="region" aria-labelledby="igListH">
      <table class="vr-table">
        <caption class="vh">Checks and incidents, ${esc(IG.group === "grouped"
          ? "grouped by project" : "by date")}, sorted ${esc(sort.toLowerCase())}</caption>
        <thead><tr>${heads.map((h) => `<th scope="col">${h}</th>`).join("")}</tr></thead>
        <tbody>${body}</tbody></table></div>`
      : `<p class="intro">${esc(IG.unanswered ? "Nothing here is waiting on an answer."
          : (d.entries || []).length ? "Nothing matches what is chosen above." : d.empty_state)}</p>`}`;

  box.querySelectorAll('[name="igGroup"]').forEach((r) =>
    r.onchange = () => { IG.group = r.value; go("integrity"); });
  box.querySelector("#igSort").onchange = (e) => { IG.sort = e.target.value; go("integrity"); };
  box.querySelector("#igKind").onchange = (e) => { IG.kind = e.target.value; go("integrity"); };
  box.querySelectorAll("[data-complete]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/checks/complete", { ref: b.dataset.complete });
    if (out && out.ok) { go("integrity"); return; }
    const said = box.querySelector(`#igRefusal-${b.dataset.complete}`);
    if (said) said.textContent = (out && out.error) || "";
  });
  box.querySelectorAll("[data-att]").forEach((b) => b.onclick = () => igDownload(b.dataset.att));
  box.querySelectorAll("[data-correct]").forEach((b) => b.onclick = () => {
    IG.corrects = b.dataset.correct; IG.form = "check"; go("integrity"); });
  const byEntry = Object.fromEntries((d.entries || []).map((r) => [r.ref, r]));
  const panel = (trigger, title, inner) => {
    const old = document.getElementById("igAct"); if (old) old.remove();
    const p = el("section", "panel"); p.id = "igAct";
    p.setAttribute("aria-labelledby", "igActH");
    p.innerHTML = `<h2 class="sub3" id="igActH" tabindex="-1" style="margin-top:0">${esc(title)}</h2>${inner}
      <p class="small" id="igActErr" role="alert"></p>`;
    box.after(p);
    p.querySelector("h2").focus();
    const cancel = p.querySelector("[data-cancel]");
    if (cancel) cancel.onclick = () => { p.remove(); trigger.focus(); };
    return p;
  };
  const failed = (p, out) => { p.querySelector("#igActErr").textContent = (out && out.error) || "That did not save."; };

  // 13 · change it while it is still being written.
  box.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => {
    const r = byEntry[b.dataset.edit] || {};
    const check = r.kind === "check";
    const p = panel(b, `Change ${r.ref}`, `${check ? `
      ${igText("ed-found", "What was found", "", { long: true, value: r.found || "" })}
      ${igText("ed-limits", "What was not tested", "", { long: true, value: r.limits || "" })}
      ${igText("ed-tried", "What it was tried on", "", { long: true, value: r.tried_on || "" })}
      ${igFiles("ed-add", d.copy || {})}` : `
      ${igText("ed-what", "What happened", "", { long: true, value: r.what_happened || "" })}
      ${igText("ed-cause", "What caused it", "If nobody knows yet, write that.", { long: true, value: r.cause || "" })}
      ${igText("ed-done", "What was done about it", "", { long: true, value: r.what_was_done || "" })}
      ${igText("ed-where", "Where does the write-up live?", "", { value: r.written_up_where || "" })}
      ${igRadios("ed-closed", "Is it closed?", ["Still open", "Closed"], r.closed || "Still open")}
      ${igText("ed-closedby", "Closed by — role", "", { value: r.closed_by || "" })}
      ${igFiles("ed-add", d.copy || {})}`}
      <p><button type="button" class="btn" data-save>Save the change</button>
        <button type="button" class="btn ghost" data-cancel>Cancel</button></p>`);
    p.querySelector("[data-save]").onclick = async () => {
      const files = await igUpload(p, "ed-add");
      if (files.error) { failed(p, files); return; }
      const fields = check
        ? { found: igVal(p, "ed-found"), limits: igVal(p, "ed-limits"), tried_on: igVal(p, "ed-tried") }
        : { what_happened: igVal(p, "ed-what"), cause: igVal(p, "ed-cause"),
            what_was_done: igVal(p, "ed-done"), written_up_where: igVal(p, "ed-where"),
            closed: igPicked(p, "ed-closed"), closed_by: igVal(p, "ed-closedby"),
            closed_at: igPicked(p, "ed-closed") === "Closed" && r.closed !== "Closed"
              ? localToday() : r.closed_at || "" };
      if (files.ids.length) fields.attachments = [...(r.attachments || []), ...files.ids];
      const out = await post("/api/entries/edit", { ref: r.ref, fields });
      if (!out || !out.ok) { failed(p, out); return; }
      toast(`${r.ref} changed.`); go("integrity");
    };
  });

  // An incident that has been closed reopens rather than being edited.
  box.querySelectorAll("[data-reopen]").forEach((b) => b.onclick = () => {
    const p = panel(b, `Reopen ${b.dataset.reopen}`, `
      <p class="small">It opens again with its whole history, and the reopening is on the audit trail. Nothing is deleted.</p>
      ${igText("ro-why", "Why it is being reopened (optional)", "", { long: true })}
      <p><button type="button" class="btn" data-save>Reopen it</button>
        <button type="button" class="btn ghost" data-cancel>Cancel</button></p>`);
    p.querySelector("[data-save]").onclick = async () => {
      const out = await post("/api/incidents/reopen", { ref: b.dataset.reopen, why: igVal(p, "ro-why") });
      if (!out || !out.ok) { failed(p, out); return; }
      toast(`${b.dataset.reopen} reopened.`); go("integrity");
    };
  });

  // 11.8 · Stop it now. The person says which of the named roles they hold;
  // nothing reads a title to decide it for them.
  box.querySelectorAll("[data-stop]").forEach((b) => b.onclick = () => {
    const roles = d.stoppers || [];
    const p = panel(b, "Stop it now", `
      ${igRadios("st-role", "Which of these are you?", [...roles, "None of these"], "",
        `You said ${roles.join(", ")} can do this without waiting for a meeting.`)}
      <p class="small" id="st-route" hidden>${esc((d.copy || {}).stop_route || "")}</p>
      <p><button type="button" class="btn" data-save>Stop the tool now</button>
        <button type="button" class="btn ghost" data-cancel>Cancel</button></p>`);
    const route = p.querySelector("#st-route"), go_ = p.querySelector("[data-save]");
    p.querySelectorAll('[name="st-role"]').forEach((x) => x.onchange = () => {
      const none = igPicked(p, "st-role") === "None of these";
      route.hidden = !none; go_.hidden = none;
    });
    go_.onclick = async () => {
      const role = igPicked(p, "st-role");
      if (!role || role === "None of these") { failed(p, { error: "Say which of the named roles you hold." }); return; }
      const out = await post("/api/incidents/stop", { ref: b.dataset.stop, role });
      if (!out || !out.ok) { failed(p, out); return; }
      const said = el("p", "", esc(out.says)); said.setAttribute("role", "alert");
      p.innerHTML = ""; p.appendChild(said);
      setTimeout(() => go("integrity"), 1500);
    };
  });
  return box;
}

/* 8.15 and 11.14 · Anything attached? Stored and never read. */
function igFiles(id, copy) {
  return `<div class="vr-field"><label for="${id}">Anything attached? (optional)</label>
    <p class="small muted vr-help" id="${id}-help">${esc(copy.attachment || "")} ${esc(copy.attachment_limit || "")}
      ${esc(copy.attachment_security || "")}</p>
    <input type="file" id="${id}" multiple aria-describedby="${id}-help"></div>`;
}
async function igUpload(host, id) {
  const input = host.querySelector(`#${id}`);
  const files = input ? [...input.files] : [];
  if (files.length > 5) return { error: "Five files is the most one record holds." };
  const ids = [];
  for (const f of files) {
    if (f.size > 5 * 1024 * 1024) return { error: `${f.name} is larger than 5 MB. Attach a smaller copy, or say where the full one lives.` };
    const data = await new Promise((ok, no) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result).split(",")[1] || "");
      r.onerror = () => no(r.error);
      r.readAsDataURL(f);
    }).catch(() => null);
    if (data === null) return { error: `${f.name} could not be read.` };
    const out = await post("/api/attachments", { name: f.name, type: f.type, data });
    if (!out || !out.ok) return { error: (out && out.error) || `${f.name} was not attached.` };
    ids.push(out.id);
  }
  return { ids };
}
/* Handed back as a download, never shown in the page. */
async function igDownload(id) {
  const out = await api(`/api/attachments/get?id=${encodeURIComponent(id)}`);
  if (!out || !out.ok) { toast((out && out.error) || "That could not be opened.", true); return; }
  const bytes = Uint8Array.from(atob(out.data), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url; a.download = out.name; document.body.appendChild(a); a.click();
  a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* Shared pieces for the two forms. Every field has a real label; help text is
   tied to its field and read before anyone types. */
function igRadios(name, legend, options, chosen, help, readback) {
  const hid = `${name}-help`;
  return `<fieldset class="vr-tri" id="${name}-set"${help || readback ? ` aria-describedby="${hid}"` : ""}>
    <legend>${esc(legend)}</legend>
    ${help || readback ? `<p class="small muted vr-help" id="${hid}" style="width:100%">${
      readback ? `<b>${esc(readback)}</b> ` : ""}${esc(help || "")}</p>` : ""}
    ${options.map((o, i) => {
      const [value, label] = Array.isArray(o) ? o : [o, o];
      return `<label><input type="radio" name="${name}" value="${esc(value)}"${
        value === chosen ? " checked" : ""}> ${esc(label)}</label>`;
    }).join("")}</fieldset>`;
}
function igText(id, label, help, { long = false, value = "", type = "text" } = {}) {
  const hid = `${id}-help`;
  const described = help ? ` aria-describedby="${hid}"` : "";
  return `<div class="vr-field"><label for="${id}">${esc(label)}</label>
    ${help ? `<p class="small muted vr-help" id="${hid}">${esc(help)}</p>` : ""}
    ${long ? `<textarea id="${id}" rows="3"${described}>${esc(value)}</textarea>`
      : `<input id="${id}" type="${type}" value="${esc(value)}"${described}>`}</div>`;
}
const igPicked = (box, name) =>
  (box.querySelector(`[name="${name}"]:checked`) || {}).value || "";
const igVal = (box, id) => ((box.querySelector(`#${id}`) || {}).value || "").trim();
function igRows(box, hostId, fields, rowsLabel) {
  const host = box.querySelector(`#${hostId}`);
  const say = box.querySelector(`#${hostId}-live`);
  const add = () => {
    const n = host.children.length + 1;
    const row = el("fieldset", "vr-tri");
    row.innerHTML = `<legend>${esc(rowsLabel)} ${n}</legend>` + fields.map(([k, l, type]) =>
      `<label style="flex:1 1 180px;flex-direction:column;align-items:stretch">${esc(l)}
        <input data-k="${k}" type="${type || "text"}"></label>`).join("") +
      `<button type="button" class="btn ghost" data-remove>Remove this row</button>`;
    row.querySelector("[data-remove]").onclick = () => {
      row.remove(); if (say) say.textContent = `${rowsLabel} removed.`;
    };
    host.appendChild(row);
    if (say) say.textContent = `${rowsLabel} ${n} added.`;
    row.querySelector("input").focus();
  };
  return { add, read: () => [...host.children].map((r) =>
    Object.fromEntries([...r.querySelectorAll("[data-k]")].map((i) => [i.dataset.k, i.value.trim()]))) };
}
function igConfirm(host, lines, title) {
  host.innerHTML = `<h2 class="sub3" tabindex="-1" style="margin-top:0">${esc(title)}</h2>
    ${lines.map((l) => `<p>${esc(l)}</p>`).join("")}
    <p><button type="button" class="btn ghost" id="igDone">Back to the register</button></p>`;
  host.setAttribute("aria-live", "polite");
  host.querySelector("h2").focus();
  host.querySelector("#igDone").onclick = () => go("integrity");
}

/* §8 · the check record. Only the project is required. */
function checkForm(host, d, byRef) {
  const inp = d.inputs || {}, rb = inp.readbacks || {}, copy = d.copy || {},
        opt = d.options || {}, rule = d.stopping_rule || {};
  const today = localToday();
  const watchItems = [...(inp.watches || [])];
  if (inp.differential && inp.differential.item && !watchItems.includes(inp.differential.item)) {
    watchItems.push(inp.differential.item);
  }
  const chips = [...new Set([inp.who_checks, ...(d.stoppers || [])].filter(Boolean))];
  host.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${IG.corrects ? `Record a check that corrects ${esc(IG.corrects)}` : "Record a check"}</h2>
    ${IG.corrects ? `<p class="vr-tell">${esc(copy.not_editable_complete || "")} Both stay on the list.</p>` : ""}
    <p class="intro">${esc(copy.only_the_project)}</p>
    <div class="vr-field"><label for="ck-project">Which project is this about?</label>
      <p class="small muted vr-help" id="ck-project-help">A check attaches to a project — one
        narrow use of a tool, with its own baseline and its own named person — rather than
        to the tool itself, because the same tool doing two jobs is two projects with two
        sets of answers. If it is not on the list, this starts it at Identify, marked as
        running unless you say otherwise.</p>
      <select id="ck-project" aria-describedby="ck-project-help" required>
        <option value="">Choose a project</option>
        ${(d.projects || []).map((p) => `<option value="${esc(p.ref)}">${esc(p.name)}</option>`).join("")}
        <option value="__new">It is not on the list yet</option></select></div>
    <div id="ck-newbox" hidden>${igText("ck-newname", "What is it called?", "")}</div>
    ${igRadios("ck-occasion", "Is this the first look, or one of the regular ones?",
      opt.occasions || [], "", "The first look attaches to Test; every look after it attaches to Measure. A look at a version the vendor has changed attaches to Test again.")}
    <div id="ck-change" hidden>
      ${igRadios("ck-back", "Does your own rule send this back for a fresh first look?",
        opt.back_to_first_look || [], "")}
      <div class="vr-field"><label for="ck-version">Which version is this check about?</label>
        <select id="ck-version"><option value="">There is no version record for this yet</option></select></div>
      <p class="small muted">${esc(copy.same_project)} ${esc(copy.no_drift)}</p>
    </div>
    ${igText("ck-at", "When did somebody look?", copy.date, { type: "date", value: today })}
    <p class="small muted">Written down ${esc(niceDate(today))}.</p>
    <div class="vr-field"><label for="ck-who">Who looked?</label>
      <p class="small muted vr-help" id="ck-who-help">${rb.who ? `<b>${esc(rb.who)}</b> ` : ""}${esc(copy.who)}</p>
      <input id="ck-who" list="ck-who-list" aria-describedby="ck-who-help" value="${esc(inp.who_checks || "")}">
      <datalist id="ck-who-list">${chips.map((c) => `<option value="${esc(c)}">`).join("")}
        <option value="Somebody outside the organization"><option value="We are not sure"></datalist></div>
    <div id="ck-outsidebox" hidden>${igText("ck-outside", "Which organization?", "")}</div>
    ${igText("ck-whoname", "Their name, if you want it beside the title (optional)", "")}
    ${igText("ck-tried", "What did they try it on?", `What material, how much of it, and why that material. For example: ${(d.examples || {}).tried_on || ""} “Whatever was on the desk that day” is an honest answer and a useful one.`, { long: true })}
    ${(d.holdings || []).length ? `<fieldset class="vr-tri"><legend>Which of your recorded holdings did the material come from?</legend>
      <p class="small muted vr-help" style="width:100%">Naming the holding is what lets this surface tell you later that a check was run on something you said never goes into a general tool. Leave it blank and nothing here is ever flagged.</p>
      ${d.holdings.map((h) => `<label><input type="checkbox" name="ck-holdings" value="${esc(h.id)}"> ${esc(h.name)}</label>`).join("")}
    </fieldset>` : ""}
    ${igRadios("ck-where", "Where was it tried?", opt.wheres || [], "", copy.no_staging)}
    ${igText("ck-period", "Over what period?", "One afternoon. Two weeks. The whole of March.")}
    ${igText("ck-found", "What was found?", copy.found, { long: true })}
    <div class="vr-field"><label for="ck-limits">What was not tested, and is therefore not known?</label>
      <p class="small muted vr-help" id="ck-limits-help">${esc(copy.limits)}</p>
      <textarea id="ck-limits" rows="3" aria-describedby="ck-limits-help ck-limits-refusal"></textarea>
      <label class="small"><input type="checkbox" id="ck-nolimits"> ${esc(copy.did_not_write)}</label>
      <p class="small" id="ck-limits-refusal" role="alert" aria-live="assertive"></p></div>
    ${igRadios("ck-verdict", "Did it hold up?", opt.verdicts || [], "")}
    <div id="ck-determination" hidden>${igRadios("ck-det", "What happens now?",
      opt.determinations || [], inp.determination || "",
      "The person writing up the check is often not the person who makes this call.", rb.determination)}</div>
    ${inp.baseline_asked ? `${igRadios("ck-baseline", "Was it measured against the baseline?",
        opt.baseline || [], "", "The baseline was written at Procure and it lives on the project. Nothing on this screen writes it or changes it; this records whether this look measured against it.", rb.baseline)}
      <p class="small" id="ck-baseline-note"></p>
      <div id="ck-whynot" hidden>${igText("ck-why", "Why could it not be retaken?", "")}</div>` : ""}
    ${watchItems.length ? `<fieldset class="vr-tri"><legend>What else did this look at?</legend>
      <p class="small muted vr-help" style="width:100%">Only the things you said you watch appear here. Nothing else is asked, and nothing here is scored.</p>
      ${watchItems.map((w, i) => `<label style="flex:1 1 100%;flex-direction:column;align-items:stretch">
        ${esc(w)} <span class="small muted">${esc(w === (inp.differential || {}).item
          ? (rb.differential || "") : "You said you watch this.")}</span>
        <input data-watch="${esc(w)}" id="ck-watch-${i}"></label>`).join("")}</fieldset>` : ""}
    ${inp.fallback_asked ? igRadios("ck-manual", "Was the manual way tried this time?",
        opt.manual || [], "", "", rb.fallback) : ""}
    ${inp.access_ongoing ? `${igRadios("ck-access", "Accessibility", opt.access || [], "", copy.access, rb.accessibility)}
      <div id="ck-accessbox" hidden>${igText("ck-accessfix", "What needs fixing?", "", { long: true })}</div>` : ""}
    ${igRadios("ck-rule", "Do you have a written rule for when testing is enough?",
      opt.rule || [], rule.have_one || "", copy.rule)}
    <div id="ck-rulebox" hidden>
      ${igText("ck-rulename", "What the rule is called", "", { value: rule.name || "" })}
      ${igText("ck-rulesays", "What it says has to be true before testing stops", "", { long: true, value: rule.says || "" })}
      ${igRadios("ck-rulemet", "Was it met on this check?", opt.rule_met || [], "")}
      <div id="ck-segments"></div><p class="vh" id="ck-segments-live" aria-live="polite"></p>
      <p><button type="button" class="btn ghost" id="ck-addseg">Add a segment</button>
        <span class="small muted">The application computes nothing from these rows. It holds what a person wrote.</span></p>
    </div>
    <h3 class="sub3">Conditions</h3>
    <p class="small muted">${esc(copy.conditions)}</p>
    <div id="ck-conds"></div><p class="vh" id="ck-conds-live" aria-live="polite"></p>
    <p><button type="button" class="btn ghost" id="ck-addcond">Add a condition</button></p>
    ${igRadios("ck-complete", "Is this account complete?", ["Complete", "Still being written"],
      "Still being written", "A check marked still being written raises nothing and blocks nothing. It becomes evidence for a passage when you mark it complete.")}
    ${igFiles("ck-files", copy)}
    <p class="small" id="ck-err" role="alert"></p>
    <p><button type="button" class="btn" id="ck-save">Add it</button>
       <button type="button" class="btn ghost" id="ck-cancel">Cancel</button></p>`;

  const $$ = (s) => host.querySelector(s);
  const show = (id, on) => { const n = $$(id); if (n) n.hidden = !on; };
  const segs = igRows(host, "ck-segments", [["segment", "What the segment is"],
    ["tried", "How many were tried"], ["did_not_hold", "How many did not hold up"],
    ["rule_says", "What your rule says about that"]], "Segment");
  const conds = igRows(host, "ck-conds", [["what", "What has to happen"],
    ["owner", "Who owns it — role"], ["by", "By when", "date"]], "Condition");
  $$("#ck-addseg").onclick = segs.add;
  $$("#ck-addcond").onclick = conds.add;

  const project = () => byRef[$$("#ck-project").value] || null;
  $$("#ck-project").onchange = () => {
    show("#ck-newbox", $$("#ck-project").value === "__new");
    const p = project();
    const sel = $$("#ck-version");
    sel.innerHTML = `<option value="">There is no version record for this yet</option>` +
      ((p && p.versions) || []).map((v) => `<option value="${esc(v.ref || v.id || "")}">${
        esc(v.said || v.what || v.ref || "")}${v.coming ? " · " + esc(v.coming) : ""}</option>`).join("");
    const note = $$("#ck-baseline-note");
    if (note) note.textContent = p && !p.has_baseline
      ? "This project carries no baseline. It is written at Procure, on the project." : "";
  };
  host.querySelectorAll('[name="ck-occasion"]').forEach((r) => r.onchange = () =>
    show("#ck-change", igPicked(host, "ck-occasion") === "A look after something changed"));
  host.querySelectorAll('[name="ck-verdict"]').forEach((r) => r.onchange = () =>
    show("#ck-determination", igPicked(host, "ck-verdict") === "It did not do what we expected"));
  host.querySelectorAll('[name="ck-baseline"]').forEach((r) => r.onchange = () =>
    show("#ck-whynot", igPicked(host, "ck-baseline") === "The measurement could not be retaken this time"));
  host.querySelectorAll('[name="ck-access"]').forEach((r) => r.onchange = () =>
    show("#ck-accessbox", igPicked(host, "ck-access") === "Checked, and there are things to fix"));
  const ruleShown = () => show("#ck-rulebox", igPicked(host, "ck-rule") === "Yes");
  host.querySelectorAll('[name="ck-rule"]').forEach((r) => r.onchange = ruleShown);
  ruleShown();
  $$("#ck-who").oninput = () => show("#ck-outsidebox",
    $$("#ck-who").value === "Somebody outside the organization");
  $$("#ck-cancel").onclick = () => { host.remove(); $("#igNewCheck").focus(); };

  $$("#ck-save").onclick = async () => {
    const err = $$("#ck-err"); err.textContent = "";
    const refusal = $$("#ck-limits-refusal"); refusal.textContent = "";
    let ref = $$("#ck-project").value;
    if (!ref) { err.textContent = "Say which project this is about."; $$("#ck-project").focus(); return; }
    const complete = igPicked(host, "ck-complete") === "Complete";
    if (complete && !igVal(host, "ck-limits") && !$$("#ck-nolimits").checked) {
      refusal.textContent = (d.copy || {}).limits_required;
      $$("#ck-limits").focus(); return;
    }
    if (ref === "__new") {
      const name = igVal(host, "ck-newname");
      if (!name) { err.textContent = "Give the project a name."; $$("#ck-newname").focus(); return; }
      const made = await post("/api/projects/start", { name, already_running: "yes" });
      if (!made || !made.ok) { err.textContent = (made && made.error) || "The project could not be started."; return; }
      ref = made.project.ref;
    }
    const watched = {};
    host.querySelectorAll("[data-watch]").forEach((i) => { if (i.value.trim()) watched[i.dataset.watch] = i.value.trim(); });
    const who = igVal(host, "ck-who");
    const files = await igUpload(host, "ck-files");
    if (files.error) { err.textContent = files.error; $$("#ck-files").focus(); return; }
    const corrects = IG.corrects || "";
    IG.corrects = "";
    const out = await post("/api/checks", {
      attachments: files.ids, corrects,
      project: ref, occasion: igPicked(host, "ck-occasion"),
      back_to_first_look: igPicked(host, "ck-back"), version: igVal(host, "ck-version"),
      at: igVal(host, "ck-at"),
      who: who === "Somebody outside the organization" ? "" : who,
      outside_organisation: who === "Somebody outside the organization" ? igVal(host, "ck-outside") : "",
      who_name: igVal(host, "ck-whoname"), tried_on: igVal(host, "ck-tried"),
      holdings: [...host.querySelectorAll('[name="ck-holdings"]:checked')].map((c) => c.value),
      where: igPicked(host, "ck-where"), period: igVal(host, "ck-period"),
      found: igVal(host, "ck-found"), limits: igVal(host, "ck-limits"),
      limits_not_written: $$("#ck-nolimits").checked,
      verdict: igPicked(host, "ck-verdict"),
      determination: igPicked(host, "ck-verdict") === "It did not do what we expected" ? igPicked(host, "ck-det") : "",
      against_baseline: igPicked(host, "ck-baseline"), baseline_why_not: igVal(host, "ck-why"),
      watched, manual_way: igPicked(host, "ck-manual"),
      accessibility: igPicked(host, "ck-access"), accessibility_fixes: igVal(host, "ck-accessfix"),
      have_rule: igPicked(host, "ck-rule"), rule_name: igVal(host, "ck-rulename"),
      rule_says: igVal(host, "ck-rulesays"), stopping_rule_met: igPicked(host, "ck-rulemet"),
      segments: segs.read(), conditions: conds.read(), complete,
    });
    if (!out || !out.ok) {
      if (out && out.field === "8.8") { refusal.textContent = out.error; $$("#ck-limits").focus(); }
      else err.textContent = (out && out.error) || "That did not save.";
      return;
    }
    igConfirm(host, out.says || [], complete ? "Added and marked complete" : "Added");
  };
}

/* §11 · the incident record, for somebody signed in. The public page is its
   own page, served without JavaScript — see app/public_report.py. */
function incidentForm(host, d, byRef) {
  const inp = d.inputs || {}, rb = inp.readbacks || {}, copy = d.copy || {},
        opt = d.options || {};
  const sev = inp.severities || [];
  host.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Write down an incident</h2>
    <p class="intro">${esc(copy.anyone)}</p>
    ${inp.attached_to_existing ? `<p class="vr-tell">You said AI incidents go through your
      existing incident process. This does not replace that. Write it here as well, so that
      the tool's whole history sits in one place.</p>` : ""}
    <div class="vr-field"><label for="in-tool">Which tool?</label>
      <select id="in-tool"><option value="">Choose one</option>
        ${(d.projects || []).map((p) => `<option value="${esc(p.ref)}">${esc(p.name)}</option>`).join("")}
        <option value="__unknown">I do not know which tool</option></select></div>
    <div id="in-usingbox" hidden>${igText("in-using", "What were you using?", "")}</div>
    ${igText("in-what", "What happened?", copy.what_happened, { long: true })}
    ${igText("in-at", "When did it happen?", "", { type: "date" })}
    <label class="small"><input type="checkbox" id="in-atunsure"> I am not sure</label>
    ${igText("in-noticed", "When did you first notice? (optional)", copy.noticed, { type: "date" })}
    ${igText("in-affected", "Who or what was affected?", `In your own words. For example: ${(d.examples || {}).affected || ""} If you only know part of it, write the part you know.`, { long: true })}
    ${igRadios("in-touched", "Did it affect a decision about a person?", opt.touched || [], "", "", rb.final_action)}
    ${sev.length ? igRadios("in-sev", "How serious is it?",
        [...sev.map((s) => [s.label, `${s.label} — ${s.meaning}`]), ["", "We have not decided yet"]],
        "", "Your own levels, in your own words.")
      : `<p class="small muted">Your framework has no severity levels yet, so this is recorded without one.</p>`}
    ${igRadios("in-stopped", "Has the tool been stopped?", opt.stopped || [], "", copy.stop_route)}
    <div id="in-stopbox" hidden>
      ${igText("in-stopat", "When was it stopped?", "", { type: "date" })}
      ${igText("in-stopby", "By whom — role", "")}</div>
    ${(inp.must_be_told || []).length ? `<fieldset class="vr-tri"><legend>Who has been told?</legend>
      ${inp.must_be_told.map((p, i) => `<label style="flex:1 1 100%">
        <input type="checkbox" data-told="${esc(p)}" id="in-told-${i}"> ${esc(p)}
        <span class="small muted">You said this party must be told.</span>
        <input type="date" data-told-on="${esc(p)}" aria-label="When ${esc(p)} was told"></label>`).join("")}
      </fieldset>` : ""}
    ${inp.lookback_answer !== "no" ? igRadios("in-lookback", "Has anyone gone back over earlier work?",
        opt.lookback || [], "", "", rb.lookback) : ""}
    <div id="in-backbox" hidden>${igText("in-backto", "Back to when?", "", { type: "date" })}</div>
    ${igText("in-cause", "What caused it? (optional)", "If nobody knows yet, write that.", { long: true })}
    ${igText("in-done", "What was done about it? (optional)", "", { long: true })}
    ${igText("in-writer", "Who is writing this up?", copy.write_up, { value: inp.writes_up || "" })}
    ${igText("in-where", "Where does the write-up live?", "")}
    ${igRadios("in-closed", "Is it closed?", ["Still open", "Closed"], "Still open")}
    <div id="in-closebox" hidden>${igText("in-closedat", "Closed on", "", { type: "date" })}
      ${igText("in-closedby", "Closed by — role", "")}</div>
    ${igFiles("in-files", copy)}
    <p class="vr-tell">${esc(copy.visible)}</p>
    <p class="small" id="in-err" role="alert"></p>
    <p><button type="button" class="btn" id="in-save">Add it</button>
       <button type="button" class="btn ghost" id="in-cancel">Cancel</button></p>`;

  const $$ = (s) => host.querySelector(s);
  const show = (id, on) => { const n = $$(id); if (n) n.hidden = !on; };
  $$("#in-tool").onchange = () => show("#in-usingbox", $$("#in-tool").value === "__unknown");
  host.querySelectorAll('[name="in-stopped"]').forEach((r) => r.onchange = () =>
    show("#in-stopbox", igPicked(host, "in-stopped") === "Yes, stopped"));
  host.querySelectorAll('[name="in-lookback"]').forEach((r) => r.onchange = () =>
    show("#in-backbox", igPicked(host, "in-lookback") === "Yes, back to a date"));
  host.querySelectorAll('[name="in-closed"]').forEach((r) => r.onchange = () =>
    show("#in-closebox", igPicked(host, "in-closed") === "Closed"));
  $$("#in-cancel").onclick = () => { host.remove(); $("#igNewIncident").focus(); };

  $$("#in-save").onclick = async () => {
    const err = $$("#in-err"); err.textContent = "";
    const tool = $$("#in-tool").value;
    const told = {};
    host.querySelectorAll("[data-told]").forEach((c) => {
      if (c.checked) told[c.dataset.told] =
        (host.querySelector(`[data-told-on="${CSS.escape(c.dataset.told)}"]`) || {}).value || "";
    });
    const files = await igUpload(host, "in-files");
    if (files.error) { err.textContent = files.error; $$("#in-files").focus(); return; }
    const out = await post("/api/incidents", {
      attachments: files.ids,
      project: tool && tool !== "__unknown" ? tool : "",
      tool: tool && tool !== "__unknown" ? (byRef[tool] || {}).name || "" : "",
      what_were_you_using: tool === "__unknown" ? igVal(host, "in-using") : "",
      what_happened: igVal(host, "in-what"),
      at: $$("#in-atunsure").checked ? "" : igVal(host, "in-at"),
      first_noticed: igVal(host, "in-noticed"), affected: igVal(host, "in-affected"),
      touched_a_person: igPicked(host, "in-touched"), severity: igPicked(host, "in-sev"),
      stopped: igPicked(host, "in-stopped"), stopped_at: igVal(host, "in-stopat"),
      stopped_by: igVal(host, "in-stopby"), told,
      lookback: igPicked(host, "in-lookback"), lookback_back_to: igVal(host, "in-backto"),
      cause: igVal(host, "in-cause"), what_was_done: igVal(host, "in-done"),
      written_up_by: igVal(host, "in-writer"), written_up_where: igVal(host, "in-where"),
      closed: igPicked(host, "in-closed"), closed_at: igVal(host, "in-closedat"),
      closed_by: igVal(host, "in-closedby"),
    });
    if (!out || !out.ok) { err.textContent = (out && out.error) || "That did not save."; return; }
    igConfirm(host, out.says || [], "Written down");
  };
}

VIEWS.configure = async () => {
  const d = await api("/api/config");
  const root = el("div");
  if (S.state.actor.role !== "ot") {
    root.appendChild(el("div", "locked", `<b>Configure is the Office of Technology's room.</b>
      You are signed in as ${esc(S.state.actor.role)}. Switch to the OT user to tune parameters.`));
    $("#view").innerHTML = ""; $("#view").appendChild(root);
    reason([{ title: "Who may change this", body: `OT owns the operational configuration. In Operating Mode even OT must route a change through ${whoDecides()}.`, cite: "SCDES AI Governance Framework §6" }]);
    return;
  }

  const intro = el("div", "panel");
  // "what SCDES actually needs" was hardcoded too — the agency's own shorthand
  // is on S.state and the screen was naming somebody else's.
  intro.innerHTML = `<p class="intro">The appendices were adopted as
    <em>templates</em>. This is where OT sets what ${esc(agencyShort())}
    actually needs. Move a control to preview its consequence before saving.
    <span class="mono">parameter set ${esc(d.parameter_set_hash)}</span></p>`;
  root.appendChild(intro);

  const panel = el("div", "panel");
  d.fields.forEach((f) => {
    const w = el("div", "field");
    const slider = f.control === "slider";
    w.innerHTML = `<h3>${esc(f.label)}</h3><p class="governs">${esc(f.governs)}</p>
      <div class="ctrl">` +
      (slider ? `<input type="range" min="${f.min}" max="${f.max}" step="${f.step}" value="${f.value}">`
              : `<input type="number" min="${f.min ?? 0}" step="${f.step ?? 1}" value="${f.value}">`) +
      `<span class="val">${f.key.includes("weight") ? "×" : ""}${f.value}</span></div>
       <div class="impact quiet"><b>Impact:</b> move the control to preview.</div>`;
    const inp = w.querySelector("input"), out = w.querySelector(".val"), box = w.querySelector(".impact");
    let timer;
    inp.oninput = () => {
      out.textContent = (f.key.includes("weight") ? "×" : "") + inp.value;
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const cq = await post("/api/config/preview", { key: f.key, value: inp.value });
        if (!cq.affected) { box.className = "impact quiet";
          box.innerHTML = `<b>Impact:</b> ${esc(cq.summary)}`; return; }
        box.className = "impact";
        box.innerHTML = `<b>Impact:</b> ${esc(cq.summary)}<ul>` +
          cq.reclassified.slice(0, 5).map((r) =>
            `<li>${esc(r.name.slice(0, 42))} — <b>${esc(vlabel("risk_band", r.from))} → ${esc(vlabel("risk_band", r.to))}</b>
             (${r.score_before} → ${r.score_after})</li>`).join("") + `</ul>`;
      }, 170);
    };
    const row = el("div", "row");
    const b = el("button", "btn", "Review & save");
    b.onclick = async () => {
      const r = await post("/api/config/edit", { key: f.key, value: inp.value });
      if (!r.committed) return toast(r.reason, true);
      toast(`Saved. ${r.consequence.summary}`); await refreshState(); go("configure");
    };
    row.appendChild(b); row.appendChild(el("span", "note", `Implements ${esc(f.citation)}`));
    w.appendChild(row);
    panel.appendChild(w);
  });
  root.appendChild(panel);
  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why previewing matters", body: "The point is not to guess a number on paper. Moving a weight shows which projects reclassify, which gates newly trigger and which instruments become required — before anything is saved.", cite: "Appendix B — AI Risk Classification Matrix" },
    { title: "What happens next", body: `When the set is right, OT proposes it and ${whoDecides()} adopts it. The guardrails then activate and every later change routes through ${whoDecides()}.`, cite: "SCDES AI Governance Framework §6; Appendix N" },
  ]);
};

/* Budget — what it costs you, all in. One entry per cost line, committed or
   not. Replaces a screen built on the reference agency's budget pools. The
   full cost is computed here from the lines and never typed. */
const BG = { said: "", form: null };

VIEWS.budget = async () => {
  const d = await api("/api/costs");
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    const p = el("div", "panel");
    p.innerHTML = `<p class="intro">${esc(d.why || "This is part of the subscription.")}</p>`;
    $("#view").appendChild(p);
    return;
  }
  const inp = d.inputs || {}, copy = d.copy || {};
  const byRef = Object.fromEntries((d.lines || []).map((l) => [l.ref, l]));
  const root = el("div");
  const live = el("p", "vh"); live.setAttribute("aria-live", "polite");
  root.appendChild(live);

  const head = el("div", "panel");
  head.innerHTML = `
    <p class="intro" style="margin-top:0">What a tool costs you over its whole life,
      including what it would cost to leave it.</p>
    ${copy.not_required ? `<p class="small">${esc(copy.not_required)}</p>` : ""}
    <p class="small"><a href="#bgFindings">Skip to the findings</a> · <a href="#bgList">Skip to the list</a></p>
    <p><button type="button" class="btn" id="bgNew">Record a cost line</button></p>`;
  root.appendChild(head);

  // §2 · five counters, then the money strip.
  const c = d.counters || {}, says = c.says || {};
  const m = d.money || {};
  const stats = el("section", "panel");
  stats.setAttribute("aria-label", "Counts and money");
  stats.innerHTML = `<div class="vr-tiles">${[
      [c.recorded, "Cost lines recorded", ""],
      [c.full_cost_estimated, "Projects with the full cost estimated", says.full_cost_estimated],
      [c.no_number_against_it, "No number against it", ""],
      [c.no_cost_of_leaving, "No cost of leaving recorded", says.no_cost_of_leaving],
      [c.costing_more_than_estimated, "Costing more than estimated", ""]]
    .map(([n, l, s], i) => `<div class="vr-tile"${s ? ` tabindex="0" aria-describedby="bgTip${i}"` : ""}>
      <b>${n || 0}</b><span>${esc(l)}</span>${s ? `<span class="small" id="bgTip${i}">${esc(s)}</span>` : ""}</div>`).join("")}</div>
    <div class="bg-money">${(m.headline || []).map((s) => `<p class="vr-money">${esc(s)}</p>`).join("")}
      ${(m.conditional || []).map((s) => `<p class="small">${esc(s)}</p>`).join("")}</div>
    <p class="small muted">${esc(copy.no_lifetime_total)}</p>`;
  root.appendChild(stats);

  // §6.20 · the one setting, asked once at the top.
  const diff = d.difference || {};
  const set = el("section", "panel");
  set.innerHTML = `<details><summary>When does a difference between an estimate and an actual become worth a conversation?</summary>
    <p class="small">This is a setting for this screen rather than one of your framework answers. Until you pick one, every line above its estimate is counted in the row of numbers at the top and nothing is flagged. The app supplies no amount and no percentage.</p>
    ${igRadios("bg-diff", "Worth a conversation when", d.options.difference, diff.mode || "We have not decided")}
    ${igText("bg-diffval", "The amount or percentage", "", { value: diff.value ?? "" })}
    ${d.may_set_difference ? `<p><button type="button" class="btn ghost" id="bgDiffSave">Keep this</button>
      <span class="small" role="alert" id="bgDiffErr"></span></p>` : `<p class="small muted">Whoever decides sets this.</p>`}</details>`;
  const ds = set.querySelector("#bgDiffSave");
  if (ds) ds.onclick = async () => {
    const out = await post("/api/costs/difference", { mode: igPicked(set, "bg-diff"), value: igVal(set, "bg-diffval") });
    if (out && out.ok) { BG.said = "Kept."; go("budget"); }
    else set.querySelector("#bgDiffErr").textContent = (out && out.error) || "";
  };
  root.appendChild(set);

  // §3 · findings.
  const raised = d.raised || [];
  const projName = Object.fromEntries((d.projects || []).map((p) => [p.ref, p.name]));
  const f = el("section", "panel");
  f.id = "bgFindings";
  f.setAttribute("aria-labelledby", "bgFindingsH");
  f.innerHTML = `<h2 class="sub3" id="bgFindingsH" style="margin-top:0">${raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"}` : "Nothing to flag"}</h2>
    ${raised.length ? `<ul class="vr-flags">${raised.map((x) => {
      const about = x.line && byRef[x.line] ? byRef[x.line].what_for || byRef[x.line].kind_shown
        : projName[x.project] || "";
      return `<li>${about ? `<b>${esc(about)}</b> ` : ""}${esc(x.says)}</li>`;
    }).join("")}</ul>` : `<p class="intro">${esc(d.nothing_to_flag)}</p>`}`;
  root.appendChild(f);

  // §4 · the comparison.
  const cmp = d.comparison || {};
  const comp = el("section", "panel");
  comp.setAttribute("aria-labelledby", "bgCmpH");
  comp.innerHTML = `<h2 class="sub3" id="bgCmpH" style="margin-top:0">The comparison</h2>
    <p class="small muted">${esc(cmp.says)}</p>
    <p class="small"><b>Estimate against actual:</b> ${(cmp.estimate_actual || []).map(([n, l]) => `${n} ${esc(l)}`).join(" | ")}</p>
    <p class="small"><b>Against Vendors:</b> ${(cmp.vendors || []).map(([n, l]) => `${n} ${esc(l)}`).join(" | ")}</p>
    <p><button type="button" class="btn ghost" id="bgCompare">Compare them all now</button></p>
    <p class="small">${esc(cmp.cannot)}</p>`;
  comp.querySelector("#bgCompare").onclick = () => {
    const total = (cmp.estimate_actual || []).reduce((a, [n]) => a + n, 0);
    const bad = ((cmp.estimate_actual || [])[1] || [0])[0];
    BG.said = `Comparison finished. ${total} lines compared. ${bad} disagree.`;
    go("budget");
  };
  root.appendChild(comp);

  // §5 · the list, grouped by project.
  root.appendChild(budgetList(d, byRef));

  const scope = el("div", "panel");
  scope.innerHTML = `<p class="small">${esc(copy.scope)}</p><p class="small">${esc(copy.no_return)}</p>`;
  root.appendChild(scope);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  live.textContent = BG.said || (raised.length ? `${raised.length} finding${raised.length === 1 ? "" : "s"}.` : "");
  BG.said = "";

  const open = (line) => {
    const old = $("#bgForm"); if (old) old.remove();
    const host = el("section", "panel");
    host.id = "bgForm";
    head.after(host);
    costForm(host, d, line);
    const h = host.querySelector("h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  };
  $("#bgNew").onclick = () => open(null);
  $("#view").querySelectorAll("[data-bg-edit]").forEach((b) => b.onclick = () => open(byRef[b.dataset.bgEdit]));
};

function budgetList(d, byRef) {
  const box = el("section", "panel");
  box.id = "bgList";
  box.setAttribute("aria-labelledby", "bgListH");
  const anyVersion = (d.lines || []).some((l) => l.version);
  const heads = ["What this cost is for", "Kind", "Estimate", "Actual", "Per", "Whose money",
                 "Owner", "Starts", "Ends", "Committed", "Line status"].concat(anyVersion ? ["Change"] : [], [""]);
  const cell = (v) => v ? esc(v) : "";
  const row = (l) => `<tr>
    <th scope="row">${esc(l.what_for || l.kind_shown)}<br><span class="small muted">${esc(l.ref)}</span></th>
    <td>${esc(l.kind_shown)}</td>
    <td aria-label="Estimate ${esc(l.estimate_shown || "none")} ${esc(l.basis_shown)}">${cell(l.estimate_shown) || '<span class="muted">None yet</span>'}</td>
    <td aria-label="Actual ${esc(l.actual_shown || "none")} ${esc(l.basis_shown)}">${cell(l.actual_shown) || '<span class="muted">None yet</span>'}${l.above_estimate ? '<br><span class="small">above estimate</span>' : ""}</td>
    <td>${esc(l.basis_shown)}${l.headcount ? ` · ${l.headcount} people` : ""}${l.hours_a_year ? `<br>${l.hours_a_year} hours a year` : ""}${l.hours_one_off ? `<br>${l.hours_one_off} hours one-off` : ""}</td>
    <td>${cell(l.whose_money)}</td>
    <td>${esc(l.owner || "Recorded as unknown — nobody named to close it")}</td>
    <td>${cell(l.starts)}</td><td>${cell(l.ends || l.ends_how)}</td>
    <td>${l.committed ? `Committed ${esc(l.committed_on || "")}` : "Not committed"}</td>
    <td>${esc(l.status_shown)}</td>
    ${anyVersion ? `<td>${cell(l.version)}</td>` : ""}
    <td>${l.status === "open" ? `<button type="button" class="btn ghost" data-bg-edit="${esc(l.ref)}">${l.committed ? "Supersede it" : "Edit"}</button>
      ${l.committed ? "" : `<button type="button" class="btn ghost" data-bg-commit="${esc(l.ref)}">Commit this line</button>`}
      <button type="button" class="btn ghost" data-bg-status="ended" data-ref="${esc(l.ref)}">It has ended</button>
      <button type="button" class="btn ghost" data-bg-status="withdrawn" data-ref="${esc(l.ref)}">Withdraw it</button>
      <span class="small" role="alert" data-bg-err="${esc(l.ref)}"></span>` : ""}</td></tr>`;
  const groups = d.groups || [];
  let body = "";
  groups.forEach((g) => {
    body += `<tr><th scope="rowgroup" colspan="${heads.length}" class="ig-group">${esc(g.name)}
      <span class="small muted">· ${esc(`$${Math.round(g.full_cost.a_year).toLocaleString()} a year and $${Math.round(g.full_cost.one_off).toLocaleString()} one-off, computed from these lines`)}</span></th></tr>`;
    body += g.lines.map((r) => byRef[r] ? row(byRef[r]) : "").join("");
    body += (g.gaps || []).map((gp) => `<tr><th scope="row">${esc((d.options.kinds.find((k) => k.value === gp.kind) || {}).label || gp.kind)}</th>
      <td colspan="${heads.length - 1}">Recorded as unknown — ${esc(gp.owner || "nobody named to close it")}${gp.by ? `, by ${esc(gp.by)}` : ", no date set"}</td></tr>`).join("");
    body += (g.nothing_recorded || []).map((n) => `<tr class="pr-ghost"><th scope="row">${esc(n.label)}</th>
      <td colspan="${heads.length - 2}">Nothing recorded</td>
      <td><button type="button" class="btn ghost" data-bg-gap="${esc(g.project)}" data-kind="${esc(n.kind)}">Nobody knows this one — record it as a gap</button></td></tr>`).join("");
  });
  if ((d.programme || []).length) {
    body += `<tr><th scope="rowgroup" colspan="${heads.length}" class="ig-group">Costs of running the program, not tied to one project</th></tr>`;
    body += d.programme.map((r) => row(byRef[r])).join("");
  }
  box.innerHTML = `<h2 class="sub3" id="bgListH" style="margin-top:0">Cost lines, by project</h2>
    ${(d.lines || []).length || groups.length ? `<div class="vr-scroll" tabindex="0" role="region" aria-labelledby="bgListH">
      <table class="vr-table"><caption class="vh">Cost lines grouped by project</caption>
      <thead><tr>${heads.map((h) => `<th scope="col">${h || '<span class="vh">Actions</span>'}</th>`).join("")}</tr></thead>
      <tbody>${body}</tbody></table></div>` : `<p class="intro">${esc(d.empty)}</p>`}`;

  const err = (ref, t) => { const n = box.querySelector(`[data-bg-err="${ref}"]`); if (n) n.textContent = t; };
  box.querySelectorAll("[data-bg-commit]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/costs/commit", { ref: b.dataset.bgCommit });
    if (out && out.ok) { BG.said = "Committed. Line status: Open."; go("budget"); }
    else err(b.dataset.bgCommit, (out && out.error) || "");
  });
  box.querySelectorAll("[data-bg-status]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/costs/status", { ref: b.dataset.ref, status: b.dataset.bgStatus });
    if (out && out.ok) { BG.said = b.dataset.bgStatus === "ended" ? "Line status: Ended. It stays on the list." : "Line status: Withdrawn. It stays on the list."; go("budget"); }
    else err(b.dataset.ref, (out && out.error) || "");
  });
  // "Recorded as unknown. Who should close it, and by when?" — asked at the
  // moment, because a gap with no owner is not a valid gap.
  box.querySelectorAll("[data-bg-gap]").forEach((b) => b.onclick = () => {
    const cell = b.parentElement;
    if (cell.querySelector(".bg-gapask")) return;
    const ask = el("div", "bg-gapask");
    const id = `bgGap-${b.dataset.bgGap}-${b.dataset.kind}`;
    ask.innerHTML = `<p class="small">Recorded as unknown. Who should close it, and by when?</p>
      <label class="small">Role <input id="${id}-o"></label>
      <label class="small">By <input type="date" id="${id}-b"></label>
      <button type="button" class="btn ghost">Record it</button>
      <span class="small" role="alert"></span>`;
    cell.appendChild(ask);
    ask.querySelector("input").focus();
    ask.querySelector("button").onclick = async () => {
      const owner = ask.querySelector(`#${CSS.escape(id)}-o`).value.trim();
      if (!owner) { ask.querySelector('[role="alert"]').textContent = "Name a role. A gap with nobody named will not get closed."; return; }
      const out = await post("/api/costs/gap", { project: b.dataset.bgGap, kind: b.dataset.kind,
        owner, by: ask.querySelector(`#${CSS.escape(id)}-b`).value });
      if (out && out.ok) { BG.said = `Recorded as unknown, owned by ${owner}.`; go("budget"); }
    };
  });
  return box;
}

/* §6 · the add form. Only the first line is required. */
function costForm(host, d, line) {
  const inp = d.inputs || {}, copy = d.copy || {}, opt = d.options || {};
  const l = line || {};
  const superseding = line && line.committed;
  const counts = opt.kinds.filter((k) => k.counts), others = opt.kinds.filter((k) => !k.counts);
  const kindRadios = (list) => list.map((k) => `<label><input type="radio" name="bg-kind" value="${k.value}"${
    (l.kind === k.value) ? " checked" : ""}> ${esc(k.label)}</label>`).join("");
  host.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${superseding ? "Record a line that supersedes this one" : line ? "Change this line" : "Record a cost line"}</h2>
    <p class="intro">${esc(copy.form_head)}</p>
    ${igText("bg-for", "What is this cost for?", "One line, in your own words. Examples: the annual license · the consultant who set it up · two weeks of clerk time every year to clean the file · getting our information out if we leave.", { value: l.what_for || "" })}
    <p class="small" id="bg-for-err" role="alert"></p>
    <fieldset class="vr-tri"><legend>Which project is this for?</legend>
      <p class="small muted vr-help" style="width:100%">A shared license covering four jobs is four projects and one line, listed under all four and counted once.</p>
      ${(d.projects || []).map((p) => `<label><input type="checkbox" name="bg-projects" value="${esc(p.ref)}"${(l.projects || []).includes(p.ref) ? " checked" : ""}> ${esc(p.name)}</label>`).join("")}
      <label style="flex:1 1 100%"><input type="checkbox" id="bg-programme"${l.not_one_project ? " checked" : ""}> Not tied to one project — this is a cost of running the program</label></fieldset>
    <div id="bg-versionbox" hidden><div class="vr-field"><label for="bg-version">Did this cost arrive with a change the vendor made?</label>
      <select id="bg-version"><option value="">No — this is not from a change</option></select></div></div>
    <fieldset class="vr-tri" style="display:block"><legend>What kind of cost is it?</legend>
      ${counts.length ? `<p class="small"><b>What you said counts as cost</b></p><div class="row" style="gap:6px 16px">${kindRadios(counts)}</div>
        ${others.length ? `<p class="small"><b>What you did not count as cost</b> — you can record one of these. Nothing here will be flagged for it, and recording it does not change your framework.</p>
        <div class="row" style="gap:6px 16px">${kindRadios(others)}</div>` : ""}`
      : `<div class="row" style="gap:6px 16px">${kindRadios(opt.kinds)}</div>
        <p class="small muted">You have not said what counts as cost. Nothing you pick here will be flagged, and picking one does not change your framework.</p>`}
      <div id="bg-otherbox" hidden>${igText("bg-other", "Say what", "", { value: l.other_kind || "" })}</div></fieldset>
    <div class="row" style="gap:16px;flex-wrap:wrap">
      <div class="vr-field" style="flex:1 1 200px"><label for="bg-est">How much? <span class="small muted">(the estimate, in dollars)</span></label>
        <input id="bg-est" inputmode="decimal" value="${esc(l.estimate ?? "")}" aria-describedby="bg-est-help bg-est-err">
        <p class="small muted" id="bg-est-help">A number you can point to a source for is worth more than a number nobody can trace.</p>
        <label class="small"><input type="checkbox" id="bg-est-unsure"${l.estimate_unsure ? " checked" : ""}> We are not sure</label>
        <p class="small" id="bg-est-err" role="alert"></p></div>
      <div class="vr-field" style="flex:1 1 200px"><label for="bg-act">What did it actually come to? <span class="small muted">(in dollars)</span></label>
        <input id="bg-act" inputmode="decimal" value="${esc(l.actual ?? "")}" aria-describedby="bg-act-help bg-act-err">
        <p class="small muted" id="bg-act-help">Leave this empty until you know. Both numbers live on this line.</p>
        <label class="small"><input type="checkbox" id="bg-act-unsure"${l.actual_unsure ? " checked" : ""}> We are not sure</label>
        <p class="small" id="bg-act-err" role="alert"></p></div></div>
    ${igRadios("bg-basis", "Per", opt.basis.map((b) => [b.value, b.label]), l.basis || "", "One basis covers both numbers on the line.")}
    <div id="bg-headbox" hidden>${igText("bg-heads", "How many people?", "Without this the line cannot be turned into a yearly figure, so it is left out of the totals and counted as left out.", { value: l.headcount || "" })}</div>
    <div id="bg-hoursbox" hidden>
      <p class="small muted">Hours are a real answer. They are reported separately and are never added to money.</p>
      ${igText("bg-hy", "Hours of staff time, every year", "", { value: l.hours_a_year || "" })}
      ${igText("bg-ho", "Hours of staff time, one-off", "", { value: l.hours_one_off || "" })}</div>
    <div id="bg-whenbox" hidden>${igRadios("bg-when", "When was the estimate made?", opt.estimate_when, l.estimate_when || "",
      "An estimate made before you committed and an estimate made after the fact are two different things, and only the first one was ever a decision.")}</div>
    ${igText("bg-based", "What are these figures based on?", "A quote, an invoice, last year's contract, a colleague's recollection.", { value: l.based_on || "" })}
    <div id="bg-inclbox" hidden>${igRadios("bg-incl", "Is the AI part included in what you already pay?", opt.included, l.included_or_extra || "",
      inp.added_ai_words ? `This is the question that turns a switched-on feature into a purchase. You said at 8.5: ${inp.added_ai_words}.` : "")}</div>
    ${igRadios("bg-whose", "Whose money is it?", opt.whose_money, l.whose_money || "")}
    ${igText("bg-starts", "When does this money start?", "", { type: "date", value: l.starts || "" })}
    ${igRadios("bg-endshow", "When does it run out?", opt.ends_how, l.ends_how || "")}
    <div id="bg-endsbox" hidden>${igText("bg-ends", "On this date", "", { type: "date", value: l.ends || "" })}</div>
    ${igText("bg-owner", "Who owns this line item — a role", "A title rather than a name, so it survives turnover.", { value: l.owner || (d.projects.find((p) => (l.projects || []).includes(p.ref)) || {}).accountable || "" })}
    <div id="bg-leavebox" hidden>${igText("bg-leave", "What does leaving actually involve?", "Getting your information out in a form you can still use · running both ways while you move across · keeping the records for as long as your retention schedule says · the staff time all of that takes.", { long: true, value: l.leaving_involves || "" })}</div>
    ${igText("bg-note", "Anything else worth recording (optional)", "", { long: true, value: l.note || "" })}
    <p class="small" id="bg-err" role="alert"></p>
    <p><button type="button" class="btn" id="bg-save">${line && !superseding ? "Save it" : "Add it"}</button>
      <button type="button" class="btn ghost" id="bg-cancel">Cancel</button></p>`;
  const $$ = (s) => host.querySelector(s);
  const show = (id, on) => { const n = $$(id); if (n) n.hidden = !on; };
  const sync = () => {
    const kind = igPicked(host, "bg-kind"), basis = igPicked(host, "bg-basis");
    show("#bg-otherbox", kind === "other");
    show("#bg-headbox", basis === "per_person_month");
    show("#bg-hoursbox", (opt.hours_kinds || []).includes(kind));
    show("#bg-whenbox", !!igVal(host, "bg-est") || $$("#bg-est-unsure").checked);
    show("#bg-leavebox", kind === "exit");
    show("#bg-endsbox", igPicked(host, "bg-endshow") === "On this date");
    const picked = [...host.querySelectorAll('[name="bg-projects"]:checked')].map((c) => c.value);
    const proj = (d.projects || []).filter((p) => picked.includes(p.ref));
    const versions = proj.flatMap((p) => p.versions || []);
    show("#bg-versionbox", versions.length > 0);
    show("#bg-inclbox", proj.some((p) => ["activated", "found"].includes(p.route)));
    const sel = $$("#bg-version");
    if (versions.length && sel.options.length === 1) versions.forEach((v) => {
      const o = document.createElement("option"); o.value = v.ref || v.id || ""; o.textContent = v.said || v.what || v.ref || "";
      if (o.value === l.version) o.selected = true; sel.appendChild(o);
    });
  };
  host.addEventListener("change", sync);
  host.addEventListener("input", sync);
  sync();
  $$("#bg-cancel").onclick = () => { host.remove(); $("#bgNew").focus(); };
  $$("#bg-save").onclick = async () => {
    ["#bg-err", "#bg-for-err", "#bg-est-err", "#bg-act-err"].forEach((s) => { $$(s).textContent = ""; });
    const whatFor = igVal(host, "bg-for");
    if (!whatFor && !(line && !superseding)) { $$("#bg-for-err").textContent = "Say what this cost is for, in one line."; $$("#bg-for").focus(); return; }
    const body = {
      ref: line && !superseding ? line.ref : "",
      supersedes: superseding ? line.ref : "",
      what_for: whatFor, kind: igPicked(host, "bg-kind"), other_kind: igVal(host, "bg-other"),
      projects: [...host.querySelectorAll('[name="bg-projects"]:checked')].map((c) => c.value),
      not_one_project: $$("#bg-programme").checked, version: igVal(host, "bg-version"),
      estimate: igVal(host, "bg-est"), actual: igVal(host, "bg-act"),
      estimate_unsure: $$("#bg-est-unsure").checked, actual_unsure: $$("#bg-act-unsure").checked,
      basis: igPicked(host, "bg-basis"), headcount: igVal(host, "bg-heads"),
      hours_a_year: igVal(host, "bg-hy"), hours_one_off: igVal(host, "bg-ho"),
      estimate_when: igPicked(host, "bg-when"), based_on: igVal(host, "bg-based"),
      included_or_extra: igPicked(host, "bg-incl"), whose_money: igPicked(host, "bg-whose"),
      starts: igVal(host, "bg-starts"), ends_how: igPicked(host, "bg-endshow"),
      ends: igPicked(host, "bg-endshow") === "On this date" ? igVal(host, "bg-ends") : "",
      owner: igVal(host, "bg-owner"), leaving_involves: igVal(host, "bg-leave"), note: igVal(host, "bg-note"),
    };
    const out = await post("/api/costs", body);
    if (!out || !out.ok) {
      const where = out && out.field === "estimate" ? "#bg-est-err" : out && out.field === "actual" ? "#bg-act-err"
        : out && out.field === "what_for" ? "#bg-for-err" : "#bg-err";
      $$(where).textContent = (out && out.error) || "That did not save.";
      return;
    }
    BG.said = superseding ? "Recorded. The earlier line is marked superseded and stays on the list."
      : line ? "Saved." : `Written down as ${out.line.ref}. Line status: Open. Not committed.`;
    go("budget");
  };
}

/* Oversight — who decides, and what happens when it goes wrong. One entry per
   decision: one thing decided, by one recorded decider, on one date. Replaces
   a screen built on the reference agency's incident levels. */
const OV = { tab: "decisions", said: "", filter: "" };

VIEWS.oversight = async () => {
  const d = await api("/api/oversight");
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    const p = el("div", "panel");
    p.innerHTML = `<p class="intro">${esc(d.why || "This is part of the subscription.")}</p>`;
    $("#view").appendChild(p);
    return;
  }
  const inp = d.inputs || {}, copy = d.copy || {};
  const root = el("div");
  const live = el("p", "vh"); live.setAttribute("aria-live", "polite");
  root.appendChild(live);

  const head = el("div", "panel");
  head.innerHTML = `
    <p class="intro" style="margin-top:0">The record of every decision made under your
      framework: who decided, on what day, under whose authority, and what they
      attached to it.</p>
    <p class="small"><a href="#ovFindings">Skip to the findings</a> ·
      <a href="#ovList">Skip to the list</a></p>
    <p><button type="button" class="btn" id="ovNew">Record a decision</button></p>`;
  root.appendChild(head);

  // §2 · five counters and the adoption line.
  const c = d.counters || {};
  const roles = c.roles_held || {};
  const stats = el("section", "panel");
  stats.setAttribute("aria-label", "Counts");
  const tile = (n, label, go_) => go_
    ? `<button type="button" class="vr-tile ov-tile" data-ov-go="${go_}"><b>${n || 0}</b><span>${esc(label)}</span></button>`
    : `<div class="vr-tile"><b>${esc(String(n))}</b><span>${esc(label)}</span></div>`;
  stats.innerHTML = `<div class="vr-tiles">
      ${tile(c.recorded, "Decisions recorded", "decisions:")}
      ${tile(c.asked_not_decided, "Asked for, not yet decided", "decisions:waiting")}
      ${tile(c.conditions_open, "Conditions still open", "conditions:open")}
      ${tile(c.conditions_overdue, "Conditions past their date", "conditions:past")}
      ${tile(roles.shown_as || "1 of 3", "Roles held by one person")}</div>
    <p class="small muted" style="margin:8px 0 0">${esc(roles.says || "")}</p>
    <p class="vr-money">${esc(d.adoption_line)}</p>`;
  stats.querySelectorAll("[data-ov-go]").forEach((b) => b.onclick = () => {
    const [tab, filter] = b.dataset.ovGo.split(":");
    OV.tab = tab; OV.filter = filter; go("oversight");
  });
  root.appendChild(stats);

  // §3 · findings.
  const raised = d.raised || [];
  const whatOf = Object.fromEntries((d.decisions || []).map((r) => [r.ref, r.what]));
  const f = el("section", "panel");
  f.id = "ovFindings";
  f.setAttribute("aria-labelledby", "ovFindingsH");
  f.innerHTML = `<h2 class="sub3" id="ovFindingsH" style="margin-top:0">${raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"}` : "Nothing to flag"}</h2>
    ${raised.length ? `<ul class="vr-flags">${raised.map((x) => `<li>${whatOf[x.entry]
      ? `<b>${esc(whatOf[x.entry])}</b> ` : ""}${esc(x.says)}</li>`).join("")}</ul>`
      : `<p class="intro">${esc(d.nothing_to_flag)}</p>`}`;
  root.appendChild(f);

  // §4 · the standing watch, and §4A · what you said happens when it goes wrong.
  const w = d.standing_watch || {};
  const watch = el("section", "panel");
  watch.setAttribute("aria-labelledby", "ovWatchH");
  watch.innerHTML = `<h2 class="sub3" id="ovWatchH" style="margin-top:0">The standing watch</h2>
    <p class="small muted">${esc(w.says)}</p>
    <div class="vr-tiles">${[[w.with_a_date, "Conditions with a date"],
      [w.coming_due_shown, "Coming due before your next look"],
      [w.past_their_date, "Past their date"], [w.no_date_set, "With no date set"]]
      .map(([n, l]) => `<div class="vr-tile"><b>${esc(String(n ?? 0))}</b><span>${esc(l)}</span></div>`).join("")}</div>
    ${w.coming_due_note ? `<p class="small">${esc(w.coming_due_note)}</p>` : ""}
    <p><button type="button" class="btn ghost" id="ovCheck">Check the dates now</button></p>
    <p class="small">${esc(w.cannot)}</p>`;
  watch.querySelector("#ovCheck").onclick = () => {
    OV.said = `Standing watch finished. ${w.past_their_date || 0} conditions past their date.`;
    go("oversight");
  };
  root.appendChild(watch);

  const ww = d.when_it_goes_wrong || {};
  const wrong = el("section", "panel");
  wrong.setAttribute("aria-labelledby", "ovWrongH");
  wrong.innerHTML = `<h2 class="sub3" id="ovWrongH" style="margin-top:0">${esc(ww.heading || "")}</h2>
    <table class="vr-table"><caption class="vh">What you said happens when a tool produces a wrong or harmful result</caption>
    <tbody>${(ww.rows || []).map((r) => `<tr><th scope="row">${esc(r.label)}</th>
      <td>${(r.lines || []).map((l) => esc(l)).join("<br>")}</td></tr>`).join("")}</tbody></table>
    <p class="small muted">This is read from your framework and edited by recording a
      standing decision or an amendment, never by typing here.</p>
    <p><button type="button" class="btn ghost" id="ovWentWrong">Record something that went wrong</button></p>`;
  root.appendChild(wrong);

  // §5 · the two views.
  root.appendChild(oversightLists(d));

  // §7 · their own labels, collapsed at the foot and off the first-run path.
  const lab = el("section", "panel");
  lab.innerHTML = `<details${d.labels_on ? " open" : ""}><summary>Do you keep your own labels for information?</summary>
    <p class="small">Most organizations do not, and nothing here needs them. This is not
      part of your framework and nothing here is asking you for it. If you already label
      information — for records, for freedom-of-information handling, for any reason of
      your own — you can put your labels in and they will be offered back to you wherever
      information is recorded.</p>
    ${igRadios("ov-labels-on", "Do you keep your own labels?", ["Yes", "No"],
      d.labels_on ? "Yes" : "")}
    <div id="ovLabelsBox"${d.labels_on ? "" : " hidden"}>
      <p class="small">${esc(copy.labels_says)}</p>
      ${igText("ov-labels", "Your labels, one per line", "Your words, in your order. They are offered back as written.",
        { long: true, value: (d.labels || []).join("\n") })}
      <p><button type="button" class="btn ghost" id="ovLabelsSave">Keep these labels</button></p></div></details>`;
  lab.querySelectorAll('[name="ov-labels-on"]').forEach((r) => r.onchange = async () => {
    const on = igPicked(lab, "ov-labels-on") === "Yes";
    await post("/api/decisions/labels", { on });
    lab.querySelector("#ovLabelsBox").hidden = !on;
  });
  lab.querySelector("#ovLabelsSave").onclick = async () => {
    const labels = igVal(lab, "ov-labels").split("\n").map((s) => s.trim()).filter(Boolean);
    const out = await post("/api/decisions/labels", { labels });
    if (out && out.ok) { OV.said = "Kept."; go("oversight"); }
  };
  root.appendChild(lab);

  const scope = el("div", "panel");
  scope.innerHTML = `<p class="small">${esc(copy.scope)}</p>`;
  root.appendChild(scope);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  live.textContent = OV.said || (raised.length ? `${raised.length} finding${raised.length === 1 ? "" : "s"}.` : "");
  OV.said = "";

  const open = (kind) => {
    const old = $("#ovForm"); if (old) old.remove();
    const host = el("section", "panel");
    host.id = "ovForm";
    head.after(host);
    decisionForm(host, d, kind);
    const h = host.querySelector("h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  };
  $("#ovNew").onclick = () => open("");
  $("#ovWentWrong").onclick = () => open("kind.went_wrong");
};

/* §5 · the tab set: Decisions and Conditions. A real tablist, with arrow keys
   moving between tabs. */
function oversightLists(d) {
  const box = el("section", "panel");
  box.id = "ovList";
  box.setAttribute("aria-label", "Decisions and conditions");
  const tabs = [["decisions", "Decisions"], ["conditions", "Conditions"]];
  const today = localToday();
  let rows = (d.decisions || []).slice();
  if (OV.filter === "waiting") rows = rows.filter((r) => !r.outcome || r.outcome === "outcome.deferred");
  rows.sort((a, b) => (!!a.outcome - !!b.outcome) ||
    String(b.decided_on || "").localeCompare(String(a.decided_on || "")));
  let conds = (d.conditions || []).slice();
  if (OV.filter === "open") conds = conds.filter((c) => !c.closed);
  if (OV.filter === "past") conds = conds.filter((c) => c.state === "Past its date");
  const rank = (c) => c.state === "Past its date" ? 0 : c.closed ? 3 : c.by_shown === "No date set" ? 2 : 1;
  conds.sort((a, b) => rank(a) - rank(b) || String(a.by_shown).localeCompare(String(b.by_shown)));

  const decisionsTable = rows.length ? `<div class="vr-scroll" tabindex="0" role="region" aria-label="Decisions table">
    <table class="vr-table"><caption class="vh">Decisions${OV.filter === "waiting" ? ", not decided yet" : ""}, not decided first, then most recent</caption>
    <thead><tr>${["What was decided", "About", "Gate", "Who decided", "Date", "Outcome", "Conditions"]
      .map((h) => `<th scope="col">${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>
      <th scope="row">${esc(r.what)}<br><span class="small muted">${esc(r.ref)} · ${esc(r.kind_shown)}</span></th>
      <td>${esc(r.about_shown)}</td><td>${esc(r.gate_shown)}</td>
      <td>${esc([r.decider, r.hat_worn && r.decider ? `as ${hatName(r.hat_worn)}` : ""].filter(Boolean).join(", ") || "Not recorded")}</td>
      <td>${esc(r.date_shown)}${r.before_framework ? `<br><span class="small">${esc(d.before_framework_label)}</span>` : ""}</td>
      <td>${esc(r.outcome_shown)}</td><td>${esc(r.conditions_shown)}</td></tr>`).join("")}</tbody></table></div>`
    : `<p class="intro">${esc((d.decisions || []).length
      ? `Nothing matches those filters. No decision is ever removed from this list, so what you are looking for is here under a different filter.`
      : d.empty_state)}</p>`;
  const conditionsTable = conds.length ? `<div class="vr-scroll" tabindex="0" role="region" aria-label="Conditions table">
    <table class="vr-table"><caption class="vh">Conditions, past their date first</caption>
    <thead><tr>${["What has to happen", "Who owns it", "By when", "State", "From this decision", "About", "Gate it was attached at", ""]
      .map((h) => `<th scope="col">${h || '<span class="vh">Actions</span>'}</th>`).join("")}</tr></thead>
    <tbody>${conds.map((c) => `<tr>
      <th scope="row">${esc(c.what)}</th><td>${esc(c.owner)}</td><td>${esc(c.by_shown)}</td>
      <td>${esc(c.state)}</td><td>${esc(c.from)}</td><td>${esc(c.about === "framework" ? "The framework itself" : c.about)}</td>
      <td>${esc(c.gate_shown)}</td>
      <td>${c.closed ? "" : `<button type="button" class="btn ghost" data-ov-close="${esc(c.decision)}" data-index="${c.index}">Close it</button>
        <span class="small" role="alert" data-ov-err="${esc(c.decision)}-${c.index}"></span>`}</td></tr>`).join("")}</tbody></table></div>`
    : `<p class="intro">${(d.conditions || []).length
      ? `No conditions match those filters. Clear them to see all ${(d.conditions || []).length} conditions.`
      : "No conditions attached to anything. That is a real answer. Approving something outright is a decision, and this stays empty until somebody attaches a condition."}</p>`;

  box.innerHTML = `<div role="tablist" aria-label="Views" class="row" style="gap:8px">
      ${tabs.map(([k, l]) => `<button type="button" role="tab" id="ovTab-${k}" aria-controls="ovPanel-${k}"
        aria-selected="${OV.tab === k}" tabindex="${OV.tab === k ? 0 : -1}" class="btn ${OV.tab === k ? "" : "ghost"}">${l}</button>`).join("")}
    </div>
    ${OV.filter ? `<p class="small">Showing ${OV.filter === "waiting" ? "only what is not decided yet"
      : OV.filter === "open" ? "only open conditions" : "only conditions past their date"}.
      <button type="button" class="btn ghost" id="ovClear">Clear</button></p>` : ""}
    <div role="tabpanel" id="ovPanel-decisions" aria-labelledby="ovTab-decisions"${OV.tab === "decisions" ? "" : " hidden"}>${decisionsTable}</div>
    <div role="tabpanel" id="ovPanel-conditions" aria-labelledby="ovTab-conditions"${OV.tab === "conditions" ? "" : " hidden"}>${conditionsTable}</div>`;

  const select = (k, focus) => { OV.tab = k; OV.filter = "";
    Promise.resolve(go("oversight")).then(() => {
      const t = $(`#ovTab-${k}`); if (t && focus) t.focus(); }); };
  box.querySelectorAll('[role="tab"]').forEach((t, i) => {
    t.onclick = () => select(tabs[i][0], true);
    t.onkeydown = (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        select(tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length][0], true);
      }
    };
  });
  const clear = box.querySelector("#ovClear");
  if (clear) clear.onclick = () => { OV.filter = ""; go("oversight"); };
  box.querySelectorAll("[data-ov-close]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/decisions/condition/close",
      { decision: b.dataset.ovClose, index: Number(b.dataset.index) });
    if (out && out.ok) { OV.said = "Closed. It stays on the list."; go("oversight"); }
    else { const n = box.querySelector(`[data-ov-err="${b.dataset.ovClose}-${b.dataset.index}"]`);
      if (n) n.textContent = (out && out.error) || ""; }
  });
  return box;
}

function hatName(h) {
  return { operator: "User", ot: "Office of Technology", "council-member": "Decision-maker" }[h] || h;
}

/* §6 · the form. Only the line saying what was decided is required. */
function decisionForm(host, d, presetKind) {
  const inp = d.inputs || {}, rb = inp.readbacks || {}, copy = d.copy || {},
        opt = d.options || {};
  const today = localToday();
  const shape = d.shape;
  const deciders = [...new Set([...(inp.seats || []), "The adopting authority"].filter(Boolean))];
  const checks = (name, legend, options, chosen, help) => `<fieldset class="vr-tri">
    <legend>${esc(legend)}</legend>
    ${help ? `<p class="small muted vr-help" style="width:100%">${esc(help)}</p>` : ""}
    ${options.map(([v, l, note]) => `<label style="flex:1 1 100%"><input type="checkbox" name="${name}" value="${esc(v)}"${
      (chosen || []).includes(v) ? " checked" : ""}> ${esc(l)}${note ? ` <span class="small muted">${esc(note)}</span>` : ""}</label>`).join("")}</fieldset>`;
  host.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Record a decision</h2>
    <p class="intro">${esc(copy.only_what)}</p>
    <fieldset class="vr-tri" style="display:block"><legend>What kind of decision is this?</legend>
      <p class="small muted">This only changes which questions you see next. Everything lands on the same list.</p>
      ${opt.kinds.map((k) => `<label style="display:flex;margin:6px 0"><input type="radio" name="ov-kind" value="${k.value}"${
        (presetKind || "kind.tool") === k.value ? " checked" : ""}> <span><b>${esc(k.name)}</b> — ${esc(k.says)}</span></label>`).join("")}
    </fieldset>
    <div class="vr-field"><label for="ov-what">What was decided <span class="small">(required)</span></label>
      <p class="small muted vr-help" id="ov-what-help">One line, in your own words, the way you would say it to somebody in the hallway.${inp.example ? ` For example: “${esc(inp.example)}”.` : ""}</p>
      <input id="ov-what" aria-describedby="ov-what-help ov-what-err" required aria-required="true">
      <p class="small" id="ov-what-err" role="alert"></p></div>
    ${igText("ov-on", "On what date", "The day it was actually decided, not the day you are typing it. Recording something after the fact is normal and the list will show both dates.", { type: "date", value: today })}
    <div class="vr-field"><label for="ov-decider">Who decided</label>
      <p class="small muted vr-help" id="ov-decider-help">The role, not the person's name; titles survive turnover.</p>
      <input id="ov-decider" list="ov-decider-list" aria-describedby="ov-decider-help">
      <datalist id="ov-decider-list">${deciders.map((x) => `<option value="${esc(x)}">`).join("")}</datalist></div>
    ${igRadios("ov-hat", "Which hat was worn", [["operator", "User"], ["ot", "Office of Technology"], ["council-member", "Decision-maker"]],
      d.hat, "The application records the hat, not a second person. This is what keeps the trail from showing two participants where there was one.")}
    ${igRadios("ov-how", "How it was decided", opt.how_decided.map((o) => [o.value, o.label]), "")}
    <div class="vr-field" id="ov-aboutbox"><label for="ov-about">What it was about</label>
      <select id="ov-about"><option value="">Not written up yet</option>
        ${(d.projects || []).map((p) => `<option value="${esc(p.ref)}">${esc(p.ref)} · ${esc(p.name)}</option>`).join("")}</select></div>
    <div class="vr-field" id="ov-gatebox"><label for="ov-gate">Which gate this was at</label>
      <p class="small muted vr-help" id="ov-gate-help">The gate the record was standing at when you decided. Choosing one here proposes the move; the project is what actually moves.</p>
      <select id="ov-gate" aria-describedby="ov-gate-help"><option value="">Not at a gate</option>
        ${opt.gates.map((g) => `<option value="${g.id}">${esc(g.name)}</option>`).join("")}</select></div>
    <div id="ov-outcomebox">${igRadios("ov-outcome", "Outcome", opt.outcomes.map((o) => [o.value, o.label]), "",
      "Choosing an outcome here proposes the matching move. The record's own state is written on the project, so what you record here is the decision itself. Leaving this blank is a real answer; the list will show it as not decided yet.")}</div>
    <div id="ov-consultbox">${(inp.must_consult || []).length || (inp.consult_outside || []).length
      ? checks("ov-consulted", "Who was asked before this", (inp.must_consult || []).map((p) => [p, p, "you said this has to be asked"]), [])
        + (inp.consult_outside || []).map((p) => `<p class="small">${esc(p)} — you said outside help would be needed here. That is recorded as a gap.</p>`).join("")
      : ""}</div>
    <h3 class="sub3">Conditions</h3>
    <p class="small muted">A condition with nobody's name on it will not get done. A condition with no date will not come back on its own, and this list will say so.</p>
    <div id="ov-conds"></div>
    ${igText("ov-why", "Why (optional)", "The reason, in your own words. This is the field somebody reads two years from now when they are asked why.", { long: true })}
    ${shape !== "one" ? igText("ov-disagreed", "Anything anyone disagreed with (optional)", "Recorded as written, attributed to a role if you want it attributed.", { long: true }) : ""}
    ${igText("ov-where", "Where else this is written down", "Pre-filled with what you told us at Step 4. Change it here if this one went somewhere else.", { value: inp.decision_place || "" })}
    <div id="ov-kindblock"></div>
    <p class="small" id="ov-err" role="alert" aria-live="assertive"></p>
    <div id="ov-anyway" hidden>${igText("ov-reason", "Why record it anyway", "One line.")}</div>
    <p><button type="button" class="btn" id="ov-save">Add it</button>
      <button type="button" class="btn ghost" id="ov-cancel">Cancel</button></p>`;

  const $$ = (s) => host.querySelector(s);
  const conds = prRows($$("#ov-conds"), [["what", "What has to happen"],
    ["owner", "Who owns it"], ["by", "By when", "date"]], [], "Condition");
  let weightRows = null, factorRows = null, toldRows = null;
  const block = $$("#ov-kindblock");
  const drawKind = () => {
    const kind = igPicked(host, "ov-kind");
    $$("#ov-aboutbox").hidden = ["kind.framework", "kind.weights", "kind.standing"].includes(kind);
    $$("#ov-consultbox").hidden = kind !== "kind.tool";
    weightRows = factorRows = toldRows = null;
    if (kind === "kind.framework") {
      const amendSaid = inp.amend_words ? `You said ${inp.amend_words}.` : "";
      const owedPre = inp.amend === "group_alone" ? "Not required, we said the group can change it on its own" : "Not yet";
      block.innerHTML = `<h3 class="sub3">About the framework itself</h3>
        ${igRadios("ov-fw", "What is this?", opt.framework_what, "")}
        ${igText("ov-adopter", "Adopted by", "The title of whoever adopted it — 'the Board of Commissioners', 'the City Manager'. A title, not a person's name; titles survive turnover. They do not need an account here.")}
        ${igText("ov-effective", "Effective date", "The day it starts binding, which is often not the day it was signed.", { type: "date" })}
        ${igText("ov-changed", "What changed", "In your own words. Only the records whose answers actually moved will be flagged.", { long: true })}
        ${igRadios("ov-owed", "What was owed to the adopting authority, and was it done", opt.owed, owedPre, "", amendSaid)}
        ${igText("ov-back", "When it comes back", inp.review_words ? `You said ${inp.review_words}. Change it here if that changed.` : "", { type: "date" })}`;
    } else if (kind === "kind.went_wrong") {
      block.innerHTML = `<h3 class="sub3">About something that went wrong</h3>
        <p class="vr-tell">Record the event on Integrity. What you decided about it goes here.</p>
        <div class="vr-field"><label for="ov-incident">Which one</label>
          <select id="ov-incident"><option value="">Not recorded there yet</option>
          ${(d.incidents || []).map((i) => `<option value="${esc(i.ref)}">${esc(i.ref)} · ${esc(i.what)}</option>`).join("")}</select></div>
        ${(inp.severities || []).length ? igRadios("ov-sev", "How serious", inp.severities.map((s) => [s.label, `${s.label} — ${s.meaning}`]), "") : ""}
        ${igRadios("ov-stopped", "Was the tool stopped?", opt.stopped, "", (inp.stoppers || []).length ? `You said ${inp.stoppers.join(", ")} can stop a tool without waiting for a meeting.` : "")}
        ${igText("ov-stopby", "Who stopped it (if it was)", "")}
        ${igText("ov-stopat", "When", "", { type: "datetime-local" })}
        <fieldset class="vr-tri" style="display:block"><legend>Who was told, and when</legend><div id="ov-told"></div></fieldset>
        ${inp.lookback_yes ? igRadios("ov-lookback", "Did you go back over earlier work?", opt.lookback, "", "",
          `You said ${inp.lookback_period || "you go back"}. If a tool was wrong today it was probably wrong yesterday.`) : ""}
        ${igText("ov-restart", "What has to be true before it goes back on", "This becomes a condition on the record with an owner and a date.", { long: true })}
        ${igText("ov-restartowner", "Who owns that — role", "")}
        ${igText("ov-restartby", "By when", "", { type: "date" })}
        ${igText("ov-writeup", "Who writes it up", "", { value: inp.writes_up || "" })}`;
      toldRows = prRows(block.querySelector("#ov-told"), [["party", "Who"], ["when", "When", "date"],
        ["not_told", "Not told — why"]], (inp.must_tell || []).map((p) => ({ party: p })), "Party");
    } else if (kind === "kind.standing") {
      block.innerHTML = `<h3 class="sub3">A standing decision</h3>
        ${igRadios("ov-which", "Which one", opt.standing_which, "")}
        ${igText("ov-saysnow", "What it says now", "Edited rather than composed.", { long: true })}
        ${igRadios("ov-changes", "Does this change the framework?", opt.standing_changes, "",
          "A standing decision that changes the rules is an amendment; one that interprets them is not. Say which, and the list will show it as what it is.")}`;
    } else if (kind === "kind.weights") {
      block.innerHTML = `<h3 class="sub3">About how candidates are weighed</h3>
        <p class="small">${esc(d.scoring_line)}</p>
        ${igRadios("ov-ww", "What is this?", opt.weights_what, "")}
        <fieldset class="vr-tri" style="display:block"><legend>What is being weighed</legend>
          <p class="small muted">Your axes and your weights. The application offers none of its own and computes nothing until you have settled what you are weighing and how heavily; until then, candidates are shown side by side and nothing is ranked.</p>
          <div id="ov-axes"></div></fieldset>
        ${inp.single_factor ? `<fieldset class="vr-tri" style="display:block"><legend>Where one factor settles it on its own</legend>
          <p class="small muted">You said a tool rating high on any single factor goes to your highest level even where everything else is low.${(inp.factors || []).length ? ` The factors you marked as mattering: ${esc(inp.factors.join("; "))}.` : ""}</p>
          <div id="ov-factors"></div></fieldset>` : ""}
        ${igText("ov-wowner", "Who owns these weights — role", "The role that answers for these when somebody asks why the ranking came out the way it did.")}
        ${igText("ov-wfrom", "From what date", "Comparisons already run keep the weights they were run with. Nothing is recomputed behind somebody's back.", { type: "date" })}
        ${igText("ov-wchanged", "What changed, and why", "", { long: true })}`;
      weightRows = prRows(block.querySelector("#ov-axes"), [["axis", "The axis, in your own words"],
        ["weight", "The weight it carries", "number"], ["why", "One line on why"]], [], "Axis");
      const fh = block.querySelector("#ov-factors");
      if (fh) factorRows = prRows(fh, [["factor", "The factor, in your words"]], [], "Factor");
    } else {
      block.innerHTML = "";
    }
  };
  host.querySelectorAll('[name="ov-kind"]').forEach((r) => r.onchange = drawKind);
  drawKind();
  $$("#ov-cancel").onclick = () => { host.remove(); $("#ovNew").focus(); };

  $$("#ov-save").onclick = async () => {
    const err = $$("#ov-err"), whatErr = $$("#ov-what-err");
    err.textContent = ""; whatErr.textContent = "";
    const what = igVal(host, "ov-what");
    if (!what) { whatErr.textContent = "Say what was decided, in one line."; $$("#ov-what").focus(); return; }
    const kind = igPicked(host, "ov-kind") || "kind.tool";
    const body = {
      kind, what, decided_on: igVal(host, "ov-on"), decider: igVal(host, "ov-decider"),
      hat_worn: igPicked(host, "ov-hat"), how_decided: igPicked(host, "ov-how"),
      about: igVal(host, "ov-about"), gate: igVal(host, "ov-gate"),
      outcome: igPicked(host, "ov-outcome"),
      consulted: [...host.querySelectorAll('[name="ov-consulted"]:checked')].map((c) => c.value),
      conditions: conds.read().filter((c) => c.what),
      why: igVal(host, "ov-why"), disagreed: igVal(host, "ov-disagreed"),
      where_else: igVal(host, "ov-where"), anyway_reason: igVal(host, "ov-reason"),
    };
    if (kind === "kind.framework") Object.assign(body, {
      framework_what: igPicked(host, "ov-fw"), adopted_by_title: igVal(host, "ov-adopter"),
      effective_on: igVal(host, "ov-effective"), what_changed: igVal(host, "ov-changed"),
      owed: igPicked(host, "ov-owed"), comes_back: igVal(host, "ov-back") });
    if (kind === "kind.went_wrong") Object.assign(body, {
      incident: igVal(host, "ov-incident"), severity: igPicked(host, "ov-sev"),
      was_stopped: igPicked(host, "ov-stopped"), stopped_by: igVal(host, "ov-stopby"),
      stopped_at: igVal(host, "ov-stopat"), told: toldRows ? toldRows.read() : [],
      lookback: igPicked(host, "ov-lookback"), restart_condition: igVal(host, "ov-restart"),
      restart_owner: igVal(host, "ov-restartowner"), restart_by: igVal(host, "ov-restartby"),
      writeup_by: igVal(host, "ov-writeup") });
    if (kind === "kind.standing") Object.assign(body, {
      standing_which: igPicked(host, "ov-which"), says_now: igVal(host, "ov-saysnow"),
      changes_framework: igPicked(host, "ov-changes") });
    if (kind === "kind.weights") Object.assign(body, {
      weights_what: igPicked(host, "ov-ww"), axes: weightRows ? weightRows.read() : [],
      single_factors: factorRows ? factorRows.read() : [],
      weights_owner: igVal(host, "ov-wowner"), weights_from: igVal(host, "ov-wfrom"),
      what_changed: igVal(host, "ov-wchanged") });
    const out = await post("/api/decisions", body);
    if (!out || !out.ok) {
      err.textContent = (out && out.error) || "That did not save.";
      if (out && out.needs_reason) { $$("#ov-anyway").hidden = false; $$("#ov-reason").focus(); }
      return;
    }
    OV.said = `Written down as ${out.decision.ref}.` + (out.move && !out.move.ok && out.move.says
      ? ` The project did not move: ${out.move.says}` : out.move && out.move.ok ? " The project moved." : "");
    OV.tab = "decisions"; OV.filter = "";
    go("oversight");
  };
}

/* Process — intake and the gates. One entry per standing procedure: a
   written instruction that exists once and that more than one record points
   at. Replaces a screen that mapped the reference agency's appendices and
   risk bands, which no other organization has. */
const PR = { form: null, said: "" };

VIEWS.process = async () => {
  const d = await api("/api/process");
  if (d && d.available === false) {
    $("#view").innerHTML = "";
    const p = el("div", "panel");
    p.innerHTML = `<p class="intro">${esc(d.why || "This is part of the subscription.")}</p>`;
    $("#view").appendChild(p);
    return;
  }
  const inp = d.inputs || {}, copy = d.copy || {}, may = d.may || {};
  const root = el("div");
  const live = el("p", "vh"); live.setAttribute("aria-live", "polite");
  root.appendChild(live);

  const head = el("div", "panel");
  head.innerHTML = `
    <p class="intro" style="margin-top:0">How something gets proposed, what has to
      exist on paper before it moves, and where the instructions for running it live.</p>
    <p class="small"><a href="#prFindings">Skip to the findings</a> ·
      <a href="#prList">Skip to the register</a></p>
    <p><button type="button" class="btn" id="prNew">Write a procedure</button></p>`;
  root.appendChild(head);

  // §2 · five counters, and the waiting line beneath them.
  const c = d.counters || {};
  const stats = el("section", "panel");
  stats.setAttribute("aria-label", "Counts");
  stats.innerHTML = `<div class="vr-tiles">${[
      [c.written_down, "Procedures written down"], [c.in_force, "In force today"],
      [c.required_not_written, "Required here and not written"],
      [c.never_confirmed, "Never confirmed since it was written"],
      [c.past_its_date, "Past the date its owner set"]]
    .map(([n, l]) => `<div class="vr-tile"><b>${n || 0}</b><span>${esc(l)}</span></div>`).join("")}</div>
    <p class="vr-money">${esc(d.waiting_line)}</p>`;
  root.appendChild(stats);

  // Seeding, on first use — an offer with a preview, never automatic.
  if ((d.seed || []).length) {
    const seed = el("section", "panel");
    seed.setAttribute("aria-labelledby", "prSeedH");
    seed.innerHTML = `<h2 class="sub3" id="prSeedH" style="margin-top:0">Start from your framework</h2>
      <p class="intro">These would be written from your own answers, every one of them
        as drafted and not adopted, so somebody still has to put each in force.</p>
      <ul class="vr-flags">${d.seed.map((s) => `<li><b>${esc(s.name)}</b>
        <span class="muted">${esc(s.kind)}${(s.items || []).length
          ? ` · ${s.items.length} item${s.items.length === 1 ? "" : "s"} from what you said has to exist` : ""}</span></li>`).join("")}</ul>
      <p><button type="button" class="btn" id="prSeed">Write these as drafts</button></p>`;
    seed.querySelector("#prSeed").onclick = async () => {
      const out = await post("/api/procedures/seed", {});
      if (out && out.ok) { PR.said = `Written as drafts: ${out.made.length}.`; go("process"); }
      else toast((out && out.error) || "That did not work.", true);
    };
    root.appendChild(seed);
  }

  // §3 · findings.
  const raised = d.raised || [];
  const byRef = Object.fromEntries((d.procedures || []).map((p) => [p.ref, p]));
  const projByRef = Object.fromEntries((d.projects || []).map((p) => [p.ref, p]));
  const about = (ref) => (byRef[ref] || {}).name || (projByRef[ref] || {}).name || "";
  const f = el("section", "panel");
  f.id = "prFindings";
  f.setAttribute("aria-labelledby", "prFindingsH");
  f.innerHTML = `<h2 class="sub3" id="prFindingsH" style="margin-top:0">${raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"}` : "Nothing to flag"}</h2>
    ${raised.length ? `<ul class="vr-flags">${raised.map((x) => `<li>${about(x.entry)
      ? `<b>${esc(about(x.entry))}</b> ` : ""}${esc(x.says)}</li>`).join("")}</ul>`
      : `<p class="intro">${esc(d.clean_state)}</p>`}`;
  root.appendChild(f);

  // §4 · the standing check.
  const sc = d.standing_check || {};
  const recordable = (d.options.recordable || []).filter((t) => (inp.triggers || []).includes(t));
  const check = el("section", "panel");
  check.setAttribute("aria-labelledby", "prCheckH");
  check.innerHTML = `<h2 class="sub3" id="prCheckH" style="margin-top:0">The standing check</h2>
    <div class="vr-tiles">${[[sc.watched, "Watched"], [sc.current, "Current"],
      [sc.past_their_date, "Past their date"], [sc.overtaken, "Overtaken by something"]]
      .map(([n, l]) => `<div class="vr-tile"><b>${n || 0}</b><span>${esc(l)}</span></div>`).join("")}</div>
    ${(sc.results || []).filter((r) => !r.state.includes("Current")).length
      ? `<ul class="vr-flags">${sc.results.filter((r) => !r.state.includes("Current")).map((r) =>
        `<li><b>${esc(about(r.procedure))}</b> ${esc(r.state.join(" · "))}${
          (r.fired || []).length ? ` <span class="muted">${esc(r.fired.join("; "))}</span>` : ""}</li>`).join("")}</ul>` : ""}
    <p><button type="button" class="btn ghost" id="prCheck">Check them all now</button></p>
    ${recordable.length ? `<details><summary>Record that something happened</summary>
      <p class="small muted">A person writes these down. Nothing here watches the statute
        book, a budget office or a vendor.</p>
      ${igRadios("pr-ev", "What happened?", recordable, "")}
      ${igText("pr-evon", "When?", "", { type: "date" })}
      ${igText("pr-evnote", "Anything to add (optional)", "")}
      <p><button type="button" class="btn ghost" id="prEvent">Record it</button>
        <span class="small" id="prEventErr" role="alert"></span></p></details>` : ""}
    <details><summary>What this check cannot see</summary>
      ${String(copy.check_cannot || "").split("\n\n").map((p) => `<p class="small">${esc(p)}</p>`).join("")}</details>`;
  check.querySelector("#prCheck").onclick = () => {
    PR.said = `Standing check finished. ${sc.watched || 0} watched, ${sc.past_their_date || 0} past their date.`;
    go("process");
  };
  const evBtn = check.querySelector("#prEvent");
  if (evBtn) evBtn.onclick = async () => {
    const out = await post("/api/procedures/event", {
      trigger: igPicked(check, "pr-ev"), on: igVal(check, "pr-evon"),
      note: igVal(check, "pr-evnote") });
    if (out && out.ok) { PR.said = "Recorded."; go("process"); }
    else check.querySelector("#prEventErr").textContent = (out && out.error) || "";
  };
  root.appendChild(check);

  // §5 · the register — ghost rows first, then what is missing, then A to Z.
  root.appendChild(processRegister(d, may));

  const scope = el("div", "panel");
  scope.innerHTML = `<p class="small">${esc(copy.scope)}</p>`;
  root.appendChild(scope);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  live.textContent = PR.said || (raised.length
    ? `${raised.length} finding${raised.length === 1 ? "" : "s"} on this surface.` : "");
  PR.said = "";

  const openForm = (proc, preset) => {
    const old = $("#prForm"); if (old) old.remove();
    const host = el("section", "panel");
    host.id = "prForm";
    head.after(host);
    procedureForm(host, d, proc, preset);
    const h = host.querySelector("h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  };
  $("#prNew").onclick = () => openForm(null, null);
  $("#view").querySelectorAll("[data-pr-edit]").forEach((b) =>
    b.onclick = () => openForm(byRef[b.dataset.prEdit], null));
  $("#view").querySelectorAll("[data-pr-ghost]").forEach((b) => b.onclick = () => {
    const g = (d.ghosts || [])[Number(b.dataset.prGhost)] || {};
    openForm(null, { kind: g.kind, levels: g.level ? [g.level] : [] });
  });
  if (PR.form) { const f2 = PR.form; PR.form = null; openForm(byRef[f2] || null, null); }
};

function processRegister(d, may) {
  const box = el("section", "panel");
  box.id = "prList";
  box.setAttribute("aria-labelledby", "prListH");
  const rows = (d.procedures || []).slice();
  const today = localToday();
  const rank = (p) => p.status === "In force" && !p.confirmed_on ? 0
    : p.status === "In force" && p.look_again_date && p.look_again_date < today ? 1 : 2;
  rows.sort((a, b) => rank(a) - rank(b) || String(a.name).localeCompare(String(b.name)));
  const ghosts = d.ghosts || [];
  const actions = (p) => {
    const out = [`<button type="button" class="btn ghost" data-pr-edit="${esc(p.ref)}">${
      p.status === "In force" ? "Save a new version" : "Edit"}</button>`];
    if (p.status === "Drafted, not adopted" && may.adopt)
      out.push(`<button type="button" class="btn ghost" data-pr-status="In force" data-ref="${esc(p.ref)}">Put in force</button>`);
    if (p.status === "In force") {
      out.push(`<button type="button" class="btn ghost" data-pr-confirm="${esc(p.ref)}">Confirm it is still true</button>`);
      if (may.withdraw)
        out.push(`<button type="button" class="btn ghost" data-pr-status="Withdrawn" data-ref="${esc(p.ref)}">Withdraw</button>`);
    }
    if (p.kind === "How the work gets done when the tool is off" && p.status === "In force")
      out.push(`<button type="button" class="btn ghost" data-pr-tried="${esc(p.ref)}">Record that it was tried</button>`);
    if (p.status === "Replaced" && (p.covered_records || []).length && may.adopt)
      out.push(`<button type="button" class="btn ghost" data-pr-move="${esc(p.ref)}">Move them to the new version</button>`);
    return out.join(" ");
  };
  box.innerHTML = `
    <h2 class="sub3" id="prListH" style="margin-top:0">The register</h2>
    <p class="small muted">Sorted with what is missing at the top: kinds your answers
      require and nobody has written, then procedures in force and never confirmed, then
      those past the date their owner set, then everything else by name.</p>
    ${rows.length || ghosts.length ? `<div class="vr-scroll" tabindex="0" role="region" aria-labelledby="prListH">
      <table class="vr-table"><caption class="vh">Standing procedures, what is missing first</caption>
      <thead><tr>${["What it is called", "Kind", "Where it applies", "Who owns it",
        "Status", "Last confirmed", "Records pointing at it", ""].map((h) =>
        `<th scope="col">${h || '<span class="vh">Actions</span>'}</th>`).join("")}</tr></thead>
      <tbody>
      ${ghosts.map((g, i) => `<tr class="pr-ghost">
        <th scope="row">Not written${g.level ? ` · ${esc(g.level)}` : ""}</th>
        <td>${esc(g.kind)}</td>
        <td>${esc((g.gates || []).join(", "))}${g.level ? ` · ${esc(g.level)}` : ""}</td>
        <td colspan="4">${esc(g.says)}</td>
        <td><button type="button" class="btn ghost" data-pr-ghost="${i}">Write it</button></td></tr>`).join("")}
      ${rows.map((p) => `<tr>
        <th scope="row">${esc(p.name)}<br><span class="small muted">${esc(p.ref)}</span>${
          p.unusual ? `<br><span class="small">${esc(p.unusual)}</span>` : ""}</th>
        <td>${esc(p.kind || "Not chosen yet")}</td>
        <td>${esc(p.where_shown || "Not said yet")}</td>
        <td>${esc(p.owner_shown)}</td>
        <td>${esc(p.status)}</td>
        <td>${esc(p.confirmed_shown)}</td>
        <td>${esc(p.pointing_shown)}</td>
        <td>${actions(p)}<span class="small" role="alert" data-pr-err="${esc(p.ref)}"></span></td></tr>`).join("")}
      </tbody></table></div>`
    : `<p class="intro">${esc(d.empty_state)}</p>`}`;

  const errFor = (ref, text) => {
    const n = box.querySelector(`[data-pr-err="${ref}"]`); if (n) n.textContent = text;
  };
  box.querySelectorAll("[data-pr-status]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/procedures/status", { ref: b.dataset.ref, status: b.dataset.prStatus });
    if (out && out.ok) { PR.said = b.dataset.prStatus === "In force" ? "Put in force." : "Withdrawn. It stays on the list."; go("process"); }
    else errFor(b.dataset.ref, (out && out.error) || "");
  });
  box.querySelectorAll("[data-pr-confirm]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/procedures/confirm", { ref: b.dataset.prConfirm });
    if (out && out.ok) { PR.said = "Recorded as still true today."; go("process"); }
    else errFor(b.dataset.prConfirm, (out && out.error) || "");
  });
  box.querySelectorAll("[data-pr-tried]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/procedures/tried", { ref: b.dataset.prTried, answer: "Yes, on a date" });
    if (out && out.ok) { PR.said = "Recorded as tried today."; go("process"); }
    else errFor(b.dataset.prTried, (out && out.error) || "");
  });
  box.querySelectorAll("[data-pr-move]").forEach((b) => b.onclick = async () => {
    const out = await post("/api/procedures/move", { ref: b.dataset.prMove });
    if (out && out.ok) { PR.said = `Moved ${out.moved.length} to the new version.`; go("process"); }
    else errFor(b.dataset.prMove, (out && out.error) || "");
  });
  return box;
}

/* Repeatable rows with keyboard move-up and move-down, pre-filled so the
   person is editing rather than composing. `fields` are [key, label, type,
   options]; a row marked fixed cannot be moved or removed. */
function prRows(host, fields, initial, label, { onAdd } = {}) {
  const list = el("div");
  const say = el("p", "vh"); say.setAttribute("aria-live", "polite");
  const add = el("button", "btn ghost", `Add ${label.toLowerCase()}`);
  add.type = "button";
  host.append(list, say, add);
  const renumber = () => [...list.children].forEach((r, i) => {
    r.querySelector("legend").textContent = `${label} ${i + 1}`;
  });
  const make = (values = {}, focus = false) => {
    const row = el("fieldset", "vr-tri");
    row.dataset.fixed = values.fixed ? "1" : "";
    row.innerHTML = `<legend></legend>` + fields.map(([k, l, type, opts]) => {
      const v = values[k];
      if (type === "select") return `<label style="flex:1 1 200px;flex-direction:column;align-items:stretch">${esc(l)}
        <select data-k="${k}">${opts.map((o) => `<option${o === v ? " selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`;
      if (type === "check") return `<label><input type="checkbox" data-k="${k}"${v ? " checked" : ""}${
        values.fixed ? " disabled" : ""}> ${esc(l)}</label>`;
      return `<label style="flex:1 1 200px;flex-direction:column;align-items:stretch">${esc(l)}
        <input data-k="${k}" type="${type || "text"}" value="${esc(v || "")}"${
        values.fixed && k === "question" ? " readonly" : ""}></label>`;
    }).join("") + (values.fixed
      ? `<span class="small muted">This row stays first and cannot be removed.</span>`
      : `<span class="row" style="gap:6px">
          <button type="button" class="btn ghost" data-up>Move up</button>
          <button type="button" class="btn ghost" data-down>Move down</button>
          <button type="button" class="btn ghost" data-remove>Remove</button></span>`);
    const up = row.querySelector("[data-up]"), down = row.querySelector("[data-down]"),
          rm = row.querySelector("[data-remove]");
    if (up) up.onclick = () => {
      const prev = row.previousElementSibling;
      if (prev && !prev.dataset.fixed) { list.insertBefore(row, prev); renumber(); up.focus();
        say.textContent = `Moved to position ${[...list.children].indexOf(row) + 1}.`; }
    };
    if (down) down.onclick = () => {
      const next = row.nextElementSibling;
      if (next) { list.insertBefore(next, row); renumber(); down.focus();
        say.textContent = `Moved to position ${[...list.children].indexOf(row) + 1}.`; }
    };
    if (rm) rm.onclick = () => {
      const after = row.nextElementSibling || row.previousElementSibling;
      row.remove(); renumber(); say.textContent = `${label} removed.`;
      ((after && after.querySelector("input,select")) || add).focus();
    };
    list.appendChild(row); renumber();
    if (focus) { row.querySelector("input,select").focus(); say.textContent = `${label} ${list.children.length} added.`; }
    if (onAdd) onAdd(row);
  };
  (initial || []).forEach((v) => make(v));
  add.onclick = () => make({}, true);
  return { read: () => [...list.children].map((r) => ({
    ...(r.dataset.fixed ? { fixed: true, required: true } : {}),
    ...Object.fromEntries([...r.querySelectorAll("[data-k]")].map((i) =>
      [i.dataset.k, i.type === "checkbox" ? i.checked : i.value.trim()])) })) };
}

/* §6 · the add and edit form. Only the name is required. */
function procedureForm(host, d, proc, preset) {
  const inp = d.inputs || {}, rb = inp.readbacks || {}, copy = d.copy || {},
        opt = d.options || {};
  const p = { ...(proc || {}), ...(preset || {}) };
  const inForce = proc && proc.status === "In force";
  const levels = inp.levels || [];
  const gateNames = (d.gates || []).map((g) => [g.id, g.name]);
  const checks = (name, legend, options, chosen, help) => `<fieldset class="vr-tri">
    <legend>${esc(legend)}</legend>
    ${help ? `<p class="small muted vr-help" style="width:100%">${esc(help)}</p>` : ""}
    ${options.map(([v, l]) => `<label><input type="checkbox" name="${name}" value="${esc(v)}"${
      (chosen || []).includes(v) ? " checked" : ""}> ${esc(l)}</label>`).join("")}</fieldset>`;
  const picked = (name) => [...host.querySelectorAll(`[name="${name}"]:checked`)].map((c) => c.value);
  const suggestions = [...new Set([...(inp.seats || []), ...(inp.stoppers || []),
                                   ...(inp.functions || [])])];

  host.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${proc ? esc(proc.name) : "Write a procedure"}</h2>
    <p class="intro">${esc(copy.only_the_name)}</p>
    ${inForce ? `<p class="vr-tell">${esc(copy.version_rule)}</p>` : ""}
    ${igText("pf-name", "What is it called?", copy.name, { value: p.name || "" })}
    ${igText("pf-steps", "What does it tell somebody to do?", copy.steps, { long: true, value: p.steps || "" })}
    ${igText("pf-where", "Where does it live?", rb.where_it_lives || "", { value: p.where_it_lives || "" })}
    <label class="small"><input type="checkbox" id="pf-here"${p.lives_here ? " checked" : ""}> It lives here, in this field.</label>
    ${copy.nothing_private ? `<p class="small muted">${esc(copy.nothing_private)}</p>` : ""}
    ${igText("pf-unusual", "Anything unusual about how this one runs here? (optional)", "", { long: true, value: p.unusual || "" })}
    <div class="vr-field"><label for="pf-kind">What kind of procedure it is</label>
      <p class="small muted vr-help" id="pf-kind-help">This decides what else the form asks and which gate the procedure attaches to. Pick the closest; nothing here is locked afterward.</p>
      <select id="pf-kind" aria-describedby="pf-kind-help"><option value="">Choose one</option>
        ${opt.kinds.map((k) => `<option${k === p.kind ? " selected" : ""}>${esc(k)}</option>`).join("")}</select>
      <p class="small" id="pf-kind-note"></p></div>
    ${checks("pf-gates", "Which gate does it belong to?", [...gateNames,
      [opt.every_gate, "It applies at every gate"], [opt.no_gate, "It does not belong to a gate"]],
      p.gates || [], "These are names rather than numbers. A procedure that applies everywhere should say so rather than being ticked seven times.")}
    ${levels.length ? checks("pf-levels", "Which level of scrutiny does it apply at?",
      [[opt.every_level, "Every level"], ...levels.map((l) => [l, l])], p.levels || [], rb.levels)
      : `<p class="small muted">Your framework has not set its levels of scrutiny yet, so none are offered.</p>`}
    ${igRadios("pf-covers", "Which records does it cover?", opt.covers, p.covers || "",
      "A procedure can exist before anything points at it. That is a procedure waiting to be used rather than an error.")}
    <div id="pf-pickbox" hidden>${checks("pf-records", "Which ones?",
      (d.projects || []).map((x) => [x.ref, x.name]), p.covered_records || [])}</div>
    <div class="vr-field"><label for="pf-owner">Who owns it — a role</label>
      <p class="small muted vr-help" id="pf-owner-help">${esc(copy.owner)}</p>
      <input id="pf-owner" list="pf-owner-list" aria-describedby="pf-owner-help" value="${esc(p.owner || "")}">
      <datalist id="pf-owner-list">${suggestions.map((s) => `<option value="${esc(s)}">`).join("")}</datalist></div>
    ${rb.adopted ? `<p class="small muted">${esc(rb.adopted)} Putting it in force is a separate step on the register.</p>` : ""}
    ${checks("pf-look", "When should somebody look at this again?",
      [["On a date I set", "On a date I set"], ...(opt.triggers || []).map((t) => [t, t]),
       ["It does not need looking at again", "It does not need looking at again"]],
      p.look_again || opt.triggers || [], rb.triggers)}
    ${igText("pf-lookdate", "The date", rb.review || "", { type: "date", value: p.look_again_date || "" })}
    <div id="pf-blocks"></div>
    <p class="small" id="pf-err" role="alert"></p>
    <p><button type="button" class="btn" id="pf-save">${inForce ? "Save a new version" : proc ? "Save it" : "Add it"}</button>
      <button type="button" class="btn ghost" id="pf-cancel">Cancel</button></p>`;

  const $$ = (s) => host.querySelector(s);
  const coversShown = () => $$("#pf-pickbox").hidden = igPicked(host, "pf-covers") !== "Only the ones I pick";
  host.querySelectorAll('[name="pf-covers"]').forEach((r) => r.onchange = coversShown);
  coversShown();

  // The extra blocks, one per kind.
  let block = {};
  const blocks = $$("#pf-blocks");
  const drawBlock = () => {
    const kind = $$("#pf-kind").value;
    const note = $$("#pf-kind-note");
    note.textContent = kind === "How an update gets tried before it goes live"
      ? "A tool changes under you. The vendor updates what is underneath it, and the tool you approved in one month behaves differently in another. This is the instruction somebody follows when that happens; the version itself is recorded on the project."
      : kind === "How a problem gets reported, and who gets told"
        ? "The route is written here; the reports themselves are recorded on Integrity, which anyone can use with no role at all." : "";
    blocks.innerHTML = ""; block = {};
    if (kind === "The way something gets written down in the first place") {
      blocks.innerHTML = `<fieldset class="vr-tri" style="display:block"><legend>What the route asks for</legend>
        <p class="small muted">${esc(copy.asks_help)}</p><div id="pf-asks"></div></fieldset>
        ${igText("pf-next", "What happens next, in your words", "What the person sees at the end of the walkthrough on Projects. Keep [record id] where the identifier goes.",
          { long: true, value: p.what_happens_next || copy.what_they_are_told })}`;
      const initial = (p.asks && p.asks.length ? p.asks : (d.seed[0] || {}).asks || [
        { question: "Who is asking, and how do we reach you?", type: "short text", required: true, fixed: true }]);
      block.asks = prRows(blocks.querySelector("#pf-asks"), [
        ["question", "The question"], ["type", "Input type", "select", opt.input_types],
        ["required", "Required", "check"], ["help", "Help text"]],
        initial.map((a, i) => ({ ...a, fixed: i === 0 || a.fixed })), "Question");
    } else if (kind === "What has to exist on paper before something passes a gate") {
      const lv = (p.levels || [])[0];
      const paper = lv && (inp.paper || {})[lv];
      blocks.innerHTML = `<fieldset class="vr-tri" style="display:block"><legend>What has to exist here</legend>
        <p class="small muted">${paper ? `You said that before something is approved at ${esc(lv)}, ${esc(paper)} has to exist. Write that out as items, one per line.` : "One item per line."}
          ${esc(copy.consequence)}</p>
        <div id="pf-deploy"></div><div id="pf-items"></div></fieldset>`;
      const initial = (p.items && p.items.length) ? p.items : (paper ? paper.split(/[;\n]/).map((s) => s.trim()).filter(Boolean)
        .map((s) => ({ item: s, consequence: "It should exist; record it as a condition if it does not" })) : []);
      block.items = prRows(blocks.querySelector("#pf-items"), [
        ["item", "The item"], ["confirms", "Who confirms it"],
        ["consequence", "What happens if it is missing", "select", opt.consequences]], initial, "Item");
      const showSix = () => {
        const g = picked("pf-gates");
        const deploy = g.includes("gate.deploy") || g.includes(opt.every_gate);
        blocks.querySelector("#pf-deploy").innerHTML = deploy ? `<h3 class="sub3">${esc(copy.six)}</h3>
          <table class="vr-table"><caption class="vh">The six locked rows at Deploy</caption>
          <thead><tr><th scope="col">The item</th><th scope="col">What happens if it is missing</th></tr></thead>
          <tbody>${(d.locked || []).map((r) => `<tr><th scope="row">${esc(r.says)}</th>
            <td>It has to exist before this passes</td></tr>`).join("")}</tbody></table>
          <p class="small">${esc(copy.under_six)}</p>` : "";
      };
      host.querySelectorAll('[name="pf-gates"]').forEach((c) => c.addEventListener("change", showSix));
      showSix();
    } else if (kind === "The words the public sees when a tool is involved") {
      blocks.innerHTML = `
        ${igText("pf-words", "The exact words", "Paste the words as they appear rather than a description of them. This is the version everyone is supposed to use.", { long: true, value: p.words || "" })}
        ${checks("pf-appear", "Where do these words appear?", [...(inp.places || []).map((x) => [x, x]),
          ["Somewhere else", "Somewhere else"]], p.words_appear || [], inp.places && inp.places.length ? `You said: ${inp.places.join(", ")}.` : "")}
        ${igText("pf-wrote", "Who wrote it — role", rb.wording_roles || "", { value: p.wrote_it || "" })}
        ${igText("pf-approved", "Who approved it — role", "", { value: p.approved_by || "" })}
        ${igText("pf-approvedon", "When", "", { type: "date", value: p.approved_on || "" })}
        ${igRadios("pf-current", "Is this the version the public sees today?", opt.yes_no_unsure, p.is_current || "",
          "This is the one thing here the app cannot check for you.")}`;
    } else if (kind === "How to turn it off") {
      blocks.innerHTML = `
        ${igText("pf-stopper", "Who can do this without waiting for a meeting", (inp.stoppers || []).length
          ? `You named ${inp.stoppers.join(", ")} as able to stop a tool without waiting for a meeting. Whoever that is has to be able to find this instruction at seven in the morning.` : "",
          { value: p.may_stop_it || (inp.stoppers || [])[0] || "" })}
        ${igRadios("pf-offmeans", "What turning it off means here", opt.turning_off, p.turning_off_means || "",
          "These are different acts with different consequences, and the person doing it in a hurry should not have to work out which one they are performing.")}
        ${igText("pf-rollback", "Can the version before this one be put back, and how?", "Where the answer is no, write no; you are then relying on the vendor's own ability to go back, and knowing that in advance is worth more than a blank.", { long: true, value: p.can_roll_back || "" })}
        <div class="vr-field"><label for="pf-fallsback">What the work falls back to while it is off</label>
          <select id="pf-fallsback"><option value="">There is none written</option>
          ${(d.procedures || []).filter((x) => x.kind === "How the work gets done when the tool is off")
            .map((x) => `<option value="${esc(x.ref)}"${x.ref === p.falls_back_to ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div>`;
    } else if (kind === "How an update gets tried before it goes live") {
      blocks.innerHTML = `
        ${igRadios("pf-somewhere", "Is there somewhere to try an update before it goes live?", opt.yes_no_unsure,
          p.somewhere_to_try || "", rb.staging_term || "Somewhere separate from the live system, so that the first people to meet a change are not the people doing the work.")}
        ${igText("pf-tries", "Who tries it, and what do they check?", "The people who would notice. The same handful of cases every time is worth more than a new list each release.", { long: true, value: p.who_tries_it || "" })}
        ${igText("pf-howlong", "How long does an update sit there before it goes live?", "Your answer rather than ours. Write no set period if there is none.", { value: p.how_long || "" })}
        ${igText("pf-nowhere", "What happens where there is nowhere to try it", "Who is told it is coming, what gets watched in the first days, and how you go back.", { long: true, value: p.when_nowhere_to_try || "" })}
        ${igText("pf-recorder", "Who records that the version went live, and which version it replaced — role", "The version record itself lives on the project.", { value: p.records_the_version || "" })}
        <p class="small muted">This does not stop an update. The vendor releases when the vendor releases. It decides who tries one, what they look at, and what happens when nobody could.</p>`;
    } else if (kind === "How the work gets done when the tool is off") {
      blocks.innerHTML = `<p class="small muted">${esc(rb.fallback_tried || "")}</p>`;
    }
  };
  $$("#pf-kind").onchange = drawBlock;
  drawBlock();

  $$("#pf-cancel").onclick = () => { host.remove(); $("#prNew").focus(); };
  $$("#pf-save").onclick = async () => {
    const err = $$("#pf-err"); err.textContent = "";
    const name = igVal(host, "pf-name");
    if (!name) { err.textContent = "Give it a name."; $$("#pf-name").focus(); return; }
    const body = {
      ref: proc ? proc.ref : "", name, kind: $$("#pf-kind").value,
      steps: igVal(host, "pf-steps"), where_it_lives: igVal(host, "pf-where"),
      lives_here: $$("#pf-here").checked, unusual: igVal(host, "pf-unusual"),
      gates: picked("pf-gates"), levels: picked("pf-levels"),
      covers: igPicked(host, "pf-covers"), covered_records: picked("pf-records"),
      owner: igVal(host, "pf-owner"), look_again: picked("pf-look"),
      look_again_date: igVal(host, "pf-lookdate"),
    };
    if (block.asks) { body.asks = block.asks.read(); body.what_happens_next = igVal(host, "pf-next"); }
    if (block.items) body.items = block.items.read().filter((r) => r.item);
    if ($$("#pf-words")) Object.assign(body, { words: igVal(host, "pf-words"),
      words_appear: picked("pf-appear"), wrote_it: igVal(host, "pf-wrote"),
      approved_by: igVal(host, "pf-approved"), approved_on: igVal(host, "pf-approvedon"),
      is_current: igPicked(host, "pf-current") });
    if ($$("#pf-stopper")) Object.assign(body, { may_stop_it: igVal(host, "pf-stopper"),
      turning_off_means: igPicked(host, "pf-offmeans"), can_roll_back: igVal(host, "pf-rollback"),
      falls_back_to: igVal(host, "pf-fallsback") });
    if ($$("#pf-tries")) Object.assign(body, { somewhere_to_try: igPicked(host, "pf-somewhere"),
      who_tries_it: igVal(host, "pf-tries"), how_long: igVal(host, "pf-howlong"),
      when_nowhere_to_try: igVal(host, "pf-nowhere"), records_the_version: igVal(host, "pf-recorder") });
    const out = await post("/api/procedures", body);
    if (!out || !out.ok) { err.textContent = (out && out.error) || "That did not save."; return; }
    PR.said = out.new_version ? "Saved as a new version. The old one stays on the list."
      : `Written down as ${out.procedure.ref}.`;
    go("process");
  };
}

VIEWS.council = async () => {
  const d = await api("/api/council");
  const who = d.decider || {};
  paintDecider(who);
  const root = el("div");

  // Nobody has answered yet, so there is nothing to show a log of. Ask.
  if (!who.decided) { await renderWhoDecides(root, who); return; }

  /* Derived is not answered. The app read a signed charter and 218 mentions of a
     Council and proposed one — good evidence, and still a guess about what this
     agency intends. Same distinction the framework already draws between a
     document being loaded and a body having adopted it. */
  if (!who.confirmed) {
    const ask = el("div", "locked");
    ask.innerHTML = `<b>Proposed from your documents, not yet confirmed.</b>
      ${esc(who.evidence || "")}
      <div class="small" style="margin-top:8px">Until someone confirms it, this
        room is running on a guess.</div>`;
    const go2 = el("button", "btn", "Answer it properly");
    go2.onclick = async () => {
      const box = el("div");
      await renderWhoDecides(box, who);
    };
    ask.appendChild(go2);
    root.appendChild(ask);
  }

  const holder = who.is_group ? "members" : "the named decision-maker";
  if (!d.is_member)
    root.appendChild(el("div", "locked",
      `<b>${esc(who.rail_label)} is a gated room.</b>
       The decision log is readable for transparency, but only ${esc(holder)}
       amend the Framework, decide gates, or move the mode.`));

  const head = el("div", "panel");
  head.innerHTML = `<p class="intro">${esc(who.sentence)}</p>
    <p class="intro">Append-only. Mode <b>${esc(d.mode)}</b> ·
    <span class="mono">parameter set ${esc(d.parameter_set_hash)}</span></p>`;
  if (d.is_member && d.mode === "configuration") {
    const b = el("button", "btn", "Adopt the tuned parameter set → activate guardrails");
    b.onclick = async () => {
      const r = await post("/api/council/adopt", {
        members_present: presentMembers(d),
        summary: "Tuned parameter set adopted; change guardrails activated." });
      if (!r.adopted) return toast(r.reason, true);
      toast(`Operating Mode. Every governed change now routes through ${whoDecides()}.`);
      await refreshState(); go("council");
    };
    head.appendChild(b);
  }
  root.appendChild(head);

  const log = el("div", "panel");
  log.innerHTML = `<h2 class="sub3" style="margin-top:0">Decision log</h2>` +
    (d.decisions.length ? d.decisions.map((x) =>
      `<div class="entry"><time>${esc(whenLocal(x.at))}</time>
       <span class="k dec">${esc(vlabel("council_decision", (x.tier || "b").toLowerCase()))}</span>
       <p>${esc(x.summary)}${x.status === "awaiting_decision"
         ? ' <span class="pill neutral">awaiting</span>' : ""}
       <br><span class="mono">${esc(x.decision_id)}</span></p></div>`).join("")
      : `<p class="muted">No decisions recorded.</p>`);
  root.appendChild(log);

  const pending = d.decisions.filter((x) => x.status === "awaiting_decision");
  if (d.is_member && pending.length) {
    const p = el("div", "panel");
    p.innerHTML = `<h2 class="sub3" style="margin-top:0">Awaiting a decision</h2>`;
    pending.forEach((x) => {
      const w = el("div", "req");
      w.innerHTML = `<span class="t"><b>${esc(x.decision_id)}</b> — ${esc(x.summary)}</span>`;
      const ok = el("button", "btn", "Approve");
      ok.onclick = async () => {
        const r = await post("/api/council/decide", { decision_id: x.decision_id,
          outcome: "approved",
          members_present: presentMembers(d),
          rationale: who.is_group ? "Convened session — consensus."
                                  : `Decided by ${who.noun}.` });
        toast(r.decided ? "Approved." : r.reason, !r.decided);
        await refreshState(); go("council");
      };
      w.appendChild(ok); p.appendChild(w);
    });
    root.appendChild(p);
  }
  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "The second adoption", body: `The appendices were adopted as templates. Adopting the tuned parameter set is a distinct act — it is what activates the change guardrails, and it is ${who.possessive} to make.`, cite: "Appendix N — Adoption; SCDES AI Governance Framework §6" },
    { title: "Why this room is called this", body: who.is_group
        ? `Your framework named a standing body — ${who.noun} — with a quorum of ${who.quorum}. That answer is what created this room and the three decision levels.`
        : `Your framework named one person: ${who.noun}. There is no quorum and no session to convene, so there is one decision level and this room is a record of calls made, not a meeting.`,
      cite: "Framework — who decides" },
  ]);
};

/* Which members to record as present. A single decider is the only person there,
   and sending a seeded roster of council seats would put three names that do not
   exist into an audit entry. */
function presentMembers(d) {
  const who = d.decider || {};
  if (!who.is_group) return [(S.state && S.state.actor.id) || "council.cto"];
  const roster = (d.members && d.members.members) || [];
  return roster.length ? roster.slice(0, Math.max(1, who.quorum || 3)).map((m) => m.id)
                       : ["council.cto"];
}

/* The question itself. This is the only place it is asked, and it is asked in
   the room whose existence depends on the answer. */
async function renderWhoDecides(root, who) {
  const q = await api("/api/decider");
  const head = el("div", "panel");
  head.innerHTML = `<h2 class="sub3" style="margin-top:0">${esc(q.question)}</h2>
    <p class="intro">${esc(q.why)}</p>
    ${q.evidence ? `<div class="locked" style="margin-top:10px">
      <b>Suggested from your documents.</b> ${esc(q.evidence)}</div>` : ""}
    <p class="small muted" style="margin-top:10px">Answering changes:
      ${q.affects.map((a) => esc(a)).join(" · ")}</p>`;
  root.appendChild(head);

  if (!q.can_answer) {
    root.appendChild(el("div", "locked",
      `<b>This is not yours to answer.</b> Naming the decision-maker is part of
       writing the framework, which the Office of Technology holds. Switch
       capacity in the header if that is you.`));
    $("#view").innerHTML = ""; $("#view").appendChild(root);
    return;
  }

  const form = el("div", "panel");
  form.innerHTML = `<h2 class="sub3" style="margin-top:0">Choose one</h2>` +
    q.shapes.map((s) => `
      <label class="step-row" style="cursor:pointer">
        <input type="radio" name="wdShape" value="${esc(s.key)}"
               ${s.key === (q.shape === "individual" ? "individual" : "group")
                 ? "checked" : ""} style="margin-top:4px">
        <div class="step-main">
          <div class="step-name">${esc(s.label)}</div>
          <div class="step-why">${esc(s.means)}</div>
        </div>
      </label>`).join("") + `
    <div id="wdFields" style="margin-top:12px"></div>
    <div class="row" style="margin-top:12px">
      <button class="btn" id="wdSave" type="button">Record this answer</button>
    </div>
    <p class="small muted" style="margin-top:8px">Audited, and attributed to you
      by name and title. Changing it afterward is a framework amendment, not a
      setting — so it stops being yours alone to change.</p>`;
  root.appendChild(form);

  const fields = form.querySelector("#wdFields");
  /* The noun field shows a proposal only where the agency's own documents
     evidenced one. It used to fall back to "Council" as the input's *value*,
     not merely its placeholder, so an agency with nothing proposed arrived here
     with the word already filled in and could save it without typing it — the
     client's point that a Council is one agency's answer, arriving as a
     pre-filled default. */
  const paintFields = () => {
    const shape = form.querySelector('input[name="wdShape"]:checked').value;
    fields.innerHTML = shape === "group"
      ? `<label class="small">What is it called?</label>
         <div class="row">
           <input id="wdNoun" list="wdNouns" placeholder="Council, board, committee…"
                  value="${esc(q.noun || "")}"
                  style="flex:1;min-width:180px">
           <datalist id="wdNouns">${q.group_nouns.map((n) =>
             `<option value="${esc(n)}">`).join("")}</datalist>
           <label class="small">Quorum</label>
           <input id="wdQuorum" type="number" min="2" max="25"
                  value="${Math.max(2, Number(q.quorum) || 3)}"
                  style="width:80px">
         </div>
         <p class="small muted">Quorum is how many must be present for a
           convened session — the most serious decision level.</p>`
      : `<label class="small">Which role holds the decision?</label>
         <div class="row">
           <input id="wdNoun" list="wdRoles" placeholder="Chief Technology Officer"
                  value="${esc(q.shape === "individual" ? (q.noun || "") : "")}"
                  style="flex:1;min-width:220px">
           <datalist id="wdRoles">${q.individual_roles.map((n) =>
             `<option value="${esc(n)}">`).join("")}</datalist>
         </div>
         <label class="small" style="margin-top:8px">Who do they report out to?
           <span class="muted">(optional)</span></label>
         <input id="wdReport" placeholder="the agency director, monthly"
                style="width:100%;max-width:420px">
         <p class="small muted">No quorum is asked for, and no session is held.
           One decision level, and a record of every call.</p>`;
  };
  form.querySelectorAll('input[name="wdShape"]').forEach(
    (r) => r.addEventListener("change", paintFields));
  paintFields();

  $("#view").innerHTML = ""; $("#view").appendChild(root);

  $("#wdSave").onclick = async () => {
    const shape = form.querySelector('input[name="wdShape"]:checked').value;
    const noun = ($("#wdNoun").value || "").trim();
    const r = await post("/api/decider/answer", {
      shape, noun,
      quorum: $("#wdQuorum") ? Number($("#wdQuorum").value) : 3,
      report_out: $("#wdReport") ? $("#wdReport").value : "",
    });
    if (!r.ok) return toast(r.error, true);
    toast(shape === "group" ? `${noun} recorded as your deciding body.`
                            : `${noun} recorded as your decision-maker.`);
    await refreshState();
    go("council");
  };

  reason([
    { title: "Why the app asks instead of assuming",
      body: "The reference regime has a council, so an earlier build shipped one for everybody. An agency that never stood one up would have been told its approvals route to a body it does not have.",
      cite: "Framework — who decides" },
    { title: "What it does not do",
      body: "It does not create the body or appoint anyone. Both happen outside the software; this records which arrangement your framework chose, so every screen after it is worded correctly.",
      cite: "Framework §1 (Purpose and Authority)" },
  ]);
}

/* The bug queue.

   The client's note: since this will be the only ticketing system, it has to be
   a real workflow tool. Phase 1 is the honest subset of that — queue, detail,
   status, reply, search — and the pieces that are missing are missing on
   purpose rather than forgotten: assignment needs a roster of real people,
   which this build does not have, and grouping is Phase 2.

   What is here that is easy to leave out: every ticket shows how many other
   reports share its fingerprint. One bad deploy produces forty reports of one
   fault, and a queue that does not say so reads as forty problems. */
VIEWS.bugs = async () => {
  const d = await api("/api/bugs" + (S.bugFilter ? "?status=" + S.bugFilter : ""));
  const root = el("div");

  /* Not an admin. The rail heading is not drawn for them, so getting here means
     the URL was typed — and the honest answer is to say whose screen this is
     rather than render a thinner version of it. Their own reports are still
     theirs: the server returned them, and the bell is where they live. */
  if (!d.team) {
    const mine = el("div", "panel");
    mine.innerHTML = `<h2 class="sub3" style="margin-top:0">Your reports</h2>
      <p class="intro">${esc(d.note || "")}</p>
      ${(d.tickets || []).length ? d.tickets.map((b) => `
        <div class="entry"><time>${esc(whenLocal(b.at))}</time>
          <span class="k ${b.status === "fixed" ? "allow" : "deny"}">${
            esc(b.status)}</span>
          <p><b>${esc(b.id)}</b> — ${esc(b.happened)}
          ${(b.replies || []).length ? `<br><span class="small muted">${
            esc(b.replies[b.replies.length - 1].message)}</span>` : ""}</p>
        </div>`).join("")
        : `<p class="muted">You have not reported anything yet.</p>`}`;
    root.appendChild(mine);
    $("#view").innerHTML = ""; $("#view").appendChild(root);
    return;
  }

  const head = el("div", "panel");
  head.innerHTML = `
    <div class="spread">
      <div>
        <h2 class="sub3" style="margin-top:0">Reported bugs</h2>
        <p class="intro" style="margin:0">${d.total} in total ·
          ${d.summary.open} still open</p>
      </div>
      <div class="bug-filters">
        ${["", "new", "open", "fixed", "wont_fix", "closed"].map((s) => `
          <button class="btn ghost${S.bugFilter === s ? " on" : ""}"
            data-filter="${esc(s)}" type="button">${
            esc(s ? s.replace("_", " ") : "all")}${
            s && d.counts[s] ? ` ${d.counts[s]}` : ""}</button>`).join("")}
      </div>
    </div>
    <p class="small muted" style="margin-top:10px">${esc(d.summary.captures)}
      ${esc(d.summary.keeps)}</p>`;
  root.appendChild(head);

  (d.tickets || []).forEach((b) => {
    const card = el("div", "panel bug-ticket");
    card.innerHTML = `
      <div class="spread">
        <div>
          <span class="bug-id">${esc(b.id)}</span>
          <span class="pill ${b.status === "new" ? "warn"
            : b.status === "fixed" ? "ok" : "neutral"}">${esc(b.status)}</span>
          ${b.duplicates > 1 ? `<span class="pill info">${b.duplicates}
            reports of this</span>` : ""}
          ${b.reopened ? `<span class="pill bad">reopened</span>` : ""}
        </div>
        <span class="small muted">${esc(whenLocal(b.at))}</span>
      </div>
      <p class="bug-said"><b>Happened.</b> ${esc(b.happened)}</p>
      ${b.expected ? `<p class="bug-said"><b>Expected.</b> ${
        esc(b.expected)}</p>` : ""}
      <div class="bug-context">
        <span><b>Screen</b> ${esc(b.view || "—")}</span>
        <span><b>Agency</b> ${esc(b.agency || "—")}</span>
        <span><b>Build</b> ${esc(b.version || "—")}</span>
        <span><b>Window</b> ${esc(b.screen || "—")}</span>
        <span><b>By</b> ${esc(b.name || b.reporter || "anonymous")}</span>
      </div>
      ${(b.events || []).length ? `
        <details class="bug-attached">
          <summary>${b.events.length} captured events</summary>
          <ul class="bug-events">${b.events.slice().reverse().map((e) => `
            <li class="ev-${esc(e.kind)}"><b>${esc(e.kind)}</b>
              ${e.status ? `<i>${esc(e.method)} ${esc(e.status)}</i>` : ""}
              ${esc(e.text)}</li>`).join("")}</ul>
        </details>`
        : `<p class="small muted">${b.events_note
            ? esc(b.events_note) : "No technical capture attached."}</p>`}
      ${(b.replies || []).map((r) => `
        <div class="bug-reply${r.team ? " team" : ""}">
          <b>${esc(r.by)}</b> <span class="small muted">${
            esc(whenLocal(r.at))} · set to ${esc(r.status)}</span>
          <p>${esc(r.message)}</p>
        </div>`).join("")}
      <div class="row" style="margin-top:12px">
        <input type="text" data-msg="${esc(b.id)}" placeholder="Reply to the reporter"
               style="flex:1;min-width:200px">
        <select data-status="${esc(b.id)}">
          ${Object.keys(d.statuses).map((s) => `
            <option value="${esc(s)}"${s === b.status ? " selected" : ""}>${
            esc(s.replace("_", " "))}</option>`).join("")}
        </select>
        <button class="btn" data-reply="${esc(b.id)}" type="button">Send</button>
      </div>`;
    root.appendChild(card);
  });

  if (!(d.tickets || []).length) {
    root.appendChild(el("div", "panel",
      `<p class="muted">Nothing here.</p>`));
  }

  $("#view").innerHTML = ""; $("#view").appendChild(root);

  document.querySelectorAll("[data-filter]").forEach((b) => {
    b.onclick = () => { S.bugFilter = b.dataset.filter; go("bugs"); };
  });
  document.querySelectorAll("[data-reply]").forEach((b) => {
    b.onclick = async () => {
      const id = b.dataset.reply;
      const msg = document.querySelector(`[data-msg="${id}"]`).value.trim();
      const status = document.querySelector(`[data-status="${id}"]`).value;
      const r = await post("/api/bugs/respond", { id, message: msg, status });
      if (!r.ok) return toast(r.error, true);
      toast(`${id} set to ${status}.`);
      go("bugs");
    };
  });

  reason([
    { title: "Why the evidence is already attached",
      body: "Most faults cannot be reproduced on demand. The widget holds the last minute of console errors and network calls from the moment the page loads, so a report carries what actually happened rather than what someone remembered.",
      cite: "Bug Report Panel — Phase 1" },
    { title: "What is never captured",
      body: "No page contents, no keystrokes, no screen recording. Network entries record method, address and status code — never the body. Email addresses and codes are removed before anything is stored, in the browser and again on arrival.",
      cite: "Privacy in v1, not added later" },
  ]);
};

/* Who is using GAIUS, from where, for how long, and how far they have got.

   The client's ask: "which state, how many hours he logged in, track every
   single user and what they have worked on and their progress", for whoever
   signs in on an @iiac.ai address.

   Admin only, on the same terms as the bug queue and for the same reason:
   this reads across every agency, which is the line nothing else in the
   application crosses. The server re-checks the proven address; the rail
   heading being hidden is only so that nobody who cannot use it wonders what
   it is.

   What this screen has to be careful about is the hours. There was no record
   of signing in when the page was asked for — five weeks of audit log and not
   one session-shaped event — so the figure is inferred from activity for the
   history and measured from now on, and the screen says which it is looking
   at rather than presenting one number as though it were the other. A usage
   page nobody can trust the numbers on is worse than no usage page. */
/* Subscriptions — the GAIUS team's half of the invoice route.
 *
 * An organization could ask for an invoice on its Subscription page, and the
 * server could record one as paid, but nothing drew the list anybody at IIA
 * would settle from. So no organization could become subscribed through the
 * application at all. This is that list.
 *
 * Marking an order paid is the most sensitive thing in billing — there is no
 * payment provider behind an invoice to confirm it, so a person does. The
 * server restricts it to the three GAIUS addresses and refuses it without a
 * payment reference; this screen asks for the reference in words, and says
 * plainly what the action does before anybody takes it. */
VIEWS.subscriptions = async () => {
  const d = await api("/api/billing/admin");
  const root = el("div");

  if (!d.ok) {
    const no = el("div", "panel");
    no.innerHTML = `<h2 class="sub3" style="margin-top:0">Subscriptions</h2>
      <p class="intro">${esc(d.error || "This screen is for the GAIUS team.")}</p>`;
    root.appendChild(no);
    $("#view").innerHTML = ""; $("#view").appendChild(root);
    return;
  }

  const money = (o) => o.amount_set
    ? (o.amount || 0).toLocaleString(undefined, { style: "currency",
        currency: o.currency || "USD", maximumFractionDigits: 0 })
    : "Quoted";

  const head = el("div", "panel");
  head.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Subscriptions</h2>
    <p class="intro" style="margin:0">Every organization's orders on this
      installation. ${d.pending} waiting on payment.</p>
    ${d.override ? `<p class="bl-off" style="margin-top:12px"><b>The paid
      modules are forced open on this installation</b> by a server setting, so
      every organization can already open them whether or not it has paid.
      Settling an order here still records a real subscription, and that is
      what an organization will see on its own Subscription page.</p>` : ""}`;
  root.appendChild(head);

  const pending = d.orders.filter((o) => o.state === "pending");
  const wait = el("div", "panel");
  wait.innerHTML = `<h2 class="sub3" style="margin-top:0">Waiting on payment</h2>` +
    (pending.length ? `
      <p class="small muted">Mark an order paid once the money has actually
        arrived. The organization's subscription starts from today, and the
        payment reference you enter goes on the record so it can be matched
        against a bank statement.</p>
      <table><thead><tr><th>Organization</th><th>Raised</th><th>By</th>
        <th>Route</th><th class="num">Amount</th><th>Payment reference</th>
        <th></th></tr></thead><tbody>` +
      pending.map((o) => `<tr>
        <td><b>${esc(o.agency_label)}</b><br><span class="mono">${esc(o.id)}</span></td>
        <td class="small">${esc(niceDate(o.raised_at))}</td>
        <td class="small">${esc(o.raised_by || "")}</td>
        <td class="small">${esc(o.route_label || o.route)}</td>
        <td class="num">${esc(money(o))}</td>
        <td><label class="small" for="ref-${esc(o.id)}" style="display:block">
              Check number, ACH trace or remittance</label>
            <input id="ref-${esc(o.id)}" type="text" style="width:100%"></td>
        <td><button class="btn" type="button" data-settle="${esc(o.id)}">Mark paid</button></td>
      </tr>`).join("") + `</tbody></table>`
    : `<p class="intro">Nothing is waiting on payment.</p>`);
  root.appendChild(wait);

  const ents = el("div", "panel");
  ents.innerHTML = `<h2 class="sub3" style="margin-top:0">Subscriptions on record</h2>` +
    (d.entitlements.length ? `<table><thead><tr><th>Organization</th>
      <th>State</th><th>Since</th><th>Until</th><th>Order</th></tr></thead><tbody>` +
      d.entitlements.map((e) => `<tr><td><b>${esc(e.agency_label)}</b></td>
        <td>${esc(e.state)}</td><td class="small">${esc(e.since || "")}</td>
        <td class="small">${esc(e.until || "")}</td>
        <td class="mono">${esc(e.order || "")}</td></tr>`).join("") +
      `</tbody></table>`
    : `<p class="intro">No organization has a subscription yet.</p>`);
  root.appendChild(ents);

  if ((d.findings || []).length) {
    const off = el("div", "panel");
    off.innerHTML = `<h2 class="sub3" style="margin-top:0">What does not add up</h2>
      <ul class="small">${d.findings.map((f) => `<li><b>${esc(f.agency)}</b>
        ${esc(f.order || "")} — ${esc(f.says)}</li>`).join("")}</ul>`;
    root.appendChild(off);
  }

  const done = el("div", "panel");
  done.innerHTML = `<h2 class="sub3" style="margin-top:0">Everything else</h2>` +
    (d.orders.filter((o) => o.state !== "pending").length
      ? `<table><thead><tr><th>Organization</th><th>State</th><th>Raised</th>
         <th>Reference</th></tr></thead><tbody>` +
        d.orders.filter((o) => o.state !== "pending").map((o) => `<tr>
          <td>${esc(o.agency_label)}</td><td>${esc(o.state)}</td>
          <td class="small">${esc(niceDate(o.raised_at))}</td>
          <td class="mono">${esc(o.reference || "")}</td></tr>`).join("") +
        `</tbody></table>`
      : `<p class="intro">No settled, refunded or expired orders yet.</p>`);
  root.appendChild(done);

  $("#view").innerHTML = ""; $("#view").appendChild(root);

  root.querySelectorAll("[data-settle]").forEach((b) => {
    b.onclick = async () => {
      const id = b.dataset.settle;
      const ref = ($("#ref-" + CSS.escape(id)) || {}).value || "";
      if (!ref.trim()) {
        toast("A payment reference is required — a check number, an ACH "
              + "trace, or the remittance advice.", true);
        return;
      }
      b.disabled = true;
      const r = await post("/api/billing/settle", { order: id, reference: ref });
      b.disabled = false;
      if (r.ok) { toast("Recorded as paid. The subscription is active."); go("subscriptions"); }
      else toast(r.error || "Could not record the payment.", true);
    };
  });

  reason([
    { title: "Why this is an admin screen", body: "An invoice has no payment provider behind it to confirm anything, so a person confirms it. That is the most sensitive action in billing, and it is restricted to the three GAIUS addresses on the server, not only on this screen.", cite: "app/billing.py — settle_invoice" },
    { title: "What marking paid does", body: "It starts the organization's subscription from today for the plan's term, records the payment reference and your name against the order, and writes an audit entry. The organization sees it on its own Subscription page.", cite: "app/billing.py — mark, _grant" },
  ]);
};

/* Organizations — the GAIUS team appoints every organization's admins.

   brett@, lokesh@ and dev@iiac.ai are the permanent owners of every state's
   agencies. A new registration has no admin until one of them appoints one
   here; that admin then adds people and makes other admins, in their own
   organization only. Sign-ups that were sent a code and never finished are
   listed here too, and can be cleared.

   People only. The server sends names, titles, addresses and roles, and
   nothing from any organization's framework — this screen could not show an
   answer if it tried. Every change is checked against the proven address on
   the server and written to the audit log. */
VIEWS.organizations = async () => {
  const first = await api("/api/admin/organizations");
  const root = el("div");
  $("#view").innerHTML = ""; $("#view").appendChild(root);

  if (!first.ok) {
    root.innerHTML = `<div class="panel"><h2 class="sub3" style="margin-top:0">Organizations</h2>
      <p class="intro">${esc(first.error || "This screen is for the GAIUS team.")}</p></div>`;
    return;
  }

  let showTests = !!S.orgsShowTests;
  let filter = "";
  let statesList = null;

  const person = (p) => `<b>${esc(p.name || p.email)}</b>${p.title ? `, ${esc(p.title)}` : ""}
    <span class="small muted">${esc(p.email)}</span>`;

  const peopleTable = (o) => `<div class="table-scroll" role="region" tabindex="0"
      aria-label="People in ${esc(o.organization)}">
    <table class="vr-table"><thead><tr><th scope="col">Name</th><th scope="col">Title</th>
      <th scope="col">Work email</th><th scope="col">Role</th>
      <th scope="col"><span class="vh">Actions</span></th></tr></thead><tbody>${
      o.people.map((p) => `<tr><th scope="row">${esc(p.name || "—")}</th>
        <td>${esc(p.title)}</td><td class="small">${esc(p.email)}</td>
        <td>${p.role === "admin" ? "Admin" : "Member"}</td>
        <td><button type="button" class="btn ghost" data-org="${esc(o.agency)}"
              data-orgname="${esc(o.organization)}" data-email="${esc(p.email)}"
              data-name="${esc(p.name || p.email)}" data-setrole="${p.role === "admin" ? "member" : "admin"}"
              aria-label="Make ${esc(p.name || p.email)} ${p.role === "admin" ? "a member" : "an admin"} of ${esc(o.organization)}">${
              p.role === "admin" ? "Make member" : "Make admin"}</button>
            <button type="button" class="btn ghost" data-org="${esc(o.agency)}"
              data-orgname="${esc(o.organization)}" data-email="${esc(p.email)}"
              data-name="${esc(p.name || p.email)}" data-drop="1"
              aria-label="Remove ${esc(p.name || p.email)} from ${esc(o.organization)}">Remove</button>
            ${o.status === "active" ? `<button type="button" class="btn ghost" data-viewas="${esc(p.email)}"
              data-name="${esc(p.name || p.email)}" data-orgname="${esc(o.organization)}"
              aria-label="View as ${esc(p.name || p.email)}, view only">View as</button>` : ""}</td>
      </tr>`).join("") || `<tr><td colspan="5" class="small muted">Nobody is on it.</td></tr>`
    }</tbody></table></div>`;

  const render = (d, said, focusSel) => {
    const orgs = d.organizations || [];
    const waiting = orgs.filter((o) => o.needs_admin && (showTests || !o.test));
    const q = filter.trim().toLowerCase();
    const shown = orgs.filter((o) => (showTests || !o.test) && (!q
      || o.organization.toLowerCase().includes(q) || o.agency.includes(q)
      || o.people.some((p) => (p.name + " " + p.email).toLowerCase().includes(q))));
    const pending = d.pending || [];
    const status = (p) => p.status === "pending_approval" ? "Waiting on a reviewer"
      : p.signin ? (p.code_expired ? "Signing in — code expired" : "Signing in — code sent")
      : (p.code_expired ? "Registering — code expired" : "Registering — code sent");

    root.innerHTML = `
      <div class="panel">
        <h2 class="sub3" style="margin-top:0">Organizations</h2>
        <p class="intro" style="margin:0">The GAIUS team appoints every organization's admins,
          in every state. An admin then adds people and makes other admins in their own
          organization only. You see people here, never an organization's framework.</p>
        <p class="small" id="orgSaid" aria-live="polite">${esc(said || "")}</p>
        <label class="small"><input type="checkbox" id="orgTests"${showTests ? " checked" : ""}>
          Show IIA's test organizations</label>
      </div>

      <div class="panel" aria-labelledby="orgWaitH">
        <h2 class="sub3" id="orgWaitH" style="margin-top:0">Waiting for an admin (${waiting.length})</h2>
        ${waiting.length ? `<p class="small muted">Until you appoint an admin, nobody can add people
            to these. Usually it is the person who registered it.</p>` +
          waiting.map((o) => `<h3 class="sub4">${esc(o.organization)}
              <span class="small muted">${esc(o.state)} · registered ${esc(niceDate(o.created_at))}</span></h3>
            ${peopleTable(o)}`).join("")
          : `<p class="intro">Every organization has an admin.</p>`}
      </div>

      <div class="panel" aria-labelledby="orgPendH">
        <h2 class="sub3" id="orgPendH" style="margin-top:0">Unfinished sign-ups (${pending.length})</h2>
        ${pending.length ? `<p class="small muted">Sent a code and never entered it. Removing one
            clears the sign-up; the person can start again at any time. Each removal is kept on
            the record.</p>
          <div class="table-scroll" role="region" tabindex="0" aria-labelledby="orgPendH">
          <table class="vr-table"><thead><tr><th scope="col">Name</th><th scope="col">Work email</th>
            <th scope="col">Organization</th><th scope="col">Started</th><th scope="col">Where it stopped</th>
            <th scope="col"><span class="vh">Actions</span></th></tr></thead><tbody>${
            pending.map((p) => `<tr><th scope="row">${esc(p.name || "—")}</th>
              <td class="small">${esc(p.email)}</td><td>${esc(p.organization)}</td>
              <td class="small">${esc(niceDate(p.started))}</td><td class="small">${esc(status(p))}</td>
              <td>${p.status === "pending_approval" ? "" : `<button type="button" class="btn ghost"
                data-pending="${esc(p.email)}" data-name="${esc(p.name || p.email)}"
                aria-label="Remove the sign-up for ${esc(p.name || p.email)}">Remove</button>`}</td></tr>`).join("")
          }</tbody></table></div>`
          : `<p class="intro">No unfinished sign-ups.</p>`}
      </div>

      ${(d.awaiting_signed || []).length ? `<div class="panel" aria-labelledby="orgSignedH">
        <h2 class="sub3" id="orgSignedH" style="margin-top:0">Waiting for a signed agreement (${d.awaiting_signed.length})</h2>
        <p class="small muted">Their counsel asked for the signed form of the Terms of Use, and it was
          emailed to them and to brett@iiac.ai. When the executed copy comes back, mark it received —
          they can then get their verification code and continue registering.</p>
        <div class="table-scroll" role="region" tabindex="0" aria-labelledby="orgSignedH">
        <table class="vr-table"><thead><tr><th scope="col">Name</th><th scope="col">Work email</th>
          <th scope="col">Governmental unit</th><th scope="col">Requested</th>
          <th scope="col"><span class="vh">Actions</span></th></tr></thead><tbody>${
          d.awaiting_signed.map((p) => `<tr><th scope="row">${esc(p.name || "—")}${p.title ? `, ${esc(p.title)}` : ""}</th>
            <td class="small">${esc(p.email)}</td><td>${esc(p.unit)}</td>
            <td class="small">${esc(niceDate(p.requested_at))}</td>
            <td><button type="button" class="btn ghost" data-signed="${esc(p.email)}" data-name="${esc(p.name || p.email)}"
              data-unit="${esc(p.unit)}" aria-label="Mark the signed agreement received for ${esc(p.name || p.email)}">Mark signed form received</button></td></tr>`).join("")
        }</tbody></table></div></div>` : ""}

      <div class="panel" aria-labelledby="orgAppH">
        <h2 class="sub3" id="orgAppH" style="margin-top:0">Appoint an admin</h2>
        <p class="small muted">For any agency in any state, registered or not. If nobody has
          registered it yet, this opens it with this person as its admin. Their address must
          fit the agency's email rule, and they prove it with a code when they sign in.
          Nothing is sent to them from here.</p>
        <div class="ap-row">
          <div class="vr-field"><label for="appState">State</label>
            <select id="appState"><option value="">Choose a state…</option></select></div>
          <div class="vr-field"><label for="appAgency">Agency</label>
            <select id="appAgency" disabled><option value="">Choose a state first</option></select></div>
        </div>
        <div class="ap-row">
          <div class="vr-field"><label for="appName">Full name</label>
            <input id="appName" type="text" autocomplete="off" spellcheck="false"></div>
          <div class="vr-field"><label for="appTitle">Job title</label>
            <input id="appTitle" type="text" autocomplete="off"></div>
          <div class="vr-field"><label for="appEmail">Work email</label>
            <input id="appEmail" type="email" autocomplete="off" spellcheck="false"></div>
          <button type="button" class="btn" id="appGo">Make admin</button>
        </div>
        <p class="signin-error" id="appErr" role="alert" hidden></p>
      </div>

      <div class="panel" aria-labelledby="orgAllH">
        <h2 class="sub3" id="orgAllH" style="margin-top:0">All organizations (${shown.length})</h2>
        <div class="vr-field" style="max-width:420px"><label for="orgFind">Find an organization or person</label>
          <input id="orgFind" type="search" autocomplete="off" value="${esc(filter)}"></div>
        ${shown.map((o) => {
          const admins = o.people.filter((p) => p.role === "admin");
          return `<details class="org-row">
            <summary><b>${esc(o.organization)}</b> <span class="small muted">${esc(o.state)} ·
              ${o.people.length} ${o.people.length === 1 ? "person" : "people"} ·
              ${admins.length ? `admin: ${esc(admins.map((p) => p.name || p.email).join(", "))}`
                : `<b>no admin</b>`}${o.test ? " · test" : ""}${o.status !== "active" ? ` · ${esc(o.status)}` : ""}</span></summary>
            ${peopleTable(o)}</details>`;
        }).join("") || `<p class="intro">Nothing matches that.</p>`}
      </div>`;

    wire(d);
    const target = focusSel && root.querySelector(focusSel);
    if (target) { if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1"); target.focus(); }
  };

  const act = async (url, body, focusSel) => {
    const r = await post(url, body);
    if (!r || !r.ok) { toast((r && r.error) || "That did not work.", true); return null; }
    render(r, r.says, focusSel || "#orgSaid");
    return r;
  };

  const wire = (d) => {
    root.querySelector("#orgTests").onchange = (e) => {
      showTests = S.orgsShowTests = e.target.checked; render(d);
    };
    const find = root.querySelector("#orgFind");
    find.oninput = () => {
      filter = find.value; render(d);
      const again = root.querySelector("#orgFind");
      again.focus(); again.setSelectionRange(again.value.length, again.value.length);
    };

    root.querySelectorAll("[data-setrole]").forEach((b) => b.onclick = () => {
      const toAdmin = b.dataset.setrole === "admin";
      askConfirm({
        title: toAdmin ? `Make ${b.dataset.name} an admin of ${b.dataset.orgname}?`
                       : `Make ${b.dataset.name} a member of ${b.dataset.orgname}?`,
        body: toAdmin
          ? `${b.dataset.name} will be able to add people, make people admins, and take people `
            + `off ${b.dataset.orgname} — and no other organization.`
          : `${b.dataset.name} stays on ${b.dataset.orgname} but can no longer add or remove people.`,
        confirmLabel: toAdmin ? "Make admin" : "Make member",
        onYes: () => act("/api/admin/member/role",
          { agency: b.dataset.org, email: b.dataset.email, role: b.dataset.setrole }),
      });
    });
    root.querySelectorAll("[data-drop]").forEach((b) => b.onclick = () => askConfirm({
      title: `Remove ${b.dataset.name} from ${b.dataset.orgname}?`,
      body: `${b.dataset.name} comes off ${b.dataset.orgname} and is signed out now. Everything `
          + "they recorded stays on the record with their name on it.",
      confirmLabel: "Remove them",
      onYes: () => act("/api/admin/member/remove", { agency: b.dataset.org, email: b.dataset.email }),
    }));
    root.querySelectorAll("[data-signed]").forEach((b) => b.onclick = () => askConfirm({
      title: `Signed agreement received from ${b.dataset.name}?`,
      body: `Only once you have the executed Terms of Use for ${b.dataset.unit}, signed by both `
          + "parties. They can then get their verification code. This is recorded with your name.",
      confirmLabel: "Mark received",
      onYes: () => act("/api/admin/terms/received", { email: b.dataset.signed }, "#orgSaid"),
    }));
    // View as — see app/impersonate.py. View only, and nothing reaches the
    // organization; the bar across the top ends it.
    root.querySelectorAll("[data-viewas]").forEach((b) => b.onclick = () => askConfirm({
      title: `View as ${b.dataset.name}?`,
      body: `You will see ${b.dataset.orgname} exactly as ${b.dataset.name} does — view only. `
          + "Nothing can be saved or changed, and they are not told or interrupted. "
          + "Press End impersonation in the bar at the top to come back.",
      confirmLabel: "View as them",
      onYes: async () => {
        const r = await post("/api/admin/impersonate/start", { email: b.dataset.viewas });
        if (!r || !r.ok) { toast((r && r.error) || "That did not work.", true); return; }
        location.reload();
      },
    }));
    root.querySelectorAll("[data-pending]").forEach((b) => b.onclick = () => askConfirm({
      title: `Remove the sign-up for ${b.dataset.name}?`,
      body: "Their unfinished sign-up is cleared. They can start again at any time. "
          + "The removal is kept on the record.",
      confirmLabel: "Remove sign-up",
      onYes: () => act("/api/admin/pending/remove", { email: b.dataset.pending }, "#orgPendH"),
    }));

    // Appointing: states and their agencies, loaded once when first needed.
    const stSel = root.querySelector("#appState"), agSel = root.querySelector("#appAgency");
    const fillStates = () => {
      stSel.innerHTML = `<option value="">Choose a state…</option>` + statesList
        .map((s) => `<option value="${esc(s.code)}">${esc(s.state)}</option>`).join("");
    };
    if (statesList) fillStates();
    else api("/api/states").then((r) => {
      statesList = ((r && r.states) || []).slice()
        .sort((a, b) => a.state.localeCompare(b.state));
      if (root.contains(stSel)) fillStates();
    });
    stSel.onchange = () => {
      const s = (statesList || []).find((x) => x.code === stSel.value);
      const registered = new Set((d.organizations || []).map((o) => o.agency));
      const extra = (d.organizations || []).filter((o) => s && o.state === s.code
        && !(s.agencies || []).some((a) => a.id === o.agency));
      agSel.disabled = !s;
      agSel.innerHTML = s
        ? `<option value="">Choose an agency…</option>` + (s.agencies || [])
            .map((a) => `<option value="${esc(a.id)}">${esc(a.name)}${registered.has(a.id) ? " (registered)" : ""}</option>`).join("")
          + extra.map((o) => `<option value="${esc(o.agency)}">${esc(o.organization)} (not on the list)</option>`).join("")
        : `<option value="">Choose a state first</option>`;
    };
    const appErr = root.querySelector("#appErr");
    root.querySelector("#appGo").onclick = async () => {
      appErr.hidden = true;
      const v = (id) => root.querySelector(`#${id}`).value.trim();
      if (!v("appAgency") || !v("appEmail").includes("@")) {
        appErr.textContent = "Choose the agency and enter their work email.";
        appErr.hidden = false; return;
      }
      const b = root.querySelector("#appGo");
      b.disabled = true;
      const r = await post("/api/admin/appoint", { agency: v("appAgency"), name: v("appName"),
        title: v("appTitle"), email: v("appEmail") });
      b.disabled = false;
      if (!r || !r.ok) {
        appErr.textContent = (r && r.error) || "That did not work.";
        appErr.hidden = false; root.querySelector("#appEmail").focus(); return;
      }
      render(r, r.says, "#orgSaid");
    };
  };

  render(first);

  reason([
    { title: "Why only three addresses", body: "Appointing an organization's admins decides who can bring people into it, in every state. That is kept to brett@, lokesh@ and dev@iiac.ai, checked against the proven address on the server — not only by hiding this screen.", cite: "app/admin.py; app/tenancy.py — appoint" },
    { title: "What this screen cannot do", body: "Open any organization's framework, answers or documents. It reads and changes who is in an organization, and nothing else. Every change is on the audit log with who made it.", cite: "app/server.py — api_admin_organizations" },
  ]);
};

VIEWS.usage = async () => {
  const d = await api("/api/usage" + (S.usageRobots ? "?robots=1" : ""));
  const root = el("div");

  if (!d.allowed) {
    const no = el("div", "panel");
    no.innerHTML = `<h2 class="sub3" style="margin-top:0">Usage</h2>
      <p class="intro">${esc(d.note || "This screen is for the GAIUS team.")}</p>`;
    root.appendChild(no);
    $("#view").innerHTML = ""; $("#view").appendChild(root);
    return;
  }

  const o = d.overview || {};
  const c = d.caveats || {};

  const head = el("div", "panel");
  head.innerHTML = `
    <div class="spread">
      <div>
        <h2 class="sub3" style="margin-top:0">Usage</h2>
        <p class="intro" style="margin:0">Every agency on this installation, and
          everyone who has done anything in it.</p>
      </div>
      <button class="btn ghost${S.usageRobots ? " on" : ""}" id="usageRobots"
              type="button" aria-pressed="${!!S.usageRobots}">${
        S.usageRobots ? "Hide" : "Show"} test accounts</button>
    </div>
    <div class="us-tiles">
      ${[["People", o.people, "with a name on the record"],
         ["Agencies", o.agencies, "with activity"],
         ["States", o.states, "represented"],
         ["Time active", o.active, c.time_is_inferred ? "inferred" : "measured"],
         ["Log entries", (o.entries || 0).toLocaleString(), "since " +
           niceDate(o.first_entry)]]
        .map(([label, value, note]) => `
          <div class="us-tile">
            <b>${esc(String(value == null ? "—" : value))}</b>
            <span>${esc(label)}</span>
            <i>${esc(note)}</i>
          </div>`).join("")}
    </div>
    <div class="us-caveat">
      <b>About the time figure.</b> ${esc(c.note || "")}
      ${c.sign_ins_recorded
        ? `<br>${c.sign_ins_recorded} sign-in(s) are now recorded, so this is
           measured for those and inferred for everything before them.`
        : `<br>No sign-ins are recorded yet. They are written from now on, so
           this becomes measured rather than inferred as people return.`}
    </div>`;
  root.appendChild(head);

  /* Agencies first. "Which state" was the first thing he asked for, and an
     agency with nobody on it and nothing answered is as much of an answer as
     a busy one. */
  const byAgency = el("div", "panel");
  byAgency.innerHTML = `
    <h2 class="sub3" style="margin-top:0">By agency</h2>
    ${(d.agencies || []).length ? `
    <table class="grid">
      <thead><tr>
        <th scope="col">State</th><th scope="col">Agency</th>
        <th scope="col">Progress</th><th scope="col">Versions</th>
        <th scope="col">Adopted</th><th scope="col">People</th>
        <th scope="col">Last active</th>
      </tr></thead>
      <tbody>${d.agencies.map((a) => {
        const p = a.progress || {};
        return `<tr${a.test_only ? ' class="us-test"' : ""}>
          <td>${esc(a.state || "—")}</td>
          <td>${esc(a.name || a.agency)}
            ${a.test_only ? '<span class="us-tag">test</span>' : ""}
            <div class="small muted mono">${esc(a.agency)}</div></td>
          <td>
            <div class="us-bar" role="img"
                 aria-label="${p.answered || 0} of ${p.asked || 0} answered">
              <i style="width:${p.percent || 0}%"></i></div>
            <span class="small">${p.answered || 0} of ${p.asked || 0}
              (${p.percent || 0}%)</span></td>
          <td>${p.versions || 0}</td>
          <td>${p.adopted ? "yes" : "no"}</td>
          <td>${(a.people || []).length}
            <div class="small muted">${esc((a.people || []).join(", "))}</div></td>
          <td class="small mono">${esc(whenLocal(a.last))}</td>
        </tr>`;
      }).join("")}</tbody>
    </table>` : `<p class="muted">Nothing recorded against any agency yet.</p>`}`;
  root.appendChild(byAgency);

  const byPerson = el("div", "panel");
  byPerson.innerHTML = `
    <h2 class="sub3" style="margin-top:0">By person</h2>
    <p class="small muted">A person is the name they entered, not the capacity
      they were acting in — the header lets one person move between several of
      those deliberately, and they are listed rather than treated as different
      people.</p>
    ${(d.people || []).length ? `
    <table class="grid">
      <thead><tr>
        <th scope="col">Name</th><th scope="col">State</th>
        <th scope="col">Agency</th><th scope="col">Actions</th>
        <th scope="col">Sittings</th><th scope="col">Time active</th>
        <th scope="col">Worked on</th><th scope="col">Last seen</th>
      </tr></thead>
      <tbody>${d.people.map((p) => `
        <tr${p.test_account ? ' class="us-test"' : ""}>
          <td>${esc(p.name)}
            ${p.test_account ? '<span class="us-tag">test</span>' : ""}
            ${p.titles.length
              ? `<div class="small muted">${esc(p.titles.join(", "))}</div>`
              : ""}</td>
          <td>${esc((p.states || []).join(", ") || "—")}</td>
          <td class="small mono">${esc((p.agencies || []).join(", ") || "—")}</td>
          <td>${p.actions}${p.refused
            ? `<div class="small" style="color:var(--alert)">${p.refused}
               refused</div>` : ""}</td>
          <td>${p.sittings}${p.sessions_recorded
            ? `<div class="small muted">${p.sessions_recorded} signed in</div>`
            : ""}</td>
          <td>${esc(p.active)}</td>
          <td class="small">${(p.worked_on || []).slice(0, 3).map((w) =>
            `${esc(w.what)} <span class="muted">&times;${w.times}</span>`)
            .join("<br>")}</td>
          <td class="small mono">${esc(whenLocal(p.last_seen))}</td>
        </tr>`).join("")}</tbody>
    </table>` : `<p class="muted">Nobody has done anything yet.</p>`}`;
  root.appendChild(byPerson);

  $("#view").innerHTML = ""; $("#view").appendChild(root);

  const toggle = $("#usageRobots");
  if (toggle) toggle.onclick = () => {
    S.usageRobots = !S.usageRobots;
    VIEWS.usage();
  };

  reason([
    { title: "Why this screen crosses the line",
      body: "Every other screen in this application is scoped to one agency, because reading another agency's work is the thing it must never do. This one reads all of them, which is why it is keyed on a verified email address and not on a capacity anybody can choose. Running the product is a different job from being governed by it.",
      cite: "app/admin.py" },
    { title: "Why the hours are called active, not logged in",
      body: "Nothing recorded signing in when this was asked for, so the time here is the span from a person's first action in a sitting to their last. Somebody who reads their framework for an hour and changes nothing shows as no time at all. Sign-ins are recorded from now on, and the figure becomes measured as they accumulate.",
      cite: "app/usage.py" },
  ]);
};

/* Audit trail — what happened, who did it, and under which rules. One entry
   per event, this organization's own and nobody else's. Nothing here is
   edited and nothing here is removed; a mistake is corrected by a second
   entry beside it. */
const AT = { said: "", filter: {}, sort: "Newest first", form: null };

VIEWS.audit = async () => {
  const qs = new URLSearchParams({ ...AT.filter, sort: AT.sort }).toString();
  const d = await api(`/api/audit?${qs}`);
  const root = el("div");
  const live = el("p", "vh"); live.setAttribute("aria-live", "polite");
  root.appendChild(live);
  const story = !!AT.filter.record;

  const head = el("div", "panel");
  head.innerHTML = `
    <p class="intro" style="margin-top:0">One entry per event — one thing that happened, done by
      one person, at one moment, to one record. Nothing here is edited and nothing here is removed.</p>
    <p class="small"><a href="#atFindings">Skip to the findings</a> · <a href="#atList">Skip to the list</a></p>
    <p class="row" style="gap:8px;flex-wrap:wrap">
      <button type="button" class="btn" id="atElsewhere">Record something that happened somewhere else</button>
      <button type="button" class="btn ghost" id="atProduce">Produce the record</button></p>`;
  root.appendChild(head);

  // §4 · the stat row, and the trail line under it.
  const c = d.counters || {}, g = c.guidance || {};
  const stats = el("section", "panel");
  stats.setAttribute("aria-label", "Counts");
  stats.innerHTML = `<div class="vr-tiles">${[
      [c.entries, "Entries in the trail", g.entries],
      [c.after_the_fact, "Recorded after it happened", g.after_the_fact],
      [c.nothing_said_about_why, "Nothing said about why", g.nothing_said_about_why],
      [c.corrections, "Corrections recorded", g.corrections],
      [c.versions, "Versions of your framework in this trail", g.versions]]
    .map(([n, l, s], i) => `<div class="vr-tile" tabindex="0" aria-describedby="atTip${i}">
      <b>${n || 0}</b><span>${esc(l)}</span><span class="small vh" id="atTip${i}">${esc(s || "")}</span></div>`).join("")}</div>
    <p class="vr-money">${esc(d.trail_line)}</p>
    ${d.small && d.people_count === 1 ? `<p class="small muted">In an organization your size, one person writing every line is ordinary.</p>` : ""}`;
  root.appendChild(stats);

  // §5 · findings.
  const raised = d.raised || [];
  const f = el("section", "panel");
  f.id = "atFindings";
  f.setAttribute("aria-labelledby", "atFindingsH");
  f.innerHTML = `<h2 class="sub3" id="atFindingsH" style="margin-top:0">${raised.length
      ? `${raised.length} finding${raised.length === 1 ? "" : "s"}` : "Nothing to flag"}</h2>
    ${raised.length ? `<ul class="vr-flags">${raised.map((x) => `<li>${esc(x.says)}</li>`).join("")}</ul>`
      : `<p class="intro">${esc(d.nothing_to_flag)}</p>`}`;
  root.appendChild(f);

  // §6 · the seal check and the version window check, and what neither can see.
  const s = d.seal || {}, w = d.window || {};
  const checks = el("section", "panel");
  checks.setAttribute("aria-labelledby", "atSealH");
  checks.innerHTML = `<h2 class="sub3" id="atSealH" style="margin-top:0">The seal check</h2>
    <p class="small">${esc(s.says)}</p>
    <p class="small"><b>${s.checked || 0}</b> Entries checked | <b>${s.matched || 0}</b> Matched |
      <b>${s.did_not_match || 0}</b> Did not match | <b>${s.could_not_be_read || 0}</b> Could not be read</p>
    <p><button type="button" class="btn ghost" id="atSeal">Check the trail now</button></p>
    <p class="small">${esc(s.limit)}</p>
    <h2 class="sub3">Which rules were in force</h2>
    <p class="small">${esc(w.says)}</p>
    <p class="small"><b>${w.covered || 0}</b> Entries covered by a version | <b>${w.before_adoption || 0}</b> Written before your framework took effect |
      <b>${w.no_version_in_force || 0}</b> With no version in force | <b>${w.versions_without_a_date || 0}</b> Versions with no date on them</p>
    <p class="small muted">${esc(w.note)}</p>
    <h2 class="sub3">What this trail cannot see</h2>
    <p class="small">${esc(d.cannot_see)}</p>
    <h2 class="sub3">What is not recorded here, on purpose</h2>
    ${String(d.not_recorded || "").split("\n\n").map((p) => `<p class="small">${esc(p)}</p>`).join("")}`;
  checks.querySelector("#atSeal").onclick = () => {
    AT.said = `Seal check finished. ${s.checked || 0} entries checked. ${s.did_not_match ? `${s.did_not_match} did not match.` : "All matched."}`;
    go("audit");
  };
  root.appendChild(checks);

  // §7 · the trail, or one record in order.
  const list = el("section", "panel");
  list.id = "atList";
  list.setAttribute("aria-labelledby", "atListH");
  const entries = d.entries || [];
  const notesFor = (seq) => (d.notes || {})[String(seq)] || [];
  list.innerHTML = `<h2 class="sub3" id="atListH" style="margin-top:0">${story ? `Everything that happened to ${esc(AT.filter.record)}, in order` : "The trail"}</h2>
    <form id="atFilter" class="row" style="gap:12px;flex-wrap:wrap;align-items:flex-end">
      <label class="vr-field" style="margin:0">Record
        <input id="at-record" list="at-records" value="${esc(AT.filter.record || "")}">
        <datalist id="at-records">${(d.projects || []).map((p) => `<option value="${esc(p.ref)}">${esc(p.name)}</option>`).join("")}</datalist></label>
      <label class="vr-field" style="margin:0">Person
        <select id="at-person"><option value="">Anybody</option>${(d.people || []).map((p) => `<option${p === AT.filter.person ? " selected" : ""}>${esc(p)}</option>`).join("")}</select></label>
      <label class="vr-field" style="margin:0">Hat
        <select id="at-hat"><option value="">Any hat</option>${d.options.hats.map((h) => `<option${h === AT.filter.hat ? " selected" : ""}>${esc(h)}</option>`).join("")}</select></label>
      <label class="vr-field" style="margin:0">From <input type="date" id="at-since" value="${esc(AT.filter.since || "")}"></label>
      <label class="vr-field" style="margin:0">To <input type="date" id="at-until" value="${esc(AT.filter.until || "")}"></label>
      <label class="vr-field" style="margin:0">Sort
        <select id="at-sort">${d.options.sorts.map((o) => `<option${o === AT.sort ? " selected" : ""}>${esc(o)}</option>`).join("")}</select></label>
      <button type="submit" class="btn ghost">Show</button>
      ${Object.keys(AT.filter).length ? `<button type="button" class="btn ghost" id="atClear">Clear</button>` : ""}</form>
    <p class="small">${esc(d.filter_sentence)}</p>
    ${story ? `<div class="vr-tell"><p>Nobody has written down yet what somebody would need to explain a decision this one touched. That question is asked on the retirement record, at the point the tool is shut off, and this one has not reached that. Everything below is what this application has. Whether it is enough is a judgment for whoever your framework named.${d.written_where ? ` The rest of the record is wherever you said you keep it: ${esc(d.written_where)}` : ""}</p></div>` : ""}
    ${entries.length ? (story
      ? `<ol class="at-story">${entries.map((r) => `<li><p><b>${esc(r.when)}.</b> ${esc(r.what)}. ${esc(r.who)}, as ${esc(r.hat)}. Under ${esc(r.version)}.</p>
          ${r.changed ? `<p class="small">${esc(r.changed)}</p>` : ""}
          ${notesFor(r.seq).length ? `<ul>${notesFor(r.seq).map((n) => `<li class="small">${esc(n.when)}. ${esc(n.what)} — ${esc(n.who)}: ${esc(n.changed)}</li>`).join("")}</ul>` : ""}
          <p><button type="button" class="btn ghost" data-at-note="${r.seq}">Add a note</button>
            <button type="button" class="btn ghost" data-at-correct="${r.seq}">Correct this entry</button></p></li>`).join("")}</ol>`
      : `<div class="vr-scroll" tabindex="0" role="region" aria-labelledby="atListH">
        <table class="vr-table"><caption class="vh">${esc(d.filter_sentence)} Sorted ${esc(AT.sort.toLowerCase())}.</caption>
        <thead><tr>${["When", "What happened", "Which record", "Where", "Who", "Hat", "What changed", "Under which version", ""]
          .map((h) => `<th scope="col">${h || '<span class="vh">Actions</span>'}</th>`).join("")}</tr></thead>
        <tbody>${entries.map((r) => `<tr>
          <td>${esc(r.when)}</td><th scope="row">${esc(r.what)}${r.from_elsewhere ? '<br><span class="small">Recorded by a person, from somewhere else</span>' : ""}${r.denied ? '<br><span class="small">Refused</span>' : ""}
            ${notesFor(r.seq).length ? `<br><span class="small">${notesFor(r.seq).length} note${notesFor(r.seq).length === 1 ? "" : "s"} or correction${notesFor(r.seq).length === 1 ? "" : "s"} beside this</span>` : ""}</th>
          <td>${r.record !== "How you run things" && r.record !== "Your framework"
            ? `<button type="button" class="btn ghost" data-at-story="${esc(r.record)}">${esc(r.record)}</button>` : esc(r.record)}</td>
          <td>${esc(r.where)}</td><td>${esc(r.who)}</td><td>${esc(r.hat)}</td>
          <td>${esc(r.changed)}</td><td>${esc(r.version)}</td>
          <td><button type="button" class="btn ghost" data-at-note="${r.seq}">Add a note</button>
            <button type="button" class="btn ghost" data-at-correct="${r.seq}">Correct</button></td></tr>`).join("")}</tbody></table></div>`)
      : `<p class="intro">${esc(d.empty_state)}</p>`}`;
  list.querySelector("#atFilter").onsubmit = (e) => {
    e.preventDefault();
    const pick = { record: igVal(list, "at-record"), person: igVal(list, "at-person"), hat: igVal(list, "at-hat"),
                   since: igVal(list, "at-since"), until: igVal(list, "at-until") };
    AT.filter = Object.fromEntries(Object.entries(pick).filter(([, v]) => v));
    AT.sort = igVal(list, "at-sort") || "Newest first";
    go("audit");
  };
  const clr = list.querySelector("#atClear");
  if (clr) clr.onclick = () => { AT.filter = {}; go("audit"); };
  list.querySelectorAll("[data-at-story]").forEach((b) => b.onclick = () => {
    AT.filter = { record: b.dataset.atStory }; go("audit"); });
  root.appendChild(list);

  const scope = el("div", "panel");
  scope.innerHTML = `<p class="small">A record of what happened, not a records system. This is not your retention schedule and it does not satisfy it. It holds no permits, no letters, no minutes, no invoices, no contracts and no correspondence. It does not hold what anybody typed into an AI tool or what the tool said back. It does not watch anybody work, count anybody's output, or record who read anything. It shows what was decided, by whom, on what date, and under which version of the rules you wrote.</p>
    <p class="small">Your trail is yours, and you can take it with you. The whole trail can be produced at any time, by anybody with an account, without asking us and without a fee.</p>`;
  root.appendChild(scope);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  live.textContent = AT.said || (raised.length ? `${raised.length} finding${raised.length === 1 ? "" : "s"}.` : "");
  AT.said = "";

  const open = (builder) => {
    const old = $("#atForm"); if (old) old.remove();
    const host = el("section", "panel");
    host.id = "atForm";
    head.after(host);
    builder(host);
    const h = host.querySelector("h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
  };
  $("#atElsewhere").onclick = () => open((host) => trailElsewhereForm(host, d));
  $("#atProduce").onclick = () => open((host) => trailProduce(host, d));
  $("#view").querySelectorAll("[data-at-note]").forEach((b) => b.onclick = () =>
    open((host) => trailNoteForm(host, d, entries.find((r) => String(r.seq) === b.dataset.atNote))));
  $("#view").querySelectorAll("[data-at-correct]").forEach((b) => b.onclick = () =>
    open((host) => trailCorrectForm(host, d, entries.find((r) => String(r.seq) === b.dataset.atCorrect))));
};

/* §8A · Record something that happened somewhere else. Only the first line
   is required, and there is no upload. */
function trailElsewhereForm(host, d) {
  const opt = d.options;
  host.innerHTML = `<h2 class="sub3" style="margin-top:0">Record something that happened somewhere else</h2>
    <p class="intro">Only the first line is required. Governance happens in rooms this application
      cannot see — a board votes, a vendor says something on a call, somebody finds a tool running in a
      back office. Everything you record here is marked as recorded by you, from somewhere else, and it is
      never mixed with what the application watched happen.</p>
    ${igText("at-what", "What happened?", "One line, in your own words. For example: the board voted to adopt the framework · the vendor told us on a call that the AI feature had been switched on.")}
    <p class="small" id="at-what-err" role="alert"></p>
    ${igText("at-happened", "When did it happen?", "The date it happened, if you know it, rather than today's date. Today's date is recorded anyway, on its own.", { type: "date" })}
    ${igRadios("at-how", "How do you know?", opt.how_known, "", "Two years from now the difference between what you saw and what somebody told you will matter, and nobody will remember which it was.")}
    ${igRadios("at-about", "Which record is this about?", opt.about, "")}
    <div id="at-refbox" hidden><div class="vr-field"><label for="at-ref">Which project</label>
      <select id="at-ref"><option value="">Choose one</option>${(d.projects || []).map((p) => `<option value="${esc(p.ref)}">${esc(p.name)}</option>`).join("")}</select></div></div>
    <fieldset class="vr-tri" style="display:block"><legend>Who was involved?</legend>
      <p class="small muted">Titles survive turnover and names do not, so the title is the one that is required.</p>
      <div id="at-people"></div></fieldset>
    ${igText("at-paper", "Where is the paper copy?", d.written_where ? `Pre-filled with what you told us at Step 4. Change it here if this one went somewhere else. The kind, never the credential: name where the document is; do not paste what is inside it.` : "You have not said where decisions get written down. Say where this one is.", { value: d.written_where || "" })}
    ${d.written_where ? igRadios("at-where", "Was this written down where you said?", opt.written_where, "", `You said decisions get written down here: ${d.written_where}`) : ""}
    ${igText("at-note", "Anything else worth recording (optional)", "", { long: true })}
    <p class="vr-tell small">${esc(d.copy.record_it)}</p>
    <p><button type="button" class="btn" id="at-save">Record it</button>
      <button type="button" class="btn ghost" id="at-cancel">Cancel</button></p>`;
  const $$ = (q) => host.querySelector(q);
  host.querySelectorAll('[name="at-about"]').forEach((r) => r.onchange = () => {
    $$("#at-refbox").hidden = igPicked(host, "at-about") !== "A project"; });
  const people = prRows($$("#at-people"), [["role", "Role title"], ["name", "Name (optional)"],
    ["outside", "Which organization, if outside this one"]], [{}], "Person");
  $$("#at-cancel").onclick = () => { host.remove(); $("#atElsewhere").focus(); };
  $$("#at-save").onclick = async () => {
    const what = igVal(host, "at-what");
    if (!what) { $$("#at-what-err").textContent = "Say what happened, in one line."; $$("#at-what").focus(); return; }
    const out = await post("/api/trail/elsewhere", {
      what, happened: igVal(host, "at-happened"), how_known: igPicked(host, "at-how"),
      about: igPicked(host, "at-about"), ref: igVal(host, "at-ref"),
      involved: people.read().filter((p) => p.role), paper: igVal(host, "at-paper"),
      written_where: igPicked(host, "at-where"), note: igVal(host, "at-note") });
    if (out && out.ok) { AT.said = "Recorded, as recorded by you from somewhere else."; go("audit"); }
    else $$("#at-what-err").textContent = (out && out.error) || "That did not save.";
  };
}

function trailNoteForm(host, d, entry) {
  host.innerHTML = `<h2 class="sub3" style="margin-top:0">Add a note to an entry</h2>
    <p class="small"><b>${esc(entry.when)}.</b> ${esc(entry.what)}. ${esc(entry.who)}, as ${esc(entry.hat)}.</p>
    ${igText("at-notetext", "What do you want to say about this entry?", "", { long: true })}
    ${igRadios("at-notekind", "What kind of note is this?", d.options.note_kinds, "Nothing more, just a note",
      "If a permit, a case, an appeal or a claim that this touched is still open, say so. That note tells whoever is doing the tidying in three years that this one is not finished with.")}
    <p class="small muted">${esc(d.copy.note)}</p>
    <p class="small" id="at-noteerr" role="alert"></p>
    <p><button type="button" class="btn" id="at-notesave">Add the note</button>
      <button type="button" class="btn ghost" id="at-notecancel">Cancel</button></p>`;
  const $$ = (q) => host.querySelector(q);
  host.querySelectorAll('[name="at-notekind"]').forEach((r) => r.onchange = () => {
    if (igPicked(host, "at-notekind") === "Something here is wrong") {
      trailCorrectForm(host, d, entry); host.querySelector("h2").focus(); } });
  $$("#at-notecancel").onclick = () => host.remove();
  $$("#at-notesave").onclick = async () => {
    const out = await post("/api/trail/note", { of: entry.seq, text: igVal(host, "at-notetext"),
      kind: igPicked(host, "at-notekind") });
    if (out && out.ok) { AT.said = "Note added. The entry is unchanged."; go("audit"); }
    else $$("#at-noteerr").textContent = (out && out.error) || "";
  };
}

function trailCorrectForm(host, d, entry) {
  host.innerHTML = `<h2 class="sub3" style="margin-top:0">Correct an entry</h2>
    <p class="small"><b>${esc(entry.when)}.</b> ${esc(entry.what)}. ${esc(entry.who)}, as ${esc(entry.hat)}.
      ${entry.changed ? esc(entry.changed) : ""}</p>
    ${igText("at-wrong", "What is wrong with it?", "")}
    ${igText("at-should", "What should it say? (optional)", "", { long: true })}
    <p class="vr-tell small">${esc(d.copy.correction)}</p>
    <p class="small" id="at-correrr" role="alert"></p>
    <p><button type="button" class="btn" id="at-corrsave">Record the correction</button>
      <button type="button" class="btn ghost" id="at-corrcancel">Cancel</button></p>`;
  const $$ = (q) => host.querySelector(q);
  $$("#at-corrcancel").onclick = () => host.remove();
  $$("#at-corrsave").onclick = async () => {
    const out = await post("/api/trail/correct", { of: entry.seq, wrong: igVal(host, "at-wrong"),
      should: igVal(host, "at-should") });
    if (out && out.ok) { AT.said = "Correction recorded beside the entry. Both stay on the record."; go("audit"); }
    else $$("#at-correrr").textContent = (out && out.error) || "";
  };
}

/* §7C · Produce the record. Two files, from exactly what the filter selected. */
function trailProduce(host, d) {
  host.innerHTML = `<h2 class="sub3" style="margin-top:0">Produce the record</h2>
    <p>Two files, from exactly what is on this screen right now. One for a person to read: every entry
      in date order, with your framework's versions at the front and the filter that produced it stated on
      the first page. One for a system to read: one row for every entry with every field on it. Both carry
      the result of the seal check at the moment they were produced. Producing this is itself written down.</p>
    <p class="small">${esc(d.filter_sentence)}</p>
    <p class="small muted">${esc(d.copy.no_excluding)}</p>
    <p><button type="button" class="btn" id="at-go">Produce it</button>
      <button type="button" class="btn ghost" id="at-producecancel">Cancel</button></p>
    <p class="small" id="at-produced" role="status"></p>`;
  const $$ = (q) => host.querySelector(q);
  $$("#at-producecancel").onclick = () => host.remove();
  $$("#at-go").onclick = async () => {
    const out = await post("/api/trail/produce", { filter: AT.filter });
    if (!out || !out.ok) { $$("#at-produced").textContent = (out && out.error) || "That did not work."; return; }
    const save = (b64, name, type) => {
      const bytes = Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type }));
      const a = document.createElement("a"); a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    };
    const stamp = localToday();
    try { save(out.html, `the-record-${stamp}.html`, "text/html"); save(out.csv, `the-record-${stamp}.csv`, "text/csv"); }
    catch (e) { /* a browser that cannot save still hears what was produced */ }
    $$("#at-produced").textContent = `Produced: ${out.count} entries. ${out.seal}`;
  };
}

/* ------------------------------------------------------------------ init */

// Only items that name a view navigate. "Choose agency" is a .rail-item too but
// carries no data-view, and without this filter it also fired go(undefined),
// blanking the record behind the launcher.
document.querySelectorAll(".rail-item[data-view]").forEach((b) =>
  b.addEventListener("click", () => go(b.dataset.view)));
// Same for the chips; the agency chip has its own handler.
document.querySelectorAll(".tb-chip[data-view]").forEach((b) =>
  b.addEventListener("click", () => go(b.dataset.view)));

/* Keyboard navigation for the rail.
 *
 * These are ordinary <button>s in a <nav>, so Tab has always walked them but
 * arrow keys did nothing — browsers only move focus with arrows inside composite
 * widgets (radio groups, listboxes, toolbars), and that has to be implemented.
 *
 * Up/Down move focus and wrap, Home/End jump to the ends, and typing a letter
 * jumps to the next item starting with it. Enter or Space opens the focused
 * item. Focus moves without selecting on purpose: this is a navigation
 * landmark, and arrowing past six sections should not load six views.
 *
 * Tab stops are left intact rather than collapsed into a single roving one —
 * Tab walking a nav is what most people expect of a sidebar, so this is added
 * on top of that behavior rather than replacing it.
 */
function railItems() {
  return [...document.querySelectorAll(".rail-item")]
    .filter((b) => b.offsetParent !== null && !b.disabled);
}

/** The item's own label, without its icon glyph or its OT/GATED tag. */
function railLabel(button) {
  const own = [...button.childNodes]
    .find((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
  return (own ? own.textContent : button.textContent).trim().toLowerCase();
}

$(".rail").addEventListener("keydown", (e) => {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const items = railItems();
  const at = items.indexOf(document.activeElement);
  if (at === -1) return;                 // focus is in the rail but not on an item

  let to = null;
  if (e.key === "ArrowDown") to = (at + 1) % items.length;
  else if (e.key === "ArrowUp") to = (at - 1 + items.length) % items.length;
  else if (e.key === "Home") to = 0;
  else if (e.key === "End") to = items.length - 1;
  else if (e.key.length === 1 && /\S/.test(e.key)) {
    // Search from the item after the current one, so repeats cycle matches.
    const key = e.key.toLowerCase();
    const order = [...items.slice(at + 1), ...items.slice(0, at + 1)];
    const hit = order.find((b) => railLabel(b).startsWith(key));
    if (hit) { e.preventDefault(); hit.focus(); }
    return;
  } else return;

  e.preventDefault();                    // otherwise Up/Down scrolls the page
  items[to].focus();
});
/* `#spineProj` went with the retired strip, so nothing is wired to it. */
/* The collapse toggle went with the column. Guarded rather than deleted so the
   markup and the script can be updated independently without one throwing. */
const reasonToggle = $("#reasonToggle");
if (reasonToggle) {
  reasonToggle.onclick = () => $(".shell").classList.toggle("no-reason");
}
$("#userPick").addEventListener("change", async (e) => {
  S.user = e.target.value; await refreshState(); go(S.view);
});

/* The agency is chosen once, during onboarding, and is not something to flick
   between mid-session — so the rail no longer carries a switcher. The picker is
   reachable at #agency only before an agency has been chosen — showLauncher()
   refuses once one has,
   and by the "Choose another agency" button on the no-corpus screen. */
/* The agency picker, and the one rule about it.

   Once someone is signed in to an agency, this must not open. The client's rule
   is not "discourage switching" — it is that a user "should not be able to ever
   see another agency or switch agencies/governmental units", and the picker is
   a list of 149 of them.

   The hole this closes: the empty-state screen on Vision carried a "Choose
   another agency" button. Pressing it opened the map, and picking a different
   agency took you into it — from inside a signed-in DEMO session. Every other
   guard in the application is about not *rendering* another agency's records;
   this one was a door straight into them.

   Signing out is the way to a different agency, and it is the only way: it
   clears the stored agency, which is what lets the map open again. */
const showLauncher = () => {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem("scdes.registration") || "{}") || {};
  } catch (e) { saved = {}; }

  if (saved.verified && saved.agency) {
    toast("Sign out first — an agency cannot be switched from inside one.");
    return;
  }
  if (window.openLauncher) window.openLauncher();
  else location.reload();          // launcher.js failed to load — force a fetch
};
/* The tour, the intro, the bug form and the destination search now live in one
   launcher in the corner — see guide.js. The header chip that used to start the
   tour is gone with them, so this guards for its absence rather than assuming
   markup that is no longer there. */
const tourChip = $("#tourChip");
if (tourChip) tourChip.onclick = () => window.startTour && window.startTour(true);
if (window.initVoice) window.initVoice();
// Capture starts with the page, not with the report — most faults cannot be
// reproduced on demand, and asking someone to try loses the evidence.
if (window.initBugs) window.initBugs();
if (window.initGuide) window.initGuide();
if (window.initNotify) window.initNotify();

/* Signing out.

   There is no server session to end — this build has no authentication of its
   own, and identity travels as headers on each request. So what this actually
   does is forget the identity *this browser* is presenting, and the wording
   says that rather than implying a session was terminated somewhere.

   What it clears and what it keeps is a deliberate split. Identity goes: the
   registration, the verified flag, the name and title on every audit entry.
   Display preferences stay — light or dark mode, whether the tour has been
   seen — because they belong to the person using the machine, not to the
   account, and resetting someone's theme when they hand the laptop over is
   just rude.

   Nothing on the server is touched. The agency container, its answers and the
   audit trail are all still there; this is the door, not a demolition. That
   distinction matters enough to say on the confirmation, because "sign out"
   and "start over" are one click apart and only one of them is reversible. */
/* Ask before doing something, without using the browser's dialog.

   Reported as "Clicking Sign Out would sign me out" → "Nothing." This was the
   last `confirm()` in the application and it is a silent single point of
   failure: from the second dialog a page raises, Chrome offers "prevent this
   page from creating additional dialogs", and once that box is ticked
   `confirm()` returns false forever without drawing anything. The handler then
   hits `if (!ok) return` and the button is dead for the life of that browser
   profile — with nothing on screen to explain why, and pressing it again only
   makes it deader.

   The one door out of the application cannot depend on a control the browser
   is allowed to switch off, so it draws its own. */
function askConfirm({ title, body, confirmLabel = "Continue", onYes }) {
  document.getElementById("confirmVeil")?.remove();

  const veil = document.createElement("div");
  veil.id = "confirmVeil";
  veil.className = "confirm-veil";
  veil.innerHTML = `
    <div class="confirm-card" role="alertdialog" aria-modal="true"
         aria-labelledby="confirmTitle">
      <h2 id="confirmTitle">${esc(title)}</h2>
      <p>${esc(body)}</p>
      <div class="confirm-actions">
        <button class="btn ghost" id="confirmNo" type="button">Cancel</button>
        <button class="btn" id="confirmYes" type="button">${esc(confirmLabel)}</button>
      </div>
    </div>`;
  document.body.appendChild(veil);

  const close = () => { veil.remove(); document.removeEventListener("keydown", key); };
  const key = (e) => {
    if (e.key === "Escape") { e.preventDefault(); close(); }
  };
  document.addEventListener("keydown", key);
  // A click on the backdrop cancels; one inside the card must not.
  veil.onclick = (e) => { if (e.target === veil) close(); };
  document.getElementById("confirmNo").onclick = close;
  document.getElementById("confirmYes").onclick = () => { close(); onYes(); };
  document.getElementById("confirmYes").focus();
}

function signOut() {
  const who = (S.state && S.state.actor && S.state.actor.name) || "";
  askConfirm({
    title: who ? `Sign ${who} out of this browser?` : "Sign out?",
    body: "This forgets who you are on this device. Nothing is deleted — your "
      + "agency, everything you have answered and the audit trail all stay "
      + "exactly as they are, and signing back in returns you to them.",
    confirmLabel: "Sign out",
    onYes: finishSignOut,
  });
}

function finishSignOut() {
  // Retired on the server before it is dropped here, so a token copied off a
  // shared machine stops working rather than merely stopping being convenient.
  // Fire and forget: a failed request must not leave someone stuck signed in.
  const token = sessionToken();
  if (token) {
    try {
      fetch("/api/session/end", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: token }),
      }).catch(() => {});
    } catch (e) {}
  }
  ["scdes.registration", "scdes.signin", "scdes.welcomeSeen",
   "scdes.session"].forEach((k) => {
    try { localStorage.removeItem(k); } catch (e) {}
  });
  /* Land on the map, not on the portal picker.

     `scdes.portal` is deliberately NOT in the list above. Clearing it would
     make this browser look brand new and send the next visit back to "Which of
     these are you?" — which is what happened when this was a one-shot session
     marker instead: sign-out reached the map, and the next refresh asked the
     question again. The kind of organization is a property of the machine, not
     of the person who just left. */
  // Deliberately kept: scdes.mode (light/dark) and scdes.tour. Preferences of
  // whoever is at the keyboard, not of the account that just left.

  // A full reload rather than clearing the in-memory state by hand. Every
  // module caches something — the framework status, the decider, the theme —
  // and a half-signed-out screen showing the previous person's agency is worse
  // than a second of white.
  location.replace(location.pathname);
}

/* "Your session ended — sign in again."

   On Sep 29 one tab kept working after the session behind it had gone — most
   likely signed out from another tab — and 111 framework answers were saved
   under no organization while the screen looked normal. Two things now stop
   that: the server refuses a change it cannot tie to an organization, and
   this tab notices when another one signs out or switches account. Either
   way the person is told plainly, nothing more is sent, and the one button
   takes them back to sign in. */
/* Nothing typed is lost. A change the server refused is kept here — for this
   person and this organization only — and sent again once they have signed
   back in. Kept in the browser, so it survives the reload a sign-in may take.
   The same answer refused twice is kept once, newest wins. */
const OUTBOX_KEY = "gaius.outbox";
function outbox() {
  try { return JSON.parse(localStorage.getItem(OUTBOX_KEY) || "[]") || []; }
  catch (e) { return []; }
}
function saveOutbox(items) {
  try { localStorage.setItem(OUTBOX_KEY, JSON.stringify(items.slice(-300))); } catch (e) {}
}
function whoIsHere() {
  try {
    const reg = JSON.parse(localStorage.getItem("scdes.registration") || "{}") || {};
    return { email: String(reg.email || "").toLowerCase(), agency: String(reg.agency || "") };
  } catch (e) { return { email: "", agency: "" }; }
}
function queueRefused(path, body) {
  const me = whoIsHere();
  if (!me.email || !me.agency) return;
  let key = "";
  try { key = (JSON.parse(body || "{}") || {}).key || ""; } catch (e) {}
  const items = outbox().filter((i) => !(key && i.path === path && i.key === key
    && i.email === me.email && i.agency === me.agency));
  items.push({ path, body: body || "{}", key, email: me.email, agency: me.agency,
               at: new Date().toISOString() });
  saveOutbox(items);
}
window.queueRefused = queueRefused;

/* Send what was kept, for whoever is signed in now. Anything kept for a
   different person or organization stays where it is — it is never sent in
   somebody else's name. Returns how many went. */
async function flushOutbox() {
  const me = whoIsHere();
  if (!me.email || !me.agency || !sessionToken()) return 0;
  let sent = 0;
  const keep = [];
  for (const item of outbox()) {
    if (item.email !== me.email || item.agency !== me.agency) { keep.push(item); continue; }
    let r = null;
    try { r = await api(item.path, { method: "POST", body: item.body }); } catch (e) { r = null; }
    if (r && r.ok !== false) sent += 1;
    else if (r && r.session_ended) keep.push(item);   // still not signed in: keep it
  }
  saveOutbox(keep);
  return sent;
}
window.flushOutbox = flushOutbox;

/* "Your session ended" — and signing back in from where they are, without
   losing the screen. A code goes to the address they are signed in with;
   entering it here signs them back in, and whatever was refused is sent. Where
   this tab no longer knows who they are (another tab signed out), the button
   goes back to the start instead, and the kept changes go once they sign in. */
function keptSentence(me) {
  const kept = outbox().filter((i) => i.email === me.email && i.agency === me.agency).length;
  return kept ? `${kept} change${kept === 1 ? " is" : "s are"} kept, and will be saved as soon as you are back.`
              : "Everything saved before this is where you left it.";
}

function sessionEnded(why) {
  const me = whoIsHere();
  const open = document.getElementById("sessionEndedVeil");
  if (open) {                    // already saying so: keep the count current
    const line = open.querySelector("#seKept");
    if (line) line.textContent = keptSentence(me);
    return;
  }
  const inPlace = !!(me.email && me.agency);
  const veil = document.createElement("div");
  veil.id = "sessionEndedVeil";
  veil.className = "confirm-veil";
  veil.innerHTML = `
    <div class="confirm-card" role="alertdialog" aria-modal="true"
         aria-labelledby="seTitle" aria-describedby="seBody" tabindex="-1">
      <h2 id="seTitle">Your session ended</h2>
      <p id="seBody">${esc(why || "You were signed out, so nothing more can be saved from this tab.")}
        <span id="seKept" aria-live="polite">${esc(keptSentence(me))}</span></p>
      ${inPlace ? `
        <p class="small">Sign back in here — a six-digit code goes to <b>${esc(me.email)}</b>.</p>
        <div id="seCodeRow" hidden>
          <p class="small" id="seShown"></p>
          <label class="small" for="seCode" style="display:block">Verification code</label>
          <input id="seCode" type="text" inputmode="numeric" maxlength="6" autocomplete="one-time-code">
        </div>
        <p class="small" id="seSaid" role="alert"></p>` : ""}
      <div class="confirm-actions">
        <button class="btn" id="seGo" type="button">${inPlace ? "Send me a code" : "Sign in again"}</button>
      </div>
    </div>`;
  document.body.appendChild(veil);
  const go = veil.querySelector("#seGo");
  const said = veil.querySelector("#seSaid");
  const focusables = () => [...veil.querySelectorAll("input:not([hidden]), button")]
    .filter((n) => !n.closest("[hidden]"));
  veil.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = focusables(); if (!f.length) return;
    const i = f.indexOf(document.activeElement);
    e.preventDefault();
    f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
  });
  const startOver = () => {
    ["scdes.registration", "scdes.session"].forEach((k) => {
      try { localStorage.removeItem(k); } catch (e) {}
    });
    location.replace("/");
  };
  if (!inPlace) { go.onclick = startOver; go.focus(); return; }

  let stage = "send";
  const post_ = (path, body) => fetch(path, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then((r) => r.json()).catch(() => ({ ok: false, error: "Could not reach the server." }));
  go.onclick = async () => {
    said.textContent = "";
    if (stage === "send") {
      go.disabled = true;
      const r = await post_("/api/agency/signin", { email: me.email });
      go.disabled = false;
      if (!r.ok) { said.textContent = r.error || "Could not send a code."; return; }
      veil.querySelector("#seCodeRow").hidden = false;
      if (r.code) veil.querySelector("#seShown").textContent = `No email is sent here, so the code is shown: ${r.code}`;
      stage = "verify";
      go.textContent = "Verify and carry on";
      veil.querySelector("#seCode").focus();
      return;
    }
    const code = (veil.querySelector("#seCode").value || "").replace(/\D/g, "");
    if (code.length !== 6) { said.textContent = "Enter the six-digit code."; return; }
    go.disabled = true;
    const v = await post_("/api/agency/verify", { email: me.email, code });
    go.disabled = false;
    if (!v.ok || !v.session) { said.textContent = v.error || "That code was not accepted."; return; }
    try { localStorage.setItem("scdes.session", v.session); } catch (e) {}
    // Back as the same person, in the same organization — or start over.
    let access = {};
    try { access = await fetch("/api/agency/access?email=" + encodeURIComponent(me.email)).then((r) => r.json()); }
    catch (e) {}
    if (access.state !== me.agency) { startOver(); return; }
    const n = await flushOutbox();
    veil.remove();
    await refreshState();
    toast(n ? `Signed back in. ${n} change${n === 1 ? "" : "s"} saved.` : "Signed back in.");
  };
  go.focus();
}
window.sessionEnded = sessionEnded;

/* A warning before a sign-in ends. Sessions renew while they are used
   (app/tenancy.py), so this is for one left idle to its end — said ten
   minutes ahead, with the way to keep it. */
let SESSION_WARN = null;
function watchSessionEnd(st) {
  clearTimeout(SESSION_WARN);
  const ends = st && st.session_expires ? new Date(st.session_expires).getTime() : 0;
  if (!ends) return;
  const warnIn = ends - Date.now() - 10 * 60 * 1000;
  if (warnIn > 24 * 3600 * 1000) return;            // more than a day away: look again later
  SESSION_WARN = setTimeout(() => {
    if (document.getElementById("sessionWarn")) return;
    const bar = el("div", "locked");
    bar.id = "sessionWarn";
    bar.setAttribute("role", "status");
    bar.style.margin = "0 0 14px";
    bar.innerHTML = `<b>Your sign-in ends in about 10 minutes.</b>
      <div class="row" style="margin-top:8px"><button type="button" class="btn" id="sessionStay">Stay signed in</button></div>`;
    const record = $("#record");
    if (record) record.prepend(bar);
    bar.querySelector("#sessionStay").onclick = async () => {
      await post("/api/session/renew", {});
      bar.remove();
      await refreshState();
    };
  }, Math.max(0, warnIn));
}

// Another tab signed out, or signed in as somebody else: this tab's identity
// is gone, so it stops here instead of carrying on with nobody behind it.
window.addEventListener("storage", (e) => {
  if (!S.state || (e.key !== "scdes.session" && e.key !== "scdes.registration")) return;
  if (e.key === "scdes.registration" && e.newValue) return;   // a detail changed, not who
  if (!e.oldValue || e.oldValue === e.newValue) return;       // nobody was signed in
  // Only a tab that is inside the product — not one on the home page or the
  // map, where there is nothing to lose.
  const home = document.getElementById("home");
  if ((home && !home.hidden) || document.body.classList.contains("launcher-open")) return;
  sessionEnded(e.newValue ? "You signed in as somebody else in another tab."
                          : "You signed out in another tab.");
});

const signOutBtn = $("#signOut");
if (signOutBtn) signOutBtn.onclick = signOut;
window.signOut = signOut;
window.addEventListener("hashchange", () => {
  if (location.hash === "#agency") showLauncher();
});
window.toast = toast;   // the launcher reports theme changes through the same toast
/* Exported for builder.js, which is a separate script and must not rely on
   sharing app.js's lexical scope to navigate or write the reason rail. */
window.go = go;
/* For tour.js and welcome.js, which are separate scripts and must not assume
   they share app.js's scope. The deciding body is one answer and it is read
   from one place. */
window.whoDecides = whoDecides;
window.whoDecidesPossessive = whoDecidesPossessive;
window.whoDecidesLabel = whoDecidesLabel;
/* Exported so tools/check_decider_wording.js can substitute a different
   agency's answer and re-render, which is the only way to tell wording that
   follows the decider from wording that happens to match it. */
window.paintDecider = paintDecider;
window.reason = reason;
window.refreshFramework = refreshFramework;

/* The sign-in step hands the chosen identity back here. Everything downstream —
   which rooms are writable, whose name lands in the audit entry — follows from
   this one value, so it is set in exactly one place. */
/* The beta notice, once each time somebody signs in.
 *
 * Keyed on the session token, which a reload keeps and a new sign-in
 * replaces — so it appears after signing in, as asked, and not on every
 * refresh. A new wording carries a new version and is shown again. The
 * words come from the server (`app/beta.py`) so they live in one place and
 * are checked like the rest of the product's language, and pressing the
 * button is recorded in the audit trail: "log all choices".
 *
 * `force` reopens it from the Beta chip in the header, for anybody who wants
 * to read it again. */
async function showBetaNotice(force = false) {
  let n;
  try { n = await api("/api/beta"); } catch (e) { return; }
  if (!n || !n.version) return;
  const key = "gaius.beta";
  const seen = `${sessionToken()}|${n.version}`;
  if (!force) {
    try { if (localStorage.getItem(key) === seen) return; } catch (e) {}
  }
  document.getElementById("betaVeil")?.remove();

  const before = document.activeElement;
  const veil = document.createElement("div");
  veil.id = "betaVeil";
  veil.className = "confirm-veil";
  veil.innerHTML = `
    <div class="confirm-card beta-card" role="dialog" aria-modal="true"
         aria-labelledby="betaTitle" aria-describedby="betaLead" tabindex="-1">
      <h2 id="betaTitle">${esc(n.title)}</h2>
      <p id="betaLead">${esc(n.lead)}</p>
      <ul class="beta-points">${n.points.map((p) =>
        `<li><b>${esc(p.head)}</b> ${esc(p.body)}</li>`).join("")}</ul>
      <p class="small">${esc(n.data)}</p>
      <div class="confirm-actions">
        <button class="btn" id="betaOk" type="button">${esc(n.button)}</button>
      </div>
      <p class="small muted" style="margin:8px 0 0">${esc(n.recorded)}</p>
    </div>`;
  document.body.appendChild(veil);

  const card = veil.querySelector(".beta-card");
  const ok = document.getElementById("betaOk");
  // Focus the dialog itself rather than the button, so a screen reader reads
  // the title and the notice before the one thing there is to press.
  card.focus();
  // Tab stays inside the notice while it is open. There is one control, so
  // Tab and Shift-Tab both land on it.
  const trap = (e) => {
    if (e.key === "Tab") { e.preventDefault(); ok.focus(); }
  };
  veil.addEventListener("keydown", trap);

  ok.onclick = async () => {
    ok.disabled = true;
    try { await post("/api/beta/acknowledge", { version: n.version }); }
    catch (e) { /* read is read; a failed log write does not stop anyone */ }
    try { localStorage.setItem(key, seen); } catch (e) {}
    veil.remove();
    if (before && before.focus) before.focus();
  };
}
window.showBetaNotice = showBetaNotice;
{
  const chip = document.getElementById("betaChip");
  if (chip) chip.onclick = () => showBetaNotice(true);
}

window.signInAs = async (id, name, title) => {
  if (!id) return;
  S.user = id;
  S.actorName = name || "";
  S.actorTitle = title || "";
  window.SCDES_NAME = S.actorName;
  window.SCDES_TITLE = S.actorTitle;
  window.SCDES_USER = id;
  await refreshState();
  await refreshFramework();

  /* First thing after signing in is the 60-second welcome, then the Framework
     screen — not the Vision screen. The order is the message: nothing downstream
     means anything until the framework is in. */
  const land = () => {
    // The seven-step lifecycle. Someone arriving needs to see the whole path
    // before being asked to walk the first step of it — what Govern is for only
    // makes sense next to the six steps that depend on it. The Continue button
    // at the bottom of that page is the way through to the Framework.
    go("home");
    const who = (S.state && S.state.actor) || {};
    toast(`Signed in as ${who.name || name || id}` +
          (who.title ? ` · ${who.title}` : ""));
  };

  /* The 60-second welcome no longer plays by itself. Brett's order after the
     code (Oct 2026) is the disclaimer, then — on first use — the walkthrough;
     the welcome played on top of both, and again after every sign-in because
     signing out forgot it had been seen. It stays one click away: "Watch the
     welcome" on Home, and in the help panel. */
  land();
  // Signed in now: the first-use tour may be offered once the disclaimer is
  // done (see the end of this file).
  if (window.offerTourSoon) window.offerTourSoon();
  // Anything kept from a session that ended, for this same person and
  // organization, goes now.
  const sent = await flushOutbox();
  if (sent) toast(`${sent} change${sent === 1 ? "" : "s"} kept from before you signed in again ${sent === 1 ? "was" : "were"} saved.`);
};

(async () => {
  window.SCDES_USER = S.user;
  // Build the launcher first and independently: if the main app fails to
  // load, the agency picker should still work rather than open blank.
  try {
    if (window.initLauncher) await window.initLauncher();
  } catch (err) {
    console.error("launcher failed to initialize", err);
  }
  // Light/dark must work even if the launcher above threw. Idempotent, so this
  // is a no-op when initLauncher already wired it.
  if (window.initColorMode) window.initColorMode();
  await refreshState();
  await refreshFramework();
  // Land on the framework unless one is adopted — the gate decides the door.
  go("home");

  /* Only now is the shell safe to show. refreshState() supplies the tester and
     subscription flags, refreshFramework() supplies the gate, and go() paints
     the rail from both — before all three have run, every lock in the interface
     is simply absent.

     Placed after them rather than in a `finally`, on purpose: if the boot
     throws, the veil stays and nobody gets a half-locked application. Failing
     closed is the only correct direction for this one. */
  document.body.classList.remove("booting");

  // Offer the tour once, and only after the launcher has been dismissed —
  // spotlighting the header while the map covers it would explain nothing.
  // Declining it is no longer a dead end: the help button in the corner has it.
  //
  // And only once they are registered and signed in (BUG-F379A222): on a first
  // visit the map is hidden while the welcome and "Register your work email"
  // cards are up, and the tour started over them — explaining an application
  // the person had not yet been let into. Checked on a timer as well as on
  // clicks, because the code verifies itself on the sixth digit without one.
  if (window.startTour && window.tourSeen && !window.tourSeen()) {
    const signedIn = () => {
      try {
        const saved = JSON.parse(localStorage.getItem("scdes.registration") || "{}") || {};
        return !!(saved.verified && saved.agency);
      } catch (e) { return false; }
    };
    // Not over the disclaimer either (Brett: the disclaimer first, then the
    // walkthrough), nor over the home page or a View as session.
    const covered = () => ["#launcher", "#onboard", "#welcome", "#home", "#betaVeil"].some((sel) => {
      const n = $(sel);
      return n && !n.hidden;
    }) || document.body.classList.contains("launcher-open")
      || !!(S.state && S.state.impersonating);
    // First use means first use for the person, not for this browser: the
    // server remembers it (app/firstuse.py), so a new laptop does not replay it.
    const seenByThem = () => !!(S.state && S.state.tour_seen);
    // The disclaimer comes first: it is fetched after sign-in, so its veil may
    // not exist yet when the map closes. Wait until this session has
    // acknowledged it (showBetaNotice records that against the session).
    const disclaimerDone = () => {
      const token = sessionToken();
      if (!token) return true;
      try { return (localStorage.getItem("gaius.beta") || "").startsWith(token + "|"); }
      catch (e) { return true; }
    };
    let timer = null;
    let offered = false;
    const offer = () => {
      if (offered || !signedIn() || covered() || !disclaimerDone()) return;    // not in yet; wait
      offered = true;
      document.removeEventListener("click", offer);
      clearInterval(timer);
      if (seenByThem()) {
        try { localStorage.setItem("scdes.tour", "seen"); } catch (e) {}
        return;
      }
      setTimeout(() => {
        if (!signedIn() || covered() || seenByThem()) return;
        window.startTour(true);
        post("/api/me/tour-seen", {}).catch(() => {});
        if (S.state) S.state.tour_seen = true;
      }, 400);
    };
    document.addEventListener("click", offer);
    // The timer runs only once somebody is signed in — from here on a
    // reload, or from signInAs after a code — and stops once the tour is
    // offered. It used to tick every second for every visitor, forever,
    // including on the home page where there is nothing to offer.
    const soon = () => { if (!timer && !offered) timer = setInterval(offer, 1000); };
    window.offerTourSoon = soon;
    if (signedIn()) soon();
    offer();
  }
})();


