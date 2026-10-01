/* Does Module One work as a screen, not just as an API?

   The module adapts, and the adaptation is the product: answer 1.4 and the
   offices you do not have stop being mentioned. That is a claim about what a
   person sees after clicking, which only a rendered DOM can settle.

   So this walks it: opens the builder, opens a step, answers a matrix, then
   re-opens the step that depends on it and checks the options actually changed.
   It also checks the four rules the spec is firm about — nothing disabled,
   "we don't know" everywhere, a gap gets an owner, and no other organization is
   named anywhere on screen.

   Usage:  node tools/check_builder_ui.js       (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

/* This walk is destructive by design — it blanks answers so its assertions
   mean something — so it may only run where there is nothing to lose. */
const HARNESS_AGENCY = "gaius.harness";
const HARNESS_EMAIL = "walk@harness.gaius.test";

async function demandScratchContainer() {
  const url = `${BASE}/api/whose-container?email=${encodeURIComponent(HARNESS_EMAIL)}`;
  let found = await (await fetch(url)).json();
  if (!found.safe_to_overwrite) {
    // Not registered yet on this server: join the container, then re-ask.
    await fetch(`${BASE}/api/agency/register`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agency: HARNESS_AGENCY, name: "Automated walk",
        title: "Harness", email: HARNESS_EMAIL,
        phone: "(843) 555 0100", attested: true }) });
    found = await (await fetch(url)).json();
  }
  if (!found.safe_to_overwrite) {
    console.error(`\n  Refusing to run.\n`
      + `  Writes would land in: ${found.agency}\n`
      + `  against: ${BASE}\n\n`
      + `  This walk blanks answers, so it only runs in the container kept\n`
      + `  for the checks. See tools/harness_identity.py.\n`);
    process.exit(2);
  }
  return found;
}

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

