/* Does the vendor registry work as a screen?

   The client: "the vendor registry; Module will contain a list of vendors,
   costs, and use case potential."

   Three things this asserts that a unit test cannot:

     1. It is reachable by a person. Working endpoints with no interface is
        how the reset button hid for weeks.
     2. The checkboxes that produce every finding — 8.3's required terms, and
        which holdings a vendor can see — can actually be ticked in a browser.
        The data register shipped with that field settable only over the API,
        which made its whole point unreachable.
     3. It says what it cannot do. A cost that cannot honestly be annualized
        is counted separately rather than folded into the total.

   Needs the subscription on:
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_vendors_ui.js
*/

const { harnessSession } = require("./_jsdom_boot");
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

const HARNESS_AGENCY = "gaius.harness";
const HARNESS_EMAIL = "walk@harness.gaius.test";

async function demandScratchContainer() {
  const url = `${BASE}/api/whose-container?email=${encodeURIComponent(HARNESS_EMAIL)}`;
  let found = await (await fetch(url)).json();
  if (!found.safe_to_overwrite) {
    await fetch(`${BASE}/api/agency/register`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agency: HARNESS_AGENCY, name: "Automated walk",
        title: "Harness", email: HARNESS_EMAIL,
        phone: "(843) 555 0100", attested: true }) });
    found = await (await fetch(url)).json();
  }
  if (!found.safe_to_overwrite) {
    console.error(`\n  Refusing to run — writes would land in ${found.agency}.\n`);
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
    value: store({ "scdes.registration": JSON.stringify(
      { email: HARNESS_EMAIL, name: "Automated walk", verified: true,
        state: "SC", agency: HARNESS_AGENCY, abbrev: "HARNESS" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government",
      // Signed in for real: changes need a proven session now.
      "scdes.session": await harnessSession() }), writable: true });
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

const settle = (ms = 500) => new Promise((r) => setTimeout(r, ms));

async function until(condition, ms = 12000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try { if (await condition()) return true; } catch { /* not yet */ }
    await settle(150);
  }
  return false;
}

