/* Does registering with one agency ever show you another agency's record?

   Reported: signed in as DEMO agency, the header read SCDES, the breadcrumb
   read "South Carolina Department of Environmental Services", the PermitPro
   project spine was across the top, and the Framework page listed SCDES's own
   documents. That is the one thing this application is not allowed to do.

   Signs in as each agency in turn and reports what the shell says it is.

   Usage:  node tools/check_agency_isolation.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/...
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

async function signedInAs(agencyId, query) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "lokesh@iiac.ai", verified: true, tester: true }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);
  window.console = { ...console, log: () => {},
    error: (...a) => errors.push(a.map(String).join(" ")),
    warn: (...a) => errors.push("warn: " + a.map(String).join(" ")) };
  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }

  /* Drive the real interface. `LNCH` is a const inside the eval'd script and is
     not reachable from out here — and reaching in would exercise a path no user
     takes. So this clicks the state, types the agency into the search box,
     presses Enter and accepts the NDA, exactly as a person would. */
  const doc = window.document;
  const state = doc.querySelector('.st[data-code="SC"]');
  if (state) state.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 500));

  const input = doc.getElementById("agencyPick");
  input.focus();
  input.value = query;
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
  input.dispatchEvent(new window.KeyboardEvent("keydown",
    { key: "Enter", bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));

  doc.getElementById("lnchEnter")
     .dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 1600));

  const accept = doc.getElementById("ndaYes");
  if (accept) {
    accept.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 1800));
  }
  return { window, errors };
}

function report(agencyId, expected, { window, errors }) {
  const doc = window.document;
  const text = doc.body.textContent || "";
  const short = (doc.getElementById("agencyShort") || {}).textContent || "";
  const crumb = (doc.getElementById("agencyCrumb") || {}).textContent || "";
  const spine = doc.getElementById("spine");

  console.log(`\n--- signed in as ${agencyId} ---`);
  console.log("  header shorthand :", short);
  console.log("  breadcrumb       :", crumb.slice(0, 58));
  console.log("  project spine    :",
    spine && !spine.hidden
      ? "SHOWN — " + ((doc.getElementById("projName") || {}).textContent || "")
      : "hidden");
  console.log("  view             :", doc.getElementById("viewTitle").textContent);

  // The test that matters: does another agency's name appear anywhere at all?
  const leaks = [];
  if (agencyId !== "sc.des") {
    // Joined, not concatenated: "SCDE" + "South Carolina…" reads as "SCDES"
    // across the seam and reported a leak that was not there.
    if (/\bSCDES\b/.test(short + " | " + crumb))
      leaks.push("SCDES in the header");
    if (/PermitPro/.test(text)) leaks.push("PermitPro (SCDES's project)");
    if (/Department of Environmental Services/.test(text))
      leaks.push("SCDES's full name");
    if (/SCDES_AI_Governance_Framework/.test(text))
      leaks.push("SCDES's framework documents");
  }
  console.log("  cross-agency leak:", leaks.length ? "YES — " + leaks.join(", ")
                                                   : "none");
  if (errors.length) console.log("  errors           :", errors.join(" | "));
  return leaks.length === 0;
}

/* The room built from the corpus owner's own documents. A non-owner must be
   told it is not theirs; the owner must see it. This replaced a check for
   "PermitPro" on the landing page, which came from the project strip that
   was retired — its absence said nothing about over-blocking. */
async function agencyRoom(window) {
  await window.go("agency");
  await new Promise((r) => setTimeout(r, 1500));
  return (window.document.getElementById("view") || {}).textContent || "";
}

async function main() {
  console.log("base:", BASE);
  let clean = true;
  for (const [id, short, query] of [["iia.test", "DEMO", "DEMO"],
                                    ["sc.ed", "SCDE", "Department of Education"]]) {
    const who = await signedInAs(id, query);
    clean = report(id, short, who) && clean;
    const room = await agencyRoom(who.window);
    const kept = /Nothing here belongs to you yet/.test(room) &&
      !/Environmental Services|SCDES_AI_Governance/.test(room);
    console.log("  owner's room      :", kept ? "not theirs, and says so" : "LEAK — " + room.slice(0, 80));
    clean = kept && clean;
  }
  // Choosing the owner organization is a claim, not proof. Without a session
  // code for that mailbox the server serves this browser as nobody in
  // particular, so the room must stay shut — that is the fail-closed rule
  // doing its job. That a proven owner is NOT over-blocked is asserted in
  // tests/test_isolation.py, where the organization can be bound for real.
  const owner = await signedInAs("sc.des", "Department of Environmental Services");
  report("sc.des", "SCDES", owner);
  const room = await agencyRoom(owner.window);
  const ownerOk = /Nothing here belongs to you yet/.test(room);
  console.log("  unproven claim to the owner:", ownerOk ? "shut until membership is proven"
                                                        : "OPEN without proof — " + room.slice(0, 80));

  console.log(`\n${clean && ownerOk ? "PASS" : "FAIL"}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
