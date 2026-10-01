/* What does the sidebar actually offer, and what does it only appear to?

   It had one live row sitting under a heading that said "subscription" — Agency
   profile, which is free — and nine greyed rooms across two headings with
   nothing saying why they were gray. A sidebar that is four fifths dim and
   unexplained reads as broken software rather than as a price list.

   Usage:  node tools/check_rail.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_rail.js
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

async function boot() {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "jane.smith@des.sc.gov", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
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
  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js",
                   "speech.js", "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  if (window.signInAs) await window.signInAs("sean.ot", "Test", "CTO");
  await new Promise((r) => setTimeout(r, 900));
  return { window, errors };
}

async function main() {
  const { window, errors } = await boot();
  const doc = window.document;
  const rows = [...doc.querySelectorAll(".rail-item[data-view]")];

  console.log("rail items       :", rows.length);
  console.log("live             :",
    rows.filter((b) => !b.disabled).map((b) => b.dataset.view).join(", "));
  console.log("locked           :",
    rows.filter((b) => b.disabled).map((b) => b.dataset.view).join(", "));
  console.log("headings         :",
    [...doc.querySelectorAll(".rail-eyebrow")]
      .map((n) => n.textContent.replace(/\s+/g, " ").trim()).join("  |  "));
  console.log("note under locked:",
    (doc.querySelector(".rail-note") || {}).textContent ? "present" : "MISSING");

  // The defect this check exists for: a paid room rendering live, or a free one
  // rendering under a heading that says it costs money.
  //
  // "Live but paid" is only a defect on a deployment that has not bought the
  // paid modules. Run against a subscribed server — which is how the data
  // warehouse gets walked — every paid room is live and that is the correct
  // answer. The line said "(must be 0)" beside a 1 and exited 0 anyway, which
  // teaches whoever reads it to ignore the number.
  const paid = !!(await (await fetch(`${BASE}/api/state?user=sean.ot`))
    .json()).subscription;
  const liveButPaid = rows.filter((b) => !b.disabled && b.dataset.paid === "1");
  console.log("subscription     :", paid ? "on" : "off");
  console.log("live but paid    :", liveButPaid.length,
    paid ? "(expected — the subscription is on)" : "(must be 0)");
  const wrong = paid ? [] : liveButPaid.map((b) => b.dataset.view);

  const eyebrows = [...doc.querySelectorAll(".rail-eyebrow")];
  const freeGroup = eyebrows[0];
  let inFree = [];
  for (let n = freeGroup.nextElementSibling; n && !n.classList.contains("rail-eyebrow");
       n = n.nextElementSibling) {
    if (n.dataset && n.dataset.view) inFree.push(n.dataset.view);
  }
  console.log("under 'free'     :", inFree.join(", "));
  const paidInFree = inFree.filter((v) =>
    rows.find((b) => b.dataset.view === v && b.dataset.paid === "1"));
  console.log("paid under free  :", paidInFree.length, "(must be 0)");

  console.log("errors           :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));

  // Said its invariants out loud and then exited 0 whatever they were.
  const broken = [...wrong.map((v) => `${v} is live and paid for`),
                  ...paidInFree.map((v) => `${v} is paid and sits under free`),
                  ...(errors.length ? ["script errors"] : [])];
  if (broken.length) {
    console.log(`\nFAIL — ${broken.join("; ")}`);
    process.exit(1);
  }
  console.log("\nPASS — the rail offers what it says it offers");
}

main().catch((e) => { console.error(e); process.exit(1); });