async function main() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(48)} ${detail}`);
    if (!ok) failures.push(label);
  };

  await demandScratchContainer();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");

  const auth = `user=sean.ot&email=${encodeURIComponent(HARNESS_EMAIL)}`;
  // With the harness's own sign-in: changes need a proven session now.
  const post = (p, body) => window.fetch(`${p}?${auth}`, {
    method: "POST", headers: { "Content-Type": "application/json",
      "X-GAIUS-Session": window.localStorage.getItem("scdes.session") || "" },
    body: JSON.stringify(body) });
  const get = async (p) => (await window.fetch(`${p}?${auth}`)).json();

  // Start clean, so counts mean something.
  const before = await get("/api/vendors");
  if (before.available === false) {
    console.error("\n  The subscription is off, so there is nothing to walk.");
    console.error("  Set IIA_SUBSCRIPTION=1 on the server and try again.\n");
    process.exit(2);
  }
  for (const row of before.vendors || []) {
    await post("/api/vendors/forget", { id: row.id });
  }
  for (const row of (await get("/api/holdings")).holdings || []) {
    await post("/api/holdings/forget", { id: row.id });
  }

  // The framework answers the findings are checked against.
  await post("/api/versions/answer",
    { key: "proc.terms", value: ["disclose", "breach", "accessibility"] });
  await post("/api/versions/answer", { key: "proc.full_cost", value: "yes" });
  await post("/api/versions/answer",
    { key: "proc.cost_parts", value: ["licence", "exit"] });
  await post("/api/versions/answer", { key: "data.never", value: ["personal"] });
  await post("/api/versions/answer", { key: "floor.access_docs", value: "yes" });
  // One holding, so a vendor can be tied to what it can see.
  await post("/api/holdings", { name: "Permit system", reachable: "api",
    owner: "The Permitting Manager", sensitive: ["personal"] });

  console.log("the module is reachable by a person");
  const rail = [...doc.querySelectorAll(".rail-item")].map((b) => b.dataset.view);
  check("there is a rail entry for it", rail.includes("vendors"));

  await window.go("vendors");
  await until(() => /Who you buy from/.test(said()));
  check("the screen opens", /Who you buy from/.test(said()));
  check("and says what a vendor entry is",
    /One entry per supplier relationship/.test(said()));

  console.log("\nrecording one");
  const type = (id, value) => { doc.querySelector(`#${id}`).value = value; };
  type("vn-name", "Northbridge Software");
  type("vn-product", "CaseNote");
  type("vn-what_for", "Summarizing inspection reports for the weekly review");
  type("vn-could_also", "Drafting letters, and searching across old reports");
  type("vn-owner", "The Permitting Manager");
  type("vn-amount", "$41,500");
  type("vn-status", "in_use");
  type("vn-basis", "year");
  type("vn-criticality", "low");
  type("vn-facing", "public");
  type("vn-training", "yes");
  type("vn-accessibility", "unknown");
  // One of their required terms, marked absent on this agreement.
  const breach = doc.querySelector(
    'input[data-key="breach"][value="absent"]');
  if (breach) breach.checked = true;
  check("each term is answered Present / Absent / Not asked", !!breach);
  doc.querySelector("#vnSave").click();
  await until(() => /Northbridge Software/.test(
    doc.querySelector(".vr-table")?.textContent || ""));
  const table = () => doc.querySelector(".vr-table").textContent
    .replace(/\s+/g, " ");
  check("it appears in the registry", /Northbridge Software/.test(table()));
  check("a price typed by a person survives", /\$41,500/.test(table()),
    "\"$41,500\" is what somebody writes in a box");
  check("no tier is shown — the spec retires it", !/Tier \d/.test(said()));

  console.log("\nwhat the registry found");
  const flags = () => (doc.querySelector(".vr-flags") || {}).textContent || "";
  check("a term they require, marked absent, is flagged",
    /You require this term in every agreement/.test(flags()));
  check("accessibility documentation they require and nobody asked for",
    /Nobody asked for it/.test(flags()), "Floor 4, their own answer");
  check("using their information to improve the product is flagged",
    /use your information to improve their product/.test(flags()));

  console.log("\nthe join with the data register");
  const holdingBox = doc.querySelector('[name="vn-holdings"]');
  check("the holdings from the data register are offered", !!holdingBox,
    holdingBox ? "" : "no way to say what a vendor can see");
  doc.querySelector("[data-vedit]").click();
  await settle(400);
  const tie = doc.querySelector('[name="vn-holdings"]');
  if (tie) {
    tie.checked = true;
    doc.querySelector("#vnSave").click();
    await until(() => /7\.1/.test(flags()));
  }
  check("tying a vendor to a sensitive holding is flagged",
    /7\.1/.test(flags()),
    flags().replace(/\s+/g, " ").match(/Northbridge[^·]{0,70}/)?.[0] || "");
  check("and it names the holding", /Permit system/.test(flags()));
  // The live defect: a saved vendor would not open a second time.
  doc.querySelector("[data-vedit]").click();
  await settle(400);
  check("a saved vendor opens for editing a second time",
    doc.querySelector("#vn-name")?.value === "Northbridge Software");
  check("and its absent term is still marked",
    !!doc.querySelector('input[data-key="breach"][value="absent"]:checked'));

  console.log("\na change the vendor made");
  check("the edit form has a place to record one", !!doc.querySelector("#vc-what")
    && /Changes this vendor made/.test(doc.querySelector("#vnForm")?.textContent || ""));
  doc.querySelector("#vcGo").click();
  await settle(200);
  check("with no words it asks for them", !doc.querySelector("#vcErr").hidden);
  doc.querySelector("#vc-what").value = "They switched the summarizer to a new version overnight.";
  doc.querySelector("#vc-nottold").checked = true;
  doc.querySelector("#vc-nottold").dispatchEvent(new window.Event("change"));
  check("not told disables the date", doc.querySelector("#vc-told").disabled);
  doc.querySelector("#vcGo").click();
  check("it is recorded, in their words", await until(() =>
    /switched the summarizer/.test(doc.querySelector("#vnForm")?.textContent || "")));
  check("and says they did not tell us", /we were not told/.test(doc.querySelector("#vnForm")?.textContent || ""));
  check("and the result is announced", /Recorded/.test(doc.querySelector("#vcSaid")?.textContent || ""));

  console.log("\nwhat it will not add up");
  await post("/api/vendors", { name: "Ridgeline Analytics", status: "in_use",
    amount: "900", basis: "per_user", owner: "The IT Manager" });
  await window.go("vendors");
  await until(() => /Ridgeline/.test(said()));
  check("a per-person price is not folded into the yearly total",
    /cannot be added up/.test(said()) && !/no cost recorded/.test(said()),
    "a total with a guess in it is the wrong kind of useful");
  check("the yearly total counts the one that can be", /\$41,500 a year/
    .test(said()), said().match(/\$[\d,]+ a year/)?.[0] || "no total shown");

  console.log("\nuse case potential");
  check("what else a tool could do is listed",
    /already pay for could also do this/.test(said())
      && /Drafting letters/.test(said()),
    "8.6 — check what you have before buying");
  check("and it is listed rather than matched for them",
    /not matched for you/.test(said()),
    "claiming two products overlap is a procurement judgment");

  console.log(`\nerrors             : ${errors.length ? errors.join("; ") : "none"}`);
  if (errors.length) failures.push("script errors");

  console.log();
  if (failures.length) {
    console.log(`FAIL — ${failures.length}: ${failures.slice(0, 4).join("; ")}`);
    process.exit(1);
  }
  console.log("PASS — the registry records, checks their own rules, and says "
              + "what it cannot total");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
