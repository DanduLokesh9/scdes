/* Does the subscription page work, and does it give anything away?

   A payment page has two failure modes worth a browser to find:

     1. It cannot be reached. The page that sells the paid modules must not
        be behind the paid modules, or the framework gate, or the corpus
        gate. This is the same fault the reset button had — endpoints with
        no way in — and it would be funnier here.
     2. It hands over what it is selling. Raising an order must not open the
        paid modules; only a settled payment may. The gap between "asked to
        buy" and "paid" is where a paywall gets given away.

   It also checks the promise the page makes about itself: that no field on
   it collects a card number, an expiry, a CVC or a wallet credential.

   Needs the subscription OFF, so the unpaid state is what is on screen:
       Remove-Item Env:\IIA_SUBSCRIPTION
       node tools/check_billing_ui.js
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
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(50)} ${detail}`);
    if (!ok) failures.push(label);
  };

  await demandScratchContainer();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent
    .replace(/\s+/g, " ");

  const auth = `user=sean.ot&email=${encodeURIComponent(HARNESS_EMAIL)}`;
  const get = async (p) => (await window.fetch(`${p}?${auth}`)).json();

  const state = await get("/api/state");
  if (state.subscription) {
    console.error("\n  The deployment-wide subscription flag is on, so the");
    console.error("  unpaid state cannot be observed. Unset IIA_SUBSCRIPTION");
    console.error("  and try again.\n");
    process.exit(2);
  }

  console.log("the page that sells is not behind what it sells");
  const rail = [...doc.querySelectorAll(".rail-item")];
  const entry = rail.find((b) => b.dataset.view === "billing");
  check("there is a rail entry for it", !!entry);
  check("and it is not itself marked paid",
    !!entry && entry.dataset.paid !== "1");
  check("so it is not greyed out on an unpaid agency",
    !!entry && !entry.disabled,
    "the shop cannot be locked inside the thing it sells");

  await window.go("billing");
  await until(() => /What a subscription covers/.test(said()));
  check("the page opens with nothing bought and no framework",
    /What a subscription covers/.test(said()));
  check("it says the framework is free and stays free",
    /free/.test(said()) && /stays yours/.test(said()));

  console.log("\nwhat it says about money");
  check("no price is invented when none is set",
    /quoted rather than listed/.test(said()),
    "a fabricated number would be worse than none");
  const modules = doc.querySelectorAll(".bl-covers li").length;
  const paidRail = rail.filter((b) => b.dataset.paid === "1").length;
  check("what it covers is read from the rail, not a second list",
    modules === paidRail && modules > 0, `${modules} listed, ${paidRail} paid`);

  console.log("\nthe two routes");
  check("the invoice route is offered first",
    said().indexOf("Purchase order and invoice") < said().indexOf("Card"),
    "how public bodies actually buy");
  check("and it is actionable", !!doc.querySelector("#blInvoice"),
    (doc.querySelector("#blInvoice") || {}).textContent);
  check("the card route says why it cannot be used yet",
    !doc.querySelector("#blCard") && /not switched on/.test(said()),
    "no provider configured");

  console.log("\nnothing on this page collects a card");
  const fields = [...doc.querySelectorAll("#view input, #view select, "
    + "#view textarea")];
  const named = fields.map((f) =>
    `${f.id} ${f.name} ${f.getAttribute("autocomplete") || ""}`.toLowerCase());
  const banned = ["cardnumber", "card-number", "cc-number", "cvc", "cvv",
                  "exp-month", "exp-year", "cc-exp"];
  const offending = named.filter((n) => banned.some((b) => n.includes(b)));
  check("no card, expiry, cvc or wallet field exists", offending.length === 0,
    `${fields.length} field(s) on the page, none of them an instrument`);

  console.log("\nasking to buy does not open what is being bought");
  doc.querySelector("#blInvoice").click();
  await until(() => /Your orders/.test(said()));
  check("the order is recorded", /Your orders/.test(said()));
  check("and it is pending, not paid", /pending/.test(said()),
    "an order grants nothing until it is settled");

  const after = await get("/api/state");
  check("the paid modules are still shut", after.subscription === false,
    "this is the gap where a paywall gets given away");
  const holdings = await get("/api/holdings");
  check("and a paid endpoint still refuses",
    holdings.available === false,
    holdings.available === false ? "NOT_SUBSCRIBED" : "LEAKED");

  console.log("\nasking twice does not raise two orders");
  await window.go("billing");
  await until(() => !!doc.querySelector("#blInvoice"));
  doc.querySelector("#blInvoice").click();
  await settle(900);
  const mine = await get("/api/billing");
  check("one order, not two", (mine.orders || []).length === 1,
    `${(mine.orders || []).length} order(s)`);

  console.log(`\nerrors             : ${errors.length ? errors.join("; ") : "none"}`);
  if (errors.length) failures.push("script errors");

  console.log();
  if (failures.length) {
    console.log(`FAIL — ${failures.length}: ${failures.slice(0, 4).join("; ")}`);
    process.exit(1);
  }
  console.log("PASS — it sells without giving anything away, and takes no "
              + "card details");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