async function boot() {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    /* The harness's own address, in the harness's own container.

       This was `lokesh@iiac.ai`, a real working address, which the server
       resolves — correctly — to `iia.test`. That is the client's container.
       The walk below blanks answers to make itself deterministic, so on
       staging it blanked his. See tools/harness_identity.py. */
    value: store({ "scdes.registration": JSON.stringify(
      { email: HARNESS_EMAIL, name: "Automated walk", verified: true,
        state: "SC", agency: HARNESS_AGENCY, abbrev: "HARNESS" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage",
    { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  for (const f of ["bugs.js", "dock.js", "guide.js", "notify.js", "onboard.js",
                   "welcome.js", "tour.js", "launcher.js", "speech.js",
                   "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  await new Promise((r) => setTimeout(r, 800));
  return { window, errors };
}

const settle = (ms = 700) => new Promise((r) => setTimeout(r, ms));

/* Wait for a condition rather than for a duration.

   A fixed sleep is calibrated against whichever machine it was written on.
   Every timing here passed locally and six of them failed against staging,
   where the same redraw costs a network round trip. */
async function until(condition, ms = 12000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    // Awaited, so an async condition is not just a truthy Promise.
    try { if (await condition()) return true; } catch { /* not there yet */ }
    await settle(150);
  }
  return false;
}

async function main() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(46)} ${detail}`);
    if (!ok) failures.push(label);
  };

  const container = await demandScratchContainer();
  console.log(`writing into: ${container.agency}`);

  const { window, errors } = await boot();
  const doc = window.document;

  /* Start from a clean slate so the walk is deterministic. Every key the walk
     touches, including the ones it only reads: 5.3's pre-fills were left over
     from the previous run, so "every level arrives pre-filled" was passing on
     saved answers rather than on the defaults it claims to check. */
  for (const key of ["org.functions", "org.size", "org.delegated",
                     "who.consulted", "who.shape", "org.kind",
                     "scope.arbiter", "risk.factors", "risk.levels",
                     "risk.tiers",
                     /* The keys the later blocks write, cleared for the same
                        reason as the rest: "5.5 arrives with the
                        recommendations ticked" was failing on an answer this
                        walk itself had stored on its previous run, and a
                        pre-check is correctly skipped once there is one. */
                     "risk.revisit", "proc.added_ai", "who.without",
                     "watch.publish", "bad.tell", "scope.covered",
                     "floor.disclose_who", "words.03", "who.signs"]) {
    await window.fetch("/api/versions/answer?user=sean.ot&email=walk%40harness.gaius.test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value: "" }) });
  }

  console.log("the overview");
  await window.go("framework");
  await settle(1400);
  const view = doc.getElementById("view");
  check("the module's own title", /Build Your AI Governance Framework/
    .test(view.textContent));
  check("the steps are listed",
    doc.querySelectorAll(".fb-section").length >= 12,
    `${doc.querySelectorAll(".fb-section").length} rows`);
  check("orientation is marked read-this-first",
    /read this first/.test(view.textContent));
  /* Eleven numbered steps and the assembly at the end, all present. Whatever
     the module says is still pending is listed rather than dropped — a section
     that says "not yet" is honest in a way a silently missing one is not.
     Module One is whole now, so the pending count is zero and the claim is
     checked against what the API reports rather than against a fixed number
     that would quietly stop meaning anything. */
  const overview = await (await window.fetch(
    "/api/module?user=sean.ot&email=walk%40harness.gaius.test")).json();
  const built = doc.querySelectorAll(".fb-section:not(.pending)").length;
  const waiting = doc.querySelectorAll(".fb-section.pending").length;
  // Twelve numbered steps and the assembly. Step 11 — "why this framework
  // exists" — was added after the client compared our output with a real
  // adopted framework: it produces the Purpose and Scope pages.
  check("every step is on screen", built + waiting === 13,
    `${built} built, ${waiting} pending`);
  check("and whatever is still pending is shown, not hidden",
    waiting === (overview.pending || []).length,
    `${(overview.pending || []).length} pending in the module`);
  check("the document-building panel is there",
    !!doc.querySelector(".fb-parts"),
    `${doc.querySelectorAll(".fb-part").length} parts`);

  console.log("\nstep 00 asks nothing and still goes somewhere");
  await window.fbOpenStep("00");
  await settle();
  check("no questions", doc.querySelectorAll(".fb-q").length === 0);
  check("but there is a way onward", !!doc.getElementById("fbNext"));
  check("the asset analogy is on the page",
    /truck|asset/i.test(doc.getElementById("view").textContent));

  console.log("\nstep 01 — answering the matrix that drives everything");
  await window.fbOpenStep("01");
  await settle();
  const matrix = doc.querySelector('.fb-q[data-key="org.functions"] .fb-matrix');
  check("1.4 renders as a matrix", !!matrix,
    matrix ? `${matrix.querySelectorAll(".fb-mrow").length - 1} rows` : "missing");
  /* There are two ways out of a question you cannot answer, and which one you
     get depends on whether there is a list to put it in. Where he wrote a
     response set, "Not sure" is one of the choices; where the question is a
     bare text field or a matrix, it is a tick-box underneath. Counting only
     tick-boxes counted the second kind and missed the first. */
  const escapes = [...doc.querySelectorAll(".fb-q")].filter((q) =>
    q.querySelector(".fb-unknown")
    || q.querySelector('input[value="unknown"]'));
  const asked = doc.querySelectorAll(".fb-q").length;
  check("every question offers a way out except 1.8",
    escapes.length === asked - 1, `${escapes.length} of ${asked}`);
  // Where he wrote the wording himself it must be his, not ours.
  const hisWords = doc.querySelector(
    '.fb-q[data-key="org.delegated"] input[value="unknown"]');
  check("1.5 says “Not sure”, which is his wording", !!hisWords
    && hisWords.closest(".fb-card").querySelector("b")
         .textContent.trim() === "Not sure",
    hisWords ? hisWords.closest(".fb-card").querySelector("b").textContent : "");

  // A small district: no cybersecurity, no HR, no communications.
  const none = { legal: "contracted", it: "part", security: "none",
                 purchasing: "part", records: "part", finance: "part",
                 hr: "none", comms: "none" };
  for (const [row, value] of Object.entries(none)) {
    const radio = doc.querySelector(
      `input[name="m-org--functions-${row}"][value="${value}"]`);
    if (radio) { radio.checked = true; }
  }
  const anyRadio = doc.querySelector('input[name="m-org--functions-legal"]');
  anyRadio.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(1200);
  check("the matrix saved",
    doc.querySelector('.fb-q[data-key="org.functions"]')
       .classList.contains("answered"));

  console.log("\nand step 04 adapts to it");
  await window.fbOpenStep("04");
  await settle(900);
  const consulted = doc.querySelector('.fb-q[data-key="who.consulted"]');
  const offered = [...consulted.querySelectorAll("input[type=checkbox]")]
    .map((i) => i.value);
  check("no cybersecurity office is offered", !offered.includes("security"),
    offered.join(", ").slice(0, 52));
  check("no HR, no communications",
    !offered.includes("hr") && !offered.includes("comms"));
  check("the offices it does have are", offered.includes("it")
    && offered.includes("legal"));
  const missing = doc.querySelector('.fb-q[data-key="who.missing"]');
  check("and it asks what happens instead", !!missing,
    missing ? `${missing.querySelectorAll(".fb-mrow").length - 1} missing offices`
            : "not asked");

  console.log("\nnothing is ever disabled");
  const shape = doc.querySelector('.fb-q[data-key="who.shape"]');
  const cards = [...shape.querySelectorAll("input[type=radio]")];
  // "Not sure" rides in the same list, so it is not one of the four shapes.
  const shapes = cards.filter((c) => c.value !== "unknown");
  check("all four shapes selectable", shapes.length === 4
    && shapes.every((c) => !c.disabled));
  check("one is marked recommended",
    shape.querySelectorAll(".fb-rec").length === 1,
    shape.querySelector(".fb-rec")
      ? shape.querySelector(".fb-rec").closest(".fb-card")
          .querySelector("b").textContent : "none");

  // Pick heavier than recommended: one line, then accepted.
  const council = cards.find((c) => c.value === "council");
  council.checked = true;
  council.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(900);
  const csq = shape.querySelector(".fb-consequence");
  check("a heavier shape gets one line of consequence",
    !!csq && !csq.hidden, (csq.textContent || "").slice(0, 50));
  check("and the answer was still recorded",
    shape.classList.contains("answered"));

  /* His "Not sure" is an ordinary radio in the response set, so nothing about
     it looks special to the person clicking. It has to behave like the
     tick-box does: open the owner field and land in the gap list. */
  console.log("\nthe unknown option behaves like the tick-box");
  const notSure = cards.find((c) => c.value === "unknown");
  // He wrote no "Not sure" at 4.1, so the generic one is appended instead.
  check("4.1 gets the generic, since he wrote none there", !!notSure
    && notSure.closest(".fb-card").querySelector("b")
         .textContent.trim() === "We don't know",
    notSure ? notSure.closest(".fb-card").querySelector("b").textContent : "");
  notSure.checked = true;
  notSure.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(900);
  check("picking it opens the owner field",
    !shape.querySelector(".fb-owner").hidden);
  const shapeOwner = shape.querySelector(".fb-owner input[type=text]");
  shapeOwner.value = "The board chair";
  shapeOwner.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(900);
  const early = await (await window.fetch(
    "/api/module?user=sean.ot&email=walk%40harness.gaius.test")).json();
  const shapeGap = (early.gaps || []).find((g) => g.key === "who.shape");
  check("and it is recorded as a gap, owner and all",
    !!shapeGap && shapeGap.owner === "The board chair",
    shapeGap ? `${shapeGap.number} → ${shapeGap.owner}` : "not recorded");
  // Put the real answer back so the rest of the walk sees a decided shape.
  council.checked = true;
  council.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(900);

  console.log("\n“we don't know” becomes a gap with an owner");
  const arb = await (async () => {
    await window.fbOpenStep("03");
    await settle(800);
    return doc.querySelector('.fb-q[data-key="scope.arbiter"]');
  })();
  const unk = arb.querySelector(".fb-unknown input[type=checkbox]");
  unk.checked = true;
  unk.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(800);
  check("the owner field appears", !arb.querySelector(".fb-owner").hidden);
  /* The owner field specifically, not the first text input on the question.
     Picking the first put the owner's name into the *answer* box — whose
     handler then cleared the "we don't know", which is correct behavior and
     made this look like the gap was not being recorded. */
  const ownerField = arb.querySelector(".fb-owner input[type=text]");
  check("and it is not the answer box",
    ownerField.id.startsWith("ownin-"), ownerField.id);
  ownerField.value = "Town Attorney";
  ownerField.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(900);
  const state = await (await window.fetch(
    "/api/module?user=sean.ot&email=walk%40harness.gaius.test")).json();
  const gap = (state.gaps || []).find((g) => g.key === "scope.arbiter");
  check("it is recorded as a gap", !!gap, gap ? gap.number : "not recorded");
  check("with the owner against it", gap && gap.owner === "Town Attorney",
    gap ? gap.owner : "");
  check("so it does not need one", gap && gap.needs_owner === false);

  /* Step 05 is where the module stops describing the organization and starts
     asking it to decide something. Two claims worth a real DOM: the levels of
     scrutiny they picked are the levels they are then asked about, and the
     pre-fills arrive written in the structure they chose at 4.1. */
  console.log("\nstep 05 — the levels of scrutiny follow their own answers");
  await window.fbOpenStep("05");
  await settle(900);
  const factors = doc.querySelector('.fb-q[data-key="risk.factors"]');
  const rowCount = factors.querySelectorAll(".fb-mrow").length - 1;
  check("the factors are asked one row at a time", rowCount === 7,
    `${rowCount} factors — no delegated program, so it isn't offered`);
  check("nothing on screen calls it a matrix",
    !/matrix/i.test(doc.getElementById("view").textContent));

  const levels = doc.querySelector('.fb-q[data-key="risk.levels"]');
  const three = levels.querySelector('input[value="three"]');
  check("three levels is the standing recommendation",
    !!levels.querySelector(".fb-rec")
    && levels.querySelector(".fb-rec").closest(".fb-card")
        .querySelector("input").value === "three");
  const tierNames = () => [...doc.querySelectorAll(
    '.fb-q[data-key="risk.tiers"] .fb-tier > h4')]
    .map((h) => h.textContent.trim()).join(" · ");

  const two = levels.querySelector('input[value="two"]');
  two.checked = true;
  two.dispatchEvent(new window.Event("change", { bubbles: true }));
  await until(() => tierNames() === "Routine · Elevated");
  check("choosing two re-asks 5.3 about exactly those two",
    tierNames() === "Routine · Elevated", tierNames());

  three.checked = true;
  three.dispatchEvent(new window.Event("change", { bubbles: true }));
  await until(() => tierNames() === "Low · Moderate · High");
  check("and choosing three re-asks it about three",
    tierNames() === "Low · Moderate · High", tierNames());

  let tiers = doc.querySelector('.fb-q[data-key="risk.tiers"]');

  const filled = [...tiers.querySelectorAll(".fb-tfield")];
  check("every level arrives pre-filled, not blank",
    filled.length > 0 && filled.every((f) => f.value.trim()),
    `${filled.filter((f) => f.value.trim()).length} of ${filled.length}`);
  // 4.1 was answered "a formal council" above, so the pre-fills should say so.
  check("and in the structure they chose at 4.1",
    filled.some((f) => /council/i.test(f.value)),
    (filled.find((f) => /council/i.test(f.value)) || {}).value || "no mention");
  const picked = [...tiers.querySelectorAll("input[type=radio][data-tier]")]
    .filter((r) => r.checked);
  check("the choices are pre-filled too", picked.length === 6,
    `${picked.length} of 6 — two questions across three levels`);

  /* Editing one field must save the whole grid, pre-fills included. Saving
     only what they touched would produce a framework whose levels of scrutiny
     are blank — when the screen they approved plainly had words in every box. */
  filled[0].value = "The program manager and the council";
  filled[0].dispatchEvent(new window.Event("change", { bubbles: true }));
  const held = async () => {
    const saved = await (await window.fetch(
      "/api/versions?user=sean.ot&email=walk%40harness.gaius.test")).json();
    const grid = (saved.working || {})["risk.tiers"];
    return grid && (grid.value !== undefined ? grid.value : grid);
  };
  let inner = null;
  await until(async () => { inner = await held(); return !!inner; });
  inner = await held();
  check("editing one box saves the whole grid",
    !!inner && Object.keys(inner).length === 3,
    inner ? Object.keys(inner).join(", ") : "nothing saved");
  check("including the levels they never touched",
    !!inner && !!(inner.high || {}).written,
    inner && inner.high ? (inner.high.written || "").slice(0, 40) : "");

  // And it comes back the way they left it, not back to the pre-fill.
  await window.fbOpenStep("04");
  await until(() => !!doc.querySelector('.fb-q[data-key="who.shape"]'));
  await window.fbOpenStep("05");
  const again = () => doc.querySelector(
    '.fb-q[data-key="risk.tiers"] .fb-tfield');
  await until(() => again()
    && again().value === "The program manager and the council");
  check("and it is still there when they come back",
    !!again() && again().value === "The program manager and the council",
    again() ? again().value : "not rendered");

  /* Step 06 is the one place the module is directive, and the client's
     instruction is that it "should say so out loud rather than sneaking it
     in". That is a claim about what the screen looks like. */
  console.log("\nstep 06 — the floor says it is the floor");
  await window.fbOpenStep("06");
  await until(() => doc.querySelectorAll(".fb-floor").length === 9);
  const floors = [...doc.querySelectorAll(".fb-floor")];
  check("eight floors plus the optional block", floors.length === 9,
    `${floors.length} blocks`);
  check("each states the rule and why it exists",
    floors.every((f) => f.querySelector("h2") && f.querySelector(".intro")));
  const badges = floors.map((f) => (f.querySelector(".fb-floor-badge") || {})
    .textContent || "");
  check("and is badged required, not suggested",
    badges.filter((b) => /required/i.test(b)).length === 8,
    badges.filter((b) => /required/i.test(b)).length + " required");
  check("accessibility is badged as law",
    !!doc.querySelector(".fb-floor-badge.law"));
  check("and names the standard, not just the idea",
    /WCAG 2\.1 Level AA/.test(doc.getElementById("view").textContent));

  // 6.3b is the only question in the module with no way out.
  const reach = doc.querySelector('.fb-q[data-key="floor.reach_human"]');
  check("reaching a person has no opt-out",
    !reach.querySelector(".fb-unknown"),
    "floor 3 is a promise made to the public");

  // "Who writes it, and who approves it" — one question, two boxes.
  const writes = doc.querySelector('.fb-q[data-key="floor.disclose_who"]');
  const pair = writes.querySelector(".fb-also input[type=text]");
  check("a two-part question shows both halves", !!pair,
    pair ? writes.querySelector(".fb-also span").textContent : "missing");
  writes.querySelector('input[id^="in-"]').value = "Communications Manager";
  writes.querySelector('input[id^="in-"]')
    .dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(900);
  pair.value = "The Town Attorney";
  pair.dispatchEvent(new window.Event("change", { bubbles: true }));
  const pairRecord = async () => {
    const both = await (await window.fetch(
      "/api/versions?user=sean.ot&email=walk%40harness.gaius.test")).json();
    const raw = (both.working || {})["floor.disclose_who"] || {};
    return raw.value && raw.value.value !== undefined ? raw.value : raw;
  };
  let kept = {};
  await until(async () => {
    kept = await pairRecord();
    return kept.approver === "The Town Attorney";
  });
  check("and keeps them together in one record",
    kept.approver === "The Town Attorney"
      && (kept.value === "Communications Manager"),
    JSON.stringify(kept).slice(0, 70));

  check("and it shows what comes back, and when",
    doc.querySelectorAll(".fb-when tbody tr").length === 8,
    `${doc.querySelectorAll(".fb-when tbody tr").length} obligations`);

  /* "If the pre-checked boxes are not un-selected and re-selected at least
     once by the user, it is registering as 'incomplete', but to me I answered
     all of the questions and just accepted the recommendations."

     The progress display was lying, and the export left those answers out.
     His own fix: leaving the step accepts what is on it. */
  console.log("\naccepting the recommendations counts as answering");
  await window.fbOpenStep("05");
  await until(() => !!doc.querySelector('.fb-q[data-key="risk.revisit"]'));
  const revisit = doc.querySelector('.fb-q[data-key="risk.revisit"]');
  const ticked = [...revisit.querySelectorAll("input[type=checkbox]")]
    .filter((b) => b.checked);
  check("5.5 arrives with the recommendations ticked", ticked.length >= 5,
    `${ticked.length} ticked`);
  check("and the module does not yet call it answered",
    !revisit.classList.contains("answered"),
    "nothing stored — this is the bug he found");

  /* Continue is the act of accepting them. Clicking it starts an async
     handler that commits the step and then navigates, and `click()` does not
     await either — so this waits for the destination to actually arrive
     before reading anything. Without that, step 06's render landed on top of
     whatever the next block had opened. */
  doc.getElementById("fbNext").click();
  await until(() => doc.querySelectorAll(".fb-floor").length === 9);
  await until(async () => {
    const v = await (await window.fetch("/api/versions?user=sean.ot&email="
      + encodeURIComponent(HARNESS_EMAIL))).json();
    return !!(v.working || {})["risk.revisit"];
  });
  const after55 = await (await window.fetch("/api/versions?user=sean.ot&email="
    + encodeURIComponent(HARNESS_EMAIL))).json();
  const stored55 = (after55.working || {})["risk.revisit"];
  const list55 = stored55 && (stored55.value !== undefined
    ? stored55.value : stored55);
  check("moving on records what they accepted",
    Array.isArray(list55) && list55.length >= 5,
    Array.isArray(list55) ? `${list55.length} recorded` : "nothing recorded");
  // And the pre-filled grid at 5.3 with it.
  const stored53 = (after55.working || {})["risk.tiers"];
  check("including the grid that was filled in for them", !!stored53,
    stored53 ? "5.3 recorded" : "5.3 still empty");

  /* Four tickets about the shape of a step rather than its content. None of
     them would fail a unit test, which is why they reached him. */
  console.log("\nthe step reads and moves the way he asked");
  await window.fbOpenStep("05");
  await until(() => !!doc.querySelector('.fb-q[data-key="risk.factors"]'));

  // 94687A56 — a way back, to the left of the way forward.
  const nav = [...doc.querySelectorAll(".panel .row button")]
    .map((b) => b.id).filter(Boolean);
  check("there is a Back button as well as Continue",
    nav.includes("fbPrev") && nav.includes("fbNext"), nav.join(", "));
  check("and Back comes first, as he placed it",
    nav.indexOf("fbPrev") < nav.indexOf("fbNext"));
  const backBtn = doc.getElementById("fbPrev");
  check("naming the step it returns to",
    /Back to 04/.test(backBtn.textContent), backBtn.textContent.trim());

  // 21DBEC69 — the number on the same line as the question it numbers.
  const numbered = doc.querySelector('.fb-q[data-key="risk.factors"] .fb-ask');
  check("the number sits inside the question",
    !!numbered.querySelector(".fb-qno")
    && numbered.textContent.trim().startsWith("5.1 ")
    && /5\.1 How much/.test(numbered.textContent.replace(/\s+/g, " ")),
    numbered.textContent.trim().slice(0, 40));

  // CFB51494 — context before the answers, not after them.
  const worst = doc.querySelector('.fb-q[data-key="risk.worst"]');
  const kids = [...worst.children];
  const helpAt = kids.findIndex((el) => el.classList.contains("fb-help"));
  const answersAt = kids.findIndex((el) => el.classList.contains("fb-control"));
  check("the explanation comes before the answers",
    helpAt >= 0 && answersAt >= 0 && helpAt < answersAt,
    `help at ${helpAt}, answers at ${answersAt}`);
  check("and it is the averaging note he meant",
    /averaging/i.test(worst.querySelector(".fb-help").textContent));

  // 527E2217 — Continue lands at the top. The page does not scroll; the
  // record pane does, which is why scrolling the window did nothing.
  const pane = doc.getElementById("record");
  if (pane) {
    pane.scrollTop = 900;
    await window.fbOpenStep("06");
    await until(() => doc.querySelectorAll(".fb-floor").length > 0);
    check("moving on opens the step at the top", pane.scrollTop === 0,
      `scrollTop ${pane.scrollTop}`);
  } else {
    check("moving on opens the step at the top", false, "no #record pane");
  }

  /* "Locked in only options now. Let them add their own." — four of his
     tickets. The claim is that what they type comes back as a choice they can
     see, un-tick and carry into the document, which only a real DOM settles. */
  console.log("\nthey can add a choice we didn't think of");
  await window.fbOpenStep("03");
  await until(() => !!doc.querySelector(
    '.fb-q[data-key="scope.covered"] .fb-addown'));
  const covered = doc.querySelector('.fb-q[data-key="scope.covered"]');
  check("3.1 offers a way to add one", !!covered.querySelector(".fb-addown"),
    covered.querySelector(".fb-addown span").textContent);

  const before = covered.querySelectorAll(".fb-card").length;
  const ownField = covered.querySelector('input[id^="add-"]');
  ownField.value = "Meter reading models";
  covered.querySelector('button[id^="addbtn-"]').click();
  await until(() => /Meter reading models/.test(
    (doc.querySelector('.fb-q[data-key="scope.covered"]') || {})
      .textContent || ""));

  const after = doc.querySelector('.fb-q[data-key="scope.covered"]');
  check("what they typed appears in the list",
    /Meter reading models/.test(after.textContent),
    `${after.querySelectorAll(".fb-card").length} choices, was ${before}`);
  const theirs = [...after.querySelectorAll(".fb-card input")]
    .find((i) => i.value.startsWith("custom:"));
  check("and it is ticked, because they just chose it",
    !!theirs && theirs.checked, theirs ? theirs.value : "not found");
  check("the box is empty again, ready for another",
    after.querySelector('input[id^="add-"]').value === "");

  // Un-ticking has to work, or it is a choice they can never take back.
  theirs.checked = false;
  theirs.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(900);
  const gone = await (await window.fetch(
    "/api/versions?user=sean.ot&email=" + encodeURIComponent(HARNESS_EMAIL)))
    .json();
  const stored = (gone.working || {})["scope.covered"];
  const list = stored && (stored.value !== undefined ? stored.value : stored);
  check("and they can take it back off",
    Array.isArray(list) && !list.some((v) => String(v).startsWith("custom:")),
    JSON.stringify(list));

  // 5.1 is a grid, so adding one has to produce a row they can weight.
  await window.fbOpenStep("05");
  await until(() => !!doc.querySelector(
    '.fb-q[data-key="risk.factors"] .fb-addown'));
  const riskGrid = doc.querySelector('.fb-q[data-key="risk.factors"]');
  const rowsBefore = riskGrid.querySelectorAll(".fb-mrow").length;
  riskGrid.querySelector('input[id^="add-"]').value = "Chlorine dosing";
  riskGrid.querySelector('button[id^="addbtn-"]').click();
  await until(() => /Chlorine dosing/.test(
    (doc.querySelector('.fb-q[data-key="risk.factors"]') || {})
      .textContent || ""));
  const grid = doc.querySelector('.fb-q[data-key="risk.factors"]');
  check("5.1 gains a row of their own", /Chlorine dosing/.test(grid.textContent),
    `${grid.querySelectorAll(".fb-mrow").length} rows, was ${rowsBefore}`);
  const weights = [...grid.querySelectorAll("input[type=radio][data-row]")]
    .filter((r) => r.dataset.row.startsWith("custom:"));
  check("with the same weights as every other factor", weights.length === 3,
    `${weights.length} choices against it`);
  check("and none chosen for them", !weights.some((w) => w.checked));

  /* The assembly step reads the whole framework back before anything is
     signed. The claim that earns trust is the contradiction check — "it proves
     something read the answers" — so it is provoked deliberately rather than
     hoped for. */
  console.log("\nthe review screen reads the answers back");

  // Two answers that cannot both be operated: nothing moves without them,
  // and also three things do.
  await window.fbOpenStep("04");
  await until(() => !!doc.querySelector('.fb-q[data-key="who.without"]'));
  const without = doc.querySelector('.fb-q[data-key="who.without"]');
  /* 4.6's "nothing — everything goes through the process" is exclusive now,
     on his instruction, so this pair can no longer both be ticked. Which is
     the better outcome and worth asserting: prevented at the click, not
     reported four steps later. */
  for (const value of ["free", "nothing"]) {
    const cb = without.querySelector(`input[value="${value}"]`);
    cb.checked = true;
    cb.dispatchEvent(new window.Event("change", { bubbles: true }));
    await settle(500);
  }
  const locked = [...without.querySelectorAll("input[type=checkbox]")]
    .filter((b) => b.disabled);
  check("ticking “nothing” locks the others out",
    locked.length > 0 && !without.querySelector('input[value="free"]').checked,
    `${locked.length} locked`);

  // Back to a coherent answer, then provoke a contradiction the interface
  // cannot prevent — one that spans two steps.
  const freeAgain = without.querySelector('input[value="free"]');
  freeAgain.checked = true;
  freeAgain.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(600);
  for (const [key, value] of [["risk.revisit", "vendor_change"]]) {
    await window.fetch("/api/versions/answer?user=sean.ot&email="
      + encodeURIComponent(HARNESS_EMAIL), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value: [value] }) });
  }
  await window.fetch("/api/versions/answer?user=sean.ot&email="
    + encodeURIComponent(HARNESS_EMAIL), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: "proc.added_ai", value: "nothing" }) });
  // 4.8 too, because the assembly step pre-fills who signs from it.
  const signs = doc.querySelector(
    '.fb-q[data-key="who.signs"] input[value="board"]');
  signs.checked = true;
  signs.dispatchEvent(new window.Event("change", { bubbles: true }));
  await settle(700);

  await window.fbOpenStep("—");
  await until(() => !!doc.querySelector(".fb-clash, .fb-clear"));
  check("the assembly step opens with the read-back",
    /read back/i.test(doc.getElementById("view").textContent));
  check("and it caught the contradiction",
    !!doc.querySelector(".fb-clash"),
    (doc.querySelector(".fb-clash li") || {}).textContent
      ? doc.querySelector(".fb-clash li").textContent.trim().slice(0, 58)
      : "nothing flagged");
  check("naming the questions it came from",
    /5\.5/.test((doc.querySelector(".fb-clash") || {}).textContent || "")
    && /8\.5/.test((doc.querySelector(".fb-clash") || {}).textContent || ""),
    "a clash across two steps, which no single control can prevent");

  check("the gap from earlier is still listed",
    /Town Attorney/.test((doc.querySelector(".fb-gaps") || {}).textContent
      || ""));
  check("all eight floors are accounted for",
    doc.querySelectorAll(".fb-floorlist li").length === 8,
    `${doc.querySelectorAll(".fb-floorlist li").length} listed`);
  check("every section is read back",
    doc.querySelectorAll(".fb-readback section").length === 11,
    `${doc.querySelectorAll(".fb-readback section").length} sections`);
  check("and each one is a way back into it",
    doc.querySelectorAll(".fb-readback button[data-step]").length === 11);
  /* Five fields, none of them policy: the title, who signs it and when, how
     formal it should read, where it lives, and when it comes back. The
     register choice is about the document, not about how they govern —
     "both say exactly the same thing and hold you to exactly the same
     rules". */
  /* Six since —.2c was added: how the language should read, "As written" or
     "Polished" — a choice about the wording that "changes the wording, never
     the rules", so still no policy question. */
  check("no new policy question is asked here",
    doc.querySelectorAll(".fb-q").length === 6,
    `${doc.querySelectorAll(".fb-q").length} fields — title, signer, register, language, home, review`);
  check("and the register is recommended from their own answers",
    !!doc.querySelector('.fb-q[data-key="done.register"] .fb-rec'),
    (doc.querySelector('.fb-q[data-key="done.register"] .fb-rec') || {})
      .closest ? doc.querySelector('.fb-q[data-key="done.register"] .fb-rec')
        .closest(".fb-card").querySelector("b").textContent : "none");
  check("who signs is pre-filled from what they already said",
    !!doc.querySelector('.fb-q[data-key="done.signs"] .fb-rec'));
  check("and the handoff is stated plainly, not pitched",
    /Premium Subscription/.test(doc.getElementById("view").textContent));

  // Their own paragraph, on a section that records decisions.
  await window.fbOpenStep("03");
  await until(() => !!doc.querySelector(".fb-mine textarea"));
  const mine = doc.querySelector(".fb-mine textarea");
  mine.value = "Our board asked for this in April.";
  mine.dispatchEvent(new window.Event("change", { bubbles: true }));
  await until(async () => {
    const v = await (await window.fetch(
      "/api/versions?user=sean.ot&email=walk%40harness.gaius.test")).json();
    const held = (v.working || {})["words.03"];
    return held && (held.value || held) === "Our board asked for this in April.";
  });
  await window.fbOpenStep("—");
  await until(() => !!doc.querySelector(".fb-verbatim"));
  check("their own words come back verbatim",
    /Our board asked for this in April\./.test(
      (doc.querySelector(".fb-verbatim") || {}).textContent || ""));

  /* "Allow me to erase all of my content I have built in this tenant. Lets me
     demo easily and consistently and also test from 0." — and, on being
     offered the alternative to a one-way wipe: "Great idea. Didn't know it was
     even possible."

     The round trip is the claim: keep a copy, wipe, put it back. Worth a real
     DOM because the endpoints existed for weeks with nothing calling them. */
  /* Braced. This walk is one long function and every new `const` in it has to
     dodge every name used above — three collisions in a row before this block
     was scoped, all of them found by the parser rather than by thinking. */
  {
  console.log("\nkeep a copy, start fresh, put it back");
  await window.go("framework");
  await until(() => !!doc.querySelector("#snapTake"));
  check("the panel is reachable at all", !!doc.querySelector("#snapTake"),
    "it had no interface before this");
  // The panel fills itself in from two requests, so wait for them rather
  // than reading an empty element the moment it is drawn.
  await until(() => /Would clear|nothing recorded/i.test(
    (doc.querySelector("#resetWhat") || {}).textContent || ""));
  check("and it says what starting over would clear",
    /Would clear|nothing recorded/i.test(
      doc.querySelector("#resetWhat").textContent),
    doc.querySelector("#resetWhat").textContent.slice(0, 46));

  /* Clear up after previous runs before taking another copy.
   *
   * This walk had been leaking state for weeks. It took a snapshot on every
   * run and never removed one, and an agency may hold twelve — so the
   * container filled its own quota and `take` began refusing, correctly,
   * with "You are holding 12 snapshots, which is the limit."
   *
   * That is the whole story of the failure I first wrote off as a flake: as
   * the count climbed the restore picked an arbitrary older copy and the
   * answer count did not match; once it hit twelve the take failed outright.
   * The app was right at every stage. A destructive walk that does not tidy
   * up eventually tests the cleanup it never does. */
  const snapUrl = "/api/snapshots?user=sean.ot&email="
    + encodeURIComponent(HARNESS_EMAIL);
  const forget = async (id) => window.fetch(
    "/api/snapshots/forget?user=sean.ot&email="
    + encodeURIComponent(HARNESS_EMAIL), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }) });

  const before = await (await window.fetch(snapUrl)).json();
  const leftovers = (before.snapshots || [])
    .filter((s) => (s.label || "").startsWith("Before the walk"));
  for (const old of leftovers) await forget(old.id);
  if (leftovers.length) {
    console.log(`      (cleared ${leftovers.length} copy(ies) this walk left `
      + `behind on earlier runs)`);
  }

  /* Unique per run. "Before the walk" was shared by every run ever, so
     `find` below matched whichever copy happened to be first in the list —
     an older one, taken when a different number of questions was answered.
     Finding it by label was only half the fix; the label has to identify
     this run. */
  const label = `Before the walk ${Date.now()}`;
  doc.querySelector("#snapLabel").value = label;
  doc.querySelector("#snapTake").click();
  await until(() => /Before the walk/.test(
    doc.querySelector("#snapList").textContent));
  check("a copy can be kept, and is named and dated",
    /Before the walk/.test(doc.querySelector("#snapList").textContent),
    // The panel's own error, if there is one — otherwise the date it stamped.
    (doc.querySelector("#contentErr") || {}).hidden === false
      ? "refused: " + doc.querySelector("#contentErr").textContent
      : ((doc.querySelector(".fb-snap-main i") || {}).textContent || "")
        .trim().slice(0, 40));

  /* Taking a copy needs no capacity — it destroys nothing, and it is what
     makes the wipe recoverable. Wiping still needs the authority it has
     always needed, and the panel says which rather than letting them type the
     phrase and then be refused. */
  const wipeBtn = doc.querySelector("#resetGo");
  const asOperator = wipeBtn.disabled;
  check("a copy needs no special capacity",
    /Before the walk/.test(doc.querySelector("#snapList").textContent),
    "kept as " + (asOperator ? "an operator" : "the OT"));
  if (asOperator) {
    check("and starting over says which capacity it needs",
      /Office of Technology/.test(
        doc.querySelector("#resetWhat").parentElement.textContent),
      "explained, not refused after the fact");
  } else {
    doc.querySelector("#resetPhrase").value = "start over please";
    wipeBtn.click();
    await settle(900);
    const stillThere = await (await window.fetch(
      "/api/versions?user=sean.ot&email=" + encodeURIComponent(HARNESS_EMAIL)))
      .json();
    check("the wrong confirmation clears nothing",
      Object.keys(stillThere.working || {}).length > 0,
      `${Object.keys(stillThere.working || {}).length} answers intact`);
    check("and says what to type instead",
      /START OVER/.test(doc.querySelector("#contentErr").textContent));
  }

  /* The real wipe and the restore go through the API rather than the button,
     because the button reloads the page and takes the harness with it. The
     panel above is what proves a person can reach them. */
  const answersNow = async () => {
    const v = await (await window.fetch("/api/versions?user=sean.ot&email="
      + encodeURIComponent(HARNESS_EMAIL))).json();
    return Object.keys(v.working || {}).length;
  };
  const hadBefore = await answersNow();
  await window.fetch("/api/reset?user=sean.ot&email="
    + encodeURIComponent(HARNESS_EMAIL), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: "START OVER", reason: "harness" }) });
  const wiped = await answersNow();
  check("starting over clears the answers", wiped === 0,
    `${hadBefore} → ${wiped}`);

  /* The snapshot *this run* took, found by its label rather than by being
     first in the list.

     This took `snapshots[0]` and assumed it was its own. Runs leave their
     copies behind, so on a container with history it restored somebody
     else's older snapshot — one taken when a different number of questions
     was answered — and the count check below failed. It looked like an
     intermittent fault in snapshot/restore and was a defect in this file:
     the app was putting back exactly what it had been given. */
  const kept = await (await window.fetch("/api/snapshots?user=sean.ot&email="
    + encodeURIComponent(HARNESS_EMAIL))).json();
  const mine = (kept.snapshots || []).find((s) => s.label === label);
  check("the copy survived the wipe", !!mine,
    mine ? mine.label : `gone (${(kept.snapshots || []).length} others)`);
  if (!mine) {
    console.log("      ! cannot test restore without this run's own copy");
  }
  if (mine) {
    await window.fetch("/api/snapshots/restore?user=sean.ot&email="
      + encodeURIComponent(HARNESS_EMAIL), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: mine.id }) });
    const back = await answersNow();
    check("and putting it back returns every answer", back === hadBefore,
      `${wiped} → ${back}, was ${hadBefore}`);
    // And take it away again, so the next run starts with the quota free.
    await forget(mine.id);
  }
  }

  console.log("\nnobody else's framework is on screen");
  await window.fbOpenStep("01");
  await settle(700);
  const text = doc.getElementById("view").textContent;
  for (const word of ["SCDES", "South Carolina", "Appendix", "Operations Manual"]) {
    check(`no mention of ${word}`, !text.includes(word));
  }
  check("no source quote block anywhere",
    !doc.querySelector(".fb-source"));

  console.log("\nerrors             :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));

  console.log();
  if (failures.length || errors.length) {
    console.log(`FAIL — ${failures.join("; ") || "errors on the page"}`);
    process.exit(1);
  }
  console.log("PASS — the builder walks, adapts, and refuses nothing");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });









