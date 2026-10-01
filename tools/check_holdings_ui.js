/* Does the data warehouse module work as a screen?

   The client: "Data warehouse module is the foundation on which all
   deployments rest, so that must be robust, reliable and helpful."

   Robust and reliable have unit tests. Helpful is a claim about what a person
   sees, and the specific claim here is that the screen leads with what the
   register *found* — a list of holdings is an inventory, a list of holdings
   beside "this one holds student records on an open interface, and you said
   that must never happen" is the reason to keep one.

   Also checks the thing that has bitten this project twice: that a module
   with working endpoints actually has an interface. The reset button had none
   for weeks.

   Needs the subscription on:
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_holdings_ui.js
*/

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
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(46)} ${detail}`);
    if (!ok) failures.push(label);
  };

  await demandScratchContainer();
  const { window, errors } = await boot();
  const doc = window.document;

  const post = (path, body) => window.fetch(
    `${path}?user=sean.ot&email=${encodeURIComponent(HARNESS_EMAIL)}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) });

  // Start clean, so counts mean something.
  const before = await (await window.fetch(
    `/api/holdings?user=sean.ot&email=${encodeURIComponent(HARNESS_EMAIL)}`))
    .json();
  if (before.available === false) {
    console.error("\n  The subscription is off, so there is nothing to walk.");
    console.error('  Set IIA_SUBSCRIPTION=1 on the server and try again.\n');
    process.exit(2);
  }
  for (const row of before.holdings || []) {
    await post("/api/holdings/forget", { id: row.id });
  }

  // The data register sits behind the framework gate like every other paid
  // room, so the scratch tenant needs a framework in draft before any of this
  // is reachable. One answer is enough to put it there.
  await post("/api/versions/answer", { key: "data.never", value: [] });
  if (window.refreshFramework) await window.refreshFramework();

  console.log("the module is reachable by a person");
  const rail = [...doc.querySelectorAll(".rail-item")]
    .map((b) => b.dataset.view);
  check("there is a rail entry for it", rail.includes("holdings"),
    "endpoints with no interface is how the reset button hid for weeks");

  await window.go("holdings");
  await until(() => /What you hold/.test(
    doc.getElementById("view").textContent));
  const said = () => doc.getElementById("view").textContent
    .replace(/\s+/g, " ");
  if (!/What you hold/.test(said())) {
    console.log("\n  the view says instead:\n  " + said().slice(0, 400) + "\n");
  }
  check("the screen opens", /What you hold/.test(said()));
  check("and says what a holding is",
    /whatever the people who use it would call it/.test(said()));

  console.log("\nrecording one");
  doc.querySelector("#dh-name").value = "Permit system";
  doc.querySelector("#dh-contains").value = "Every permit and inspection";
  doc.querySelector("#dh-owner").value = "The Permitting Manager";
  doc.querySelector("#dh-endpoint").value = "https://example.com/permits";
  doc.querySelector("#dh-reachable").value = "api";
  doc.querySelector("#dh-location").value = "gov_cloud";
  doc.querySelector("#dhSave").click();
  await until(() => /Permit system/.test(
    doc.querySelector(".dh-table")?.textContent || ""));
  check("it appears in the register",
    /Permit system/.test(doc.querySelector(".dh-table").textContent));
  check("with the owner against it",
    /The Permitting Manager/.test(doc.querySelector(".dh-table").textContent));
  check("and the tiles count it",
    /1/.test(doc.querySelector(".dh-tile b").textContent),
    doc.querySelector(".dh-tile b").textContent);

  console.log("\nthe monitor");
  const checkBtn = doc.querySelector("[data-check]");
  check("an endpoint gets a check button", !!checkBtn);
  if (checkBtn) {
    checkBtn.click();
    await until(() => /answering|not answering|cannot be checked/.test(
      doc.querySelector(".dh-table")?.textContent || ""));
    const state = doc.querySelector(".dh-state");
    check("and reports in words, not only color", !!state,
      state ? state.textContent.trim() : "no state shown");
  }
  check("it says private networks cannot be watched",
    /agent inside your network/.test(said()),
    "the limitation is stated rather than hidden");

  // Detecting an outage means somebody is told. A state written into a JSON
  // file nobody opens is not detection. A public host on a port nothing
  // listens on resolves fine and then does not answer, which is what a real
  // outage looks like from out here — an unresolvable name is refused instead
  // and never reaches this path.
  //
  // Done by moving the holding that is already answering onto a dead port, so
  // the monitor sees a transition rather than a first reading — "down" is a
  // status, "down since 09:12, it was answering" is an outage.
  const held = await (await window.fetch(
    `/api/holdings?user=sean.ot&email=${encodeURIComponent(HARNESS_EMAIL)}`))
    .json();
  const permit = (held.holdings || []).find((h) => h.name === "Permit system");
  await post("/api/holdings", { id: permit.id, name: "Permit system",
    reachable: "api", owner: "The Permitting Manager",
    endpoint: "https://example.com:81/api" });
  const probe = await (await post("/api/holdings/check",
    { id: permit.id })).json();
  check("a public endpoint that does not answer reads as down",
    probe.result && probe.result.state === "down",
    probe.result ? `${probe.result.state} — ${
      (probe.result.why || "").slice(0, 38)}` : "no result");

  await window.go("holdings");
  await until(() => !!doc.querySelector(".dh-outage"));
  const outage = doc.querySelector(".dh-outage");
  check("and is named at the top of the panel", !!outage,
    outage ? outage.textContent.replace(/\s+/g, " ").trim().slice(0, 56)
           : "no outage line");
  check("the row says when it changed, not only that it is down",
    /since .*was answering/.test(
      doc.querySelector(".dh-table").textContent.replace(/\s+/g, " ")),
    "a status is not an outage without a time");

  console.log("\nwhat the register found");
  // The flag machinery is the reason this module exists, and it fires on the
  // `sensitive` field. That field was settable only by the API — the register
  // could not disagree with the framework by any route a person could take.
  await post("/api/versions/answer",
    { key: "data.never", value: ["personal"] });
  await window.go("holdings");
  await until(() => !!doc.querySelector(".dh-sens"));
  check("the form offers their own 7.1 categories",
    !!doc.querySelector(".dh-sens"),
    "settable in the browser, not only over the API");
  check("and marks the ones they said never",
    /you said never/.test(said()));

  doc.querySelector("[data-edit]").click();
  await settle(300);
  const tick = doc.querySelector('[name="dh-sensitive"][value="personal"]');
  check("the category can be ticked on a holding", !!tick);
  if (tick) {
    tick.checked = true;
    doc.querySelector("#dhSave").click();
    await until(() => !!doc.querySelector(".dh-flags"));
  }
  const flagged = doc.querySelector(".dh-flags");
  check("a sensitive holding on an open interface is flagged", !!flagged,
    flagged ? flagged.textContent.trim().replace(/\s+/g, " ").slice(0, 58)
            : "nothing flagged");
  check("and it names the question it came from",
    /7\.1/.test((flagged || {}).textContent || ""));

  // And it can be taken off again — a tick that cannot be cleared is a
  // register that only ever accumulates alarms.
  doc.querySelector("[data-edit]").click();
  await settle(300);
  const off = doc.querySelector('[name="dh-sensitive"][value="personal"]');
  if (off) {
    off.checked = false;
    doc.querySelector("#dhSave").click();
    await until(() => !/holds names, addresses/i.test(said()));
  }
  check("and unticking it clears the flag",
    !/holds names, addresses/i.test(said()));

  console.log(`\nerrors             : ${errors.length ? errors.join("; ") : "none"}`);
  if (errors.length) failures.push("script errors");

  console.log();
  if (failures.length) {
    console.log(`FAIL — ${failures.length}: ${failures.slice(0, 4).join("; ")}`);
    process.exit(1);
  }
  console.log("PASS — the register records, flags, and says what it cannot do");
  // jsdom leaves timers behind and node will sit there holding them.
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
